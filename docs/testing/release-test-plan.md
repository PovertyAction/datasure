# Release Test Plan

This plan is for testing a DataSure release candidate (a version such as
`1.2.0rc1`) before it ships. Maintainers run all of it on Windows and macOS.
Early-access testers run [Before you start](#before-you-start), then as many
sections as they can, starting with the ones that match their own work.

The plan has two parts:

- **[Core tests](#core-tests)** cover the whole workflow and stay the same from
  release to release.
- **[Release-specific tests](#release-specific-tests)** cover what is new in
  this release. Maintainers replace this part for each release, from
  [RELEASENOTES.md](../../RELEASENOTES.md).

Each step says what you should see. When you see something else, report it
(see [Reporting a problem](#reporting-a-problem)) and carry on with the next
step if you can.

## Before you start

### Data you can use

Test with the demo project or with project data you are allowed to use.
Never put participant names, phone numbers, locations or other personal data
in an issue, screenshot or log you share. Crop or blur screenshots first. If
you are not sure whether your data can be used, use the demo project and ask
<researchsupport@poverty-action.org>.

### Back up your projects

A release candidate may change how projects are stored, and you might want
to go back to the stable version. Before you install it, close DataSure and
copy the DataSure cache folder somewhere safe:

- **Windows**: `%APPDATA%/datasure/cache/`
- **macOS and Linux**: `~/.local/share/datasure/cache/`

### Install the release candidate

Release candidates are published on Test PyPI, not PyPI. Replace `X.Y.ZrcN`
with the version you were asked to test, for example `1.2.0rc1`:

```bash
uv tool install "datasure==X.Y.ZrcN" --force \
    --index https://test.pypi.org/simple/ \
    --index https://pypi.org/simple/
```

Then check the version:

```bash
datasure --version
```

It should print the release candidate's version.

To go back to the stable version, close DataSure, run
`uv tool install datasure --force`, and copy your backed-up cache folder back
in place of the current one.

### Before reporting a problem

Check [KNOWN_ISSUES.md](../../KNOWN_ISSUES.md) and the
[open issues](https://github.com/PovertyAction/datasure/issues). If your
problem is already listed, add a 👍 and any new details to that issue instead.

## Reporting a problem

Open a [bug report](https://github.com/PovertyAction/datasure/issues/new?template=bug_report.yml)
and fill in every field:

- Start the title with the version, for example `[1.2.0rc1] Duplicates card
  Save stays disabled`.
- Name the section and step of this plan, for example "Core C4".
- Give the steps that lead to the problem, what you expected and what you saw.
- Paste the terminal output around the error, and attach a screenshot if it
  helps. Remove personal data first.

Maintainers label the issue `rc-feedback` and triage it daily. A blocker
means another release candidate and a later release date, so report early.

For questions that aren't bugs, email <researchsupport@poverty-action.org>.

## Core tests

### Core A. Install and launch

| # | Do this | You should see |
| --- | --- | --- |
| A1 | Run `datasure --version` | The release candidate's version |
| A2 | Run `datasure` | The app opens in your browser on the Start page, and stays connected |
| A3 | Leave the app open for 5 minutes, then click around | No "connection lost" message, and no errors in the terminal |
| A4 | Close the browser tab and run `datasure` again | The app opens again with your projects listed |

### Core B. Upgrade from the previous stable version

Run this only if you had projects in the previous stable version.

| # | Do this | You should see |
| --- | --- | --- |
| B1 | Open the Start page | Every project you had is listed |
| B2 | Open a project and go to each page in the sidebar | Each page loads without an error |
| B3 | Open each check page, then each check on it | Each check loads, or says why it is not set up |
| B4 | Open the Correct Data page | Earlier corrections are listed with a **Successful** status, or with a reason |
| B5 | On Import Data, click **Load Data** | The data loads; the check pages show the refreshed data |

### Core C. Demo project

| # | Do this | You should see |
| --- | --- | --- |
| C1 | On the Start page, click **Start Demo** on the **DataSure Demo** row | The demo opens on Import Data with its data already loaded |
| C2 | Follow the guidance on every step, in order, to the last step | Each step's guidance matches the page: every column, button and value it names is there, and each worked example gives the result it describes |
| C3 | Check the sidebar's **Demo Help** on each step | It shows the current step and the total number of steps |
| C4 | On the last step, build the replication package and tick the confirmation | One completion message, with **Restart Demo** and **Create Real Project** |
| C5 | Click **Exit Demo** in the sidebar, then **Resume** on the demo row | The demo reopens with your work kept |
| C6 | Click **Restart** on the demo row and confirm | The demo starts from the beginning, with none of your earlier corrections or check pages |
| C7 | After exiting the demo, open a real project | No demo data, datasets or settings appear in it |

### Core D. Real project: import and prepare

| # | Do this | You should see |
| --- | --- | --- |
| D1 | Click **+ New Project**, enter a name and click **Create Project** | The project is created and opened |
| D2 | Add a local file (CSV, Excel `.xlsx`, Stata, JSON or Parquet) with **Add Import Configuration**, then **Load Data** | The dataset appears under **Preview Imported Data** with the right row and column counts |
| D3 | Add your SurveyCTO credentials under **Manage Credentials**, add a form, then **Load Data** | The form imports with the same number of submissions as the SurveyCTO console |
| D4 | Remove those credentials with **Remove Credentials**, then check your OS credential store (Credential Manager or Keychain Access) | The `datasure_` entry for that server is gone |
| D5 | On Prepare Data, add a few steps (convert a date, rename or remove a column, remove rows) | Each step's message gives the rows and columns left; the preview matches |
| D6 | Click **Load Data** on Import Data again, then reopen Prepare Data | Your steps are applied again to the new data |

### Core E. Real project: checks

| # | Do this | You should see |
| --- | --- | --- |
| E1 | On Configure Checks, add a check configuration with your KEY, ID, enumerator and date columns, and a backcheck dataset if you have one | A new check page appears under **DQA Reports** |
| E2 | Open each check on the page and set it up | Each check shows results that agree with what you know about the data |
| E3 | Change a filter on a check, switch to another check, then come back | The filter is kept |
| E4 | Open **Summary** | Every check has a row; each row's numbers match what the check itself shows |
| E5 | Set missing codes on Missing Values (for example `-99`) | Those codes are not flagged as outliers and not counted in means or minimums |

### Core F. Corrections and outputs

| # | Do this | You should see |
| --- | --- | --- |
| F1 | On Correct Data, add a **modify value** correction | The value changes in the check reports, and the Correction Log shows it as **Successful** |
| F2 | Remove that correction | The original value comes back |
| F3 | On Export Replication Package, build and download a package | The zip downloads; its scripts and `correction_log.csv` match your project |
| F4 | On the Start page, export the project's configuration, then create a new project **From a configuration file** with it | The new project has the same import sources, prep steps, check pages and check settings |

## Release-specific tests

Maintainers: replace this section for each release, using the release's
section of [RELEASENOTES.md](../../RELEASENOTES.md). Keep the step IDs unique
so reports can name them.

### 1.2.0

#### R1. Check page navigation and status

| # | Do this | You should see |
| --- | --- | --- |
| R1.1 | Open a check page | Group buttons (**Overview**, **Data integrity**, **Field team**, **Exploration**) and a row of checks for the selected group |
| R1.2 | Pick a check, copy the page address, open it in a new tab | The new tab opens on the same check |
| R1.3 | Close and reopen the app, then open the check page | It opens on the check you last viewed |
| R1.4 | Click **Reset filters** on a check | Only that check's filters reset |
| R1.5 | Open a check that is not set up (for example Backchecks with no backcheck dataset) | It is muted in the check row and explains what is missing |

#### R2. Summary check health

| # | Do this | You should see |
| --- | --- | --- |
| R2.1 | Open Summary | One row per check with **Status**, **Outstanding** and **Resolved**, grouped like the navigation |
| R2.2 | Change the **Comparison period** (Day, 7 days, Week, 30 days, Month) | The **Change** column and "+N since …" update; the choice is kept after you reopen the app |
| R2.3 | Resolve an issue on a check (for example accept an outlier), then reopen Summary | That row's **Outstanding** goes down and **Resolved** goes up |
| R2.4 | Click **Open →** on a row | The check opens |

#### R3. Outliers & Constraints review

| # | Do this | You should see |
| --- | --- | --- |
| R3.1 | Click **Review** on a flagged outlier and **accept** it with a reason | The flag disappears and the counts drop |
| R3.2 | Turn on **Show reviewed** | The accepted value is highlighted green with your reason |
| R3.3 | **Review** another value and **modify** it to a value in range | The value is corrected and no longer flagged |
| R3.4 | Accept a hard constraint violation | You are asked to confirm first |
| R3.5 | Turn on **Show only reviewed** | Only accepted and corrected values are listed |

#### R4. GPS Checks review

| # | Do this | You should see |
| --- | --- | --- |
| R4.1 | Save a Mapbox token in the GPS settings, then reopen the app | The map still shows; the token was kept |
| R4.2 | **Review** a GPS outlier and **accept** it | The point turns green on the map and leaves the outlier count |
| R4.3 | **Review** another outlier and **modify coordinates** | Both coordinates change, and the Correction Log has two entries with source `gps` |
| R4.4 | Remove the Mapbox token, if you can | The outliers table and counts still show, without the map |

#### R5. Duplicate ID cards

| # | Do this | You should see |
| --- | --- | --- |
| R5.1 | Open Duplicates on data with duplicate IDs | One card per duplicate ID, with the records side by side and differences highlighted |
| R5.2 | Try **Compare all fields**, **Only differing fields**, search, sort and **Download duplicates (CSV)** | Each works as labelled |
| R5.3 | On a card, choose **Modify ID** for one record with a new ID, and **Keep** for the other; add a reason and note; **Save** | The card disappears and **Resolved** goes up by one |
| R5.4 | Try to save a card where two records keep the ID | **Save** is disabled with a message saying why |
| R5.5 | Remove the correction on Correct Data | The card comes back |
| R5.6 | On a page with back check data, switch to **Backcheck data** | Duplicate back check IDs and unmatched back checks have their own cards |

#### R6. Backchecks

| # | Do this | You should see |
| --- | --- | --- |
| R6.1 | Set a **Backcheck target (%)** and reopen the app | The target is kept and used in **Targets** |
| R6.2 | Check **Targets** | **Backcheck Coverage** against the target, and **Backchecks vs Expected** when the page has a survey target |
| R6.3 | **Review** a mismatch and attribute it to the **Enumerator**; attribute another to the **Respondent** with a note | Both show their error source; **Mismatches Attributed** goes up; the **Attribution log** lists both |
| R6.4 | Compare the error rate and the adjusted error rate in the enumerator statistics | The regular rate is unchanged; the adjusted rate leaves out the respondent mismatch |
| R6.5 | Set an **Error rate target (%)** | Rates above it are highlighted |

#### R7. Correction log, reviewer name and replication package

| # | Do this | You should see |
| --- | --- | --- |
| R7.1 | Set your **Reviewer name** in the sidebar, then make a correction | The Correction Log's User column shows your name |
| R7.2 | Use the **Source** and **Action** filters above the Correction Log | Only matching entries are listed |
| R7.3 | On a page with back check data, switch Correct Data to **Backcheck data** | Only "modify value" on the ID and "remove row" are offered |
| R7.4 | Build a replication package with **Exclude reviewer names** ticked | `correction_log.csv` in the zip has an empty `user` column; the project's own log is unchanged |

#### R8. Project setups and Prep

| # | Do this | You should see |
| --- | --- | --- |
| R8.1 | Export a configuration with **Include record-level decisions** unticked, and apply it to a new project | Missing codes, Descriptive Stats columns and the Duplicates, Outliers, GPS and Backchecks column rules come across; corrections and attributions do not |
| R8.2 | On Prepare Data, add a **concat** column from two text columns | The values are joined with the separator you chose |
| R8.3 | Use **to string** on a number column and **to number** on a true/false column | The columns convert as described in the User Guide |
| R8.4 | Add a local `.xls` file | DataSure rejects it with a message to save it as `.xlsx` |

## Sign-off

Maintainers record each run in the release checklist issue.

| Platform | Tester | Version | Core | Release-specific | Blockers found |
| --- | --- | --- | --- | --- | --- |
| Windows | | | | | |
| macOS | | | | | |
| Upgrade from previous stable | | | | | |
