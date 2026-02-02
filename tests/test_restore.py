#!/usr/bin/env python3
"""Unit tests for restore commands with replay functionality."""

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


def run_cli(cwd: Path, *args):
    """Run rewindo CLI command."""
    project_root = Path(__file__).parent.parent
    env = {**subprocess.os.environ, 'PYTHONPATH': str(project_root / 'lib')}
    result = subprocess.run(
        [sys.executable, str(project_root / "bin" / "rewindo"), "--cwd", str(cwd)] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env
    )
    return result.returncode, result.stdout, result.stderr


def get_file_content(cwd: Path, path: str) -> str:
    """Get file content."""
    file_path = cwd / path
    if file_path.exists():
        return file_path.read_text()
    return ""


def test_restore_to_step():
    """Test basic restore to a step."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("v1\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v1")

        # Create checkpoint #1 (assistant creates v2)
        run_cli(test_repo, "capture-prompt", "--prompt", "Add feature")
        (test_repo / "file.txt").write_text("v2\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v2")
        run_cli(test_repo, "capture-stop")

        # Create checkpoint #2 (assistant creates v3)
        run_cli(test_repo, "capture-prompt", "--prompt", "Add another")
        (test_repo / "file.txt").write_text("v3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v3")
        run_cli(test_repo, "capture-stop")

        # Verify file is v3
        assert get_file_content(test_repo, "file.txt") == "v3\n"

        # Restore to #1 (should be v2, since #1 captured the state after first assistant response)
        run_cli(test_repo, "revert", "1", "--yes")

        # File should be v2 (what assistant created in step #1)
        assert get_file_content(test_repo, "file.txt") == "v2\n"

        print("[OK] Basic restore works")


def test_restore_with_replay_user():
    """Test restore with replay of user edits."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("v1\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v1")

        # Step #1: Assistant creates v2
        run_cli(test_repo, "capture-prompt", "--prompt", "Update to v2")
        (test_repo / "file.txt").write_text("v2\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v2")
        run_cli(test_repo, "capture-stop")

        # Step #2: User makes manual edit to v2.1
        (test_repo / "file.txt").write_text("v2.1\n")
        run_cli(test_repo, "capture-prompt", "--prompt", "Next step")

        # Step #3: Assistant creates v3
        (test_repo / "file.txt").write_text("v3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v3")
        run_cli(test_repo, "capture-stop")

        # Current: v3
        assert get_file_content(test_repo, "file.txt") == "v3\n"

        # Restore to #1 with replay user
        # #1 has v2, then we cherry-pick the user edit (v2.1)
        run_cli(test_repo, "revert", "1", "--replay", "user", "--yes")

        # Should be v2.1 (v2 from step #1 + user edit cherry-picked)
        content = get_file_content(test_repo, "file.txt")
        assert content == "v2.1\n", f"Expected 'v2.1\\n', got '{repr(content)}'"

        print("[OK] Restore with replay user works")


def test_restore_replay_to_specific_step():
    """Test restore with --to option to limit replay."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("v1\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v1")

        # Step #1: Assistant creates v2
        run_cli(test_repo, "capture-prompt", "--prompt", "Update to v2")
        (test_repo / "file.txt").write_text("v2\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v2")
        run_cli(test_repo, "capture-stop")

        # Step #2: User makes manual edit to v2.1
        (test_repo / "file.txt").write_text("v2.1\n")
        run_cli(test_repo, "capture-prompt", "--prompt", "Next step")

        # Step #3: Assistant creates v3
        (test_repo / "file.txt").write_text("v3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v3")
        run_cli(test_repo, "capture-stop")

        # Step #4: User makes manual edit to v3.1
        (test_repo / "file.txt").write_text("v3.1\n")
        run_cli(test_repo, "capture-prompt", "--prompt", "Final step")

        # Step #5: Assistant creates v4
        (test_repo / "file.txt").write_text("v4\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v4")
        run_cli(test_repo, "capture-stop")

        # Current: v4
        assert get_file_content(test_repo, "file.txt") == "v4\n"

        # Restore to #1 with replay user --to 3
        # This should replay user step #2 but NOT user step #4
        run_cli(test_repo, "revert", "1", "--replay", "user", "--to", "3", "--yes")

        # Should be v2.1 (v2 from step #1 + user edit from #2, NOT #4)
        content = get_file_content(test_repo, "file.txt")
        assert content == "v2.1\n", f"Expected 'v2.1\\n', got '{repr(content)}'"

        print("[OK] Restore with --to option works")


def test_restore_conflict_handling():
    """Test that conflicts are detected and handled.

    This test simulates a scenario where a later user step modifies the same
    code that was already changed in an intermediate assistant step, creating
    a conflict when replayed.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("line1\nline2\nline3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Step #1: Assistant modifies line2
        run_cli(test_repo, "capture-prompt", "--prompt", "Modify line2")
        (test_repo / "file.txt").write_text("line1\nassistant line2\nline3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Assistant")
        run_cli(test_repo, "capture-stop")

        # Step #2: User modifies line2 (creating a divergent change)
        (test_repo / "file.txt").write_text("line1\nuser line2\nline3\n")
        run_cli(test_repo, "capture-prompt", "--prompt", "User edit")

        # Step #3: Assistant ALSO modifies line2 differently
        (test_repo / "file.txt").write_text("line1\ndifferent assistant line2\nline3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Assistant2")
        run_cli(test_repo, "capture-stop")

        # Step #4: User creates another snapshot that will conflict
        # This user step's parent is step #3, which has "different assistant line2"
        (test_repo / "file.txt").write_text("line1\nuser step4 line2\nline3\n")
        run_cli(test_repo, "capture-prompt", "--prompt", "Another user edit")

        # Step #5: Assistant commits more changes
        (test_repo / "file.txt").write_text("line1\ndifferent assistant line2\nmore content\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Assistant3")
        run_cli(test_repo, "capture-stop")

        # Now restore to #1 and replay user steps #2 and #4
        # Step #2 will apply cleanly (parent is #1)
        # Step #4's parent is #3, but after replaying #2, we don't have #3's state
        # So cherry-picking #4 should conflict because the base doesn't match
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--replay", "user", "--yes")

        # Should return error code 1 for conflict
        assert rc == 1, f"Expected error code 1 for conflict, got {rc}"
        assert "Conflict" in stderr or "conflict" in stderr or "error:" in stderr.lower(), f"Expected conflict message, got: {stderr}"

        print("[OK] Conflict handling works")


def test_restore_no_user_edits():
    """Test restore with --replay user when there are no user edits."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("v1\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v1")

        # Step #1: Assistant creates v2
        run_cli(test_repo, "capture-prompt", "--prompt", "Update to v2")
        (test_repo / "file.txt").write_text("v2\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v2")
        run_cli(test_repo, "capture-stop")

        # Step #2: Assistant creates v3 (no user edits in between)
        run_cli(test_repo, "capture-prompt", "--prompt", "Update to v3")
        (test_repo / "file.txt").write_text("v3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v3")
        run_cli(test_repo, "capture-stop")

        # Current: v3
        assert get_file_content(test_repo, "file.txt") == "v3\n"

        # Restore to #1 with replay user (but no user edits between #1 and #3)
        run_cli(test_repo, "revert", "1", "--replay", "user", "--yes")

        # Should be v2 (step #1 captured v2, no user edits to replay)
        assert get_file_content(test_repo, "file.txt") == "v2\n"

        print("[OK] Restore with no user edits works")


def test_list_shows_actor_for_restore():
    """Test that list shows actor to help decide what to restore."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("v1\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v1")

        # Create mixed timeline
        run_cli(test_repo, "capture-prompt", "--prompt", "Add auth")
        (test_repo / "file.txt").write_text("v2\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v2")
        run_cli(test_repo, "capture-stop")

        (test_repo / "file.txt").write_text("v2-user\n")
        run_cli(test_repo, "capture-prompt", "--prompt", "Add db")

        # List should show actor column
        rc, stdout, stderr = run_cli(test_repo, "list")
        output = stdout

        # Check for actor indicators
        assert "A" in output, "Should show assistant actor"
        assert "U" in output, "Should show user actor"

        print("[OK] List shows actor for restore planning")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Restore Commands Unit Tests")
    print("=" * 60)

    test_restore_to_step()
    test_restore_with_replay_user()
    test_restore_replay_to_specific_step()
    test_restore_conflict_handling()
    test_restore_no_user_edits()
    test_list_shows_actor_for_restore()

    print("=" * 60)
    print("[SUCCESS] All restore command tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
