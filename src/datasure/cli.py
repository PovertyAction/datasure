"""
Command-line interface for DataSure.

This module provides the main entry point for running DataSure
as a command-line application.
"""

import argparse
import logging
import sys
from pathlib import Path

import streamlit.web.cli as stcli


class _SuppressStaticSyncRouteError(logging.Filter):
    """Suppress spurious WinError 123 from Streamlit's static/:sync: routing on Windows.

    Streamlit's internal /:sync: endpoint is sometimes misrouted to the static
    file handler, which constructs an invalid Windows path containing ':sync:'.
    """

    def filter(self, record):
        if record.exc_info:
            exc = record.exc_info[1]
            if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 123:
                filename = str(getattr(exc, "filename", "") or "")
                if ":sync:" in filename:
                    return False
        return True


def main():
    """Main CLI entry point for DataSure."""
    parser = argparse.ArgumentParser(
        description="DataSure - IPA Data Management System",
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
        "--logging",
        type=str,
        default="info",
        help="Level of logging for Streamlit's internal logger: 'error', 'warning', 'info', or 'debug'. (default: info)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"DataSure {get_version()}",
    )

    args = parser.parse_args()

    # Find the app.py file in the package
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
        "--logger.level",
        str(args.logging),
    ]

    logging.getLogger("uvicorn.error").addFilter(_SuppressStaticSyncRouteError())

    sys.exit(stcli.main())


def get_version():
    """Get the package version from installed metadata."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("DataSure")
    except PackageNotFoundError:
        # Better to admit ignorance than report a stale hardcoded version
        return "unknown"


if __name__ == "__main__":
    main()
