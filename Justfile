# Set the shell to use
# set shell := ["nu", "-c"]
# Set shell for Windows

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# Set path to virtual environment's python

python_dir := ".venv/"
python := python_dir + if os_family() == "windows" { "Scripts/python.exe" } else { "bin/python3" }

# Display system information
system-info:
    @echo "CPU architecture: {{ arch() }}"
    @echo "Operating system type: {{ os_family() }}"
    @echo "Operating system: {{ os() }}"
    @echo "Home directory: {{ home_directory() }}"

# Clean venv
[linux]
clean:
    rm -rf .venv

# Clean venv
[macos]
clean:
    rm -rf .venv

# Clean venv
[windows]
clean:
    if (Test-Path ".venv") { Remove-Item ".venv" -Recurse -Force }

# Setup environment
get-started: pre-install venv

# Update project software versions in requirements
update-reqs:
    uv lock --upgrade
    pre-commit autoupdate

# create virtual environment
venv:
    uv sync
    uv tool install pre-commit
    pre-commit install

# Print the command to activate the virtual environment
[windows]
activate-venv:
    @Write-Host "Run: .venv\Scripts\activate.ps1"

# Print the command to activate the virtual environment
[unix]
activate-venv:
    @echo "Run: source .venv/bin/activate"

# launch jupyter lab
lab:
    uv run jupyter lab

# Launch DataSure Streamlit app for local testing
datasure-dev:
    uv run streamlit run src/datasure/app.py

# Lint python code
lint-py:
    uv run ruff check

# Format python code
fmt-python:
    uv run ruff format

# Format a single python file, "f"
fmt-py f:
    uv run ruff format {{ f }}

# Format all markdown and config files
fmt-markdown:
    markdownlint --config .markdownlint.yaml "**/*.md" --fix

# Format a single markdown file, "f"
fmt-md f:
    markdownlint --config .markdownlint.yaml {{ f }} --fix

# Check format of all markdown files
fmt-check-markdown:
    markdownlint --config .markdownlint.yaml "**/*.md" "**/*.md"

# Run all linting and formatting
fmt-all: lint-py fmt-python fmt-markdown

# Run tests
test:
    uv run python -m pytest

# Run tests with coverage report (terminal)
test-cov:
    uv run python -m pytest --cov=src --cov-report=term-missing

test-verbose:
    uv run python -m pytest -v

# Run tests with HTML coverage report
test-cov-html:
    uv run python -m pytest --cov=src --cov-report=html
    @echo "Coverage report available at htmlcov/index.html"

# Run tests with XML coverage report (for CI)
test-cov-xml:
    uv run python -m pytest --cov=src --cov-report=xml

# Run tests for a specific file
test-file f:
    uv run python -m pytest {{ f }}

# Run tests for a module with coverage (auto-discovers test file and coverage module)
# Usage: just test-mod-cov <module>  e.g. just test-mod-cov descriptive
[linux]
test-mod-cov mod:
    #!/usr/bin/env bash
    MOD="{{mod}}"
    TEST_FILE=$(find tests -name "test_${MOD}.py" -type f | head -1)
    if [ -z "$TEST_FILE" ]; then
        echo "Error: no test file matching 'test_${MOD}.py' found under tests/"
        exit 1
    fi
    SRC_FILE=$(find src/datasure -name "${MOD}.py" -type f | head -1)
    if [ -z "$SRC_FILE" ]; then
        echo "Error: no source file matching '${MOD}.py' found under src/datasure/"
        exit 1
    fi
    COV_MODULE="${SRC_FILE#src/}"
    COV_MODULE="${COV_MODULE%.py}"
    COV_MODULE="${COV_MODULE//\//.}"
    echo "Test file : $TEST_FILE"
    echo "Coverage  : $COV_MODULE"
    uv run python -m pytest "$TEST_FILE" -v --cov="$COV_MODULE" --cov-report=term-missing

[macos]
test-mod-cov mod:
    #!/usr/bin/env bash
    MOD="{{mod}}"
    TEST_FILE=$(find tests -name "test_${MOD}.py" -type f | head -1)
    if [ -z "$TEST_FILE" ]; then
        echo "Error: no test file matching 'test_${MOD}.py' found under tests/"
        exit 1
    fi
    SRC_FILE=$(find src/datasure -name "${MOD}.py" -type f | head -1)
    if [ -z "$SRC_FILE" ]; then
        echo "Error: no source file matching '${MOD}.py' found under src/datasure/"
        exit 1
    fi
    COV_MODULE="${SRC_FILE#src/}"
    COV_MODULE="${COV_MODULE%.py}"
    COV_MODULE="${COV_MODULE//\//.}"
    echo "Test file : $TEST_FILE"
    echo "Coverage  : $COV_MODULE"
    uv run python -m pytest "$TEST_FILE" -v --cov="$COV_MODULE" --cov-report=term-missing

[windows]
test-mod-cov mod:
    @$mod = "{{mod}}"; $testFile = Get-ChildItem -Path "tests" -Recurse -Filter "test_$mod.py" | Select-Object -First 1; if (-not $testFile) { Write-Host "Error: no test file matching 'test_$mod.py' found under tests/"; exit 1 }; $srcFile = Get-ChildItem -Path "src\datasure" -Recurse -Filter "$mod.py" | Select-Object -First 1; if (-not $srcFile) { Write-Host "Error: no source file matching '$mod.py' found under src\datasure\"; exit 1 }; $srcIdx = $srcFile.FullName.IndexOf("src\") + 4; $covModule = $srcFile.FullName.Substring($srcIdx) -replace "\\", "." -replace "\.py$", ""; Write-Host "Test file : $($testFile.FullName)"; Write-Host "Coverage  : $covModule"; uv run python -m pytest $testFile.FullName -v --cov=$covModule --cov-report=term-missing


# Run pre-commit hooks on all files
pre-commit-run:
    uv tool run pre-commit run --all-files

# Build the package using uv
build-package:
    uv build

# Verify CHANGELOG.md has entries under [Unreleased] (release gate).
# Accepts the same bump stages as bump-and-tag so stable releases can skip the check.
check-changelog +bumps="":
    uv run python scripts/check_changelog.py {{ bumps }}

# Bump the version only (no commit, no tag). Accepts any `uv version --bump`
# stage, combinable: `just bump patch`, `just bump minor rc`, `just bump stable`
bump +bumps:
    uv version {{ prepend("--bump=", bumps) }}

# Bump version by patch, commit, and create git tag
bump-patch: (bump-and-tag "patch")

# Bump version by minor, commit, and create git tag
bump-minor: (bump-and-tag "minor")

# Bump version by major, commit, and create git tag
bump-major: (bump-and-tag "major")

# Finalize the current pre-release (e.g. 1.0.0rc1 -> 1.0.0), commit, and tag
bump-stable: (bump-and-tag "stable")

# Pre-release bump, commit, and tag: `just bump-pre patch rc` -> v0.8.4rc1
bump-pre type stage: (bump-and-tag type stage)

# Internal recipe to bump version, commit pyproject.toml + uv.lock, and tag.
# Gated on a non-empty [Unreleased] section in CHANGELOG.md (skipped for stable).
[unix]
bump-and-tag +bumps:
    #!/usr/bin/env bash
    set -euo pipefail
    # Run changelog gate (skipped automatically for stable releases)
    uv run python scripts/check_changelog.py {{ bumps }}

    # Check if the repo is clean
    if [[ -n $(git status --porcelain) ]]; then
        echo "Error: Git repository has uncommitted changes. Please commit or stash them first."
        exit 1
    fi

    # Get the current version before bumping
    OLD_VERSION=$(uv version --short)
    echo "Current version: $OLD_VERSION"

    # Bump the version
    echo "Bumping version ({{ bumps }})..."
    uv version {{ prepend("--bump=", bumps) }}

    # Get the new version
    NEW_VERSION=$(uv version --short)
    echo "New version: $NEW_VERSION"

    # Run uv sync to update the lock file
    echo "Updating lock file with uv sync..."
    uv sync

    # Commit only the files the bump changes
    git add pyproject.toml uv.lock
    git commit -m "Bump version: $OLD_VERSION → $NEW_VERSION"

    # Create tag directly rather than calling another recipe
    TAG="v$NEW_VERSION"

    # Check if tag already exists
    if git rev-parse "$TAG" >/dev/null 2>&1; then
        echo "Tag $TAG already exists. Skipping tag creation."
    else
        echo "Creating git tag $TAG..."
        git tag -a "$TAG" -m "Version $NEW_VERSION"
        echo "Created git tag: $TAG"
        echo "To push the tag, run: git push origin $TAG"
    fi

[windows]
bump-and-tag +bumps:
    @uv run python scripts/check_changelog.py {{ bumps }}; if ($LASTEXITCODE -ne 0) { exit 1 }; $status = & git status --porcelain; if ($status) { Write-Host "Error: Git repository has uncommitted changes. Please commit or stash them first."; exit 1 }; $OLD_VERSION = & uv version --short; Write-Host "Current version: $OLD_VERSION"; Write-Host "Bumping version ({{ bumps }})..."; & uv version {{ prepend("--bump=", bumps) }}; if ($LASTEXITCODE -ne 0) { exit 1 }; $NEW_VERSION = & uv version --short; Write-Host "New version: $NEW_VERSION"; Write-Host "Updating lock file with uv sync..."; & uv sync; & git add pyproject.toml uv.lock; & git commit -m "Bump version: $OLD_VERSION → $NEW_VERSION"; $TAG = "v$NEW_VERSION"; if (git rev-parse "$TAG" 2>$null) { Write-Host "Tag $TAG already exists. Skipping tag creation." } else { Write-Host "Creating git tag $TAG..."; git tag -a "$TAG" -m "Version $NEW_VERSION"; Write-Host "Created git tag: $TAG"; Write-Host "To push the tag, run: git push origin $TAG" }

# Create git tag from current version if it doesn't exist
[unix]
tag-version:
    #!/usr/bin/env bash
    VERSION=$(uv version --short)
    TAG="v$VERSION"

    # Check if tag already exists
    if git rev-parse "$TAG" >/dev/null 2>&1; then
        echo "Tag $TAG already exists. Skipping tag creation."
    else
        echo "Creating git tag $TAG..."
        git tag -a "$TAG" -m "Version $VERSION"
        echo "Created git tag: $TAG"
        echo "To push the tag, run: git push origin $TAG"
    fi

[windows]
tag-version:
    @$VERSION = & uv version --short; $TAG = "v$VERSION"; if (git rev-parse "$TAG" 2>$null) { Write-Host "Tag $TAG already exists. Skipping tag creation." } else { Write-Host "Creating git tag $TAG..."; git tag -a "$TAG" -m "Version $VERSION"; Write-Host "Created git tag: $TAG"; Write-Host "To push the tag, run: git push origin $TAG" }

# Push the latest version tag to remote
[unix]
push-tag:
    #!/usr/bin/env bash
    VERSION=$(uv version --short)
    TAG="v$VERSION"

    # Check if tag exists locally
    if git rev-parse "$TAG" >/dev/null 2>&1; then
        echo "Pushing tag $TAG to remote..."
        git push origin "$TAG"
        echo "Tag $TAG pushed successfully!"
    else
        echo "Tag $TAG does not exist locally. Create it first with 'just tag-version'."
        exit 1
    fi

[windows]
push-tag:
    @$VERSION = & uv version --short; $TAG = "v$VERSION"; if (git rev-parse "$TAG" 2>$null) { Write-Host "Pushing tag $TAG to remote..."; git push origin "$TAG"; Write-Host "Tag $TAG pushed successfully!" } else { Write-Host "Tag $TAG does not exist locally. Create it first with 'just tag-version'."; exit 1 }

# Push both commits and tag to remote
[unix]
push-all:
    #!/usr/bin/env bash
    VERSION=$(uv version --short)
    TAG="v$VERSION"

    # Push commits
    echo "Pushing commits to remote..."
    git push

    # Check if tag exists locally
    if git rev-parse "$TAG" >/dev/null 2>&1; then
        echo "Pushing tag $TAG to remote..."
        git push origin "$TAG"
        echo "All changes pushed successfully!"
    else
        echo "Tag $TAG does not exist locally. Create it first with 'just tag-version'."
        exit 1
    fi

[windows]
push-all:
    @$VERSION = & uv version --short; $TAG = "v$VERSION"; Write-Host "Pushing commits to remote..."; git push; if (git rev-parse "$TAG" 2>$null) { Write-Host "Pushing tag $TAG to remote..."; git push origin "$TAG"; Write-Host "All changes pushed successfully!" } else { Write-Host "Tag $TAG does not exist locally. Create it first with 'just tag-version'."; exit 1 }

# Clean build artifacts
[unix]
clean-build:
    rm -rf dist/
    rm -rf build/

# Clean build artifacts
[windows]
clean-build:
    if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }
    if (Test-Path "build") { Remove-Item "build" -Recurse -Force }

# Install the package locally from the built wheel
[windows]
install-package: build-package
    $wheel = Get-ChildItem -Path "dist" -Filter "*.whl" | Select-Object -First 1; uv pip install --force-reinstall $wheel.FullName

[unix]
install-package: build-package
    uv pip install --force-reinstall dist/datasure-*.whl

# Uninstall the package
uninstall-package:
    uv pip uninstall datasure

# Test the CLI after installation
test-cli: install-package
    uv run datasure --version

# Manual publish escape hatches. CI (.github/workflows/release.yml) is the
# primary publish path via PyPI Trusted Publishing; these recipes need
# UV_PUBLISH_TOKEN set. Both rebuild from a clean dist/ with --no-sources,
# as recommended by https://docs.astral.sh/uv/guides/package/

# Publish to TestPyPI (for testing)
publish-test: clean-build
    uv build --no-sources
    uv publish --index testpypi

# Publish to PyPI (production)
publish: clean-build
    uv build --no-sources
    uv publish --index pypi

# Verify the published package installs and runs from PyPI
verify-published:
    uv run --no-project --refresh-package datasure --with datasure -- datasure --version

# Package development workflow: test, build, and verify
package-workflow: test build-package test-cli clean-build
    @echo "Package workflow completed successfully!"

# Display the current version of DataSure
version:
    uv version --short

# install required software
[windows]
pre-install:
    winget install Casey.Just astral-sh.uv GitHub.cli OpenJS.NodeJS
    npm install -g markdownlint-cli

# install required software
[linux]
pre-install:
    brew install just uv gh markdownlint-cli

# install required software
[macos]
pre-install:
    brew install just uv gh markdownlint-cli
