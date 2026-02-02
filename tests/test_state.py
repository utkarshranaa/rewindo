#!/usr/bin/env python3
"""Unit tests for StateManager."""

import json
import tempfile
from pathlib import Path
import sys

# Add lib to path
LIB_DIR = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB_DIR))

from state import StateManager


def test_state_manager_creates_file():
    """Test that StateManager creates state file."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        manager = StateManager(data_dir)

        # Initially, state should be empty
        state = manager.load_state()
        assert state["last_step_sha"] is None
        assert state["last_step_id"] is None
        assert state["updated_at"] is None

        # State file should exist after load (even if empty)
        # Actually, it shouldn't exist until we save
        assert not manager.state_file.exists()

        print("[OK] StateManager creates empty state")


def test_state_manager_saves_and_loads():
    """Test saving and loading state."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        manager = StateManager(data_dir)

        # Save state (timestamp will be auto-added)
        result = manager.save_state({
            "last_step_sha": "abc123",
            "last_step_id": 5
        })
        assert result
        assert manager.state_file.exists()

        # Load state
        state = manager.load_state()
        assert state["last_step_sha"] == "abc123"
        assert state["last_step_id"] == 5
        assert state["updated_at"] is not None
        assert "T" in state["updated_at"]  # ISO format

        print("[OK] StateManager saves and loads state")


def test_update_last_step():
    """Test update_last_step method."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        manager = StateManager(data_dir)

        # Update last step
        result = manager.update_last_step("def456", 10)
        assert result

        # Verify
        assert manager.get_last_step_sha() == "def456"
        assert manager.get_last_step_id() == 10

        # Load and verify
        state = manager.load_state()
        assert state["last_step_sha"] == "def456"
        assert state["last_step_id"] == 10
        assert state["updated_at"] is not None  # Should have timestamp

        print("[OK] update_last_step works correctly")


def test_getters_return_none_for_empty_state():
    """Test that getters return None for empty state."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        manager = StateManager(data_dir)

        assert manager.get_last_step_sha() is None
        assert manager.get_last_step_id() is None

        print("[OK] Getters return None for empty state")


def test_clear_state():
    """Test clearing state."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        manager = StateManager(data_dir)

        # Add some state
        manager.update_last_step("abc123", 5)
        assert manager.state_file.exists()

        # Clear
        result = manager.clear()
        assert result
        assert not manager.state_file.exists()

        # Verify empty state
        assert manager.get_last_step_sha() is None
        assert manager.get_last_step_id() is None

        print("[OK] Clear works correctly")


def test_invalid_json_returns_empty_state():
    """Test that invalid JSON returns empty state (graceful degradation)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        manager = StateManager(data_dir)

        # Write invalid JSON
        manager.state_file.write_text("{invalid json")

        # Load should return empty state, not crash
        state = manager.load_state()
        assert state["last_step_sha"] is None
        assert state["last_step_id"] is None
        assert state["updated_at"] is None

        print("[OK] Invalid JSON handled gracefully")


def test_atomic_write():
    """Test that writes are atomic (uses temp file)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        manager = StateManager(data_dir)

        # Save state
        manager.update_last_step("abc123", 5)

        # Verify temp file was cleaned up
        temp_file = manager.state_file.with_suffix(".tmp")
        assert not temp_file.exists()

        # Verify main file exists and is valid
        assert manager.state_file.exists()
        with open(manager.state_file) as f:
            data = json.load(f)
            assert data["last_step_sha"] == "abc123"

        print("[OK] Atomic write works (temp file cleaned up)")


def test_timestamp_auto_added():
    """Test that timestamp is automatically added."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        manager = StateManager(data_dir)

        # Save without timestamp
        result = manager.save_state({"last_step_sha": "abc", "last_step_id": 1})
        assert result

        # Load and check timestamp was added
        state = manager.load_state()
        assert state["updated_at"] is not None
        assert "T" in state["updated_at"]  # ISO format has 'T'

        print("[OK] Timestamp automatically added")


def main():
    """Run all tests."""
    print("=" * 60)
    print("StateManager Unit Tests")
    print("=" * 60)

    test_state_manager_creates_file()
    test_state_manager_saves_and_loads()
    test_update_last_step()
    test_getters_return_none_for_empty_state()
    test_clear_state()
    test_invalid_json_returns_empty_state()
    test_atomic_write()
    test_timestamp_auto_added()

    print("=" * 60)
    print("[SUCCESS] All StateManager tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
