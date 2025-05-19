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

## Testing the Streamlit App

Follow these steps to test the app:

### 1. Prepare Your Environment

- Ensure all necessary files are on your local machine. To do this, pull the latest updates from the GitHub repository:
  - **Using Visual Studio Code (VS Code):** Sync files through the Source Control panel.
  - **Using Command Line:** Run the following command in your terminal:

    ```bash
    git pull
    ```

### 2. Navigate to the Repository

- Open your terminal (VS Code terminal, Command Prompt, or PowerShell).
- Navigate to the folder where the repository is located. This folder should contain the `pydms.py` file.

### 3. Start the App

- Run one of the following commands to launch the app:

    ```bash
    just streamlit-run pydms.py
    ```

    or

    ```bash
    uv run streamlit run pydms.py
    ```

---

### App Features

### Import Data Page

- When the app starts, the **Import Data** page is displayed.
- This page includes four tabs for connecting datasets. Currently, only the **SurveyCTO** and **Local Storage** tabs are functional.
- Use these tabs to upload or connect your datasets.

### Prepare Data Page

- After importing data, go to the **Prepare Data** page to preview your datasets. Each dataset will appear in a separate tab.
- **Note:** This section is still under development. While the functions listed won't work yet, you can review them and suggest additional features.

### Configure Checks Page

- Set up **HFCs** (High-Frequency Checks) on this page:
  1. Enter a name in the **Page Name** input box.
  2. Select a dataset from the **Select Data** dropdown.
  3. Additional input fields will appear as you provide information.
  4. Once the form is complete, click **Add Page** and save the settings.
- This will create an HFC page, but currently, you can only set up one HFC page at a time.
- If the HFC page doesn’t appear immediately, select another page from the left navigation menu and return.

### HFC Page

- The HFC page contains dashboards for various checks, organized into tabs.
- To set up the checks:
  1. Open a tab and expand the **Settings Expander** at the top.
  2. Configure the settings as needed for the check to display the required output.

## Running Tests

The project uses Python's built-in `unittest` framework for testing. The test files are located in the `tests/` directory.

To run all tests, execute the following command from the project root directory:

```bash
python -m unittest discover tests
```

To run a specific test file:

```bash
python -m unittest tests/test_summary.py
```
