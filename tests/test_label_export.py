#!/usr/bin/env python3
"""Integration tests for rewindo label and export CLI commands."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


def run_git(cwd: Path, *args):
    return subprocess.run(
        ["git"] + list(args),
        cwd=cwd, capture_output=True, text=True
    )


def run_cli(cwd: Path, *args):
    env = {**subprocess.os.environ, "PYTHONPATH": str(PROJECT_ROOT / "lib")}
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "bin" / "rewindo"),
         "--cwd", str(cwd)] + list(args),
        cwd=cwd, capture_output=True, text=True, env=env
    )
    return result.returncode, result.stdout, result.stderr


def setup_repo_with_checkpoint(tmp_path: Path) -> Path:
    """Create a git repo with one rewindo checkpoint and return its path."""
    repo = tmp_path / "repo"
    repo.mkdir()

    run_git(repo, "init")
    run_git(repo, "config", "user.email", "test@test.com")
    run_git(repo, "config", "user.name", "Test")

    (repo / "README.md").write_text("# Project\n")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", "Initial commit")

    # Create checkpoint via CLI (must commit changes so capture-stop detects them)
    run_cli(repo, "capture-prompt", "--prompt", "Add hello function")
    (repo / "hello.py").write_text("def hello():\n    return 'hi'\n")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", "Add hello function")
    run_cli(repo, "capture-stop")

    return repo


# ---------------------------------------------------------------------------
# label command
# ---------------------------------------------------------------------------

class TestLabelCommand:

    def test_label_adds_to_entry(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        rc, stdout, stderr = run_cli(repo, "label", "1", "milestone")
        assert rc == 0

    def test_label_visible_in_show(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        run_cli(repo, "label", "1", "release-v1")
        rc, stdout, stderr = run_cli(repo, "show", "1")
        assert rc == 0
        assert "release-v1" in stdout

    def test_label_visible_in_list(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        run_cli(repo, "label", "1", "important")
        rc, stdout, stderr = run_cli(repo, "list")
        assert rc == 0
        assert "important" in stdout

    def test_multiple_labels_on_same_entry(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        run_cli(repo, "label", "1", "alpha")
        run_cli(repo, "label", "1", "beta")
        rc, stdout, stderr = run_cli(repo, "show", "1")
        assert "alpha" in stdout
        assert "beta" in stdout

    def test_duplicate_label_does_not_duplicate(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        run_cli(repo, "label", "1", "dup")
        run_cli(repo, "label", "1", "dup")

        timeline = repo / ".claude" / "data" / "timeline.jsonl"
        entries = [json.loads(l) for l in timeline.read_text().splitlines() if l.strip()]
        entry = next(e for e in entries if e["id"] == 1)
        assert entry["labels"].count("dup") == 1

    def test_label_nonexistent_entry_fails_gracefully(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        rc, stdout, stderr = run_cli(repo, "label", "999", "ghost")
        assert rc != 0 or "not found" in stdout.lower() or "not found" in stderr.lower()

    def test_label_with_hyphens_and_underscores(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        rc, stdout, stderr = run_cli(repo, "label", "1", "my-label_v2")
        assert rc == 0

    def test_label_persists_across_sessions(self, tmp_path):
        """Label written to timeline.jsonl should survive re-reading."""
        repo = setup_repo_with_checkpoint(tmp_path)
        run_cli(repo, "label", "1", "persistent")

        timeline = repo / ".claude" / "data" / "timeline.jsonl"
        entries = [json.loads(l) for l in timeline.read_text().splitlines() if l.strip()]
        entry = next(e for e in entries if e["id"] == 1)
        assert "persistent" in entry["labels"]


# ---------------------------------------------------------------------------
# export command
# ---------------------------------------------------------------------------

class TestExportCommand:

    def test_export_exits_zero(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        rc, stdout, stderr = run_cli(repo, "export", "1")
        assert rc == 0

    def test_export_produces_output(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        rc, stdout, stderr = run_cli(repo, "export", "1")
        assert stdout.strip() != ""

    def _get_export_dir(self, repo: Path, entry_id: int) -> Path:
        """Return the export directory for an entry."""
        return repo / f"export-{entry_id:05d}"

    def _export_bundle_text(self, repo: Path, entry_id: int) -> str:
        """Run export and return all text from the export directory."""
        run_cli(repo, "export", str(entry_id))
        export_dir = self._get_export_dir(repo, entry_id)
        texts = []
        if export_dir.exists():
            for f in export_dir.iterdir():
                if f.is_file():
                    texts.append(f.read_text(errors="replace"))
        return "\n".join(texts)

    def test_export_includes_prompt(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        content = self._export_bundle_text(repo, 1)
        assert "Add hello function" in content

    def test_export_includes_checkpoint_ref(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        content = self._export_bundle_text(repo, 1)
        assert "refs/rewindo/checkpoints" in content or "checkpoint" in content.lower()

    def test_export_nonexistent_entry_fails_gracefully(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        rc, stdout, stderr = run_cli(repo, "export", "999")
        assert rc != 0 or "not found" in stdout.lower() or "not found" in stderr.lower()

    def test_export_includes_files_changed(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        content = self._export_bundle_text(repo, 1)
        assert "hello.py" in content

    def test_export_after_label_includes_label(self, tmp_path):
        repo = setup_repo_with_checkpoint(tmp_path)
        run_cli(repo, "label", "1", "exported-label")
        content = self._export_bundle_text(repo, 1)
        assert "exported-label" in content
