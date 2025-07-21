# CLAUDE.md

This file provides comprehensive guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **pyDMS** - an IPA (Innovations for Poverty Action) Data Management System built with Python and Streamlit. It provides a web-based interface for data quality monitoring and high-frequency checks (HFCs) in survey data collection projects.

**Key Characteristics:**

- Modern Python package using src/ layout with uv_build backend
- Streamlit-based web application with sophisticated navigation
- Professional-grade build system with multi-platform distribution
- Comprehensive testing framework with pytest and extensive fixtures
- Code quality tooling with ruff, pre-commit hooks, and SonarQube integration

## Project Structure

```text
/
├── src/pydms/                   # Main package (source layout)
│   ├── __init__.py             # Package metadata (__version__ = "0.1.0")
│   ├── app.py                  # Main Streamlit application entry point
│   ├── cli.py                  # Command-line interface (pydms command)
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
uv run pydms                 # Launch application via CLI
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

### Package Building & Distribution

```bash
just build-package        # Build wheel and source distribution
just install-package      # Install package locally from built wheel
just test-cli             # Test CLI after installation
just package-workflow     # Complete workflow: test, build, and verify

# Publishing (requires credentials)
just publish-test         # Publish to TestPyPI
just publish              # Publish to PyPI

# Release workflow
just release-windows 0.1.0  # Shows deprecation message for Windows builds
```

## Package Architecture

### Modern Python Package Structure

- **Build System**: Hatchling (PEP 517/518 compliant)
- **Package Manager**: UV (fast Python package installer)
- **Layout**: src/ layout for better isolation and testing
- **Version Management**: Dynamic versioning from `src/pydms/__init__.py`
- **Entry Points**: CLI command `pydms` defined in pyproject.toml

### Core Application Components

#### Main Application (`src/pydms/app.py`)

- Streamlit multi-page application with dynamic navigation
- Session state management for complex UI interactions
- Asset management with package-aware path resolution
- Logo integration with fallback logic for development vs production

#### CLI Interface (`src/pydms/cli.py`)

- Argparse-based command-line interface
- Streamlit server integration with custom host/port
- Version reporting from package metadata
- Error handling for missing package files

#### Data Quality Checks (`src/pydms/checks/`)

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

#### Data Connectors (`src/pydms/connectors/`)

- **SurveyCTO** (`scto.py`): Direct API integration with form metadata and authentication
- **Local Files** (`local.py`): CSV/Excel upload with automatic type detection
- **Custom Scripts** (`script.py`): Python script execution for data processing

#### Utilities (`src/pydms/utils/`)

- `cache_utils.py` - Cross-platform cache directory management
- `duckdb_utils.py` - DuckDB database operations and table management
- `chart_utils.py` - Plotly chart generation and styling
- `settings_utils.py` - JSON configuration management
- `dataframe_utils.py` - DataFrame manipulation utilities
- `metric_utils.py` - Statistical calculations and metrics

#### Views (`src/pydms/views/`)

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

- Windows: `%APPDATA%/pydms/cache/`
- Linux/macOS: `~/.local/share/pydms/cache/`
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
uv run pydms --version

# Complete workflow
just package-workflow  # Tests, builds, and verifies package
```

### Multi-Platform Distribution

#### PyPI Distribution

- **Standard Python Package**: `pip install pyDMS`
- **Entry Point**: `pydms` command available globally
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

Cross-platform command automation:

- Environment setup and management
- Development workflow commands
- Build and distribution automation
- Platform-specific installation helpers

## Code Quality Standards

### Linting and Formatting

- **Ruff**: Modern, fast Python linter and formatter
- **Configuration**: Defined in pyproject.toml
- **Pre-commit Hooks**: Automatic formatting and linting
- **Line Length**: 88 characters (Black-compatible)

### Code Quality Checks

- **SonarQube Cloud**: Continuous code quality analysis
- **Coverage**: Pytest-cov with HTML and XML reporting
- **Type Hints**: Encouraged but not strictly enforced
- **Docstrings**: NumPy-style documentation

### Git Workflow

- **Pre-commit Hooks**: Run automatically on commit
- **Branch Protection**: Required for main branch
- **Conventional Commits**: Encouraged for clear history
- **GitHub Actions**: CI/CD pipeline for testing and building

## Common Development Tasks

### Adding a New Data Quality Check

1. Create new module in `src/pydms/checks/`
2. Implement standardized interface with report function
3. Add imports to `src/pydms/checks/__init__.py`
4. Create corresponding test file in `tests/checks/`
5. Update navigation in `src/pydms/app.py` if needed

### Adding a New Data Connector

1. Create new module in `src/pydms/connectors/`
2. Implement data loading and form functions
3. Add imports to `src/pydms/connectors/__init__.py`
4. Update import view to include new connector
5. Add appropriate tests and documentation

### Modifying UI Components

1. Edit appropriate view file in `src/pydms/views/`
2. Use package-relative paths for assets
3. Follow session state patterns for data persistence
4. Test with different project configurations

### Package Version Updates

1. Update `__version__` in `src/pydms/__init__.py`
2. Test package building: `just build-package`
3. Verify CLI version: `uv run pydms --version`
4. Update documentation if API changes

## Troubleshooting Common Issues

### Import Errors

- Use absolute imports: `from pydms.utils import ...`
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

This comprehensive guide should help you navigate the pyDMS codebase effectively and maintain its professional standards. The project follows modern Python best practices and provides multiple distribution channels for different user needs.
