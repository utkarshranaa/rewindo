#!/usr/bin/env python3
"""Integration test for dirty working tree handling.

This test verifies behavior when there are uncommitted changes before
a revert operation, including proper handling of stashing, warnings, and
confirmation prompts.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

# Add lib to path
LIB_DIR = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB_DIR))


def run_git(cwd: Path, *args):
    """Run git command."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout, result.stderr


def run_cli(cwd: Path, *args, input_text: str = None):
    """Run rewindo CLI command."""
    project_root = Path(__file__).parent.parent
    env = {**subprocess.os.environ, 'PYTHONPATH': str(project_root / 'lib')}
    result = subprocess.run(
        [sys.executable, str(project_root / "bin" / "rewindo"), "--cwd", str(cwd)] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        input=input_text
    )
    return result.returncode, result.stdout, result.stderr


def get_file_content(cwd: Path, path: str) -> str:
    """Get file content."""
    file_path = cwd / path
    if file_path.exists():
        return file_path.read_text()
    return ""


def test_revert_with_uncommitted_changes_warning():
    """Test that revert warns about uncommitted changes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-dirty"
        test_repo.mkdir()

        print("\n=== Phase 8.2: Dirty Working Tree Tests ===\n")

        # Initialize
        print("[1/6] Initializing repo...")
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("v1\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v1")

        # Create checkpoint
        print("[2/6] Creating checkpoint...")
        run_cli(test_repo, "capture-prompt", "--prompt", "Add feature")
        (test_repo / "file.txt").write_text("v2\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v2")
        run_cli(test_repo, "capture-stop")

        # Make uncommitted changes (dirty working tree)
        print("[3/6] Making uncommitted changes...")
        (test_repo / "file.txt").write_text("uncommitted changes\n")

        # Verify working tree is dirty
        rc, stdout, stderr = run_git(test_repo, "status", "--porcelain")
        assert stdout.strip(), "Working tree should be dirty"
        print("       [OK] Working tree is dirty")

        # Test: Revert without --yes should warn
        print("[4/6] TEST: Revert without --yes shows warning...")
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", input_text="n\n")

        # Should show confirmation prompt
        assert "Continue?" in stdout or "continue" in stdout.lower(), \
            "Should prompt for confirmation"
        print("       [OK] Confirmation prompt shown")

        # Uncommitted changes should still exist after aborting
        content = get_file_content(test_repo, "file.txt")
        assert "uncommitted changes" in content, \
            "Uncommitted changes should remain after aborting revert"
        print("       [OK] Uncommitted changes preserved after abort")

        # Test: Revert with --yes should proceed
        print("[5/6] TEST: Revert with --yes proceeds...")
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--yes")

        # Revert should succeed
        assert rc == 0, f"Revert should succeed: {stderr}"

        # File should be reverted to v2 (checkpoint #1's state, uncommitted changes lost)
        content = get_file_content(test_repo, "file.txt")
        assert content == "v2\n", f"File should be v2 after revert to #1, got: {repr(content)}"
        print("       [OK] Revert with --yes discards uncommitted changes")

        print("[6/6] TEST: Git status after revert...")
        rc, stdout, stderr = run_git(test_repo, "status", "--porcelain")
        # Filter out .claude files (Rewindo internal files that may be untracked)
        non_claude_lines = [line for line in stdout.strip().split('\n') if line and '.claude' not in line]
        assert not non_claude_lines, f"Working tree should be clean after revert, got: {non_claude_lines}"
        print("       [OK] Working tree is clean after revert")

        print("\n[SUCCESS] Uncommitted changes warning test passed!")


def test_revert_preserves_timeline_with_dirty_tree():
    """Test that timeline is preserved even with dirty working tree."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-timeline"
        test_repo.mkdir()

        print("\n[1/4] Test timeline preservation with dirty tree...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("v1\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v1")

        # Create two checkpoints
        run_cli(test_repo, "capture-prompt", "--prompt", "First")
        (test_repo / "file.txt").write_text("v2\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v2")
        run_cli(test_repo, "capture-stop")

        run_cli(test_repo, "capture-prompt", "--prompt", "Second")
        (test_repo / "file.txt").write_text("v3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v3")
        run_cli(test_repo, "capture-stop")

        # Make uncommitted changes
        (test_repo / "file.txt").write_text("dirty\n")

        # Revert to #1
        run_cli(test_repo, "revert", "1", "--yes")

        # Timeline should still have both entries
        print("[2/4] Verifying timeline preserved...")
        rc, stdout, stderr = run_cli(test_repo, "list")
        assert rc == 0, "List command should work"

        assert "#2" in stdout, "Entry #2 should still be in timeline"
        assert "#1" in stdout, "Entry #1 should still be in timeline"
        print("       [OK] Timeline entries preserved")

        # Show should work for both entries
        print("[3/4] Verifying show command works...")
        rc, stdout, stderr = run_cli(test_repo, "show", "2")
        assert rc == 0, "Show command should work for entry #2"
        assert "Second" in stdout or "v3" in stdout, "Entry #2 content should be accessible"
        print("       [OK] Show command works for all entries")

        # Git refs should still exist
        print("[4/4] Verifying git refs preserved...")
        rc, stdout, stderr = run_git(test_repo, "show-ref")
        assert rc == 0, "Show-ref should work"
        assert "refs/rewindo/" in stdout, "Rewindo refs should exist"
        print("       [OK] Git refs preserved")

        print("\n[SUCCESS] Timeline preservation test passed!")


def test_undo_with_dirty_tree():
    """Test undo command with dirty working tree."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-undo"
        test_repo.mkdir()

        print("\n[1/3] Test undo with dirty tree...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("v1\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v1")

        # Create checkpoint
        run_cli(test_repo, "capture-prompt", "--prompt", "Add feature")
        (test_repo / "file.txt").write_text("v2\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v2")
        run_cli(test_repo, "capture-stop")

        # Make uncommitted changes
        (test_repo / "file.txt").write_text("dirty\n")

        # Test undo without --yes (should prompt)
        print("[2/3] TEST: Undo without --yes prompts...")
        rc, stdout, stderr = run_cli(test_repo, "undo", input_text="n\n")
        assert "Continue?" in stdout or "continue" in stdout.lower(), \
            "Should prompt for confirmation"
        print("       [OK] Undo prompts for confirmation")

        # Test undo with --yes
        print("[3/3] TEST: Undo with --yes works...")
        rc, stdout, stderr = run_cli(test_repo, "undo", "--yes")
        assert rc == 0, f"Undo should succeed: {stderr}"

        # Should be back to v1
        content = get_file_content(test_repo, "file.txt")
        assert content == "v1\n", f"File should be v1 after undo, got: {repr(content)}"
        print("       [OK] Undo discards uncommitted changes and restores state")

        print("\n[SUCCESS] Undo with dirty tree test passed!")


def test_multiple_files_with_mixed_states():
    """Test with some files committed and some uncommitted."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-mixed"
        test_repo.mkdir()

        print("\n[1/3] Test mixed file states...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file1.txt").write_text("v1\n")
        (test_repo / "file2.txt").write_text("v1\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v1")

        # Create checkpoint
        run_cli(test_repo, "capture-prompt", "--prompt", "Update files")
        (test_repo / "file1.txt").write_text("v2\n")
        (test_repo / "file2.txt").write_text("v2\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v2")
        run_cli(test_repo, "capture-stop")

        # Make uncommitted changes to only file2
        print("[2/3] Creating partial dirty state...")
        (test_repo / "file2.txt").write_text("uncommitted\n")

        # Revert should work
        print("[3/3] TEST: Revert with partial dirty state...")
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--yes")
        assert rc == 0, f"Revert should succeed: {stderr}"

        # Both files should be at v2 (checkpoint #1's state)
        file1_content = get_file_content(test_repo, "file1.txt")
        file2_content = get_file_content(test_repo, "file2.txt")
        assert file1_content == "v2\n", f"file1 should be v2 (checkpoint #1 state), got: {repr(file1_content)}"
        assert file2_content == "v2\n", f"file2 should be v2 (checkpoint #1 state), got: {repr(file2_content)}"
        print("       [OK] All files restored correctly")

        print("\n[SUCCESS] Mixed file states test passed!")


def test_untracked_files_with_revert():
    """Test that untracked files are handled correctly."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-untracked"
        test_repo.mkdir()

        print("\n[1/3] Test untracked files...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("v1\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v1")

        # Create checkpoint
        run_cli(test_repo, "capture-prompt", "--prompt", "Add feature")
        (test_repo / "file.txt").write_text("v2\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v2")
        run_cli(test_repo, "capture-stop")

        # Add untracked file
        print("[2/3] Creating untracked file...")
        (test_repo / "untracked.txt").write_text("untracked\n")

        # Revert
        print("[3/3] TEST: Revert with untracked file...")
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--yes")
        assert rc == 0, f"Revert should succeed: {stderr}"

        # Tracked file should be reverted to checkpoint #1's state (v2)
        file_content = get_file_content(test_repo, "file.txt")
        assert file_content == "v2\n", f"Tracked file should be v2 (checkpoint #1), got: {repr(file_content)}"
        print("       [OK] Tracked file reverted correctly")

        print("\n[SUCCESS] Untracked files test passed!")


def main():
    """Run all dirty working tree tests."""
    print("\n" + "=" * 60)
    print("Phase 8.2: Dirty Working Tree Handling Tests")
    print("=" * 60)

    test_revert_with_uncommitted_changes_warning()
    test_revert_preserves_timeline_with_dirty_tree()
    test_undo_with_dirty_tree()
    test_multiple_files_with_mixed_states()
    test_untracked_files_with_revert()

    print("\n" + "=" * 60)
    print("[SUCCESS] All Phase 8.2 tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
