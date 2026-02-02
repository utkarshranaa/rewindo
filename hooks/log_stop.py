#!/usr/bin/env python3
"""
Rewindo Stop Hook

Creates checkpoints when Claude finishes responding.

Input (JSON via stdin):
{
  "session_id": "...",
  "cwd": "/path/to/project",
  "hook_event_name": "Stop",
  "stop_hook_active": false
}

What it does:
1. Reads prompt_state.json (written by UserPromptSubmit hook)
2. Checks for git changes using git diff --stat
3. If changes exist:
   - Creates checkpoint using git refs (not commits on branch)
   - Saves diff stats, full diff, and prompt
   - Appends entry to timeline.jsonl
4. Cleans up prompt_state.json

Exit code 0: Success
Exit code 2: Blocking error
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any


def run_git(cwd: Path, *args, capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the specified directory."""
    cmd = ["git"] + list(args)
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture_output,
        text=True
    )


def get_next_entry_id(timeline_path: Path) -> int:
    """Get the next entry ID from timeline file."""
    if not timeline_path.exists():
        return 1

    max_id = 0
    with open(timeline_path, "r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                max_id = max(max_id, entry.get("id", 0))
            except (json.JSONDecodeError, KeyError):
                continue

    return max_id + 1


def parse_git_stat(stat_output: str) -> List[Dict[str, Any]]:
    """
    Parse git diff --stat output into file change list.

    Input format:
    path/to/file.txt | 5 +++--
    another/file.py  | 20 +++++++++++
    """
    files = []

    if not stat_output or not stat_output.strip():
        return files

    for line in stat_output.strip().split("\n"):
        # Match lines like: path/to/file | 5 +---
        match = re.match(r"^\s*(.+?)\s+\|\s*(\d+)\s*([\+\-]*)", line)
        if match:
            file_path = match.group(1).strip()
            total_changes = int(match.group(2))
            indicators = match.group(3)

            # Count additions and deletions from indicators
            additions = indicators.count("+")
            deletions = indicators.count("-")

            files.append({
                "path": file_path,
                "add": additions,
                "del": deletions
            })

    return files


def create_git_checkpoint(cwd: Path, entry_id: int) -> Optional[str]:
    """
    Create a git checkpoint using refs (not branch commits).

    Process:
    1. git add -A (stage all changes)
    2. git write-tree (capture tree state)
    3. git commit-tree (create detached commit)
    4. git update-ref refs/rewindo/checkpoints/<id> (store ref)
    5. git reset --hard HEAD (return to previous state)

    Returns:
        Commit SHA if successful, None otherwise
    """
    try:
        # 1. Stage all changes
        run_git(cwd, "add", "-A", capture_output=False)

        # 2. Capture tree state
        tree_result = run_git(cwd, "write-tree")
        if tree_result.returncode != 0:
            return None
        tree_sha = tree_result.stdout.strip()

        # 3. Get current HEAD (parent commit)
        head_result = run_git(cwd, "rev-parse", "HEAD")
        parent_sha = head_result.stdout.strip() if head_result.returncode == 0 else None

        # 4. Create detached commit
        commit_message = f"rewindo-{entry_id}"
        commit_args = ["commit-tree", tree_sha, "-m", commit_message]
        if parent_sha:
            commit_args.extend(["-p", parent_sha])

        commit_result = run_git(cwd, *commit_args)
        if commit_result.returncode != 0:
            return None
        commit_sha = commit_result.stdout.strip()

        # 5. Store in refs namespace
        ref_name = f"refs/rewindo/checkpoints/{entry_id}"
        update_result = run_git(cwd, "update-ref", ref_name, commit_sha)
        if update_result.returncode != 0:
            return None

        return commit_sha

    except Exception as e:
        print(f"Error creating checkpoint: {e}", file=sys.stderr)
        return None


def save_full_diff(cwd: Path, diff_path: Path) -> bool:
    """Save full git diff to file."""
    try:
        result = run_git(cwd, "diff", "HEAD")
        if result.returncode != 0:
            # Try diff without HEAD (for empty repo)
            result = run_git(cwd, "diff", "--cached")

        if result.returncode == 0 and result.stdout:
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            with open(diff_path, "w") as f:
                f.write(result.stdout)
            return True
        return False
    except Exception as e:
        print(f"Error saving diff: {e}", file=sys.stderr)
        return False


def save_full_prompt(prompt_path: Path, prompt: str) -> None:
    """Save full prompt text to file."""
    try:
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        with open(prompt_path, "w") as f:
            f.write(prompt)
    except Exception as e:
        print(f"Error saving prompt: {e}", file=sys.stderr)


def main():
    # Read hook input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(0)  # Non-blocking error

    # Validate event type
    event_name = input_data.get("hook_event_name")
    if event_name != "Stop":
        sys.exit(0)

    # Extract fields
    cwd = input_data.get("cwd", "")
    if not cwd:
        sys.exit(0)

    project_root = Path(cwd)
    data_dir = project_root / ".claude" / "data"

    # Ensure .claude/data/ is in .gitignore to prevent tracking timeline files
    gitignore = project_root / ".gitignore"
    gitignore_entries = []
    if gitignore.exists():
        gitignore_entries = gitignore.read_text().splitlines()

    # Add .claude/data/ to gitignore if not present
    if ".claude/data/" not in gitignore_entries and "/.claude/data/" not in gitignore_entries:
        try:
            with open(gitignore, "a") as f:
                f.write("\n# Rewindo timeline data\n.claude/data/\n")
            run_git(project_root, "add", ".gitignore")
        except Exception:
            pass  # Non-fatal if we can't update gitignore

    # Read prompt state (written by UserPromptSubmit hook)
    state_file = data_dir / "prompt_state.json"
    if not state_file.exists():
        # No prompt was submitted, nothing to do
        sys.exit(0)

    try:
        with open(state_file, "r") as f:
            state = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading prompt state: {e}", file=sys.stderr)
        state_file.unlink(missing_ok=True)
        sys.exit(0)

    prompt = state.get("prompt", "")
    session_id = state.get("session_id", "")
    timestamp = state.get("timestamp", datetime.now().isoformat())

    # Check for git changes
    diff_stat_result = run_git(project_root, "diff", "--stat", "HEAD")

    has_changes = False
    if diff_stat_result.returncode == 0 and diff_stat_result.stdout.strip():
        has_changes = True

    # Check for staged changes too
    if not has_changes:
        staged_result = run_git(project_root, "diff", "--cached", "--stat")
        if staged_result.returncode == 0 and staged_result.stdout.strip():
            has_changes = True
            diff_stat_result = staged_result

    if not has_changes:
        # No changes, just clean up state file
        state_file.unlink(missing_ok=True)
        sys.exit(0)

    # We have changes - create checkpoint
    timeline_path = data_dir / "timeline.jsonl"
    entry_id = get_next_entry_id(timeline_path)

    # Parse file changes from git stat
    files_changed = parse_git_stat(diff_stat_result.stdout)

    # Create git checkpoint
    commit_sha = create_git_checkpoint(project_root, entry_id)
    if not commit_sha:
        print("Error: Failed to create git checkpoint", file=sys.stderr)
        state_file.unlink(missing_ok=True)
        sys.exit(0)

    # Save full diff
    diff_path = data_dir / "diffs" / f"{entry_id:05d}.patch"
    save_full_diff(project_root, diff_path)

    # Save full prompt
    prompt_path = data_dir / "prompts" / f"{entry_id:05d}.txt"
    save_full_prompt(prompt_path, prompt)

    # Create timeline entry
    entry = {
        "id": entry_id,
        "ts": timestamp,
        "session": session_id,
        "prompt": prompt[:500],  # Truncate in timeline (full in file)
        "prompt_ref": f"prompts/{entry_id:05d}.txt",
        "checkpoint_ref": f"refs/rewindo/checkpoints/{entry_id}",
        "checkpoint_sha": commit_sha,
        "files": files_changed,
        "diff_path": f"diffs/{entry_id:05d}.patch",
        "labels": [],
        "notes": ""
    }

    # Append to timeline
    try:
        timeline_path.parent.mkdir(parents=True, exist_ok=True)
        with open(timeline_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"Error writing timeline: {e}", file=sys.stderr)

    # Clean up state file
    state_file.unlink(missing_ok=True)

    # Success - optionally output to stderr for visibility in verbose mode
    print(f"[rewindo] Checkpoint #{entry_id} created: {len(files_changed)} file(s) changed", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
