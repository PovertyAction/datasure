import json
import random
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import ClassVar

import pandas as pd
import polars as pl
import streamlit as st

from datasure.utils.cache_utils import get_cache_path
from datasure.utils.duckdb_utils import duckdb_remove_table, duckdb_save_table

DEMO_PROJECT_NAME = "DataSure Demo"
DEMO_PROJECT_ID = "demoproject"


class CheckPage(Enum):
    """Enum for different check output pages."""

    SUMMARY = "Summary"
    SURVEY_PROGRESS = "Survey Progress"
    DUPLICATES = "Duplicates"
    MISSING_DATA = "Missing Data"
    OUTLIERS = "Outliers"
    ENUMERATOR_STATS = "Enumerator Stats"
    DESCRIPTIVE_STATS = "Descriptive Stats"
    BACK_CHECKS = "Back Checks"
    GPS_CHECKS = "GPS Checks"


# create a coloured container


def demo_container(text: str = ""):
    """Create an info container for demo messages."""
    st.info(text)


class ImportDemoInfo:
    """Class to provide demo messages for import scenarios."""

    ADD_TO_SESSION_INFO: ClassVar[str] = """
        Your demo survey data has been loaded successfully.
        The survey and backcheck datasets are now available for analysis.
    """

    PREVIEW_DATA_INFO: ClassVar[str] = """
        Your demo datasets are loaded and ready to explore.
        Switch between **demo_survey** and **demo_backcheck** to review the data,
        then click **Prepare Your Data** below to continue to the next step.
    """

    PREPARE_DATA_INFO: ClassVar[str] = """
        What is Data Preparation?

        ##### Data preparation is a crucial step that:
        - **Cleans and transforms data**: Handles text case changes, date conversions, and mathematical operations
        - **Creates new variables**: Add calculated fields, unique identifiers, or custom columns for analysis
        - **Removes problematic data**: Delete unnecessary columns or filter out rows with critical data quality issues

        ##### For this demo, you can:
        1. **Explore your data**: Alternate between the **demo_survey** and **demo_backcheck**
        tabs below to see your survey data and backcheck data.
        2. **Transform date column**: Add data preparation steps if you want to experiment.
        Do the following:
            - Select the **demo_survey** tab
            - Click on the ":material/add: Add data prep step" button
            - Under "Select Action", choose "Transform Column"
            - For "Select Column to Transform", choose "submissiondate"
            - For "Select function", choose "string to datetime". Note that the functions
              available depend on the type of column selected.
            - Click on ":material/check: Apply" to save the preparation step.
            - Review the "submissiondate" column to see the changes.
        3. **Apply same step to backcheck data**: Select the **demo_backcheck** tab and repeat
        the same steps to transform the "submissiondate" column there as well.


        **Ready to continue?** Preview data and try additional transformations.
    """

    PROCEED_TO_CONFIG_INFO: ClassVar[str] = """
        ##### Want to experiment with data preparation?** Try these features:

        ##### Transform columns:
        - Convert text to uppercase/lowercase
        - Extract patterns from text fields
        - Perform mathematical operations on numeric data

        ##### Add new columns:
        - Create calculated fields
        - Add unique identifiers
        - Generate summary statistics

        ##### Remove problematic data:
        - Delete unnecessary columns
        - Remove rows with missing critical data
        - Filter out outliers

        Your demo data is already prepared for quality checks, so these steps are optional in the demo.
    """

    DEMO_DATA_INFO: ClassVar[str] = """
        **Demo Status: Data Import Complete!**

        Your survey data has been successfully imported and is ready for analysis.

        **Next:** Let's move to data preparation where we'll clean and prepare this data for comprehensive quality checks!
    """

    PROCEED_TO_HFCS_INFO: ClassVar[str] = """
        Your configuration is set up and your data is ready for quality analysis.

        Click **View Quality Reports** to explore the results — DataSure has run all
        configured checks and the reports are ready to review.
    """

    ADD_CHECK_CONFIG_INFO: ClassVar[str] = """
        ##### Follow these steps to set up data quality checks:

        ##### Step 1: Click ":material/add: Add new check configuration"
        - A dialog window will appear to guide you through the configuration process
        - Give your configuration a descriptive name like "Household HFCs" (1-20 characters)

        ##### Step 2: Select your survey dataset
        - Choose "demo_survey" (your main household survey data) from the dropdown
        - The column selector will automatically refresh to show available columns

        ##### Step 3: Configure survey key columns:
        DataSure will categorize your columns by type (datetime, numeric, categorical) to help you choose:
        - **Key Column**: Choose "KEY" (unique row identifier) - this uniquely identifies each survey record
        - **ID Column**: Choose "hhid" (Household ID) - identifies each household/respondent
        - **Enumerator Column**: Choose "enum_name" (shows who collected the data)
        - **Team Column**: Select "team_id" - indicates the team responsible for data collection
        - **Form Version Column (optional)**: Select "form_version" - indicates the version of the survey form used. Skip for this demo.
        - **Duration Column**: Select "duration" (time taken to complete survey)
        - **Date Column**: Choose "submissiondate" (when the survey was submitted)
        - **Survey Target** (optional): Enter expected number of interviews (e.g., 200)

        ##### Step 4: Add backcheck dataset (optional)
        - **Backcheck Dataset**: Choose "demo_backcheck" (from your imported backcheck data)
        - Configure backcheck columns similarly (date: submissiondate, backchecker: bcer_name, backchecker team: team_id, target percentage: 10)

        ##### Step 5: Click "Submit" to create the configuration
        - DataSure validates your inputs using Pydantic models for data integrity
        - If validation passes, a new quality analysis page is automatically created!

        **:material/celebration: What happens next:** DataSure creates a comprehensive quality analysis page with all configured checks!
    """

    ADD_PREP_STEPS_INFO: ClassVar[str] = """
        You will need to add a data preparation step to convert the submissiondate
        column to a date format for both the survey and backcheck surveys. This is a
        crucial step to ensure accurate date handling in your analysis.
    """

    ADD_CORRECTION_STEP_INFO: ClassVar[str] = """
        This page lets you apply targeted corrections to your survey data based on
        issues identified in the quality reports. Corrections are logged and can be
        undone at any time.

        **Page structure:** There is one tab per HFC configuration (e.g., "Household HFCs").
        Inside each tab you will find:
        - :material/add: **Add correction step** — open a popover to apply a new correction.
        - :material/delete: **Remove correction step** — open a popover to undo a previous correction.
        - **Correction Log** — appears after the first correction is applied; shows all
          corrections made so far with their reasons.
        - **Preview Corrected Data** — a live preview of the dataset after all corrections
          have been applied, with row/column/missingness metrics.

        The three correction actions available are:
        - **Modify Value**: Replace a specific value in a column with a new value.
        - **Remove Value**: Replace a specific value with null/missing.
        - **Remove Row**: Delete the entire row from the dataset.

        ##### Instructions for Demo:
        Fix the duplicate **hhid** found in the Duplicates tab. Investigation confirmed that
        the response with key **uuid:0dk0vt97-786b-250u-34k7-z34615zz820c** has the wrong
        household ID — it should be **UP015-055**, not **UP015-005**.

        1. Click **:material/add: Add correction step**.
        2. Under **Select KEY**, choose **uuid:0dk0vt97-786b-250u-34k7-z34615zz820c**.
        3. Under **Select Action**, choose **modify value**.
        4. Under **Select Column to Modify**, choose **hhid**.
           The current value (**UP015-005**) loads automatically.
        5. Under **New Value**, enter **UP015-055**.
        6. Under **Reason for Correction**, enter something like
           *Correcting duplicate HHID after investigation*.
        7. Click **Apply** to save the correction.

        Once applied, check the **Correction Log** to confirm the entry, and return to
        the **Duplicates** tab in the quality reports to verify the duplicate is resolved.

        **You have completed the DataSure demo!** You have imported data, prepared it,
        configured quality checks, reviewed reports across all tabs, and applied a
        correction. Return to the quality reports at any time to see how corrections
        have improved data quality.
    """

    @classmethod
    def get_info_message(cls, message_id: str) -> str:
        """Retrieve demo messages based on type."""
        demo_messages = {
            "add_to_session_info": cls.ADD_TO_SESSION_INFO,
            "prepare_data_info": cls.PREPARE_DATA_INFO,
            "preview_data_info": cls.PREVIEW_DATA_INFO,
            "proceed_to_config_info": cls.PROCEED_TO_CONFIG_INFO,
            "demo_data_info": cls.DEMO_DATA_INFO,
            "proceed_to_hfcs_info": cls.PROCEED_TO_HFCS_INFO,
            "add_check_config_info": cls.ADD_CHECK_CONFIG_INFO,
            "add_prep_steps_info": cls.ADD_PREP_STEPS_INFO,
            "add_correction_step_info": cls.ADD_CORRECTION_STEP_INFO,
        }
        return demo_messages.get(message_id, "Invalid message ID.")


class OnboardingSteps:
    """Class to define onboarding steps."""

    START: ClassVar[dict] = {
        "step": 1,
        "title": "Start Here",
        "description": "Welcome to DataSure! Learn how to manage survey data quality.",
        "icon": ":material/home:",
        "page": "start_view.py",
        "guidance_title": "Welcome to DataSure!",
        "guidance_content": """
        ##### What you'll learn in this demo:
        - How to import survey data from different sources
        - How to run data quality checks
        - How to identify and fix data issues
        - How to generate quality reports

        **Demo scenario:** You're working with household survey data from rural communities in India.
        The data includes information about demographics, income, land ownership, and living conditions.
        """,
    }

    IMPORT: ClassVar[dict] = {
        "step": 2,
        "title": "Import Data",
        "description": "Import your survey data from various sources.",
        "icon": ":material/upload:",
        "page": "import_view.py",
        "guidance_title": "Your Data is Pre-loaded",
        "guidance_content": """
        Your demo data has already been imported — no configuration needed here.

        **What's been imported:**
        - **Survey Data**: 132 household survey responses from rural communities in India
        - **Backcheck Data**: 30 quality control validation records

        Both datasets contain realistic data quality issues including missing values,
        duplicate household IDs, and inconsistent income reporting — exactly the kind
        of issues DataSure is designed to catch.

        **:material/arrow_downward: What to do now:** Scroll down to **Preview Imported Data**,
        switch between the **demo_survey** and **demo_backcheck** datasets to explore the data,
        then click **Prepare Your Data** to continue.
        """,
    }

    PREPARE: ClassVar[dict] = {
        "step": 3,
        "title": "Prepare Data",
        "description": "Clean and prepare your data for quality checks.",
        "icon": ":material/build:",
        "page": "prep_view.py",
        "guidance_title": "Data Preparation (Optional)",
        "guidance_content": """
        One preparation step is required before you can continue: convert the
        **submissiondate** column from text to a datetime format in **both** datasets.

        **:material/arrow_forward: To do this for each dataset tab (demo_survey and demo_backcheck):**
        1. Click **:material/add: Add data prep step**
        2. Under **Select Action**, choose **Transform Column**
        3. Under **Select Column to Transform**, choose **submissiondate**
        4. Under **Select Function**, choose **string to datetime**
        5. Click **Add** to save the step

        Once both datasets have been prepared, the **Configure Quality Checks** button will become active.
        """,
    }

    CONFIGURE: ClassVar[dict] = {
        "step": 4,
        "title": "Configure Checks",
        "description": "Set up data quality checks and validation rules.",
        "icon": ":material/tune:",
        "page": "config_view.py",
        "guidance_title": "Configure Quality Checks",
        "guidance_content": """
        One configuration covers both datasets. Click **:material/add: Add New Check Configuration**
        and fill in the form with these values:

        **Configuration name:** Household HFCs

        **Survey dataset:** demo_survey
        - Key Column: KEY | ID Column: hhid | Enumerator Column: enum_name
        - Team Column: team_id | Duration Column: duration | Date Column: submissiondate
        - Survey Target: 200 (optional)

        **Backcheck dataset:** demo_backcheck
        - Date: submissiondate | Backchecker: bcer_name | Team: team_id | Target %: 10

        Click **Submit** — DataSure creates a quality analysis page automatically.
        Once created, the **View Quality Reports** button will appear at the bottom of this page.
        """,
    }

    OUTPUTS: ClassVar[dict] = {
        "step": 5,
        "title": "Review Reports",
        "description": "Analyze data quality results and insights.",
        "icon": ":material/bar_chart:",
        "page": "output_view_1.py",
        "guidance_title": "Review Quality Reports",
        "guidance_content": """
        Each tab covers a different data quality check. Start by expanding the
        :material/settings: **settings panel** at the top of each tab and configuring
        it for your data. Then work through the sections below — demo guidance is
        available within each section to explain what you are seeing and what to do next.

        **Tabs to explore:** Summary, Descriptive Statistics, Progress Tracking,
        Missing Values, Duplicates, Outliers & Constraints, GPS Checks,
        Enumerator Statistics, Backcheck Analysis.
        """,
    }

    CORRECT: ClassVar[dict] = {
        "step": 6,
        "title": "Correct Data",
        "description": "Make corrections to your data based on quality findings.",
        "icon": ":material/edit:",
        "page": "correction_view.py",
        "guidance_title": "Correct Data Issues",
        "guidance_content": """
        ##### In this step you'll:
        - Learn how to make corrections to your datasets after analyzing Data Quality Reports

        ##### Instructions for Demo:
        - Make the following corrections to the demo_survey dataset:
            1. For the duplicate records found on hhid "UP015-005", we find out upon investigation that
            the correct HHID for the response with the key "uuid:0dk0vt97-786b-250u-34k7-z34615zz820c" is "UP015-055". Correct the ID by
            doing the following:
                - Click on **:material/add: Add correction** button
                - Under **Select Key**, choose "uuid:0dk0vt97-786b-250u-34k7-z34615zz820c"
                - Under **Select Action**, choose "modify value"
                - Under **Select Column to Modify**, choose "hhid"
                - You will notice that the current value is loaded automatically.
                - Under **New Value**, enter "UP015-055"
                - Add **Reason for Correction** such as "Correcting duplicate HHID after investigation"
                - Click on **:material/check: Apply** to save the correction.
                - Go back to the **Duplicates** tab to verify that the duplicate has been resolved.
            2. You can apply a similar correction progress for all corrections. The options for corrections include:
                - Modify Value: Modify a specific value in a column
                - Remove Row: Remove an entire row from the dataset
                - Remove Value: Replace a specific value with null/missing

        **Final step:** After applying corrections, revisit the quality reports to see how the data quality has improved!

        """,
    }

    @classmethod
    def get_step_info(cls, step: str) -> dict:
        """Retrieve step information based on step name."""
        steps = {
            "start": cls.START,
            "import": cls.IMPORT,
            "prepare": cls.PREPARE,
            "configure": cls.CONFIGURE,
            "reports": cls.OUTPUTS,
            "correct": cls.CORRECT,
        }
        return steps.get(step, {})

    @classmethod
    def get_all_steps(cls) -> list[dict]:
        """Retrieve all onboarding steps in order."""
        return [
            cls.START,
            cls.IMPORT,
            cls.PREPARE,
            cls.CONFIGURE,
            cls.OUTPUTS,
            cls.CORRECT,
        ]

    @classmethod
    def get_guidance(cls, step: int) -> None:
        """Retrieve guidance for a specific step."""
        steps = {
            1: cls.START,
            2: cls.IMPORT,
            3: cls.PREPARE,
            4: cls.CONFIGURE,
            5: cls.OUTPUTS,
            6: cls.CORRECT,
        }
        guidance = steps.get(step, {})
        if not guidance:
            raise ValueError(f"Invalid step: {step}")
        with st.expander(
            f":material/menu_book: **{guidance['guidance_title']}**", expanded=True
        ):
            demo_container(guidance["guidance_content"])


class OutputOnboardingInfo:
    """Class to provide onboarding messages for check output pages."""

    SUMMARY: ClassVar[dict] = {
        "summary_report": {
            "title": "Data Quality Summary",
            "content": """
        ##### Summary of Data Quality Checks

        This tab provides an overview of the data quality checks performed on your survey data.
        It summarizes key metrics such as the number of checks run, issues identified,
        and overall data quality score.

        **Next**: Click on the :material/settings: settings icon to configure global settings for the summary tab.
        """,
        },
        "summary_settings": {
            "title": "Summary Settings",
            "content": """
        ##### Setup for Summary Tab
        In this section, you can configure global settings for the summary tab, you will notice that some settings are pre-filled based on your check configuration.
        This tab contains the following settings:
        - Survey ID: The main identifier for your survey respondents (e.g., household ID, Respondent ID).
        - Survey Date: The date when the survey was conducted or submitted. (e.g., submissiondate, starttime).
        - Total Expected Interviews: The total number of survey interviews you expect to have in your dataset (e.g., 1000).

        ##### Instructions for Demo:
        For the demo data, you will need to indicate a total of **200** expected interviews.

        **Next**: Explore the data summary section below.
        """,
        },
        "summary_data_summary": {
            "title": "Data Summary",
            "content": """
        ##### Data Summary
        This section provides a quick overview of your survey dataset, including:
        - String columns: Number of text-based columns in your dataset.
        - Numeric columns: Number of numeric columns in your dataset (includes int, float)
        - Date columns: Number of date/time columns in your dataset.
        - Total rows: Total number of rows (records) in your dataset.

        **Next**: Explore the Submission Details section below.
        """,
        },
        "summary_submissions": {
            "title": "Submission Details",
            "content": """
        ##### Submission Details
        This section provides insights into the submission patterns of your survey data, including:
        - Today: Number of submissions received today.
        - This Week: Number of submissions received in the last 7 days.
        - This Month: Number of submissions received in the last 30 days.
        - Total Submissions: Total number of submissions received to date.

        This section also includes a submission trend chart that visualizes the number of submissions over time, helping you identify patterns and peaks in data collection.

        **Next**: Explore the Progress section below.
        """,
        },
        "summary_progress": {
            "title": "Progress",
            "content": """
        ##### Progress
        This section provides an overview of the progress of your survey data collection, including:
        - Submission Progress: A progress bar showing the percentage of completed submissions against the total expected interviews.
        - Average Submissions per Day: The average number of submissions per calendar day across the full survey period.
        - Average Submissions Per Week: The average number of submissions per calendar week (Monday to Sunday) across the full survey period.
        - Average Submissions Per Month: The average number of submissions per calendar month across the full survey period.

        **Next**: Explore the progress by subsections below.

        ##### Instructions for Demo:
        For the demo, you will explore how to create a table showing progress by subgroups such as enumerator or region.
        - At "Progress by" dropdown, select "state" to see submission progress by state.

        **Optionally**,
        - you can also explore by selecting other categorical columns.
        - on the right side of the table, you can switch between, "Auto", "Daily", "Weekly", and "Monthly" views to see how submission progress varies over different time intervals.
        The "Auto" view automatically adjusts the time interval based on the data density while the other options allow you to manually select the desired time frame for analysis.
        """,
        },
        "summary_data_quality": {
            "title": "Data Quality",
            "content": """
        ##### Data Quality
        This section provides an overview of the overall data quality of your survey dataset, including:
        - % of duplicate values on ID column: Percentage of duplicate entries found in the ID column.
        - % of values flagged as outliers: Percentage of data points identified as outliers. This will show **0%** until you configure the **Outliers & Constraints** tab — once configured, return here to see the updated value.
        - % of missing values in survey dataset: Percentage of missing or null values in the survey dataset.
        - Backcheck error rate: Percentage of discrepancies found between survey data and backcheck data.

        **Next**: Explore the "Descriptive Statistics" tab.
        """,
        },
    }

    PROGRESS: ClassVar[dict] = {
        "progress_report": {
            "title": "Progress Report",
            "content": """
        ### Survey Progress Report
        This tab provides detailed insights into the progress of your survey data collection.
        It includes metrics such as submission counts over time, progress by enumerator or selected categories, and overall submission trends.
        **Next**: Go to the :material/settings: settings icon to configure global settings for the survey progress tab.
        """,
        },
        "progress_report_settings": {
            "title": "Progress Settings",
            "content": """
        ##### Setup for Survey Progress Tab
        In this section, you can configure global settings for the survey progress tab, you will notice that some settings are pre-filled based on your check configuration.
        This tab contains the following settings:
        - Survey ID: The main identifier for your survey respondents (e.g., household ID, Respondent ID).
        - Date: The column indicating the date when the survey was conducted or submitted. (e.g., submissiondate, starttime).
        - Enumerator: The column indicating who collected the data (e.g., enumerator name or ID).
        - Total Expected Interviews: The total number of survey interviews you expect to collect (e.g., 200).
        - Target Submissions Per Period: The number of submissions you aim to collect per day, week, or month. This sets the threshold line on the Progress Over Time chart.

        ##### Instructions for Demo:
        - Set **Total Expected Interviews** to **200**.
        - Set **Target Submissions Per Period** to **5** (roughly 5 interviews per day).

        **Next**: Explore the **Progress Summary** section below.
        """,
        },
        "display_progress_summary": {
            "title": "Progress Summary",
            "content": """
        ##### Progress Summary
        This section provides a quick overview of your survey data collection progress, including:
        - Submission Progress: Percentage of completed submissions against the total expected interviews.
        - Target Interviews: Total number of interviews you aim to collect.
        - Total Submitted Interviews: Total number of submissions received to date.
        **Next**: Explore the **Progress Over Time** section below.
        """,
        },
        "display_progress_overtime": {
            "title": "Progress Over Time",
            "content": """
        ##### Submission Trends
        This section visualizes the submission trends of your survey data over time, helping you identify patterns and peaks in data collection.

        Bars are color-coded: **green** when the number of submissions meets or exceeds the threshold, **red** when below. The threshold is the **Target Submissions Per Period** if set in settings, otherwise the overall average.

        ##### Instructions for Demo:
        - Switch between "Day", "Week", and "Month" views using the pills above the chart.
        - Notice that some bars are red — these are periods where submissions fell below the average.
        - If you set a **Target Submissions Per Period** in settings, the threshold line will reflect that target instead of the average.

        **Next**: Explore the **Attempted Interviews** section below.
        """,
        },
        "display_attempted_interviews": {
            "title": "Attempted Interviews",
            "content": """
        ##### Attempted Interviews
        This section provides insights into the number of attempted interviews in your survey data, including:
        - Total Submitted Interviews: Total number of submissions received to date.
        - Number of Unique IDs: Count of unique respondents based on the ID column.
        - Min Attempts: Minimum number of attempts made by any respondent.
        - Max Attempts: Maximum number of attempts made by any respondent.

        It also includes the following visualizations:
        - A horizontal bar chart showing the **distribution of attempt counts** — how many respondents had exactly 1 attempt, 2 attempts, 3 or more, etc.
        - A data table summarizing attempted interviews by respondent ID (e.g., household ID), including the date of each attempt.

        **Next**: Explore the **Missing Values** tab.
        """,
        },
        "display_progress_chart": {
            "title": "Consent and Completion Progress",
            "content": """
        ##### Consent and Completion Progress
        This section helps you monitor the consent and completion rates of your survey data collection, including:
        - Consent Rate: Percentage of respondents who provided consent.
        - Completion Rate: Percentage of respondents who completed the survey.

        ##### Instructions for Demo:
        For the demo, you will setup the consent and completion criteria as follows:
        - Consent Criteria: Select the "consent" column and set the value to "yes".
        - Completion Criteria: Select the "completion_status" column and set the value to "complete".
        **Next**: Explore other tabs for more data quality insights.
        """,
        },
    }

    DUPLICATES: ClassVar[dict] = {
        "duplicates_report_settings": {
            "title": "Duplicates Settings",
            "content": """
        ##### Duplicates Settings
        These settings control which columns identify a unique survey record and how
        duplicate detection is performed.

        - **Survey Key**: The unique row identifier for each submission (e.g., KEY).
          Different from Survey ID — every submission has a unique key even if two share
          the same respondent ID.
        - **Survey ID**: The respondent or household identifier checked for duplicates
          (e.g., hhid).
        - **Survey Date**: The submission or interview date column (e.g., submissiondate).
        - **Enumerator ID**: The column identifying who collected the data (e.g., enum_name).
        - **Duplicates Conditions**: Optional filter to restrict the check to a subset of
          records. Use the toggle to treat missing values as duplicates.

        ##### Instructions for Demo:
        Your settings are pre-filled from the check configuration you set up earlier.
        Confirm the following values are selected, then close the panel and explore the
        sections below:
        - Survey Key: **KEY**
        - Survey ID: **hhid**
        - Survey Date: **submissiondate**
        - Enumerator ID: **enum_name**
        """,
        },
    }
    MISSING: ClassVar[dict] = {
        "missing_summary": {
            "title": "Missing Values Tab",
            "content": """
        This tab helps you understand the extent and patterns of missing data in your survey dataset.

        **Start here**: At the top of this tab, configure your **missing value codes** (the
        :material/add: **Add** / :material/edit: **Modify** / :material/delete: **Delete** buttons).
        These codes tell DataSure which numeric values in your data represent survey-specific
        non-responses (e.g., -99 = Don't Know).

        The tab then provides five sections:
        - **Missing Data Statistics**: High-level summary metrics.
        - **Missingness by Column**: Per-column breakdown with a filter slider.
        - **Compare Missing Data Within Groups**: Missing rates broken down by a grouping variable.
        - **Missingness Over Time**: Trend chart showing how missingness changes over the survey period.
        - **Nullity Correlation**: Heatmap showing which columns tend to be missing together.
        - **Nullity Matrix**: Visual grid of presence/absence across all rows and columns.

        **Next**: Explore the **Missingness by Column** section below.
        """,
        },
        "missing_columns": {
            "title": "Missingness by Column",
            "content": """
        ##### Missingness by Column
        This section provides a detailed view of missing data by column, including:
        - A table showing each column in the dataset with the following details:
            - Column Name: Name of the column.
            - Total Missing: Total number of missing values in the column.
            - % Total Missing: Percentage of missing values in the column.
            - Null Values: Count of null or NaN values in the column.
            - % Null Values: Percentage of null or NaN values in the column.
            - Don't Know: Count of values marked as "Don't Know".
            - % Don't Know: Percentage of values marked as "Don't Know".
            - Refused to Answer: Count of values marked as "Refused to Answer".
            - % Refused to Answer: Percentage of values marked as "Refused to Answer".
            - Not Applicable: Count of values marked as "Not Applicable".
            - % Not Applicable: Percentage of values marked as "Not Applicable".
        - The table can be sorted by any of the columns to help identify which columns have the highest or lowest missing data.
        - The table also includes a "Filter Report by % missing" slider at the top right to allow you to filter the report based on a minimum percentage of missing data.

        ##### Instructions for Demo:
        For the demo, use the "% missing" slider to filter the report to only show columns with 100% missing values.
        **Next**: Explore the **Compare missing data within groups** section below.
        """,
        },
        "missing_compare": {
            "title": "Compare Missing Data Within Groups",
            "content": """
        ##### Compare Missing Data Within Groups
        This section allows you to compare missing data patterns within different groups in your dataset, including:
        - A dropdown to select a categorical column (e.g., enumerator, region, etc.) to group the data by.
        - A dropdown to select columns to compare. By default, all columns will be used but an aggregate view will be shown.
        - A table showing the percentage of missing values for each selected column within each group.

        ##### Instructions for Demo:
        For the demo:
         - **first** - at the **Select column to group by** dropdown, choose "state" to see how missing data varies across different states in the dataset.
         - **then** - at the **Select columns to compare** dropdown, choose "land_acre", "child_loan" and "pvt_sch" to see how missing data varies for these specific columns across different states.
        **Next**: Explore the **Missingness over time** section below.
        """,
        },
        "missing_over_time": {
            "title": "Missingness Over Time",
            "content": """
        ##### Missingness Over Time
        This section visualizes missing data patterns over time, helping you identify trends and changes in data quality during the survey period, including:
        - A line chart showing the percentage of missing values over time.
        - A dropdown to select a specific date column to use for analysis.
        ##### Instructions for Demo:
        For the demo, at the **Select column to analyze missingness over time** dropdown, choose "submissiondate" to see how missing data varies over the survey period.
        **Next**: Explore the **Nullity Correlation** section below.
        """,
        },
        "missing_correlation": {
            "title": "Nullity Correlation",
            "content": """
        ##### Nullity Correlation
        This section provides insights into the correlation of missing data between different columns in your dataset, helping you identify patterns and relationships in missingness, including:
        - A heatmap visualizing the correlation of missing values between columns.
        - Use the **All columns** toggle to include every column at once, or turn it off to
          manually select specific columns from the dropdown.

        ##### Instructions for Demo:
        For the demo:
        - Turn off the **All columns** toggle, then at the **Select columns** dropdown, choose "min_dist" and "travel_sch".
        - You will notice that whenever "min_dist" is missing, "travel_sch" is also missing. This makes sense: if the distance to school is not recorded, the mode of travel is also likely missing.

        This insight can help identify potential data collection issues or patterns in missingness that may require further investigation.
        **Next**: Explore the **Nullity Matrix** section.
        """,
        },
        "missing_matrix": {
            "title": "Nullity Matrix",
            "content": """
        ##### Nullity Matrix
        This section provides a visual representation of the missing data patterns in your dataset, helping you quickly identify areas with high or low missingness, including:
        - A matrix visualization showing the presence or absence of data for each column in the dataset. The red blocks represent missing values, while the blue blocks represent non-missing values.
        **Next**: Explore the **Duplicates** tab.
        """,
        },
    }
    OUTLIERS: ClassVar[dict] = {
        "outliers_report_settings": {
            "title": "Outliers & Constraints Settings",
            "content": """
        ##### Outliers & Constraints Settings
        These settings identify the key columns DataSure uses to contextualise flagged
        records in the report tables.

        - **Survey Key**: Unique row identifier for each submission (e.g., KEY).
        - **Survey ID**: Respondent or household identifier (e.g., hhid).
        - **Survey Date**: Submission or interview date column (e.g., submissiondate).
        - **Enumerator ID**: Column identifying the data collector (e.g., enum_name).
        - **Team ID**: Column identifying the team (e.g., team_id).

        ##### Instructions for Demo:
        Your settings are pre-filled from the check configuration. Confirm the following
        are selected, then close the panel and proceed to configure outlier columns below:
        - Survey Key: **KEY**
        - Survey ID: **hhid**
        - Survey Date: **submissiondate**
        - Enumerator ID: **enum_name**
        - Team ID: **team_id**
        """,
        },
    }
    ENUMERATORS: ClassVar[dict] = {
        "enumerator_report_settings": {
            "title": "Enumerator Statistics Settings",
            "content": """
        ##### Enumerator Statistics Settings
        These settings identify the key columns DataSure uses to track enumerator
        performance across the report.

        - **Survey Key**: Unique row identifier for each submission (e.g., KEY).
        - **Survey ID**: Respondent or household identifier (e.g., hhid).
        - **Survey Date**: Submission or interview date column (e.g., submissiondate).
        - **Enumerator ID**: Column identifying the data collector (e.g., enum_name).
        - **Team**: Column identifying the team (e.g., team_id).
        - **Duration Column**: Column recording how long each interview took (e.g., duration).
        - **Duration Unit**: Unit of the duration column — seconds, minutes, or hours.
        - **Form Version Column**: Column recording the form version used (e.g., formdef_version).
        - **Consent and Outcome Settings**: Configure which column and value indicate consent
          and which indicate a completed survey, then click **Apply Consent and Outcome Settings**.

        ##### Instructions for Demo:
        Your Survey Key, Survey ID, Survey Date, Enumerator ID, and Form Version are
        pre-filled from earlier configuration. Confirm and complete the remaining fields:
        - Duration Column: **duration**
        - Duration Unit: **seconds**
        - Team: **team_id**
        - Consent Column: **consent** | Valid Consent Values: **yes**
        - Outcome Column: **completion_status** | Completed Survey Values: **complete**

        Click **Apply Consent and Outcome Settings**, then close the panel and explore
        the sections below.
        """,
        },
    }

    DESCRIPTIVE_STATS: ClassVar[dict] = {
        "descriptive_report": {
            "title": "Descriptive Statistics",
            "content": """
        This tab lets you explore the distribution and characteristics of any column
        in your dataset. Use the **column selector** below to choose which columns to
        analyse, then explore three sections:

        - **Summary Stats**: Count, mean, median, standard deviation, min/max, quartiles,
          skewness, and kurtosis for each selected numeric column.
        - **Histogram**: Distribution chart for a selected numeric column, with mean and
          median lines marked. Use the **Bins** slider to adjust the resolution.
        - **Value Counts**: Frequency table showing how often each value appears.
          Switch between table and chart view, and toggle between count and percentage.

        ##### Instructions for Demo:
        1. In the **column selector**, check **age** and **household_count** — or use the
           **Select by Type** pill and choose **Numeric** to select all numeric columns at once.
        2. Click **Apply Selection** to load the analysis.
        3. In **Summary Stats**, compare the mean and median for each column to spot skewed distributions.
        4. In **Histogram**, select **age** and try adjusting the **Bins** slider.
        5. In **Value Counts**, switch the column to **state** or **enum_name** to see how
           responses are distributed across categories. Note that categorical columns like
           **state** are only available here if you included them in your column selection —
           if you selected numeric columns only, go back to the column selector and add
           **state** or **enum_name**.

        **Next**: Explore the **Progress Tracking** tab.
        """,
        },
    }
    BACKCHECKS: ClassVar[dict] = {
        "backchecks_report_settings": {
            "title": "Backcheck Analysis Settings",
            "content": """
        ##### Backcheck Analysis Settings
        These settings link your survey dataset to your backcheck dataset so DataSure
        can match records and compare values.

        - **Survey Key**: Unique row identifier in the survey dataset (e.g., KEY).
        - **Survey ID**: Respondent or household identifier (e.g., hhid).
        - **Survey Date**: Date column in the survey dataset (e.g., submissiondate).
        - **Backcheck Date**: Date column in the backcheck dataset (e.g., bc_date).
        - **Enumerator**: Column identifying the original data collector (e.g., enum_name).
        - **Backchecker**: Column in the backcheck dataset identifying who conducted
          the back check (e.g., backchecker_name).
        - **Target number of backchecks**: Expected total number of back checks.
        - **Additional Options**: Duplicate handling (Drop All / Keep First / Keep Last),
          No Differences Values, Exclude Values, and String Comparison Options
          (case sensitivity, trim spaces, remove symbols).

        ##### Instructions for Demo:
        Your Survey Key, Survey ID, Survey Date, Enumerator, and Backchecker are
        pre-filled from earlier configuration. Confirm they are set, then close the
        panel and proceed to the **Backchecks Columns Configuration** section below.
        """,
        },
    }

    GPSCHECKS: ClassVar[dict] = {
        "gpschecks_report_settings": {
            "title": "GPS Checks Settings",
            "content": """
        ##### GPS Checks Settings
        These settings identify the key columns DataSure uses to label records on maps
        and in report tables.

        - **Survey Key**: Unique row identifier for each submission (e.g., KEY).
        - **Survey ID**: Respondent or household identifier (e.g., hhid).
        - **Survey Date**: Submission or interview date column (e.g., submissiondate).
        - **Enumerator ID**: Column identifying the data collector (e.g., enum_name).
        - **Team**: Column identifying the team (e.g., team_id).
        - **Mapbox API Token**: Required to render map visualizations. Enter your token
          in the **Mapbox API Token Configuration** section and click **Save Mapbox Token**.

        ##### Instructions for Demo:
        Your settings are pre-filled from the check configuration. Confirm the following
        are selected, then close the panel:
        - Survey Key: **KEY**
        - Survey ID: **hhid**
        - Survey Date: **submissiondate**
        - Enumerator ID: **enum_name**
        - Team: **team_id**

        If you have a Mapbox API token, enter it under **Mapbox API Token Configuration**
        and click **Save Mapbox Token** to enable all map visualizations.
        """,
        },
    }

    @classmethod
    def get_onboarding_message(cls, tab: CheckPage, message_id: str) -> str:
        """Retrieve onboarding messages based on type."""
        messages = {
            "summary": cls.SUMMARY,
            "progress": cls.PROGRESS,
            "duplicates": cls.DUPLICATES,
            "missing": cls.MISSING,
            "outliers": cls.OUTLIERS,
            "enumerators": cls.ENUMERATORS,
            "descriptive_stats": cls.DESCRIPTIVE_STATS,
            "backchecks": cls.BACKCHECKS,
            "gpschecks": cls.GPSCHECKS,
        }
        return messages.get(tab, {"invalid": "Invalid Message"}).get(
            message_id, "Invalid Message"
        )


def demo_output_onboarding(tab: str):
    """Decorator to display onboarding messages for demo functions."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            message_id = func.__name__
            message = OutputOnboardingInfo.get_onboarding_message(tab, message_id)
            title, content = message.get("title"), message.get("content")
            if is_demo_project():
                demo_expander(
                    title,
                    content,
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator


def is_demo_project() -> bool:
    """Check if the current session is using the demo project."""
    return st.session_state.get("st_project_id") == DEMO_PROJECT_ID


def set_onboarding_step(step: int):
    """Set the current onboarding step."""
    st.session_state["onboarding_step"] = step


def get_onboarding_step() -> int:
    """Get the current onboarding step."""
    if "onboarding_step" not in st.session_state:
        return 1
    return st.session_state["onboarding_step"]


def show_progress_indicator():
    """Display the onboarding progress indicator."""
    if not is_demo_project():
        return

    current_step = get_onboarding_step()

    st.markdown("### Demo Progress")

    onboarding_steps = OnboardingSteps.get_all_steps()

    cols = st.columns(len(onboarding_steps))

    for i, step_info in enumerate(onboarding_steps):
        step = step_info["step"]
        icon = step_info["icon"]
        title = step_info["title"]
        with cols[i]:
            if step < current_step:
                st.success(f":material/check: **{title}**", icon=None)
            elif step == current_step:
                with st.container(border=True):
                    st.markdown(f"{icon} **Step {step}**  \n{title}")
            else:
                st.markdown(f"{icon} {title}")

    st.divider()


def show_demo_intro():
    """Display the demo introduction message."""
    demo_container("""
        **New to DataSure?** This guided demo walks you through a complete survey data quality
        workflow using realistic sample data. Expect to spend about **45 minutes** going through all steps.

        **What you will do:**

        1. **Import** - Load 132 household survey responses and 30 backcheck records
        2. **Prepare** - Transform and clean columns ready for analysis
        3. **Configure** - Set up quality check rules for your survey
        4. **Review** - Explore duplicate detection, missing data, outliers, enumerator stats, and more
        5. **Correct** - Log a data correction and watch its effect in the reports
        6. **Export** - Download a replication package with all scripts and audit logs

        **Demo data:** 132 household survey records from rural communities in India,
        with realistic data quality issues built in.
    """)


def show_demo_banner():
    """Display the demo mode banner."""
    if not is_demo_project():
        return

    st.info("""
    **Demo Mode Active** - You're exploring DataSure with sample data!
    This guided tour will show you how to use DataSure for survey data quality management.
    """)


def show_next_steps(current_step: int):
    """Show next steps and navigation options."""
    if not is_demo_project():
        return

    onboarding_steps = OnboardingSteps.get_all_steps()

    if current_step < len(onboarding_steps):
        next_step = onboarding_steps[current_step]  # next_step is 0-indexed

        st.markdown("### What's Next?")
        st.info(f"""
        **Next: {next_step["title"]}**
        {next_step["description"]}
        """)

        if current_step == 1:
            st.markdown("""
            **Ready to continue?** Click "Import Data" in the navigation menu to start importing your demo survey data!
            """)
    else:
        st.success("""
        **Congratulations!** You've completed the DataSure demo.

        **What you've learned:**
        - How to import and prepare survey data
        - How to run comprehensive data quality checks
        - How to interpret quality reports and take action

        **Ready to use DataSure with your own data?**
        """)

        if st.button("Start New Project", type="primary"):
            # Clear demo project and redirect to start
            st.session_state.st_project_id = ""
            st.session_state.pop("onboarding_step", None)
            st.rerun()


def create_demo_project():
    """Create and initialize the demo project."""
    # Save demo project
    project_path = get_cache_path(DEMO_PROJECT_ID)
    if not project_path.exists():
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / "data").mkdir(exist_ok=True)
        (project_path / "settings").mkdir(exist_ok=True)

    # Save project info
    projects_file = get_cache_path("projects.json")
    projects = {}
    if projects_file.exists():
        with open(projects_file) as f:
            projects = json.load(f)

    projects[DEMO_PROJECT_ID] = {
        "name": DEMO_PROJECT_NAME,
        "created_at": "2025-01-01 00:00:00",
        "last_used": "2025-01-01 00:00:00",
        "is_demo": True,
    }

    with open(projects_file, "w") as f:
        json.dump(projects, f, indent=4)

    return DEMO_PROJECT_ID


class DemoDataGenerator:
    """Class to generate demo data with realistic date fields."""

    def __init__(self, df: pl.DataFrame):
        self.df = df

    def _gen_starttime(self) -> pl.DataFrame:
        """Generate starttime column with random dates within the last 60 days."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)
        random_dates = [
            start_date
            + timedelta(
                days=random.randint(0, 60),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            for _ in range(self.df.height)
        ]

        self.df = self.df.with_columns(
            [
                pl.Series("starttime", random_dates),
            ]
        )

        return self.df

    def _gen_endtime(self) -> pl.DataFrame:
        """Generate endtime to be starttime + random minutes between 15 and
        136 minutes.
        """
        end_times = [
            start + timedelta(minutes=random.randint(15, 136))
            for start in self.df["starttime"]
        ]

        self.df = self.df.with_columns(
            [
                pl.Series("endtime", end_times),
            ]
        )
        return self.df

    def _gen_submissiondate(self) -> pl.DataFrame:
        """Generate submissiondate to be endtime + random minutes between 1
        and 30 minutes.
        """
        submission_dates = [
            end + timedelta(minutes=random.randint(1, 30)) for end in self.df["endtime"]
        ]

        self.df = self.df.with_columns(
            [
                pl.Series("submissiondate", submission_dates),
            ]
        )
        return self.df

    def _gen_dates(self) -> pl.DataFrame:
        """Generate all date columns."""
        self._gen_starttime()
        self._gen_endtime()
        self._gen_submissiondate()

        # convert datetime columns to string
        self.df = self.df.with_columns(
            [
                pl.col("starttime").cast(pl.Utf8),
                pl.col("endtime").cast(pl.Utf8),
                pl.col("submissiondate").cast(pl.Utf8),
            ]
        )

        # remove milliseconds from the datetime strings
        self.df = self.df.with_columns(
            [
                pl.col("starttime").str.replace(r"\.\d{3}", "", literal=False),
                pl.col("endtime").str.replace(r"\.\d{3}", "", literal=False),
                pl.col("submissiondate").str.replace(r"\.\d{3}", "", literal=False),
            ]
        )

        # convert seconds from 5 digits to 2 digits
        self.df = self.df.with_columns(
            [
                pl.col("starttime").str.replace(
                    r":(\d{2})\d{3}", r":00", literal=False
                ),
                pl.col("endtime").str.replace(r":(\d{2})\d{3}", r":00", literal=False),
                pl.col("submissiondate").str.replace(
                    r":(\d{2})\d{3}", r":00", literal=False
                ),
            ]
        )

        return self.df

    def _gen_consent_status(self):
        """Generate consent column with 'yes' or 'no' values."""
        consent_values = ["yes", "no"]
        random_consents = [
            random.choices(consent_values, weights=[0.98, 0.02])[0]
            for _ in range(self.df.height)
        ]

        self.df = self.df.with_columns(
            [
                pl.Series("consent", random_consents),
            ]
        )

        return self.df

    def _gen_completion_status(self):
        """Generate completion_status column with 'complete' or 'incomplete' values."""
        status_values = ["complete", "incomplete"]
        random_statuses = [
            random.choices(status_values, weights=[0.95, 0.05])[0]
            for _ in range(self.df.height)
        ]

        self.df = self.df.with_columns(
            [
                pl.Series("completion_status", random_statuses),
            ]
        )

        return self.df

    def add_demo_fields(self, datatype: str = "survey") -> pl.DataFrame:
        """Add all demo fields."""
        self._gen_dates()
        if datatype == "survey":
            self._gen_consent_status()
            self._gen_completion_status()
        return self.df


# Load csv files with flexible parsing
def load_csv_flexibly(file_path: Path) -> pl.DataFrame:
    """Load CSV file with flexible parsing using polars and pandas as fallback."""
    try:
        df = pl.read_csv(str(file_path), truncate_ragged_lines=True, ignore_errors=True)
    except Exception as e:
        st.error(f"Error loading CSV data: {e}")
        try:
            df = pl.from_pandas(pd.read_csv(str(file_path)))
        except Exception as fallback_e:
            st.error(f"Failed to load CSV data with fallback method: {fallback_e}")
            raise e  # noqa: B904
    return df


def load_demo_data() -> bool:
    """Load demo data files into the demo project."""
    # Get asset paths
    assets_dir = Path(__file__).parent.parent / "assets"
    survey_path = assets_dir / "demo_survey.csv"
    backcheck_path = assets_dir / "demo_backcheck.csv"

    if not survey_path.exists() or not backcheck_path.exists():
        st.error("Demo data files not found. Please check the installation.")
        return False

    # Load survey data with flexible CSV parsing
    try:
        survey_df = load_csv_flexibly(survey_path)
    except Exception:
        return False

    try:
        backcheck_df = load_csv_flexibly(backcheck_path)
    except Exception:
        return False

    survey_df = DemoDataGenerator(survey_df).add_demo_fields()

    # Save to raw database (for import system)
    duckdb_save_table(DEMO_PROJECT_ID, survey_df, "demo_survey", "raw")

    # clean prep/corrected entries
    duckdb_remove_table(DEMO_PROJECT_ID, "demo_survey", "prep")
    duckdb_remove_table(DEMO_PROJECT_ID, "demo_survey", "corrected")

    # Load backcheck data with flexible CSV parsing
    backcheck_df = pl.read_csv(
        str(backcheck_path), truncate_ragged_lines=True, ignore_errors=True
    )

    backcheck_df = DemoDataGenerator(backcheck_df).add_demo_fields("backcheck")

    # Save to raw database (for import system)
    duckdb_save_table(DEMO_PROJECT_ID, backcheck_df, "demo_backcheck", "raw")

    # clean prep/corrected entries
    duckdb_remove_table(DEMO_PROJECT_ID, "demo_backcheck", "prep")
    duckdb_remove_table(DEMO_PROJECT_ID, "demo_backcheck", "corrected")

    # clean log entries
    duckdb_remove_table(DEMO_PROJECT_ID, "prep_log_demo_survey", "logs")
    duckdb_remove_table(DEMO_PROJECT_ID, "prep_log_demo_backcheck", "logs")
    duckdb_remove_table(DEMO_PROJECT_ID, "check_config", "logs")

    # Create import log entries to register the data as imported
    import_log_data = [
        {
            "refresh": True,
            "load": True,
            "alias": "demo_survey",
            "filename": "demo_survey.csv",
            "sheet_name": None,
            "source": "Demo Data",
            "server": None,
            "username": None,
            "form_id": None,
            "private_key": None,
            "save_to": None,
            "attachments": False,
        },
        {
            "refresh": True,
            "load": True,
            "alias": "demo_backcheck",
            "filename": "demo_backcheck.csv",
            "sheet_name": None,
            "source": "Demo Data",
            "server": None,
            "username": None,
            "form_id": None,
            "private_key": None,
            "save_to": None,
            "attachments": False,
        },
    ]

    import_log_df = pl.DataFrame(import_log_data)
    duckdb_save_table(DEMO_PROJECT_ID, import_log_df, "import_log", "logs")

    # Create empty prep logs for each dataset
    for alias in ["demo_survey", "demo_backcheck"]:
        empty_prep_log = pl.DataFrame({"action": [], "description": []})
        duckdb_save_table(DEMO_PROJECT_ID, empty_prep_log, f"prep_log_{alias}", "logs")

    # Update session state with loaded datasets
    st.session_state.st_raw_dataset_list = ["demo_survey", "demo_backcheck"]

    return True


def is_demo_complete() -> bool:
    """Check if the demo has been completed."""
    onboarding_steps = OnboardingSteps.get_all_steps()
    return get_onboarding_step() >= len(onboarding_steps)


def show_demo_completion_message():
    """Show completion message and options."""
    if not is_demo_project() or not is_demo_complete():
        return

    st.balloons()

    st.success("""
    **Demo Complete!**

    You've successfully learned how to use DataSure for survey data quality management!
    """)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Restart Demo", width="stretch"):
            set_onboarding_step(1)
            st.rerun()

    with col2:
        if st.button("Create Real Project", type="primary", width="stretch"):
            st.session_state.st_project_id = ""
            st.session_state.pop("onboarding_step", None)
            st.switch_page("pages/start_view.py")


def demo_expander(title: str, content: str, expanded: bool = True):
    """Create a demo-specific expander with helpful information."""
    if not is_demo_project():
        return

    with st.expander(f"**Learn More: {title}**", expanded=expanded):
        demo_container(content)
