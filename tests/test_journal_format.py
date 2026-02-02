#!/usr/bin/env python3
"""Unit tests for journal format update (actor and parent_sha fields)."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Add lib to path
LIB_DIR = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB_DIR))

from rewindo import Rewindo


def run_git(cwd: Path, *args):
    """Run git command."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout, result.stderr


def test_normalize_entry_adds_actor_to_old_entries():
    """Test that _normalize_entry adds actor='assistant' to old entries."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        run_git(test_repo, "commit", "--allow-empty", "-m", "Initial")

        # Create Rewindo instance
        rewindo = Rewindo(str(test_repo))

        # Old format entry (no actor)
        old_entry = {
            "id": 1,
            "ts": "2026-02-01T10:00:00",
            "session": "test",
            "prompt": "Add feature",
            "checkpoint_sha": "abc123"
        }

        # Normalize
        normalized = rewindo._normalize_entry(old_entry.copy())

        assert normalized["actor"] == "assistant", "Old entries should default to assistant"
        assert "parent_sha" in normalized, "Should have parent_sha field"
        assert normalized["parent_sha"] is None, "parent_sha should be None for old entries"

        print("[OK] Old entries get actor='assistant' by default")


def test_normalize_entry_preserves_new_fields():
    """Test that _normalize_entry preserves actor and parent_sha in new entries."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        run_git(test_repo, "commit", "--allow-empty", "-m", "Initial")

        # Create Rewindo instance
        rewindo = Rewindo(str(test_repo))

        # New format entry
        new_entry = {
            "id": 1,
            "ts": "2026-02-01T10:00:00",
            "actor": "user",
            "parent_sha": "def456",
            "message": "Manual edits"
        }

        # Normalize
        normalized = rewindo._normalize_entry(new_entry.copy())

        assert normalized["actor"] == "user", "Should preserve actor='user'"
        assert normalized["parent_sha"] == "def456", "Should preserve parent_sha"

        print("[OK] New entries preserve actor and parent_sha")


def test_list_entries_includes_actor():
    """Test that list_entries includes actor in results."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        run_git(test_repo, "commit", "--allow-empty", "-m", "Initial")

        # Create Rewindo instance
        rewindo = Rewindo(str(test_repo))

        # Create a user entry
        rewindo.append_entry(
            actor="user",
            checkpoint_sha="abc123",
            files=[{"path": "test.txt", "status": "M"}],
            message="Manual edits"
        )

        # List entries
        entries = rewindo.list_entries()

        assert len(entries) == 1, "Should have 1 entry"
        assert entries[0]["actor"] == "user", "Should include actor"

        print("[OK] list_entries includes actor")


def test_list_entries_can_filter_by_actor():
    """Test that list_entries can filter by actor."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        run_git(test_repo, "commit", "--allow-empty", "-m", "Initial")

        # Create Rewindo instance
        rewindo = Rewindo(str(test_repo))

        # Create mixed entries
        rewindo.append_entry(
            actor="assistant",
            checkpoint_sha="abc111",
            files=[],
            prompt="Prompt 1"
        )
        rewindo.append_entry(
            actor="user",
            checkpoint_sha="abc222",
            files=[],
            message="Manual edit 1"
        )
        rewindo.append_entry(
            actor="assistant",
            checkpoint_sha="abc333",
            files=[],
            prompt="Prompt 2"
        )

        # Filter by actor
        user_entries = rewindo.list_entries(actor="user")
        assistant_entries = rewindo.list_entries(actor="assistant")

        assert len(user_entries) == 1, "Should have 1 user entry"
        assert len(assistant_entries) == 2, "Should have 2 assistant entries"
        assert user_entries[0]["actor"] == "user"

        print("[OK] Can filter entries by actor")


def test_get_entry_normalizes_old_entries():
    """Test that get_entry normalizes old entries."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        run_git(test_repo, "commit", "--allow-empty", "-m", "Initial")

        # Create Rewindo instance
        rewindo = Rewindo(str(test_repo))

        # Manually write an old-format entry
        timeline_path = rewindo._get_timeline_path()
        old_entry = {
            "id": 1,
            "ts": "2026-02-01T10:00:00",
            "session": "test",
            "prompt": "Add feature",
            "checkpoint_sha": "abc123"
        }
        with open(timeline_path, "a") as f:
            f.write(json.dumps(old_entry) + "\n")

        # Get entry
        entry = rewindo.get_entry(1)

        assert entry is not None, "Should find entry"
        assert entry["actor"] == "assistant", "Should normalize to assistant"
        assert "parent_sha" in entry, "Should have parent_sha field"

        print("[OK] get_entry normalizes old entries")


def test_append_entry_creates_new_format():
    """Test that append_entry creates entries with new format."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        run_git(test_repo, "commit", "--allow-empty", "-m", "Initial")

        # Create Rewindo instance
        rewindo = Rewindo(str(test_repo))

        # Append user entry
        entry_id = rewindo.append_entry(
            actor="user",
            checkpoint_sha="abc123",
            files=[{"path": "test.txt", "status": "M", "additions": 5, "deletions": 2}],
            message="Manual edits",
            parent_sha="def456",
            session="test-session"
        )

        assert entry_id == 1, "Entry ID should be 1"

        # Get the entry and verify
        entry = rewindo.get_entry(entry_id)

        assert entry["actor"] == "user"
        assert entry["checkpoint_sha"] == "abc123"
        assert entry["parent_sha"] == "def456"
        assert entry["message"] == "Manual edits"
        assert entry["session"] == "test-session"
        assert len(entry["files"]) == 1
        assert entry["files"][0]["path"] == "test.txt"

        print("[OK] append_entry creates new format entries")


def test_append_entry_for_assistant():
    """Test that append_entry works for assistant steps."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        run_git(test_repo, "commit", "--allow-empty", "-m", "Initial")

        # Create Rewindo instance
        rewindo = Rewindo(str(test_repo))

        # Append assistant entry
        entry_id = rewindo.append_entry(
            actor="assistant",
            checkpoint_sha="abc123",
            files=[],
            prompt="Add authentication feature",
            session="test-session"
        )

        # Get the entry and verify
        entry = rewindo.get_entry(entry_id)

        assert entry["actor"] == "assistant"
        assert entry["prompt"] == "Add authentication feature"
        assert "message" not in entry, "Assistant entries shouldn't have message"
        assert "prompt_ref" in entry, "Should have prompt_ref"

        print("[OK] append_entry works for assistant steps")


def test_backward_compatibility_reading_old_timeline():
    """Test that old timelines can still be read correctly."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        run_git(test_repo, "commit", "--allow-empty", "-m", "Initial")

        # Create Rewindo instance
        rewindo = Rewindo(str(test_repo))

        # Manually write old-format entries
        timeline_path = rewindo._get_timeline_path()
        for i in range(3):
            old_entry = {
                "id": i + 1,
                "ts": "2026-02-01T10:00:00",
                "session": "test",
                "prompt": f"Prompt {i+1}",
                "checkpoint_sha": f"abc{i}23",
                "files": [],
                "labels": [],
                "notes": ""
            }
            with open(timeline_path, "a") as f:
                f.write(json.dumps(old_entry) + "\n")

        # List entries - should work without errors
        entries = rewindo.list_entries()

        assert len(entries) == 3, "Should read all old entries"
        for entry in entries:
            assert entry["actor"] == "assistant", "All should default to assistant"

        print("[OK] Old timelines are readable with backward compatibility")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Journal Format Unit Tests")
    print("=" * 60)

    test_normalize_entry_adds_actor_to_old_entries()
    test_normalize_entry_preserves_new_fields()
    test_list_entries_includes_actor()
    test_list_entries_can_filter_by_actor()
    test_get_entry_normalizes_old_entries()
    test_append_entry_creates_new_format()
    test_append_entry_for_assistant()
    test_backward_compatibility_reading_old_timeline()

    print("=" * 60)
    print("[SUCCESS] All journal format tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
