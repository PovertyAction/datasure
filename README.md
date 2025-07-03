# pyDMS

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
uv run pydms                  # Launch the pyDMS application
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
    uv run pydms
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

pyDMS is set up as a proper Python package using [uv](https://docs.astral.sh/uv/) for building and publishing. This allows for easy distribution and installation.

### Building the Package

To build the package for distribution:

```bash
# Build both wheel and source distribution
just build-package

# Or use uv directly
uv build
```

This creates two files in the `dist/` directory:

- `pydms-{version}-py3-none-any.whl` (wheel distribution)
- `pydms-{version}.tar.gz` (source distribution)

### Testing the Package

To test the built package locally:

```bash
# Install the package locally
just install-package

# Or install directly from the wheel
uv pip install dist/pydms-*.whl
```

### Using the CLI

Once installed, you can use the command-line interface:

```bash
# Show version
uv run pydms --version

# Launch the dashboard (default: localhost:8501)
uv run pydms

# Launch with custom host/port
uv run pydms --host 0.0.0.0 --port 8080
```

### Package Development Workflow

1. **Make changes** to the code
2. **Update version** in `src/pydms/__init__.py`
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
   uv run pydms --version
   ```

### Version Management

The version number is stored in `src/pydms/__init__.py` and follows [semantic versioning](https://semver.org/):

- **MAJOR** version when you make incompatible API changes
- **MINOR** version when you add functionality in a backward compatible manner
- **PATCH** version when you make backward compatible bug fixes

To update the version:

1. **Edit the version in `src/pydms/__init__.py`**:

   ```python
   __version__ = "0.2.0"  # Update this line
   ```

2. **The build system automatically uses this version** when building packages via the hatch configuration in `pyproject.toml`:

   ```toml
   [tool.hatch.version]
   path = "src/pydms/__init__.py"
   ```

3. **Verify the version update**:

   ```bash
   uv build
   # Check that dist/ contains files with the new version number
   ```

### Publishing to PyPI

When ready to publish:

```bash
# Build the package
just build-package

# Publish to TestPyPI first (recommended)
just publish-test

# Publish to PyPI
just publish
```

**Note:** You'll need to configure your PyPI credentials before publishing. See [uv publishing documentation](https://docs.astral.sh/uv/guides/publish/) for details.

## Deployment

pyDMS can be deployed using [Ploomber Cloud](https://docs.cloud.ploomber.io/en/latest/intro.html). You will need a deployment key from [Ploomber's platform console](https://www.platform.ploomber.io/).

```bash
# make sure your venv is synced
uv sync

# set your Ploomber Cloud key locally
uv run ploomber-cloud key YOUR-KEY

# make sure that the requirements.txt file is up to date
uv pip compile pyproject.toml -o requirements.txt --no-annotate --no-header

# make sure that app.py is the same as pydms.py and deploy the app
# Ploomber needs to use app.py as the entry point for the Streamlit app
cd src/pydms && uv run ploomber-cloud deploy --watch
```

See Ploomber docs for more details on deployment options and configurations of [Streamlit apps](https://docs.cloud.ploomber.io/en/latest/apps/streamlit.html). Password protection docs are found in [Ploomber docs](https://docs.cloud.ploomber.io/en/latest/user-guide/cli.html#password-protection).

## Data Storage and Cache

pyDMS automatically manages data storage and caching for optimal performance across different environments:

### Cache Directory Locations

- **Development Mode** (when running from source): `./cache/` (in project root)
- **Production Mode** (when installed as package):
  - **Windows**: `%APPDATA%/pydms/cache/`
  - **Linux/macOS**: `~/.local/share/pydms/cache/`

### What's Stored

The cache directory contains:

- **Project configurations**: HFC page settings and form configurations
- **Database files**: DuckDB databases for processed survey data
- **SurveyCTO cache**: Cached form metadata and server connections
- **User settings**: Check configurations and preferences

### Cache Management

- Cache directories are created automatically when needed
- No manual setup required - pyDMS detects the environment and uses appropriate paths
- Development and production modes use separate cache locations
- Cache is preserved between application sessions

## Code Quality Reports

Code quality metrics and reports are available on SonarQube Cloud:

- **Dashboard**: [https://sonarcloud.io/project/overview?id=PovertyAction_pydms](https://sonarcloud.io/project/overview?id=PovertyAction_pydms)

The SonarQube dashboard provides insights into code coverage, code smells, bugs, vulnerabilities, and maintainability ratings.
