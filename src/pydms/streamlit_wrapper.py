"""
Streamlit wrapper for PyInstaller executable.

This module provides a proper wrapper to run Streamlit applications
in PyInstaller executables, avoiding subprocess issues.
"""

import os
import sys
from pathlib import Path

import streamlit.web.cli as stcli


def run_streamlit_app():
    """Run the Streamlit app with proper configuration for executables."""
    # Set environment variables for Streamlit
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

    # Get the app.py path
    # Check if running in PyInstaller bundle
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running in PyInstaller bundle
        app_path = Path(sys._MEIPASS) / "pydms" / "app.py"
    else:
        # Running normally
        app_path = Path(__file__).parent / "app.py"

    if not app_path.exists():
        print(f"Error: Could not find app.py at {app_path}", file=sys.stderr)

        # Debug information for PyInstaller
        if getattr(sys, "frozen", False):
            print(
                f"Running in PyInstaller bundle. sys._MEIPASS = {getattr(sys, '_MEIPASS', 'N/A')}",
                file=sys.stderr,
            )
            print(f"__file__ = {__file__}", file=sys.stderr)

        sys.exit(1)

    # Configure sys.argv for Streamlit
    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.address",
        "localhost",
        "--server.port",
        "8501",
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--global.developmentMode",
        "false",
    ]

    # Run Streamlit
    try:
        stcli.main()
    except SystemExit:
        # Handle normal Streamlit exit
        pass
    except Exception as e:
        print(f"Error running Streamlit: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_streamlit_app()
