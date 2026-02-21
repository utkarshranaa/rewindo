#!/usr/bin/env python3
"""Tests for stop hook change detection logic.

Verifies:
- Pure chat (no file changes) → no checkpoint
- Auto-gitignored Claude Code files (.claude/settings.local.json) → no checkpoint
- Explicitly gitignored files → no checkpoint
- Tracked file modified → checkpoint created, files_changed shows only that file
- New untracked non-gitignored file → checkpoint created, file appears in files_changed
- Per-prompt delta: consecutive prompts create separate checkpoints with correct file lists
- Stop hook never writes to stderr (Claude Code shows hook stderr as a visible error)
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
STOP_HOOK = HOOKS_DIR / "log_stop.py"
PROMPT_HOOK = HOOKS_DIR / "log_prompt.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def init_repo(path: Path) -> None:
    """Initialize a git repo with initial commit.

    Pre-commits .gitignore with .claude/data/ so the stop hook's gitignore
    auto-management doesn't modify it (which would itself trigger a checkpoint
    and pollute tests that expect no checkpoint).
    """
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
    (path / "README.md").write_text("# Test\n")
    # Pre-commit .gitignore so the stop hook doesn't modify it at runtime
    (path / ".gitignore").write_text(".claude/data/\n.claude/settings.local.json\n")
    subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, capture_output=True)


def run_prompt_hook(repo: Path, prompt: str, session: str = "s1") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PROMPT_HOOK)],
        input=json.dumps({
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(repo),
            "session_id": session,
            "prompt": prompt,
        }),
        capture_output=True,
        text=True,
    )


def run_stop_hook(repo: Path, session: str = "s1") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(STOP_HOOK)],
        input=json.dumps({
            "hook_event_name": "Stop",
            "cwd": str(repo),
            "session_id": session,
        }),
        capture_output=True,
        text=True,
    )


def timeline_entries(repo: Path) -> list:
    """Return all timeline entries as parsed dicts."""
    timeline = repo / ".claude" / "data" / "timeline.jsonl"
    if not timeline.exists():
        return []
    entries = []
    for line in timeline.read_text().splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def file_paths_in_entry(entry: dict) -> set:
    """Return the set of file paths recorded in a timeline entry."""
    return {f["path"] for f in entry.get("files", [])}


# ---------------------------------------------------------------------------
# Test: pure chat → no checkpoint
# ---------------------------------------------------------------------------

class TestNoPureChat:

    def test_no_checkpoint_when_no_files_changed(self, tmp_path):
        """If nothing changes, the stop hook must not create a checkpoint."""
        init_repo(tmp_path)

        run_prompt_hook(tmp_path, "what is 2+2?")
        # No file changes
        run_stop_hook(tmp_path)

        assert timeline_entries(tmp_path) == [], \
            "No checkpoint should be created when no files changed"

    def test_state_file_cleaned_up_on_no_changes(self, tmp_path):
        """prompt_state.json should be removed even when no checkpoint is created."""
        init_repo(tmp_path)

        run_prompt_hook(tmp_path, "hello")
        state_file = tmp_path / ".claude" / "data" / "prompt_state.json"
        assert state_file.exists(), "prompt_state.json should exist after prompt hook"

        run_stop_hook(tmp_path)
        assert not state_file.exists(), \
            "prompt_state.json should be cleaned up even when no checkpoint created"


# ---------------------------------------------------------------------------
# Test: auto-gitignored and explicitly gitignored files → no checkpoint
# ---------------------------------------------------------------------------

class TestIgnoredFilesNoCheckpoint:

    def test_claude_settings_local_does_not_trigger_checkpoint(self, tmp_path):
        """.claude/settings.local.json (auto-gitignored) must never trigger a checkpoint.

        This is the primary noise file reported: Claude Code writes to this file
        constantly, but it must not cause spurious checkpoints.
        """
        init_repo(tmp_path)

        # Create .claude dir and write the noise file
        (tmp_path / ".claude").mkdir(exist_ok=True)
        (tmp_path / ".claude" / "settings.local.json").write_text('{"theme": "dark"}\n')

        run_prompt_hook(tmp_path, "what is 3+3?")
        # settings.local.json changes again mid-prompt
        (tmp_path / ".claude" / "settings.local.json").write_text('{"theme": "light"}\n')
        run_stop_hook(tmp_path)

        assert timeline_entries(tmp_path) == [], \
            ".claude/settings.local.json must not trigger a checkpoint (it is gitignored)"

    def test_explicitly_gitignored_file_does_not_trigger_checkpoint(self, tmp_path):
        """A file listed in .gitignore must not trigger a checkpoint."""
        init_repo(tmp_path)

        # Add *.log to the pre-existing gitignore (re-commit it)
        (tmp_path / ".gitignore").write_text(".claude/data/\n.claude/settings.local.json\n*.log\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add log to gitignore"], cwd=tmp_path, capture_output=True)

        run_prompt_hook(tmp_path, "just chatting")
        (tmp_path / "app.log").write_text("some log output\n")
        run_stop_hook(tmp_path)

        assert timeline_entries(tmp_path) == [], \
            "Gitignored *.log file must never trigger a checkpoint"

    def test_noise_file_after_real_checkpoint_does_not_trigger_again(self, tmp_path):
        """After a real checkpoint exists, a noise file change must not create another one.

        This is the exact bug: checkpoint #1 captures a noise file via git add -A,
        the noise file then changes, and the stop hook creates checkpoint #2
        even though only the noise file changed.
        """
        init_repo(tmp_path)

        # Prompt 1: modify README.md (working tree, not committed) → real checkpoint
        run_prompt_hook(tmp_path, "update readme")
        (tmp_path / "README.md").write_text("# Updated\n")
        run_stop_hook(tmp_path)
        assert len(timeline_entries(tmp_path)) == 1, "Checkpoint #1 should be created"

        # Now only the auto-gitignored noise file changes
        (tmp_path / ".claude").mkdir(exist_ok=True)
        (tmp_path / ".claude" / "settings.local.json").write_text('{"x": 1}\n')

        run_prompt_hook(tmp_path, "what is 4+4?")
        (tmp_path / ".claude" / "settings.local.json").write_text('{"x": 2}\n')  # changed
        run_stop_hook(tmp_path)

        assert len(timeline_entries(tmp_path)) == 1, \
            "No second checkpoint should be created when only noise file changes"


# ---------------------------------------------------------------------------
# Test: tracked file modified → checkpoint created correctly
# ---------------------------------------------------------------------------

class TestTrackedFileCheckpoint:

    def test_tracked_file_edit_creates_checkpoint(self, tmp_path):
        """Modifying a tracked file (working tree, not committed) must create a checkpoint."""
        init_repo(tmp_path)

        run_prompt_hook(tmp_path, "fix the bug")
        # Modify in working tree only — stop hook should detect this
        (tmp_path / "README.md").write_text("# Updated\n")
        run_stop_hook(tmp_path)

        entries = timeline_entries(tmp_path)
        assert len(entries) == 1, "One checkpoint should be created"

    def test_tracked_file_appears_in_files_changed(self, tmp_path):
        """The modified tracked file must appear in files_changed."""
        init_repo(tmp_path)

        run_prompt_hook(tmp_path, "update readme")
        (tmp_path / "README.md").write_text("# Updated\n")
        run_stop_hook(tmp_path)

        entries = timeline_entries(tmp_path)
        assert len(entries) == 1
        assert "README.md" in file_paths_in_entry(entries[0]), \
            "README.md should be listed in files_changed"

    def test_noise_file_excluded_from_files_changed(self, tmp_path):
        """When a tracked file AND a gitignored noise file both change, only the tracked file appears."""
        init_repo(tmp_path)

        (tmp_path / ".claude").mkdir(exist_ok=True)
        run_prompt_hook(tmp_path, "edit code")
        (tmp_path / "README.md").write_text("# Updated\n")
        (tmp_path / ".claude" / "settings.local.json").write_text('{"x": 1}\n')  # gitignored noise
        run_stop_hook(tmp_path)

        entries = timeline_entries(tmp_path)
        assert len(entries) == 1
        paths = file_paths_in_entry(entries[0])
        assert "README.md" in paths, "Tracked file should appear"
        assert ".claude/settings.local.json" not in paths, \
            "Auto-gitignored noise file must not appear in files_changed"

    def test_git_ref_created(self, tmp_path):
        """A git ref should be created under refs/rewindo/checkpoints/."""
        init_repo(tmp_path)

        run_prompt_hook(tmp_path, "add feature")
        (tmp_path / "README.md").write_text("# Feature\n")
        run_stop_hook(tmp_path)

        result = subprocess.run(
            ["git", "show-ref"],
            cwd=tmp_path, capture_output=True, text=True
        )
        assert "refs/rewindo/checkpoints/1" in result.stdout, \
            "Git ref should be created at refs/rewindo/checkpoints/1"


# ---------------------------------------------------------------------------
# Test: new untracked non-gitignored file → checkpoint created
# ---------------------------------------------------------------------------

class TestNewUntrackedFile:

    def test_new_file_creates_checkpoint(self, tmp_path):
        """Creating a new non-gitignored file (working tree) must trigger a checkpoint."""
        init_repo(tmp_path)

        run_prompt_hook(tmp_path, "create main.py")
        (tmp_path / "main.py").write_text("print('hello')\n")
        run_stop_hook(tmp_path)

        entries = timeline_entries(tmp_path)
        assert len(entries) == 1, "A checkpoint should be created for a new file"

    def test_new_file_appears_in_files_changed(self, tmp_path):
        """The new untracked file must appear in files_changed."""
        init_repo(tmp_path)

        run_prompt_hook(tmp_path, "create main.py")
        (tmp_path / "main.py").write_text("print('hello')\n")
        run_stop_hook(tmp_path)

        entries = timeline_entries(tmp_path)
        assert len(entries) == 1
        assert "main.py" in file_paths_in_entry(entries[0]), \
            "New file main.py should appear in files_changed"

    def test_new_file_not_checkpoint_if_gitignored(self, tmp_path):
        """A new file that is gitignored must not trigger a checkpoint."""
        init_repo(tmp_path)

        # Add *.pyc to gitignore (commit so gitignore modification doesn't count as a change)
        (tmp_path / ".gitignore").write_text(".claude/data/\n.claude/settings.local.json\n*.pyc\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add pyc to gitignore"], cwd=tmp_path, capture_output=True)

        run_prompt_hook(tmp_path, "run something")
        (tmp_path / "module.pyc").write_bytes(b"\x00\x01\x02")  # gitignored
        run_stop_hook(tmp_path)

        assert timeline_entries(tmp_path) == [], \
            "Gitignored new file must not create a checkpoint"


# ---------------------------------------------------------------------------
# Test: per-prompt delta correctness
# ---------------------------------------------------------------------------

class TestPerPromptDelta:

    def test_second_checkpoint_does_not_show_first_prompts_file(self, tmp_path):
        """Checkpoint #2 must not list files that were already captured in checkpoint #1.

        Scenario: prompt 1 creates app.py, prompt 2 creates utils.py.
        Checkpoint #2 should show only utils.py.
        """
        init_repo(tmp_path)

        # Prompt 1: create app.py in working tree (not committed)
        run_prompt_hook(tmp_path, "create app")
        (tmp_path / "app.py").write_text("x = 1\n")
        run_stop_hook(tmp_path)

        entries = timeline_entries(tmp_path)
        assert len(entries) == 1
        assert "app.py" in file_paths_in_entry(entries[0]), \
            "Checkpoint #1 should show app.py"

        # Prompt 2: create utils.py (app.py unchanged since checkpoint #1)
        run_prompt_hook(tmp_path, "add utils")
        (tmp_path / "utils.py").write_text("def helper(): pass\n")
        run_stop_hook(tmp_path)

        entries = timeline_entries(tmp_path)
        assert len(entries) == 2

        checkpoint2_files = file_paths_in_entry(entries[1])
        assert "utils.py" in checkpoint2_files, "Checkpoint #2 should show utils.py"
        assert "app.py" not in checkpoint2_files, \
            "Checkpoint #2 must NOT show app.py — it was already captured in checkpoint #1 " \
            "and hasn't changed since"

    def test_modification_of_previously_new_file_shows_delta(self, tmp_path):
        """If a file created in prompt 1 is modified in prompt 2, checkpoint #2 shows only the delta.

        Scenario: prompt 1 creates app.py with 3 lines → checkpoint #1.
        Prompt 2 adds 1 more line → checkpoint #2 should show +1, not +4.
        """
        init_repo(tmp_path)

        # Prompt 1: create app.py with 3 lines
        run_prompt_hook(tmp_path, "create app")
        (tmp_path / "app.py").write_text("line1\nline2\nline3\n")
        run_stop_hook(tmp_path)

        entries = timeline_entries(tmp_path)
        assert len(entries) == 1
        first_entry_files = entries[0]["files"]
        assert any(f["path"] == "app.py" for f in first_entry_files)
        first_add = next(f["add"] for f in first_entry_files if f["path"] == "app.py")

        # Prompt 2: add one more line to app.py
        run_prompt_hook(tmp_path, "add line 4")
        (tmp_path / "app.py").write_text("line1\nline2\nline3\nline4\n")
        run_stop_hook(tmp_path)

        entries = timeline_entries(tmp_path)
        assert len(entries) == 2

        second_entry_files = entries[1]["files"]
        assert any(f["path"] == "app.py" for f in second_entry_files), \
            "app.py should appear in checkpoint #2 (it was modified)"
        second_add = next(f["add"] for f in second_entry_files if f["path"] == "app.py")

        assert second_add < first_add, \
            f"Checkpoint #2 should show fewer additions ({second_add}) than checkpoint #1 " \
            f"({first_add}) since only 1 line was added in prompt 2"

    def test_tracked_file_per_prompt_delta(self, tmp_path):
        """Two consecutive prompts editing a tracked file each show only their own delta."""
        init_repo(tmp_path)

        # Prompt 1: append 3 lines to README.md (tracked file)
        run_prompt_hook(tmp_path, "expand readme")
        (tmp_path / "README.md").write_text("# Test\nline2\nline3\nline4\n")
        run_stop_hook(tmp_path)

        entries = timeline_entries(tmp_path)
        assert len(entries) == 1
        readme_files1 = [f for f in entries[0]["files"] if f["path"] == "README.md"]
        assert readme_files1, "README.md should be in checkpoint #1"
        add1 = readme_files1[0]["add"]

        # Prompt 2: add one more line
        run_prompt_hook(tmp_path, "add one more line")
        (tmp_path / "README.md").write_text("# Test\nline2\nline3\nline4\nline5\n")
        run_stop_hook(tmp_path)

        entries = timeline_entries(tmp_path)
        assert len(entries) == 2
        readme_files2 = [f for f in entries[1]["files"] if f["path"] == "README.md"]
        assert readme_files2, "README.md should be in checkpoint #2"
        add2 = readme_files2[0]["add"]

        assert add2 < add1, \
            f"Checkpoint #2 delta ({add2} additions) should be less than checkpoint #1 delta " \
            f"({add1} additions) since only 1 line was added in prompt 2"


# ---------------------------------------------------------------------------
# Test: stop hook never writes to stderr
# ---------------------------------------------------------------------------

class TestNoStderr:

    def test_no_stderr_on_normal_run(self, tmp_path):
        """Stop hook must produce no stderr output during a normal run."""
        init_repo(tmp_path)

        run_prompt_hook(tmp_path, "write some code")
        (tmp_path / "main.py").write_text("print('hello')\n")
        result = run_stop_hook(tmp_path)

        assert result.stderr == "", \
            f"Stop hook wrote to stderr on normal run: {result.stderr!r}"

    def test_no_stderr_on_no_changes(self, tmp_path):
        """Stop hook must produce no stderr when there are no file changes."""
        init_repo(tmp_path)

        run_prompt_hook(tmp_path, "what is 2+2?")
        result = run_stop_hook(tmp_path)

        assert result.stderr == "", \
            f"Stop hook wrote to stderr when no changes: {result.stderr!r}"

    def test_no_stderr_when_prompt_save_fails(self, tmp_path):
        """Stop hook must not write to stderr even if the prompts directory is unwritable.

        This specifically tests the save_full_prompt error path — previously it had
        a print(..., file=sys.stderr) that would surface as a visible hook error.
        """
        import stat
        init_repo(tmp_path)

        # Create a read-only prompts directory so save_full_prompt raises
        prompts_dir = tmp_path / ".claude" / "data" / "prompts"
        prompts_dir.mkdir(parents=True)
        prompts_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x, no write

        run_prompt_hook(tmp_path, "write code")
        (tmp_path / "app.py").write_text("x = 1\n")
        result = run_stop_hook(tmp_path)

        # Restore permissions so tmp_path cleanup can delete it
        prompts_dir.chmod(stat.S_IRWXU)

        assert result.stderr == "", \
            f"Stop hook wrote to stderr when prompt save failed: {result.stderr!r}"


# ---------------------------------------------------------------------------
# Test: .git/info/exclude management (no tracked .gitignore modification)
# ---------------------------------------------------------------------------

def init_repo_bare(path: Path) -> None:
    """Initialize a repo with NO rewindo gitignore entries — simulates a fresh project.

    The stop hook must handle this without modifying any tracked file.
    """
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
    (path / "README.md").write_text("# Test\n")
    (path / ".gitignore").write_text("*.pyc\n__pycache__/\n")
    subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, capture_output=True)


class TestGitInfoExclude:

    def test_fresh_project_pure_chat_no_checkpoint(self, tmp_path):
        """In a project with no rewindo gitignore entries, pure chat must NOT
        create a checkpoint. The stop hook uses .git/info/exclude (not .gitignore)
        to avoid spurious tracked-file modifications.
        """
        init_repo_bare(tmp_path)

        run_prompt_hook(tmp_path, "what is 2+2?")
        # No code changes
        run_stop_hook(tmp_path)

        assert timeline_entries(tmp_path) == [], \
            "Pure-chat on a fresh project must not create a checkpoint"

    def test_gitignore_not_modified_by_stop_hook(self, tmp_path):
        """The stop hook must never modify .gitignore — only .git/info/exclude."""
        import hashlib
        init_repo_bare(tmp_path)

        original_content = (tmp_path / ".gitignore").read_text()
        original_hash = hashlib.md5(original_content.encode()).hexdigest()

        run_prompt_hook(tmp_path, "what is 2+2?")
        run_stop_hook(tmp_path)

        current_content = (tmp_path / ".gitignore").read_text()
        current_hash = hashlib.md5(current_content.encode()).hexdigest()

        assert current_hash == original_hash, \
            "Stop hook must not modify .gitignore (use .git/info/exclude instead)"

    def test_git_info_exclude_written(self, tmp_path):
        """After the stop hook runs, .git/info/exclude should contain the rewindo paths."""
        init_repo_bare(tmp_path)

        run_prompt_hook(tmp_path, "hello")
        run_stop_hook(tmp_path)

        exclude_file = tmp_path / ".git" / "info" / "exclude"
        assert exclude_file.exists(), ".git/info/exclude should be created"
        content = exclude_file.read_text()
        assert ".claude/data/" in content, ".claude/data/ should be in .git/info/exclude"
        assert ".claude/settings.local.json" in content, \
            ".claude/settings.local.json should be in .git/info/exclude"

    def test_claude_data_files_not_seen_as_untracked_after_exclude(self, tmp_path):
        """After the stop hook writes .git/info/exclude, .claude/data/ files
        should not be visible as untracked — so they never trigger false checkpoints.
        """
        init_repo_bare(tmp_path)

        # Run stop hook once so it writes .git/info/exclude
        run_prompt_hook(tmp_path, "setup run")
        run_stop_hook(tmp_path)

        # Now simulate the next prompt — .claude/data/ files exist but should be excluded
        run_prompt_hook(tmp_path, "what is 3+3?")
        run_stop_hook(tmp_path)

        # Still no checkpoint — .claude/data/ files are ignored
        assert timeline_entries(tmp_path) == [], \
            ".claude/data/ files must not trigger a checkpoint after .git/info/exclude is written"
