"""
Command-line interface for pyDMS.

This module provides the main entry point for running pyDMS
as a command-line application.
"""

import argparse
import contextlib
import os
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

            # Configure Streamlit for the executable with proper security settings
            config.set_option("server.headless", True)
            config.set_option("server.address", args.host)
            config.set_option("server.port", args.port)
            config.set_option("browser.gatherUsageStats", False)
            config.set_option("global.developmentMode", False)

            # Security configuration - properly handle CORS and XSRF protection
            config.set_option("server.enableCORS", True)
            config.set_option("server.enableXsrfProtection", True)

            # Set allowed origins for security
            config.set_option("server.allowRunOnSave", False)
            config.set_option("server.runOnSave", False)

            # Create a properly accessible temporary app file
            bundle_app_path = Path(sys._MEIPASS) / "pydms" / "app.py"

            # Create temp file in a user-writable location
            temp_fd, temp_app_path = tempfile.mkstemp(suffix=".py", prefix="pydms_app_")
            temp_path = Path(temp_app_path)

            try:
                # Read the app content from the bundle
                with open(bundle_app_path, encoding="utf-8") as src:
                    app_content = src.read()

                # Write to the temporary file
                with os.fdopen(temp_fd, "w", encoding="utf-8") as dst:
                    dst.write(app_content)

                # Ensure proper permissions
                os.chmod(temp_path, 0o644)

                # Set up Streamlit arguments with security settings
                sys.argv = [
                    "streamlit",
                    "run",
                    str(temp_path),
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
                    "--server.enableCORS",
                    "true",
                    "--server.enableXsrfProtection",
                    "true",
                ]

                # Register cleanup
                import atexit

                atexit.register(lambda: temp_path.unlink(missing_ok=True))

                # Use the standard Streamlit CLI
                stcli.main()

            except Exception:
                # Ensure cleanup even if there's an error
                with contextlib.suppress(Exception):
                    temp_path.unlink(missing_ok=True)
                raise

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
