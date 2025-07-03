"""
Command-line interface for pyDMS.

This module provides the main entry point for running pyDMS
as a command-line application.
"""

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

import streamlit.web.cli as stcli


def main():
    """Main CLI entry point for pyDMS."""
    parser = argparse.ArgumentParser(
        description="pyDMS - IPA Data Management System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--host",
        default="localhost",
        help="Host to bind the server to (default: localhost)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8501,
        help="Port to bind the server to (default: 8501)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"pyDMS {get_version()}",
    )

    args = parser.parse_args()

    # Find the app.py file in the package
    # Check if running in PyInstaller bundle
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running in PyInstaller bundle - need to copy files to temp location
        bundle_app_path = Path(sys._MEIPASS) / "pydms" / "app.py"

        if not bundle_app_path.exists():
            print(
                f"Error: Could not find app.py in bundle at {bundle_app_path}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Create a temporary directory and copy the entire pydms package there
        temp_dir = Path(tempfile.mkdtemp(prefix="pydms_"))
        temp_pydms_dir = temp_dir / "pydms"
        bundle_pydms_dir = Path(sys._MEIPASS) / "pydms"

        try:
            # Copy the entire pydms directory to temp location
            shutil.copytree(bundle_pydms_dir, temp_pydms_dir)
            app_path = temp_pydms_dir / "app.py"

            # Register cleanup function
            import atexit

            atexit.register(lambda: shutil.rmtree(temp_dir, ignore_errors=True))

        except Exception as e:
            print(f"Error copying app files to temp directory: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Running normally
        app_path = Path(__file__).parent / "app.py"

    if not app_path.exists():
        print(f"Error: Could not find app.py at {app_path}", file=sys.stderr)
        print("Make sure the package is installed properly.", file=sys.stderr)
        sys.exit(1)

    # Set environment variables for better executable compatibility
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

    # Launch Streamlit with the app.py file
    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.address",
        args.host,
        "--server.port",
        str(args.port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--global.developmentMode",
        "false",
    ]

    try:
        stcli.main()
    except SystemExit as e:
        # Handle normal Streamlit exit
        sys.exit(e.code)
    except Exception as e:
        print(f"Error running Streamlit: {e}", file=sys.stderr)
        sys.exit(1)


def get_version():
    """Get the package version."""
    try:
        from . import __version__
    except ImportError:
        return "unknown"
    else:
        return __version__


if __name__ == "__main__":
    main()
