# DataSure

IPA Dashboard Solution for Data Management Systems.

## Development set up

Development relies on the following software

- `winget` (Windows) or `homebrew` (MacOS/Linux) for package management and installation
- `git` for source control management
- `just` for running common command line patterns
- `uv` for installing Python and managing virtual environments

First, clone this repository to your local computer either via GitHub Desktop.

or from the command line:

```bash
# If using HTTPS
git clone https://github.com/PovertyAction/dms-dashboard.git

# If using SSH
git clone git@github.com:PovertyAction/dms-dashboard.git
```

This repository uses a `Justfile` for collecting common command line actions that we run
to set up the computing environment and build the assets of the handbook. Note that you
should also have Git installed

To get started, make sure you have `Just` installed on your computer by running the
following from the command line:

| Platform  | Commands                                                            |
| --------- | ------------------------------------------------------------------- |
| Windows   | `winget install Git.Git Casey.Just astral-sh.uv` |
| Mac/Linux | `brew install just uv gh`                                          |

This will make sure that you have the latest version of `Just`, as well as
[uv](https://docs.astral.sh/uv/) (installer for Python) and

- We use `Just` in order to make it easier for all IPA users to be productive with data
  and technology systems. The goal of using a `Justfile` is to help make the end goal of
  the user easier to achieve without needing to know or remember all of the technical
  details of how we get to that goal.
- We use `uv` to help ease use of Python. `uv` provides a global system for creating and
  building computing environments for Python.

As a shortcut, if you already have `Just` installed, you can run the following to
install required software and build a python virtual environment that is used to build
the handbook pages:

```bash
just get-started
```

Note: you may need to restart your terminal after running the command above to activate
the installed software.

After the required software is installed, you can activate the Python virtual
environment:

| Shell      | Commands                                |
| ---------- | --------------------------------------- |
| Bash       | `.venv/Scripts/activate`                |
| Powershell | `.venv/Scripts/activate.ps1`            |
| Nushell    | `overlay use .venv/Scripts/activate.nu` |

## Available Justfile Commands

This project uses [Just](https://github.com/casey/just) as a command runner to simplify common development tasks. Here are the available commands:

### Environment Setup

```bash
just get-started          # Complete setup (install software + create venv)
just venv                 # Create virtual environment and install dependencies
just clean                # Remove virtual environment
just activate-venv        # Activate the virtual environment
```

### Development

```bash
uv run datasure                  # Launch the DataSure application
just lab                     # Launch Jupyter Lab
```

### Code Quality

```bash
just lint-py              # Lint Python code with Ruff
just fmt-python           # Format Python code with Ruff
just fmt-py <file>         # Format a specific Python file
just fmt-markdown          # Format all markdown files
just fmt-md <file>         # Format a specific markdown file
just fmt-check-markdown    # Check markdown formatting
just fmt-all              # Format all code and markdown files
just pre-commit-run        # Run pre-commit hooks
```

### Testing

```bash
just test                 # Run all tests
just test-cov             # Run tests with coverage report (terminal)
just test-cov-html        # Run tests with HTML coverage report
just test-cov-xml         # Run tests with XML coverage report (for CI)
```

### Package Building

```bash
just build-package        # Build both wheel and source distribution
just clean-build          # Clean build artifacts
just install-package      # Install the package locally from built wheel
just uninstall-package    # Uninstall the package
just test-cli             # Test the CLI after installation
just package-workflow     # Complete workflow: test, build, and verify
```

### Publishing

```bash
just check-pypi           # Check package metadata and structure
just pypi-info            # View package info and version
just publish-test         # Publish to TestPyPI (for testing)
just publish              # Publish to PyPI (production)
```

### Utilities

```bash
just system-info          # Display system information
just update-reqs          # Update project dependencies
```

## Testing the Streamlit App

Follow these steps to test the app:

### 1. Prepare Your Environment

- Ensure all necessary files are on your local machine. To do this, pull the latest updates from the GitHub repository:
  - **Using Visual Studio Code (VS Code):** Sync files through the Source Control panel.
  - **Using Command Line:** Run the following command in your terminal:

    ```bash
    git pull
    ```

### 2. Navigate to the Repository

- Open your terminal (VS Code terminal, Command Prompt, or PowerShell).
- Navigate to the folder where the repository is located.

### 3. Start the App

- Run one of the following commands to launch the app:

    ```bash
    uv run datasure
    ```

---

### App Features

### Import Data Page

- When the app starts, the **Import Data** page is displayed.
- This page includes four tabs for connecting datasets. Currently, only the **SurveyCTO** and **Local Storage** tabs are functional.
- Use these tabs to upload or connect your datasets.

### Prepare Data Page

- After importing data, go to the **Prepare Data** page to preview your datasets. Each dataset will appear in a separate tab.
- **Note:** This section is still under development. While the functions listed won't work yet, you can review them and suggest additional features.

### Configure Checks Page

- Set up **HFCs** (High-Frequency Checks) on this page:
  1. Enter a name in the **Page Name** input box.
  2. Select a dataset from the **Select Data** dropdown.
  3. Additional input fields will appear as you provide information.
  4. Once the form is complete, click **Add Page** and save the settings.
- This will create an HFC page, but currently, you can only set up one HFC page at a time.
- If the HFC page doesn’t appear immediately, select another page from the left navigation menu and return.

### HFC Page

- The HFC page contains dashboards for various checks, organized into tabs.
- To set up the checks:
  1. Open a tab and expand the **Settings Expander** at the top.
  2. Configure the settings as needed for the check to display the required output.

## Running Tests

The project uses Python `pytest` framework for testing. The test files are located in the `tests/` directory.

To run all tests, execute the following command from the project root directory:

```bash
uv run python -m pytest
```

To run a specific test file, use:

```bash
uv run python -m pytest tests/test_file.py
```

## Package Building and Distribution

DataSure is set up as a proper Python package using [uv](https://docs.astral.sh/uv/) with the `uv_build` backend for simple and fast building and publishing.

### Building the Package

To build the package for distribution:

```bash
# Build both wheel and source distribution
just build-package

# Or use uv directly
uv build
```

This creates two files in the `dist/` directory:

- `datasure-{version}-py3-none-any.whl` (wheel distribution)
- `datasure-{version}.tar.gz` (source distribution)

### Testing the Package

To test the built package locally:

```bash
# Install the package locally
just install-package

# Or install directly from the wheel
uv pip install dist/datasure-*.whl
```

### Using the CLI

Once installed, you can use the command-line interface:

```bash
# Show version
uv run datasure --version

# Launch the dashboard (default: localhost:8501)
uv run datasure

# Launch with custom host/port
uv run datasure --host 0.0.0.0 --port 8080
```

### Package Development Workflow

1. **Make changes** to the code
2. **Update version** in `pyproject.toml`
3. **Run tests** to ensure everything works:

   ```bash
   just test
   ```

4. **Build the package**:

   ```bash
   just build-package
   ```

5. **Test the package installation**:

   ```bash
   just install-package
   uv run datasure --version
   ```

### Version Management

DataSure uses automated version management through `uv version` commands. The package follows [semantic versioning](https://semver.org/):

- **MAJOR** version when you make incompatible API changes
- **MINOR** version when you add functionality in a backward compatible manner
- **PATCH** version when you make backward compatible bug fixes

#### Version Bump Commands

```bash
# Alpha releases (early development testing)
just bump-patch-alpha     # 0.1.0 -> 0.1.1a1
just bump-minor-alpha     # 0.1.0 -> 0.2.0a1
just bump-major-alpha     # 0.1.0 -> 1.0.0a1

# Beta releases (feature-complete testing)
just bump-patch-beta      # 0.1.0 -> 0.1.1b1
just bump-minor-beta      # 0.1.0 -> 0.2.0b1
just bump-major-beta      # 0.1.0 -> 1.0.0b1

# Release candidates (final testing)
just bump-patch-rc        # 0.1.0 -> 0.1.1rc1
just bump-minor-rc        # 0.1.0 -> 0.2.0rc1
just bump-major-rc        # 0.1.0 -> 1.0.0rc1

# Final releases
just bump-patch           # 0.1.0 -> 0.1.1
just bump-minor           # 0.1.0 -> 0.2.0
just bump-major           # 0.1.0 -> 1.0.0
```

These commands automatically:

- Update the version in `src/datasure/__init__.py`
- Run `uv sync` to update the lock file
- Commit the changes to git
- Create a git tag for the new version

#### Git Tag Management

```bash
# Create git tag for current version (if it doesn't exist)
just tag-version          # Creates tag like v0.1.2

# Push tag to remote repository
just push-tag            # Push the current version tag

# Push both commits and tags
just push-all            # Push commits and current version tag
```

**Note:** The version bump commands (`just bump-*`) automatically create git tags, so you typically don't need to run `just tag-version` manually.

### Testing the Build and Publish Workflow

Before publishing your package, it's essential to test the entire workflow using TestPyPI:

#### 1. Set Up TestPyPI Account

1. Login at <https://test.pypi.org/account> (you need to be a member of the IPA PyPI organization)
2. Generate an API token:
   - Go to <https://test.pypi.org/manage/account/>
   - Click "Add API token"
   - Give it a name (e.g., "datasure-test")
   - Copy the token (starts with `pypi-`)

#### 2. Configure Authentication

Set the `UV_PUBLISH_TOKEN` environment variable with your TestPyPI token:

**Windows (PowerShell):**

```powershell
$env:UV_PUBLISH_TOKEN = "pypi-your-token-here"
```

**Windows (Command Prompt):**

```cmd
set UV_PUBLISH_TOKEN=pypi-your-token-here
```

**Linux/macOS:**

```bash
export UV_PUBLISH_TOKEN="pypi-your-token-here"
```

**Permanent Setup (recommended):**
Add the token to your shell profile (`.bashrc`, `.zshrc`, or Windows Environment Variables) to avoid setting it each time.

#### 3. Test the Complete Workflow

```bash
# 1. Clean any existing build artifacts
just clean-build

# 2. Bump version for testing (use alpha for test releases)
just bump-patch-alpha

# 3. Verify the version was updated
uv run datasure --version

# 4. Build the package
just build-package

# 5. Publish to TestPyPI
just publish-test

# 6. Install from TestPyPI to verify it works
uv pip install --index-url https://test.pypi.org/simple/ datasure
```

#### 4. Troubleshooting Common Issues

**Version Already Exists Error:**

```bash
error: Local file and index file do not match for datasure-X.Y.Z
```

Solution: Bump the version again - you cannot republish the same version.

**Authentication Error:**

```bash
error: 401 Unauthorized
```

Solution: Verify your `UV_PUBLISH_TOKEN` is set correctly and the token is valid.

### Publishing to PyPI (Production)

Once you've successfully tested with TestPyPI

#### 1. Set Up PyPI Account

1. Create an account at <https://pypi.org/account/register/>
2. Generate an API token at <https://pypi.org/manage/account/>
3. Set the token as `UV_PUBLISH_TOKEN` (same as TestPyPI setup)

#### 2. Production Publishing Workflow

```bash
# 1. Ensure you're on the main branch with latest changes
git checkout main
git pull

# 2. Run tests to ensure everything works
just test

# 3. Bump to final version (automatically creates git tag and commits)
just bump-patch  # or bump-minor/bump-major as appropriate

# 4. Push changes and tags to trigger automated release
just push-all

# 5. GitHub Actions will automatically:
#    - Run Code Coverage workflow (tests + quality checks)
#    - If successful, run Build and Release workflow
#    - Build package and publish to PyPI
#    - Create GitHub release with artifacts
```

## Automated Release Pipeline

DataSure uses GitHub Actions for automated testing and releasing:

### Workflow Dependencies

1. **Code Coverage Workflow** (`.github/workflows/build.yml`)
   - Runs on: branches `main`, tags `v*`, and pull requests
   - Executes: pre-commit hooks, tests, SonarQube analysis
   - **Must pass** before releases can proceed

2. **Build and Release Workflow** (`.github/workflows/build-and-release.yml`)
   - **Triggered by**: Code Coverage workflow completion
   - **Only runs if**: Code Coverage succeeded AND triggered by tag push
   - Executes: package building, PyPI publishing, GitHub release creation

### Release Process

```bash
# Step 1: Create a release (this triggers both workflows)
just bump-patch  # Creates git tag v1.0.1

# Step 2: Push to trigger automation
just push-all    # Pushes commits and tags

# Step 3: Monitor workflows in GitHub Actions
# - Code Coverage runs first (quality gate)
# - Build and Release runs only if Code Coverage passes
# - Package published to PyPI automatically
# - GitHub release created with artifacts
```

### Manual Release Override

For emergency releases bypassing quality checks:

```bash
# Trigger Build and Release workflow manually
# Go to GitHub Actions → Build and Release → Run workflow
# Enter version (e.g., v1.0.1) and click "Run workflow"
```

### Quality Gates

- **Pre-commit hooks**: Code formatting and linting
- **Test suite**: All tests must pass
- **SonarQube analysis**: Code quality and security checks
- **Failed quality checks** = **No release**

#### 3. Verifying Package Before Publishing

Before publishing, you can verify your package:

```bash
# Check package metadata and structure
just check-pypi

# View package info
just pypi-info
```

**Note:** The project now uses `uv publish` for all publishing operations.

## Data Storage and Cache

DataSure automatically manages data storage and caching for optimal performance across different environments:

### Cache Directory Locations

- **Development Mode** (when running from source): `./cache/` (in project root)
- **Production Mode** (when installed as package):
  - **Windows**: `%APPDATA%/datasure/cache/`
  - **Linux/macOS**: `~/.local/share/datasure/cache/`

### What's Stored

The cache directory contains:

- **Project configurations**: HFC page settings and form configurations
- **Database files**: DuckDB databases for processed survey data
- **SurveyCTO cache**: Cached form metadata and server connections
- **User settings**: Check configurations and preferences

### Cache Management

- Cache directories are created automatically when needed
- No manual setup required - DataSure detects the environment and uses appropriate paths
- Development and production modes use separate cache locations
- Cache is preserved between application sessions

## Code Quality Reports

Code quality metrics and reports are available on SonarQube Cloud:

- **Dashboard**: [https://sonarcloud.io/project/overview?id=PovertyAction_datasure](https://sonarcloud.io/project/overview?id=PovertyAction_datasure)

The SonarQube dashboard provides insights into code coverage, code smells, bugs, vulnerabilities, and maintainability ratings.
