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
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any


@contextmanager
def lock_timeline(data_dir: Path, timeout: float = 10.0):
    """Acquire an exclusive lock on the timeline file."""
    lock_path = data_dir / "timeline.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout

    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                try:
                    lock_path.unlink()
                except OSError:
                    pass
                raise TimeoutError("Could not acquire timeline lock")
            time.sleep(0.05)

    try:
        yield
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass


def run_git(cwd: Path, *args, capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the specified directory."""
    cmd = ["git"] + list(args)
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            timeout=25
        )
    except subprocess.TimeoutExpired:
        # Return a failed result so callers treat it as a git error
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="timeout")


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


def get_last_checkpoint_sha(timeline_path: Path) -> Optional[str]:
    """Get the checkpoint SHA from the most recent timeline entry."""
    if not timeline_path.exists():
        return None
    last_sha = None
    with open(timeline_path, "r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                sha = entry.get("checkpoint_sha")
                if sha:
                    last_sha = sha
            except (json.JSONDecodeError, KeyError):
                continue
    return last_sha


def get_new_untracked_files(cwd: Path) -> List[str]:
    """Return non-gitignored untracked files (candidates for new files Claude created)."""
    result = run_git(cwd, "ls-files", "--others", "--exclude-standard")
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [f for f in result.stdout.strip().splitlines() if f.strip()]


def get_checkpoint_tree_files(cwd: Path, sha: str) -> set:
    """Return the set of all file paths stored in a checkpoint's tree."""
    result = run_git(cwd, "ls-tree", "-r", "--name-only", sha)
    if result.returncode != 0 or not result.stdout.strip():
        return set()
    return set(result.stdout.strip().splitlines())


def make_new_file_diff(file_path: Path, relative_path: str) -> str:
    """Build a unified diff string for a brand-new file (vs /dev/null)."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        header = (
            f"diff --git a/{relative_path} b/{relative_path}\n"
            f"new file mode 100644\n"
            f"--- /dev/null\n"
            f"+++ b/{relative_path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n"
        )
        body = "\n".join(f"+{line}" for line in lines)
        return header + body + "\n"
    except Exception:
        return ""


def filter_diff_output(diff_text: str, exclude_paths: set) -> str:
    """Remove sections for specified paths from a unified diff string."""
    if not exclude_paths or not diff_text:
        return diff_text
    result = []
    current_section: List[str] = []
    current_path: Optional[str] = None
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current_section and current_path not in exclude_paths:
                result.extend(current_section)
            current_section = [line]
            # Extract path after " b/" — handles filenames with spaces correctly.
            # Line format: "diff --git a/<path> b/<path>"
            m = re.search(r" b/(.+?)[\r\n]*$", line)
            current_path = m.group(1) if m else None
        else:
            current_section.append(line)
    if current_section and current_path not in exclude_paths:
        result.extend(current_section)
    return "".join(result)


def get_prev_untracked_changes(
    cwd: Path,
    all_new_untracked: List[str],
    checkpoint_tree: set,
    prev_sha: str,
) -> List[Dict[str, Any]]:
    """For untracked files already captured in a previous checkpoint, check if they changed.

    git diff <prev_sha> shows these as false deletions (they're in the checkpoint tree but
    not in the real git index). We compare content directly instead.
    Returns file-change dicts only for files whose content actually changed.
    """
    import difflib

    changed = []
    for path in all_new_untracked:
        if path not in checkpoint_tree:
            continue  # truly new — handled separately
        cp_result = run_git(cwd, "show", f"{prev_sha}:{path}")
        if cp_result.returncode != 0:
            continue
        try:
            cur_content = (cwd / path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if cur_content == cp_result.stdout:
            continue  # unchanged — skip entirely
        # File changed: compute line-level add/del counts
        cp_lines = cp_result.stdout.splitlines(keepends=True)
        cur_lines = cur_content.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(cp_lines, cur_lines))
        add = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
        del_ = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
        changed.append({"path": path, "add": add, "del": del_})
    return changed


def make_modified_untracked_diff(
    prev_content: str, cur_content: str, relative_path: str
) -> str:
    """Build a unified diff for an untracked file that changed since the last checkpoint."""
    import difflib

    prev_lines = prev_content.splitlines(keepends=True)
    cur_lines = cur_content.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(
            prev_lines, cur_lines,
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
        )
    )
    if not diff:
        return ""
    return f"diff --git a/{relative_path} b/{relative_path}\n" + "".join(diff)


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

    Uses a temporary GIT_INDEX_FILE to avoid modifying the user's real index.

    Process:
    1. Create temporary index file
    2. git read-tree HEAD (populate temp index from HEAD)
    3. git add -A (stage all changes in temp index)
    4. git write-tree (capture tree state from temp index)
    5. git commit-tree (create detached commit)
    6. git update-ref refs/rewindo/checkpoints/<id> (store ref)
    7. Clean up temp index file

    Returns:
        Commit SHA if successful, None otherwise
    """
    temp_index_fd = None
    temp_index_path = None

    try:
        # 1. Create temporary index file
        temp_index_fd, temp_index_path = tempfile.mkstemp(suffix=".index")
        os.close(temp_index_fd)
        temp_index_fd = None

        # Set GIT_INDEX_FILE to use our temp index
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = temp_index_path

        # 2. Initialize the temp index from HEAD (if exists)
        read_tree_result = subprocess.run(
            ["git", "read-tree", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
            timeout=25
        )
        if read_tree_result.returncode != 0:
            # HEAD might not exist (empty repo), that's ok
            pass

        # 3. Stage all changes to temp index
        add_result = subprocess.run(
            ["git", "add", "-A"],
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
            timeout=25
        )
        if add_result.returncode != 0:
            return None

        # 4. Capture tree state from temp index
        tree_result = subprocess.run(
            ["git", "write-tree"],
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
            timeout=25
        )
        if tree_result.returncode != 0:
            return None
        tree_sha = tree_result.stdout.strip()

        # 5. Get current HEAD (parent commit)
        head_result = run_git(cwd, "rev-parse", "HEAD")
        parent_sha = head_result.stdout.strip() if head_result.returncode == 0 else None

        # 6. Create detached commit
        commit_message = f"rewindo-{entry_id}"
        commit_args = ["git", "commit-tree", tree_sha, "-m", commit_message]
        if parent_sha:
            commit_args.extend(["-p", parent_sha])

        commit_result = subprocess.run(
            commit_args,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
            timeout=25
        )
        if commit_result.returncode != 0:
            return None
        commit_sha = commit_result.stdout.strip()

        # 7. Store in refs namespace
        ref_name = f"refs/rewindo/checkpoints/{entry_id}"
        update_result = run_git(cwd, "update-ref", ref_name, commit_sha)
        if update_result.returncode != 0:
            return None

        return commit_sha

    except Exception:
        return None

    finally:
        # Clean up temp index file
        if temp_index_fd is not None:
            try:
                os.close(temp_index_fd)
            except (IOError, OSError):
                pass

        if temp_index_path and os.path.exists(temp_index_path):
            try:
                os.unlink(temp_index_path)
            except (IOError, OSError):
                pass


def save_full_prompt(prompt_path: Path, prompt: str) -> None:
    """Save full prompt text to file."""
    try:
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        with open(prompt_path, "w") as f:
            f.write(prompt)
    except Exception as e:
        print(f"Error saving prompt: {e}", file=sys.stderr)


def main():
    try:
        # Read hook input from stdin
        input_data = json.load(sys.stdin)

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

        # Ensure rewindo-managed paths are in .gitignore
        gitignore = project_root / ".gitignore"
        gitignore_entries = []
        if gitignore.exists():
            gitignore_entries = gitignore.read_text().splitlines()

        needs_update = []
        if ".claude/data/" not in gitignore_entries and "/.claude/data/" not in gitignore_entries:
            needs_update.append(".claude/data/")
        if (
            ".claude/settings.local.json" not in gitignore_entries
            and "/.claude/settings.local.json" not in gitignore_entries
        ):
            needs_update.append(".claude/settings.local.json")

        if needs_update:
            try:
                with open(gitignore, "a") as f:
                    f.write("\n# Rewindo — auto-ignored paths\n")
                    for entry in needs_update:
                        f.write(f"{entry}\n")
            except Exception:
                pass

        # Read prompt state (written by UserPromptSubmit hook)
        state_file = data_dir / "prompt_state.json"
        if not state_file.exists():
            sys.exit(0)

        try:
            with open(state_file, "r") as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            state_file.unlink(missing_ok=True)
            sys.exit(0)

        prompt = state.get("prompt", "")
        session_id = state.get("session_id", "")
        timestamp = state.get("timestamp", datetime.now().isoformat())

        # Determine comparison base: previous checkpoint or HEAD
        timeline_path = data_dir / "timeline.jsonl"
        prev_sha = get_last_checkpoint_sha(timeline_path)
        diff_base = prev_sha if prev_sha else "HEAD"

        # Gather all currently untracked non-gitignored files
        all_new_untracked = get_new_untracked_files(project_root)
        untracked_set = set(all_new_untracked)

        # Diff stat vs comparison base — used for tracked-file per-prompt delta.
        # NOTE: untracked files that were captured in a previous checkpoint appear here
        # as false deletions (they're in the checkpoint tree but not in the real index).
        # We filter them out and handle them separately below.
        diff_stat_result = run_git(project_root, "diff", "--stat", diff_base)
        all_stat_files = parse_git_stat(diff_stat_result.stdout) if diff_stat_result.returncode == 0 else []
        real_tracked_changes = [f for f in all_stat_files if f["path"] not in untracked_set]

        if prev_sha:
            checkpoint_tree = get_checkpoint_tree_files(project_root, prev_sha)
            # Truly new: appeared since last checkpoint
            truly_new = [f for f in all_new_untracked if f not in checkpoint_tree]
            # Previously captured untracked files that actually changed
            prev_untracked_changes = get_prev_untracked_changes(
                project_root, all_new_untracked, checkpoint_tree, prev_sha
            )
        else:
            checkpoint_tree = set()
            truly_new = all_new_untracked
            prev_untracked_changes = []

        has_changes = bool(real_tracked_changes) or bool(prev_untracked_changes) or bool(truly_new)

        if not has_changes:
            state_file.unlink(missing_ok=True)
            sys.exit(0)

        # We have changes - create checkpoint
        with lock_timeline(data_dir):
            timeline_path = data_dir / "timeline.jsonl"
            entry_id = get_next_entry_id(timeline_path)

            # files_changed: real tracked deltas + changed prev-captured untracked + truly new
            files_changed = real_tracked_changes + prev_untracked_changes
            for new_file in truly_new:
                try:
                    line_count = len(
                        (project_root / new_file).read_text(
                            encoding="utf-8", errors="replace"
                        ).splitlines()
                    )
                except Exception:
                    line_count = 1
                files_changed.append({"path": new_file, "add": line_count, "del": 0})

            commit_sha = create_git_checkpoint(project_root, entry_id)
            if not commit_sha:
                state_file.unlink(missing_ok=True)
                sys.exit(0)

            # Save full diff: filter false-deletion noise, append new/changed untracked diffs
            diff_path = data_dir / "diffs" / f"{entry_id:05d}.patch"
            try:
                raw_diff = run_git(project_root, "diff", diff_base)
                raw_text = raw_diff.stdout if raw_diff.returncode == 0 else ""
                # Strip false deletions caused by untracked files in the checkpoint tree
                filtered = filter_diff_output(raw_text, untracked_set)
                diff_path.parent.mkdir(parents=True, exist_ok=True)
                with open(diff_path, "w") as f:
                    f.write(filtered)
                    # Append diffs for previously-captured untracked files that changed
                    for entry in prev_untracked_changes:
                        cp_result = run_git(project_root, "show", f"{prev_sha}:{entry['path']}")
                        if cp_result.returncode == 0:
                            try:
                                cur = (project_root / entry["path"]).read_text(
                                    encoding="utf-8", errors="replace"
                                )
                                f.write(make_modified_untracked_diff(cp_result.stdout, cur, entry["path"]))
                            except Exception:
                                pass
                    # Append diffs for truly new files
                    for new_file in truly_new:
                        f.write(make_new_file_diff(project_root / new_file, new_file))
            except Exception:
                pass

            # Save full prompt
            prompt_path = data_dir / "prompts" / f"{entry_id:05d}.txt"
            save_full_prompt(prompt_path, prompt)

            # Create timeline entry
            entry = {
                "id": entry_id,
                "ts": timestamp,
                "session": session_id,
                "prompt": prompt[:500],
                "prompt_ref": f"prompts/{entry_id:05d}.txt",
                "checkpoint_ref": f"refs/rewindo/checkpoints/{entry_id}",
                "checkpoint_sha": commit_sha,
                "files": files_changed,
                "diff_path": f"diffs/{entry_id:05d}.patch",
                "labels": [],
                "notes": ""
            }

            try:
                timeline_path.parent.mkdir(parents=True, exist_ok=True)
                with open(timeline_path, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception:
                pass

        # Clean up state file
        state_file.unlink(missing_ok=True)

    except Exception:
        # Silently exit — never write to stderr as Claude Code shows it as a hook error
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
