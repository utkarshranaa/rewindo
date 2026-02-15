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
    try:
        # Read hook input from stdin
        input_data = json.load(sys.stdin)

        # Validate event type
        event_name = input_data.get("hook_event_name")
        if event_name != "UserPromptSubmit":
            sys.exit(0)

        # Extract required fields
        prompt = input_data.get("prompt", "")
        session_id = input_data.get("session_id", "")
        cwd = input_data.get("cwd", "")

        if not cwd or not prompt:
            sys.exit(0)

        # Determine project root
        project_root = Path(cwd)

        # Create data directory
        data_dir = project_root / ".claude" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # Write prompt state for Stop hook to read
        state_file = data_dir / "prompt_state.json"

        state = {
            "prompt": prompt,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "cwd": str(project_root)
        }

        with open(state_file, "w") as f:
            json.dump(state, f)

    except Exception:
        # Silently exit — never write to stderr as Claude Code shows it as a hook error
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
