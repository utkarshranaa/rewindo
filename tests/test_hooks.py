#!/usr/bin/env python3
"""Test Rewindo hooks end-to-end (Windows compatible)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run_hook(hook_path: Path, input_data: dict, cwd: Path) -> tuple:
    """Run a hook script with JSON input."""
    # Create temp input file
    input_file = cwd / "hook_input.json"
    input_file.write_text(json.dumps(input_data))

    result = subprocess.run(
        [sys.executable, str(hook_path)],
        cwd=cwd,
        stdin=input_file.open(),
        capture_output=True,
        text=True
    )

    input_file.unlink(missing_ok=True)
    return result.returncode, result.stdout, result.stderr


def run_git(cwd: Path, *args):
    """Run git command."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout, result.stderr


def main():
    PROJECT_ROOT = Path(__file__).parent.parent
    HOOKS_DIR = PROJECT_ROOT / "hooks"

    # Create temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_repo = temp_path / "test-repo"
        test_repo.mkdir()

        print(f"Test repo: {test_repo}")

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test User")

        # Create initial commit
        (test_repo / "README.md").write_text("# Test Project\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial commit")

        # Test 1: UserPromptSubmit hook
        print("\n=== Test 1: UserPromptSubmit hook ===")
        code, stdout, stderr = run_hook(
            HOOKS_DIR / "log_prompt.py",
            {
                "session_id": "test-session-123",
                "transcript_path": str(test_repo / ".claude" / "projects" / "test.jsonl"),
                "cwd": str(test_repo),
                "permission_mode": "default",
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Create a hello world function in Python"
            },
            test_repo
        )

        if code != 0:
            print(f"[FAIL] Hook failed with code {code}: {stderr}")
            return False

        # Check state file
        state_file = test_repo / ".claude" / "data" / "prompt_state.json"
        if not state_file.exists():
            print("[FAIL] State file not created")
            return False

        with open(state_file) as f:
            state = json.load(f)
        print(f"[OK] Prompt captured: {state['prompt'][:50]}...")

        # Test 2: Simulate code changes
        print("\n=== Test 2: Simulate code changes ===")
        (test_repo / "hello.py").write_text('def hello():\n    print("Hello")\n')
        run_git(test_repo, "add", "-A")
        print("[OK] Created hello.py")

        # Test 3: Stop hook
        print("\n=== Test 3: Stop hook (create checkpoint) ===")
        code, stdout, stderr = run_hook(
            HOOKS_DIR / "log_stop.py",
            {
                "session_id": "test-session-123",
                "transcript_path": str(test_repo / ".claude" / "projects" / "test.jsonl"),
                "cwd": str(test_repo),
                "permission_mode": "default",
                "hook_event_name": "Stop",
                "stop_hook_active": False
            },
            test_repo
        )

        if code != 0:
            print(f"[FAIL] Hook failed: {stderr}")
            return False

        print(f"[OK] Stop hook completed: {stderr.strip()}")

        # Test 4: Verify checkpoint
        print("\n=== Test 4: Verify checkpoint ===")

        timeline_file = test_repo / ".claude" / "data" / "timeline.jsonl"
        if not timeline_file.exists():
            print("[FAIL] Timeline file not created")
            return False

        with open(timeline_file) as f:
            entry = json.loads(f.read())

        print(f"[OK] Timeline entry #{entry['id']} created")
        print(f"      Prompt: {entry['prompt'][:50]}...")
        print(f"      Files: {len(entry['files'])} changed")

        # Check git ref
        code, stdout, stderr = run_git(test_repo, "show-ref")
        if "refs/rewindo/checkpoints/1" not in stdout:
            print("[FAIL] Git ref not created")
            print(f"show-ref output: {stdout}")
            return False

        print("[OK] Git ref created")

        # Test 5: CLI list
        print("\n=== Test 5: CLI list ===")
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "bin" / "rewindo"),
             "--cwd", str(test_repo), "list"],
            cwd=test_repo,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"[FAIL] CLI list failed: {result.stderr}")
            return False

        if "#1" not in result.stdout:
            print(f"[FAIL] CLI doesn't show entry #1")
            return False

        print("[OK] CLI list works")
        print(result.stdout)

        # Test 6: CLI undo (revert to before last checkpoint)
        print("\n=== Test 6: CLI undo ===")

        # Check what checkpoint commit contains
        code, stdout, stderr = run_git(test_repo, "show", "--stat", "refs/rewindo/checkpoints/1")
        print(f"Checkpoint #1 contents:\n{stdout}")

        # Check parent
        code, stdout, stderr = run_git(test_repo, "rev-parse", "refs/rewindo/checkpoints/1^1")
        print(f"Checkpoint #1 parent: {stdout.strip()}")

        code, stdout, stderr = run_git(test_repo, "show", "--stat", "HEAD")
        print(f"Current HEAD contents:\n{stdout}")

        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "bin" / "rewindo"),
             "--cwd", str(test_repo), "undo", "--yes"],
            cwd=test_repo,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"[FAIL] CLI undo failed: {result.stderr}")
            return False

        # Check git status after undo
        code, stdout, stderr = run_git(test_repo, "status", "--short")
        print(f"Git status after undo: {stdout}")

        # List files in directory
        files = list(test_repo.iterdir())
        print(f"Files in test_repo: {[f.name for f in files]}")

        if (test_repo / "hello.py").exists():
            print("[FAIL] File still exists after undo")
            return False

        print("[OK] CLI undo works (file removed)")

        # Test 7: Verify revert to checkpoint works (file should exist)
        print("\n=== Test 7: CLI revert to checkpoint ===")
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "bin" / "rewindo"),
             "--cwd", str(test_repo), "revert", "1", "--yes"],
            cwd=test_repo,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"[FAIL] CLI revert failed: {result.stderr}")
            return False

        if not (test_repo / "hello.py").exists():
            print("[FAIL] File doesn't exist after revert to checkpoint #1")
            return False

        print("[OK] CLI revert to checkpoint works (file restored)")

        print("\n" + "="*50)
        print("[SUCCESS] All tests passed!")
        print("="*50)
        return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[FAIL] Exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
