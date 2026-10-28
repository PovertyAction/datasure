# DataSure User Guide

Version 1.2 - Comprehensive Guide to Survey Data Quality Management

---

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Step-by-Step Workflow](#step-by-step-workflow)
   - [Step 1: Start Here](#step-1-start-here)
   - [Step 2: Import Data](#step-2-import-data)
   - [Step 3: Prepare Data](#step-3-prepare-data)
   - [Step 4: Configure Checks](#step-4-configure-checks)
   - [Step 5: Review Reports](#step-5-review-reports)
   - [Step 6: Correct Data](#step-6-correct-data)
   - [Step 7: Replication Package](#step-7-replication-package)
4. [Quality Check Reports](#quality-check-reports)
5. [Demo Mode](#demo-mode)
6. [Best Practices](#best-practices)

---

## Introduction

**DataSure** is an IPA (Innovations for Poverty Action) Data Management System designed for comprehensive survey data quality monitoring. It helps field researchers, data managers, and survey teams identify and resolve data quality issues in real-time through automated high-frequency checks (HFCs).

### What DataSure Does

- **Import** survey data from multiple sources (SurveyCTO, CSV, Excel, JSON, Stata)
- **Prepare** and clean data with transformation tools
- **Configure** customizable quality check parameters
- **Analyze** data with 9 specialized quality check modules
- **Report** comprehensive quality metrics and visualizations
- **Correct** data issues with tracking and audit trails
- **Export** a replication package (Stata or Python scripts) that reproduces your full data pipeline

### Key Features

- **9 Quality Check Modules**: Summary, Progress, Duplicates, Missing Data, Outliers, Enumerator Stats, Descriptive Stats, Back Checks, GPS Checks
- **Real-time Monitoring**: Track data collection progress and quality as surveys are submitted
- **Interactive Visualizations**: Charts, tables, and heatmaps for easy interpretation
- **Audit Trails**: Complete tracking of all data corrections and modifications
- **Demo Mode**: Guided tutorial with sample household survey data
- **Replication Package Export**: Generate Stata or Python scripts that reproduce your complete data pipeline for sharing or archiving

---

## Getting Started

### System Requirements

- Modern web browser (Chrome, Firefox, Safari, Edge)
- Minimum 4GB RAM
- Internet connection (for SurveyCTO integration)
- Python 3.11+ (only required when installing via pip; uv manages Python automatically)

### Installation

```bash
# Install via uv (recommended)
uv tool install datasure

# Or pip
pip install datasure

# Launch the application
datasure
```

The application will open in your default web browser at `http://localhost:8501`.

### First Time Setup

1. **Launch DataSure**: Run the `datasure` command
2. **Choose Demo Mode** (recommended for first-time users):
   - Click "Start Demo" on the welcome screen
   - Follow the guided 7-step tutorial
3. **Or Create New Project**:
   - Click **+ New Project**
   - Enter a project name and click **Create Project**
   - Begin importing your data

---

## Step-by-Step Workflow

DataSure follows a 7-step workflow for complete data quality management:

### Step 1: Start Here

**Purpose**: Project selection and initialization

**What You'll Do**:

- Create a new project or select an existing one
- Access the demo mode (recommended for new users)
- View project dashboard and navigation

**Demo Scenario**:
You're working with household survey data from rural communities in India, including demographics, income, land ownership, and living conditions data.

**Key Actions**:

- **+ New Project**: Enter a descriptive project name, or start from a
  configuration file (see [Copying a Project's Setup](#copying-a-projects-setup))
- **Select Existing Project**: Choose from previously created projects
- **Start Demo**: Launch the interactive tutorial with sample data

#### Copying a Project's Setup

To reuse a project's setup, open **More** on its project card and choose
**Export configuration**. In the dialog that opens, choose what to include and
click **Download configuration** to save a configuration file. To use it,
choose **From a configuration file** when you create a new project, or choose
**Update from configuration** under **More** on an existing project. The
**DataSure Demo** row has an **Export** button that opens the same dialog.
Applying a configuration file exported from the demo rebuilds the demo data,
so it needs no file or sign-in.

The configuration file includes:

- Your import sources, without passwords or file paths. You sign in to
  SurveyCTO again and pick the local files on the computer doing the import.
- Prep steps.
- Check pages, with their settings and check tables: duplicate, outlier, GPS
  and back check columns, Descriptive Stats column selections, and back check
  mismatch attributions.
- Missing codes.
- Corrections.

It does not include survey data or remembered filters.

Corrections and back check mismatch attributions are record-level decisions:
they apply to particular submissions rather than to the setup. The **Include
record-level decisions (corrections and backcheck attribution)** option in the
export dialog is ticked by default. Untick it to share only the setup, for
example when starting a new survey round with the same checks. The file then
has no corrections or attributions, and it imports the same way.

When you import a configuration file:

- A check page is only created when the project has no page with that name
  and the page's dataset was imported. A skipped page is listed after the
  import, and an existing page keeps its own settings and check tables.
- Missing codes are merged with the project's own. A code with the same label
  as one in the project replaces it; the project's other codes are kept.
- A configuration file exported by an older version of DataSure has no check
  tables or missing codes. It still imports, with a warning, and you set
  those up again by hand.
- Whatever the file contains is applied without asking. An attribution for a
  submission that isn't in the imported data is kept but has no effect.

---

### Step 2: Import Data

**Purpose**: Load survey data from various sources

**What You'll Do**:

- Connect to data sources
- Import survey and backcheck datasets
- Preview imported data
- Verify data structure

#### Import Options

Import sources are added via the **"Add Import Configuration"** popover. Click it and select the import type from the **Import Type** dropdown.

##### Option A: SurveyCTO Integration

First save your SurveyCTO sign-in, once per server:

1. Under **Manage Credentials**, click **Add Credentials**
2. Enter:
   - **Server name**: The name of your SurveyCTO server, for example
     `myserver` for `myserver.surveycto.com`
   - **Email address**: Your SurveyCTO account email
   - **Password**: Your SurveyCTO password (stored securely in your OS
     keyring, never written to disk)
3. Click **Connect & Save Credentials**

**Remove Credentials** deletes a saved sign-in, including the password in
your OS keyring.

Then add each form:

1. Under **Import Data From Sources**, click **Add Import Configuration**
2. Select **"SurveyCTO"** from the Import Type dropdown
3. Choose the saved sign-in under **Select Server Credentials**
4. Choose the form under **Select Form ID**
5. Configure import settings:
   - **Alias**: A short name for the dataset
   - **Download attachments** (optional)
   - **File path for Private Key** (encrypted forms only)
   - **File path to save data** (optional)
6. Click **Add Form**
7. Click **Load Data** to download the data

> **Note**: Each refresh downloads every submission again, so refreshing a
> large or encrypted form takes about as long as the first import. Your data
> is complete either way. See [KNOWN_ISSUES.md](../KNOWN_ISSUES.md)
> (KI-015).

##### Option B: Local File

DataSure reads the file from where it is on your computer, so you enter its
path rather than uploading it. **Load Data** reads the file again, so a file
you update in place is picked up on the next load.

1. Click **Add Import Configuration**
2. Select **"local storage"** from the Import Type dropdown
3. Enter:
   - **Alias**: A short name for the dataset (up to 20 characters)
   - **File Path**: The file's full path, for example `C:/data/survey.dta`.
     Supported formats: .csv, .xlsx, .json, .dta (Stata), .parquet. Save
     legacy Excel (.xls) files as .xlsx first
   - **Sheet Name** (Excel files only)
4. Click **Add File**
5. Click **Load Data**

Use **Edit Import Configuration** to change a source, and **Remove Import
Configuration** to delete it with its imported, prepared and corrected data.

#### Preview Imported Data

After import, you'll see:

- **Dataset tabs**: Switch between imported datasets
- **Column information**: Names, types, counts
- **Sample data**: First 100 rows preview
- **Data metrics**: Total rows, columns, missing values

**Demo Data Includes**:

- **Survey Data**: 132 household survey responses
- **Backcheck Data**: 30 quality control validation records

Both datasets contain realistic data quality issues including:

- Missing data patterns
- Duplicate household IDs
- Inconsistent income reporting
- Missing demographic information

---

### Step 3: Prepare Data

**Purpose**: Clean and transform data for analysis

**What You'll Do**:

- Transform columns (dates, text, numeric)
- Add calculated columns
- Remove problematic data
- Apply preparation steps to multiple datasets

#### Choosing a Dataset

The buttons at the top of the page list your imported datasets. They wrap onto
more lines on projects with many forms. Only the selected dataset's
preparation steps, Change Log and preview load, so the page responds quickly.

- A dataset with no imported rows is muted and marked **not set up**.
  Selecting it explains what to import on the Import Data page.
- The selected dataset is part of the page address, for example
  `...?dataset=demo_survey`, and the page reopens on it next time.
- Every dataset stays available on Configure Checks, including datasets you
  never opened here.
- **Columns to show**, under **Preview Prepared Data**, limits the preview to
  the columns you pick. Your choice is remembered for each dataset, and
  **Reset filters** beside the preview header clears it.

#### Data Preparation Actions

##### Transform Column

Convert or modify existing column data:

**Available Transformations**:

- **String to Datetime**: Convert text dates to date format
  - Example: "2025-01-15 10:30:00" → datetime object
- **String to Uppercase**: Convert all text to uppercase
- **String to Lowercase**: Convert all text to lowercase
- **Extract Pattern**: Extract specific patterns from text
  - Example: Extract phone numbers, IDs, codes
- **Mathematical Operations**: Add, subtract, multiply, divide numeric values
  - Example: Calculate age from birth year
- **To String**: Convert a number, date, datetime or true/false column to
  text, keeping its name, so you can use it in **concat**
  - Whole numbers lose a trailing `.0` (`12.0` becomes `"12"`); other
    decimals are kept (`12.5` becomes `"12.5"`)
  - Dates become `YYYY-MM-DD`, datetimes `YYYY-MM-DD HH:MM:SS.ffffff`, and
    true/false becomes `"true"`/`"false"`
  - Missing values stay missing
- **To Number**: Convert a true/false column to whole numbers, keeping its
  name: true becomes `1` and false becomes `0`
  - Missing values stay missing
  - DataSure keeps true/false columns as they are when you import data. Use
    this step when you want them as 0/1, for example to use them in numeric
    checks

**Steps**:

1. Select the dataset
2. Click "Add data prep step"
3. Choose "Transform Column"
4. Select column to transform
5. Select transformation function
6. Configure parameters (if applicable)
7. Click "Add" to apply
8. Review transformed data

##### Add Column

Create new calculated or derived columns:

**Use Cases**:

- Add unique identifiers (UUID, sequential IDs)
- Calculate fields (total income, household density)
- Generate summary statistics
- Create categorical groupings
- Build a composite ID or full name by joining text columns (**concat**)

**Steps**:

1. Click "Add data prep step"
2. Choose "Add Column"
3. Enter new column name
4. Define calculation or value
5. Click "Add"

**Joining text columns (concat)**:

1. Choose the **concat** method.
2. Select two or more text columns in the order they should appear. Only text
   columns are listed: convert numbers or dates with the **To String**
   transform first.
3. Choose a separator: **None**, **Space**, **Comma**, **Underscore**,
   **Hyphen**, or **Specify** to type your own. A typed separator is used
   exactly as entered, including spaces.

For example, `region`, `district` and `hhid` joined with **Underscore** give
`R01_D05_123`. A missing value counts as empty, so the other values still
join. The new column is missing only when every selected value is missing.
If a re-import makes a selected column missing or no longer text, the step
is skipped and the rest of your steps still run.

##### Remove Column/Row

Delete unnecessary or problematic data:

**Remove Column**:

- Select columns to delete
- Useful for PII removal, irrelevant fields

**Remove Row**:

- Filter rows based on conditions
- Remove incomplete surveys
- Filter out test submissions

**Steps**:

1. Click "Add data prep step"
2. Choose "Remove Column" or "Remove Row"
3. Select column(s) or define row filter
4. Click "Add"

#### Change Log

All preparation steps are tracked:

- Action type
- Affected columns
- Timestamp
- Applied to which datasets

If your steps remove every row, the Prepare Data page warns you and keeps the
Change Log, so you can remove the step that caused it. Check pages show that
the dataset has no rows instead of running checks.

**Demo Example**:
Convert `submissiondate` column to datetime format for both survey and backcheck datasets:

1. Select the **demo_survey** dataset
2. Click "Add data prep step"
3. Select "Transform Column"
4. Choose "submissiondate" column
5. Select "string to datetime" function
6. Click "Add"
7. Repeat for **demo_backcheck** dataset

---

### Step 4: Configure Checks

**Purpose**: Set up data quality validation rules

**What You'll Do**:

- Create check configurations
- Map dataset columns to quality checks
- Connect survey and backcheck data
- Define validation parameters

#### Creating a Check Configuration

**Steps**:

1. Click "Add New Check Configuration" (+ button)
2. **Configuration Details**:
   - **Name**: Descriptive name of up to 20 characters (e.g., "Household HFCs")
   - **Survey Dataset**: Select main survey dataset (e.g., "demo_survey")

3. **Configure Key Columns**:
   - **Key Column**: Unique row identifier
     - Must be unique for every row
     - If none exists, create during data preparation
     - Example: "KEY", "uuid"
   - **ID Column**: Survey respondent identifier
     - May have duplicates (multiple visits)
     - Example: "hhid", "respondent_id"
   - **Enumerator Column**: Data collector identifier
     - Example: "enum_name", "enumerator_id"
   - **Date Column**: Submission/collection date
     - Must be in date format
     - Example: "submissiondate", "starttime"

4. **Optional Columns**:
   - **Team Column**: Team or group assignment
   - **Form Version Column**: Survey version field
   - **Duration Column**: Interview length field
   - **Target Number of Responses**: Expected total submissions

5. **Optional: Add Backcheck Dataset**:
   - Select backcheck dataset
   - Must have matching ID column
   - Used for validation comparisons

6. Click "Add Check Configuration"

#### What Happens Next

DataSure automatically creates a comprehensive quality analysis page with:

- **Summary Report**: Overall data quality metrics
- **Survey Progress**: Submission trends and targets
- **Duplicates**: Duplicate record detection
- **Missing Data**: Missing value analysis
- **Outliers**: Statistical outlier identification
- **Enumerator Stats**: Performance metrics by enumerator
- **Descriptive Stats**: Distribution analysis
- **Back Checks**: Validation error rates
- **GPS Checks**: Location data quality

**Demo Configuration**:

- **Name**: "Household HFCs"
- **Survey Dataset**: "demo_survey"
- **Key Column**: "KEY"
- **ID Column**: "hhid"
- **Enumerator Column**: "enum_name"
- **Date Column**: "submissiondate"
- **Team Column**: "team_id"; **Duration Column**: "duration"
- **Target Number of Responses**: 200 (optional)
- **Backcheck Dataset**: "demo_backcheck", with Backcheck Date
  "submissiondate", Backchecker "bcer_name", Backchecker Team "team_id" and
  Target Percentage 10

---

### Step 5: Review Reports

**Purpose**: Analyze data quality results and identify issues

**What You'll Do**:

- Open a check page from **DQA Reports** in the sidebar (one page per check
  configuration)
- Move between the quality checks on that page
- Review metrics and visualizations
- Identify data quality issues
- Export findings for action

#### Finding a Check

Each check page shows two rows of controls above the report:

1. **Group**: Overview, Data integrity, Field team or Exploration.
2. **Check**: the checks in the selected group.

| Group | Checks |
| --- | --- |
| Overview | Summary, Progress |
| Data integrity | Missing Values, Duplicates, Outliers & Constraints, GPS Checks |
| Field team | Enumerator Stats, Backchecks |
| Exploration | Descriptive Stats |

Every check is at most two clicks away. Choosing a group opens the check you
last used in that group, or its first check. Only the selected check runs, so
the page responds faster than when every check ran at once.

The page opens on the check you last viewed on it, or on **Summary** the first
time. The selected check is part of the page address, for example
`...?check=duplicates`, so you can bookmark or share a link to a check. A link
always opens the check it points to; a link to a check that does not exist
opens the last viewed check or Summary.

#### Remembered Filters

Each check remembers its filters, selections and sort order, such as
Summary's "Progress by" column and time period, the Progress time period and
extra attempted-interview columns, the Missing Values threshold, date,
grouping, comparison and correlation choices, the duplicates sort order, the
outlier table toggles and inspected column, the extra columns shown in the
duplicates and outliers reports, the GPS map colour and filter, detection
method, Auto-Clustering **Number of Neighbors** and **Expected Outlier
Proportion**, clustering column and distance threshold, the enumerator summary
information, periods, columns and statistics, the backcheck comparison filters,
productivity period and staff statistics view, and the Descriptive Stats
histogram and value counts choices. They stay set when you switch to another
check and back, and when you reopen the app.

- Pagination, search boxes and the inputs in dialogs always start fresh.
- A remembered value that no longer matches your data, for example an
  enumerator, column or dataset that was removed, is dropped quietly and the
  filter goes back to its default.
- **Reset filters**, beside each check's settings (or its title, on Missing
  Values and Descriptive Stats), clears that check's remembered filters only.
  Its settings and the other checks' filters stay.
- Remembered filters are personal. They are not included when you export a
  project configuration, apply one to a project, or build a replication
  package.

#### Check Status

A check that cannot show results yet is muted in the check row, with an icon
and a text marker:

- **not set up**: something you can configure is missing, for example
  Backchecks with no backcheck dataset or Outliers & Constraints with no
  columns added. Opening the check explains what is missing and shows its
  settings below the message ("Set it up below"). Backchecks instead says
  to fix it on the page linked below, and links to Configure Checks or
  Import Data, where its dataset is chosen and imported.
- **not applicable**: your data cannot support the check, for example GPS
  Checks when no column looks like GPS data, or Backchecks when the
  backcheck dataset has no rows. Opening the check explains why and still
  shows the check's settings, so you can, for example, add a GPS column
  configuration for columns with other names. GPS Checks is ready as soon as
  a saved GPS column configuration uses columns in the data.
- **error**: the check failed. It shows the error and an **Error details**
  section to include in a bug report. The other checks keep working.

Muted checks can still be opened.

*Detailed report information is provided in the [Quality Check Reports](#quality-check-reports) section below.*

---

### Step 6: Correct Data

**Purpose**: Fix identified data quality issues, or record that a flagged value
is correct

**What You'll Do**:

- Correct a flagged record from the check page that flagged it, or any record
  from the Correct Data page
- Accept outliers, constraint violations and GPS outliers that are correct
- Attribute back check mismatches to whoever caused them
- Review, filter and undo entries in the Correction Log

#### Where to Make Corrections

You can correct data from the check pages and from the Correct Data page. Both
write to the same Correction Log, one per dataset, so a change made in one
place shows up in the other and in every report that uses the dataset.

| Page | What you can do | Details |
| --- | --- | --- |
| Outliers: constraint violations and outlier inspection tables | modify value, remove value, accept | [Correcting or Accepting Flagged Values](#correcting-or-accepting-flagged-values) |
| GPS Checks: outliers table | modify coordinates, remove coordinates, remove observation, accept | [Correcting or Accepting GPS Outliers](#correcting-or-accepting-gps-outliers) |
| Duplicates: ID duplicate cards | Keep, Modify ID or Drop each record | [Resolving a card](#resolving-a-card) |
| Back Checks: Comparison Details | attribute a mismatch to the Enumerator, Backchecker or Respondent (the data is not changed) | [Attributing Mismatches](#attributing-mismatches) |
| Correct Data | modify value, remove value, remove row, for any KEY and column | [Correction Actions](#correction-actions) |

On the Outliers and GPS Checks pages, click **Review** on a flagged row to open
a correction form with the KEY and current value filled in: one column on
Outliers, the latitude and longitude pair on GPS Checks. You correct one record
at a time. After you save, the page reloads and shows a confirmation. A
correction applies to every row with the same KEY.

Duplicates and Back Checks work differently. Duplicate and unmatched IDs are
resolved on per-ID cards (see [Resolving a card](#resolving-a-card)), and back
check mismatches are attributed rather than corrected, one or several at a
time (see [Attributing Mismatches](#attributing-mismatches)).

The Correct Data page keeps working as before, for any record, including ones
no check flagged. It is also the only place to undo a correction or an
acceptance. It lists acceptances but can't create them, because it has no
check flag to accept.

#### Choosing a Check Page

The buttons at the top of the Correct Data page list your check pages, one per
check configuration. They wrap onto more lines on projects with many forms.
Only the selected check page's corrections load.

- The page opens on the check page you last reviewed, also after you reopen
  the app, so you can fix what you found straight away. Otherwise it opens
  on the check page you last chose here, or on the first one.
- The selected check page is part of the page address, for example
  `...?page=household_hfcs`. A link always opens the check page it points to.
- A check page with nothing to correct is muted and marked **not set up**: it
  has no survey KEY column configured, or its survey data has not been
  imported. Selecting it explains what is missing.
- The **Survey data** / **Backcheck data** choice and the Correction Log
  filters are remembered for each check page, also after you reopen the app.
  **Reset filters** clears them for the selected check page.

#### Accept as Valid

**accept** records that a flagged value was reviewed and is correct, without
changing the data. It is offered for outliers, constraint violations and GPS
outliers only:

- A reason is required.
- An acceptance covers one check, one KEY and one column: accepting an outlier
  does not accept a constraint violation on the same value. A GPS acceptance
  covers the KEY's latitude and longitude together.
- Accepted flags are hidden from the tables and left out of the metrics. Turn
  on **Show reviewed** to see them again, highlighted in green.
- An acceptance lapses, and the value is flagged again, if the value changes
  (for GPS, if either coordinate changes).
- Accepting a **hard** constraint violation needs an extra confirmation, and
  the entry is highlighted in red in the Correction Log.

Duplicates and back checks can't be accepted. An ID belongs to one record, so
a duplicate ID is resolved on its card or left out with **Records to
Include**. Back check results measure data collection quality, so a mismatch
is attributed instead.

#### Back Check Mismatches

The Back Checks page never changes survey or back check data. Instead, click
**Review** on a mismatch in Comparison Details and attribute it to the
**Enumerator**, the **Backchecker** or the **Respondent**. To attribute several
mismatches at once, select their rows first. Attribution leaves the mismatch
counts and the regular error rate unchanged. The statistics show an **adjusted
error rate** next to the error rate. There are two: the enumerator adjusted
rate leaves out mismatches attributed to the back checker or the respondent,
and the back checker adjusted rate leaves out those attributed to the
enumerator or the respondent. Attributions are kept in their own
attribution log, not in the Correction Log. See
[Attributing Mismatches](#attributing-mismatches).

#### Duplicate and Unmatched IDs

All ID problems are resolved in the Duplicates check, where each duplicate ID
has a card that compares its records side by side. A **Survey data** /
**Backcheck data** switcher adds cards for duplicate back check IDs and for
back checks whose ID is not in the survey data. Choose **Keep**, **Modify ID**
or **Drop** for each record, then save the card once with one reason. Either
every correction on the card is saved or none are. Save is allowed only when
at most one included record keeps the ID. See
[Resolving a card](#resolving-a-card).

A repeat visit that legitimately shares an ID, such as a failed first attempt
followed by a completed interview, is handled with the **Records to Include**
filter in the [Duplicates Settings](#duplicates-settings) instead. The Back
Checks comparison uses the same filters, and leaves out unresolved duplicate
IDs until they are resolved in the Duplicates check.

#### Correction Actions

These actions are on the Correct Data page.

##### Modify Value

Change specific field values:

**Use Cases**:

- Fix typos in IDs
- Correct miscoded responses
- Update incorrect dates

**Steps**:

1. Click "Add correction step" (+ button)
2. **Select Key**: Choose record to modify
3. **Select Action**: "modify value"
4. **Select Column**: Choose field to modify
5. **Current Value**: Auto-populated
6. **New Value**: Enter correct value
7. **Reason**: Document why (required)
8. Click "Apply"

##### Remove Value

Replace specific value with null/missing:

**Use Cases**:

- Invalid responses
- Data entry errors
- Out-of-range values

**Steps**:

1. Click "Add correction step" (+ button)
2. **Select Key**: Choose record
3. **Select Action**: "remove value"
4. **Select Column**: Choose field
5. **Reason**: Document why (required)
6. Click "Apply"

##### Remove Row

Delete entire survey records:

**Use Cases**:

- Test submissions
- Duplicate surveys (after investigation; the Duplicates check cards are
  quicker, see [ID Duplicates](#id-duplicates))
- Invalid records

**Steps**:

1. Click "Add correction step" (+ button)
2. **Select Key**: Choose record to remove
3. **Select Action**: "remove row"
4. **Reason**: Document why (required)
5. Click "Apply"

#### Correction Audit Trail

All corrections are tracked with:

- Record identifier (key)
- Column modified
- Original value
- New value
- Action type
- Reason for correction
- Timestamp
- Status of the last reapply, with the reason if it failed
- Source: the page that made the entry: `corrections_page` (the Correct Data
  page), `outliers`, `constraints`, `duplicates` or `gps`
- User: who made the entry. This is your computer login unless you set a
  **Reviewer name** in the sidebar, which DataSure remembers across sessions.
  Entries logged before DataSure recorded the user show an empty User.

The replication package includes the full log as
`4_output/3_logs/correction_log.csv`, User column included. Before sharing a
package outside your team, check **Exclude reviewer names** on the Export
Replication Package page, then build the package. The User column is kept
but left blank in the exported copy. The project's own Correction Log is not
changed. The option is off by default.

The log can also contain **accept** entries. An accept entry records that a
flagged value was reviewed and is correct. It never changes the data, and the
Check type column shows which check it applies to. It stays in effect only
while the value is unchanged; once the value changes, its Status shows
`Inactive` with the reason. Accept entries are kept in `correction_log.csv`
in the replication package but are not part of the corrections script. You can
remove an accept entry with "Remove correction step" like any other entry.
Accepting a hard constraint violation sets Severity to `hard`, and those rows
are highlighted in red.

To blank a cell, use "remove value": "modify value" needs a non-empty new
value (`0` is valid).

If corrections or prep steps remove every row, the page warns you. The
Correction Log and "Remove correction step" stay available, so you can remove
the entry that caused it. There are no records left to add corrections to.

##### Filtering the Log

Above the Correction Log, **Source** and **Action** filters list the sources
and actions that appear in the log. Select one or more values to show only
the matching entries; with nothing selected, a filter shows everything. The
two filters combine, so selecting the `gps` source and the `accept` action
shows only GPS acceptances. While a filter is on, a caption counts the entries
shown out of the total; if nothing matches, a message says so instead. The
filters only change what the table shows: "Remove correction step"
still lists every entry.

#### Correcting Back Check Data

On a page with back check data, a **Survey data** / **Backcheck data**
switcher under the check page name picks the dataset. The back check data
has its own Correction Log, removal list and preview. Back check results
measure data quality, so on back check data you can only modify the ID (the
Survey ID column set in the Backchecks settings) or remove a row. Back
check data that was never prepared is corrected from its imported data. The
Duplicates check has the same switcher, and its back check cards write to the
back check data's Correction Log.

#### Verifying Corrections

Reports read the corrected data every time they load, so there is nothing to
refresh:

1. After saving on a check page, the page reloads with the correction applied.
   After saving on the Correct Data page, open the report again.
2. Check that the flag is gone. On the Outliers page, turn on **Show
   reviewed** to see corrected values marked Corrected.
3. In the Correction Log, check that the entry's Status is `Successful`. If
   new data or a prep change means a correction can no longer be applied, its
   Status shows why. This includes a correction of a blank value that was later
   filled in at source: the source value is kept and the correction fails.

**Demo Example**:
Correcting duplicate household ID:

**Issue**: Two records with same hhid "UP015-005"
**Investigation**: One record has typo, should be "UP015-055"

**Steps**:

1. Open the Duplicates check and find the card for "UP015-005"
2. On the record with KEY "uuid:0dk0vt97-786b-250u-34k7-z34615zz820c",
   choose **Modify ID** and enter "UP015-055"
3. Leave the other record on **Keep**
4. **Reason**: "Wrong ID entered"; **Note**: "Typo confirmed with the field
   team"
5. Click **Save**. The card disappears and **Resolved** goes up by one.

The same correction can be made on the Correct Data page with "modify value"
on the "hhid" column.

---

### Step 7: Replication Package

**Purpose**: Export everything needed to reproduce your corrected dataset

On the **Export Replication Package** page, select a check page under **Page
Name**, review **Selected page details** and **What's inside the zip?**, then
click **Build Replication Package**. Confirm the PII notice and click
**Download replication package (.zip)**. See
[Correction Audit Trail](#correction-audit-trail) for the **Exclude reviewer
names** option.

---

## Quality Check Reports

### Summary Report

**Purpose**: High-level overview of data quality

#### Sections

##### Summary Settings

Configure global parameters:

- **Survey Date**: Submission date column
- **Total Expected Interviews**: Target sample size

##### Data Summary

Quick dataset overview:

- String columns count
- Numeric columns count
- Date columns count
- Total rows

##### Submission Details

Submission patterns:

- Today's submissions
- This week's submissions
- This month's submissions
- Total submissions
- **Submission Trend Chart**: Line chart showing submissions over time

##### Progress

Collection progress metrics:

- **Progress Bar**: Percentage of target achieved
- Average submissions per day
- Average submissions per week
- Average submissions per month

**Progress by Subgroups**:

- Select categorical column (state, region, enumerator)
- View progress by category
- Toggle time intervals (Auto, Daily, Weekly, Monthly)

##### Check Health

After Progress, Summary lists every other check in one row each, so you can see
where to start triage. The rows are grouped like the check navigation
(**Overview**, **Data integrity**, **Field team** and **Exploration**) under
one shared column header, and each check sits in its own box. Each row shows:

- **Check**: the check's name
- **Status**: a coloured pill with an icon and a label, so the status does not
  rely on colour alone
- **Outstanding**: the issues still to deal with, with a detail line under the
  number. For a check that is not ready, the reason instead
- **Resolved**: the issues already resolved through corrections, acceptances
  or error-source attributions, or "—" for checks that resolve nothing or
  when the count can't be worked out
- **Open →** or **Set up →**

| Status | Colour | When |
| --- | --- | --- |
| **Not set up** | Grey | The check needs settings first |
| **Not applicable** | Grey | The check has nothing to work with on this page, for example GPS Checks without a GPS column |
| **Error** | Red | The check failed, or its numbers could not be worked out, for example because its saved settings no longer fit the data. The detail line says why; the other rows still show |
| **Flagged** | Amber | The check is ready and has more than 0 outstanding issues |
| **No issues** | Green | The check is ready and has 0 outstanding issues. Progress, Enumerator Stats and Descriptive Stats only describe the data, so they are green when ready |
| **Ready** | Blue | The check is ready, but Summary does not count its issues, so it makes no claim about them. Open the check to see them. GPS Checks shows this until outliers can be detected (fewer than 6 points for Auto-Clustering, or no clustering column chosen for Cluster by Column), as does Backchecks when no values were compared |

| Check | Outstanding | Detail | Resolved |
| --- | --- | --- | --- |
| Progress | Submissions out of the target, for example "310 / 500", or the submissions when no target is set | Share of the target reached | — |
| Missing Values | Share of columns where every value is missing, counting missing codes | "of columns all missing (5 of 40)" | — |
| Duplicates | Duplicate survey IDs not yet resolved, after Records to Include | "duplicate IDs" | Duplicate IDs resolved through corrections |
| Outliers & Constraints | Outliers plus constraint violations, leaving out accepted flags | For example "3 outliers (1.4% of values), 1 constraint violation" | Flags accepted as valid, and corrected values that were flagged before the correction and are no longer flagged, once for each check that flagged them. Correcting a value that was never flagged does not count |
| GPS Checks | The check's **Outliers Detected**: GPS outliers not yet accepted, for the GPS configuration, detection method and settings last chosen in the outliers section | For example "GPS outliers (4.00% of 250 points)" | Points accepted as valid, and points whose coordinates were corrected or that were removed from the GPS outliers table and are not outliers now. Each point counts once |
| Enumerator Stats | Enumerators active in the past 7 days, out of all enumerators | "active in the past 7 days" | — |
| Backchecks | Mismatches with no error source attributed | The total error rate, for example "4.25% error rate" | Mismatches attributed to the enumerator, backchecker or respondent |
| Descriptive Stats | Status only | — | — |

Backchecks counts unattributed mismatches rather than the error rate because
the error rate is above 0 on nearly every project and would keep the row amber.
Review each mismatch on the Backchecks tab and attribute it to an error source
to move it from Outstanding to Resolved.

A GPS point whose coordinates were corrected but that the check still flags as
an outlier stays in **Outstanding**, not **Resolved**: the correction did not
fix it. Accept it as valid, or correct it again, to resolve it. Only corrected
points that are no longer outliers count as resolved.

Each number is the number the check itself shows. The numbers are worked out
again only when the data, the check's settings or its corrections change, so
Summary stays quick. For GPS Checks, changing the GPS configuration, detection
method, clustering column or Auto-Clustering sliders in the outliers section
also counts again; other GPS view choices, such as the map colour, do not. The
GPS count needs no Mapbox token.

###### Comparison period

The collapsible **Comparison period** box above the rows sets what the
**Change** column compares with. "Today" is your computer's date.

| Option | Compares with |
| --- | --- |
| **Day** (default) | The end of yesterday |
| **7 days** | The end of the day 7 days ago |
| **Week** | The start of this week. Choose the first day of the week under **Week starts on** (default Sunday) |
| **30 days** | The end of the day 30 days ago |
| **Month** | The start of this month (the 1st) |

The choice is one setting for the whole project: it applies to Summary on
every check page and is remembered next time. It is personal, so project
exports leave it out.

Each check is worked out again on the submissions dated on or before the start
of the period, and compared with now. Submissions without a date never count
as new.

| Check | Change shows |
| --- | --- |
| Progress | New submissions dated in the period, for example "▲ 12 new submissions since yesterday" |
| Missing Values | The change in the share of columns all missing, in percentage points, for example "▼ 2.50 pp since yesterday" |
| Duplicates | Unresolved duplicate IDs held by a submission dated in the period, for example "▲ 3 new since yesterday". An ID that was already duplicated before the period counts when a submission in the period joins it |
| Outliers & Constraints | Flags on submissions dated in the period that are not accepted or corrected. The flags are not worked out again on the earlier submissions, since that would move the outlier bounds |
| GPS Checks | GPS outliers on submissions dated in the period that are not accepted, for example "▲ 2 new since yesterday". Outliers are not detected again on the earlier submissions, since that would change which points stand out |
| Enumerator Stats | The change in enumerators active in the past 7 days, for example "▲ 2 more active since yesterday" |
| Backchecks | Unattributed mismatches on backchecks dated in the period |

Under **Resolved**, "+N since …" counts the resolutions made in the period
that are still in effect: corrections and acceptances from the correction log
(Duplicates, Outliers & Constraints, GPS Checks) and error-source attributions
(Backchecks). A duplicate ID counts when it was still duplicated at the start
of the period and a correction made in the period removed one of its records,
or changed or removed its ID; correcting another column of a record with that
ID does not count, and neither does a later correction to an ID that was
already resolved. The other checks follow the same rule: a flag, GPS point or
mismatch counts only if it was not yet resolved at the start of the period. A
flag that was accepted or corrected before the period and corrected again in
it does not count, and nor does a GPS point first accepted or corrected
before the period, or a mismatch attributed before the period and
re-attributed in it. An undone correction, an acceptance whose value has changed since,
and an attribution later changed back to Unattributed drop out.

If a row's change cannot be worked out, **Change** shows an error marker and
the reason instead of a number, and the row keeps its other numbers. Open the
check to see what is wrong.

The rows use Summary's date column: the date set in Summary's settings, else the
page's survey date. The Backchecks row uses the backcheck date column from its
settings. A caption under the box shows the latest submission date, so a
change of zero is explained. A row without a date column shows "—" in
**Change**. When no row has a date column, the box and the **Change** column
are hidden and Summary says "Set a date column in Summary settings to see
changes over time."; the Resolved totals still show.

Changes are worked out once per comparison period and kept with the other
numbers, so switching back to a period you have already viewed is instant.

Click **Open →** on a row to go to that check, or **Set up →** to open a check
that is not set up and configure it. Both update the page address, like
choosing the check in the navigation. Checks that do not apply to your data
have no button; their row says why.

---

### Progress Report

**Purpose**: Detailed submission tracking and progress monitoring

#### Sections

##### Progress Settings

Configure parameters:

- **Survey ID**: Respondent identifier
- **Survey Key**: Unique row identifier
- **Date**: Submission date column
- **Enumerator**: Data collector column
- **Target Number of Interviews**: Expected total
- **Target Submissions Per Period**: Target rate per time interval

##### Progress Summary

High-level metrics:

- Submission progress (%)
- Target interviews
- Total submitted interviews

##### Submission Trends

Visualize collection patterns:

- **Time Interval Toggle**: Day, Week, Month
- Line chart showing cumulative submissions
- Identify collection peaks and gaps

##### Attempted Interviews

Track multiple attempts:

- Total submitted interviews
- Number of unique IDs
- Min/Max attempts per respondent
- **Bar chart**: Attempts over time
- **Data table**: Attempts by respondent ID

##### Consent and Completion Progress

Monitor survey completion:

- **Consent Rate**: % who provided consent
- **Completion Rate**: % who completed survey

**Setup**:

- Consent column and value (e.g., "consent" = "yes")
- Completion column and value (e.g., "completion_status" = "complete")

---

### Duplicates Report

**Purpose**: Find survey and back check records that share an ID, and back
checks whose ID is not in the survey data

#### Sections

##### Duplicates Settings

Configure detection:

- **Survey ID**: Main identifier to check
- **Survey Key**: Unique key column
- **Date**: Submission date
- **Enumerator ID**: Data collector identifier
- **Records to Include**: Check only the records that match a condition, for
  example `consent == Yes`. Use it to leave out a failed first visit when the
  enumerator interviewed the respondent again under the same ID. Pages with
  back check data have a separate **Backcheck Records to Include** filter.
  Each page keeps its own filters. A filter that matches no records shows a
  warning and checks no records.

##### ID Duplicates

A **Survey data** / **Backcheck data** switcher picks the dataset. Each option
shows its number of unresolved duplicate IDs, for example **Survey data (3)**.
On pages without back checks, the option reads **Backcheck data (N/A)** and
cannot be selected. The back check view uses the Survey ID and Survey Key set
in the Backchecks settings.

Metrics above the cards:

- **Duplicate IDs**: IDs shared by two or more records
- **Records involved**: Records that share an ID
- **Missing IDs**: Records with no ID
- **Unmatched IDs** (back check view): Back checks whose ID is not in the
  survey data
- **Resolved**: Duplicate IDs that corrections have resolved, made on the
  cards or on the Correct Data page

Each duplicate ID has a card showing its record count and date range. The card
compares the records side by side, one column per record, and highlights the
fields that differ. By default it shows the KEY, date, enumerator (back checker
in the back check view) and team, plus the columns chosen in **Show more
columns in report**. Turn on **Compare all fields** to see every column, and
**Only differing fields** to hide fields that are the same in every record.

In the back check view, each unmatched back check has its own card with its
KEY, ID, date and back checker.

Search by ID or KEY, sort by group size or latest date, and move between pages
of 10 cards. **Download duplicates (CSV)** exports every record on the cards
that match the search, across all pages, with the displayed columns.

##### Resolving a card

An ID belongs to one record, so a duplicate ID can't be accepted as valid. A
repeat visit that legitimately shares an ID, such as a failed first attempt
followed by a completed interview, is handled with **Records to Include**
instead.

Each card lists its records with a choice of **Keep**, **Modify ID** or
**Drop**. **Modify ID** asks for the new ID. Choose a **Reason** and enter a
**Note**, then click **Save**. Save stays disabled, with a message saying
what's missing, until:

- at most one record keeps the ID;
- every new ID is filled in, differs from the current ID and from the other
  new IDs, fits the ID column (a number for a numeric ID), and is not already
  held by an included record (the message names that record's KEY); and
- a reason and a note are given.

Dropping every record removes the ID from the data, so it asks for a
confirmation first. An unmatched back check card offers **Modify ID** or
**Drop**; its new ID must be an ID in the survey data.

One save logs one correction per changed record, with the reason and note on
each, in the survey or back check data's Correction Log, with source
`duplicates`. Either every correction is saved or none are. The card then
disappears. A caption above the cards counts the corrections logged in this
session and links to the Correction Log, which is where you undo one: remove
it there, and the card comes back if the ID is duplicated again. A record with
no KEY, or whose KEY is also on another record (even one Records to Include
hides), can't be corrected on a card, because a correction applies to every
row with its KEY.

##### Other Duplicates

Shown in the survey view only. Check duplicates in non-ID columns:

- Phone numbers
- Addresses
- ID numbers
- Other identifiers

---

### Missing Values Report

**Purpose**: Analyze missing value patterns

#### Sections

##### Missing Data Settings

Configure missing codes:

- **Missing Labels**: Category names (Don't Know, Refused, N/A)
- **Missing Codes**: Numeric codes (-99, -88, -77)
  - Multiple codes separated by commas
  - Decimal codes such as `.999` are supported for surveys that used them.
    They only match columns that hold decimals, so `.999` never marks a `0`
    as missing in a whole-number column

Numeric codes count as missing, not as values, on the other checks: Outliers &
Constraints don't flag them, and Descriptive Stats and the enumerator
statistics leave them out of the mean, minimum and other statistics. Back
checks use their own settings for values to exclude.

##### Missing Data Statistics

Overview metrics:

- % overall missing values
- % columns with missing values
- % columns with at least one missing
- % columns with no missing values

##### Missingness by Column

Detailed column-level analysis:

- Column name
- Total missing count and %
- Null values count and %
- Don't Know count and %
- Refused to Answer count and %
- Not Applicable count and %
- **Sortable table**: Sort by any column
- **Filter slider**: Show columns with minimum % missing

##### Compare Missing Data Within Groups

Group-level comparison:

- Select grouping column (enumerator, region, state)
- Select columns to compare
- Table showing % missing by group

##### Missingness Over Time

Temporal patterns:

- Select date column
- Line chart showing % missing over time
- Identify data quality trends during collection

##### Nullity Correlation

Missing data relationships:

- Select columns to analyze
- Heatmap showing correlation of missingness
- Identify systematic missing patterns

##### Nullity Matrix

Visual representation:

- Matrix of all records and columns
- Red blocks: missing values
- Blue blocks: non-missing values
- Quickly identify problem areas

---

### Outliers & Constraints Report

**Purpose**: Detect statistical outliers in numeric data

#### Sections

##### Outliers Settings

**Admin Settings**:

- Survey ID
- Survey Key
- Enumerator ID

**Display Settings**:

- Display columns to show in report
- Minimum threshold (min non-missing values required)

**Outlier Columns Configuration**:
Click "Add Outlier Column" (+ button):

- **Search Type**: How to find columns
  - "exact": Specific column names
  - "contains": Partial match (e.g., "land" finds "land_acre", "land_rent")
  - "startswith": Prefix match
  - "endswith": Suffix match
  - "regex": Regular expression pattern

- **Select Columns**: Choose numeric columns to check

- **Detection Method**:
  - **IQR (Interquartile Range)**: Default, robust to extreme values
  - **Standard Deviation**: More sensitive to outliers

- **Multiplier**: Sensitivity threshold
  - IQR default: 1.5
  - SD default: 3.0
  - Lower values = more outliers detected

- **Soft Minimum** (optional): Values below automatically flagged

- **Soft Maximum** (optional): Values above automatically flagged

##### Outlier Statistics

Overview metrics:

- Variables checked
- Outlier variables (columns with outliers)
- Number of outliers found

##### Outlier Summaries

Column-level statistics table:

- Column name
- \# of values (non-missing)
- \# of outliers
- Min/Max values
- Mean/Median
- Standard deviation
- Interquartile range
- Lower/Upper bounds

##### Outlier Details Table

Record-level outlier information:

- Key column
- Survey ID
- Enumerator ID
- Column name
- Outlier value
- Column statistics
- Outlier reason
- Detection parameters

##### Inspect Outlier Columns

Visual analysis:

- Select outlier column to visualize
- **Statistics display**: All relevant metrics
- **Box Plot**: Distribution with outliers highlighted
- **Table**: All records with outlier indicators

##### Correcting or Accepting Flagged Values

Above each of the constraint violations and outlier inspection tables,
**Show only flagged values** (on by default) limits the table to flagged
values. Turn it off to see every checked value.

Each row of the constraint violations table and the outlier inspection table
starts with a **Review** button. Click it to open a correction form in a
dialog, with the KEY, column and current value filled in. Choose an action,
enter a reason and click "Apply":

- **modify value** or **remove value** corrects the data. The page reloads, and
  the flag is updated or disappears.
- **accept** records that the flagged value is correct. The flag is hidden
  and no longer counted in the metrics. Turn on "Show reviewed" to see
  accepted flags highlighted in green, with a Reviewed badge and the reason.

"Show reviewed" also highlights corrected values in green, with a Corrected
badge and the correction's reason. A corrected value that is now in range is
no longer flagged, so turn off "Show only flagged values" to see it. A
corrected value that is still flagged stays in the table and in the metrics
until it is fixed or accepted. The badge clears if the value changes again.

Turn on **Show only reviewed** to list only accepted and corrected values. While
it is on, the other two toggles are disabled.

Outlier and constraint acceptances are separate: accepting an outlier does not
accept a constraint violation on the same value. Accepting a **hard**
constraint violation needs an extra confirmation. An accepted flag comes back
if the value changes, or if you remove the acceptance on the Correct Data page.
Every entry appears in the Correction Log with source `outliers` or
`constraints`.

Corrections and acceptances apply to every row with the same KEY. If a KEY is
on more than one row with different values in the flagged column, Review shows
a warning instead of the form, because a correction would change all those
rows. Give each record a unique KEY in the source data first. The Duplicates
check lists duplicated KEYs.

---

### Enumerator Stats Report

**Purpose**: Monitor enumerator performance and data quality

#### Sections

##### Enumerator Settings

Configure parameters:

- **Date**: Submission date column
- **Form Version**: Survey version used
- **Survey ID**: Respondent identifier
- **Duration**: Interview length column
- **Enumerator**: Data collector column
- **Team**: Team/group assignment
- **Consent**: Consent column and value
- **Outcome**: Completion column and value

The report uses the consent and outcome settings as soon as you change them,
and again after every data refresh; there is nothing to apply. Each check
page keeps its own consent and outcome settings. The % consent and %
completed columns appear in the Enumerator Summary only once you choose both
a column and its values.

##### Enumerator Overview

High-level metrics:

- Total enumerators
- Total teams
- Active enumerators (past 7 days)
- % active enumerators
- Min/Max/Average submissions
- Total submissions

##### Enumerator Summary Table

Detailed performance by enumerator:

- Enumerator ID
- First/Last submission dates
- \# submissions (total, today, this week, this month)
- \# unique dates active
- \# null values in submissions
- Duration stats (min, max, mean, median)
- % consent rate
- % completion rate

Today, this week and this month are counted from your computer's date, not the
latest submission in the data, and so is "active in the past 7 days" in the
Enumerator Overview. Weeks start on Monday. If fieldwork has paused or the data
hasn't been refreshed, these counts can be 0. The note under the table shows
the latest submission date ("Data as of").

##### Enumerator Productivity

Visualize productivity over time:

- Heatmap showing submissions per enumerator
- Toggle: Day, Week, Month views
- Identify high/low performers

##### Enumerator Statistics

Compare statistics by enumerator:

- Select column to analyze
- Select statistics (count, mean, median, min, max, std, 25th, 75th percentile)
- Table showing values per enumerator
- Identify outlier enumerators

##### Enumerator Statistics Over Time

Temporal performance trends:

- Select column
- Select statistic
- Toggle: Day, Week, Month
- Line chart per enumerator
- Track performance changes

---

### Descriptive Stats Report

**Purpose**: Understand variable distributions

#### Sections

##### Descriptive Stats Settings

Configure analysis:

- Select columns to analyze, then click **Apply Selection**
- Separate report per column

Each check page keeps its own column selection. After upgrading from a
version that shared one selection across pages, each page starts from that
shared selection, keeping only the columns in the page's dataset.

##### For Each Selected Column

**Basic Statistics Toggle**:

- ON: Show only count, mean, std, min, 25%, 50%, 75%, max
- OFF: Show extended statistics

**Table Type Selection**:

1. **One-Way Table**: Single variable distribution
2. **Two-Way Table**: Cross-tabulation with another variable
3. **Summary Statistics**: Descriptive statistics only

##### Visualizations

Depending on data type:

- Histograms (numeric)
- Bar charts (categorical)
- Box plots (numeric with groups)
- Frequency tables

---

### Backchecks Report

**Purpose**: Validate survey data against quality control visits

#### Sections

##### Back Checks Settings

Configure validation:

- **Survey ID**: Respondent identifier
- **Survey Key**: Unique row identifier
- **Enumerator**: Original data collector
- **Back Checker**: QC validator
- **Date**: Back check date
- **Backcheck target (%)**: Share of surveys to back check (e.g., 10%).
  Pre-filled from the page configuration. A value you enter here is saved and
  overrides the page configuration; clear it to fall back. If neither is set,
  10% is used and a warning is shown.
- **Error rate target (%)**: Optional. The highest acceptable error rate. In
  the enumerator and back checker statistics, every error rate and adjusted
  error rate above it is highlighted, each column on its own. Leave blank to
  highlight nothing.
- **Eligibility Filter**: Optional survey column and values that mark a survey
  eligible for back checks (e.g., `consent` in `1`). Only eligible surveys
  count towards coverage.

The comparison and coverage use the records kept by the **Records to Include**
filters in the Duplicates check: the survey filter for survey data and the
**Backcheck Records to Include** filter for back check data. When a filter is
set, the page says so, for example "Comparing 1,240 of 1,310 surveys (Records
to Include: interview_status == Complete)". Records whose survey ID is
duplicated, in the survey or the back check data, are left out of the
comparison and of coverage until the duplicate is resolved.

##### Backchecks Summary

A row of counts (survey observations, back check observations, enumerators and
back checkers) and **Mismatches Attributed**, the share of mismatches given an
error source (see [Attributing Mismatches](#attributing-mismatches)). Then a
**Targets** section with two metrics side by side:

- **Backcheck Coverage**: Share of eligible survey IDs (leaving out
  duplicated IDs) with a matching back check, and how many points it is
  above or below the target. It is calculated before any back check columns
  are configured.
- **Backchecks vs Expected**: When the page configuration sets the target
  number of survey responses, back checks done against the back checks
  expected (survey target × target %, rounded up), and how many back checks
  above or below that it is. Values over 100% are shown as is.

Below the targets, an **Error Rates** section has one card for the total error
rate and one for each category. Each card shows mismatches ÷ values compared
over every back check. Its grey delta is the enumerator adjusted error rate,
and the card's help gives the back checker adjusted error rate (see
[Attributing Mismatches](#attributing-mismatches)). A category with no values
compared shows N/A, with "No values compared" in place of the delta. The cards
appear once back check columns are configured.

**Add Back Check Columns**:
Click "Add a back check column" (+ button):

- **Column**: Variable to validate
- **Category**: Grouping (1, 2, 3 for analysis)
- **OK Range**: Acceptable difference for numeric values
- **Comparison Condition**:
  - "ignore_missing_values": Skip if missing in either dataset
  - "compare_all": Compare all, including missing

##### Back Check Trends by Category

Metrics per category:

- Number of columns
- Number of values compared
- % discrepancies found

##### Error Trends

Visualize error rates over time:

- Line chart showing % discrepancies
- Filter by category
- Toggle time period (Daily, Weekly, Monthly)

##### Column Statistics

Detailed column-level validation:

- Column name
- Data type
- Category
- \# surveys, backchecks, compared
- \# different values
- Error rate (%)
- \# mismatches attributed to the enumerator, the back checker and the
  respondent, and \# still unattributed (there is no adjusted rate per column)

##### Enumerator Statistics

Performance by original enumerator:

- Enumerator ID
- Surveys: eligible unique submissions
- Backchecks: how many of those were back checked
- Coverage % and points vs target (coverage below target is highlighted;
  enumerators with no back checks show 0%)
- \# values compared
- \# different values
- Error rate (%) and adjusted error rate (%), by category and in total

##### Back Checker Statistics

Performance by validator:

- Back Checker ID
- Backchecks: unique surveys back checked
- \# values compared
- \# discrepancies
- Error rate (%) and adjusted error rate (%), by category and in total

##### Comparison Details

Record-level validation results:

- Survey ID
- Enumerator
- Back Checker
- Survey value
- Back check value
- Comparison result
- Error source, for mismatches
- Column name

##### Attributing Mismatches

Back check results measure how well data was collected, so the Back Checks
page never changes survey or back check data. There is no way to accept a
mismatch as valid or to replace a survey value with the back check value.
Expected differences, such as "Don't know" against "Refused", belong in the
exclude and no-differences lists in the settings. The comparison uses the
corrected survey data, so corrections made on the Correct Data page are
reflected.

What you can record is who caused each mismatch:

- **Enumerator**: the survey value is wrong.
- **Backchecker**: the back check value is wrong. A note is required.
- **Respondent**: the respondent gave different answers. A note is required.
- **Unattributed**: no source yet. Every mismatch starts here, and choosing it
  clears an earlier attribution.

Click **Review** on a mismatch in the Comparison Details table to open the
attribution dialog. It shows the survey and back check values, which you
can't edit. To attribute several mismatches at once, select their rows, then
click **Review** on one of the selected rows. Only mismatches can be
attributed.

Each attribution records your reviewer name and the date. The latest
attribution for a mismatch applies only while the survey and back check values
are the ones you attributed. If either value changes, the mismatch is
Unattributed again; if the values now match, there is no mismatch to
attribute. The **Attribution log** expander below the table lists every
attribution, newest first, including the ones later replaced.

Attribution never changes the mismatch counts or the regular error rate. It
only affects the **adjusted error rate**, which has the same denominator as
the error rate (values compared):

- Enumerator adjusted error rate = (mismatches − Backchecker − Respondent) ÷
  values compared
- Back checker adjusted error rate = (mismatches − Enumerator − Respondent) ÷
  values compared

Unattributed mismatches always count against both. For example, an enumerator
with 10 values compared and 4 mismatches, 1 attributed to the respondent and 1
to the back checker, has an error rate of 40% and an adjusted error rate of
20%.

Above Comparison Results Details, a warning counts the duplicate survey IDs,
duplicate back check IDs and unmatched back check IDs that are left out of the
comparison. Resolve them in the **Backcheck data** or **Survey data** view of
the Duplicates check; a resolved record is compared again.

---

### GPS Checks Report

**Purpose**: Validate GPS coordinate quality

#### Sections

##### GPS Settings

Configure GPS validation:

- **Date**: Submission date
- **Survey Key**: Unique identifier
- **Survey ID**: Respondent identifier
- **Enumerator**: Data collector

**GPS Column Configuration**:

- Toggle "Data contains GPS column(s)"

**Option A: Separate Lat/Lon Columns**:

- Toggle "GPS has latitude and longitude columns"
- Select latitude column
- Select longitude column (a different column from latitude)
- Select accuracy column (optional)

**Option B: Combined GPS Column**:

- Select single GPS column (format: "lat, lon")
- Select accuracy column (optional)

##### GPS Overview

Quality metrics:

- Total GPS records
- Valid coordinates
- Invalid coordinates
- Accuracy statistics

##### GPS Quality Issues

Identify problems:

- Missing coordinates
- Out-of-range values (lat: -90 to 90, lon: -180 to 180)
- Low accuracy readings
- Duplicate locations

##### GPS Visualization

Map display:

- Interactive map with all GPS points
- Color-coded by quality
- Click points for details
- Identify geographic outliers

##### Correcting or Accepting GPS Outliers

Each row of the outliers table (expand **View Outliers Data**) starts with a
**Review** button. Click it to open a correction form in a dialog, with the
KEY and its latitude and longitude filled in. Choose an action, enter a reason
and click "Apply":

- **modify coordinates** sets a new latitude and longitude. Latitude must be
  between -90 and 90 and longitude between -180 and 180.
- **remove coordinates** clears the configured latitude and longitude columns.
  Accuracy and altitude are kept.
- **remove observation** removes the record from the dataset, so it
  disappears from every GPS section.
- **accept** records that the location is correct.

Modifying or removing coordinates writes two Correction Log entries, one for
latitude and one for longitude, with the same reason. Both are applied or
neither is. Every entry has source `gps`. The page reloads after a save.

Accepted outliers are hidden from the table and are not counted in
**Outliers Detected**, here or on Summary's GPS Checks row. Without a Mapbox
token the outliers section still shows its counts and table, but no map.
Remembered **Number of Neighbors** values that no longer fit the data, for
example more neighbours than points, go back to the default. On the map
accepted outliers are drawn in green and labelled
Accepted. Turn on **Show reviewed** to list them in the table, highlighted in
green, with the reason. An acceptance lapses, and the point is flagged again,
if either coordinate changes. You can also remove the acceptance on the Correct
Data page.

Corrections need separate latitude and longitude columns. For a configuration
that stores both in one column, the only action offered is **remove
observation**, and a KEY on more than one row can't be reviewed. For separate
columns, as on the outliers page, a KEY on more than one row with different
coordinates can't be reviewed here. An acceptance applies to every GPS
configuration that uses the same latitude and longitude columns. Outliers
can't be reviewed if the Survey KEY column is named `review status` or
`review reason`.

---

## Demo Mode

### What is Demo Mode?

Demo Mode is an interactive guided tutorial that walks you through all DataSure features using realistic household survey data from rural India.

### Demo Data

**Survey Dataset** (132 records):

- Household demographics
- Income and expenditure
- Land ownership
- Education access
- Living conditions

**Backcheck Dataset** (30 records):

- Quality control validation visits
- Matched to survey records by household ID

**Intentional Quality Issues**:

- Missing data patterns
- Duplicate household IDs
- Income outliers
- Inconsistent responses

### Starting Demo Mode

1. Launch DataSure
2. On the Start page, find the **DataSure Demo** row and click **Start
   Demo**. The demo data loads and the demo opens on Import Data.
3. Follow the step-by-step guidance on each page

The first time, an introduction to the demo is shown above the row. Once the
demo exists, the row offers three buttons instead:

- **Resume**: Reopens the demo on Import Data. Your work is kept.
- **Restart**: Asks you to confirm, then deletes everything in the demo
  project (the `cache/demoproject/` folder): imported and prepared data, data
  preparation steps, corrections, check pages and their settings. The demo
  data is loaded again and the demo starts from the beginning. This cannot be
  undone. If the reset fails, the row shows "Failed to reset the demo. Close
  any other DataSure windows and try again."
- **Export**: Opens the same export dialog as **Export configuration** on
  other projects (see [Copying a Project's Setup](#copying-a-projects-setup)).

### Demo Help in the Sidebar

While the demo is open, the sidebar shows a **Demo Help** section with the
current step ("Current Step: N of 7"), its title and description, and two
buttons:

- **Restart Demo**: The same confirmation and reset as **Restart** on the
  Start page.
- **Exit Demo**: Leaves the demo and opens the Start page. Your demo work is
  kept, so you can **Resume** later.

### Demo Progress Indicator

At the top of each page, see:

- Current step highlighted
- Completed steps (✓ checkmark)
- Future steps (grayed out)
- Step titles and icons

### Demo Instructions

Demo guidance appears as blue callouts next to the parts of the page it
describes, and as expandable "**Learn More:**" sections with a blue
background. They cover:

- Step-by-step instructions
- Best practices
- What to expect next

The guidance also walks you through setting your **Reviewer name**, editing
and removing a check configuration, what SurveyCTO import involves, exporting
the demo's configuration, and excluding reviewer names from the replication
package.

### Completing the Demo

The demo ends on its last step, the Export Replication Package page (step 7
of 7). After you click **Build Replication Package** and check the PII
confirmation box:

- Balloons appear once per demo run
- A **Demo Complete!** message is shown, with two options:
  - **Restart Demo**: Asks you to confirm, then resets the whole demo as
    **Restart** does and reopens Import Data
  - **Create Real Project**: Leaves the demo and opens the Start page, where
    you can create a project with your own data

---

## Best Practices

### Data Import

1. **Use Consistent Naming**:
   - Dataset aliases should be descriptive
   - Example: "baseline_survey", "midline_survey", "backchecks_wave1"

2. **Verify Data Structure**:
   - Check column names and types
   - Preview first 100 rows
   - Verify expected row count

3. **SurveyCTO Integration**:
   - Use form IDs, not form names
   - Consider date range filters for large datasets
   - Include attachments only if needed (slow)

### Data Preparation

1. **Date Columns**:
   - Always convert date strings to datetime format
   - Use consistent date format across datasets
   - Verify timezone handling

2. **ID Columns**:
   - Create unique key column if none exists
   - Use consistent ID format (no spaces, special characters)
   - Document ID generation method

3. **Track Changes**:
   - Review preparation log regularly
   - Document why transformations were made
   - Test on small subset first

### Quality Check Configuration

1. **Key Column Requirements**:
   - Must be unique for every row
   - No missing values
   - Stable (doesn't change)

2. **ID vs Key**:
   - **Key**: Unique per row (like UUID)
   - **ID**: Unique per respondent (may repeat)
   - Both are needed for most checks

3. **Backcheck Dataset**:
   - Must have matching ID column
   - Should be subset of main survey
   - Date column recommended

### Report Settings

1. **Configure Once, Use Everywhere**:
   - Settings persist across sessions
   - Update when data structure changes
   - Document non-standard settings

2. **Missing Data Codes**:
   - Define all codes used in survey
   - Be consistent across forms
   - Document in survey codebook

3. **Outlier Detection**:
   - Start with default multipliers (IQR: 1.5, SD: 3.0)
   - Adjust based on domain knowledge
   - Use soft min/max for known ranges

### Data Corrections

1. **Always Document**:
   - Provide detailed correction reason
   - Reference investigation notes
   - Set a **Reviewer name** in the sidebar so the log shows who made each
     entry; the date and source are recorded for you

2. **Correct Where the Flag Is**:
   - Review flagged values from the Outliers and GPS Checks pages, and
     resolve ID problems in the Duplicates check cards
   - Use the Correct Data page for records no check flagged, and to undo
     corrections and acceptances

3. **Accept Only What You Have Checked**:
   - Accept a flagged value only after confirming it with the field team or
     the respondent, and say how in the reason
   - Accept a hard constraint violation only when the bound itself is wrong
     for this record
   - Use **Show reviewed** now and then to look over what has been accepted

4. **Keep Back Check Results Honest**:
   - Back check mismatches can't be corrected or accepted; attribute each one
     to the Enumerator, Backchecker or Respondent instead
   - Report the regular error rate next to the adjusted error rate
   - In the note, say how you know who caused the mismatch

5. **Resolve IDs Before Comparing**:
   - Use **Records to Include** for repeat visits that legitimately share an
     ID, rather than dropping them
   - Resolve the remaining duplicate and unmatched IDs in the Duplicates check
     so they are included in the back check comparison

6. **Verify After Correction**:
   - Open the report again and confirm the issue is resolved
   - Check the Correction Log for entries whose Status is not `Successful`,
     for example after new data is imported
   - Check for new issues created

7. **Correction Workflow**:
   - Identify issue in quality report
   - Investigate root cause
   - Apply correction with documentation
   - Verify resolution
   - Update enumerator if needed

### Team Collaboration

1. **Project Organization**:
   - One project per survey wave
   - Consistent naming convention
   - Regular backups

2. **Quality Check Frequency**:
   - Daily during active data collection
   - Weekly for ongoing monitoring
   - After each data refresh

3. **Communication**:
   - Share quality reports with team
   - Alert enumerators to systematic issues
   - Document all correction decisions

---

## Additional Resources

### Getting Help

- **Documentation**: [DataSure How-To Guide](https://data.poverty-action.org/data-quality/datasure/how-to-datasure.html)
- **GitHub Issues**: [Report bugs and request features](https://github.com/PovertyAction/datasure/issues)
- **Email Support**: <researchsupport@poverty-action.org>

### Further Reading

- High-Frequency Checks best practices
- Survey data quality standards
- IPA Data Management resources

---

**Document Version**: 1.2
**Last Updated**: October 2026
**DataSure Version**: 1.2.0
