"""Copy surveycto_python_dict's library modules into src/datasure/vendor/scto_dict.

Used by the `just vendor-scto` recipe. Reads each module at a git ref of a local
surveycto_python_dict checkout, rewrites the package imports, applies PATCHES and
records the ref in VENDORED.md. Exits 1 when a patch no longer applies: upstream
has changed that code, so the patch is either merged upstream or needs redoing.

Also copies the upstream offline tests in TESTS to tests/vendor/scto_dict.

Usage: ``vendor_scto.py <path to surveycto_python_dict checkout> <git ref>``
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEST = ROOT / "src" / "datasure" / "vendor" / "scto_dict"
TESTS_DEST = ROOT / "tests" / "vendor" / "scto_dict"
# The typed import, plus questions, which the xml_contract tests use. The
# dictionary, stats, codebook and PII modules join when features use them.
MODULES = ("xpath", "xml_contract", "questions", "cast")
# The offline tests for the modules the import uses, and their fixture.
TESTS = ("farm_form", "test_xpath", "test_xml_contract", "test_cast")
# (module, upstream text, replacement), each pending an upstream PR.
PATCHES = (
    (
        "xml_contract",
        '''def parse_contract(xml_path) -> FormContract:
    """Parse a compiled XForm XML into a FormContract."""
    import xml.etree.ElementTree as ET

    root = ET.parse(str(xml_path)).getroot()
''',
        '''def parse_contract(xml_path) -> FormContract:
    """Parse a compiled XForm XML, as a path or as bytes, into a FormContract."""
    import xml.etree.ElementTree as ET

    if isinstance(xml_path, bytes):
        root = ET.fromstring(xml_path)
    else:
        root = ET.parse(str(xml_path)).getroot()
''',
    ),
)


def _show(repo: str, ref: str, path: str) -> str:
    return subprocess.run(
        ["git", "-C", repo, "show", f"{ref}:{path}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def main() -> int:
    """Vendor MODULES from the checkout at the given ref."""
    repo, ref = sys.argv[1:3]
    sha = subprocess.run(
        ["git", "-C", repo, "rev-parse", ref],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    sources = {
        m: _show(repo, sha, f"src/surveycto_python_dict/{m}.py").replace(
            "surveycto_python_dict.", "datasure.vendor.scto_dict."
        )
        for m in MODULES
    }
    tests = {
        t: _show(repo, sha, f"tests/{t}.py")
        .replace("surveycto_python_dict.", "datasure.vendor.scto_dict.")
        .replace(
            "from farm_form import", "from tests.vendor.scto_dict.farm_form import"
        )
        for t in TESTS
    }
    for module, old, new in PATCHES:
        if old not in sources[module]:
            print(f"Error: the {module} patch no longer applies at {sha}")
            return 1
        sources[module] = sources[module].replace(old, new)

    DEST.mkdir(parents=True, exist_ok=True)
    for module, text in sources.items():
        (DEST / f"{module}.py").write_text(text, encoding="utf-8", newline="\n")
    TESTS_DEST.mkdir(parents=True, exist_ok=True)
    for test, text in tests.items():
        (TESTS_DEST / f"{test}.py").write_text(text, encoding="utf-8", newline="\n")
    (DEST / "LICENSE").write_text(
        _show(repo, sha, "LICENSE"), encoding="utf-8", newline="\n"
    )

    vendored = (DEST / "VENDORED.md").read_text(encoding="utf-8").splitlines()
    vendored = [
        f"Source commit: `{sha}`" if line.startswith("Source commit:") else line
        for line in vendored
    ]
    (DEST / "VENDORED.md").write_text(
        "\n".join(vendored) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Vendored {len(MODULES)} modules at {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
