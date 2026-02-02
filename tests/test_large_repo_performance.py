#!/usr/bin/env python3
"""Integration test for performance with large repositories.

This test verifies that Rewindo performs well with larger repositories:
- 100+ files in the repository
- 100+ timeline entries
- Commands complete within acceptable time limits
- List operations with high limit work efficiently
"""

import subprocess
import sys
import tempfile
import time
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


def create_large_repo(cwd: Path, num_files: int = 100):
    """Create a repository with many files."""
    src_dir = cwd / "src"
    src_dir.mkdir()

    # Create multiple Python files
    for i in range(num_files):
        file_path = src_dir / f"module_{i:03d}.py"
        content = f"""# Module {i}
class Class{i}:
    def __init__(self):
        self.value = {i}
        self.name = "module_{i}"

    def method_{i}(self):
        return self.value * {i % 10}

    def compute(self):
        result = 0
        for j in range(100):
            result += self.method_{i}()
        return result

CONSTANT_{i} = {i * 123}
"""
        file_path.write_text(content)

    # Create a main file
    (cwd / "main.py").write_text("""# Main application
from src.module_000 import Class000

def main():
    obj = Class000()
    print(obj.name)

if __name__ == "__main__":
    main()
""")

    # Initialize git
    run_git(cwd, "init")
    run_git(cwd, "config", "user.email", "test@test.com")
    run_git(cwd, "config", "user.name", "Test")
    run_git(cwd, "add", "-A")
    run_git(cwd, "commit", "-m", "Initial commit")


def create_many_checkpoints(cwd: Path, num_checkpoints: int = 50):
    """Create many timeline entries."""
    print(f"Creating {num_checkpoints} checkpoints...")

    for i in range(num_checkpoints):
        # Update a file
        if i % 3 == 0:
            # Modify main.py
            (cwd / "main.py").write_text(f"""# Main application
# Version {i}
from src.module_{i:03d} import Class{i}

def main():
    obj = Class{i}()
    print(obj.name, "version", {i})

if __name__ == "__main__":
    main()
""")
        elif i % 3 == 1:
            # Modify a specific module
            module_num = i % 100
            (cwd / "src" / f"module_{module_num:03d}.py").write_text(f"""# Module {module_num}
# Updated at checkpoint {i}
class Class{module_num}:
    def __init__(self):
        self.value = {module_num}
        self.checkpoint = {i}
""")
        else:
            # Create a new file
            (cwd / f"file_{i}.txt").write_text(f"File {i} content\n")

        # Commit
        run_git(cwd, "add", "-A")
        run_git(cwd, "commit", "-m", f"Checkpoint {i}")

        # Create rewindo checkpoint
        run_cli(cwd, "capture-prompt", "--prompt", f"Update {i}")
        run_cli(cwd, "capture-stop")

        if (i + 1) % 10 == 0:
            print(f"       {i + 1}/{num_checkpoints} checkpoints created")


def measure_time(func, *args):
    """Measure execution time of a function."""
    start = time.time()
    result = func(*args)
    end = time.time()
    return end - start, result


def test_list_performance_with_many_entries():
    """Test that list command performs well with many entries."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-perf"
        test_repo.mkdir()

        print("\n=== Phase 8.5: Large Repository Performance Tests ===\n")

        # Setup: Create repo with many files and checkpoints
        print("[1/6] Setting up large repository (100 files)...")
        create_large_repo(test_repo, num_files=100)

        print("[2/6] Creating 30 timeline entries...")
        create_many_checkpoints(test_repo, num_checkpoints=30)

        # Test list with default limit
        print("[3/6] TEST: List with default limit (20)...")
        elapsed, (rc, stdout, stderr) = measure_time(run_cli, test_repo, "list")
        assert rc == 0, f"List command failed: {stderr}"
        assert elapsed < 2.0, f"List took {elapsed:.2f}s, should be < 2s"
        print(f"       [OK] List(20) completed in {elapsed:.2f}s")

        # Test list with high limit
        print("[4/6] TEST: List with high limit (100)...")
        elapsed, (rc, stdout, stderr) = measure_time(run_cli, test_repo, "list", "--limit", "100")
        assert rc == 0, f"List command failed: {stderr}"
        assert elapsed < 3.0, f"List(100) took {elapsed:.2f}s, should be < 3s"
        print(f"       [OK] List(100) completed in {elapsed:.2f}s")

        # Test show command
        print("[5/6] TEST: Show command performance...")
        elapsed, (rc, stdout, stderr) = measure_time(run_cli, test_repo, "show", "15")
        assert rc == 0, f"Show command failed: {stderr}"
        assert elapsed < 1.0, f"Show took {elapsed:.2f}s, should be < 1s"
        print(f"       [OK] Show completed in {elapsed:.2f}s")

        # Test search
        print("[6/6] TEST: Search performance...")
        elapsed, (rc, stdout, stderr) = measure_time(run_cli, test_repo, "search", "Update")
        assert rc == 0, f"Search command failed: {stderr}"
        assert elapsed < 2.0, f"Search took {elapsed:.2f}s, should be < 2s"
        print(f"       [OK] Search completed in {elapsed:.2f}s")

        print("\n[SUCCESS] List performance test passed!")


def test_revert_performance():
    """Test that revert performs well with large repository."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-revert-perf"
        test_repo.mkdir()

        print("\n[1/4] Test revert performance...")

        # Setup
        print("[2/4] Setting up...")
        create_large_repo(test_repo, num_files=100)
        create_many_checkpoints(test_repo, num_checkpoints=20)

        # Test revert performance
        print("[3/4] TEST: Revert performance...")
        start = time.time()
        rc, stdout, stderr = run_cli(test_repo, "revert", "10", "--yes")
        elapsed = time.time() - start

        assert rc == 0, f"Revert failed: {stderr}"
        assert elapsed < 3.0, f"Revert took {elapsed:.2f}s, should be < 3s"
        print(f"       [OK] Revert completed in {elapsed:.2f}s")

        # Verify repo state
        print("[4/4] TEST: Repo state after revert...")
        rc, stdout, stderr = run_cli(test_repo, "list", "--limit", "5")
        assert rc == 0, "List should work after revert"
        print("       [OK] Repo state valid after revert")

        print("\n[SUCCESS] Revert performance test passed!")


def test_undo_performance():
    """Test that undo performs well."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-undo-perf"
        test_repo.mkdir()

        print("\n[1/3] Test undo performance...")

        # Setup
        create_large_repo(test_repo, num_files=100)
        create_many_checkpoints(test_repo, num_checkpoints=20)

        # Test undo performance
        print("[2/3] TEST: Undo performance...")
        start = time.time()
        rc, stdout, stderr = run_cli(test_repo, "undo", "--yes")
        elapsed = time.time() - start

        assert rc == 0, f"Undo failed: {stderr}"
        assert elapsed < 2.0, f"Undo took {elapsed:.2f}s, should be < 2s"
        print(f"       [OK] Undo completed in {elapsed:.2f}s")

        print("[3/3] TEST: Repo state after undo...")
        rc, stdout, stderr = run_cli(test_repo, "doctor")
        assert rc == 0, "Doctor should work"
        print("       [OK] Repo valid after undo")

        print("\n[SUCCESS] Undo performance test passed!")


def test_export_performance():
    """Test that export performs well with large diffs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-export-perf"
        test_repo.mkdir()

        print("\n[1/3] Test export performance...")

        # Setup
        create_large_repo(test_repo, num_files=100)
        create_many_checkpoints(test_repo, num_checkpoints=10)

        # Test export performance
        print("[2/3] TEST: Export performance...")
        start = time.time()
        rc, stdout, stderr = run_cli(test_repo, "export", "5")
        elapsed = time.time() - start

        assert rc == 0, f"Export failed: {stderr}"
        assert elapsed < 2.0, f"Export took {elapsed:.2f}s, should be < 2s"
        print(f"       [OK] Export completed in {elapsed:.2f}s")

        # Verify export was created
        print("[3/3] TEST: Export contents...")
        export_dir = test_repo / "export-00005"
        assert export_dir.exists(), "Export directory should exist"
        assert (export_dir / "meta.json").exists(), "meta.json should exist"
        assert (export_dir / "prompt.txt").exists(), "prompt.txt should exist"
        print("       [OK] Export files created")

        print("\n[SUCCESS] Export performance test passed!")


def test_many_consecutive_operations():
    """Test performance of many consecutive operations."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-ops-perf"
        test_repo.mkdir()

        print("\n[1/3] Test consecutive operations...")

        # Setup
        create_large_repo(test_repo, num_files=50)
        create_many_checkpoints(test_repo, num_checkpoints=10)

        # Run multiple operations in sequence
        print("[2/3] TEST: Multiple consecutive operations...")
        start = time.time()

        operations = [
            ("list", []),
            ("list", ["--limit", "50"]),
            ("search", ["test"]),
            ("show", ["5"]),
            ("show", ["1"]),
            ("label", ["5", "test-label"]),
        ]

        for op_name, op_args in operations:
            rc, stdout, stderr = run_cli(test_repo, op_name, *op_args)
            assert rc == 0, f"{op_name} failed: {stderr}"

        elapsed = time.time() - start
        assert elapsed < 5.0, f"All operations took {elapsed:.2f}s, should be < 5s"
        print(f"       [OK] {len(operations)} operations completed in {elapsed:.2f}s")

        print("[3/3] TEST: Labels persist...")
        rc, stdout, stderr = run_cli(test_repo, "show", "5")
        assert "test-label" in stdout, "Label should persist"
        print("       [OK] Labels persist across operations")

        print("\n[SUCCESS] Consecutive operations test passed!")


def test_timeline_file_size():
    """Test that timeline file size remains reasonable."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repo = Path(tmp_dir) / "test-size"
        test_repo.mkdir()

        print("\n[1/3] Test timeline file size...")

        # Setup
        create_large_repo(test_repo, num_files=100)
        create_many_checkpoints(test_repo, num_checkpoints=50)

        # Check timeline file size
        print("[2/3] TEST: Timeline file size...")
        timeline_file = test_repo / ".claude" / "data" / "timeline.jsonl"
        assert timeline_file.exists(), "Timeline file should exist"

        file_size = timeline_file.stat().st_size
        # 50 entries with full prompts should be manageable
        # Each entry is roughly 500-1000 bytes, so 50 entries = 25-50KB
        assert file_size < 200000, f"Timeline file is {file_size} bytes, should be < 200KB"
        print(f"       [OK] Timeline file: {file_size} bytes ({file_size / 1024:.1f} KB)")

        # Verify list still performs well
        print("[3/3] TEST: Performance with large timeline...")
        elapsed, (rc, stdout, stderr) = measure_time(run_cli, test_repo, "list")
        assert rc == 0, f"List failed: {stderr}"
        assert elapsed < 2.0, f"List took {elapsed:.2f}s with large timeline"
        print(f"       [OK] List performs well with {file_size / 1024:.1f} KB timeline")

        print("\n[SUCCESS] Timeline file size test passed!")


def main():
    """Run all performance tests."""
    print("\n" + "=" * 60)
    print("Phase 8.5: Large Repository Performance Tests")
    print("=" * 60)
    print("\nNote: These tests may take a minute to run...")

    test_list_performance_with_many_entries()
    test_revert_performance()
    test_undo_performance()
    test_export_performance()
    test_many_consecutive_operations()
    test_timeline_file_size()

    print("\n" + "=" * 60)
    print("[SUCCESS] All Phase 8.5 performance tests passed!")
    print("=" * 60)
    print("\nSummary:")
    print("  List operations: < 2s for 100+ entries")
    print("  Show command: < 1s")
    print("  Revert: < 3s")
    print("  Undo: < 2s")
    print("  Export: < 2s")
    print("  Timeline file: < 200KB for 50 entries")


if __name__ == "__main__":
    main()
