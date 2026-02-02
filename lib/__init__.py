"""Rewindo library."""

from .rewindo import Rewindo

__all__ = ["Rewindo", "main"]
__version__ = "0.1.0"


def main():
    """Main entry point for the CLI when installed as a package."""
    import sys
    import os
    from pathlib import Path

    # When installed, the bin/rewindo script should be in the package
    # We need to import and run it
    try:
        # Try to import from the installed package
        from rewindo import _cli_main
        return _cli_main()
    except ImportError:
        # Fallback: run the bin/rewindo script directly
        package_root = Path(__file__).parent.parent
        bin_script = package_root / "bin" / "rewindo"

        # Read and exec the script
        import runpy
        sys.path.insert(0, str(package_root / "lib"))
        return runpy.run_path(str(bin_script), run_name="__main__")


def _cli_main():
    """Internal CLI main - imports and runs bin/rewindo."""
    import sys
    from pathlib import Path

    # Find and run the bin/rewindo script
    current_file = Path(__file__)
    package_root = current_file.parent.parent
    bin_script = package_root / "bin" / "rewindo"

    if not bin_script.exists():
        raise FileNotFoundError(f"CLI script not found at {bin_script}")

    # Execute the CLI script
    import runpy
    sys.path.insert(0, str(package_root / "lib"))
    runpy.run_path(str(bin_script), run_name="__main__")
