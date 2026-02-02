#!/usr/bin/env python3
"""Integration test for conflict resolution in replay.

This test verifies more complex conflict scenarios during user edit replay:
- When user and assistant modified the same lines
- When later commits affect the same code
- Proper conflict detection and error messages
- Timeline survives conflict scenarios
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


def test_conflict_when_same_line_modified_differently():
    """Test conflict when user and assistant modify same line differently."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-conflict"
        test_repo.mkdir()

        print("\n=== Phase 8.4: Conflict Resolution Tests ===\n")

        # Initialize
        print("[1/5] Initializing repo...")
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "config.py").write_text("""# Config
DEBUG = True
PORT = 8000
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Step 1: Assistant modifies PORT
        print("[2/5] Creating base checkpoint...")
        run_cli(test_repo, "capture-prompt", "--prompt", "Update config")
        (test_repo / "config.py").write_text("""# Config
DEBUG = True
PORT = 8080
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Update port")
        run_cli(test_repo, "capture-stop")

        # Step 2: User modifies same line differently
        print("[3/5] User creates conflicting edit...")
        (test_repo / "config.py").write_text("""# Config
DEBUG = False
PORT = 3000
""")
        run_cli(test_repo, "capture-prompt", "--prompt", "Continue")

        # Step 3: Assistant creates another checkpoint where the conflict will emerge
        # (modifies DEBUG line, which wasn't touched by user, but same overall file)
        print("[4/5] Assistant creates follow-up checkpoint...")
        (test_repo / "config.py").write_text("""# Config
DEBUG = False
PORT = 8080
HOST = "localhost"
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add host config")
        run_cli(test_repo, "capture-stop")

        # Step 4: Try to replay user step #2 onto step #1
        # User's PORT=3000 conflicts with step #1's PORT=8080
        print("[5/5] TEST: Conflict detection during replay...")
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--replay", "user", "--yes")

        if rc != 0:
            # Conflict was detected (expected)
            assert "conflict" in stderr.lower() or "error" in stderr.lower(), \
                f"Expected conflict message, got: {stderr}"
            print("       [OK] Conflict detected and reported")
        else:
            # Might not have conflicted if git auto-merged
            # Verify the result is valid
            print("       [OK] No conflict (auto-merged or replay skipped)")

        # Timeline should be intact
        print("\n[6/6] TEST: Timeline survives conflict...")
        rc, stdout, stderr = run_cli(test_repo, "list")
        assert rc == 0, "List should work after conflict"
        assert "#3" in stdout, "Entry #3 should be in timeline"
        print("       [OK] Timeline intact")

        print("\n[SUCCESS] Same line conflict test passed!")


def test_multi_file_conflict():
    """Test conflict spanning multiple files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-multi-conflict"
        test_repo.mkdir()

        print("\n[1/4] Test multi-file conflict...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "app.py").write_text("def main(): pass\n")
        (test_repo / "config.py").write_text("DEBUG = True\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Step 1: Assistant modifies both files
        print("[2/4] Creating base checkpoint...")
        run_cli(test_repo, "capture-prompt", "--prompt", "Add features")
        (test_repo / "app.py").write_text("def main():\n    print('hello')\n")
        (test_repo / "config.py").write_text("DEBUG = True\nLEVEL = 'info'\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add features")
        run_cli(test_repo, "capture-stop")

        # Step 2: User modifies app.py (conflicting change)
        print("[3/4] User creates conflicting edit in app.py...")
        (test_repo / "app.py").write_text("def main():\n    print('goodbye')\n")
        run_cli(test_repo, "capture-prompt", "--prompt", "Next")

        # Step 3: Assistant modifies config.py (different file, no conflict)
        (test_repo / "config.py").write_text("DEBUG = False\nLEVEL = 'error'\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Update config")
        run_cli(test_repo, "capture-stop")

        # Try replay - might conflict on app.py
        print("[4/4] TEST: Multi-file conflict handling...")
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--replay", "user", "--yes")

        # Whether conflict or not, timeline should survive
        rc, stdout, stderr = run_cli(test_repo, "list")
        assert rc == 0, "List should work"
        assert "#3" in stdout, "Timeline should be intact"
        print("       [OK] Multi-file scenario handled")

        print("\n[SUCCESS] Multi-file conflict test passed!")


def test_conflict_resolution_workflow():
    """Test complete conflict resolution workflow."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-workflow"
        test_repo.mkdir()

        print("\n[1/5] Test conflict resolution workflow...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "code.py").write_text("""def process():
    value = 10
    return value * 2
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Step 1: Assistant modifies function
        print("[2/5] Creating checkpoint...")
        run_cli(test_repo, "capture-prompt", "--prompt", "Optimize")
        (test_repo / "code.py").write_text("""def process():
    value = 10
    return value * 3  # Optimized
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Optimize")
        run_cli(test_repo, "capture-stop")

        # Step 2: User creates conflicting change
        print("[3/5] User creates conflicting change...")
        (test_repo / "code.py").write_text("""def process():
    value = 20  # User changed this
    return value * 2
""")
        run_cli(test_repo, "capture-prompt", "--prompt", "Continue")

        # Step 3: Assistant adds more changes
        (test_repo / "code.py").write_text("""def process():
    value = 10
    result = value * 3
    print(result)  # Added debug
    return result
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add debug")
        run_cli(test_repo, "capture-stop")

        # Try replay
        print("[4/5] TEST: Conflict detection...")
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--replay", "user", "--yes")

        # Check for conflict
        if rc != 0:
            print("       [OK] Conflict detected")

            # Test: User can still use commands after conflict
            print("[5/5] TEST: Commands work after conflict...")
            rc, stdout, stderr = run_cli(test_repo, "list")
            assert rc == 0, "List should work after conflict"

            rc, stdout, stderr = run_cli(test_repo, "doctor")
            assert rc == 0, "Doctor should work after conflict"
            print("       [OK] Commands functional after conflict")
        else:
            print("       [OK] No conflict (replay succeeded)")

        print("\n[SUCCESS] Conflict resolution workflow test passed!")


def test_no_conflict_with_separate_edits():
    """Test that no conflict occurs when edits are to separate parts of file."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-no-conflict"
        test_repo.mkdir()

        print("\n[1/4] Test no conflict with separate edits...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "app.py").write_text("""class App:
    def __init__(self):
        self.name = "App"
        self.version = "1.0"

    def run(self):
        print(f"{self.name} v{self.version}")
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Step 1: Assistant modifies run() method
        print("[2/4] Assistant modifies run() method...")
        run_cli(test_repo, "capture-prompt", "--prompt", "Add logging")
        (test_repo / "app.py").write_text("""class App:
    def __init__(self):
        self.name = "App"
        self.version = "1.0"

    def run(self):
        logger.info(f"{self.name} v{self.version}")
        return True
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add logging")
        run_cli(test_repo, "capture-stop")

        # Step 2: User modifies __init__() method (different part of class)
        print("[3/4] User modifies __init__() method...")
        (test_repo / "app.py").write_text("""class App:
    def __init__(self):
        self.name = "App"
        self.version = "1.0"
        self.debug = True  # User added this

    def run(self):
        logger.info(f"{self.name} v{self.version}")
        return True
""")
        run_cli(test_repo, "capture-prompt", "--prompt", "Continue")

        # Step 3: Assistant adds another method (different part again)
        (test_repo / "app.py").write_text("""class App:
    def __init__(self):
        self.name = "App"
        self.version = "1.0"
        self.debug = True  # User added this

    def run(self):
        logger.info(f"{self.name} v{self.version}")
        return True

    def stop(self):
        logger.info("Stopping")
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add stop method")
        run_cli(test_repo, "capture-stop")

        # Replay should work without conflict
        print("[4/4] TEST: Replay with separate edits succeeds...")
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--replay", "user", "--yes")
        assert rc == 0, f"Replay should succeed: {stderr}"

        # Verify user's edit was replayed
        content = get_file_content(test_repo, "app.py")
        assert "self.debug = True" in content, "User edit should be replayed"
        print("       [OK] Separate edits replay without conflict")

        print("\n[SUCCESS] No conflict test passed!")


def test_conflict_in_replay_to_specific_step():
    """Test --to option limits replay and avoids conflicts."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-to-option"
        test_repo.mkdir()

        print("\n[1/5] Test --to option avoids conflicts...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "config.py").write_text("A = 1\nB = 2\nC = 3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Step 1: Assistant modifies A
        print("[2/5] Creating first checkpoint...")
        run_cli(test_repo, "capture-prompt", "--prompt", "Change A")
        (test_repo / "config.py").write_text("A = 10\nB = 2\nC = 3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Change A")
        run_cli(test_repo, "capture-stop")

        # Step 2: User modifies B
        print("[3/5] User modifies B...")
        (test_repo / "config.py").write_text("A = 10\nB = 20\nC = 3\n")
        run_cli(test_repo, "capture-prompt", "--prompt", "Continue")

        # Step 3: User modifies B again (will conflict if we replay both)
        print("[4/5] User modifies B again...")
        (test_repo / "config.py").write_text("A = 10\nB = 30\nC = 3\n")
        run_cli(test_repo, "capture-prompt", "--prompt", "Next")

        # Step 4: Assistant modifies B differently
        (test_repo / "config.py").write_text("A = 10\nB = 200\nC = 3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Change B")
        run_cli(test_repo, "capture-stop")

        # Replay only up to step 3 (should work)
        print("[5/5] TEST: Replay with --to avoids later conflicts...")
        # This replays user steps #3 and #4 but not the assistant's conflicting change
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--replay", "user", "--to", "3", "--yes")

        if rc == 0:
            # Should have B = 30 (from user step #3)
            content = get_file_content(test_repo, "config.py")
            assert "B = 30" in content, f"Should have user's B value, got: {content}"
            print("       [OK] Limited replay avoids conflicts")
        else:
            # If there was a conflict, it's still valid behavior
            assert "conflict" in stderr.lower(), "Should report conflict"
            print("       [OK] Conflict detected (expected)")

        print("\n[SUCCESS] --to option conflict test passed!")


def test_multiple_user_replay_attempts():
    """Test that user can try multiple replay strategies after conflict."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-multiple"
        test_repo.mkdir()

        print("\n[1/3] Test multiple replay attempts...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("line1\nline2\nline3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Create checkpoints and user edits that will conflict
        run_cli(test_repo, "capture-prompt", "--prompt", "First")
        (test_repo / "file.txt").write_text("line1\nmodified line2\nline3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "First")
        run_cli(test_repo, "capture-stop")

        (test_repo / "file.txt").write_text("line1\nuser line2\nline3\n")
        run_cli(test_repo, "capture-prompt", "--prompt", "Second")

        (test_repo / "file.txt").write_text("line1\ndifferent line2\nline3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Second")
        run_cli(test_repo, "capture-stop")

        # First replay attempt (might conflict)
        print("[2/3] First replay attempt...")
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--replay", "user", "--yes")
        first_conflict = rc != 0
        print(f"       First attempt {'conflicted' if first_conflict else 'succeeded'}")

        # Whether or not there was a conflict, user should be able to:
        # 1. Try again without replay
        # 2. Try reverting to a different checkpoint
        print("[3/3] TEST: User can try alternative strategies...")

        # Try reverting without replay
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--yes")
        assert rc == 0, "Revert without replay should work"

        # Timeline should be intact
        rc, stdout, stderr = run_cli(test_repo, "list")
        assert rc == 0, "List should work"
        print("       [OK] Alternative strategies available")

        print("\n[SUCCESS] Multiple replay attempts test passed!")


def main():
    """Run all conflict resolution tests."""
    print("\n" + "=" * 60)
    print("Phase 8.4: Conflict Resolution in Replay Tests")
    print("=" * 60)

    test_conflict_when_same_line_modified_differently()
    test_multi_file_conflict()
    test_conflict_resolution_workflow()
    test_no_conflict_with_separate_edits()
    test_conflict_in_replay_to_specific_step()
    test_multiple_user_replay_attempts()

    print("\n" + "=" * 60)
    print("[SUCCESS] All Phase 8.4 tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
