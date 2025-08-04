"""
Command-line interface for DataSure.

This module provides the main entry point for running DataSure
as a command-line application.
"""

import subprocess
import sys
from pathlib import Path

from streamlit.web import cli as stcli


def main():
    """Main entry point for the DataSure CLI."""
    app_path = Path(__file__).parent / "app.py"
    subprocess.run(["streamlit", "run", str(app_path)])


def get_version():
    """Get the package version."""
    try:
        from importlib.metadata import version

        return version("DataSure")
    except Exception:
        return "0.1.0"


if __name__ == "__main__":
    main()
    sys.exit(stcli.main())
