#!/usr/bin/env python3
"""
Rewindo UserPromptSubmit Hook

Captures user prompts when submitted to Claude.

Input (JSON via stdin):
{
  "session_id": "...",
  "cwd": "/path/to/project",
  "hook_event_name": "UserPromptSubmit",
  "prompt": "Full user prompt text..."
}

Output:
- Writes prompt state to .claude/data/prompt_state.json
- Exit code 0: Success (non-blocking)
- Exit code 2: Blocking error (shown to user)
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path


def main():
    # Read hook input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(0)  # Non-blocking error

    # Validate event type
    event_name = input_data.get("hook_event_name")
    if event_name != "UserPromptSubmit":
        print(f"Warning: Expected UserPromptSubmit, got {event_name}", file=sys.stderr)
        sys.exit(0)

    # Extract required fields
    prompt = input_data.get("prompt", "")
    session_id = input_data.get("session_id", "")
    cwd = input_data.get("cwd", "")

    if not cwd:
        print("Error: No cwd in hook input", file=sys.stderr)
        sys.exit(0)

    if not prompt:
        # Empty prompt - nothing to capture
        sys.exit(0)

    # Determine project root
    project_root = Path(cwd)

    # Create data directory
    data_dir = project_root / ".claude" / "data"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Error creating data directory: {e}", file=sys.stderr)
        sys.exit(0)

    # Write prompt state for Stop hook to read
    state_file = data_dir / "prompt_state.json"

    state = {
        "prompt": prompt,
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "cwd": str(project_root)
    }

    try:
        with open(state_file, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Error writing prompt state: {e}", file=sys.stderr)
        sys.exit(0)

    # Success - prompt is captured
    # No stdout output (would be added to context)
    sys.exit(0)


if __name__ == "__main__":
    main()
