# Contributing to DataSure

Thank you for your interest in contributing to DataSure! This guide will help you get started with development and contributing to the project.

## Table of Contents

- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Package Building](#package-building)
- [Version Management](#version-management)
- [Release Process](#release-process)
- [Submitting Changes](#submitting-changes)

## Development Setup

### Prerequisites

Development requires the following software:

- `winget` (Windows) or `homebrew` (MacOS/Linux) for package management
- `git` for source control management
- `just` for running common command line patterns
- `uv` for installing Python and managing virtual environments

### Installation Commands

| Platform  | Commands                                                            |
| --------- | ------------------------------------------------------------------- |
| Windows   | `winget install Git.Git Casey.Just astral-sh.uv GitHub.cli` |
| Mac/Linux | `brew install just uv gh`                                          |

### Quick Start

```bash
# Clone the repository
git clone https://github.com/PovertyAction/datasure.git
cd datasure

# Complete setup (install software + create venv)
just get-started

# Alternatively, create environment manually
just venv
```

**Note:** You may need to restart your terminal after installation to activate the software.

### Virtual Environment Activation

| Shell      | Commands                                |
| ---------- | --------------------------------------- |
| Bash       | `.venv/Scripts/activate`                |
| Powershell | `.venv/Scripts/activate.ps1`            |
| Nushell    | `overlay use .venv/Scripts/activate.nu` |

## Development Workflow

### Environment Management

```bash
just venv                 # Create virtual environment and install dependencies
just clean                # Remove virtual environment
just activate-venv        # Activate the virtual environment
```

### Running the Application

```bash
uv run datasure                  # Launch the DataSure application
just lab                     # Launch Jupyter Lab
```

### Code Quality

DataSure maintains high code quality standards. Always run these commands before committing:

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

**⚠️ CRITICAL:** Always run `just lint-py` before committing. Pre-commit hooks will block commits with linting violations.

### Common Linting Issues to Avoid

1. **F841 - Unused variables**: Remove or prefix with underscore
2. **F811 - Redefinition**: Check for duplicate class/function names
3. **W505 - Line too long**: Keep lines ≤ 88 characters
4. **B007 - Unused loop variables**: Prefix with underscore
5. **TRY301 - Abstract raise**: Move raise statements to helper functions

## Testing

DataSure uses pytest for testing with comprehensive coverage requirements.

### Running Tests

```bash
just test                 # Run all tests
just test-cov             # Run tests with coverage report (terminal)
just test-cov-html        # Run tests with HTML coverage report
just test-cov-xml         # Run tests with XML coverage report (for CI)
```

### Specific Test Commands

```bash
uv run python -m pytest tests/checks/test_summary.py    # Run specific test file
uv run python -m pytest -k "test_missing"               # Run tests matching pattern
uv run python -m pytest --markers                       # Show available test markers
```

### Test Structure

```text
tests/
├── conftest.py                 # Shared fixtures and test configuration
├── checks/                     # Test modules for each check type
├── processing/                 # Data processing tests
└── utils/                      # Utility function tests
```

## Package Building

### Building Commands

```bash
just build-package        # Build both wheel and source distribution
just clean-build          # Clean build artifacts
just install-package      # Install the package locally from built wheel
just uninstall-package    # Uninstall the package
just test-cli             # Test the CLI after installation
just package-workflow     # Complete workflow: test, build, and verify
```

### Publishing Commands

```bash
just check-pypi           # Check package metadata and structure
just pypi-info            # View package info and version
just publish-test         # Publish to TestPyPI (for testing)
just publish              # Publish to PyPI (production)
```

## Version Management

DataSure uses automated version management with semantic versioning (MAJOR.MINOR.PATCH).

### Version Bump Commands

#### Alpha Releases (Early Development Testing)

```bash
just bump-patch-alpha     # 0.1.0 -> 0.1.1a1
just bump-minor-alpha     # 0.1.0 -> 0.2.0a1
just bump-major-alpha     # 0.1.0 -> 1.0.0a1
```

#### Beta Releases (Feature-Complete Testing)

```bash
just bump-patch-beta      # 0.1.0 -> 0.1.1b1
just bump-minor-beta      # 0.1.0 -> 0.2.0b1
just bump-major-beta      # 0.1.0 -> 1.0.0b1
```

#### Release Candidates (Final Testing)

```bash
just bump-patch-rc        # 0.1.0 -> 0.1.1rc1
just bump-minor-rc        # 0.1.0 -> 0.2.0rc1
just bump-major-rc        # 0.1.0 -> 1.0.0rc1
```

#### Final Releases

```bash
just bump-patch           # 0.1.0 -> 0.1.1
just bump-minor           # 0.1.0 -> 0.2.0
just bump-major           # 0.1.0 -> 1.0.0
```

These commands automatically:

- Update the version in `src/datasure/__init__.py`
- Run `uv sync` to update the lock file
- Commit the changes to git
- Create a git tag for the new version

### Git Tag Management

```bash
just tag-version          # Create git tag for current version
just push-tag            # Push the current version tag
just push-all            # Push both commits and tags
```

## Release Process

DataSure uses an automated GitHub Actions pipeline for releases with comprehensive documentation management.

### Documentation Updates

Before making any release, developers must update both technical and user-facing documentation:

#### Technical Changelog (CHANGELOG.md)

- Use [docs/changelog_guide.md](docs/changelog_guide.md) for guidance
- Include technical implementation details, API changes, dependency updates
- Reference specific modules and functions (e.g., `src/datasure/checks/gpschecks.py:123`)
- Provide migration instructions for breaking changes
- Include performance metrics and code examples

#### User-Facing Release Notes (RELEASENOTES.md)

- Use [docs/release_notes_guide.md](docs/release_notes_guide.md) for guidance
- Focus on user benefits and workflow improvements
- Use plain language familiar to data managers and survey coordinators
- Describe features in terms of data quality outcomes
- Avoid technical jargon and implementation details

### Automated Release Steps

```bash
# 1. Update documentation first
# - Add entries to CHANGELOG.md (technical details)
# - Update RELEASENOTES.md (user-facing content)
# - Follow guidelines in docs/changelog_guide.md and docs/release_notes_guide.md

# 2. Create release (triggers quality gate)
just bump-patch  # Creates git tag

# 3. Push to trigger automation
just push-all    # Pushes commits and tags

# 4. Monitor workflows in GitHub Actions
# - Code Coverage runs first (quality gate)
# - Build and Release runs only if Code Coverage passes
# - Package published to PyPI automatically
# - GitHub release created with artifacts
```

### Quality Gates

All releases must pass:

- **Pre-commit hooks**: Code formatting and linting
- **Test suite**: All tests must pass
- **SonarQube analysis**: Code quality and security checks
- **Documentation completeness**: Both CHANGELOG.md and RELEASENOTES.md updated

Failed quality checks prevent releases.

### Documentation Review Process

1. **Technical Review**: Verify CHANGELOG.md entries follow [docs/changelog_guide.md](docs/changelog_guide.md)
   - Include specific module/file references
   - Provide migration instructions for breaking changes
   - Add performance metrics where applicable

2. **User Experience Review**: Verify RELEASENOTES.md follows [docs/release_notes_guide.md](docs/release_notes_guide.md)
   - Use language familiar to data managers
   - Focus on user benefits and workflow improvements
   - Include installation and setup instructions

### Manual Release Override

For emergency releases only:

1. Go to GitHub Actions → Build and Release → Run workflow
2. Enter version (e.g., `v1.0.1`) and click "Run workflow"
3. **Note**: Manual releases should still update documentation post-release

## Submitting Changes

### Workflow for Contributors

1. **Fork the repository** and create a feature branch
2. **Make your changes** following the coding standards
3. **Write or update tests** for your changes
4. **Run the full test suite**:

   ```bash
   just test
   just lint-py
   ```

5. **Build and test the package**:

   ```bash
   just package-workflow
   ```

6. **Commit your changes** with descriptive commit messages
7. **Push to your fork** and create a pull request

### Pull Request Guidelines

- **Title**: Use clear, descriptive titles
- **Description**: Explain what changes you made and why
- **Tests**: Include tests for new functionality
- **Documentation**: Update documentation if needed
- **Linting**: Ensure all linting checks pass

### Code Review Process

- All pull requests require review before merging
- Address reviewer feedback promptly
- Keep pull requests focused and reasonably sized
- Ensure CI/CD checks pass before requesting review

## Development Architecture

### Project Structure

```text
src/datasure/                   # Main package (source layout)
├── app.py                  # Main Streamlit application entry point
├── cli.py                  # Command-line interface
├── checks/                 # 10 modular data quality check modules
├── connectors/             # Data source connectors
├── processing/             # Data preparation utilities
├── utils/                  # Shared utilities
└── views/                  # Streamlit page components
```

### Key Patterns

- **Session State Management**: Extensive use of Streamlit session state
- **Configuration System**: JSON-based configuration files
- **Asset Management**: Package-aware path resolution
- **Error Handling**: Comprehensive exception handling

### Adding New Features

#### Adding a New Data Quality Check

1. Create new module in `src/datasure/checks/`
2. Implement standardized interface with report function
3. Add imports to `src/datasure/checks/__init__.py`
4. Create corresponding test file in `tests/checks/`
5. Update navigation in `src/datasure/app.py` if needed

#### Adding a New Data Connector

1. Create new module in `src/datasure/connectors/`
2. Implement data loading and form functions
3. Add imports to `src/datasure/connectors/__init__.py`
4. Update import view to include new connector
5. Add appropriate tests and documentation

## Getting Help

- **Documentation**: Check the [CLAUDE.md](CLAUDE.md) file for comprehensive development guidance
- **Issues**: Report bugs or request features on GitHub Issues
- **Discussions**: Use GitHub Discussions for questions and ideas
- **Code Quality**: Monitor [SonarQube Dashboard](https://sonarcloud.io/project/overview?id=PovertyAction_datasure)

## Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct. Please treat all contributors with respect and create a welcoming environment for everyone.

---

Thank you for contributing to DataSure! Your contributions help improve data quality monitoring for survey research worldwide.
