# Contributing to DataSure

Thank you for your interest in contributing to DataSure! This guide will help you get started with development and contributing to the project.

## Table of Contents

- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Dependency Management](#dependency-management)
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

### Error Handling Conventions

Bare `except:` is never allowed (Ruff `E722` is enforced). Catch the most
specific exception the code can actually raise, and follow these rules:

1. **Library and utility code** (`utils/`, `processing/`, `checks/`): catch
   specific exceptions only (`OSError`, `ValueError`, `pl.exceptions.PolarsError`,
   `duckdb.Error`, etc.). Never silently swallow an exception - log it with a
   module logger (`logger = logging.getLogger(__name__)`) before returning a
   fallback value.

2. **Domain-error translation**: when wrapping arbitrary lower-level failures
   in a domain exception (e.g. `OperationError` in `processing/prep.py`),
   re-raise known domain exceptions first, then translate the rest:

   ```python
   except (ValidationError, OperationError):
       raise
   except Exception as e:
       raise OperationError(f"Failed to remove columns: {e}") from e
   ```

   Always chain with `from e` so the original traceback is preserved.

3. **UI boundaries** (Streamlit button callbacks, per-item loops where one
   failure must not abort the batch or crash the page): a broad
   `except Exception` is acceptable *only* here, and it must both log the full
   traceback (`logger.exception(...)`) and show the user a message
   (`st.error(...)`). Add a short comment marking the boundary.

4. **Streamlit control flow**: never call `st.rerun()` inside a `try` block
   with a broad except - it raises a control-flow exception that the handler
   would swallow. Put it in the `else:` clause instead.

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

## Dependency Management

DataSure declares dependencies in `pyproject.toml` and locks exact versions
in `uv.lock`. Three places matter:

- **`[project.dependencies]`** - packages DataSure imports directly. These
  are install requirements of the published package.
- **`[dependency-groups].dev`** - development tooling (PEP 735). Never
  shipped with the package.
- **`[tool.uv] constraint-dependencies`** - security version floors for
  transitive packages DataSure does *not* import (they are pulled in by
  streamlit, requests, matplotlib, keyring, etc.). Constraints steer
  dependency resolution but are not install requirements, so they never
  leak into the published package metadata.

For routine (non-security) refreshes, `just update-reqs` re-locks everything
to the latest compatible versions.

### Responding to a Dependabot Alert

When an alert flags a vulnerable package, work through this decision tree:

1. **Upgrade the lock first - this is the actual remediation:**

   ```bash
   uv lock --upgrade-package <package>
   uv sync
   just test
   ```

   `uv.lock` controls what developers and CI actually install. If the
   resolver reaches the fixed version, the alert closes once this merges.

2. **Add a version floor so a future re-lock cannot regress.** Where the
   floor goes depends on whether DataSure imports the package - check with
   `uv tree --invert --package <package>` and grep `src/datasure/`:

   - **Transitive** (not imported): add or raise its floor in
     `[tool.uv] constraint-dependencies`, e.g. `"pillow>=12.2.0"`. Do
     **not** add transitive packages to `[project.dependencies]` - pins
     there become install requirements of the published package and rot
     once the CVE is forgotten.
   - **Direct** (imported in `src/datasure/`): raise its floor in
     `[project.dependencies]` instead, with a short comment naming the
     reason. This also protects users who install DataSure from PyPI.

   Re-run `uv lock` after editing and commit `pyproject.toml` + `uv.lock`
   together.

3. **If the resolver cannot reach the fixed version**, a parent package is
   capping it (for example, streamlit pinning protobuf below the fix).
   Upgrading the parent is the real fix: `uv lock --upgrade-package
   <parent>`, or raise the parent's floor. Adding a conflicting constraint
   only makes resolution fail - acceptable temporarily to keep the problem
   loud, but remove it if you need to cut a release before the parent ships
   a fix.

4. **Verify**: run the full test suite (a vulnerable-version bump can be a
   major-version bump), and after merging confirm the alert closes under
   GitHub Security -> Dependabot.

In short: the lock upgrade remediates today; the floor (constraint for
transitive, `[project.dependencies]` for direct) prevents regression
tomorrow. A security fix usually needs both.

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

Releases are normally published by CI via PyPI Trusted Publishing when a
version tag is pushed. The recipes below are manual escape hatches and
require `UV_PUBLISH_TOKEN` to be set:

```bash
just publish-test         # Clean build + publish to TestPyPI
just publish              # Clean build + publish to PyPI (production)
just verify-published     # Install latest from PyPI and run datasure --version
```

## Version Management

DataSure uses automated version management with semantic versioning (MAJOR.MINOR.PATCH).

### Version Bump Commands

Version bumps use [`uv version --bump`](https://docs.astral.sh/uv/guides/package/)
under the hood. Stages can be combined, and `stable` finalizes a pre-release.

#### Releases (bump + commit + tag)

```bash
just bump-patch            # 0.1.0  -> 0.1.1
just bump-minor            # 0.1.0  -> 0.2.0
just bump-major            # 0.1.0  -> 1.0.0
just bump-pre patch rc     # 0.1.0  -> 0.1.1rc1 (stages: alpha, beta, rc)
just bump-pre minor beta   # 0.1.0  -> 0.2.0b1
just bump-stable           # 1.0.0rc1 -> 1.0.0 (finalize a pre-release)
```

These commands automatically:

- Verify CHANGELOG.md has entries under `[Unreleased]` (release gate)
- Update the version in `pyproject.toml`
- Run `uv sync` to update the lock file
- Commit `pyproject.toml` and `uv.lock`
- Create a git tag for the new version (pushing the tag triggers the
  release pipeline)

#### Version-only bump (no commit, no tag)

```bash
just bump patch            # any `uv version --bump` stage, combinable
just bump minor rc
just bump stable
```

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

# 4. Monitor the Release workflow in GitHub Actions
# - The tag push triggers .github/workflows/release.yml, which runs:
#   test (pre-commit + pytest) -> build and verify -> publish -> GitHub release
# - The build job fails if the tag does not match the pyproject.toml version
# - Pre-releases (a/b/rc/dev suffixes) publish to Test PyPI;
#   final X.Y.Z versions publish to PyPI
# - Publishing uses PyPI Trusted Publishing (OIDC) - no API tokens
```

### Quality Gates

All releases must pass (enforced by the `test` and `build` jobs in release.yml):

- **Pre-commit hooks**: Code formatting and linting
- **Test suite**: All tests must pass
- **Version consistency**: Git tag must match the version in pyproject.toml
- **Wheel smoke test**: Built wheel installs cleanly and `datasure --version` works
- **Documentation completeness**: Both CHANGELOG.md and RELEASENOTES.md updated

SonarQube analysis runs on every push to main via the Code Coverage workflow.
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

1. Go to GitHub Actions → Release → Run workflow
2. Enter the version (e.g., `v1.0.1`) and click "Run workflow"
3. The version must match `pyproject.toml` on the selected branch; the build
   job fails otherwise. Manual runs publish to PyPI/Test PyPI but do not
   create a GitHub release (that requires a tag push).
4. **Note**: Manual releases should still update documentation post-release

## Submitting Changes

### Workflow for Contributors

1. **Review the roadmap**: Check [ROADMAP.md](ROADMAP.md) to understand current priorities and avoid duplicating in-progress work
2. **Fork the repository** and create a feature branch
3. **Make your changes** following the coding standards
4. **Write or update tests** for your changes
5. **Run the full test suite**:

   ```bash
   just test
   just lint-py
   ```

6. **Build and test the package**:

   ```bash
   just package-workflow
   ```

7. **Commit your changes** with descriptive commit messages
8. **Push to your fork** and create a pull request

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

By participating in this project, you agree to abide by our Code of Conduct ([CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)). Please treat all contributors with respect and create a welcoming environment for everyone.

---

Thank you for contributing to DataSure! Your contributions help improve data quality monitoring for survey research worldwide.
