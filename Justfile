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
clean:
    rm -rf .venv

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

activate-venv:
    uv shell

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

fmt-all: lint-py fmt-python fmt-markdown

# Run tests
test:
    uv run python -m pytest

# Run tests with coverage report (terminal)
test-cov:
    uv run python -m pytest --cov=src --cov-report=term-missing

# Run tests with HTML coverage report
test-cov-html:
    uv run python -m pytest --cov=src --cov-report=html
    @echo "Coverage report available at htmlcov/index.html"

# Run tests with XML coverage report (for CI)
test-cov-xml:
    uv run python -m pytest --cov=src --cov-report=xml

# Run pre-commit hooks
pre-commit-run:
    pre-commit run

# Build the package using uv
build-package:
    uv build

# Clean build artifacts
clean-build:
    rm -rf dist/
    rm -rf build/

# Install the package locally from the built wheel
install-package: build-package
    uv pip install --force-reinstall dist/pydms-*.whl

# Uninstall the package
uninstall-package:
    uv pip uninstall pydms

# Test the CLI after installation
test-cli: install-package
    uv run pydms --version

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
package-workflow: test clean-build build-package test-cli
    @echo "Package workflow completed successfully!"

[windows]
pre-install:
    winget install Casey.Just astral-sh.uv GitHub.cli
    npm install -g markdownlint-cli

[linux]
pre-install:
    brew install just uv gh markdownlint-cli

[macos]
pre-install:
    brew install just uv gh markdownlint-cli
