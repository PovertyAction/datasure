# DataSure User Guide

Version 1.0 - Comprehensive Guide to Survey Data Quality Management

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
   - Follow the guided 6-step tutorial
3. **Or Create New Project**:
   - Click "Create New Project"
   - Enter project name
   - Begin importing your data

---

## Step-by-Step Workflow

DataSure follows a 6-step workflow for complete data quality management:

### Step 1: Start Here

**Purpose**: Project selection and initialization

**What You'll Do**:

- Create a new project or select an existing one
- Access the demo mode (recommended for new users)
- View project dashboard and navigation

**Demo Scenario**:
You're working with household survey data from rural communities in India, including demographics, income, land ownership, and living conditions data.

**Key Actions**:

- **Create New Project**: Enter a descriptive project name
- **Select Existing Project**: Choose from previously created projects
- **Start Demo**: Launch the interactive tutorial with sample data

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

1. Click "Add Import Configuration"
2. Select **"SurveyCTO"** from the Import Type dropdown
3. Enter server credentials:
   - **Server Name**: Your SurveyCTO server URL
   - **Username**: Your SurveyCTO username
   - **Password**: Your SurveyCTO password (stored securely in your OS keyring — never written to disk)
4. Select form(s) to import
5. Configure import settings:
   - Include/exclude attachments
   - Private key (if encrypted)
6. Click "Import Data"

> **Note**: DataSure performs incremental refresh — only submissions newer than your last import are downloaded, so daily refreshes are fast regardless of total dataset size.

##### Option B: Local File Upload

1. Click "Add Import Configuration"
2. Select **"local storage"** from the Import Type dropdown
3. Upload file(s):
   - Drag and drop or browse
   - Supported formats: .csv, .xlsx, .xls, .json, .dta (Stata), .parquet
4. Configure settings:
   - Assign dataset alias (name)
   - Select sheet (for Excel files)
   - Preview data structure
5. Click "Load Data"

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

**Steps**:

1. Select dataset tab
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

**Steps**:

1. Click "Add data prep step"
2. Choose "Add Column"
3. Enter new column name
4. Define calculation or value
5. Click "Add"

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

##### Redact Column

Mask all values in a column with a redaction label (e.g. `[PERSON]`,
`*****`) while keeping the column in place — the primary tool for
removing PII without losing the dataset's structure:

1. Click "Add data prep step"
2. Choose "Redact Column(s)"
3. Select column(s) and set the redaction label
4. Click "Add"

#### PII Review

Each dataset tab has a **PII Review** section that scans for columns and
values suspected to contain personally identifiable information (PII):

- **Column-name heuristics** run instantly with no setup: multilingual
  restricted-word matching (English, Spanish, French, Swahili terms for
  names, addresses, phones, GPS, ages, SurveyCTO device metadata) plus a
  sparsity check that flags high-cardinality free-text columns.
- **Value scanning** uses Microsoft Presidio with a spaCy language model
  to detect PII *inside* values (person names, phone numbers, emails,
  locations) on a sample of each text column. Models are small
  (~15–40 MB) and downloaded from within the app — English is the
  default; Spanish and French are available from the language selector.

**Workflow**:

1. (Optional) Download the language model to enable value scanning
2. Click **Scan for PII**
3. Review flagged columns: what flagged them, the detected entity type,
   and sample matched values
4. Set a per-column decision: **mask**, **drop**, or **keep**
5. Click **Apply mask/drop decisions as prep steps** — the redactions
   land in the change log like any other prep step (replayable and
   removable), and the decisions also drive the export-time PII gate on
   the Export Replication Package page

> **Warning**: De-identification is not anonymization. Even with direct
> identifiers masked or dropped, respondents may remain identifiable
> through combinations of the remaining variables (age, location,
> occupation, household composition). Review data before sharing.

#### Change Log

All preparation steps are tracked:

- Action type
- Affected columns
- Timestamp
- Applied to which datasets

**Demo Example**:
Convert `submissiondate` column to datetime format for both survey and backcheck datasets:

1. Select **demo_survey** tab
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
   - **Name**: Descriptive name (e.g., "Household Survey Checks")
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

- **Name**: "Household Survey Checks"
- **Survey Dataset**: "demo_survey"
- **Key Column**: "KEY"
- **ID Column**: "hhid"
- **Enumerator Column**: "enum_name"
- **Date Column**: "submissiondate"
- **Backcheck Dataset**: "demo_backcheck"

---

### Step 5: Review Reports

**Purpose**: Analyze data quality results and identify issues

**What You'll Do**:

- Navigate through 9 quality check reports
- Review metrics and visualizations
- Identify data quality issues
- Export findings for action

#### Available Quality Check Reports

Each report is accessible from the navigation sidebar after configuration:

1. **Summary** - Overall data quality dashboard
2. **Survey Progress** - Collection progress and targets
3. **Duplicates** - Duplicate record identification
4. **Missing Data** - Missing value patterns
5. **Outliers** - Statistical outlier detection
6. **Enumerator Stats** - Performance by enumerator
7. **Descriptive Stats** - Variable distributions
8. **Back Checks** - Validation error rates
9. **GPS Checks** - Location data quality

*Detailed report information is provided in the [Quality Check Reports](#quality-check-reports) section below.*

---

### Step 6: Correct Data

**Purpose**: Fix identified data quality issues

**What You'll Do**:

- Apply corrections to specific records
- Track correction history
- Re-run quality checks to verify improvements

#### Correction Actions

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
- Duplicate surveys (after investigation)
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

#### Verifying Corrections

After applying corrections:

1. Navigate back to relevant quality report
2. Click "Refresh" or re-run checks
3. Verify issue is resolved
4. Document in correction notes

**Demo Example**:
Correcting duplicate household ID:

**Issue**: Two records with same hhid "UP015-005"
**Investigation**: One record has typo, should be "UP015-055"

**Steps**:

1. Go to Correct Data page
2. Click "Add correction step" (+ button)
3. **Select Key**: "uuid:0dk0vt97-786b-250u-34k7-z34615zz820c"
4. **Select Action**: "modify value"
5. **Select Column**: "hhid"
6. **Current Value**: "UP015-005" (auto-loaded)
7. **New Value**: "UP015-055"
8. **Reason**: "Correcting duplicate HHID after investigation"
9. Click "Apply"
10. Return to Duplicates tab to verify resolution

---

## Quality Check Reports

### 1. Summary Report

**Purpose**: High-level overview of data quality

#### Sections

##### Summary Settings

Configure global parameters:

- **Survey ID**: Main respondent identifier
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

##### Data Quality Overview

Key quality metrics:

- % duplicate values on ID column
- % values flagged as outliers
- % missing values in dataset
- Backcheck error rate

---

### 2. Survey Progress Report

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

### 3. Duplicates Report

**Purpose**: Identify duplicate records in survey data

#### Sections

##### Duplicates Settings

Configure detection:

- **Survey ID**: Main identifier to check
- **Survey Key**: Unique key column
- **Date**: Submission date
- **Enumerator ID**: Data collector identifier
- **Columns**: Additional columns to check for duplicates

##### Duplicate Statistics

Overview metrics:

- Total duplicates found
- Resolved duplicates
- Columns checked
- Columns with no duplicates
- Columns with duplicates
- Survey ID duplicates count

##### Duplicate Records Table

Detailed duplicate list:

- Survey ID
- Duplicate column values
- Count of duplicates
- Resolution status
- **Filter**: Select additional columns to display

##### Duplicate Entries for Other Columns

Check duplicates in non-ID columns:

- Phone numbers
- Addresses
- ID numbers
- Other identifiers

---

### 4. Missing Data Report

**Purpose**: Analyze missing value patterns

#### Sections

##### Missing Data Settings

Configure missing codes:

- **Missing Labels**: Category names (Don't Know, Refused, N/A)
- **Missing Codes**: Numeric codes (-99, -88, -77)
  - Multiple codes separated by commas

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

### 5. Outliers Report

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

---

### 6. Enumerator Stats Report

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

### 7. Descriptive Stats Report

**Purpose**: Understand variable distributions

#### Sections

##### Descriptive Stats Settings

Configure analysis:

- Select columns to analyze
- Separate report per column

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

### 8. Back Checks Report

**Purpose**: Validate survey data against quality control visits

#### Sections

##### Back Checks Settings

Configure validation:

- **Survey ID**: Respondent identifier
- **Survey Key**: Unique row identifier
- **Enumerator**: Original data collector
- **Back Checker**: QC validator
- **Date**: Back check date
- **Target %**: Target back check rate (e.g., 10%)
- **Handle Duplicates**: Include or exclude duplicates

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

##### Enumerator Statistics

Performance by original enumerator:

- Enumerator ID
- \# surveys back checked
- \# values compared
- \# different values
- Error rate (%)

##### Back Checker Statistics

Performance by validator:

- Back Checker ID
- \# surveys validated
- \# values compared
- \# discrepancies
- Error rate (%)

##### Comparison Details

Record-level validation results:

- Survey ID
- Enumerator
- Back Checker
- Survey value
- Back check value
- Comparison result
- Column name

---

### 9. GPS Checks Report

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
- Select longitude column
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
2. Click "Start Demo" on welcome screen
3. Follow step-by-step guidance
4. Interactive tutorials in each section

### Demo Progress Indicator

At the top of each page, see:

- Current step highlighted
- Completed steps (✓ checkmark)
- Future steps (grayed out)
- Step titles and icons

### Demo Instructions

Look for expandable "**Learn More:**" sections throughout the demo:

- Yellow background containers
- Step-by-step instructions
- Best practices
- What to expect next

### Completing the Demo

After completing all 6 steps:

- Celebration animation (balloons!)
- Demo completion message
- Options:
  - **Restart Demo**: Go through again
  - **Create Real Project**: Start with your own data

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
   - Include date and source

2. **Verify After Correction**:
   - Re-run relevant quality check
   - Confirm issue resolved
   - Check for new issues created

3. **Correction Workflow**:
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

**Document Version**: 1.0
**Last Updated**: July 2026
**DataSure Version**: 1.0.0
