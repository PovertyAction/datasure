#!/usr/bin/env python3
"""Build script for creating Windows executable with PyInstaller."""

import shutil
import subprocess
import sys
from pathlib import Path


def main():
    """Build Windows executable using PyInstaller."""
    project_root = Path(__file__).parent.parent
    spec_file = project_root / "build.spec"
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"

    print("🏗️  Building pyDMS Windows executable...")

    # Clean previous builds
    if dist_dir.exists():
        print("🧹 Cleaning previous dist directory...")
        shutil.rmtree(dist_dir)

    if build_dir.exists():
        print("🧹 Cleaning previous build directory...")
        shutil.rmtree(build_dir)

    # Run PyInstaller
    try:
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            str(spec_file),
        ]

        print(f"🚀 Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=project_root, check=True)

        if result.returncode == 0:
            print("✅ Build completed successfully!")

            # Check if executable was created
            exe_path = dist_dir / "pydms" / "pydms.exe"
            if exe_path.exists():
                print(f"📦 Executable created: {exe_path}")
                print(f"📊 Size: {exe_path.stat().st_size / (1024*1024):.1f} MB")
            else:
                print("❌ Executable not found in expected location")
                return 1

    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed with exit code {e.returncode}")
        return 1
    except Exception as e:
        print(f"❌ Build failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
