# DMS Dashboard

IPA Dashboard Solution for Data Management Systems.

## Development set up

Development relies on the following software

- `winget` (Windows) or `homebrew` (MacOS/Linux) for package management and installation
- `git` for source control management
- `just` for running common command line patterns
- `uv` for installing Python and managing virtual environments
- `Quarto` framework for creating analytics products via code

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
| Windows   | `winget install Git.Git Casey.Just astral-sh.uv GitHub.cli Posit.Quarto` |
| Mac/Linux | `brew install just uv gh`                                          |

This will make sure that you have the latest version of `Just`, as well as
[uv](https://docs.astral.sh/uv/) (installer for Python) and
[Quarto](https://quarto.org/docs/guide/) (for writing and compiling scientific and
technical documents).

- We use `Just` in order to make it easier for all IPA users to be productive with data
  and technology systems. The goal of using a `Justfile` is to help make the end goal of
  the user easier to achieve without needing to know or remember all of the technical
  details of how we get to that goal.
- We use `uv` to help ease use of Python. `uv` provides a global system for creating and
  building computing environments for Python.
- We use Quarto to allow users to focus on writing and data analytics. Writing in
  markdown, jupyter notebooks, python scripts, R scripts, etc. makes it easier to
  review, update, and deploy technical documentation.

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
