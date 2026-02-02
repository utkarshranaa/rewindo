#!/usr/bin/env python3
"""Unit tests for SnapshotCreator."""

import subprocess
import sys
import tempfile
from pathlib import Path

# Add lib to path
LIB_DIR = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB_DIR))

from snapshot import SnapshotCreator
from detector import FileChange


def run_git(cwd: Path, *args):
    """Run git command."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout, result.stderr


def test_create_snapshot_with_changes():
    """Test creating a snapshot with file changes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file1.txt").write_text("hello\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")
        _, parent_sha, _ = run_git(test_repo, "rev-parse", "HEAD")
        parent_sha = parent_sha.strip()

        # Make changes
        (test_repo / "file1.txt").write_text("hello world\n")
        (test_repo / "file2.txt").write_text("new\n")

        # Create snapshot
        creator = SnapshotCreator(test_repo)
        result = creator.create_snapshot(
            parent_sha=parent_sha,
            message="Test snapshot",
            actor="user"
        )

        assert result is not None, "Snapshot should be created"
        assert result.sha is not None, "Snapshot should have a SHA"
        assert len(result.sha) == 40, "SHA should be 40 characters"
        assert len(result.files) == 2, f"Expected 2 files, got {len(result.files)}"
        assert result.message == "Test snapshot"

        # Verify the commit exists
        _, cat_output, _ = run_git(test_repo, "cat-file", "-t", result.sha)
        assert "commit" in cat_output, "Snapshot should be a valid commit"

        print(f"[OK] Created snapshot {result.sha[:8]} with {len(result.files)} files")


def test_create_snapshot_no_changes():
    """Test creating a snapshot with no changes returns None."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file1.txt").write_text("hello\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")
        _, parent_sha, _ = run_git(test_repo, "rev-parse", "HEAD")
        parent_sha = parent_sha.strip()

        # No changes made

        # Create snapshot should return None
        creator = SnapshotCreator(test_repo)
        result = creator.create_snapshot(
            parent_sha=parent_sha,
            message="Test snapshot",
            actor="user"
        )

        assert result is None, "Snapshot should be None when no changes"

        print("[OK] Snapshot returns None when no changes")


def test_store_and_get_ref():
    """Test storing and retrieving step refs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file.txt").write_text("hello\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")
        _, sha, _ = run_git(test_repo, "rev-parse", "HEAD")
        sha = sha.strip()

        # Store ref
        creator = SnapshotCreator(test_repo)
        result = creator.store_ref(1, sha)
        assert result, "store_ref should succeed"

        # Get ref
        retrieved_sha = creator.get_ref_sha(1)
        assert retrieved_sha == sha, f"Expected {sha}, got {retrieved_sha}"

        print("[OK] Store and get ref works")


def test_list_step_refs():
    """Test listing step refs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create commits
        shas = []
        for i in range(3):
            (test_repo / f"file{i}.txt").write_text(f"content {i}\n")
            run_git(test_repo, "add", "-A")
            run_git(test_repo, "commit", "-m", f"Commit {i}")
            _, sha, _ = run_git(test_repo, "rev-parse", "HEAD")
            shas.append(sha.strip())

        # Store refs
        creator = SnapshotCreator(test_repo)
        for i, sha in enumerate(shas):
            creator.store_ref(i + 1, sha)

        # List refs
        refs = creator.list_step_refs()
        assert len(refs) == 3, f"Expected 3 refs, got {len(refs)}"
        assert refs[0]["id"] == 1
        assert refs[1]["id"] == 2
        assert refs[2]["id"] == 3

        print("[OK] List step refs works")


def test_delete_ref():
    """Test deleting a step ref."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file.txt").write_text("hello\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")
        _, sha, _ = run_git(test_repo, "rev-parse", "HEAD")
        sha = sha.strip()

        # Store ref
        creator = SnapshotCreator(test_repo)
        creator.store_ref(1, sha)

        # Verify it exists
        assert creator.get_ref_sha(1) == sha

        # Delete ref
        result = creator.delete_ref(1)
        assert result, "delete_ref should succeed"

        # Verify it's gone
        assert creator.get_ref_sha(1) is None, "Ref should be deleted"

        print("[OK] Delete ref works")


def test_snapshot_with_deleted_files():
    """Test creating a snapshot that includes deleted files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit with two files
        (test_repo / "file1.txt").write_text("hello\n")
        (test_repo / "file2.txt").write_text("world\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")
        _, parent_sha, _ = run_git(test_repo, "rev-parse", "HEAD")
        parent_sha = parent_sha.strip()

        # Delete file2
        (test_repo / "file2.txt").unlink()

        # Create snapshot
        creator = SnapshotCreator(test_repo)
        result = creator.create_snapshot(
            parent_sha=parent_sha,
            message="Deleted file2",
            actor="user"
        )

        assert result is not None, "Snapshot should be created"

        # Verify the commit reflects the deletion
        _, ls_output, _ = run_git(test_repo, "ls-tree", "-r", "--name-only", result.sha)
        files = ls_output.strip().split('\n')

        assert "file1.txt" in files, "file1 should exist in snapshot"
        assert "file2.txt" not in files, "file2 should be deleted in snapshot"

        print("[OK] Snapshot correctly handles deleted files")


def test_snapshot_with_untracked_files():
    """Test creating a snapshot that includes untracked files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file1.txt").write_text("hello\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")
        _, parent_sha, _ = run_git(test_repo, "rev-parse", "HEAD")
        parent_sha = parent_sha.strip()

        # Add untracked file
        (test_repo / "file2.txt").write_text("new\n")

        # Create snapshot
        creator = SnapshotCreator(test_repo)
        result = creator.create_snapshot(
            parent_sha=parent_sha,
            message="Added file2",
            actor="user"
        )

        assert result is not None, "Snapshot should be created"

        # Verify the commit includes the untracked file
        _, ls_output, _ = run_git(test_repo, "ls-tree", "-r", "--name-only", result.sha)
        files = ls_output.strip().split('\n')

        assert "file1.txt" in files, "file1 should exist in snapshot"
        assert "file2.txt" in files, "file2 (untracked) should be in snapshot"

        print("[OK] Snapshot correctly includes untracked files")


def test_snapshot_preserves_user_index():
    """Test that snapshot creation doesn't affect user's staged index."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file1.txt").write_text("hello\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")
        _, parent_sha, _ = run_git(test_repo, "rev-parse", "HEAD")
        parent_sha = parent_sha.strip()

        # Stage a file (user's index)
        (test_repo / "staged.txt").write_text("staged\n")
        run_git(test_repo, "add", "staged.txt")

        # Verify file is staged
        _, status, _ = run_git(test_repo, "diff", "--cached", "--name-only")
        assert "staged.txt" in status, "File should be staged"

        # Create snapshot with different changes
        (test_repo / "unstaged.txt").write_text("unstaged\n")
        creator = SnapshotCreator(test_repo)
        result = creator.create_snapshot(
            parent_sha=parent_sha,
            message="Snapshot",
            actor="user"
        )

        assert result is not None, "Snapshot should be created"

        # Verify user's staged file is still staged
        _, status, _ = run_git(test_repo, "diff", "--cached", "--name-only")
        assert "staged.txt" in status, "File should still be staged after snapshot"

        print("[OK] Snapshot preserves user's index")


def test_numstat_in_snapshot_result():
    """Test that numstat is included in snapshot result."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create initial commit
        (test_repo / "file.txt").write_text("hello\nworld\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")
        _, parent_sha, _ = run_git(test_repo, "rev-parse", "HEAD")
        parent_sha = parent_sha.strip()

        # Modify file (1 deletion, 1 addition)
        (test_repo / "file.txt").write_text("hello\nfoo\n")

        # Create snapshot
        creator = SnapshotCreator(test_repo)
        result = creator.create_snapshot(
            parent_sha=parent_sha,
            message="Modified file",
            actor="user"
        )

        assert result is not None, "Snapshot should be created"
        assert len(result.files) == 1, "Should have 1 file"

        file_info = result.files[0]
        assert file_info["path"] == "file.txt"
        assert file_info["status"] == "M"
        assert "additions" in file_info, "Should have additions"
        assert "deletions" in file_info, "Should have deletions"

        print(f"[OK] Numstat included: +{file_info['additions']}/-{file_info['deletions']}")


def main():
    """Run all tests."""
    print("=" * 60)
    print("SnapshotCreator Unit Tests")
    print("=" * 60)

    test_create_snapshot_with_changes()
    test_create_snapshot_no_changes()
    test_store_and_get_ref()
    test_list_step_refs()
    test_delete_ref()
    test_snapshot_with_deleted_files()
    test_snapshot_with_untracked_files()
    test_snapshot_preserves_user_index()
    test_numstat_in_snapshot_result()

    print("=" * 60)
    print("[SUCCESS] All SnapshotCreator tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
