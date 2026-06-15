"""Verify CHANGELOG.md has entries under [Unreleased] before a release.

Used by the `just check-changelog` recipe (a dependency of the version
bump-and-tag recipes) so a release cannot be tagged with an empty
changelog. Exits 0 if at least one bullet entry exists under the
[Unreleased] heading, 1 otherwise.
"""

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"


def main() -> int:
    """Check for bullet entries in the [Unreleased] section."""
    if not CHANGELOG.exists():
        print(f"Error: {CHANGELOG} not found")
        return 1

    text = CHANGELOG.read_text(encoding="utf-8")
    match = re.search(
        r"^## \[Unreleased\](?P<body>.*?)(?=^## |^---|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        print("Error: CHANGELOG.md has no '## [Unreleased]' section")
        return 1

    bullets = [
        line
        for line in match.group("body").splitlines()
        if line.lstrip().startswith(("- ", "* "))
    ]
    if not bullets:
        print(
            "Error: CHANGELOG.md has no entries under [Unreleased].\n"
            "Add changelog entries before tagging a release "
            "(see docs/changelog_guide.md)."
        )
        return 1

    print(f"CHANGELOG.md: {len(bullets)} entries under [Unreleased]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
