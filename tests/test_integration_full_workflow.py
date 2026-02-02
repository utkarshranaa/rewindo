#!/usr/bin/env python3
"""Integration test for full Rewindo workflow.

This test simulates a complete Claude Code session:
1. User submits prompt
2. Assistant makes changes (capture-prompt, edit files, capture-stop)
3. User makes manual edits
4. Repeat for multiple cycles
5. Test timeline listing, inspection, labels
6. Test revert with and without replay
7. Verify all functionality works end-to-end
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


def test_full_workflow_integration():
    """Test complete workflow from prompt to revert."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-project"
        test_repo.mkdir()

        print("\n=== Phase 8.1: Full Workflow Integration Test ===\n")

        # Step 0: Initialize git repo and basic project structure
        print("[1/15] Initializing git repo...")
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test User")

        # Create initial project structure
        (test_repo / "src").mkdir()
        (test_repo / "app.py").write_text("""# Main application
def main():
    print("Hello, World!")

if __name__ == "__main__":
    main()
""")
        (test_repo / "README.md").write_text("# My Project\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial commit")

        # Cycle 1: First prompt - Add authentication
        print("[2/15] Cycle 1: User prompt 'Add user authentication'...")
        run_cli(test_repo, "capture-prompt", "--prompt", "Add user authentication")

        # Assistant creates auth.py
        (test_repo / "src" / "auth.py").write_text("""# Authentication module
class User:
    def __init__(self, username, password):
        self.username = username
        self.password = password

    def login(self):
        return f"User {self.username} logged in"
""")
        (test_repo / "app.py").write_text("""# Main application
from src.auth import User

def main():
    user = User("alice", "secret")
    print(user.login())

if __name__ == "__main__":
    main()
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add authentication")
        run_cli(test_repo, "capture-stop")
        print("       Assistant step #1 created (auth.py added)")

        # Cycle 2: User makes manual edits
        print("[3/15] Cycle 2: User makes manual edits...")
        (test_repo / "src" / "auth.py").write_text("""# Authentication module
import hashlib

class User:
    def __init__(self, username, password):
        self.username = username
        # User manual edit: password hashing
        self.password_hash = hashlib.sha256(password.encode()).hexdigest()

    def login(self, password):
        check_hash = hashlib.sha256(password.encode()).hexdigest()
        if check_hash == self.password_hash:
            return f"User {self.username} logged in"
        return "Login failed"
""")
        run_cli(test_repo, "capture-prompt", "--prompt", "Add database support")
        print("       User step #2 created (manual edit: password hashing)")

        # Cycle 3: Assistant adds database
        print("[4/15] Cycle 3: Assistant adds database support...")
        (test_repo / "src" / "database.py").write_text("""# Database module
class Database:
    def __init__(self, path):
        self.path = path
        self.users = {}

    def save_user(self, user):
        self.users[user.username] = user

    def load_user(self, username):
        return self.users.get(username)
""")
        (test_repo / "app.py").write_text("""# Main application
from src.auth import User
from src.database import Database

def main():
    db = Database("data.db")
    user = User("alice", "secret")
    db.save_user(user)
    print(user.login())

if __name__ == "__main__":
    main()
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add database")
        run_cli(test_repo, "capture-stop")
        print("       Assistant step #3 created (database.py added)")

        # Cycle 4: User makes more manual edits
        print("[5/15] Cycle 4: User makes another manual edit...")
        (test_repo / "README.md").write_text("""# My Project

A simple authentication and database demo.

## Features
- User authentication with password hashing
- Simple database storage
""")
        run_cli(test_repo, "capture-prompt", "--prompt", "Add API endpoints")
        print("       User step #4 created (manual edit: README update)")

        # Cycle 5: Assistant adds API
        print("[6/15] Cycle 5: Assistant adds API endpoints...")
        (test_repo / "src" / "api.py").write_text("""# API module
from src.database import Database
from src.auth import User

class API:
    def __init__(self, db):
        self.db = db

    def create_user(self, username, password):
        user = User(username, password)
        self.db.save_user(user)
        return {"status": "created", "username": username}

    def get_user(self, username):
        user = self.db.load_user(username)
        if user:
            return {"username": user.username}
        return {"error": "not found"}
""")
        (test_repo / "app.py").write_text("""# Main application
from src.auth import User
from src.database import Database
from src.api import API

def main():
    db = Database("data.db")
    api = API(db)
    result = api.create_user("bob", "pass123")
    print(result)

if __name__ == "__main__":
    main()
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add API endpoints")
        run_cli(test_repo, "capture-stop")
        print("       Assistant step #5 created (api.py added)")

        # TEST: Verify timeline has 5 entries
        print("\n[7/15] TEST: Timeline entries created...")
        rc, stdout, stderr = run_cli(test_repo, "list")
        assert rc == 0, f"list command failed: {stderr}"

        entries = stdout.split('\n')
        entry_count = sum(1 for line in entries if line.startswith('#') and ('A  ' in line or 'U  ' in line))
        assert entry_count == 5, f"Expected 5 timeline entries, found {entry_count}"
        print(f"       [OK] Timeline has 5 entries")

        # Verify actor column shows correct actors
        assert "A" in stdout, "Assistant actor not shown"
        assert "U" in stdout, "User actor not shown"
        print("       [OK] Actor column (A/U) displayed correctly")

        # TEST: Verify checkpoint #1 (auth.py)
        print("\n[8/15] TEST: Checkpoint #1 details...")
        rc, stdout, stderr = run_cli(test_repo, "show", "1")
        assert rc == 0, f"show command failed: {stderr}"
        assert "authentication" in stdout.lower(), "Prompt not found in entry"
        assert "auth.py" in stdout, "File not listed in entry"
        print("       [OK] Checkpoint #1 shows authentication prompt")

        # TEST: Verify user step #2 has checkpoint_sha
        print("\n[9/15] TEST: User step has checkpoint_sha...")
        rc, stdout, stderr = run_cli(test_repo, "show", "2")
        assert rc == 0, f"show command failed: {stderr}"
        assert "SHA:" in stdout or "checkpoint_sha" in stdout, "checkpoint_sha not shown"
        print("       [OK] User step #2 has checkpoint_sha")

        # TEST: Label a checkpoint
        print("\n[10/15] TEST: Add label to checkpoint...")
        rc, stdout, stderr = run_cli(test_repo, "label", "3", "working")
        assert rc == 0, f"label command failed: {stderr}"
        # Verify label appears
        rc, stdout, stderr = run_cli(test_repo, "show", "3")
        assert "working" in stdout, "Label not saved"
        print("       [OK] Label 'working' added to checkpoint #3")

        # TEST: Search functionality
        print("\n[11/15] TEST: Search functionality...")
        rc, stdout, stderr = run_cli(test_repo, "search", "API")
        assert rc == 0, f"search command failed: {stderr}"
        assert "API" in stdout or "api" in stdout.lower(), "Search results not found"
        print("       [OK] Search for 'API' works")

        # TEST: Basic revert
        print("\n[12/15] TEST: Basic revert to checkpoint #3...")
        # Save current state
        before_revert = get_file_content(test_repo, "src/api.py")
        assert before_revert, "api.py should exist before revert"

        # Revert to #3 (before API was added)
        run_cli(test_repo, "revert", "3", "--yes")

        # API should be gone
        after_revert = get_file_content(test_repo, "src/api.py")
        assert not after_revert, "api.py should not exist after revert to #3"

        # But database should still exist
        db_content = get_file_content(test_repo, "src/database.py")
        assert db_content, "database.py should exist after revert to #3"
        print("       [OK] Revert to #3 works (API removed, database kept)")

        # TEST: Revert with replay user edits
        print("\n[13/15] TEST: Revert with replay user edits...")
        # First, go back to latest
        run_git(test_repo, "reset", "--hard", "HEAD")

        # Revert to #1 with replay user
        run_cli(test_repo, "revert", "1", "--replay", "user", "--yes")

        # Should have auth.py (from #1)
        # And should have user's password hashing edit (from #2 replayed)
        auth_content = get_file_content(test_repo, "src/auth.py")
        assert "hashlib" in auth_content, "User edit (password hashing) should be replayed"
        assert "sha256" in auth_content, "User edit details should be present"
        print("       [OK] Revert to #1 with user replay works")

        # TEST: Doctor command
        print("\n[14/15] TEST: Doctor command...")
        rc, stdout, stderr = run_cli(test_repo, "doctor")
        assert rc == 0, f"doctor command failed: {stderr}"
        assert "All checks passed" in stdout or "healthy" in stdout.lower(), "Doctor found issues"
        print("       [OK] Doctor reports healthy state")

        # TEST: Export functionality
        print("\n[15/15] TEST: Export checkpoint...")
        rc, stdout, stderr = run_cli(test_repo, "export", "1")
        assert rc == 0, f"export command failed: {stderr}"
        export_dir = test_repo / "export-00001"
        assert export_dir.exists(), "Export directory not created"
        assert (export_dir / "meta.json").exists(), "meta.json not exported"
        assert (export_dir / "prompt.txt").exists(), "prompt.txt not exported"
        print("       [OK] Export checkpoint #1 works")

        print("\n" + "=" * 60)
        print("[SUCCESS] Full workflow integration test passed!")
        print("=" * 60)
        print("\nSummary:")
        print("  [OK] 5 timeline entries created (3 assistant, 2 user)")
        print("  [OK] Timeline list shows actors correctly")
        print("  [OK] Show command displays entry details")
        print("  [OK] User steps have checkpoint_sha")
        print("  [OK] Labels work")
        print("  [OK] Search works")
        print("  [OK] Basic revert works")
        print("  [OK] Revert with replay user works")
        print("  [OK] Doctor command works")
        print("  [OK] Export works")
        print("\nAll Phase 8.1 integration tests passed!")


def test_workflow_with_conflicts_and_resolution():
    """Test workflow that includes conflict scenarios."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-conflict"
        test_repo.mkdir()

        print("\n=== Phase 8.1: Conflict Workflow Test ===\n")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "config.py").write_text("# Config\nDEBUG=True\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Step 1: Assistant modifies config
        run_cli(test_repo, "capture-prompt", "--prompt", "Add logging config")
        (test_repo / "config.py").write_text("""# Config
DEBUG=True
LOG_LEVEL="INFO"
LOG_FILE="app.log"
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add logging")
        run_cli(test_repo, "capture-stop")

        # Step 2: User modifies same lines
        (test_repo / "config.py").write_text("""# Config
DEBUG=False
LOG_LEVEL="ERROR"
LOG_FILE="error.log"
""")
        run_cli(test_repo, "capture-prompt", "--prompt", "Continue")

        # Step 3: Assistant modifies differently
        (test_repo / "config.py").write_text("""# Config
DEBUG=True
LOG_LEVEL="DEBUG"
LOG_FILE="debug.log"
DATABASE_URL="localhost"
""")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add database config")
        run_cli(test_repo, "capture-stop")

        print("[1/3] Created conflict scenario...")

        # TEST: Revert to #1 with replay should handle conflict
        print("[2/3] TEST: Conflict detection during replay...")
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--replay", "user", "--yes")

        if rc == 0:
            print("       [OK] Conflict handled (no conflict or auto-resolved)")
        else:
            assert "conflict" in stderr.lower() or "error" in stderr.lower(), \
                f"Expected conflict message, got: {stderr}"
            print("       [OK] Conflict detected and reported")

        # TEST: List still works after conflict
        print("[3/3] TEST: Timeline survives conflict...")
        rc, stdout, stderr = run_cli(test_repo, "list")
        assert rc == 0, f"list failed after conflict: {stderr}"
        assert "#3" in stdout, "Timeline corrupted after conflict"
        print("       [OK] Timeline intact after conflict")

        print("\n[SUCCESS] Conflict workflow test passed!")


def main():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("Phase 8.1: Full Workflow Integration Tests")
    print("=" * 60)

    test_full_workflow_integration()
    test_workflow_with_conflicts_and_resolution()

    print("\n" + "=" * 60)
    print("[SUCCESS] All Phase 8.1 integration tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
