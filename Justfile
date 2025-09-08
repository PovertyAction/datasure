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
    uv lock
    pre-commit autoupdate

# create virtual environment
venv:
    uv sync
    uv tool install pre-commit
    pre-commit install

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
[linux]
test:
    uv run python -m pytest

[macos]
test:
    uv run python -m pytest

[windows]
test:
    -uv run python -m pytest -p no:cacheprovider 2>&1 | Select-String -Pattern "^(?!INTERNALERROR)" | Select-String -Pattern "^(?!.*NotImplementedError.*PosixPath)" | Out-String -Stream

# Run tests with coverage report (terminal)
[linux]
test-cov:
    uv run python -m pytest --cov=src --cov-report=term-missing

[macos]
test-cov:
    uv run python -m pytest --cov=src --cov-report=term-missing

[windows]
test-cov:
    @echo "Running tests on Windows (coverage disabled due to pytest-cov compatibility issue)"
    @echo "Note: Suppressing internal pytest errors (INTERNALERROR>) on Windows"
    -uv run python -m pytest -p no:cacheprovider 2>&1 | Select-String -Pattern "^(?!INTERNALERROR)" | Select-String -Pattern "^(?!.*NotImplementedError.*PosixPath)" | Out-String -Stream

[linux]
test-verbose:
    uv run python -m pytest -v

[macos]
test-verbose:
    uv run python -m pytest -v

[windows]
test-verbose:
    @echo "Running tests on Windows (coverage disabled due to pytest-cov compatibility issue)"
    @echo "Note: Suppressing internal pytest errors (INTERNALERROR>) on Windows"
    -uv run python -m pytest -v -p no:cacheprovider 2>&1 | Select-String -Pattern "^(?!INTERNALERROR)" | Select-String -Pattern "^(?!.*NotImplementedError.*PosixPath)" | Out-String -Stream

# Run tests with HTML coverage report
[linux]
test-cov-html:
    uv run python -m pytest --cov=src --cov-report=html
    @echo "Coverage report available at htmlcov/index.html"

[macos]
test-cov-html:
    uv run python -m pytest --cov=src --cov-report=html
    @echo "Coverage report available at htmlcov/index.html"

[windows]
test-cov-html:
    @echo "Running tests on Windows (coverage disabled due to pytest-cov compatibility issue)"
    @echo "Note: Suppressing internal pytest errors (INTERNALERROR>) on Windows"
    -uv run python -m pytest -p no:cacheprovider 2>&1 | Select-String -Pattern "^(?!INTERNALERROR)" | Select-String -Pattern "^(?!.*NotImplementedError.*PosixPath)" | Out-String -Stream

# Run tests with XML coverage report (for CI)
[linux]
test-cov-xml:
    uv run python -m pytest --cov=src --cov-report=xml

[macos]
test-cov-xml:
    uv run python -m pytest --cov=src --cov-report=xml

[windows]
test-cov-xml:
    @echo "Running tests on Windows (coverage disabled due to pytest-cov compatibility issue)"
    @echo "Note: Suppressing internal pytest errors (INTERNALERROR>) on Windows"
    -uv run python -m pytest -p no:cacheprovider 2>&1 | Select-String -Pattern "^(?!INTERNALERROR)" | Select-String -Pattern "^(?!.*NotImplementedError.*PosixPath)" | Out-String -Stream

# Run tests for a specific file
test-file f:
    uv run python -m pytest {{ f }}

# Run pre-commit hooks
pre-commit-run:
    pre-commit run

# Build the package using uv
build-package:
    uv build

# Bump alpha patch release
bump-patch-alpha:
    uv version --bump patch --bump alpha

# Bump alpha minor release
bump-minor-alpha:
    uv version --bump minor --bump alpha

# Bump alpha major release
bump-major-alpha:
    uv version --bump major --bump alpha

# Bump beta patch release
bump-patch-beta:
    uv version --bump patch --bump beta

# Bump beta minor release
bump-minor-beta:
    uv version --bump minor --bump beta

# Bump beta major release
bump-major-beta:
    uv version --bump major --bump beta

# Bump release candidate patch release
bump-patch-rc:
    uv version --bump patch --bump rc

# Bump release candidate minor release
bump-minor-rc:
    uv version --bump minor --bump rc

# Bump release candidate major release
bump-major-rc:
    uv version --bump major --bump rc

# # Bump patch release
# bump-patch:
#     uv version --bump patch
# # Bump minor release
# bump-minor:
#     uv version --bump minor
# # Bump major release
# bump-major:
#     uv version --bump major

# Bump version by patch and create git tag
bump-patch:
    @just bump-and-tag patch

# Bump version by minor and create git tag
bump-minor:
    @just bump-and-tag minor

# Bump version by major and create git tag
bump-major:
    @just bump-and-tag major

# Internal recipe to bump version and create git tag
[linux]
bump-and-tag type:
    #!/usr/bin/env bash
    # Check if the repo is clean
    if [[ -n $(git status --porcelain) ]]; then
        echo "Error: Git repository has uncommitted changes. Please commit or stash them first."
        exit 1
    fi

    # Get the current version before bumping
    OLD_VERSION=$(uv version --short)
    echo "Current version: $OLD_VERSION"

    # Bump the version
    echo "Bumping {{ type }} version..."
    uv version --bump {{ type }}

    # Get the new version
    NEW_VERSION=$(uv version --short)
    echo "New version: $NEW_VERSION"

    # Run uv sync to update the lock file
    echo "Updating lock file with uv sync..."
    uv sync

    # Commit both the pyproject.toml and lock file changes in one commit
    git add pyproject.toml
    git add .
    git commit -m "Bump version: $OLD_VERSION → $NEW_VERSION"

    # Create tag directly rather than calling another recipe
    VERSION=$NEW_VERSION
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

[macos]
bump-and-tag type:
    #!/usr/bin/env bash
    # Check if the repo is clean
    if [[ -n $(git status --porcelain) ]]; then
        echo "Error: Git repository has uncommitted changes. Please commit or stash them first."
        exit 1
    fi

    # Get the current version before bumping
    OLD_VERSION=$(uv version --short)
    echo "Current version: $OLD_VERSION"

    # Bump the version
    echo "Bumping {{ type }} version..."
    uv version --bump {{ type }}

    # Get the new version
    NEW_VERSION=$(uv version --short)
    echo "New version: $NEW_VERSION"

    # Run uv sync to update the lock file
    echo "Updating lock file with uv sync..."
    uv sync

    # Commit both the pyproject.toml and lock file changes in one commit
    git add pyproject.toml
    git add .
    git commit -m "Bump version: $OLD_VERSION → $NEW_VERSION"

    # Create tag directly rather than calling another recipe
    VERSION=$NEW_VERSION
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
bump-and-tag type:
    @$status = & git status --porcelain; if ($status) { Write-Host "Error: Git repository has uncommitted changes. Please commit or stash them first."; exit 1 }; $OLD_VERSION = & uv version --short; Write-Host "Current version: $OLD_VERSION"; Write-Host "Bumping {{ type }} version..."; & uv version --bump {{ type }}; $NEW_VERSION = & uv version --short; Write-Host "New version: $NEW_VERSION"; Write-Host "Updating lock file with uv sync..."; & uv sync; & git add pyproject.toml; & git add .; & git commit -m "Bump version: $OLD_VERSION → $NEW_VERSION"; $VERSION = $NEW_VERSION; $TAG = "v$VERSION"; if (git rev-parse "$TAG" 2>$null) { Write-Host "Tag $TAG already exists. Skipping tag creation." } else { Write-Host "Creating git tag $TAG..."; git tag -a "$TAG" -m "Version $VERSION"; Write-Host "Created git tag: $TAG"; Write-Host "To push the tag, run: git push origin $TAG" }

# Create git tag from current version if it doesn't exist
[linux]
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

[macos]
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
[linux]
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

[macos]
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
[linux]
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

[macos]
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
[linux]
clean-build:
    rm -rf dist/
    rm -rf build/

# Clean build artifacts
[macos]
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

[linux]
install-package: build-package
    uv pip install --force-reinstall dist/datasure-*.whl

[macos]
install-package: build-package
    uv pip install --force-reinstall dist/datasure-*.whl

# Uninstall the package
uninstall-package:
    uv pip uninstall datasure

# Test the CLI after installation
test-cli: install-package
    uv run datasure --version

# Publish to TestPyPI (for testing)
publish-test: build-package
    uv publish --check-url https://test.pypi.org/simple --publish-url https://test.pypi.org/legacy/

# Publish to PyPI (production)
publish: build-package
    uv publish

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
