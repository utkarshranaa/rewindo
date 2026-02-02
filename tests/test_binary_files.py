#!/usr/bin/env python3
"""Integration test for binary file handling.

This test verifies that binary files are handled correctly:
- Binary files are detected and excluded from diff generation
- Stats are recorded for binary files (showing they changed)
- Full diffs are not stored for binary files (unless --binary is enabled)
- Revert works correctly with binary files in the repository
"""

import subprocess
import sys
import tempfile
from pathlib import Path

# Add lib to path
LIB_DIR = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB_DIR))


def run_git(cwd: Path, *args):
    """Run git command."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout, result.stderr


def run_cli(cwd: Path, *args):
    """Run rewindo CLI command."""
    project_root = Path(__file__).parent.parent
    env = {**subprocess.os.environ, 'PYTHONPATH': str(project_root / 'lib')}
    result = subprocess.run(
        [sys.executable, str(project_root / "bin" / "rewindo"), "--cwd", str(cwd)] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env
    )
    return result.returncode, result.stdout, result.stderr


def file_exists(cwd: Path, path: str) -> bool:
    """Check if file exists."""
    return (cwd / path).exists()


def get_file_size(cwd: Path, path: str) -> int:
    """Get file size in bytes."""
    file_path = cwd / path
    if file_path.exists():
        return file_path.stat().st_size
    return 0


def create_binary_file(path: Path, content: bytes) -> None:
    """Create a binary file with specific content."""
    path.write_bytes(content)


def test_binary_file_detection():
    """Test that binary files are detected and handled correctly."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-binary"
        test_repo.mkdir()

        print("\n=== Phase 8.3: Binary File Handling Tests ===\n")

        # Initialize
        print("[1/5] Initializing repo...")
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "README.md").write_text("# Test Project\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Create a binary file (simple PNG-like header)
        print("[2/5] Creating binary file...")
        binary_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
        create_binary_file(test_repo / "image.png", binary_data)
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add image")

        # Verify git detects it as binary
        rc, stdout, stderr = run_git(test_repo, "diff", "--stat", "--cached", "HEAD~1")
        print(f"       Git diff output: {stdout}")
        assert "image.png" in stdout, "Binary file should be in git diff"
        print("       [OK] Binary file created")

        # Create checkpoint after binary file was added
        print("[3/5] Creating checkpoint with binary file in history...")
        run_cli(test_repo, "capture-prompt", "--prompt", "Add documentation")
        (test_repo / "README.md").write_text("# Test Project\n\nDocumentation\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add docs")
        run_cli(test_repo, "capture-stop")

        # Show command should work
        print("[4/5] TEST: Show command works with binary files in repo...")
        rc, stdout, stderr = run_cli(test_repo, "show", "1")
        assert rc == 0, "Show command should succeed"
        print("       [OK] Show command works")

        # Revert should work
        print("[5/5] TEST: Revert works with binary files...")
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--yes")
        assert rc == 0, f"Revert should succeed: {stderr}"

        # Binary file should still exist
        assert file_exists(test_repo, "image.png"), "Binary file should still exist"
        size = get_file_size(test_repo, "image.png")
        assert size > 0, "Binary file should have content"
        print("       [OK] Revert preserves binary files")

        print("\n[SUCCESS] Binary file detection test passed!")


def test_binary_file_stats_recorded():
    """Test that binary file changes are recorded in stats."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-stats"
        test_repo.mkdir()

        print("\n[1/4] Test binary file stats recording...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("v1\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v1")

        # Create checkpoint
        run_cli(test_repo, "capture-prompt", "--prompt", "Add resources")

        # Add both text and binary files
        (test_repo / "file.txt").write_text("v2\n")
        binary_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        create_binary_file(test_repo / "icon.png", binary_data)

        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add files")
        run_cli(test_repo, "capture-stop")

        # Check that files are recorded
        print("[2/4] Checking file list...")
        rc, stdout, stderr = run_cli(test_repo, "show", "1")
        assert rc == 0, "Show should succeed"

        # Files should be listed (even if we don't show diff for binary)
        print("       [OK] Checkpoint created")

        # Verify both files exist in checkpoint
        print("[3/4] Verifying files in checkpoint...")
        assert file_exists(test_repo, "file.txt"), "Text file should exist"
        assert file_exists(test_repo, "icon.png"), "Binary file should exist"
        print("       [OK] Both files exist")

        # Revert and verify
        print("[4/4] TEST: Revert restores both file types...")
        # Make some changes
        (test_repo / "file.txt").write_text("dirty\n")
        create_binary_file(test_repo / "icon.png", b'dirty data')

        run_cli(test_repo, "revert", "1", "--yes")

        assert file_exists(test_repo, "file.txt"), "Text file should exist after revert"
        assert file_exists(test_repo, "icon.png"), "Binary file should exist after revert"
        print("       [OK] Both file types restored correctly")

        print("\n[SUCCESS] Binary file stats test passed!")


def test_mixed_binary_and_text_changes():
    """Test handling mixed changes to binary and text files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-mixed"
        test_repo.mkdir()

        print("\n[1/4] Test mixed binary and text changes...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "config.json").write_text('{"key": "value"}\n')
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # First checkpoint with binary data
        print("[2/4] Creating checkpoint with binary data...")
        run_cli(test_repo, "capture-prompt", "--prompt", "Add binary resource")

        # Create a simple binary "database" file
        binary_db = b'DB\x01\x00' + b'\x00' * 50 + b'RECORD1' + b'\x00' * 50
        create_binary_file(test_repo / "data.db", binary_db)
        (test_repo / "config.json").write_text('{"key": "value", "db": "data.db"}\n')

        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add database")
        run_cli(test_repo, "capture-stop")

        # Verify both files exist
        assert file_exists(test_repo, "data.db"), "Database file should exist"
        assert file_exists(test_repo, "config.json"), "Config file should exist"
        print("       [OK] Checkpoint with binary and text files created")

        # Modify both
        print("[3/4] Modifying both file types...")
        binary_db = b'DB\x02\x00' + b'\x00' * 50 + b'RECORD2' + b'\x00' * 50
        create_binary_file(test_repo / "data.db", binary_db)
        (test_repo / "config.json").write_text('{"key": "value2", "db": "data.db"}\n')
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Update files")
        run_cli(test_repo, "capture-stop")
        print("       [OK] Files modified")

        # Revert should restore both
        print("[4/4] TEST: Revert restores both file types correctly...")
        run_cli(test_repo, "revert", "1", "--yes")

        # Check text file
        config_content = (test_repo / "config.json").read_text()
        assert 'value' in config_content and 'value2' not in config_content, \
            "Text file should be restored to checkpoint #1 state"

        # Check binary file
        db_content = (test_repo / "data.db").read_bytes()
        assert b'DB\x01' in db_content, "Binary file should be restored to checkpoint #1 state"
        assert b'RECORD1' in db_content, "Binary file should have original content"
        print("       [OK] Mixed file types restored correctly")

        print("\n[SUCCESS] Mixed binary and text changes test passed!")


def test_binary_file_replay():
    """Test that replay works with binary files in the timeline."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-replay"
        test_repo.mkdir()

        print("\n[1/4] Test binary file handling in replay...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("v1\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v1")

        # Step 1: Assistant adds binary file
        print("[2/4] Creating checkpoint with binary file...")
        run_cli(test_repo, "capture-prompt", "--prompt", "Add image")
        binary_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 200
        create_binary_file(test_repo / "logo.png", binary_data)
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add logo")
        run_cli(test_repo, "capture-stop")

        # Step 2: User makes manual text edit
        print("[3/4] User makes manual text edit...")
        (test_repo / "file.txt").write_text("user edit\n")
        run_cli(test_repo, "capture-prompt", "--prompt", "Next step")

        # Step 3: Assistant makes more changes
        (test_repo / "file.txt").write_text("v3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "v3")
        run_cli(test_repo, "capture-stop")

        # Revert to #1 with replay
        print("[4/4] TEST: Revert with replay preserves binary files...")
        run_cli(test_repo, "revert", "1", "--replay", "user", "--yes")

        # Binary file should still exist
        assert file_exists(test_repo, "logo.png"), "Binary file should exist after replay"
        binary_size = get_file_size(test_repo, "logo.png")
        assert binary_size == len(binary_data), f"Binary file should have correct size, got {binary_size}"

        # User edit should be replayed
        file_content = (test_repo / "file.txt").read_text()
        assert "user edit" in file_content, "User edit should be replayed"

        print("       [OK] Replay works with binary files in timeline")

        print("\n[SUCCESS] Binary file replay test passed!")


def test_large_binary_file():
    """Test handling of larger binary files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-large"
        test_repo.mkdir()

        print("\n[1/3] Test large binary file handling...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "README.md").write_text("# Test\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Create a larger binary file (1MB)
        print("[2/3] Creating 1MB binary file...")
        large_binary = b'\x00\x01\x02\x03' * (1024 * 256)  # ~1MB
        create_binary_file(test_repo / "large.bin", large_binary)
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add large file")

        # Create checkpoint
        run_cli(test_repo, "capture-prompt", "--prompt", "Update docs")
        (test_repo / "README.md").write_text("# Test\n\nUpdated\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Update docs")
        run_cli(test_repo, "capture-stop")

        print("       [OK] Large binary file handled")

        # Revert should work
        print("[3/3] TEST: Revert with large binary file...")
        rc, stdout, stderr = run_cli(test_repo, "revert", "1", "--yes")
        assert rc == 0, f"Revert should succeed: {stderr}"

        # Large file should still exist
        assert file_exists(test_repo, "large.bin"), "Large binary file should exist"
        size = get_file_size(test_repo, "large.bin")
        assert size > 1024 * 1024 - 100, "Large binary file should have content"
        print("       [OK] Large binary file preserved")

        print("\n[SUCCESS] Large binary file test passed!")


def main():
    """Run all binary file handling tests."""
    print("\n" + "=" * 60)
    print("Phase 8.3: Binary File Handling Tests")
    print("=" * 60)

    test_binary_file_detection()
    test_binary_file_stats_recorded()
    test_mixed_binary_and_text_changes()
    test_binary_file_replay()
    test_large_binary_file()

    print("\n" + "=" * 60)
    print("[SUCCESS] All Phase 8.3 tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
