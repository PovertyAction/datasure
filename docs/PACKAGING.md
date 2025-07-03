# Windows Packaging & Distribution Guide

This guide explains how to package pyDMS as a Windows executable and distribute it via winget.

## Overview

The project uses PyInstaller to create standalone Windows executables and GitHub Actions for automated building and releasing. The application can be distributed through:

1. **GitHub Releases** - Direct download of installer and portable zip
2. **Windows Package Manager (winget)** - Automated installation via winget

## Build Requirements

### Local Development

- Python 3.11+
- UV package manager
- PyInstaller (installed via `uv sync --extra build`)

### CI/CD Requirements

- GitHub repository with Actions enabled
- GitHub secrets configured (see [Secrets Configuration](#secrets-configuration))

## Local Building

### Quick Build

```bash
# Build Windows executable
just build-windows

# Or manually:
uv sync --extra build
uv run python scripts/build-windows.py
```

### Complete Release Workflow

```bash
# Build for a specific version
just release-windows 1.0.0
```

This will:

1. Clean previous builds
2. Create Windows executable with PyInstaller
3. Generate installer with NSIS (if available)
4. Create portable zip archive

## Files Structure

### Build Configuration

- `build.spec` - PyInstaller specification file
- `scripts/build-windows.py` - Build automation script
- `.github/workflows/build-and-release.yml` - CI/CD workflow for releases
- `.github/workflows/build.yml` - CI/CD workflow for code quality (SonarQube, tests)
- `.github/workflows/ploomber-cloud.yaml` - Ploomber Cloud deployment workflow
- `sonar-project.properties` - SonarQube configuration
- `ploomber-cloud.json` - Ploomber Cloud deployment configuration
- `src/pydms/` - Main Python package with app.py, views/, and assets/

### Winget Manifests

- `winget/PovertyAction.pyDMS.yaml` - Version manifest
- `winget/PovertyAction.pyDMS.installer.yaml` - Installer manifest
- `winget/PovertyAction.pyDMS.locale.en-US.yaml` - Localization manifest

## Automated Releases

### GitHub Actions Workflow

The build workflow triggers on:

- **Tag pushes** starting with `v` (e.g., `v1.0.0`)
- **Manual workflow dispatch** with version input

#### What the workflow does

1. **Python Package Build Phase**:
   - Sets up Python 3.11 on Ubuntu runner
   - Installs dependencies with UV
   - Updates version in package files
   - Builds wheel and source distribution
   - Publishes to Test PyPI (for pre-releases)
   - Publishes to PyPI (for stable releases)

2. **Windows Build Phase**:
   - Sets up Python 3.11 on Windows runner
   - Installs dependencies with UV
   - Updates version in package files
   - Builds executable with PyInstaller
   - Creates NSIS installer (optional)
   - Creates portable zip archive

3. **Release Phase**:
   - Uploads build artifacts (Windows executables + Python packages)
   - Creates GitHub release with all assets
   - Generates release notes

4. **Winget Update Phase** (stable releases only):
   - Automatically submits to winget community repository
   - Updates package manifests with new version

### Creating a Release

#### Option 1: Tag-based Release

```bash
# Create and push a version tag
git tag v1.0.0
git push origin v1.0.0
```

#### Option 2: Manual Release

1. Go to GitHub Actions tab
2. Select "Build and Release" workflow
3. Click "Run workflow"
4. Enter version (e.g., `v1.0.0`)

## PyPI Distribution

### Package Information

- **Package Name**: `pyDMS`
- **Installation Command**: `pip install pyDMS`
- **CLI Command**: `pydms` (after installation)

### PyPI Publishing

#### Automatic Publishing

The workflow automatically publishes to PyPI:

- **Stable releases**: Published to PyPI when tags don't contain `-` (e.g., `v1.0.0`)
- **Pre-releases**: Published to Test PyPI when tags contain `-` (e.g., `v1.0.0-beta.1`)

#### Manual Publishing

```bash
# Build and check package
just build-package
just check-pypi

# Publish to Test PyPI (for testing)
just publish-test

# Publish to PyPI (production)
just publish
```

#### Installing from PyPI

```bash
# Install latest stable version
pip install pyDMS

# Install specific version
pip install pyDMS==1.0.0

# Install from Test PyPI
pip install --index-url https://test.pypi.org/simple/ pyDMS

# Run the application
pydms --help
pydms --port 8502
```

## Winget Distribution

### Package Information

- **Package ID**: `PovertyAction.pyDMS`
- **Publisher**: Innovations for Poverty Action
- **Installation Command**: `winget install PovertyAction.pyDMS`

### Winget Manifest Management

#### Automatic Updates

For stable releases (no pre-release tags), the workflow automatically:

1. Updates winget manifests with new version and installer hash
2. Submits PR to [winget-pkgs repository](https://github.com/microsoft/winget-pkgs)

#### Manual Updates

If automatic submission fails:

```bash
# After release is published, update manifests
just prepare-winget 1.0.0

# Then manually submit to winget-pkgs repository
```

## Secrets Configuration

Configure these GitHub repository secrets:

### Required for Basic Functionality

- `GITHUB_TOKEN` - Automatically provided by GitHub Actions

### Required for PyPI Publishing

- `PYPI_API_TOKEN` - PyPI API token for publishing stable releases
- `TEST_PYPI_API_TOKEN` - Test PyPI API token for publishing pre-releases

### Required for Winget Auto-submission

- `WINGET_TOKEN` - Personal access token for winget-pkgs repository access
- `WINGET_FORK_USER` - GitHub username for forking winget-pkgs repository

### Setting up PyPI Secrets

1. **Create PyPI API Tokens**:
   - Go to [PyPI Account Settings](https://pypi.org/manage/account/)
   - Generate API token with appropriate scope
   - Save as `PYPI_API_TOKEN` secret

2. **Create Test PyPI API Token**:
   - Go to [Test PyPI Account Settings](https://test.pypi.org/manage/account/)
   - Generate API token with appropriate scope
   - Save as `TEST_PYPI_API_TOKEN` secret

### Setting up Winget Secrets

1. **Create GitHub Personal Access Token**:
   - Go to GitHub Settings → Developer settings → Personal access tokens
   - Create token with `public_repo` and `workflow` scopes
   - Save as `WINGET_TOKEN` secret

2. **Set Fork User**:
   - Set `WINGET_FORK_USER` to your GitHub username
   - This is used to fork the winget-pkgs repository

## Distribution Artifacts

Each release creates these downloadable assets:

### 1. Python Packages

- **Wheel**: `pyDMS-1.0.0-py3-none-any.whl`
- **Source**: `pyDMS-1.0.0.tar.gz`
- **Distribution**: PyPI and Test PyPI
- **Installation**: `pip install pyDMS`

### 2. Windows Installer (`pydms-installer.exe`)

- **Type**: NSIS-based installer
- **Features**:
  - System-wide installation
  - Start menu shortcuts
  - Desktop shortcut
  - Uninstaller
  - Windows registry integration

### 3. Portable Archive (`pydms-v1.0.0-windows-portable.zip`)

- **Type**: Portable application
- **Features**:
  - No installation required
  - Self-contained executable
  - Run from any directory

## Troubleshooting

### Common Build Issues

#### PyInstaller Import Errors

If PyInstaller fails to detect modules:

1. Add missing modules to `hiddenimports` in `build.spec`
2. Check for dynamic imports in the codebase

#### Missing Data Files

If assets or views are missing:

1. Verify paths in `data` section of `build.spec`
2. Ensure files exist in the project structure

#### Large Executable Size

To reduce executable size:

1. Review `excludes` in `build.spec`
2. Consider using `--onedir` instead of `--onefile`
3. Remove unnecessary dependencies

### GitHub Actions Issues

#### Build Failures

1. Check Python version compatibility
2. Verify all dependencies are available on Windows
3. Review PyInstaller logs in Actions output

#### Winget Submission Failures

1. Verify secrets are configured correctly
2. Check if package ID already exists in winget-pkgs
3. Ensure installer URL is publicly accessible

## Version Management

### Versioning Strategy

- Use semantic versioning (e.g., `1.0.0`)
- Tag format: `v{version}` (e.g., `v1.0.0`)
- Pre-releases: Use `-` suffix (e.g., `v1.0.0-beta.1`)

### Version Updates

The workflow automatically updates version in:

- `src/pydms/__init__.py`
- Winget manifest files
- GitHub release information

### Manual Version Update

```bash
# Update version in package
sed -i 's/__version__ = ".*"/__version__ = "1.0.0"/' src/pydms/__init__.py

# Update winget manifests
just prepare-winget 1.0.0
```

## Testing Releases

### Local Testing

```bash
# Build and test locally
just build-windows

# Run the executable
./dist/pydms/pydms.exe
```

### Pre-release Testing

1. Create pre-release with `-beta` or `-rc` suffix
2. Test installation and functionality
3. Create stable release when ready

### Winget Testing

```bash
# Test winget installation (after publication)
winget install PovertyAction.pyDMS

# Test specific version
winget install PovertyAction.pyDMS --version 1.0.0
```

## Support

For packaging-related issues:

- **Build Issues**: Check GitHub Actions logs and PyInstaller documentation
- **Distribution Issues**: Contact repository maintainers
- **Winget Issues**: Check [winget-pkgs repository](https://github.com/microsoft/winget-pkgs) guidelines
