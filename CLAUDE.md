# CLAUDE.md

This file provides comprehensive guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **DataSure** - an IPA (Innovations for Poverty Action) Data Management System built with Python and Streamlit. It provides a web-based interface for data quality monitoring and high-frequency checks (HFCs) in survey data collection projects.

**Key Characteristics:**

- Modern Python package using src/ layout with uv_build backend
- Streamlit-based web application with sophisticated navigation
- Professional-grade build system with multi-platform distribution
- Comprehensive testing framework with pytest and extensive fixtures
- Code quality tooling with ruff, pre-commit hooks, and SonarQube integration

## Project Structure

```text
/
├── src/datasure/                   # Main package (source layout)
│   ├── __init__.py             # Package metadata (__version__ = "0.1.0")
│   ├── app.py                  # Main Streamlit application entry point
│   ├── cli.py                  # Command-line interface (datasure command)
│   ├── assets/                 # Static assets (logos, images) - 9 files
│   ├── checks/                 # 10 modular data quality check modules
│   ├── connectors/             # Data source connectors (SurveyCTO, local, scripts)
│   ├── processing/             # Data preparation and transformation utilities
│   ├── utils/                  # Shared utilities (charts, dataframes, settings, cache)
│   └── views/                  # Streamlit page components (6 view files)
├── tests/                      # Comprehensive pytest test suite
├── cache/                      # Project data and configuration storage (gitignored)
├── docs/                       # Documentation including PACKAGING.md
├── archived/                   # Legacy/experimental code (gitignored)
├── pyproject.toml             # Modern Python package configuration
├── Justfile                   # Cross-platform command runner
├── build.spec                 # PyInstaller configuration for Windows builds
└── CLAUDE.md                  # This file
```

## Development Commands

Run commands using `just` (cross-platform command runner):

### Environment Setup

```bash
just get-started          # Complete setup (install software + create venv)
just venv                 # Create virtual environment and install dependencies
just clean                # Remove virtual environment
```

### Development

```bash
uv run datasure                 # Launch application via CLI
just lab                     # Launch Jupyter Lab
```

### Code Quality

```bash
just lint-py              # Lint Python code with Ruff
just fmt-python           # Format Python code with Ruff
just fmt-all              # Format all code and markdown
just pre-commit-run        # Run pre-commit hooks manually
```

### Testing

```bash
just test                 # Run all tests
just test-cov             # Run tests with terminal coverage report
just test-cov-html        # Run tests with HTML coverage report
just test-cov-xml         # Run tests with XML coverage report (for CI)

# Specific test commands
uv run python -m pytest tests/checks/test_summary.py    # Run specific test file
uv run python -m pytest -k "test_missing"               # Run tests matching pattern
uv run python -m pytest --markers                       # Show available test markers
```

### Version Management & Git Tagging

```bash
# Alpha releases (pre-releases for early testing)
just bump-patch-alpha     # 0.1.0 -> 0.1.1a1
just bump-minor-alpha     # 0.1.0 -> 0.2.0a1
just bump-major-alpha     # 0.1.0 -> 1.0.0a1

# Beta releases (feature-complete pre-releases)
just bump-patch-beta      # 0.1.0 -> 0.1.1b1
just bump-minor-beta      # 0.1.0 -> 0.2.0b1
just bump-major-beta      # 0.1.0 -> 1.0.0b1

# Release candidates (final testing before release)
just bump-patch-rc        # 0.1.0 -> 0.1.1rc1
just bump-minor-rc        # 0.1.0 -> 0.2.0rc1
just bump-major-rc        # 0.1.0 -> 1.0.0rc1

# Final releases (automatically creates git tags)
just bump-patch           # 0.1.0 -> 0.1.1
just bump-minor           # 0.1.0 -> 0.2.0
just bump-major           # 0.1.0 -> 1.0.0

# Git tag management
just tag-version          # Create git tag for current version
just push-tag            # Push current version tag to remote
just push-all            # Push commits and tags to remote
```

**Cross-Platform Git Tagging:**
The Justfile includes platform-specific implementations for Windows (PowerShell), Linux, and macOS (bash) to ensure consistent git tagging behavior across all development environments.

### Package Building & Distribution

```bash
# Building
just build-package        # Build wheel and source distribution
just install-package      # Install package locally from built wheel
just test-cli             # Test CLI after installation
just package-workflow     # Complete workflow: test, build, and verify
just clean-build          # Clean build artifacts (dist/, build/)

# Version Management (using uv version command)
# Alpha releases
just bump-patch-alpha     # Bump patch version with alpha suffix (e.g., 0.1.1a1)
just bump-minor-alpha     # Bump minor version with alpha suffix (e.g., 0.2.0a1)
just bump-major-alpha     # Bump major version with alpha suffix (e.g., 1.0.0a1)

# Beta releases
just bump-patch-beta      # Bump patch version with beta suffix (e.g., 0.1.1b1)
just bump-minor-beta      # Bump minor version with beta suffix (e.g., 0.2.0b1)
just bump-major-beta      # Bump major version with beta suffix (e.g., 1.0.0b1)

# Release candidate releases
just bump-patch-rc        # Bump patch version with rc suffix (e.g., 0.1.1rc1)
just bump-minor-rc        # Bump minor version with rc suffix (e.g., 0.2.0rc1)
just bump-major-rc        # Bump major version with rc suffix (e.g., 1.0.0rc1)

# Final releases
just bump-patch           # Bump patch version (e.g., 0.1.0 -> 0.1.1)
just bump-minor           # Bump minor version (e.g., 0.1.0 -> 0.2.0)
just bump-major           # Bump major version (e.g., 0.1.0 -> 1.0.0)

# Publishing (requires credentials)
just publish-test # Publish to Test PyPI using uv publish
just publish      # Publish to PyPI using uv publish
```

## Package Architecture

### Modern Python Package Structure

- **Build System**: Hatchling (PEP 517/518 compliant)
- **Package Manager**: UV (fast Python package installer)
- **Layout**: src/ layout for better isolation and testing
- **Version Management**: Dynamic versioning from `src/datasure/__init__.py`
- **Entry Points**: CLI command `datasure` defined in pyproject.toml

### Core Application Components

#### Main Application (`src/datasure/app.py`)

- Streamlit multi-page application with dynamic navigation
- Session state management for complex UI interactions
- Asset management with package-aware path resolution
- Logo integration with fallback logic for development vs production

#### CLI Interface (`src/datasure/cli.py`)

- Argparse-based command-line interface
- Streamlit server integration with custom host/port
- Version reporting from package metadata
- Error handling for missing package files

#### Data Quality Checks (`src/datasure/checks/`)

**10 specialized check modules:**

1. `summary.py` - Overall data summary and progress tracking
2. `missing.py` - Missing data analysis and patterns
3. `duplicates.py` - Duplicate detection and analysis
4. `gpschecks.py` - GPS coordinate validation and mapping
5. `outliers.py` - Statistical outlier detection
6. `enumerator.py` - Enumerator performance analysis
7. `progress.py` - Survey progress monitoring
8. `descriptive.py` - Descriptive statistics and distributions
9. `backchecks.py` - Back-check validation workflows
10. `__init__.py` - Standardized interfaces for all checks

#### Data Connectors (`src/datasure/connectors/`)

- **SurveyCTO** (`scto.py`): Direct API integration with form metadata and authentication
- **Local Files** (`local.py`): CSV/Excel upload with automatic type detection
- **Custom Scripts** (`script.py`): Python script execution for data processing

#### Utilities (`src/datasure/utils/`)

- `cache_utils.py` - Cross-platform cache directory management
- `duckdb_utils.py` - DuckDB database operations and table management
- `chart_utils.py` - Plotly chart generation and styling
- `settings_utils.py` - JSON configuration management
- `dataframe_utils.py` - DataFrame manipulation utilities
- `metric_utils.py` - Statistical calculations and metrics

#### Views (`src/datasure/views/`)

- `start_view.py` - Project selection and creation interface
- `import_view.py` - Data import and connector management
- `prep_view.py` - Data preparation and cleaning workflows
- `config_view.py` - Check configuration and settings
- `correction_view.py` - Data correction workflows
- `output_view_1.py` - Report generation and visualization

## Key Development Patterns

### Session State Management

The application uses extensive Streamlit session state for:

- Multi-dataset support (up to 10 datasets per source type)
- Cross-page data persistence
- Dynamic navigation state
- Project configuration storage

**Key session state variables:**

- `st_project_id` - Current project identifier
- `st_load_project` - Project loading state
- `show_prep_section` - UI section visibility
- `st_prep_dataset_list` - List of prepared datasets
- Dataset storage with prefixes: `scto_1`, `local_1`, etc.

### Configuration System

- JSON-based configuration files stored in cache directories
- User-customizable check parameters and thresholds
- Project-specific settings with UUID-based organization
- Development vs production cache directory detection

### Asset Management

Assets are handled with package-aware paths:

```python
# Pattern used throughout the codebase
assets_dir = Path(__file__).parent.parent / "assets"
image_path = assets_dir / "filename.png"
st.image(str(image_path))
```

### Error Handling Patterns

- Comprehensive exception handling in data connectors
- User-friendly error messages in Streamlit UI
- Graceful degradation for missing dependencies
- Contextlib.suppress() for expected conversion failures

## Testing Framework

### Test Organization

```text
tests/
├── conftest.py                 # Shared fixtures and test configuration
├── checks/                     # Test modules for each check type
│   ├── test_summary.py
│   ├── test_missing.py
│   ├── test_duplicates.py
│   └── ...
├── processing/                 # Data processing tests
└── utils/                      # Utility function tests
```

### Key Testing Fixtures

Defined in `conftest.py`:

```python
@pytest.fixture
def sample_survey_data():
    """Realistic survey data with various data quality issues"""

@pytest.fixture
def gps_outlier_data():
    """GPS coordinates with known outliers for testing"""

@pytest.fixture
def mock_streamlit_session():
    """Mock Streamlit session state object"""

@pytest.fixture
def sample_missing_patterns():
    """Data with various missing value patterns"""
```

### Test Execution Patterns

- **Unit Tests**: Individual function testing with mocked dependencies
- **Integration Tests**: Multi-component testing with real data flows
- **UI Tests**: Streamlit component testing with session state mocking
- **Coverage Target**: Currently 16% minimum (needs improvement)

### Running Tests

```bash
# All tests
just test

# With coverage
just test-cov-html  # Opens browser with coverage report

# Specific test categories
uv run python -m pytest tests/checks/     # Only check tests
uv run python -m pytest -m "not slow"     # Skip slow tests
```

## Data Management System

### Cache Architecture

**Development Mode** (when `pyproject.toml` exists in current directory):

- Cache location: `./cache/`
- Direct access for debugging and development

**Production Mode** (when installed as package):

- Windows: `%APPDATA%/datasure/cache/`
- Linux/macOS: `~/.local/share/datasure/cache/`
- Automatic user data directory creation

**Cache Structure:**

```text
cache/
├── projects.json              # Project registry
├── {project_id}/              # Individual project data
│   ├── data/                  # DuckDB database files
│   └── settings/              # JSON configuration files
└── global_settings.json      # Application-wide settings
```

### Database Integration

- **DuckDB**: Primary data storage and analytical processing
- **Polars**: High-performance DataFrame operations for large datasets
- **Pandas**: Legacy compatibility and specific analysis functions

### Data Flow Pattern

1. **Import**: Connectors load data from various sources
2. **Preparation**: Data cleaning and transformation in processing modules
3. **Storage**: DuckDB persistence with table aliasing
4. **Analysis**: Check modules process data with configurable parameters
5. **Reporting**: View modules generate visualizations and reports

## Build System & Distribution

### Package Building

```bash
# Local development build
just build-package

# Install and test locally
just install-package
uv run datasure --version

# Complete workflow
just package-workflow  # Tests, builds, and verifies package
```

### Multi-Platform Distribution

#### PyPI Distribution

- **Standard Python Package**: `pip install DataSure`
- **Entry Point**: `datasure` command available globally
- **Version Management**: Automatic from `__init__.py`

#### Windows Distribution

- **PyInstaller Executable**: Standalone `.exe` with bundled Python
- **NSIS Installer**: Windows installer package
- **Winget Integration**: Windows Package Manager support
- **Automated Releases**: GitHub Actions build and publish

#### Development Distribution

- **Local Installation**: `uv pip install -e .` for development
- **Docker**: Potential containerization (not implemented)

### Build Configuration Files

#### `pyproject.toml`

Modern Python package configuration with:

- Build system specification (uv_build)
- Dependency management with optional groups
- Tool configuration (ruff, pytest, coverage)
- Package metadata and entry points

#### `build.spec`

PyInstaller configuration for Windows builds:

- Asset bundling and path resolution
- Dependency collection rules
- Executable metadata and icons

#### `Justfile`

Cross-platform command automation with platform-specific implementations:

- **Environment setup and management** (Windows/Linux/macOS variants)
- **Development workflow commands** (unified across platforms)
- **Build and distribution automation** (platform-aware Python/UV handling)
- **Platform-specific installation helpers** (winget/brew integration)

**Cross-Platform Compatibility Features:**

- Windows PowerShell recipes with proper command execution (`&` operator)
- Linux/macOS bash recipes with traditional shell syntax
- Platform-specific Python path resolution (`.venv/Scripts/` vs `.venv/bin/`)
- Conditional recipe execution based on OS detection (`[windows]`, `[linux]`, `[macos]`)
- Error suppression and output filtering for Windows compatibility (pytest-cov workarounds)

## Code Quality Standards

### Linting and Formatting

- **Ruff**: Modern, fast Python linter and formatter
- **Configuration**: Defined in pyproject.toml
- **Pre-commit Hooks**: Automatic formatting and linting
- **Line Length**: 88 characters (Black-compatible)

#### ⚠️ CRITICAL: Linting Requirements for Claude Code

**ALWAYS run linting checks before completing any coding task to prevent pre-commit hook failures:**

```bash
just lint-py              # Must pass with no errors
```

**Common linting errors to avoid:**

1. **F841 - Unused variables**: Remove or prefix with underscore

   ```python
   # Bad
   result = some_function()

   # Good - if not using result
   some_function()

   # Good - if intentionally unused
   _result = some_function()
   ```

2. **F811 - Redefinition**: Check for duplicate class/function names
3. **W505 - Line too long**: Keep lines ≤ 88 characters
4. **B007 - Unused loop variables**: Prefix with underscore

   ```python
   # Bad
   for item in items:
       process_something()

   # Good
   for _item in items:
       process_something()
   ```

5. **TRY301 - Abstract raise**: Move raise statements to helper functions

   ```python
   # Bad
   if condition:
       raise ValueError("Error")

   # Good
   def _handle_error():
       raise ValueError("Error")

   if condition:
       _handle_error()
   ```

**Mandatory workflow for code changes:**

1. Write/modify code
2. Run `just lint-py`
3. Fix any linting errors
4. Only then commit changes

**If linting fails:**

- Fix ALL errors before proceeding
- Never ignore linting errors
- Pre-commit hooks WILL block commits with linting violations

### Code Quality Checks

- **SonarQube Cloud**: Continuous code quality analysis
- **Coverage**: Pytest-cov with HTML and XML reporting
- **Type Hints**: Encouraged but not strictly enforced
- **Docstrings**: NumPy-style documentation

### Git Workflow & CI/CD Pipeline

- **Pre-commit Hooks**: Run automatically on commit
- **Branch Protection**: Required for main branch
- **Conventional Commits**: Encouraged for clear history
- **GitHub Actions**: Automated CI/CD pipeline with quality gates

#### Automated Release Pipeline

**Workflow Dependencies:**

1. **Code Coverage Workflow** (`.github/workflows/build.yml`)
   - Triggers: main branch pushes, tag pushes (`v*`), pull requests
   - Executes: pre-commit hooks, pytest suite, SonarQube analysis
   - **Quality Gate**: Must pass before releases proceed

2. **Build and Release Workflow** (`.github/workflows/build-and-release.yml`)
   - Triggers: Code Coverage workflow completion (workflow_run)
   - Conditions: Code Coverage succeeded AND triggered by tag push
   - Executes: package building, PyPI publishing, GitHub release creation

**Release Process:**

```bash
# Step 1: Create release with quality gate enforcement
just bump-patch              # Updates version, commits, creates tag

# Step 2: Push to trigger automated pipeline
just push-all                # Pushes commits and tags

# Step 3: GitHub Actions workflow sequence
# → Code Coverage runs first (tests + quality checks)
# → If successful → Build and Release runs automatically
# → Package built and published to PyPI
# → GitHub release created with artifacts
```

**Quality Gates Enforced:**

- Linting and formatting (Ruff)
- Test suite completion (pytest)
- Code quality analysis (SonarQube)
- Pre-commit hook validation

## Common Development Tasks

### Adding a New Data Quality Check

1. Create new module in `src/datasure/checks/`
2. Implement standardized interface with report function
3. Add imports to `src/datasure/checks/__init__.py`
4. Create corresponding test file in `tests/checks/`
5. Update navigation in `src/datasure/app.py` if needed

### Adding a New Data Connector

1. Create new module in `src/datasure/connectors/`
2. Implement data loading and form functions
3. Add imports to `src/datasure/connectors/__init__.py`
4. Update import view to include new connector
5. Add appropriate tests and documentation

### Modifying UI Components

1. Edit appropriate view file in `src/datasure/views/`
2. Use package-relative paths for assets
3. Follow session state patterns for data persistence
4. Test with different project configurations

### Package Version Updates & Automated Release

#### Version Bump Workflow (Automated)

1. **Choose appropriate version bump command:**
   - `just bump-patch` for bug fixes (0.1.0 → 0.1.1)
   - `just bump-minor` for new features (0.1.0 → 0.2.0)
   - `just bump-major` for breaking changes (0.1.0 → 1.0.0)
   - Add `-alpha`, `-beta`, or `-rc` suffix for pre-releases

2. **The command automatically performs:**
   - Updates `__version__` in `src/datasure/__init__.py`
   - Runs `uv sync` to update lock file with new version
   - Commits changes to git with descriptive message
   - Creates git tag for the new version (e.g., `v0.1.1`)

3. **Test locally before releasing:**

   ```bash
   just build-package        # Build the package
   uv run datasure --version # Verify version number
   just test                 # Run tests to ensure nothing broke
   ```

4. **Trigger automated release pipeline:**

   ```bash
   just push-all             # Push commits and tags to remote
   ```

5. **GitHub Actions handles the rest automatically:**
   - Runs Code Coverage workflow (quality gate)
   - If successful, runs Build and Release workflow
   - Builds and publishes package to PyPI
   - Creates GitHub release with artifacts

#### Manual Testing Workflow (Pre-Release)

For testing before automated release:

```bash
# 1. Create alpha/beta version for testing
just bump-patch-alpha

# 2. Test locally
just build-package
just install-package
uv run datasure --version

# 3. Test on TestPyPI (set UV_PUBLISH_TOKEN for test.pypi.org)
just publish-test

# 4. When ready for production, bump to final version
just bump-patch

# 5. Trigger automated release
just push-all
```

#### Emergency Manual Release

For bypassing quality gates in emergencies:

1. Go to GitHub Actions → "Build and Release" workflow
2. Click "Run workflow"
3. Enter version (e.g., `v1.0.1`)
4. Click "Run workflow" button

**Note:** Manual releases skip the Code Coverage quality gate and should only be used for critical hotfixes.

## Troubleshooting Common Issues

### Import Errors

- Use absolute imports: `from datasure.utils import ...`
- Check package structure matches import paths
- Verify `__init__.py` files exist in all directories

### Asset Path Issues

- Use package-relative paths: `Path(__file__).parent.parent / "assets"`
- Test both development and installed package scenarios
- Check asset files exist in expected locations

### Session State Problems

- Initialize all session state variables in app.py
- Use consistent naming patterns for dataset storage
- Clear browser cache if session state corruption occurs

### Build Issues

- Check all dependencies are listed in pyproject.toml
- Verify asset files are included in package builds
- Test both wheel and source distribution installations

### Test Failures

- Update test imports to use absolute package imports
- Mock Streamlit components properly in test fixtures
- Ensure test data matches expected formats and patterns

## Performance Considerations

### Large Dataset Handling

- Use Polars for memory-efficient operations
- Implement data chunking for massive datasets
- Consider DuckDB for analytical queries
- Monitor memory usage in Streamlit applications

### UI Responsiveness

- Use `st.cache_data()` for expensive computations
- Implement progress bars for long-running operations
- Consider lazy loading for large datasets
- Optimize chart generation and rendering

### Cache Management

- Implement cache size limits if needed
- Provide cache clearing utilities
- Monitor disk space usage in production
- Consider cache compression for large projects

## Security Considerations

### Data Handling

- Never commit sensitive data to version control
- Use environment variables for API credentials
- Implement proper input validation for file uploads
- Sanitize user inputs in configuration files

### Package Distribution

- Verify all builds before releasing
- Use trusted publishing for PyPI uploads
- Sign releases when possible
- Monitor for security vulnerabilities in dependencies

This comprehensive guide should help you navigate the DataSure codebase effectively and maintain its professional standards. The project follows modern Python best practices and provides multiple distribution channels for different user needs.
