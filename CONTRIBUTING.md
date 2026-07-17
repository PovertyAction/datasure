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

| Platform  | Commands                                                                          |
| --------- | --------------------------------------------------------------------------------- |
| Windows   | `winget install Git.Git Casey.Just astral-sh.uv GitHub.cli OpenJS.NodeJS`, then `npm install -g markdownlint-cli2` |
| Mac/Linux | `brew install just uv gh markdownlint-cli2`                                       |

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
just activate-venv        # Print the activation command for your shell
```

### Running the Application

```bash
uv run datasure                  # Launch the DataSure application (via CLI entry point)
just datasure-dev                # Launch via streamlit run on the source tree (dev mode)
just lab                         # Launch Jupyter Lab
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

**⚠️ CRITICAL:** Always run `just lint-py` **and** `just fmt-python` before committing. CI enforces both linting and formatting — a commit can pass linting and still fail CI on formatting. Run `just pre-commit-run` to catch both at once.

### Common Linting Issues to Avoid

1. **F841 - Unused variables**: Remove or prefix with underscore
2. **F811 - Redefinition**: Check for duplicate class/function names
3. **E501 - Line too long**: Keep lines ≤ 88 characters
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
├── checks/                     # Tests for each data quality check module
├── connectors/                 # Tests for data source connectors
├── data/                       # Sample data files used by tests
├── models/                     # Tests for Pydantic schemas and enums
├── processing/                 # Tests for data preparation and corrections
├── replication/                # Tests for replication package generation
├── utils/                      # Tests for utility functions
└── views/                      # Tests for Streamlit page scripts
```

### Optional: Validating replication data dictionaries

The replication package builder (`src/datasure/replication/`) generates a
`data-dict.yaml` file for each exported dataset, following the
[data-dict.yaml spec](https://data-dict.tidyverse.org/). Validating it
against the spec — and, more thoroughly, against the actual Parquet files it
describes — requires the `data-dict` CLI
(<https://github.com/tidyverse/data-dict>), a Rust tool.

This is entirely optional and outside the normal Python/uv toolchain: it is
**not** installed in CI, and the corresponding pytest tests
(`tests/replication/test_data_dict_cli.py`) automatically skip when the CLI
isn't found on `PATH`. Install it if you're working on `data_dict.py` or want
to double-check a generated package by hand.

**1. Install Rust**, if you don't already have it, via
[rustup](https://rustup.rs):

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

On Windows, use the [rustup-init.exe installer](https://rustup.rs) instead of
the shell script above. Or install via `winget`:

```bash
winget install --id Rustlang.Rustup
```

**2. Install the data-dict CLI** with Cargo:

```bash
cargo install --git https://github.com/tidyverse/data-dict data-dict-cli
```

This places a `data-dict` binary in `~/.cargo/bin` — make sure that
directory is on your `PATH`. Confirm it worked with `data-dict --help`.

**3. Run the validation tests** (they run for real now that the CLI is
installed, instead of skipping):

```bash
uv run python -m pytest tests/replication/test_data_dict_cli.py -v
```

**4. Validate an exported package by hand**, if needed:

```bash
data-dict validate-spec path/to/replication_.../1_docs/2_codebooks/data-dict.yaml
data-dict validate-meta path/to/replication_.../1_docs/2_codebooks/data-dict.yaml
data-dict validate-data path/to/replication_.../1_docs/2_codebooks/data-dict.yaml
```

`validate-spec` checks only the yaml file against the spec; `validate-meta`
additionally checks that the referenced Parquet file's column names/types
match; `validate-data` additionally checks that the actual values (ranges,
enum membership, etc.) match what's declared.

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

# 2. Run the bump recipe locally — this commits pyproject.toml + uv.lock and
#    creates a git tag. NOTE: main is branch-protected, so the commit cannot
#    be pushed directly.
just bump-patch  # or bump-minor, bump-major, bump-pre, bump-stable

# 3. Move the bump commit to a branch and open a PR
#    (the bump recipe commits to your local main; branch protection blocks
#    pushing it directly)
git checkout -b release/vX.Y.Z
git checkout main && git reset --hard origin/main
git checkout release/vX.Y.Z
git push -u origin release/vX.Y.Z
# Open a PR and merge it via GitHub

# 4. After the PR merges, pull main and push the tag to trigger automation
git checkout main && git pull
git tag -a vX.Y.Z -m "Version X.Y.Z"
git push origin vX.Y.Z

# 5. Monitor the Release workflow in GitHub Actions
# - The tag push triggers .github/workflows/release.yml, which runs:
#   test (pre-commit + pytest) -> build and verify -> publish -> GitHub release
# - The build job fails if the tag does not match the pyproject.toml version
# - Pre-releases (a/b/rc/dev suffixes) publish to Test PyPI;
#   final X.Y.Z versions publish to PyPI
# - Publishing uses PyPI Trusted Publishing (OIDC) - no API tokens
```

### Verifying a Pre-release from Test PyPI

After a pre-release tag (e.g. `v1.0.0rc1`) is pushed and the Release workflow
publishes to Test PyPI, **developers should install and test the published
package before approving the final stable release**. This catches packaging
issues (missing files, broken entry points, bad metadata) that the test suite
alone cannot detect.

```bash
# Install the pre-release from Test PyPI
# Dependencies are resolved from PyPI; the datasure package itself comes
# from Test PyPI.
uv tool install "datasure==X.Y.ZrcN" \
    --index https://test.pypi.org/simple/ \
    --index https://pypi.org/simple/

# Verify the entry point and version
datasure --version

# Smoke-test the application
datasure
```

**What to verify:**

- `datasure --version` reports the correct pre-release version
- The application launches without import errors
- The demo project loads and all nine check pages render correctly
- SurveyCTO connection and local file import work end-to-end on a real project
- The replication package export completes without errors

Only proceed to the final stable release (pushing a `vX.Y.Z` tag without a
pre-release suffix) once at least one developer has confirmed the above on
the Test PyPI build.

### Quality Gates

All releases must pass (enforced by the `test` and `build` jobs in release.yml):

- **Pre-commit hooks**: Code formatting and linting
- **Test suite**: All tests must pass
- **Version consistency**: Git tag must match the version in pyproject.toml
- **Wheel smoke test**: Built wheel installs cleanly and `datasure --version` works
- **Documentation completeness**: Both CHANGELOG.md and RELEASENOTES.md updated

SonarQube analysis runs on every push to main via the Code Coverage workflow.
Failed quality checks prevent releases.

### Release Security

The release pipeline is hardened following
[publishing-to-PyPI best practices](https://snarky.ca/how-to-publish-to-pypi-using-github-actions-securely/):

- **Trusted Publishing (OIDC)**: no PyPI API tokens; the `testpypi`/`pypi`
  GitHub environments are registered as trusted publishers on
  Test PyPI/PyPI.
- **zizmor**: GitHub Actions workflows are statically analyzed by the
  `zizmor` pre-commit hook (runs locally and in CI). Run it directly with
  `uvx zizmor .github/workflows/`.
- **SHA-pinned actions**: all `uses:` references are pinned to full commit
  SHAs with a version comment. Dependabot updates the pins on a 7-day
  cooldown (`.github/dependabot.yml`). When adding an action, pin its SHA.
- **Minimal permissions**: workflows start from `permissions: {}` (or
  `contents: read`); each job requests only what it needs, and checkouts
  use `persist-credentials: false`.
- **No caching in release jobs**: the Release workflow disables the uv
  cache so a poisoned cache cannot influence published artifacts.

Repository settings (maintainers, not enforceable in code):

- Add **required reviewers** to the `pypi` environment
  (Settings → Environments → pypi) so final releases need a manual
  approval even after a tag push; optionally do the same for `testpypi`.
- Optionally enable **"Require actions to be pinned to a full-length
  commit SHA"** (Settings → Actions → General).

#### Trusted Publishing configuration (and what to change if release.yml changes)

Trusted Publishing works by GitHub sending Test PyPI/PyPI an OIDC token
whose claims must **exactly match** a publisher registered on the index.
There are no API tokens; the match is the entire authentication. Test PyPI
and PyPI are separate accounts and separate registries — a publisher on one
does nothing for the other, so both must be configured independently.

Each publisher is registered against four values that come straight from
`.github/workflows/release.yml`:

| Publisher field   | Source in release.yml                          | Current value          |
| ----------------- | ---------------------------------------------- | ---------------------- |
| Owner             | repository owner                               | `PovertyAction`        |
| Repository        | repository name                                | `datasure`             |
| Workflow name     | the workflow **filename only** (no path)       | `release.yml`          |
| Environment name  | `environment:` on the publish job              | `testpypi` / `pypi`    |

The publish jobs are `publish-testpypi` (`environment: testpypi`, publishes
pre-releases to Test PyPI) and `publish-pypi` (`environment: pypi`, publishes
final releases to PyPI). The environment name is **case-sensitive** and must
match the registered publisher character-for-character.

**If you change any of these in `release.yml`, you must update the matching
publisher on BOTH Test PyPI and PyPI before the next release, or publishing
fails with `invalid-publisher: valid token, but no corresponding publisher`.**
Changes that require re-registering the publisher include:

- Renaming or moving `release.yml` (the workflow filename is a claim).
- Changing an `environment:` name on a publish job.
- Renaming or transferring the repository, or changing its owner.

To register or update a publisher:

- **Test PyPI** (for pre-releases): <https://test.pypi.org/manage/account/publishing/>
  if the project does not exist yet (register a *pending* publisher), or
  `https://test.pypi.org/manage/project/datasure/settings/publishing/` once it
  does.
- **PyPI** (for final releases): the same paths on <https://pypi.org>.

Select **GitHub** as the publisher, fill in the four values from the table
(matching the current `release.yml`), and add it. If a stale publisher with
the old values exists, delete it — a leftover mismatched publisher is a common
cause of `invalid-publisher`. The corresponding GitHub Environments
(Settings → Environments → `testpypi` and `pypi`) must also exist; they need
no secrets because authentication is via OIDC.

A secondary error line, `Missing credentials for
https://test.pypi.org/legacy/`, is only `uv`'s fallback after the OIDC match
failed — fixing the publisher registration resolves both. Do **not** switch to
API tokens to work around it.

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
├── checks/                 # 9 modular data quality check modules
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
3. Create corresponding test file in `tests/checks/`
4. Update navigation in `src/datasure/app.py` if needed

#### Adding a New Data Connector

1. Create new module in `src/datasure/connectors/`
2. Implement data loading and form functions
3. Update import view to include new connector
4. Add appropriate tests and documentation

## Getting Help

- **Documentation**: Check the [docs/](docs/) directory for development guides (changelog, release notes, etc.)
- **Issues**: Report bugs or request features on GitHub Issues
- **Discussions**: Use GitHub Discussions for questions and ideas
- **Code Quality**: Monitor [SonarQube Dashboard](https://sonarcloud.io/project/overview?id=PovertyAction_datasure)

## Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct ([CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)). Please treat all contributors with respect and create a welcoming environment for everyone.

---

Thank you for contributing to DataSure! Your contributions help improve data quality monitoring for survey research worldwide.
