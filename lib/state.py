"""
State file management for Rewindo.

Handles atomic reads/writes of the state file with locking to prevent
race conditions when hooks run concurrently.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Platform-specific locking
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl
    import errno


class StateManager:
    """
    Manage Rewindo state file with atomic writes and locking.

    State file format (.claude/data/state.json):
    {
        "last_step_sha": "<git-commit-sha>",
        "last_step_id": <int>,
        "updated_at": "<iso-timestamp>"
    }
    """

    def __init__(self, data_dir: Path):
        """
        Initialize state manager.

        Args:
            data_dir: Path to .claude/data directory
        """
        self.data_dir = Path(data_dir)
        self.state_file = self.data_dir / "state.json"
        self.lock_file = self.data_dir / "state.lock"

        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> Dict[str, Any]:
        """
        Load state from file.

        Returns:
            State dictionary with keys:
            - last_step_sha: str | None
            - last_step_id: int | None
            - updated_at: str | None

            If file doesn't exist or is invalid, returns empty state.
        """
        if not self.state_file.exists():
            return {
                "last_step_sha": None,
                "last_step_id": None,
                "updated_at": None
            }

        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
                return {
                    "last_step_sha": state.get("last_step_sha"),
                    "last_step_id": state.get("last_step_id"),
                    "updated_at": state.get("updated_at")
                }
        except (json.JSONDecodeError, IOError):
            # Invalid file, return empty state
            return {
                "last_step_sha": None,
                "last_step_id": None,
                "updated_at": None
            }

    def save_state(self, state: Dict[str, Any]) -> bool:
        """
        Save state to file atomically with locking.

        Args:
            state: State dictionary to save

        Returns:
            True if successful, False otherwise
        """
        # Add timestamp
        state["updated_at"] = datetime.now().isoformat()

        # Write to temporary file first (atomic write)
        temp_file = self.state_file.with_suffix(".tmp")

        try:
            with open(temp_file, "w") as f:
                json.dump(state, f, indent=2)

            # Atomic rename
            temp_file.replace(self.state_file)
            return True

        except (IOError, OSError) as e:
            # Clean up temp file on error
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except IOError:
                    pass
            return False

    def update_last_step(self, sha: str, step_id: int) -> bool:
        """
        Update last step SHA and ID.

        Args:
            sha: Git commit SHA of the step
            step_id: Step ID

        Returns:
            True if successful, False otherwise
        """
        state = self.load_state()
        state["last_step_sha"] = sha
        state["last_step_id"] = step_id
        return self.save_state(state)

    def get_last_step_sha(self) -> Optional[str]:
        """Get the last step SHA."""
        state = self.load_state()
        return state.get("last_step_sha")

    def get_last_step_id(self) -> Optional[int]:
        """Get the last step ID."""
        state = self.load_state()
        step_id = state.get("last_step_id")
        return int(step_id) if step_id is not None else None

    def clear(self) -> bool:
        """
        Clear state (remove state file).

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.state_file.exists():
                self.state_file.unlink()
            return True
        except (IOError, OSError):
            return False

    def _acquire_lock(self, timeout: float = 5.0) -> bool:
        """
        Acquire exclusive lock on state file.

        Args:
            timeout: Seconds to wait for lock (not fully supported on Windows)

        Returns:
            True if lock acquired, False otherwise
        """
        try:
            lock_fd = os.open(self.lock_file, os.O_CREAT | os.O_WRONLY)

            if sys.platform == "win32":
                # Windows: use msvcrt.locking
                try:
                    msvcrt.locking(lock_fd, msvcrt.LK_NBLCK, 1)
                except (IOError, OSError):
                    os.close(lock_fd)
                    return False
            else:
                # Unix: use fcntl
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (IOError, OSError) as e:
                    if e.errno == errno.EWOULDBLOCK:
                        os.close(lock_fd)
                        return False
                    raise

            # Store lock fd for later release
            self._lock_fd = lock_fd
            return True

        except (IOError, OSError):
            return False

    def _release_lock(self) -> bool:
        """
        Release lock.

        Returns:
            True if successful, False otherwise
        """
        try:
            if hasattr(self, "_lock_fd"):
                lock_fd = self._lock_fd

                if sys.platform == "win32":
                    msvcrt.locking(lock_fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)

                os.close(lock_fd)
                delattr(self, "_lock_fd")

            # Clean up lock file
            if self.lock_file.exists():
                self.lock_file.unlink()

            return True
        except (IOError, OSError):
            return False
