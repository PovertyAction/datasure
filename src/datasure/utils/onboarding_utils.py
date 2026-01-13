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
    """Create a colored container for demo messages."""
    with st.container():
        st.markdown(
            f"""
        <div style="padding: 10px; background-color: #F0EBE3;border-radius: 10px; border: 1px solid #D4C5A9;">
            {text}
        </div>
        """,
            unsafe_allow_html=True,
        )

    # add some spacing after the container
    st.markdown("<br>", unsafe_allow_html=True)


class ImportDemoInfo:
    """Class to provide demo messages for import scenarios."""

    ADD_TO_SESSION_INFO: ClassVar[str] = """
        Great! You've successfully loaded your demo survey data.
        You can see the survey data and backcheck data are now available for analysis.
        success
    """

    PREVIEW_DATA_INFO: ClassVar[str] = """
        Data import complete! Your demo datasets are loaded and ready for quality analysis. "
        In a real project, this is what you would see after importing from SurveyCTO or uploading CSV files."
        success
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
        **You are ready to view your HFC reports:**
        Your demo data is now prepared for quality analysis. In a real project, this is what you would see after preparing your data for quality checks.

        **Next:** Click on the "View Quality Reports" button to explore comprehensive data quality insights and reports!
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

        **🎆 What happens next:** DataSure creates a comprehensive quality analysis page with all configured checks!
    """

    ADD_PREP_STEPS_INFO: ClassVar[str] = """
        You will need to add a data preparation step to convert the submissiondate
        column to a date format for both the survey and backcheck surveys. This is a
        crucial step to ensure accurate date handling in your analysis.
    """

    ADD_CORRECTION_STEP_INFO: ClassVar[str] = """
        You are about to make corrections to the demo_survey dataset.
        Follow the instructions provided in the guidance section to apply the necessary corrections.

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
        "icon": "🏠",
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
        "icon": "📥",
        "page": "import_view.py",
        "guidance_title": "Data Successfully Imported!",
        "guidance_content": """
        ##### ✅ Your demo data is already loaded and ready!

        In a real project, you would have just:
        - Connected to your SurveyCTO server, OR
        - Uploaded CSV/Excel files from your computer, OR

        ##### What's been imported for you:
        - **Survey Data**: 132 household survey responses from rural communities
        - **Backcheck Data**: 30 quality control validation records

        ##### Both datasets contain realistic data quality issues

        **including**:
        - Missing data
        - Duplicate household IDs
        - Inconsistent income reporting
        - Missing demographic information

        **👉 Ready for the next step:** Explore your data in the **Preview Imported Data** section.
        Switch between the **demo_backcheck** and **demo_survey** datasets to see what's inside!
        """,
    }

    PREPARE: ClassVar[dict] = {
        "step": 3,
        "title": "Prepare Data",
        "description": "Clean and prepare your data for quality checks.",
        "icon": "🛠️",
        "page": "prep_view.py",
        "guidance_title": "Data Preparation (Optional)",
        "guidance_content": """
        ##### ✅ Your demo data is ALMOST ready for analysis!

        ##### What you're seeing:
        - Tools to transform, clean, and modify your data
        - Your imported survey data displayed in tabs
        - Data metrics showing rows, columns, and missing values

        ##### What to prepare:
        - In a real project, you might also want to:
            - Transform additional columns
            - Remove unwanted rows or columns
            - Create new columns
            - Handle missing values
        - For this demo, you will only need to convert the submissiondate column to a date format.

        **👉 Ready to prepare your data?** Go to the "Get your data ready" section!
        """,
    }

    CONFIGURE: ClassVar[dict] = {
        "step": 4,
        "title": "Configure Checks",
        "description": "Set up data quality checks and validation rules.",
        "icon": "⚙️",
        "page": "config_view.py",
        "guidance_title": "Configure Quality Checks",
        "guidance_content": """
        ##### 🔧 Set up your data quality checks!

        ##### What you're doing in this step:
        - Creating a "check configuration" that tells DataSure how to analyze your data
        - Mapping your data columns to specific quality checks (using categorized column types)
        - Connecting your survey data with backcheck data for validation
        - Setting validation rules using Pydantic models for data integrity

        ##### Demo Instructions:
        1. **Click ":material/add: Add new check configuration"**
            - A dialog window will appear with a step-by-step form
        2. **Name your configuration**: Enter "Household HFCs" or similar (1-20 characters)
        3. **Select Survey Dataset**: Choose "demo_survey" from the dropdown
            - The system will automatically categorize columns by type (datetime, numeric, categorical)
        4. **Configure Key Columns** (note column categories will be shown):
            - **Key Column**: "KEY" (unique row identifier) - from categorical columns
            - **ID Column**: "hhid" (Unique household identifier) - from categorical columns
            - **Enumerator Column**: "enum_name" (who collected the data) - from categorical columns
            - **Date Column**: "submissiondate" (submission date) - from datetime columns
            - **Survey Target** (optional): Enter 200 (expected number of interviews)
        5. **Add Backcheck Dataset** (optional):
            - Toggle "Add backcheck dataset" to expand options
            - **Backcheck Dataset**: Choose "demo_backcheck"
            - **Backcheck Date**: Choose "submissiondate"
            - **Backchecker**: Choose "backchecker_name"
            - **Backcheck Target %**: Enter 10 (percentage of surveys to backcheck)
        6. **Click "Submit"** to create the configuration
            - DataSure will validate all inputs
            - A new output page will be automatically created

        ##### What DataSure will analyze:
        - Duplicate household records and missing data patterns
        - Enumerator performance and data collection quality
        - Statistical outliers with configurable detection methods (IQR/Standard Deviation)
        - Backcheck validation comparing survey responses to quality control visits

        **🎆 Next step:** View comprehensive quality analysis reports on your new output page!
        """,
    }

    OUTPUTS: ClassVar[dict] = {
        "step": 5,
        "title": "Review Reports",
        "description": "Analyze data quality results and insights.",
        "icon": "📊",
        "page": "output_view_1.py",
        "guidance_title": "Review Quality Reports",
        "guidance_content": """
        ##### In this step you'll:
        - Analyze data quality results
        - Understand quality metrics
        - Learn how to act on findings

        **Final step:** Discover insights about your data quality and learn how to improve
        data collection processes based on the findings.
        """,
    }

    CORRECT: ClassVar[dict] = {
        "step": 6,
        "title": "Correct Data",
        "description": "Make corrections to your data based on quality findings.",
        "icon": "🧹",
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
        with st.expander(f"📖 **{guidance['guidance_title']}**", expanded=True):
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

        **Next**: Click on the settings icon (⚙️) to configure global settings for the summary tab.
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
        For the demo data, you will need to indicate a total of **200** expected interviews,

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
        - This Week: Number of submissions received in the current week.
        - This Month: Number of submissions received in the current month.
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
        - Average Submissions per Day: The average number of submissions received per day.
        - Average Submissions Per Week: The average number of submissions received per week.
        - Average Submissions Per Month: The average number of submissions received per month.

        **Next**: Explore the progress by sub sections below.

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
        - % of values flagged as outliers: Percentage of data points identified as outliers based on statistical analysis.
        - % of missing values in survey dataset: Percentage of missing or null values in the survey dataset.
        - Backcheck error rate: Percentage of discrepancies found between survey data and backcheck data.

        **Next**: Explore the "Survey Progress" tab.
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
        **Next**: Go to the settings icon (⚙️) to configure global settings for the survey progress tab.
        """,
        },
        "progress_report_settings": {
            "title": "Progress Settings",
            "content": """
        ##### Setup for Survey Progress Tab
        In this section, you can configure global settings for the survey progress tab, you will notice that some settings are pre-filled based on your check configuration.
        This tab contains the following settings:
        - Survey ID: The main identifier for your survey respondents (e.g., household ID, Respondent ID).
        - Date: The date when the survey was conducted or submitted. (e.g., submissiondate, starttime).\
        - Enumerator: The column indicating who collected the data (e.g., enumerator name or ID).
        - Target Number of Interviews: The total number of survey interviews you expect to have in your dataset (e.g., 1000).
        ##### Instructions for Demo:
        For the demo data, you will need to indicate a total of **200** expected interviews,
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
        **Next**: Explore the **Submission Trend** section below.
        """,
        },
        "display_progress_overtime": {
            "title": "Progress Over Time",
            "content": """
        ##### Submission Trends
        This section visualizes the submission trends of your survey data over time, helping you identify patterns and peaks in data collection.

        ##### Instructions for Demo:
        For the demo, toggle between different time intervals to see how submission trends vary:
        - At the top left of the chart, switch between "Day", "Week", and "Month" views to see submission trends over different time intervals.
        The "Day" view shows daily submission counts, the "Week" view aggregates submissions by week, and the "Month" view summarizes submissions on a monthly basis.
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
        - A bar chart visualizing the count of attempted interviews over time.
        - A data table summarizing attempted interviews by respondent ID (eg. household ID).
        **Next**: Explore the **Consent and Completion Progress Chart** section below.
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
        "duplicate_report": {
            "title": "Duplicate Records Report",
            "content": """
        ### Duplicates Report
        This tab provides detailed insights into duplicate records in your survey data.
        It includes reports for duplicates on your ID column as well as other columns in your dataset.
        **Next**: Go to the settings icon (⚙️) to configure global settings for the duplicates tab.
        """,
        },
        "duplicates_settings": {
            "title": "Duplicates Settings",
            "content": """
        ##### Setup for Duplicates Tab
        In this section, you can configure global settings for the duplicates tab, you will notice that some settings are pre-filled based on your check configuration.
        This tab contains the following settings:
        - Survey ID: The main identifier for your survey respondents (e.g., household ID, Respondent ID).
        - Survey Key: The unique key column for your survey dataset (e.g., KEY). This is different from the Survey ID which identifies unique respondents.
                                If your dataset does not have a unique key column, you can create one during data preparation.
        - Date: The date when the survey was conducted or submitted. (e.g., submissiondate, starttime).
        - Columns: Select the columns you want to check for duplicates. You can choose one or more columns from your dataset. Note that the ID column is always included in the duplicate checks.
        **Next**: Explore the **Duplicate Records on ID Column** section below.
        """,
        },
        "display_duplicates_statistics": {
            "title": "Duplicate Records on ID Column",
            "content": """
        ##### Duplicate Records on ID Column
        This section provides insights into duplicate records based on your ID column and other duplicate columns added, including:
        - Total Duplicate: Total number of duplicate records found in the dataset.
        - Resolved Duplicates: Number of duplicate records that have been resolved.
        - Columns Checked: Number of columns selected for duplicate checks.
        - Columns With No Duplicates: Number of columns checked that have no duplicate records.
        - Columns With Duplicates: Number of columns checked that have duplicate records.
        - Survey ID Duplicates: Number of unique survey IDs that have duplicate records.
        **Next**: Explore the **Duplicate Records Table** section below.
        """,
        },
        "display_id_duplicates": {
            "title": "Duplicate Records Table",
            "content": """
        - Table of duplicate records showing details such as survey ID, duplicate column values, count of duplicates, and resolution status.
        ##### Instructions for Demo:
        For the demo, explore the duplicate records found on the "hhid" column. At the **Select columns to display in the report** dropdown, choose "enum_name" and "state" to see additional context about the duplicates.
        You may also select other columns to see how duplicates vary across different attributes.
        **Next**: Look at the instructions for the **Duplictate Entries for columns** section below.
        """,
        },
        "display_column_duplicates": {
            "title": "Duplicate Entries for Other Columns",
            "content": """
        ##### Duplicate Entries for Other Columns
        This section provides insights into duplicate records based on other columns in your dataset that were selected in the settings section, including:
        - Table of duplicate records for each selected column showing details such as column name, duplicate values, count of duplicates, and resolution status.
        ##### Instructions for Demo:
        The dataset for the demo does not contain other columns for which we want to check duplicates. However, in a real project, you can select multiple columns in the settings section to identify duplicates across different attributes.
        These could include columns like "address", "phone number", "ID number", etc.
        **Next**: Explore the **Missing Data** tab.
        """,
        },
    }
    MISSING: ClassVar[dict] = {
        "missing_report": {
            "title": "Missing Data Report",
            "content": """
        ### Missing Data Report
        This tab provides detailed insights into missing data in your survey dataset.
        It includes reports on missing values by column as well as patterns of missing data across records.
        **Next**: Go to the settings icon (⚙️) to configure global settings for the missing data tab.
        """,
        },
        "missing_settings": {
            "title": "Missing Data Settings",
            "content": """
        ##### Setup for Missing Data Tab
        In this section, you can configure global settings for the missing data tab, you will notice that some settings are pre-filled with default values.

        **Important**: DataSure automatically standardizes 80+ common missing value representations during data preparation, including:
        - Empty strings and whitespace ("", "   ", "\\t", "\\n")
        - NULL variants ("NULL", "null", "None", "none")
        - N/A variants ("N/A", "n/a", "NA", "#N/A")
        - Common placeholders ("-", "--", ".", "?", "???")
        - Explicit missing labels ("Missing", "missing", "Unknown", "unknown")
        - String NaN representations ("NaN", "nan", "NaT")

        This tab contains the following settings:
        - Each row indicates a **specific coded missing value type** (e.g., Don't know = -99, Refused = -88, etc.)
        - The **Missing Labels** column allows you to specify custom labels that represent missing data in your dataset. This label will be used in the reports
        to show counts of missing values based on this category.
        - The **Missing Codes** column allows you to specify numeric or text codes that represent missing data in your dataset. This value will be used to calculate the counts of missing values based on this category.
        Multiple codes can be separated by commas (e.g., "99,999" or "-99,-999")

        ##### Instructions for Demo:
        In a real project, you should standardize your survey programming to use consistent missing data codes (e.g., always use -999, not sometimes .999).
        For this demo, edit each row to use the following missing codes:
        - Use the code **-99** for the "Don't Know" row
        - Use the code **-88** for the "Refused to Answer" row
        - Use the code **-77** for the "Not Applicable" row

        **Next**: Explore the **Missing Data Statistics** section below.
        """,
        },
        "missing_summary": {
            "title": "Missing Data Statistics",
            "content": """
        ##### Missing Data Statistics
        This section provides insights into missing data in your survey dataset, including:
        - Percentage of missing values: Overall percentage of missing values in the dataset.
        - % of columns with missing values: Percentage of columns that contain missing values.
        - % of columns with at least one missing value: Percentage of columns that have at least one missing value.
        - % of columns with no missing values: Percentage of columns that do not contain any missing values.
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
            - Don't KNow: Count of values marked as "Don't Know".
            - % Don't Know: Percentage of values marked as "Don't Know".
            - Refused to Answer: Count of values marked as "Refused to Answer".
            - % Refused to Answer: Percentage of values marked as "Refused to Answer".
            - Not Applicable: Count of values marked as "Not Applicable".
            - % Not Applicable: Percentage of values marked as "Not Applicable".
        - The table can be sorted by any of the columns to help identify which columns have the highest or lowest missing data.
        - The table also includes a "Filter Report by % missing" slider at the top left to allow you to filter the report based on a minimum percentage of missing data.

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
        - A dropdow to select columns to compare. By default, all columns will be used but an aggregate view will be shown.
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
        **Next**: Explore the **Nullity COrrection** section below.
        """,
        },
        "missing_correlation": {
            "title": "Nullity Correlation",
            "content": """
        ##### Nullity Correlation
        This section provides insights into the correlation of missing data between different columns in your dataset, helping you identify patterns and relationships in missingness, including:
        - A heatmap visualizing the correlation of missing values between columns.

        ##### Instructions for Demo:
        For the demo,
        - at the **Select columns to include in nullity correlation** dropdown, choose "min_dist" and "travel_sch" to see how missing data in these specific columns correlates with each other.
        - You will notice that whenever "min_dist" is missing, "travel_sch" is also missing. Which makes sense since if the distance to school is not recorded, the mode of travel to school is also likely not recorded.

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
        **Next**: Explore **outliers** tab.
        """,
        },
    }
    OUTLIERS: ClassVar[dict] = {
        "outlier_report": {
            "title": "Outliers Report",
            "content": """
        ### Outliers Report
        This tab provides detailed insights into outliers in your survey dataset.
        It includes reports on outlier values by column as well as patterns of outliers across records.
        **Next**: Go to the settings icon (⚙️) to configure global settings for the outliers tab.
        """,
        },
        "outliers_report_settings": {
            "title": "Outliers Settings",
            "content": """
        ##### Setup for Outliers Tab
        In this section, you can configure global settings for the outliers tab. DataSure uses Pydantic models for configuration validation to ensure data integrity.

        This tab contains the following settings:
        - **Admin Settings**:
            - **Survey ID**: The main identifier for your survey respondents (e.g., household ID, Respondent ID).
            - **Survey Key**: The unique key column for your survey dataset (e.g., KEY). This is different from the Survey ID which identifies unique respondents.
            - **Enumerator ID**: The column indicating who collected the data (e.g., enumerator name or ID).
        - **Display Settings**:
            - **Display Columns**: Select the columns you want to display in the outliers report table.
            - **Minimum Threshold**: Set the minimum number of non-missing values required for a column to be included in the outliers analysis.
            The default thresholds are:
                - **IQR Method**: 20 non-missing values minimum
                - **Standard Deviation Method**: 30 non-missing values minimum
        - **Outlier Columns Configuration**:
            - Click ":material/add: Add Outlier Column" to add columns for outlier analysis. You can select one or more numeric columns from your dataset to check for outliers.

            **Configuration options include**:
                - **Search Type**: Specifies how to search for columns. Choose from:
                    - "exact" - Match exact column name
                    - "contains" - Find columns containing the search text (e.g., "land" finds "land_acre", "land_rent")
                    - "starts_with" - Match columns starting with search text
                    - "ends_with" - Match columns ending with search text
                - **Select Columns to Check for Outliers**: Choose one or more numeric columns from your dataset. Uses text input with search functionality.
                - **Select Outlier Detection Method**: Choose between:
                    - **IQR (Interquartile Range)**: Default multiplier 1.5, minimum threshold 20 values
                    - **SD (Standard Deviation)**: Default multiplier 3.0, minimum threshold 30 values
                - **Select Multiplier for Outlier Detection**: Set the sensitivity of outlier detection:
                    - IQR: Common values are 1.5 (default), 2.0, 2.5, 3.0
                    - SD: Common values are 2.0, 2.5, 3.0 (default), 3.5, 4.0
                - **(Optional) Soft Minimum**: Set a hard floor - values below this threshold are automatically flagged as outliers
                - **(Optional) Soft Maximum**: Set a hard ceiling - values above this threshold are automatically flagged as outliers
            - Click ":material/delete:" button to remove an outlier column from the analysis.

        ##### Instructions for Demo:
        For the demo data, add the following outlier columns:
        1. Click on ":material/add: Add Outlier Column"
        2. For **search type** select "exact"
        3. For **select columns to check for outliers** select "land_acre" and "household_count"
        4. Leave the default settings for the rest (IQR method with 1.5 multiplier)
        5. Click "Apply" to add the selected columns to the outliers analysis

        **(OPTIONAL)** Add more outlier columns by repeating the steps above with different search types.

        **Next**: Explore the **Outliers Summary** section below.
        """,
        },
        "display_outlier_metrics": {
            "title": "Outliers Statistics",
            "content": """
        ##### Outliers Statistics
        This section provides insights into outliers in your survey dataset, including:
        - Variables Checked: Number of numeric columns checked for outliers. If a column has less than the minimum threshold of non-missing values, it will not be included in the outliers analysis.
        - Outlier Variables: Number of columns that contain at least 1 outlier value.
        - Number of Outliers: Total number of outlier values identified across all checked columns.
        """,
        },
        "display_outlier_column_summary": {
            "title": "Outlier Summaries",
            "content": """
        ##### Outlier Summaries
        This section provides a detailed view of outlier data by column, including:
            - A table showing each outlier column in the dataset with the following details:
            - Column Name: Name of the outlier column.
            - # of values: Total number of non-missing values in the column.
            - # of outliers: Total number of outlier values identified in the column.
            - Minimum Value: Minimum value in the column.
            - Maximum Value: Maximum value in the column.
            - Mean: Mean (average) value of the column.
            - Median: Median (middle) value of the column.
            - Standard Deviation: Standard deviation of the column.
            - Interquartile Range: Interquartile range of the column.
            - Lower Bound: Lower bound for outlier detection based on the selected method and multiplier.
            - Upper Bound: Upper bound for outlier detection based on the selected method and multiplier.
        **Next**: Explore the **Outlier Details Table** section below.
        """,
        },
        "display_outlier_output": {
            "title": "Outlier Details Table",
            "content": """
        ##### Outlier Details Table
        This section provides detailed information about the outlier values identified in your dataset, including:
        - A table showing each outlier record with the following details:
        - Key column: Unique key for the record.
        - Survey ID: Identifier for the survey respondent.
        - Enumerator ID: Identifier for the enumerator who collected the data.
        - Column Name: Name of the outlier column.
        - Outlier Value: The actual outlier value identified in the column.
        - *Column Statistics: Minimum, Maximum, Mean, Median, Standard Deviation, Interquartile Range, Lower Bound, Upper Bound for the outlier column.
        - *Other Display Columns: Any additional columns selected in the settings section to be displayed in the outliers report table.
        - Outlier Reason: Explanation of why the value was identified as an outlier (e.g., "Above Upper Bound", "Below Lower Bound").
        - Outlier Multiplier: The multiplier value used for outlier detection.
        - Soft Minimum: The soft minimum threshold set for outlier detection.
        - Soft Maximum: The soft maximum threshold set for outlier detection.
        """,
        },
        "inspect_outliers_columns": {
            "title": "Inspect Outlier Columns",
            "content": """
        ##### Inspect Outlier Columns
        This section allows you to visually inspect the distribution of outlier values in your dataset, including:
        - A dropdown to select an outlier column to visualize.
        - A dropdown to select the selct columns to display
        - Statistics for the selected outlier column, including Minimum, Maximum, Mean, Median, Standard Deviation, Interquartile Range, Lower Bound, Upper Bound.
        - A histogram visualizing the distribution of values in the selected outlier column, with outlier values highlighted.
        - A violin plot showing the distribution of values in the selected outlier column, with outlier values highlighted.
        - A table showing all records for the selected outlier column, including key column, survey ID, enumerator ID, outlier value, and other display columns and an indication of whether the value is an outlier.

        ##### Instructions for Demo:
        For inspect each of the outlier columns.

        **Next**: Explore the **Enumerator Stats** tab.
        """,
        },
    }
    ENUMERATORS: ClassVar[dict] = {
        "enumerator_report": {
            "title": "Enumerator Stats Report",
            "content": """
        ### Enumerator Stats Report
        This tab provides detailed insights into enumerator performance in your survey dataset.
        It includes reports on various metrics such as number of interviews conducted, data quality issues identified, and overall enumerator performance.
        **Next**: Go to the settings icon (⚙️) to configure global settings for the enumerator stats tab.
        """,
        },
        "enumerator_report_settings": {
            "title": "Enumerator Stats Settings",
            "content": """
        ##### Setup for Enumerator Stats Tab
        In this section, you can configure global settings for the enumerator stats tab, you will notice that some settings are pre-filled with default values.
        This tab contains the following settings:
        - Date: The date when the survey was conducted or submitted. (e.g., submissiondate, starttime).
        - Form Version: The version of the survey form used for data collection (e.g., form_version).
        - Survey ID: The main identifier for your survey respondents (e.g., household ID, Respondent ID).
        - Duration: The column indicating the duration of each survey interview (e.g., duration).
        - Enumerator: The column indicating who collected the data (e.g., enumerator name or ID).
        - Team: The column indicating the team or group the enumerator belongs to (e.g., team_name).
        - Consent: The column indicating whether the respondent provided consent (e.g., consent).
        - Consent Value: The value in the consent column that indicates consent was given (e.g., yes).
        - Outcome: The column indicating the outcome status of the survey (e.g., completion_status).
        - Outcome Value: The value in the outcome column that indicates a completed survey (e.g., complete).

        ##### Instructions for Demo:
        For the demo data, set the following values:
        - Duration: Select "duration"
        - Team: Select "team_id"
        - Consent: Select "consent"
        - Consent Value: Set to "yes"
        - Outcome: Select "completion_status"
        - Outcome Value: Set to "complete"

        **Next**: Explore the **Enumerator Overview** section below.
        """,
        },
        "display_enumerator_overview": {
            "title": "Enumerator Overview",
            "content": """
        ##### Enumerator Overview
        This section provides a quick overview of enumerator performance in your survey dataset, including:
        - Total Number Enumerators: Total number of unique enumerators in the dataset.
        - Total Number of Teams: Total number of unique teams in the dataset.
        - Active Enumerators (past 7 days): Number of enumerators who have submitted data in the past 7 days.
        - Percentage of active enumerators (past 7 days): Percentage of enumerators who have submitted data in the past 7 days.
        - Minimum number of submissions: Minimum number of submissions made by any enumerator.
        - Highest number of submissions: Maximum number of submissions made by any enumerator.
        - Average number of submissions: Average number of submissions made by enumerators.
        - Total number of submissions: Total number of submissions made by all enumerators.
        **Next**: Explore the **Top Performing Enumerators** in the **Enumerator Summary** section below.
        """,
        },
        "display_enumerator_summary": {
            "title": "Enumerator Summary",
            "content": """
        ##### Enumerator Summary
        This section provides a summary about enumerator performance in your survey dataset, including:
        - A table showing each enumerator with the following details:
            - Enumerator: Identifier for the enumerator.
            - First Submission: Date of the first submission made by the enumerator.
            - Last Submission: Date of the most recent submission made by the enumerator.
            - # submissions: Total number of submissions made by the enumerator.
            - # of unique dates: Number of unique dates on which the enumerator made submissions. This indicates the number of days the enumerator was active.
            - # number of submissions today: Number of submissions made by the enumerator on the current day.
            - # number of submissions this week: Number of submissions made by the enumerator in the current week.
            - # number of submissions this month: Number of submissions made by the enumerator in the current month.
            - # Null Values: Total number of null or missing values in the submissions made by the enumerator.
            - min duration: Minimum duration of submissions made by the enumerator.
            - max duration: Maximum duration of submissions made by the enumerator.
            - mean duration: Average duration of submissions made by the enumerator.
            - median duration: Median duration of submissions made by the enumerator.
            - % consent: Percentage of submissions where consent was given.
            - % completed survey: Percentage of submissions that were completed surveys.

        **Next**: Explore the **Enumerator Productivity** section below.
        """,
        },
        "display_enumerator_productivity": {
            "title": "Enumerator Productivity",
            "content": """
        ##### Enumerator Productivity
        This section visualizes enumerator productivity over time, helping you identify trends and patterns in data collection, including:
        - A table showing the number of submissions per enumerator over time.
        - Option to show productivity by day, week, or month.
        **Next**: Explore the **Enumerator Statistics** section below.
        """,
        },
        "display_enumerator_statistics": {
            "title": "Enumerator Statistics",
            "content": """
        ##### Enumerator Statistics
        This section provides detailed statistics about enumerator performance, including:
        - A table showing statistic for specific columns for each enumerator
        - User can select the column and statistics to display including count, mean, median, min, max, standard deviation, 25th percentile, and 75th percentile.

        ##### Instructions for Demo:
        For the demo, at the **Select column to analyze enumerator statistics** dropdown, choose "household_size" to see if there are differences by enumerator. Select the
        statistics: count, mean, min and max.

        **Next**: Explore the **Enumerator Statistics Over Time** section.
        """,
        },
        "display_enumerator_statistics_overtime": {
            "title": "Enumerator Statistics Over Time",
            "content": """
        ##### Enumerator Statistics Over Time
        This section visualizes enumerator statistics over time, helping you identify trends and patterns in data quality and performance, including:
        - A table showing selected statistics for a specific column per enumerator over time.
        - Option to show statistics by day, week, or month.
        - Option to select the statistic to display (e.g., mean, median, min, max, etc.)

        ##### Instructions for Demo:
        For the demo, at the **Select Column** dropdown, choose "household_size" to see if there are differences by enumerator. Select the statistic "mean" to see how the average household size varies by enumerator over time.
        Visualize by "week" to see broader trends.
        """,
        },
    }

    DESCRIPTIVE_STATS: ClassVar[dict] = {
        "descriptive_report": {
            "title": "Descriptive Statistics Report",
            "content": """
        ### Descriptive Statistics Report
        This tab provides detailed descriptive statistics for numeric columns in your survey dataset.
        It includes measures such as mean, median, standard deviation, min, max, and percentiles to help you understand the distribution and characteristics of your data.
        **Next**: Go to the settings icon (⚙️) to configure global settings for the descriptive statistics tab.
        """,
        },
        "descriptive_report_settings": {
            "title": "Descriptive Statistics Settings",
            "content": """
        ##### Setup for Descriptive Statistics Tab
        In this section, you can configure global settings for the descriptive statistics tab, you will notice
        that some settings are pre-filled with default values.
        This tab contains the following settings:
        - Select columns to include in descriptive statistics (maximum 10): Choose one or more numeric columns from your dataset to include in the descriptive statistics analysis.

        Note that individual descriptive statistics reports will be shown for each column selected.

        ##### Instructions for Demo:
        For the demo data, select the following columns:
        - Select the columns "age" and "household_count" for descriptive statistics analysis. When the tables are rendered, you will notice the following:
            - Basic Statistics: This toggle allows you to show only basic statistics (count, mean, std, min, 25%, 50%, 75%, max) in the descriptive statistics report table for this column. Switch on
            this toggle for the age column.
            - Select table type: This dropdown allows you to choose the type of table to display for the descriptive statistics report for this column.
            You can choose between a "one-way table", "two-way table" or "summary statistics". For the household count column,
            switch to the different table types to see how the data is presented in each format.

        **Next**: Explore the **Back Checks** tab.
        """,
        },
    }
    BACKCHECKS: ClassVar[dict] = {
        "backchecks_report": {
            "title": "Back Checks Report",
            "content": """
        ### Back Checks Report
        This tab provides detailed insights into back checks conducted for your survey dataset.
        It includes reports on back check outcomes, discrepancies identified, and overall back check performance.

        **Next**: Go to the settings icon (⚙️) to configure global settings for the back checks tab.
        """,
        },
        "backcheck_report_settings": {
            "title": "Back Checks Settings",
            "content": """
        ##### Setup for Back Checks Tab
        In this section, you can configure global settings for the back checks tab, you will notice that some settings are pre-filled with default values.
        This tab contains the following settings:
        - **Survey ID**: The main identifier for your survey respondents (e.g., household ID, Respondent ID).
        - **Survey Key**: The unique key column for your survey dataset (e.g., KEY). This is different from the Survey ID which identifies unique respondents
        - **Enumerator**: The column indicating who collected the data (e.g., enumerator name or ID).
        - **Back Checker**: The column indicating who conducted the back check (e.g., back_checker_name or ID).
        - **Date**: The date when the back check was conducted (e.g., back_check_date
        - **Target Number of backchecks**: The target number of back checks to be conducted as a percentage of total surveys collected (e.g., 10%).
        - **How would you like to handle duplicates**: Toggle to indicate whether to include or exclude duplicate survey records when calculating back check statistics.
        - :material/add: **Add Add a back check column**: Click this button to configure back check columns. You can add one or more back check columns from your dataset to analyze back check outcomes.

        ##### Instructions for Demo:
        For the demo data, set the following values:
        | column          | category | ok_range | comparison_condition  |
        |-----------------|----------|----------|-----------------------|
        | age             | 1        | 1        | ignore_missing_values |
        | household_count | 2        | None     | ignore_missing_values |
        | minc_pri        | 1        | None     | ignore_missing_values |
        | npinc_out       | 1        | None     | ignore_missing_values |
        | no_save         | 1        | None     | ignore_missing_values |
        | pri_govt_sch    | 1        | None     | ignore_missing_values |


        **Next**: Explore the **Back Check Summary** section below.
        """,
        },
        "display_category_and_trends": {
            "title": "Back Check Trends by Category",
            "content": """
        ##### Back Check Trends by Category
        This section shows the back check information by column category and the trends over time, including:
        - metrics for each back check category such as:
            - Number of columns in category
            - Number of values compared
            - Percentage of discrepancies found
        **Next**: Explore the **Error Trends** section below.
        """,
        },
        "display_error_trends": {
            "title": "Error Trends",
            "content": """
        ##### Back Check Error Trends Over Time
        This section visualizes back check error trends over time, helping you identify patterns and changes in back check performance, including:
        - A line chart showing the percentage of back check discrepancies over time.

        ##### Instructions for Demo:
        For this demo, remove the "2" in the "select back check category" section and select "weekly" in the "select time period" section to see how back check discrepancies vary over time.

        **Next**: Explore the **Column Statistics** section below.
        """,
        },
        "display_column_stats": {
            "title": "Back Check Column Statistics",
            "content": """
        ##### Back Check Column Statistics
        This section provides detailed statistics about back check performance for each back check column, including:
        - A table showing each back check column with the following details:
            - Column: Name of the back check column.
            - data type: Data type of the back check column.
            - Category: Category assigned to the back check column.
            - \# surveys: Total number of surveys where the back check column was compared.
            - \# backchecks: Total number of back checks conducted for the column.
            - \# compared: Total number of values compared for the back check column.
            - \# different: Total number of discrepancies found for the back check column.
            - error rate: Percentage of discrepancies found for the back check column.
        **Next**: Explore the **Back Check Details Table** section below.
        """,  # noqa: W605
        },
        "display_statistics_tables": {
            "title": "Enumerator Statistics",
            "content": """
        ##### Enumerator Statistics
        This section provides detailed statistics about back check performance for each enumerator, including:
        - A table showing each enumerator with the following details:
            - Enumerator: Identifier for the enumerator.
            - \# surveys: Total number of surveys where back checks were conducted by the enumerator.
            - \# back checked: Total number of enumerators surveys that have been back checked.
            - \# of values compared: Total number of values compared for back checks conducted by the enumerator.
            - \# different: Total number of discrepancies found for back checks conducted by the enumerator.
            - error rate: Percentage of discrepancies found for back checks conducted by the enumerator.

        ##### Back Checker Statistics
        This section provides detailed statistics about back check performance for each back checker, including:
        - A table showing each back checker with the following details:
            - Back Checker: Identifier for the back checker.
            - \# back checked: Total number of back checker surveys that have been back checked.
            - \# of values compared: Total number of values compared for back checks conducted by the back checker.
            - \# different: Total number of discrepancies found for back checks conducted by the back checker.
            - error rate: Percentage of discrepancies found for back checks conducted by the back checker.

        ##### Comparison Details
        This section provides detailed information about the back check comparisons made in your dataset, including:
        - A table showing each back check comparison with the following details:
            - Survey ID: Identifier for the survey respondent.
            - Enumerator: Identifier for the enumerator who collected the data.
            - Back Checker: Identifier for the back checker who conducted the back check.
            - Survey Value: The original value recorded in the survey.
            - Back Check Value: The value recorded during the back check.
            - Comparison Result: Result of the comparison (e.g., "not_compared", "different", "not_different").
            - Column Name: Name of the back check column.
        """,  # noqa: W605
        },
    }

    GPSCHECKS: ClassVar[dict] = {
        "gpschecks_report": {
            "title": "GPS Checks Report",
            "content": """
        ### GPS Checks Report
        This tab provides detailed insights into GPS data quality in your survey dataset.
        It includes reports on GPS accuracy, completeness, and overall GPS data quality.

        **Next**: Go to the settings icon (⚙️) to configure global settings for the GPS checks tab.
        """,
        },
        "gps_check_settings": {
            "title": "GPS Checks Settings",
            "content": """
        ##### Setup for GPS Checks Tab
        In this section, you can configure global settings for the GPS checks tab, you will notice that some settings are pre-filled with default values.
        This tab contains the following settings:
        - **Date**: The date when the survey was conducted or submitted. (e.g., submissiondate, starttime).
        - **Survey Key**: The unique key column for your survey dataset (e.g., KEY).
        - **Survey ID**: The main identifier for your survey respondents (e.g., household ID, Respondent ID).
        - **Enumerator**: The column indicating who collected the data (e.g., enumerator name or ID).

        ##### Adding GPS Columns:
        - On the right side of the settings page, you will see a toggle button labeled "Data contains GPS columns(s)"
        - Switch this toggle to "ON" to enable GPS column configuration.
        - The "GPS has latitude and longitude columns" toggle allows you to specify whether your dataset includes separate latitude and longitude columns for GPS data.
        When this toggle is enabled, you can add latitude and longitude columns directly, else you will need to add a single GPS column that contains both latitude and longitude information.

        ##### Instructions for Demo:
        For the demo, enable "GPS has latitude and longitude columns" toggle and add the following GPS columns:
        - Latitude Column: Select "household_latitude"
        - Longitude Column: Select "household_longitude"
        - Accuracy Column: Select "household_gps_accuracy"

        **Next**: Explore the **GPS Overview** section below.
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
    return st.session_state["onboarding_step"] or 1


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
        step_icon = step_info["icon"]
        step_title = step_info["title"]
        with cols[i]:
            if step <= current_step:
                # Completed or current step

                if step == current_step:
                    st.markdown(
                        f"""
                    <div style="text-align: center; padding: 10px; border: 2px solid #1f77b4; border-radius: 10px; background-color: #e6f3ff;">
                        <div style="font-size: 24px;">{step_icon}</div>
                        <div style="font-size: 12px; font-weight: bold; color: #1f77b4;">Step {step}</div>
                        <div style="font-size: 10px;">{step_title}</div>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"""
                    <div style="text-align: center; padding: 10px; border: 1px solid #28a745; border-radius: 10px; background-color: #d4edda;">
                        <div style="font-size: 20px; color: #28a745;">✓</div>
                        <div style="font-size: 12px; color: #28a745;">Step {step}</div>
                        <div style="font-size: 10px;">{step_title}</div>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )
            else:
                # Future step
                st.markdown(
                    f"""
                <div style="text-align: center; padding: 10px; border: 1px solid #dee2e6; border-radius: 10px; background-color: #f8f9fa;">
                    <div style="font-size: 20px; color: #6c757d;">{step_icon}</div>
                    <div style="font-size: 12px; color: #6c757d;">Step {step}</div>
                    <div style="font-size: 10px; color: #6c757d;">{step_title}</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

    st.markdown("---")


def show_demo_intro():
    """Display the demo introduction message."""
    demo_container("""
        **Start here, if you are new to DataSure.**

        This guided demo will walk you through:
        - Importing survey data
        - Running data quality checks
        - Identifying and understanding data issues
        - Generating quality reports

        **Demo data:** Household survey data from rural communities with realistic data quality challenges.
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
