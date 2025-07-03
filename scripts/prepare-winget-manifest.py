#!/usr/bin/env python3
"""Script to prepare winget manifest files for submission."""

import hashlib
import sys
from pathlib import Path

import requests
import yaml


def get_file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest().upper()


def get_remote_file_hash(url: str) -> str:
    """Calculate SHA256 hash of a remote file."""
    response = requests.get(url, stream=True)
    response.raise_for_status()

    sha256_hash = hashlib.sha256()
    for chunk in response.iter_content(chunk_size=4096):
        sha256_hash.update(chunk)
    return sha256_hash.hexdigest().upper()


def update_manifest_files(version: str, installer_url: str, installer_hash: str):
    """Update winget manifest files with version and installer information."""
    project_root = Path(__file__).parent.parent
    winget_dir = project_root / "winget"

    # Update version file
    version_file = winget_dir / "PovertyAction.pyDMS.yaml"
    with open(version_file) as f:
        version_manifest = yaml.safe_load(f)

    version_manifest["PackageVersion"] = version

    with open(version_file, "w") as f:
        yaml.dump(version_manifest, f, default_flow_style=False, sort_keys=False)

    # Update locale file
    locale_file = winget_dir / "PovertyAction.pyDMS.locale.en-US.yaml"
    with open(locale_file) as f:
        locale_manifest = yaml.safe_load(f)

    locale_manifest["PackageVersion"] = version
    locale_manifest["ReleaseNotesUrl"] = (
        f"https://github.com/PovertyAction/pydms/releases/tag/v{version}"
    )

    with open(locale_file, "w") as f:
        yaml.dump(locale_manifest, f, default_flow_style=False, sort_keys=False)

    # Update installer file
    installer_file = winget_dir / "PovertyAction.pyDMS.installer.yaml"
    with open(installer_file) as f:
        installer_manifest = yaml.safe_load(f)

    installer_manifest["PackageVersion"] = version
    installer_manifest["Installers"][0]["InstallerUrl"] = installer_url
    installer_manifest["Installers"][0]["InstallerSha256"] = installer_hash

    with open(installer_file, "w") as f:
        yaml.dump(installer_manifest, f, default_flow_style=False, sort_keys=False)

    print(f"✅ Updated winget manifests for version {version}")
    print(f"📦 Installer URL: {installer_url}")
    print(f"🔒 SHA256: {installer_hash}")


def main():
    """Main function."""
    if len(sys.argv) != 2:
        print("Usage: python prepare-winget-manifest.py <version>")
        print("Example: python prepare-winget-manifest.py 0.1.0")
        sys.exit(1)

    version = sys.argv[1]
    installer_url = f"https://github.com/PovertyAction/pydms/releases/download/v{version}/pydms-installer.exe"

    print(f"🔍 Calculating hash for {installer_url}")

    try:
        installer_hash = get_remote_file_hash(installer_url)
        update_manifest_files(version, installer_url, installer_hash)
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Make sure the release exists and the installer is uploaded.")
        sys.exit(1)


if __name__ == "__main__":
    main()
