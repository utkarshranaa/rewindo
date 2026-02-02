#!/usr/bin/env python3
"""Demo the expand feature with longer prompts."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    """Demo expand feature."""
    PROJECT_ROOT = Path(__file__).parent.parent
    HOOKS_DIR = PROJECT_ROOT / "hooks"

    with tempfile.TemporaryDirectory() as temp_dir:
        test_repo = Path(temp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=test_repo, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=test_repo, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=test_repo, capture_output=True)

        # Initial commit
        (test_repo / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "-A"], cwd=test_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=test_repo, capture_output=True)

        # Create a checkpoint with a long prompt
        long_prompt = """I need you to implement a comprehensive user authentication system with the following requirements:

1. User registration with email verification
2. Password reset flow with secure tokens
3. JWT-based session management
4. OAuth2 integration for Google and GitHub
5. Two-factor authentication using TOTP
6. Session management with refresh tokens
7. Rate limiting on auth endpoints
8. Password strength validation
9. Account lockout after failed attempts
10. Audit logging for all auth events

For the user model, I need fields for email, password_hash, is_verified, is_active, created_at, updated_at, last_login_at, failed_login_attempts, and lockout_until.

Please use SQLAlchemy for ORM, bcrypt for password hashing, and PyJWT for tokens."""

        # Simulate prompt capture
        input_file = test_repo / "prompt_input.json"
        input_file.write_text(json.dumps({
            "session_id": "test",
            "cwd": str(test_repo),
            "hook_event_name": "UserPromptSubmit",
            "prompt": long_prompt
        }))

        subprocess.run(
            [sys.executable, str(HOOKS_DIR / "log_prompt.py")],
            cwd=test_repo,
            stdin=input_file.open(),
            capture_output=True
        )

        # Make a change
        (test_repo / "auth.py").write_text("# Auth system\n")
        subprocess.run(["git", "add", "-A"], cwd=test_repo, capture_output=True)

        # Simulate stop hook
        input_file.write_text(json.dumps({
            "session_id": "test",
            "cwd": str(test_repo),
            "hook_event_name": "Stop",
            "stop_hook_active": False
        }))

        subprocess.run(
            [sys.executable, str(HOOKS_DIR / "log_stop.py")],
            cwd=test_repo,
            stdin=input_file.open(),
            capture_output=True
        )

        print("="*70)
        print("DEMO: Expand Feature with Long Prompts")
        print("="*70)

        # Default view (compact)
        print("\n1. Default view (60 chars) - notice the [+] indicator:\n")
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "bin" / "rewindo"),
             "--cwd", str(test_repo), "list"],
            capture_output=True,
            text=True
        )
        print(result.stdout)

        # Expanded view
        print("\n2. Expanded view (200 chars) with --expand flag:\n")
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "bin" / "rewindo"),
             "--cwd", str(test_repo), "list", "--expand"],
            capture_output=True,
            text=True
        )
        print(result.stdout)

        # Custom expand length
        print("\n3. Custom expand length (500 chars):\n")
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "bin" / "rewindo"),
             "--cwd", str(test_repo), "list", "--expand", "--expand-chars", "500"],
            capture_output=True,
            text=True
        )
        print(result.stdout)

        # Full prompt
        print("\n4. Full prompt with get-prompt:\n")
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "bin" / "rewindo"),
             "--cwd", str(test_repo), "get-prompt", "1"],
            capture_output=True,
            text=True
        )
        print(result.stdout)

        print("\n" + "="*70)
        print("Key points:")
        print("  - [+] indicates prompt is longer than shown")
        print("  - Use --expand to see 200 characters")
        print("  - Use --expand --expand-chars N for custom length")
        print("  - Use get-prompt <id> for full prompt")
        print("="*70)


if __name__ == "__main__":
    main()
