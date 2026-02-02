#!/usr/bin/env python3
"""Unit tests for Rewindo core library."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from rewindo import Rewindo


class TestRewindoInit:
    """Test Rewindo initialization."""

    def test_init_creates_data_directories(self, tmp_path):
        """Test that init creates data directories."""
        # Create a git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)

        data_dir = tmp_path / ".claude" / "data"

        r = Rewindo(cwd=str(tmp_path))

        assert data_dir.exists()
        assert (data_dir / "prompts").exists()
        assert (data_dir / "diffs").exists()

    def test_init_fails_without_git(self, tmp_path):
        """Test that init fails if not a git repo."""
        with pytest.raises(ValueError, match="Not a git repository"):
            Rewindo(cwd=str(tmp_path))


class TestTimelineOperations:
    """Test timeline read/write operations."""

    def test_list_empty_timeline(self, tmp_path):
        """Test listing when timeline is empty."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        entries = r.list_entries()

        assert entries == []

    def test_list_returns_entries(self, tmp_path):
        """Test listing timeline entries."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        # Create test timeline
        timeline_path = tmp_path / ".claude" / "data" / "timeline.jsonl"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)

        entry1 = {
            "id": 1,
            "ts": "2026-01-30T12:00:00",
            "prompt": "First prompt",
            "files": [{"path": "test.py", "add": 5, "del": 0}],
            "labels": []
        }
        entry2 = {
            "id": 2,
            "ts": "2026-01-30T12:01:00",
            "prompt": "Second prompt",
            "files": [{"path": "test2.py", "add": 3, "del": 1}],
            "labels": ["working"]
        }

        with open(timeline_path, "w") as f:
            f.write(json.dumps(entry1) + "\n")
            f.write(json.dumps(entry2) + "\n")

        entries = r.list_entries()

        assert len(entries) == 2
        assert entries[0]["id"] == 2  # Newest first
        assert entries[1]["id"] == 1
        assert entries[0]["prompt_snippet"] == "Second prompt"
        assert entries[1]["prompt_snippet"] == "First prompt"

    def test_list_with_limit(self, tmp_path):
        """Test listing with limit."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        timeline_path = tmp_path / ".claude" / "data" / "timeline.jsonl"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)

        for i in range(5):
            entry = {
                "id": i + 1,
                "ts": f"2026-01-30T12:0{i}:00",
                "prompt": f"Prompt {i+1}",
                "files": [],
                "labels": []
            }
            with open(timeline_path, "a") as f:
                f.write(json.dumps(entry) + "\n")

        entries = r.list_entries(limit=3)

        assert len(entries) == 3
        assert entries[0]["id"] == 5

    def test_list_with_query(self, tmp_path):
        """Test listing with search query."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        timeline_path = tmp_path / ".claude" / "data" / "timeline.jsonl"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)

        with open(timeline_path, "w") as f:
            f.write(json.dumps({
                "id": 1,
                "ts": "2026-01-30T12:00:00",
                "prompt": "Add authentication",
                "files": [],
                "labels": []
            }) + "\n")
            f.write(json.dumps({
                "id": 2,
                "ts": "2026-01-30T12:01:00",
                "prompt": "Add database",
                "files": [],
                "labels": []
            }) + "\n")

        entries = r.list_entries(query="authentication")

        assert len(entries) == 1
        assert entries[0]["id"] == 1

    def test_get_entry_by_id(self, tmp_path):
        """Test getting a specific entry."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        timeline_path = tmp_path / ".claude" / "data" / "timeline.jsonl"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)

        entry1 = {
            "id": 1,
            "ts": "2026-01-30T12:00:00",
            "prompt": "Test prompt",
            "files": [],
            "labels": [],
            "checkpoint_ref": "refs/rewindo/checkpoints/1"
        }

        with open(timeline_path, "w") as f:
            f.write(json.dumps(entry1) + "\n")

        entry = r.get_entry(1)

        assert entry is not None
        assert entry["id"] == 1
        assert entry["prompt"] == "Test prompt"

    def test_get_entry_not_found(self, tmp_path):
        """Test getting non-existent entry."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        entry = r.get_entry(999)

        assert entry is None

    def _setup_git_repo(self, path):
        """Helper to set up a git repo."""
        subprocess.run(["git", "init"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)

        # Create initial commit
        (path / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, capture_output=True)


class TestPromptRetrieval:
    """Test prompt retrieval with bounds."""

    def test_get_prompt_from_file(self, tmp_path):
        """Test getting prompt from file."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        # Create prompt file
        prompt_path = tmp_path / ".claude" / "data" / "prompts" / "00001.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text("This is a test prompt with some text")

        prompt = r.get_prompt(1)

        assert prompt == "This is a test prompt with some text"

    def test_get_prompt_with_max_chars(self, tmp_path):
        """Test getting prompt with character limit."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        prompt_path = tmp_path / ".claude" / "data" / "prompts" / "00001.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text("This is a test prompt with some text")

        prompt = r.get_prompt(1, max_chars=10)

        assert prompt == "This is a "
        assert len(prompt) <= 10

    def test_get_prompt_with_offset(self, tmp_path):
        """Test getting prompt with offset."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        prompt_path = tmp_path / ".claude" / "data" / "prompts" / "00001.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text("0123456789")

        prompt = r.get_prompt(1, max_chars=5, offset=5)

        assert prompt == "56789"

    def test_get_prompt_from_timeline(self, tmp_path):
        """Test getting prompt from timeline entry."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        timeline_path = tmp_path / ".claude" / "data" / "timeline.jsonl"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "id": 1,
            "ts": "2026-01-30T12:00:00",
            "prompt": "Prompt from timeline",
            "files": [],
            "labels": []
        }

        with open(timeline_path, "w") as f:
            f.write(json.dumps(entry) + "\n")

        prompt = r.get_prompt(1)

        assert prompt == "Prompt from timeline"

    def _setup_git_repo(self, path):
        """Helper to set up a git repo."""
        subprocess.run(["git", "init"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
        (path / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, capture_output=True)


class TestDiffRetrieval:
    """Test diff retrieval with bounds."""

    def test_get_diff_from_file(self, tmp_path):
        """Test getting diff from file."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        # Create diff file
        diff_path = tmp_path / ".claude" / "data" / "diffs" / "00001.patch"
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_content = """diff --git a/test.py b/test.py
index abc123..def456 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 def foo():
     pass
+def bar():
+    pass
"""
        diff_path.write_text(diff_content)

        diff = r.get_diff(1)

        assert "test.py" in diff
        assert "def bar():" in diff

    def test_get_diff_with_max_lines(self, tmp_path):
        """Test getting diff with line limit."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        diff_path = tmp_path / ".claude" / "data" / "diffs" / "00001.patch"
        diff_path.parent.mkdir(parents=True, exist_ok=True)

        # Create 10-line diff
        lines = [f"line {i}\n" for i in range(10)]
        diff_path.write_text("".join(lines))

        diff = r.get_diff(1, max_lines=5)

        assert len(diff.strip().split("\n")) <= 5

    def test_get_diff_with_file_filter(self, tmp_path):
        """Test filtering diff by file."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        diff_path = tmp_path / ".claude" / "data" / "diffs" / "00001.patch"
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_content = """diff --git a/file1.py b/file1.py
index abc..def 100644
--- a/file1.py
+++ b/file1.py
@@ -1 +1,2 @@
+content1
diff --git a/file2.py b/file2.py
index abc..def 100644
--- a/file2.py
+++ b/file2.py
@@ -1 +1,2 @@
+content2
"""
        diff_path.write_text(diff_content)

        diff = r.get_diff(1, file_path="file1.py")

        assert "file1.py" in diff
        assert "content1" in diff
        assert "file2.py" not in diff
        assert "content2" not in diff

    def _setup_git_repo(self, path):
        """Helper to set up a git repo."""
        subprocess.run(["git", "init"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
        (path / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, capture_output=True)


class TestLabels:
    """Test label operations."""

    def test_add_label(self, tmp_path):
        """Test adding a label to an entry."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        timeline_path = tmp_path / ".claude" / "data" / "timeline.jsonl"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "id": 1,
            "ts": "2026-01-30T12:00:00",
            "prompt": "Test",
            "files": [],
            "labels": []
        }

        with open(timeline_path, "w") as f:
            f.write(json.dumps(entry) + "\n")

        result = r.add_label(1, "working")

        assert result is True

        # Verify label was added
        with open(timeline_path) as f:
            updated = json.loads(f.read())
        assert "working" in updated["labels"]

    def test_add_label_to_nonexistent_entry(self, tmp_path):
        """Test adding label to non-existent entry."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        result = r.add_label(999, "working")

        assert result is False

    def test_add_duplicate_label(self, tmp_path):
        """Test that duplicate labels aren't added."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        timeline_path = tmp_path / ".claude" / "data" / "timeline.jsonl"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "id": 1,
            "ts": "2026-01-30T12:00:00",
            "prompt": "Test",
            "files": [],
            "labels": ["working"]
        }

        with open(timeline_path, "w") as f:
            f.write(json.dumps(entry) + "\n")

        r.add_label(1, "working")

        # Verify no duplicate
        with open(timeline_path) as f:
            updated = json.loads(f.read())
        assert updated["labels"].count("working") == 1

    def _setup_git_repo(self, path):
        """Helper to set up a git repo."""
        subprocess.run(["git", "init"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
        (path / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, capture_output=True)


class TestSearch:
    """Test search functionality."""

    def test_search_finds_matches(self, tmp_path):
        """Test that search finds matching prompts."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        timeline_path = tmp_path / ".claude" / "data" / "timeline.jsonl"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)

        entries = [
            {"id": 1, "ts": "2026-01-30T12:00:00", "prompt": "Add authentication", "files": [], "labels": []},
            {"id": 2, "ts": "2026-01-30T12:01:00", "prompt": "Add database", "files": [], "labels": []},
            {"id": 3, "ts": "2026-01-30T12:02:00", "prompt": "Add API", "files": [], "labels": []}
        ]

        with open(timeline_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        results = r.search("auth")

        assert len(results) == 1
        assert results[0]["id"] == 1

    def test_search_case_insensitive(self, tmp_path):
        """Test that search is case insensitive."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        timeline_path = tmp_path / ".claude" / "data" / "timeline.jsonl"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)

        with open(timeline_path, "w") as f:
            f.write(json.dumps({
                "id": 1,
                "ts": "2026-01-30T12:00:00",
                "prompt": "Add AUTHENTICATION module",
                "files": [],
                "labels": []
            }) + "\n")

        results = r.search("authentication")

        assert len(results) == 1

    def test_search_no_matches(self, tmp_path):
        """Test search with no matches."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        timeline_path = tmp_path / ".claude" / "data" / "timeline.jsonl"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)

        with open(timeline_path, "w") as f:
            f.write(json.dumps({
                "id": 1,
                "ts": "2026-01-30T12:00:00",
                "prompt": "Add authentication",
                "files": [],
                "labels": []
            }) + "\n")

        results = r.search("xyz")

        assert len(results) == 0

    def _setup_git_repo(self, path):
        """Helper to set up a git repo."""
        subprocess.run(["git", "init"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
        (path / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, capture_output=True)


class TestDoctor:
    """Test health check functionality."""

    def test_doctor_healthy_repo(self, tmp_path):
        """Test doctor on healthy repo."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        issues = r.doctor()

        assert issues == []

    def test_doctor_no_timeline(self, tmp_path):
        """Test doctor detects missing timeline when refs exist."""
        self._setup_git_repo(tmp_path)

        # Create a checkpoint ref (simulating a checkpoint without timeline)
        result = subprocess.run(
            ["git", "update-ref", "refs/rewindo/checkpoints/1", "HEAD"],
            cwd=tmp_path,
            capture_output=True
        )

        # Remove timeline file
        (tmp_path / ".claude" / "data" / "timeline.jsonl").unlink(missing_ok=True)

        r = Rewindo(cwd=str(tmp_path))
        issues = r.doctor()

        # Should report orphaned refs or missing timeline
        assert len(issues) > 0

    def test_doctor_invalid_json(self, tmp_path):
        """Test doctor detects invalid JSON."""
        self._setup_git_repo(tmp_path)

        # Write invalid JSONL
        timeline_path = tmp_path / ".claude" / "data" / "timeline.jsonl"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)
        with open(timeline_path, "w") as f:
            f.write("invalid json\n")

        r = Rewindo(cwd=str(tmp_path))
        issues = r.doctor()

        assert any("Invalid JSON" in issue for issue in issues)

    def _setup_git_repo(self, path):
        """Helper to set up a git repo."""
        subprocess.run(["git", "init"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
        (path / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, capture_output=True)


class TestExport:
    """Test export functionality."""

    def test_export_entry(self, tmp_path):
        """Test exporting an entry."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        # Create timeline entry
        timeline_path = tmp_path / ".claude" / "data" / "timeline.jsonl"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "id": 1,
            "ts": "2026-01-30T12:00:00",
            "prompt": "Test prompt for export",
            "prompt_ref": "prompts/00001.txt",
            "checkpoint_ref": "refs/rewindo/checkpoints/1",
            "checkpoint_sha": "abc123",
            "files": [{"path": "test.py", "add": 5, "del": 0}],
            "diff_path": "diffs/00001.patch",
            "labels": ["working"],
            "notes": ""
        }

        with open(timeline_path, "w") as f:
            f.write(json.dumps(entry) + "\n")

        # Create prompt and diff files
        (tmp_path / ".claude" / "data" / "prompts" / "00001.txt").write_text("Full prompt text")
        (tmp_path / ".claude" / "data" / "diffs" / "00001.patch").write_text("diff --git a/test.py")

        # Export
        output_dir = r.export_entry(1)

        assert output_dir.exists()
        assert (output_dir / "prompt.txt").exists()
        assert (output_dir / "diff.patch").exists()
        assert (output_dir / "meta.json").exists()

        # Verify content
        assert (output_dir / "prompt.txt").read_text() == "Full prompt text"
        assert (output_dir / "diff.patch").read_text() == "diff --git a/test.py"

        with open(output_dir / "meta.json") as f:
            meta = json.load(f)
        assert meta["id"] == 1
        assert meta["prompt"] == "Test prompt for export"

    def test_export_nonexistent_entry(self, tmp_path):
        """Test exporting non-existent entry."""
        self._setup_git_repo(tmp_path)
        r = Rewindo(cwd=str(tmp_path))

        with pytest.raises(ValueError, match="Entry #999 not found"):
            r.export_entry(999)

    def _setup_git_repo(self, path):
        """Helper to set up a git repo."""
        subprocess.run(["git", "init"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
        (path / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, capture_output=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
