#!/usr/bin/env python3
"""Unit tests for WorkingTreeDetector."""

import subprocess
import sys
import tempfile
from pathlib import Path

# Add lib to path
LIB_DIR = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB_DIR))

from detector import WorkingTreeDetector, FileChange


def run_git(cwd: Path, *args):
    """Run git command."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout, result.stderr


def test_is_dirty_from_clean():
    """Test is_dirty_from returns False for clean tree."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file.txt").write_text("hello\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Get HEAD SHA
        _, sha, _ = run_git(test_repo, "rev-parse", "HEAD")
        sha = sha.strip()

        # Create detector
        detector = WorkingTreeDetector(test_repo)

        # Should not be dirty
        assert not detector.is_dirty_from(sha), "Clean tree should not be dirty"

        print("[OK] is_dirty_from returns False for clean tree")


def test_is_dirty_from_modified():
    """Test is_dirty_from returns True for modified files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file.txt").write_text("hello\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Get HEAD SHA
        _, sha, _ = run_git(test_repo, "rev-parse", "HEAD")
        sha = sha.strip()

        # Modify file
        (test_repo / "file.txt").write_text("hello world\n")

        # Create detector
        detector = WorkingTreeDetector(test_repo)

        # Should be dirty
        assert detector.is_dirty_from(sha), "Modified file should be dirty"

        print("[OK] is_dirty_from returns True for modified files")


def test_is_dirty_from_new_file():
    """Test is_dirty_from returns True for new files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file.txt").write_text("hello\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Get HEAD SHA
        _, sha, _ = run_git(test_repo, "rev-parse", "HEAD")
        sha = sha.strip()

        # Create new file
        (test_repo / "new.txt").write_text("new\n")

        # Create detector
        detector = WorkingTreeDetector(test_repo)

        # Should be dirty
        assert detector.is_dirty_from(sha), "New file should be dirty"

        print("[OK] is_dirty_from returns True for new files")


def test_get_changed_files():
    """Test get_changed_files returns correct list."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file1.txt").write_text("hello\n")
        (test_repo / "file2.txt").write_text("world\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Make changes
        (test_repo / "file1.txt").write_text("hello world\n")  # Modified
        (test_repo / "file2.txt").unlink()  # Deleted
        (test_repo / "file3.txt").write_text("new\n")  # Added

        # Create detector
        detector = WorkingTreeDetector(test_repo)

        # Get changes
        changes = detector.get_changed_files()

        # Check we got all changes
        paths = {c.path for c in changes}
        assert "file1.txt" in paths, "Should have modified file"
        assert "file2.txt" in paths, "Should have deleted file"
        assert "file3.txt" in paths, "Should have new file"

        # Check statuses
        for change in changes:
            if change.path == "file1.txt":
                assert change.status == 'M', f"file1 should be modified, got {change.status}"
            elif change.path == "file2.txt":
                assert change.status == 'D', f"file2 should be deleted, got {change.status}"
            elif change.path == "file3.txt":
                # New files show as '??' (untracked) before staging
                assert change.status in ('??', 'A'), f"file3 should be untracked or added, got {change.status}"

        print("[OK] get_changed_files returns correct list")


def test_get_file_changes_summary():
    """Test get_file_changes_summary returns human-readable summary."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file.txt").write_text("hello\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Make changes
        (test_repo / "file.txt").write_text("hello world\n")  # Modified
        (test_repo / "new.txt").write_text("new\n")  # Added

        # Create detector
        detector = WorkingTreeDetector(test_repo)

        # Get summary
        summary = detector.get_file_changes_summary()

        assert "2 files changed" in summary, f"Expected '2 files changed', got: {summary}"

        print(f"[OK] get_file_changes_summary: {summary}")


def test_has_uncommitted_changes():
    """Test has_uncommitted_changes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file.txt").write_text("hello\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Create detector
        detector = WorkingTreeDetector(test_repo)

        # Should not have uncommitted changes
        assert not detector.has_uncommitted_changes(), "Should not have uncommitted changes"

        # Make a change
        (test_repo / "file.txt").write_text("hello world\n")

        # Should now have uncommitted changes
        assert detector.has_uncommitted_changes(), "Should have uncommitted changes after modification"

        print("[OK] has_uncommitted_changes works correctly")


def test_get_current_head_sha():
    """Test get_current_head_sha."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create detector
        detector = WorkingTreeDetector(test_repo)

        # No commits yet
        sha = detector.get_current_head_sha()
        assert sha is None, "SHA should be None before any commits"

        # Create initial commit
        (test_repo / "file.txt").write_text("hello\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Should now have a SHA
        sha = detector.get_current_head_sha()
        assert sha is not None, "SHA should not be None after commit"
        assert len(sha) == 40, f"SHA should be 40 chars, got {len(sha)}"

        print("[OK] get_current_head_sha works correctly")


def test_get_numstat():
    """Test get_numstat returns line statistics."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file.txt").write_text("hello\nworld\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Get HEAD SHA
        _, sha, _ = run_git(test_repo, "rev-parse", "HEAD")
        sha = sha.strip()

        # Modify file: delete one line, add one line
        (test_repo / "file.txt").write_text("hello\nfoo\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Changes")

        # Create detector
        detector = WorkingTreeDetector(test_repo)

        # Get numstat from initial commit
        numstat = detector.get_numstat(sha)

        # Should have one file with stats
        assert len(numstat) == 1, f"Expected 1 file, got {len(numstat)}"
        assert numstat[0]["path"] == "file.txt"
        assert numstat[0]["additions"] == 1, f"Expected 1 addition, got {numstat[0]['additions']}"
        assert numstat[0]["deletions"] == 1, f"Expected 1 deletion, got {numstat[0]['deletions']}"

        print("[OK] get_numstat returns correct statistics")


def main():
    """Run all tests."""
    print("=" * 60)
    print("WorkingTreeDetector Unit Tests")
    print("=" * 60)

    test_is_dirty_from_clean()
    test_is_dirty_from_modified()
    test_is_dirty_from_new_file()
    test_get_changed_files()
    test_get_file_changes_summary()
    test_has_uncommitted_changes()
    test_get_current_head_sha()
    test_get_numstat()

    print("=" * 60)
    print("[SUCCESS] All WorkingTreeDetector tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
