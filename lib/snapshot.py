"""
Snapshot creation for manual edits and assistant steps.

Creates git commit snapshots using a temporary index to avoid
clobbering the user's staged changes.
"""

import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from detector import WorkingTreeDetector, FileChange


@dataclass
class SnapshotResult:
    """Result of creating a snapshot."""
    sha: str
    ref: str
    files: List[Dict[str, Any]]  # List of {path, status, additions?, deletions?}
    message: str

    def __str__(self) -> str:
        return f"Snapshot {self.sha[:8]} ({len(self.files)} files)"


class SnapshotCreator:
    """
    Create git commit snapshots using a temporary index.

    This allows capturing the working tree state without affecting
    the user's staged changes or index.
    """

    def __init__(self, cwd: Optional[Path] = None, data_dir: Optional[Path] = None):
        """
        Initialize snapshot creator.

        Args:
            cwd: Working directory (default: current directory)
            data_dir: Data directory for temp files (default: .claude/tmp)
        """
        self.cwd = Path(cwd) if cwd else Path.cwd()
        self.data_dir = Path(data_dir) if data_dir else (self.cwd / ".claude" / "tmp")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Track temp index file for cleanup
        self._temp_index: Optional[Path] = None

    def _run_git(self, *args, env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
        """Run git command in working directory."""
        return subprocess.run(
            ["git"] + list(args),
            cwd=self.cwd,
            capture_output=True,
            text=True,
            env=env or os.environ.copy()
        )

    def _create_temp_index(self) -> Path:
        """
        Create a temporary index file.

        Returns:
            Path to the temporary index file
        """
        # Use a named temp file for the index
        fd, path = tempfile.mkstemp(suffix=".index", dir=self.data_dir)
        os.close(fd)
        self._temp_index = Path(path)
        return self._temp_index

    def _cleanup_temp_index(self):
        """Clean up temporary index file."""
        if self._temp_index and self._temp_index.exists():
            try:
                self._temp_index.unlink()
            except (IOError, OSError):
                pass
            self._temp_index = None

    def _stage_files_to_temp_index(self, changes: List[FileChange]) -> bool:
        """
        Stage changed files to the temporary index.

        Args:
            changes: List of FileChange objects

        Returns:
            True if successful, False otherwise
        """
        temp_index = self._create_temp_index()

        # Set GIT_INDEX_FILE to use our temp index
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(temp_index)

        # Initialize the index from HEAD (if exists)
        result = self._run_git("read-tree", "HEAD", env=env)
        if result.returncode != 0:
            # HEAD might not exist (empty repo), that's ok
            pass

        # Stage each changed file
        for change in changes:
            if change.status in ('M', 'A'):
                # Modified or Added: add to index
                result = self._run_git("add", change.path, env=env)
                if result.returncode != 0:
                    return False
            elif change.status == 'D':
                # Deleted: remove from index
                result = self._run_git("rm", change.path, env=env)
                if result.returncode != 0:
                    # File might not be in index, that's ok
                    pass
            elif change.status == '??':
                # Untracked: add to index
                result = self._run_git("add", change.path, env=env)
                if result.returncode != 0:
                    return False
            elif change.status == 'R':
                # Renamed: add new path
                result = self._run_git("add", change.path, env=env)
                if result.returncode != 0:
                    return False

        return True

    def _get_numstat_from_changes(self, changes: List[FileChange]) -> List[Dict[str, Any]]:
        """
        Get numstat for a list of file changes.

        Args:
            changes: List of FileChange objects

        Returns:
            List of dicts with path, status, and optionally additions/deletions
        """
        files_info = []

        for change in changes:
            info = {
                "path": change.path,
                "status": change.status
            }

            # For modified and added files, try to get line stats
            if change.status in ('M', 'A'):
                # Use git diff --numstat on the specific file
                result = self._run_git("diff", "--numstat", "--", change.path)
                if result.returncode == 0 and result.stdout.strip():
                    parts = result.stdout.split('\t')
                    if len(parts) >= 2:
                        try:
                            info["additions"] = int(parts[0]) if parts[0] != '-' else 0
                            info["deletions"] = int(parts[1]) if parts[1] != '-' else 0
                        except ValueError:
                            # Binary files
                            pass

            files_info.append(info)

        return files_info

    def create_snapshot(
        self,
        parent_sha: Optional[str],
        message: str,
        actor: str = "user",
        changed_files: Optional[List[FileChange]] = None
    ) -> Optional[SnapshotResult]:
        """
        Create a snapshot commit of the current working tree.

        Args:
            parent_sha: Parent commit SHA (None for initial commit)
            message: Commit message
            actor: "user" or "assistant"
            changed_files: Optional list of specific files to include
                          (if None, auto-detects all changes)

        Returns:
            SnapshotResult if successful, None otherwise
        """
        try:
            # Get changed files if not provided
            if changed_files is None:
                detector = WorkingTreeDetector(self.cwd)
                changes = detector.get_changed_files()
            else:
                changes = changed_files

            if not changes:
                # No changes to snapshot
                return None

            # Stage files to temporary index
            if not self._stage_files_to_temp_index(changes):
                self._cleanup_temp_index()
                return None

            temp_index = self._temp_index
            env = os.environ.copy()
            env["GIT_INDEX_FILE"] = str(temp_index)

            # Write the tree from our temp index
            result = self._run_git("write-tree", env=env)
            if result.returncode != 0:
                self._cleanup_temp_index()
                return None

            tree_sha = result.stdout.strip()

            # Create the commit
            if parent_sha:
                result = self._run_git(
                    "commit-tree", tree_sha,
                    "-p", parent_sha,
                    "-m", message,
                    env=env
                )
            else:
                result = self._run_git(
                    "commit-tree", tree_sha,
                    "-m", message,
                    env=env
                )

            if result.returncode != 0:
                self._cleanup_temp_index()
                return None

            commit_sha = result.stdout.strip()

            # Get file info
            files_info = self._get_numstat_from_changes(changes)

            # Clean up temp index
            self._cleanup_temp_index()

            return SnapshotResult(
                sha=commit_sha,
                ref=f"refs/rewindo/steps/{commit_sha[:8]}",
                files=files_info,
                message=message
            )

        except Exception as e:
            self._cleanup_temp_index()
            return None

    def store_ref(self, step_id: int, sha: str) -> bool:
        """
        Store a step reference under refs/rewindo/steps/.

        Args:
            step_id: Step ID number
            sha: Commit SHA to reference

        Returns:
            True if successful, False otherwise
        """
        ref_path = f"refs/rewindo/steps/{step_id}"
        result = self._run_git("update-ref", ref_path, sha)
        return result.returncode == 0

    def get_ref_sha(self, step_id: int) -> Optional[str]:
        """
        Get the SHA for a step reference.

        Args:
            step_id: Step ID number

        Returns:
            Commit SHA or None if not found
        """
        ref_path = f"refs/rewindo/steps/{step_id}"
        result = self._run_git("rev-parse", ref_path)
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def delete_ref(self, step_id: int) -> bool:
        """
        Delete a step reference.

        Args:
            step_id: Step ID number

        Returns:
            True if successful, False otherwise
        """
        ref_path = f"refs/rewindo/steps/{step_id}"
        result = self._run_git("update-ref", "-d", ref_path)
        return result.returncode == 0

    def list_step_refs(self) -> List[Dict[str, Any]]:
        """
        List all step references.

        Returns:
            List of dicts with 'id' and 'sha' keys
        """
        result = self._run_git("for-each-ref",
                              "refs/rewindo/steps/",
                              "--format=%(refname)%00%(objectname)")

        if result.returncode != 0:
            return []

        refs = []
        for line in result.stdout.splitlines():
            if not line:
                continue

            parts = line.split('\0')
            if len(parts) >= 2:
                ref_path = parts[0]
                sha = parts[1]

                # Extract step ID from ref path
                try:
                    step_id = int(ref_path.split('/')[-1])
                    refs.append({"id": step_id, "sha": sha})
                except (ValueError, IndexError):
                    pass

        return sorted(refs, key=lambda x: x["id"])

    def __del__(self):
        """Clean up temp index on deletion."""
        self._cleanup_temp_index()
