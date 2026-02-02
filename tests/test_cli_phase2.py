#!/usr/bin/env python3
"""Comprehensive CLI tests for Phase 2."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


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
    result = subprocess.run(
        [sys.executable, str(project_root / "bin" / "rewindo"),
         "--cwd", str(cwd)] + list(args),
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

        # Helper to create checkpoint
        def create_checkpoint(prompt: str, file_changes: dict):
            """Create a checkpoint by simulating hooks."""
            # UserPromptSubmit
            prompt_data = {
                "session_id": "test-session",
                "cwd": str(test_repo),
                "hook_event_name": "UserPromptSubmit",
                "prompt": prompt
            }
            input_file = test_repo / "prompt_input.json"
            input_file.write_text(json.dumps(prompt_data))

            subprocess.run(
                [sys.executable, str(HOOKS_DIR / "log_prompt.py")],
                cwd=test_repo,
                stdin=input_file.open(),
                capture_output=True
            )

            # Make file changes
            for file_path, content in file_changes.items():
                (test_repo / file_path).parent.mkdir(parents=True, exist_ok=True)
                (test_repo / file_path).write_text(content)

            run_git(test_repo, "add", "-A")

            # Stop hook
            stop_data = {
                "session_id": "test-session",
                "cwd": str(test_repo),
                "hook_event_name": "Stop",
                "stop_hook_active": False
            }
            input_file.write_text(json.dumps(stop_data))

            subprocess.run(
                [sys.executable, str(HOOKS_DIR / "log_stop.py")],
                cwd=test_repo,
                stdin=input_file.open(),
                capture_output=True
            )

            input_file.unlink(missing_ok=True)

        # Create multiple checkpoints
        print("\n=== Creating test checkpoints ===")
        create_checkpoint("Add authentication", {
            "auth.py": "def login(user, pass):\n    return True\n"
        })
        create_checkpoint("Add database layer", {
            "db.py": "class Database:\n    pass\n"
        })
        create_checkpoint("Add API endpoints", {
            "api.py": "def get_user():\n    pass\n"
        })

        # Test 1: list command (default)
        print("\n=== Test 1: rewindo list (default) ===")
        code, stdout, stderr = run_cli(test_repo, "list")
        if code != 0:
            print(f"[FAIL] list failed: {stderr}")
            return False
        print(stdout)
        if "#3" not in stdout or "#2" not in stdout or "#1" not in stdout:
            print("[FAIL] Not all entries shown")
            return False
        print("[OK] list shows all entries")

        # Test 2: list with limit
        print("\n=== Test 2: rewindo list --limit 2 ===")
        code, stdout, stderr = run_cli(test_repo, "list", "--limit", "2")
        if code != 0:
            print(f"[FAIL] list with limit failed: {stderr}")
            return False
        print(stdout)
        if "#1" in stdout:  # Should only show #3 and #2 (newest first)
            print("[FAIL] Limit not respected")
            return False
        print("[OK] list --limit works")

        # Test 3: list with query
        print("\n=== Test 3: rewindo list --query API ===")
        code, stdout, stderr = run_cli(test_repo, "list", "--query", "API")
        if code != 0:
            print(f"[FAIL] list with query failed: {stderr}")
            return False
        print(stdout)
        if "API" not in stdout:
            print("[FAIL] Query not working")
            return False
        print("[OK] list --query works")

        # Test 4: show command
        print("\n=== Test 4: rewindo show 2 ===")
        code, stdout, stderr = run_cli(test_repo, "show", "2")
        if code != 0:
            print(f"[FAIL] show failed: {stderr}")
            return False
        print(stdout)
        if "database" not in stdout.lower() or "#2" not in stdout:
            print("[FAIL] show not displaying correctly")
            return False
        print("[OK] show works")

        # Test 5: get-prompt command
        print("\n=== Test 5: rewindo get-prompt 3 ===")
        code, stdout, stderr = run_cli(test_repo, "get-prompt", "3")
        if code != 0:
            print(f"[FAIL] get-prompt failed: {stderr}")
            return False
        print(f"Prompt: {stdout}")
        if "API" not in stdout:
            print("[FAIL] get-prompt not returning prompt")
            return False
        print("[OK] get-prompt works")

        # Test 6: get-prompt with max-chars
        print("\n=== Test 6: rewindo get-prompt 1 --max-chars 10 ===")
        code, stdout, stderr = run_cli(test_repo, "get-prompt", "1", "--max-chars", "10")
        if code != 0:
            print(f"[FAIL] get-prompt with max-chars failed: {stderr}")
            return False
        print(f"Prompt (truncated): '{stdout.strip()}'")
        if len(stdout.strip()) > 15:  # Should be ~10 chars
            print("[FAIL] max-chars not respected")
            return False
        print("[OK] get-prompt --max-chars works")

        # Test 7: get-diff command
        print("\n=== Test 7: rewindo get-diff 2 ===")
        code, stdout, stderr = run_cli(test_repo, "get-diff", "2")
        if code != 0:
            print(f"[FAIL] get-diff failed: {stderr}")
            return False
        print(f"Diff preview: {stdout[:200]}...")
        if "db.py" not in stdout:
            print("[FAIL] get-diff not returning diff")
            return False
        print("[OK] get-diff works")

        # Test 8: get-diff with max-lines
        print("\n=== Test 8: rewindo get-diff 1 --max-lines 5 ===")
        code, stdout, stderr = run_cli(test_repo, "get-diff", "1", "--max-lines", "5")
        if code != 0:
            print(f"[FAIL] get-diff with max-lines failed: {stderr}")
            return False
        lines = stdout.strip().split("\n")
        print(f"Lines returned: {len(lines)}")
        if len(lines) > 6:  # Should be ~5 lines
            print(f"[FAIL] max-lines not respected, got {len(lines)} lines")
            return False
        print("[OK] get-diff --max-lines works")

        # Test 9: get-diff with file filter
        print("\n=== Test 9: rewindo get-diff 3 --file api.py ===")
        code, stdout, stderr = run_cli(test_repo, "get-diff", "3", "--file", "api.py")
        if code != 0:
            print(f"[FAIL] get-diff with --file failed: {stderr}")
            return False
        print(f"Filtered diff: {stdout[:200]}...")
        if "api.py" not in stdout:
            print("[FAIL] --file filter not working")
            return False
        if "auth.py" in stdout or "db.py" in stdout:
            print("[FAIL] --file filter showing other files")
            return False
        print("[OK] get-diff --file works")

        # Test 10: label command
        print("\n=== Test 10: rewindo label 2 working ===")
        code, stdout, stderr = run_cli(test_repo, "label", "2", "working")
        if code != 0:
            print(f"[FAIL] label failed: {stderr}")
            return False
        print(stdout)

        # Verify label was added
        code, stdout, stderr = run_cli(test_repo, "show", "2")
        if "working" not in stdout:
            print("[FAIL] label not added")
            return False
        print("[OK] label works")

        # Test 11: search command
        print("\n=== Test 11: rewindo search database ===")
        code, stdout, stderr = run_cli(test_repo, "search", "database")
        if code != 0:
            print(f"[FAIL] search failed: {stderr}")
            return False
        print(stdout)
        if "database" not in stdout.lower() or "#2" not in stdout:
            print("[FAIL] search not finding entry")
            return False
        print("[OK] search works")

        # Test 12: revert command
        print("\n=== Test 12: rewindo revert 2 --yes ===")

        # First, let's undo to the initial state
        print("\n--- Step 1: Undo to initial state ---")
        code, stdout, stderr = run_git(test_repo, "status", "--short")
        print(f"Git status before undo: {stdout[:200]}")

        # Check timeline file before undo
        timeline_file = test_repo / ".claude" / "data" / "timeline.jsonl"
        print(f"Timeline file exists before undo: {timeline_file.exists()}")
        if timeline_file.exists():
            with open(timeline_file) as f:
                entries_before = f.read()
            print(f"Timeline entries before undo: {len([l for l in entries_before.split('\\n') if l.strip()])} lines")

        code, stdout, stderr = run_cli(test_repo, "undo", "--yes")
        print(f"Undo output: {stdout}")

        # Check what state we're in now
        code, stdout, stderr = run_git(test_repo, "rev-parse", "HEAD")
        print(f"HEAD after undo: {stdout.strip()[:50]}...")

        code, stdout, stderr = run_git(test_repo, "show", "--stat", "HEAD")
        print(f"Current HEAD contents:\n{stdout}")

        # Check timeline file after undo
        print(f"Timeline file exists after undo: {timeline_file.exists()}")
        if timeline_file.exists():
            with open(timeline_file) as f:
                content = f.read()
            print(f"Timeline content after undo: {content[:200]}")

        # Now revert to checkpoint 2
        print("\n--- Step 2: Revert to checkpoint #2 ---")
        code, stdout, stderr = run_cli(test_repo, "revert", "2", "--yes")
        if code != 0:
            print(f"[FAIL] revert failed: {stderr}")
            print(f"stdout: {stdout}")
            # Try to see what's in the timeline
            if timeline_file.exists():
                with open(timeline_file) as f:
                    print(f"Timeline content: {f.read()}")
            return False
        print(stdout)

        # Check state after revert
        code, stdout, stderr = run_git(test_repo, "status", "--short")
        print(f"Git status after revert to #2: {stdout}")

        # File from checkpoint 2 should exist
        if not (test_repo / "db.py").exists():
            print("[FAIL] db.py not restored after revert")
            return False

        # File from checkpoint 3 should NOT exist (we reverted to #2)
        if (test_repo / "api.py").exists():
            print("[FAIL] api.py exists but shouldn't (reverted to #2)")
            return False

        print("[OK] revert works")

        # Test 13: doctor command
        print("\n=== Test 13: rewindo doctor ===")
        code, stdout, stderr = run_cli(test_repo, "doctor")
        if code != 0:
            print(f"[FAIL] doctor found issues (may be expected): {stdout}")
            # Don't fail on doctor issues, just report
        print(stdout)
        print("[OK] doctor runs")

        # Test 14: export command
        print("\n=== Test 14: rewindo export 1 ===")
        code, stdout, stderr = run_cli(test_repo, "export", "1")
        if code != 0:
            print(f"[FAIL] export failed: {stderr}")
            return False

        # Check export was created
        export_dir = test_repo / "export-00001"
        if not export_dir.exists():
            print("[FAIL] export directory not created")
            return False

        if not (export_dir / "meta.json").exists():
            print("[FAIL] meta.json not exported")
            return False

        if not (export_dir / "prompt.txt").exists():
            print("[FAIL] prompt.txt not exported")
            return False

        if not (export_dir / "diff.patch").exists():
            print("[FAIL] diff.patch not exported")
            return False

        print(f"[OK] export works - created {export_dir}")

        print("\n" + "="*60)
        print("[SUCCESS] All Phase 2 CLI tests passed!")
        print("="*60)
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
