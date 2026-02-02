#!/usr/bin/env python3
"""Unit tests for CLI list output with actor column."""

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


def test_list_shows_header():
    """Test that list output includes a header row."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("initial\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Create a timeline entry
        run_cli(test_repo, "capture-prompt", "--prompt", "Test")
        (test_repo / "new.txt").write_text("test\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Test")
        run_cli(test_repo, "capture-stop")

        # Get list output
        rc, stdout, stderr = run_cli(test_repo, "list")
        output = stdout

        # Check for header
        assert "ID" in output, "Should have ID in header"
        assert "A" in output, "Should have Actor in header"
        assert "Date/Time" in output, "Should have Date/Time in header"
        assert "Files" in output, "Should have Files in header"
        assert "Description" in output, "Should have Description in header"

        print("[OK] List shows header row")


def test_list_shows_actor_column():
    """Test that list output shows actor column (A/U)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("initial\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Create assistant step
        run_cli(test_repo, "capture-prompt", "--prompt", "Test")
        (test_repo / "new.txt").write_text("test\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Test")
        run_cli(test_repo, "capture-stop")

        # Create user step
        (test_repo / "file.txt").write_text("manual edit\n")
        run_cli(test_repo, "capture-prompt", "--prompt", "Another")

        # Get list output
        rc, stdout, stderr = run_cli(test_repo, "list")
        output = stdout + stderr

        # Check for actor indicators
        assert "#2" in output, "Should have entry #2"
        assert "#1" in output, "Should have entry #1"

        # Look for actor column (A or U on each line after the ID)
        lines = output.split("\n")
        entry_lines = [l for l in lines if l.startswith("#")]
        assert len(entry_lines) >= 2, "Should have at least 2 entries"

        # Check that actor column exists between ID and date
        for line in entry_lines:
            # Format should be like "#1   A  2026-02-01..."
            parts = line.split()
            assert len(parts) >= 2, f"Line should have at least 2 parts: {line}"
            # Second part should be A or U
            assert parts[1] in ["A", "U"], f"Actor should be A or U, got: {parts[1]}"

        print("[OK] List shows actor column with A/U")


def test_list_actor_legend():
    """Test that assistant and user steps are correctly labeled."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("initial\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Create assistant step
        run_cli(test_repo, "capture-prompt", "--prompt", "Assistant work")
        (test_repo / "assistant.txt").write_text("assistant\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Assistant")
        run_cli(test_repo, "capture-stop")

        # Create user step
        (test_repo / "file.txt").write_text("user edit\n")
        run_cli(test_repo, "capture-prompt", "--prompt", "User work")

        # Get list output
        rc, stdout, stderr = run_cli(test_repo, "list")
        output = stdout

        # Find the lines with entries
        lines = output.split("\n")
        assistant_line = None
        user_line = None

        for line in lines:
            if "#2" in line:
                user_line = line
            elif "#1" in line:
                assistant_line = line

        assert assistant_line is not None, "Should find entry #1"
        assert user_line is not None, "Should find entry #2"

        # Check actor labels
        # Entry #1 should be A (assistant)
        assert " A " in assistant_line, f"Entry #1 should be A (assistant): {assistant_line}"

        # Entry #2 should be U (user)
        assert " U " in user_line, f"Entry #2 should be U (user): {user_line}"

        print("[OK] Actor column correctly labels A and U")


def main():
    """Run all tests."""
    print("=" * 60)
    print("CLI List Output Tests")
    print("=" * 60)

    test_list_shows_header()
    test_list_shows_actor_column()
    test_list_actor_legend()

    print("=" * 60)
    print("[SUCCESS] All CLI list output tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
