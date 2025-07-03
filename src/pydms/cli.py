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

    # Set environment variables for better executable compatibility
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

    # Handle PyInstaller bundle execution differently
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running in PyInstaller bundle - use direct module import approach
        try:
            # Add the bundle path to sys.path so imports work correctly
            sys.path.insert(0, str(Path(sys._MEIPASS)))

            # Import Streamlit components for direct execution
            from streamlit import config
            from streamlit.web import cli as web_cli

            # Configure Streamlit for the executable
            config.set_option("server.headless", True)
            config.set_option("server.address", args.host)
            config.set_option("server.port", args.port)
            config.set_option("browser.gatherUsageStats", False)
            config.set_option("global.developmentMode", False)

            # Import the app module directly to execute it

            # Start the Streamlit server directly
            web_cli._main_run_clExplicit = (
                lambda target, command_line, args_list: web_cli._main_run(
                    target, command_line, args_list
                )
            )

            # This approach runs the imported app
            from streamlit.web.bootstrap import run

            run("", "streamlit run", [])

        except Exception as e:
            print(f"Error running Streamlit in bundle mode: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Running normally - use standard streamlit run
        app_path = Path(__file__).parent / "app.py"

        if not app_path.exists():
            print(f"Error: Could not find app.py at {app_path}", file=sys.stderr)
            print("Make sure the package is installed properly.", file=sys.stderr)
            sys.exit(1)

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
