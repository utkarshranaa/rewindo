"""
Working tree detection for manual edits.

Compares the current working tree against a base SHA to detect
manual changes made between prompts.
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class FileChange:
    """Represents a single file change."""
    path: str
    status: str  # 'M' = modified, 'A' = added, 'D' = deleted, '??' = untracked

    def __str__(self) -> str:
        return f"{self.status} {self.path}"


class WorkingTreeDetector:
    """
    Detect changes in working tree compared to a base SHA.

    Uses git commands to efficiently detect:
    - Modified files
    - Added files
    - Deleted files
    - Untracked files (respecting .gitignore)
    """

    def __init__(self, cwd: Optional[Path] = None):
        """
        Initialize detector.

        Args:
            cwd: Working directory (default: current directory)
        """
        self.cwd = Path(cwd) if cwd else Path.cwd()

    def _run_git(self, *args) -> subprocess.CompletedProcess:
        """Run git command in working directory."""
        return subprocess.run(
            ["git"] + list(args),
            cwd=self.cwd,
            capture_output=True,
            text=True
        )

    def is_dirty_from(self, base_sha: str) -> bool:
        """
        Check if working tree has changes compared to base SHA.

        Args:
            base_sha: Git commit SHA to compare against

        Returns:
            True if there are any changes, False otherwise
        """
        # Compare HEAD to base SHA first (if they differ, we're dirty)
        result = self._run_git("rev-parse", "HEAD")
        if result.returncode != 0:
            return True  # Can't determine, assume dirty

        current_head = result.stdout.strip()
        if current_head != base_sha:
            return True

        # Check for unstaged changes
        result = self._run_git("diff", "--quiet")
        if result.returncode != 0:
            return True  # Has unstaged changes

        # Check for staged changes
        result = self._run_git("diff", "--cached", "--quiet")
        if result.returncode != 0:
            return True  # Has staged changes

        # Check for untracked files
        result = self._run_git("ls-files", "--others", "--exclude-standard")
        if result.stdout.strip():
            return True  # Has untracked files

        return False

    def get_changed_files(self, base_sha: Optional[str] = None) -> List[FileChange]:
        """
        Get list of changed files compared to base SHA.

        Args:
            base_sha: Git commit SHA to compare against (None = compare to HEAD)

        Returns:
            List of FileChange objects
        """
        changes = []

        # Use git status --porcelain for efficient change detection
        # Format: XY path1 path2 (but we only care about the status char and path)
        result = self._run_git("status", "--porcelain", "-z")
        if result.returncode != 0:
            return []

        # -z output is null-separated, format: XY<path>\0<path2>\0...
        # For renamed files: XY<path1>\0<path2>\0
        output = result.stdout
        if not output:
            return []

        # Parse null-separated output
        parts = output.split('\0')
        i = 0
        while i < len(parts):
            part = parts[i]
            if not part:
                i += 1
                continue

            # First part is the status code(s) followed by path
            if len(part) >= 3:
                status = part[:2].strip()
                path = part[3:]

                # Handle renamed files (status starts with 'R')
                if status.startswith('R'):
                    # Renamed: format is "R123 <old>\0<new>\0"
                    # We already have the old path, next part is new path
                    if i + 1 < len(parts):
                        new_path = parts[i + 1]
                        changes.append(FileChange(path=new_path, status='R'))
                        i += 2
                        continue

                # Convert status to our format
                if status == 'M':
                    changes.append(FileChange(path=path, status='M'))
                elif status == 'A':
                    changes.append(FileChange(path=path, status='A'))
                elif status == 'D':
                    changes.append(FileChange(path=path, status='D'))
                elif status == '??':
                    changes.append(FileChange(path=path, status='??'))
                elif status:
                    # Other statuses (merged, etc.)
                    changes.append(FileChange(path=path, status=status))

            i += 1

        return changes

    def get_file_changes_summary(self, base_sha: Optional[str] = None) -> str:
        """
        Get a human-readable summary of changes.

        Args:
            base_sha: Git commit SHA (None = compare to HEAD)

        Returns:
            Summary string like "3 files changed (+15/-2)"
        """
        changes = self.get_changed_files(base_sha)

        if not changes:
            return "No changes"

        # Count by status
        modified = sum(1 for c in changes if c.status == 'M')
        added = sum(1 for c in changes if c.status in ('A', '??'))
        deleted = sum(1 for c in changes if c.status == 'D')
        renamed = sum(1 for c in changes if c.status == 'R')

        parts = []
        total = len(changes)

        if modified:
            parts.append(f"{modified} modified")
        if added:
            parts.append(f"{added} added")
        if deleted:
            parts.append(f"{deleted} deleted")
        if renamed:
            parts.append(f"{renamed} renamed")

        return f"{total} files changed: {', '.join(parts)}"

    def get_numstat(self, base_sha: str) -> List[Dict[str, Any]]:
        """
        Get line-level statistics for changes compared to base SHA.

        Args:
            base_sha: Git commit SHA to compare against

        Returns:
            List of dicts with 'path', 'additions', 'deletions'
        """
        numstat = []

        # git diff --numstat gives: additions\tdeletions\tpath
        result = self._run_git("diff", "--numstat", base_sha)
        if result.returncode != 0:
            return []

        for line in result.stdout.splitlines():
            if not line:
                continue

            parts = line.split('\t')
            if len(parts) >= 3:
                try:
                    additions = int(parts[0]) if parts[0] != '-' else 0
                    deletions = int(parts[1]) if parts[1] != '-' else 0
                    path = parts[2]

                    numstat.append({
                        "path": path,
                        "additions": additions,
                        "deletions": deletions
                    })
                except ValueError:
                    # Binary files show as '-' '-' which we handle above
                    pass

        return numstat

    def has_uncommitted_changes(self) -> bool:
        """
        Check if there are any uncommitted changes.

        Returns:
            True if there are unstaged or staged changes, or untracked files
        """
        # Check for unstaged changes
        result = self._run_git("diff", "--quiet")
        if result.returncode != 0:
            return True

        # Check for staged changes
        result = self._run_git("diff", "--cached", "--quiet")
        if result.returncode != 0:
            return True

        # Check for untracked files
        result = self._run_git("ls-files", "--others", "--exclude-standard")
        if result.stdout.strip():
            return True

        return False

    def get_current_head_sha(self) -> Optional[str]:
        """
        Get the current HEAD SHA.

        Returns:
            Current HEAD SHA or None if not in a git repo
        """
        result = self._run_git("rev-parse", "HEAD")
        if result.returncode != 0:
            return None
        return result.stdout.strip()
