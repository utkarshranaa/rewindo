"""
Rewindo - Core library for timeline management.

This module provides the main Rewindo class for:
- Reading/writing timeline entries
- Managing git refs for checkpoints
- Retrieving prompts and diffs with bounds
- Reverting to checkpoints
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


class Rewindo:
    """Main Rewindo class for timeline management."""

    # Ref namespace for checkpoints
    REFS_PREFIX = "refs/rewindo/checkpoints"

    # Data directory structure
    TIMELINE_FILE = "timeline.jsonl"
    PROMPTS_DIR = "prompts"
    DIFFS_DIR = "diffs"

    def __init__(self, cwd: Optional[str] = None, data_dir: str = ".claude/data"):
        """
        Initialize Rewindo.

        Args:
            cwd: Working directory (default: current directory)
            data_dir: Data directory relative to project root
        """
        self.root = Path(cwd) if cwd else Path.cwd()
        self.data_dir = self.root / data_dir

        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / self.PROMPTS_DIR).mkdir(exist_ok=True)
        (self.data_dir / self.DIFFS_DIR).mkdir(exist_ok=True)

        # Verify we're in a git repo
        if not self._is_git_repo():
            raise ValueError(f"Not a git repository: {self.root}")

    def _is_git_repo(self) -> bool:
        """Check if current directory is a git repository."""
        git_dir = self.root / ".git"
        return git_dir.exists() and git_dir.is_dir()

    def _run_git(self, *args, capture_output: bool = True, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Run a git command."""
        cmd = ["git"] + list(args)
        return subprocess.run(
            cmd,
            cwd=cwd or self.root,
            capture_output=capture_output,
            text=True
        )

    def _get_timeline_path(self) -> Path:
        """Get path to timeline file."""
        return self.data_dir / self.TIMELINE_FILE

    def _get_prompt_path(self, entry_id: int) -> Path:
        """Get path to prompt file for an entry."""
        return self.data_dir / self.PROMPTS_DIR / f"{entry_id:05d}.txt"

    def _get_diff_path(self, entry_id: int) -> Path:
        """Get path to diff file for an entry."""
        return self.data_dir / self.DIFFS_DIR / f"{entry_id:05d}.patch"

    def _get_ref_name(self, entry_id: int) -> str:
        """Get git ref name for an entry."""
        return f"{self.REFS_PREFIX}/{entry_id}"

    def _normalize_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize an entry to ensure it has all required fields.

        Handles backward compatibility by adding missing fields with defaults.

        Args:
            entry: Raw entry from timeline

        Returns:
            Normalized entry with all required fields
        """
        # Default actor to "assistant" for old entries
        if "actor" not in entry:
            entry["actor"] = "assistant"

        # Ensure parent_sha exists (can be None for initial entries)
        if "parent_sha" not in entry:
            entry["parent_sha"] = None

        return entry

    def list_entries(self, limit: int = 20, query: Optional[str] = None, actor: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List timeline entries.

        Args:
            limit: Maximum number of entries to return
            query: Optional query string to filter by
            actor: Optional actor filter ("assistant" or "user")

        Returns:
            List of entry dictionaries with limited fields for token efficiency
        """
        entries = []
        timeline_path = self._get_timeline_path()

        if not timeline_path.exists():
            return []

        with open(timeline_path, "r") as f:
            for line in reversed(list(f)):  # Newest first
                if len(entries) >= limit:
                    break
                try:
                    entry = json.loads(line)
                    entry = self._normalize_entry(entry)

                    if query:
                        # Search in prompt text or message
                        prompt = entry.get("prompt", "")
                        message = entry.get("message", "")
                        if query.lower() not in prompt.lower() and query.lower() not in message.lower():
                            continue

                    if actor and entry.get("actor") != actor:
                        continue

                    # Return token-efficient summary
                    entries.append({
                        "id": entry["id"],
                        "ts": entry["ts"],
                        "actor": entry.get("actor", "assistant"),
                        "prompt_snippet": entry.get("prompt", entry.get("message", ""))[:80],
                        "files": entry.get("files", []),
                        "labels": entry.get("labels", [])
                    })
                except (json.JSONDecodeError, KeyError):
                    continue

        return entries

    def get_entry(self, entry_id: int) -> Optional[Dict[str, Any]]:
        """
        Get full entry by ID.

        Args:
            entry_id: Entry ID

        Returns:
            Entry dictionary or None if not found
        """
        timeline_path = self._get_timeline_path()

        if not timeline_path.exists():
            return None

        with open(timeline_path, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("id") == entry_id:
                        return self._normalize_entry(entry)
                except (json.JSONDecodeError, KeyError):
                    continue

        return None

    def get_prompt(self, entry_id: int, max_chars: int = 2000, offset: int = 0) -> Optional[str]:
        """
        Get prompt text with server-side bounds.

        Args:
            entry_id: Entry ID
            max_chars: Maximum characters to return
            offset: Character offset to start from

        Returns:
            Prompt text or None if not found
        """
        prompt_path = self._get_prompt_path(entry_id)

        if not prompt_path.exists():
            # Try reading from timeline entry
            entry = self.get_entry(entry_id)
            if entry and "prompt" in entry:
                prompt = entry["prompt"]
            else:
                return None
        else:
            with open(prompt_path, "r") as f:
                prompt = f.read()

        # Enforce server-side bounds
        end = offset + max_chars
        return prompt[offset:end]

    def get_next_entry_id(self) -> int:
        """
        Get the next available entry ID.

        Returns:
            Next entry ID (1 if timeline doesn't exist)
        """
        timeline_path = self._get_timeline_path()

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

    def append_entry(
        self,
        actor: str,
        checkpoint_sha: str,
        files: List[Dict[str, Any]],
        prompt: Optional[str] = None,
        message: Optional[str] = None,
        parent_sha: Optional[str] = None,
        session: Optional[str] = None,
        diff_path: Optional[str] = None
    ) -> int:
        """
        Append a new entry to the timeline.

        Args:
            actor: "assistant" or "user"
            checkpoint_sha: Git commit SHA for this step
            files: List of file change dicts
            prompt: Prompt text (for assistant steps)
            message: Message/description (for user steps)
            parent_sha: Parent commit SHA
            session: Session ID
            diff_path: Path to diff file

        Returns:
            Entry ID of the created entry
        """
        entry_id = self.get_next_entry_id()
        timestamp = datetime.now().isoformat()

        # Build the entry
        entry = {
            "id": entry_id,
            "ts": timestamp,
            "actor": actor,
            "checkpoint_sha": checkpoint_sha,
            "checkpoint_ref": f"refs/rewindo/checkpoints/{entry_id}",
            "files": files,
            "labels": [],
            "notes": ""
        }

        # Add optional fields
        if parent_sha is not None:
            entry["parent_sha"] = parent_sha

        if session:
            entry["session"] = session

        if prompt:
            entry["prompt"] = prompt[:500]  # Truncate in timeline
            entry["prompt_ref"] = f"prompts/{entry_id:05d}.txt"

        if message:
            entry["message"] = message

        if diff_path:
            entry["diff_path"] = diff_path

        # Append to timeline
        timeline_path = self._get_timeline_path()
        timeline_path.parent.mkdir(parents=True, exist_ok=True)

        with open(timeline_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        return entry_id

    def get_diff(
        self,
        entry_id: int,
        max_lines: int = 200,
        offset_lines: int = 0,
        file_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Get diff with server-side bounds.

        Args:
            entry_id: Entry ID
            max_lines: Maximum lines to return
            offset_lines: Line offset to start from
            file_path: Optional specific file to filter by

        Returns:
            Diff text or None if not found
        """
        diff_path = self._get_diff_path(entry_id)

        if not diff_path.exists():
            # Try reading from timeline entry
            entry = self.get_entry(entry_id)
            if not entry:
                return None
            # Entry doesn't contain full diff by default (token efficiency)
            return None

        with open(diff_path, "r") as f:
            lines = f.readlines()

        # Filter by file if requested
        if file_path:
            lines = self._filter_diff_by_file(lines, file_path)

        # Enforce server-side bounds
        end = offset_lines + max_lines
        return "".join(lines[offset_lines:end])

    def _filter_diff_by_file(self, diff_lines: List[str], file_path: str) -> List[str]:
        """Filter diff lines to only show changes for a specific file."""
        result = []
        in_target_file = False

        for line in diff_lines:
            # Check for diff header
            if line.startswith("diff --git"):
                if file_path in line:
                    in_target_file = True
                    result.append(line)
                else:
                    in_target_file = False
            elif in_target_file:
                result.append(line)

        return result

    def revert_to(self, entry_id: int) -> bool:
        """
        Revert working tree to checkpoint.

        Args:
            entry_id: Entry ID to revert to

        Returns:
            True if successful
        """
        # Try to get checkpoint_sha from journal entry first
        entry = self.get_entry(entry_id)
        if not entry:
            raise ValueError(f"Entry #{entry_id} not found")

        checkpoint_sha = entry.get("checkpoint_sha")
        if not checkpoint_sha:
            # Fallback to old ref-based approach for backward compatibility
            ref_name = self._get_ref_name(entry_id)
            result = self._run_git("rev-parse", ref_name)
            if result.returncode != 0:
                # Try new ref location
                ref_name = f"refs/rewindo/steps/{entry_id}"
                result = self._run_git("rev-parse", ref_name)
                if result.returncode != 0:
                    raise ValueError(f"Checkpoint #{entry_id} not found")
            checkpoint_sha = result.stdout.strip()

        # Reset working tree
        # First, stash the timeline file so we don't lose newer entries
        timeline_backup = None
        if self._get_timeline_path().exists():
            timeline_backup = self._get_timeline_path().read_text()

        result = self._run_git("reset", "--hard", checkpoint_sha)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to reset to checkpoint: {result.stderr}")

        # Restore timeline file if we had a backup
        if timeline_backup:
            self._get_timeline_path().write_text(timeline_backup)

        # Show disclaimer after revert
        print("\n" + "="*70, file=sys.stderr)
        print("IMPORTANT: Dependencies may be out of sync!", file=sys.stderr)
        print("="*70, file=sys.stderr)
        print("You reverted to an earlier state. Your installed packages may not match.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Recommended actions:", file=sys.stderr)
        print("  • npm install        # JavaScript/Node.js projects", file=sys.stderr)
        print("  • pip install -r requirements.txt  # Python projects", file=sys.stderr)
        print("  • bundle install     # Ruby projects", file=sys.stderr)
        print("  • cargo build        # Rust projects", file=sys.stderr)
        print("", file=sys.stderr)
        print("Run the appropriate command for your project type.", file=sys.stderr)
        print("="*70 + "\n", file=sys.stderr)

        return True

    def undo(self) -> bool:
        """
        Undo the last checkpoint by reverting to its parent commit.

        This reverts to the state immediately BEFORE the last checkpoint.

        Returns:
            True if successful
        """
        entries = self.list_entries(limit=1)
        if not entries:
            raise ValueError("No checkpoints to undo")

        last_id = entries[0]["id"]

        # Try to get the checkpoint ref (try steps location first, then checkpoints for backward compatibility)
        ref_name = f"refs/rewindo/steps/{last_id}"
        result = self._run_git("rev-parse", ref_name)
        if result.returncode != 0:
            # Fallback to old checkpoints location
            ref_name = self._get_ref_name(last_id)
            result = self._run_git("rev-parse", ref_name)
            if result.returncode != 0:
                raise ValueError(f"Checkpoint #{last_id} not found")

        # Get the parent commit (first parent, ^1)
        parent_result = self._run_git("rev-parse", f"{ref_name}^1")
        if parent_result.returncode != 0:
            raise ValueError(f"Cannot find parent of checkpoint #{last_id}")

        parent_sha = parent_result.stdout.strip()

        # Reset to parent (state before the checkpoint)
        result = self._run_git("reset", "--hard", parent_sha)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to reset: {result.stderr}")

        # Show disclaimer after undo
        print("\n" + "="*70, file=sys.stderr)
        print("IMPORTANT: Dependencies may be out of sync!", file=sys.stderr)
        print("="*70, file=sys.stderr)
        print("You undid the last checkpoint. Your installed packages may not match.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Recommended actions:", file=sys.stderr)
        print("  • npm install        # JavaScript/Node.js projects", file=sys.stderr)
        print("  • pip install -r requirements.txt  # Python projects", file=sys.stderr)
        print("  • bundle install     # Ruby projects", file=sys.stderr)
        print("  • cargo build        # Rust projects", file=sys.stderr)
        print("", file=sys.stderr)
        print("Run the appropriate command for your project type.", file=sys.stderr)
        print("="*70 + "\n", file=sys.stderr)

        return True

    def add_label(self, entry_id: int, label: str) -> bool:
        """
        Add a label to an entry.

        Args:
            entry_id: Entry ID
            label: Label to add

        Returns:
            True if successful
        """
        entry = self.get_entry(entry_id)
        if not entry:
            return False

        # Read all entries
        timeline_path = self._get_timeline_path()
        if not timeline_path.exists():
            return False

        entries = []
        with open(timeline_path, "r") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if e.get("id") == entry_id:
                        # Add label if not already present
                        labels = e.get("labels", [])
                        if label not in labels:
                            labels.append(label)
                        e["labels"] = labels
                    entries.append(e)
                except (json.JSONDecodeError, KeyError):
                    entries.append(json.loads(line))

        # Rewrite timeline
        with open(timeline_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        return True

    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search prompts for query string.

        Args:
            query: Search query

        Returns:
            List of matching entries
        """
        return self.list_entries(limit=100, query=query)

    def doctor(self) -> List[str]:
        """
        Check installation and timeline health.

        Returns:
            List of issues found (empty if healthy)
        """
        issues = []

        # Check git repo
        if not self._is_git_repo():
            issues.append("Not in a git repository")

        # Check data directory
        if not self.data_dir.exists():
            issues.append(f"Data directory does not exist: {self.data_dir}")

        # Check timeline file (only report issue if there are checkpoint refs)
        timeline_path = self._get_timeline_path()
        has_checkpoint_refs = False

        # First check if we have any checkpoint refs
        try:
            result = self._run_git("show-ref", capture_output=True)
            if result.returncode == 0:
                has_checkpoint_refs = self.REFS_PREFIX.replace("/checkpoints", "") in result.stdout
        except Exception:
            pass

        if timeline_path.exists():
            # Check for valid JSONL
            try:
                with open(timeline_path, "r") as f:
                    for i, line in enumerate(f, 1):
                        try:
                            json.loads(line)
                        except json.JSONDecodeError:
                            issues.append(f"Invalid JSON on line {i}")
                            break
            except Exception as e:
                issues.append(f"Error reading timeline: {e}")
        elif has_checkpoint_refs:
            # Only report missing timeline if we have checkpoint refs
            issues.append("No timeline file found (but checkpoint refs exist)")

        # Check for orphaned refs (refs without timeline entries)
        try:
            result = self._run_git("show-ref", capture_output=True)
            if result.returncode == 0:
                refs = set()
                for line in result.stdout.strip().split("\n"):
                    if line and self.REFS_PREFIX in line:
                        ref = line.split()[-1]
                        refs.add(int(ref.split("/")[-1]))

                # Get entry IDs from timeline
                entry_ids = set()
                if timeline_path.exists():
                    with open(timeline_path, "r") as f:
                        for line in f:
                            try:
                                entry_ids.add(json.loads(line)["id"])
                            except (json.JSONDecodeError, KeyError):
                                pass

                # Find refs without entries
                orphaned = refs - entry_ids
                if orphaned:
                    issues.append(f"Orphaned checkpoint refs: {sorted(orphaned)}")
        except Exception:
            pass  # Skip ref check if git fails

        return issues

    def export_entry(self, entry_id: int, output_dir: Optional[str] = None) -> Path:
        """
        Export entry as a bundle.

        Args:
            entry_id: Entry ID
            output_dir: Output directory (defaults to ./export-<id>)

        Returns:
            Path to exported bundle
        """
        entry = self.get_entry(entry_id)
        if not entry:
            raise ValueError(f"Entry #{entry_id} not found")

        if output_dir is None:
            output_dir = self.root / f"export-{entry_id:05d}"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # Export prompt
        prompt_path = self._get_prompt_path(entry_id)
        if prompt_path.exists():
            import shutil
            shutil.copy(prompt_path, output_dir / "prompt.txt")

        # Export diff
        diff_path = self._get_diff_path(entry_id)
        if diff_path.exists():
            import shutil
            shutil.copy(diff_path, output_dir / "diff.patch")

        # Export metadata
        with open(output_dir / "meta.json", "w") as f:
            json.dump(entry, f, indent=2)

        return output_dir

    def print_entries(self, entries: List[Dict[str, Any]], expand: bool = False, expand_chars: int = 200) -> None:
        """
        Print entries in table format.

        Args:
            entries: List of timeline entries
            expand: If True, show longer prompt snippets
            expand_chars: Number of characters to show when expanded (default 200)
        """
        if not entries:
            print("No entries found")
            return

        # Check if we have full prompt data for truncation detection
        for entry in entries:
            entry_id = entry["id"]
            # Try to get actual prompt length to detect truncation
            try:
                prompt_path = self._get_prompt_path(entry_id)
                if prompt_path.exists():
                    with open(prompt_path, "r") as f:
                        full_prompt = f.read()
                    entry["_full_len"] = len(full_prompt)
                else:
                    entry["_full_len"] = len(entry.get("prompt_snippet", ""))
            except Exception:
                entry["_full_len"] = len(entry.get("prompt_snippet", ""))

        # Print header if we have entries
        if entries:
            print()
            # Header: ID Actor Date/Time Files Description
            print(f"{'ID':<4} {'A':<1}  {'Date/Time':<19}  {'Files':<40}  Description")
            print("-" * 100)

        for entry in entries:
            # Format: #ID Actor timestamp  files  prompt_snippet [more]
            id_str = f"#{entry['id']}"
            actor = entry.get("actor", "assistant")
            actor_char = "A" if actor == "assistant" else "U"
            ts = entry["ts"][:19].replace("T", " ")

            # Format file changes
            files_str = ""
            if entry.get("files"):
                changes = []
                for f in entry["files"][:3]:  # Max 3 files
                    path = Path(f.get("path", "unknown")).name
                    # Handle both old format (add/del) and new format (additions/deletions)
                    add = f.get('add', f.get('additions', 0))
                    del_count = f.get('del', f.get('deletions', 0))
                    changes.append(f"+{path} ({add:+d}/{del_count:-d})")
                if len(entry["files"]) > 3:
                    changes.append(f"+{len(entry['files']) - 3} more")
                files_str = " ".join(changes)

            # Format labels
            labels_str = ""
            if entry.get("labels"):
                labels_str = " [" + ", ".join(entry["labels"]) + "]"

            # Format prompt snippet
            if expand:
                # Show more characters when expanded
                max_len = expand_chars
                snippet = entry.get("prompt_snippet", "")
                # Replace newlines with spaces for single-line display
                snippet = snippet.replace("\n", " ").replace("\r", " ")
                if len(snippet) > max_len:
                    snippet = snippet[:max_len - 3] + "..."
                more_indicator = ""
            else:
                # Compact view (60 chars)
                max_len = 60
                snippet = entry.get("prompt_snippet", "")
                snippet = snippet.replace("\n", " ").replace("\r", " ")
                if len(snippet) > max_len:
                    snippet = snippet[:max_len - 3] + "..."
                # Show [more] indicator if prompt is longer than shown
                full_len = entry.get("_full_len", len(snippet))
                if full_len > max_len:
                    more_indicator = " [+]"
                else:
                    more_indicator = ""

            print(f"{id_str:<4} {actor_char}  {ts}  {files_str:<40}  \"{snippet}\"{labels_str}{more_indicator}")

    def print_entry_detail(self, entry: Dict[str, Any]) -> None:
        """Print full entry details."""
        print(f"\n{'='*60}")
        print(f"Checkpoint #{entry['id']}")
        print(f"{'='*60}")
        print(f"Timestamp: {entry['ts']}")
        print(f"Session:    {entry.get('session', 'unknown')}")

        if entry.get("labels"):
            print(f"Labels:     {', '.join(entry['labels'])}")

        print(f"\nPrompt:")
        print(f"  {entry.get('prompt', '')[:200]}")

        if entry.get("files"):
            print(f"\nFiles changed:")
            for f in entry["files"]:
                # Handle both old format (add/del) and new format (additions/deletions)
                add = f.get('add', f.get('additions', 0))
                del_count = f.get('del', f.get('deletions', 0))
                print(f"  {f.get('path', 'unknown')}: +{add}/-{del_count}")

        print(f"\nRef:        {entry.get('checkpoint_ref', 'unknown')}")
        print(f"SHA:        {entry.get('checkpoint_sha', 'unknown')}")
