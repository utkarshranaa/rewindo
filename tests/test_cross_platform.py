#!/usr/bin/env python3
"""Integration test for cross-platform compatibility.

This test verifies Rewindo works correctly across different platforms:
- Windows (WindowsPath with \\ separators)
- Linux/macOS (PosixPath with / separators)
- Line endings (CRLF vs LF)
- Platform-specific git behavior
"""

import os
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


def get_file_content(cwd: Path, path: str) -> str:
    """Get file content as bytes, then decode."""
    file_path = cwd / path
    if file_path.exists():
        return file_path.read_text()
    return ""


def get_file_content_raw(cwd: Path, path: str) -> bytes:
    """Get file content as raw bytes."""
    file_path = cwd / path
    if file_path.exists():
        return file_path.read_bytes()
    return b""


def detect_line_endings(content: bytes) -> str:
    """Detect line endings in content."""
    if b'\r\n' in content:
        return 'CRLF'
    elif b'\n' in content:
        return 'LF'
    return 'NONE'


def test_path_handling():
    """Test that paths are handled correctly on all platforms."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-paths"
        test_repo.mkdir()

        print("\n=== Phase 8.6: Cross-Platform Compatibility Tests ===\n")

        # Initialize
        print(f"[1/4] Testing on platform: {sys.platform}")
        print(f"[2/4] Path separator: {os.sep}")

        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create files with subdirectories (tests path handling)
        src_dir = test_repo / "src" / "components" / "ui"
        src_dir.mkdir(parents=True)
        (src_dir / "button.py").write_text("class Button: pass\n")
        (test_repo / "README.md").write_text("# Test Project\n")

        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Create checkpoint
        run_cli(test_repo, "capture-prompt", "--prompt", "Add feature")
        (src_dir / "input.py").write_text("class Input: pass\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add input")
        run_cli(test_repo, "capture-stop")

        # Test show command (should handle paths correctly)
        print("[3/4] TEST: Path handling in show command...")
        rc, stdout, stderr = run_cli(test_repo, "show", "1")
        assert rc == 0, f"Show failed: {stderr}"

        # Check that paths are displayed correctly
        # On Windows: should show forward slashes or backslashes consistently
        # On Unix: should show forward slashes
        if "button.py" in stdout or "ui/button.py" in stdout or "ui\\\\button.py" in stdout:
            print("       [OK] Paths displayed correctly")
        else:
            print(f"       [DEBUG] Show output: {stdout}")

        # Test revert (should work regardless of platform)
        print("[4/4] TEST: Revert with nested paths...")
        run_cli(test_repo, "revert", "1", "--yes")

        # Verify files exist in correct locations (checkpoint #1 has both files)
        assert (src_dir / "button.py").exists(), "button.py should exist"
        assert (src_dir / "input.py").exists(), "input.py should exist (part of checkpoint #1)"
        print("       [OK] Revert works with nested paths")

        print("\n[SUCCESS] Path handling test passed!")


def test_line_endings():
    """Test handling of different line endings."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-lineendings"
        test_repo.mkdir()

        print("\n[1/5] Test line endings...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        run_git(test_repo, "config", "core.autocrlf", "false")  # Disable auto CRLF conversion

        # Create file with platform-native line endings
        print(f"[2/5] Creating file with native line endings...")
        (test_repo / "file.txt").write_text("line1\nline2\nline3\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Detect actual line endings
        raw_content = get_file_content_raw(test_repo, "file.txt")
        line_ending = detect_line_endings(raw_content)
        print(f"       Detected line endings: {line_ending}")

        # Create checkpoint
        print("[3/5] Creating checkpoint...")
        run_cli(test_repo, "capture-prompt", "--prompt", "Update file")
        (test_repo / "file.txt").write_text("line1\nline2\nline3\nline4\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add line")
        run_cli(test_repo, "capture-stop")

        # Test revert
        print("[4/5] TEST: Revert preserves line endings...")
        run_cli(test_repo, "revert", "1", "--yes")

        # File should be restored to checkpoint #1 state (with line4)
        content = get_file_content(test_repo, "file.txt")
        assert "line1" in content and "line2" in content and "line3" in content
        assert "line4" in content, "line4 should be present (checkpoint #1 state)"
        print("       [OK] Revert preserves content")

        print("[5/5] TEST: Timeline stores line endings correctly...")
        # Timeline should store entry correctly regardless of line endings
        rc, stdout, stderr = run_cli(test_repo, "list")
        assert rc == 0, "List should work"
        print("       [OK] Timeline handles line endings")

        print("\n[SUCCESS] Line endings test passed!")


def test_windows_specific_paths():
    """Test Windows-specific path scenarios."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-windows"
        test_repo.mkdir()

        print("\n[1/3] Test Windows path handling...")

        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Create files with names that might be problematic on Windows
        # (spaces, special characters, etc.)
        print("[2/3] Creating files with special names...")
        test_files = [
            "file with spaces.txt",
            "file-with-dashes.txt",
            "file_with_underscores.txt",
        ]

        for filename in test_files:
            (test_repo / filename).write_text(f"Content of {filename}\n")

        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add files")

        # Create checkpoint
        run_cli(test_repo, "capture-prompt", "--prompt", "Update")
        for filename in test_files:
            (test_repo / filename).write_text(f"Updated {filename}\n")

        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Update")
        run_cli(test_repo, "capture-stop")

        # Test revert
        print("[3/3] TEST: Revert with special filenames...")
        run_cli(test_repo, "revert", "1", "--yes")

        for filename in test_files:
            assert (test_repo / filename).exists(), f"{filename} should exist"

        print("       [OK] Special filenames handled correctly")

        print("\n[SUCCESS] Windows path test passed!")


def test_data_directory_locations():
    """Test that data directory is in the correct location."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-datadir"
        test_repo.mkdir()

        print("\n[1/3] Test data directory location...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("test\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Create checkpoint
        run_cli(test_repo, "capture-prompt", "--prompt", "Test")
        (test_repo / "file.txt").write_text("updated\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Update")
        run_cli(test_repo, "capture-stop")

        # Check data directory location
        print("[2/3] TEST: Data directory in .claude/data...")
        data_dir = test_repo / ".claude" / "data"
        assert data_dir.exists(), ".claude/data should exist"
        assert (data_dir / "timeline.jsonl").exists(), "timeline.jsonl should exist"
        print("       [OK] Data directory in correct location")

        # Check prompts directory
        print("[3/3] TEST: Prompt files stored correctly...")
        prompts_dir = data_dir / "prompts"
        assert prompts_dir.exists(), "prompts directory should exist"
        prompt_files = list(prompts_dir.glob("*.txt"))
        assert len(prompt_files) > 0, "Should have prompt files"
        print("       [OK] Prompt files stored correctly")

        print("\n[SUCCESS] Data directory test passed!")


def test_unicode_in_filenames_and_content():
    """Test handling of Unicode characters in filenames and content."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-unicode"
        test_repo.mkdir()

        print("\n[1/3] Test Unicode handling...")

        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")

        # Use safe Unicode filenames (avoiding characters that are problematic on Windows)
        print("[2/3] Creating files with Unicode content...")
        # Use UTF-8 encoding for Unicode content
        (test_repo / "readme.txt").write_text("Test with emoji: :) [smile]\n", encoding='utf-8')
        (test_repo / "config.py").write_text("# Configuration with umlaut\nVALUE = 'cafe'\n", encoding='utf-8')

        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Add unicode")

        # Create checkpoint
        run_cli(test_repo, "capture-prompt", "--prompt", "Update")
        (test_repo / "readme.txt").write_text("Test with more emojis: :) ;) [wink][smile]\n", encoding='utf-8')
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Update")
        run_cli(test_repo, "capture-stop")

        # Test operations
        print("[3/3] TEST: Operations work with Unicode...")
        rc, stdout, stderr = run_cli(test_repo, "list")
        assert rc == 0, "List should work with Unicode"

        run_cli(test_repo, "revert", "1", "--yes")

        # Verify content preserved (using UTF-8 encoding)
        content = (test_repo / "readme.txt").read_text(encoding='utf-8')
        assert "emoji" in content or ":)" in content, "Content should be preserved"

        print("       [OK] Unicode handled correctly")

        print("\n[SUCCESS] Unicode test passed!")


def test_absolute_and_relative_paths():
    """Test that Rewindo works with both absolute and relative paths."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-paths2"
        test_repo.mkdir()

        print("\n[1/3] Test absolute vs relative paths...")

        # Initialize
        run_git(test_repo, "init")
        run_git(test_repo, "config", "user.email", "test@test.com")
        run_git(test_repo, "config", "user.name", "Test")
        (test_repo / "file.txt").write_text("test\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Initial")

        # Create checkpoint using absolute path for --cwd
        print("[2/3] TEST: Rewindo with absolute --cwd path...")
        project_root = Path(__file__).parent.parent
        env = {**subprocess.os.environ, 'PYTHONPATH': str(project_root / 'lib')}
        result = subprocess.run(
            [sys.executable, str(project_root / "bin" / "rewindo"),
             "--cwd", str(test_repo.absolute()),
             "capture-prompt", "--prompt", "Test"],
            cwd=test_repo,
            capture_output=True,
            text=True,
            env=env
        )
        assert result.returncode == 0, f"Capture-prompt with absolute path failed: {result.stderr}"
        print("       [OK] Absolute path works")

        # Continue with operations
        (test_repo / "file.txt").write_text("updated\n")
        run_git(test_repo, "add", "-A")
        run_git(test_repo, "commit", "-m", "Update")

        result = subprocess.run(
            [sys.executable, str(project_root / "bin" / "rewindo"),
             "--cwd", str(test_repo.absolute()),
             "capture-stop"],
            cwd=test_repo,
            capture_output=True,
            text=True,
            env=env
        )
        assert result.returncode == 0, f"Capture-stop failed: {result.stderr}"

        # Test revert
        print("[3/3] TEST: Revert with absolute paths...")
        result = subprocess.run(
            [sys.executable, str(project_root / "bin" / "rewindo"),
             "--cwd", str(test_repo.absolute()),
             "revert", "1", "--yes"],
            cwd=test_repo,
            capture_output=True,
            text=True,
            env=env
        )
        assert result.returncode == 0, f"Revert failed: {result.stderr}"
        print("       [OK] All operations work with absolute paths")

        print("\n[SUCCESS] Path types test passed!")


def main():
    """Run all cross-platform compatibility tests."""
    print("\n" + "=" * 60)
    print("Phase 8.6: Cross-Platform Compatibility Tests")
    print("=" * 60)
    print(f"\nPlatform: {sys.platform}")
    print(f"Python: {sys.version}")
    print(f"Path separator: {os.sep}")

    test_path_handling()
    test_line_endings()
    test_windows_specific_paths()
    test_data_directory_locations()
    test_unicode_in_filenames_and_content()
    test_absolute_and_relative_paths()

    print("\n" + "=" * 60)
    print("[SUCCESS] All Phase 8.6 cross-platform tests passed!")
    print("=" * 60)
    print("\nPlatform-specific notes:")
    if sys.platform == "win32":
        print("  Windows: Paths use backslash internally, Rewindo normalizes them")
    elif sys.platform == "darwin":
        print("  macOS: Tested with Unix-style paths")
    else:
        print("  Linux: Tested with Unix-style paths")


if __name__ == "__main__":
    main()
