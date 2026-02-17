#!/usr/bin/env python3
"""Tests for hook error handling — verifies hooks never write to stderr
and always exit 0 regardless of bad input."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
PROMPT_HOOK = HOOKS_DIR / "log_prompt.py"
STOP_HOOK = HOOKS_DIR / "log_stop.py"


def run_hook(hook_path: Path, stdin_text: str) -> subprocess.CompletedProcess:
    """Run a hook with raw stdin text, return result."""
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=stdin_text,
        capture_output=True,
        text=True,
    )


def run_hook_json(hook_path: Path, data: dict) -> subprocess.CompletedProcess:
    return run_hook(hook_path, json.dumps(data))


# ---------------------------------------------------------------------------
# log_prompt.py
# ---------------------------------------------------------------------------

class TestPromptHookErrorHandling:

    def test_invalid_json_exits_zero(self):
        result = run_hook(PROMPT_HOOK, "not valid json {{{{")
        assert result.returncode == 0

    def test_invalid_json_no_stderr(self):
        result = run_hook(PROMPT_HOOK, "not valid json {{{{")
        assert result.stderr == ""

    def test_empty_stdin_exits_zero(self):
        result = run_hook(PROMPT_HOOK, "")
        assert result.returncode == 0

    def test_empty_stdin_no_stderr(self):
        result = run_hook(PROMPT_HOOK, "")
        assert result.stderr == ""

    def test_wrong_event_name_exits_zero(self):
        result = run_hook_json(PROMPT_HOOK, {
            "hook_event_name": "Stop",
            "cwd": "/tmp",
            "prompt": "hello",
            "session_id": "s1"
        })
        assert result.returncode == 0

    def test_wrong_event_name_no_stderr(self):
        result = run_hook_json(PROMPT_HOOK, {
            "hook_event_name": "Stop",
            "cwd": "/tmp",
            "prompt": "hello",
            "session_id": "s1"
        })
        assert result.stderr == ""

    def test_missing_cwd_exits_zero(self):
        result = run_hook_json(PROMPT_HOOK, {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "hello",
            "session_id": "s1"
        })
        assert result.returncode == 0

    def test_missing_cwd_no_stderr(self):
        result = run_hook_json(PROMPT_HOOK, {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "hello",
            "session_id": "s1"
        })
        assert result.stderr == ""

    def test_empty_prompt_exits_zero(self):
        result = run_hook_json(PROMPT_HOOK, {
            "hook_event_name": "UserPromptSubmit",
            "cwd": "/tmp",
            "prompt": "",
            "session_id": "s1"
        })
        assert result.returncode == 0

    def test_empty_prompt_no_stderr(self):
        result = run_hook_json(PROMPT_HOOK, {
            "hook_event_name": "UserPromptSubmit",
            "cwd": "/tmp",
            "prompt": "",
            "session_id": "s1"
        })
        assert result.stderr == ""

    def test_nonexistent_cwd_exits_zero(self):
        result = run_hook_json(PROMPT_HOOK, {
            "hook_event_name": "UserPromptSubmit",
            "cwd": "/nonexistent/path/that/does/not/exist",
            "prompt": "hello",
            "session_id": "s1"
        })
        assert result.returncode == 0

    def test_nonexistent_cwd_no_stderr(self):
        result = run_hook_json(PROMPT_HOOK, {
            "hook_event_name": "UserPromptSubmit",
            "cwd": "/nonexistent/path/that/does/not/exist",
            "prompt": "hello",
            "session_id": "s1"
        })
        assert result.stderr == ""

    def test_no_stdout_on_success(self, tmp_path):
        """Successful hook run should produce no stdout (would pollute context)."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        result = run_hook_json(PROMPT_HOOK, {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "hello world",
            "session_id": "s1"
        })
        assert result.stdout == ""

    def test_unicode_prompt_no_stderr(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        result = run_hook_json(PROMPT_HOOK, {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "こんにちは 🎉 résumé",
            "session_id": "s1"
        })
        assert result.returncode == 0
        assert result.stderr == ""

    def test_very_long_prompt_no_stderr(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        result = run_hook_json(PROMPT_HOOK, {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "x" * 100_000,
            "session_id": "s1"
        })
        assert result.returncode == 0
        assert result.stderr == ""


# ---------------------------------------------------------------------------
# log_stop.py
# ---------------------------------------------------------------------------

class TestStopHookErrorHandling:

    def test_invalid_json_exits_zero(self):
        result = run_hook(STOP_HOOK, "not valid json {{{{")
        assert result.returncode == 0

    def test_invalid_json_no_stderr(self):
        result = run_hook(STOP_HOOK, "not valid json {{{{")
        assert result.stderr == ""

    def test_empty_stdin_exits_zero(self):
        result = run_hook(STOP_HOOK, "")
        assert result.returncode == 0

    def test_empty_stdin_no_stderr(self):
        result = run_hook(STOP_HOOK, "")
        assert result.stderr == ""

    def test_wrong_event_name_exits_zero(self):
        result = run_hook_json(STOP_HOOK, {
            "hook_event_name": "UserPromptSubmit",
            "cwd": "/tmp",
            "session_id": "s1"
        })
        assert result.returncode == 0

    def test_wrong_event_name_no_stderr(self):
        result = run_hook_json(STOP_HOOK, {
            "hook_event_name": "UserPromptSubmit",
            "cwd": "/tmp",
            "session_id": "s1"
        })
        assert result.stderr == ""

    def test_missing_cwd_exits_zero(self):
        result = run_hook_json(STOP_HOOK, {
            "hook_event_name": "Stop",
            "session_id": "s1"
        })
        assert result.returncode == 0

    def test_missing_cwd_no_stderr(self):
        result = run_hook_json(STOP_HOOK, {
            "hook_event_name": "Stop",
            "session_id": "s1"
        })
        assert result.stderr == ""

    def test_nonexistent_cwd_exits_zero(self):
        result = run_hook_json(STOP_HOOK, {
            "hook_event_name": "Stop",
            "cwd": "/nonexistent/path/that/does/not/exist",
            "session_id": "s1"
        })
        assert result.returncode == 0

    def test_nonexistent_cwd_no_stderr(self):
        result = run_hook_json(STOP_HOOK, {
            "hook_event_name": "Stop",
            "cwd": "/nonexistent/path/that/does/not/exist",
            "session_id": "s1"
        })
        assert result.stderr == ""

    def test_no_stdout_produced(self, tmp_path):
        """Stop hook should never write to stdout."""
        result = run_hook_json(STOP_HOOK, {
            "hook_event_name": "Stop",
            "cwd": str(tmp_path),
            "session_id": "s1"
        })
        assert result.stdout == ""

    def test_no_prompt_state_exits_zero(self, tmp_path):
        """Stop hook with no prompt_state.json should exit cleanly."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        result = run_hook_json(STOP_HOOK, {
            "hook_event_name": "Stop",
            "cwd": str(tmp_path),
            "session_id": "s1"
        })
        assert result.returncode == 0
        assert result.stderr == ""
