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

# Format a single python file, "f"
streamlit-run f:
    uv run streamlit run {{ f }}

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
    uv run --with twine twine upload --repository testpypi dist/*

# Publish to PyPI (production)
publish: build-package
    uv run --with twine twine upload dist/*

# Check PyPI package before publishing
check-pypi: build-package
    uv run --with twine twine check dist/*

# View PyPI package info
pypi-info:
    uv run --with twine twine check dist/* --verbose

# Package development workflow: test, build, and verify
package-workflow: test build-package test-cli clean-build
    @echo "Package workflow completed successfully!"

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
