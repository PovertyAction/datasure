"""
Command-line interface for pyDMS.

This module provides the main entry point for running pyDMS
as a command-line application.
"""

import argparse
import os
import sys
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
        # Running in PyInstaller bundle
        app_path = Path(sys._MEIPASS) / "pydms" / "app.py"
    else:
        # Running normally
        app_path = Path(__file__).parent / "app.py"

    if not app_path.exists():
        print(f"Error: Could not find app.py at {app_path}", file=sys.stderr)
        print("Make sure the package is installed properly.", file=sys.stderr)

        # Debug information for PyInstaller
        if getattr(sys, "frozen", False):
            print(
                f"Running in PyInstaller bundle. sys._MEIPASS = {getattr(sys, '_MEIPASS', 'N/A')}",
                file=sys.stderr,
            )
            print(f"__file__ = {__file__}", file=sys.stderr)
            print(f"sys.executable = {sys.executable}", file=sys.stderr)

            # List available files for debugging
            if hasattr(sys, "_MEIPASS"):
                meipass_path = Path(sys._MEIPASS)
                print(f"Files in {meipass_path}:", file=sys.stderr)
                try:
                    for item in meipass_path.iterdir():
                        print(f"  {item}", file=sys.stderr)
                        if item.is_dir() and item.name == "pydms":
                            print("    pydms directory contents:", file=sys.stderr)
                            for subitem in item.iterdir():
                                print(f"      {subitem}", file=sys.stderr)
                except Exception as e:
                    print(f"  Error listing files: {e}", file=sys.stderr)

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
