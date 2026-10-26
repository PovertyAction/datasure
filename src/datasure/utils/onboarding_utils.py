import functools
import json
import logging
import random
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, NamedTuple

import pandas as pd
import polars as pl
import streamlit as st

from datasure.checks.backchecks.attribution import ErrorSource
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.duckdb_utils import duckdb_remove_table, duckdb_save_table

logger = logging.getLogger(__name__)

DEMO_PROJECT_NAME = "DataSure Demo"
DEMO_PROJECT_ID = "demoproject"
# Seed for the demo data generator, so every demo load draws the same values.
DEMO_SEED = 360


class DemoColumn(StrEnum):
    """Survey columns that demo guidance names.

    Guidance names a ``demo_survey`` column only through a member, so a test
    can check each one exists in the demo data. Add a member before naming a
    new column.
    """

    KEY = "KEY"
    HHID = "hhid"
    ENUM_NAME = "enum_name"
    TEAM_ID = "team_id"
    DURATION = "duration"
    SUBMISSIONDATE = "submissiondate"
    STATE = "state"
    CONSENT = "consent"
    COMPLETION_STATUS = "completion_status"
    AGE = "age"
    HOUSEHOLD_COUNT = "household_count"
    LAND_ACRE = "land_acre"
    CHILD_LOAN = "child_loan"
    PVT_SCH = "pvt_sch"
    MIN_DIST = "min_dist"
    TRAVEL_SCH = "travel_sch"
    HOUSEHOLD_LATITUDE = "household_latitude"
    HOUSEHOLD_LONGITUDE = "household_longitude"


class DemoBackcheckColumn(StrEnum):
    """Backcheck columns that demo guidance names, like ``DemoColumn``."""

    SUBMISSIONDATE = "submissiondate"
    BCER_NAME = "bcer_name"
    TEAM_ID = "team_id"
    AGE = "age"
    HOUSEHOLD_COUNT = "household_count"
    MINC_PRI = "minc_pri"
    NPINC_OUT = "npinc_out"
    NO_SAVE = "no_save"
    PRI_GOVT_SCH = "pri_govt_sch"


# Every column demo guidance names, by demo dataset alias.
DEMO_GUIDANCE_COLUMNS: dict[str, type[StrEnum]] = {
    "demo_survey": DemoColumn,
    "demo_backcheck": DemoBackcheckColumn,
}


# Demo survey values that guidance names. A test loads the demo data and
# checks each one, so name a new value here before using it in guidance.
class DemoDuplicate(NamedTuple):
    """A duplicated ``hhid`` in the demo survey and how guidance resolves it."""

    hhid: str
    # KEY of the record guidance changes; the other record is kept
    key: str
    # The ID to give that record with Modify ID, or None to Drop it
    new_hhid: str | None = None


DEMO_WRONG_ID = DemoDuplicate(
    "UP015-005", "uuid:0dk0vt97-786b-250u-34k7-z34615zz820c", "UP015-055"
)
DEMO_SHARED_ID = DemoDuplicate(
    "GJ013-025", "uuid:1qv2hs40-598s-540g-57l8-s35783yl358j", "GJ013-026"
)
DEMO_REPEAT_SUBMISSION = DemoDuplicate(
    "AN002-003", "uuid:0ur3to71-184r-159l-70j6-m68512uv803n"
)
DEMO_DUPLICATES = (DEMO_WRONG_ID, DEMO_SHARED_ID, DEMO_REPEAT_SUBMISSION)


class DemoRecord(NamedTuple):
    """A demo survey record that guidance names by ID and KEY."""

    hhid: str
    key: str


class DemoFlag(NamedTuple):
    """A demo survey value that guidance corrects or accepts as valid."""

    record: DemoRecord
    column: DemoColumn
    value: float
    # The value to correct it to, or None to accept it as valid
    new_value: float | None = None


# Fixed on the Correct Data page
DEMO_LAND_CORRECTION = DemoFlag(
    DemoRecord("UP015-001", "uuid:2pb7nd59-391r-425l-40h1-t18527gn249i"),
    DemoColumn.LAND_ACRE,
    75.5,
    5.5,
)


# Check configuration values that guidance names (#361). The walkthrough
# keeps DEMO_PAGE_NAME throughout: editing changes only the target, and
# removing uses the throwaway page, since renaming or removing the main page
# loses its saved settings. Page Name accepts at most 20 characters.
DEMO_PAGE_NAME = "Household HFCs"
DEMO_SURVEY_TARGET = 200
DEMO_EDITED_TARGET = 150
DEMO_THROWAWAY_PAGE = "Test HFCs"


# --- Check-page review guidance (#361) ---


class DemoBounds(NamedTuple):
    """Constraint bounds the Outliers guidance enters for a column."""

    hard_min: float
    soft_min: float
    soft_max: float
    hard_max: float


DEMO_AGE_BOUNDS = DemoBounds(18, 25, 60, 100)


# Age 24 is below the soft minimum only: unusual but plausible, so accepted
DEMO_OUTLIER_ACCEPT = DemoFlag(
    DemoRecord("AN016-034", "uuid:3xf5wk03-411r-454r-42q4-n97169wt312n"),
    DemoColumn.AGE,
    24,
)
# A misplaced decimal point, corrected in the Review dialog
DEMO_OUTLIER_CORRECTION = DemoFlag(
    DemoRecord("AN016-008", "uuid:7yq2ff04-784p-181b-06f6-y09055jv628g"),
    DemoColumn.LAND_ACRE,
    62.0,
    6.2,
)


# Surveyed in Deesa, north Gujarat, far from the other Gujarat households but
# a real village, so the GPS outlier is accepted as valid
DEMO_GPS_ACCEPT = DemoRecord("GJ047-006", "uuid:8tp6pf85-928c-834t-16f0-g13614ux693g")


class DemoMismatch(NamedTuple):
    """A demo backcheck mismatch and the error source guidance attributes it to."""

    # The survey record; the backcheck record has its own KEY
    record: DemoRecord
    column: DemoBackcheckColumn
    survey_value: float
    backcheck_value: float
    source: ErrorSource


# Enumerator attributions need no note
DEMO_ATTRIBUTION_NO_NOTE = DemoMismatch(
    DemoRecord("AN043-029", "uuid:6lh1ml39-090a-285w-09t0-l42895pr073w"),
    DemoBackcheckColumn.AGE,
    30,
    40,
    ErrorSource.ENUMERATOR,
)
# Respondent attributions need a note
DEMO_ATTRIBUTION_WITH_NOTE = DemoMismatch(
    DemoRecord("UP053-004", "uuid:8um8wz44-940o-168k-35l3-z62845ol734i"),
    DemoBackcheckColumn.HOUSEHOLD_COUNT,
    9,
    10,
    ErrorSource.RESPONDENT,
)


def demo_accept_steps(review_label: str, dialog_title: str, reason: str) -> str:
    """Return guidance steps 2 and 3: accept a flag in a Review dialog.

    Step 1, finding the row, is the caller's. The Outliers and GPS checks
    share the dialog's **Select Action**, **Reason for Correction** and
    **Apply** inputs, so their guidance shares these steps.
    """
    return (
        f"2. Click **{review_label}** on that row. The **{dialog_title}** "
        "dialog opens.\n"
        "3. Set **Select Action** to **accept**, enter a **Reason for "
        f"Correction** (e.g., *{reason}*) and click **Apply**.\n\n"
    )


# How the Outliers and GPS guidance shows a reviewed flag again
DEMO_SHOW_REVIEWED = (
    "Turn on **Show reviewed** to list it again, highlighted green with your reason"
)


class DemoSharedValue(NamedTuple):
    """A value several demo survey records share in one column."""

    column: DemoColumn
    value: float
    hhids: tuple[str, ...]


# Other Duplicates on the two GPS columns finds only this repeated longitude;
# the latitudes differ, so the households are not at the same place
DEMO_SHARED_LONGITUDE = DemoSharedValue(
    DemoColumn.HOUSEHOLD_LONGITUDE, 77.074387, ("AN043-038", "AN043-006")
)


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

    PROCEED_TO_HFCS_INFO: ClassVar[str] = """
        Your configuration is set up and your data is ready for quality analysis.

        Click **View Quality Reports** to explore the results — DataSure has run all
        configured checks and the reports are ready to review.
    """

    SURVEYCTO_INFO: ClassVar[str] = """
        The sections below connect DataSure to real data sources. Your demo data is
        already imported, so you need no SurveyCTO server or credentials here. Read
        how a live project would import a SurveyCTO form, then scroll down to
        **Preview Imported Data**.

        1. Under **Manage Credentials**, **Add Credentials** asks for your
           **Server name**, **Email address** and **Password**.
           **Connect & Save Credentials** signs in and stores the password in your
           computer's secure keyring, never in the project.
        2. Under **Import Data From Sources**, **Add Import Configuration** with
           **Import Type** set to **SurveyCTO** asks you to
           **Select Server Credentials**, **Select Form ID** and enter an
           **Alias**, then **Add Form** adds the form to the import log.

        You can open these forms to look around, but do not click
        **Connect & Save Credentials** or **Add Form** in the demo.
    """

    @classmethod
    def get_info_message(cls, message_id: str) -> str:
        """Retrieve demo messages based on type."""
        demo_messages = {
            "add_to_session_info": cls.ADD_TO_SESSION_INFO,
            "preview_data_info": cls.PREVIEW_DATA_INFO,
            "proceed_to_config_info": cls.PROCEED_TO_CONFIG_INFO,
            "proceed_to_hfcs_info": cls.PROCEED_TO_HFCS_INFO,
            "surveycto_info": cls.SURVEYCTO_INFO,
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
        "guidance_title": "Data Preparation",
        "guidance_content": f"""
        One preparation step is required before you can continue: convert the
        **{DemoColumn.SUBMISSIONDATE}** column from text to a datetime format in **both** datasets.
        Every other preparation step is optional.

        **:material/arrow_forward: To do this for each dataset (demo_survey and demo_backcheck):**
        1. Click **:material/add: Add data prep step**
        2. Under **Select Action**, choose **transform column(s)**
        3. Under **Select column to transform**, choose **{DemoColumn.SUBMISSIONDATE}**
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
        "guidance_content": f"""
        One configuration covers both datasets. Click **:material/add: Add New Check Configuration**
        and fill in the form with these values:

        **Page Name:** {DEMO_PAGE_NAME}

        **Survey dataset:** demo_survey
        - Key Column: {DemoColumn.KEY} | ID Column: {DemoColumn.HHID} | Enumerator Column: {DemoColumn.ENUM_NAME}
        - Team Column: {DemoColumn.TEAM_ID} | Duration Column: {DemoColumn.DURATION} | Date Column: {DemoColumn.SUBMISSIONDATE}
        - Form Version Column: leave empty, the demo data has none
        - Target Number of responses: {DEMO_SURVEY_TARGET} (optional)

        **Backcheck dataset:** demo_backcheck
        - Backcheck Date: {DemoBackcheckColumn.SUBMISSIONDATE} | Backchecker: {DemoBackcheckColumn.BCER_NAME}
        - Backchecker Team: {DemoBackcheckColumn.TEAM_ID} | Target Percentage: 10

        Click **Add Check Configuration** — DataSure creates a quality analysis page automatically.
        Once created, the **View Quality Reports** button will appear at the bottom of this page.

        ##### Try editing and removing a configuration (optional):
        - **Edit:** click **:material/edit: Edit Check Configuration**, choose
          **{DEMO_PAGE_NAME}** under **Select Check Configuration to Edit**, change
          **Enter Target Number of responses for the Survey (Optional)** to
          **{DEMO_EDITED_TARGET}**, and click **Save Changes**. Change only the target:
          renaming the page would leave its saved check settings behind.
        - **Remove:** add a second configuration named **{DEMO_THROWAWAY_PAGE}** with the
          same survey dataset and columns. Then open **Remove Check Configuration**,
          choose **{DEMO_THROWAWAY_PAGE}** under **Select Check Configuration to Remove**,
          and click **Remove Check Configuration**. Do not remove **{DEMO_PAGE_NAME}**:
          the rest of the demo uses it.
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
        The page opens on **Summary**. Pick a group in the top row, then a check
        in the row below it; only the selected check runs. Checks that are not set
        up or do not apply to your data are muted with a marker, and opening one
        explains why. Start by expanding the :material/settings: **settings panel**
        at the top of each check and configuring it for your data. Then work
        through the sections below — demo guidance is available within each
        section to explain what you are seeing and what to do next.

        **Checks to explore:**
        - **Overview:** Summary, Progress
        - **Data integrity:** Missing Values, Duplicates, Outliers & Constraints,
          GPS Checks
        - **Field team:** Enumerator Stats, Backchecks
        - **Exploration:** Descriptive Stats

        **Before you correct or accept anything:** open **:material/person: Reviewer:**
        in the sidebar, below the page list and just above **Demo Help**, and type
        your name under **Reviewer name**.
        DataSure records it as the user on every correction and acceptance, for
        example in the Correction Log. Left blank, your computer login is used.
        The name is saved for the whole app, so it stays set after the demo.
        """,
    }

    REPLICATION: ClassVar[dict] = {
        "step": 7,
        "title": "Replication Package",
        "description": "Export a Stata replication package for your corrected dataset.",
        "icon": ":material/folder_zip:",
        "page": "replication_view.py",
        "guidance_title": "Export Replication Package",
        "guidance_content": f"""
        This page bundles everything needed to reproduce your corrected dataset into a
        single downloadable zip file — raw data, Stata do-files (import, prepare,
        correct), correction and prep logs, codebooks, and a README.

        ##### First, export the project setup:
        A replication package shares the data; a configuration file shares the
        setup, so a colleague can start the same project. Export it before you build
        the package: ticking the PII confirmation at the end completes the demo.
        1. Open **Start Here** in the sidebar. On the **{DEMO_PROJECT_NAME}** row,
           click **Export**.
        2. Keep **Include record-level decisions (corrections and backcheck
           attribution)** ticked to include your corrections, or untick it to share
           only the setup.
        3. Click **Download configuration** to save the `.json` file.
        4. Click **Export Replication Package** in the sidebar to come back here.

        For your own projects, the **More** menu on each Start Here row also has
        **Update from configuration**, which applies a configuration file to an
        existing project, and **Delete project**, which permanently deletes the
        project and its data. The demo row has neither: use **Restart** to reset it.

        ##### Then build the replication package:
        1. Under **Page Name**, select **{DEMO_PAGE_NAME}**.
        2. Just below it, tick **Exclude reviewer names**. The `correction_log.csv`
           in the zip then leaves the user column blank, so the package does not
           show who made each correction. The project's own Correction Log keeps
           the names.
        3. Review the configuration in **Selected page details**, then expand
           **What's inside the zip?** at the bottom of the page to see the full
           directory structure.
        4. Click **Build Replication Package**. DataSure will assemble the zip in seconds.
        5. Once the build completes, check the PII confirmation box and click
           **Download replication package (.zip)**. The completion message then appears:
           **Restart Demo** starts again, and **Create Real Project** leaves the demo.

        The demo dataset is synthetic and contains no real PII. In a live project the
        zip would include raw respondent data and must be stored on an encrypted,
        access-controlled drive in accordance with IPA data policy.
        """,
    }

    CORRECT: ClassVar[dict] = {
        "step": 6,
        "title": "Correct Data",
        "description": "Make corrections to your data based on quality findings.",
        "icon": ":material/edit:",
        "page": "correction_view.py",
        "guidance_title": "Correct Data Issues",
        "guidance_content": f"""
        This page lets you apply targeted corrections to your data based on issues
        found in the quality reports. Corrections are logged and can be undone at
        any time.

        **Page structure:** The buttons at the top list one check page per check
        configuration (e.g., "Household HFCs"); the page opens on the check page you
        last reviewed. For the selected check page you will find:
        - :material/add: **Add correction step** — apply a new correction.
        - :material/delete: **Remove correction step** — undo a previous correction.
        - **Correction Log** — every correction made so far, including those saved
          from the Duplicates cards, plus flags accepted on the check pages without
          changing the data, with their reasons. Filter it by source or action.
        - **Preview Corrected Data** — the dataset after all corrections, with
          row, column and missingness metrics.

        The three correction actions are **modify value** (replace a value),
        **remove value** (replace a value with missing) and **remove row** (delete
        the whole row).

        ##### Instructions for Demo:
        1. In the **Correction Log**, find the three duplicate ID corrections you
           saved on the **Duplicates** check.
        2. Fix a typing slip found by the Outliers check: the household with key
           **{DEMO_LAND_CORRECTION.record.key}** has **{DEMO_LAND_CORRECTION.value}** acres in
           **{DEMO_LAND_CORRECTION.column}**; the enumerator confirmed an extra 7 was typed
           and the household owns **{DEMO_LAND_CORRECTION.new_value}** acres.
           - Click **:material/add: Add correction step**.
           - Under **Select KEY**, choose **{DEMO_LAND_CORRECTION.record.key}**.
           - Under **Select Action**, choose **modify value**.
           - Under **Select Column to Modify**, choose **{DEMO_LAND_CORRECTION.column}**.
             The current value (**{DEMO_LAND_CORRECTION.value}**) loads automatically.
           - Under **New Value**, enter **{DEMO_LAND_CORRECTION.new_value}**.
           - Under **Reason for Correction**, enter *Typing slip confirmed by enumerator*.
           - Click **Apply**.
        3. Check the new entry in the **Correction Log**, then return to
           **Outliers & Constraints** in the quality reports: the value is no longer
           flagged, and the Check health row on Summary counts it as resolved.

        **Next:** Use the navigation button below or click **Replication Package** in the sidebar to proceed to the final step — exporting a Stata replication package of your corrected dataset.
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
            "replication": cls.REPLICATION,
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
            cls.REPLICATION,
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
            7: cls.REPLICATION,
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
        "summary_settings": {
            "title": "Summary Settings",
            "content": f"""
        ##### Setup for Summary
        In this section, you can configure global settings for the Summary check, you will notice that some settings are pre-filled based on your check configuration.
        This check contains the following settings:
        - Survey Date: The date when the survey was conducted or submitted (e.g., {DemoColumn.SUBMISSIONDATE}).
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
        - Total Columns: Total number of columns in your dataset.

        **Next**: Explore the Submission Details section below.
        """,
        },
        "summary_submissions": {
            "title": "Submission Details",
            "content": """
        ##### Submission Details
        This section provides insights into the submission patterns of your survey data, including:
        - First Submission and Last Submission: The dates of the earliest and latest submissions.
        - Today: Number of submissions received today. The change compares with yesterday.
        - This week: Number of submissions dated on or after the same day last week.
          The change compares with the week before.
        - This month: Number of submissions dated on or after the same day last month.
          The change compares with the month before.
        - Total: Total number of submissions received to date.

        The demo data is dated so that the latest submissions fall on yesterday and today.

        This section also includes a submission trend chart that visualizes the number of submissions over time, helping you identify patterns and peaks in data collection.

        **Next**: Explore the Progress section below.
        """,
        },
        "summary_progress": {
            "title": "Progress",
            "content": f"""
        ##### Progress
        This section provides an overview of the progress of your survey data collection, including:
        - Submission Progress: A progress bar showing the percentage of completed submissions against the total expected interviews.
        - Average Submissions per Day: The average number of submissions per calendar day across the full survey period.
        - Average Submissions Per Week: The average number of submissions per calendar week (Monday to Sunday) across the full survey period.
        - Average Submissions Per Month: The average number of submissions per calendar month across the full survey period.

        **Next**: Explore the progress by subsections below.

        ##### Instructions for Demo:
        For the demo, you will explore how to create a table showing progress by subgroups such as enumerator or region.
        - At "Progress by" dropdown, select "{DemoColumn.STATE}" to see submission progress by state.

        **Optionally**,
        - you can also explore by selecting other categorical columns.
        - on the right side of the table, you can switch between, "Auto", "Daily", "Weekly", and "Monthly" views to see how submission progress varies over different time intervals.
        The "Auto" view automatically adjusts the time interval based on the data density while the other options allow you to manually select the desired time frame for analysis.
        """,
        },
        "summary_check_health": {
            "title": "Check health",
            "content": """
        ##### Check health
        This section shows one row for every other check, grouped like the check navigation
        (Overview, Data integrity, Field team, Exploration). Each number comes from its check
        and uses that check's settings, so it matches what you see when you open the check.
        Each row shows:
        - **Status**: a coloured pill (see below).
        - **Outstanding**: the issues still to deal with, such as duplicate IDs not yet
          resolved, with a detail line under the number.
        - **Change**: how Outstanding changed since the start of the comparison period,
          for example "▲ 2 new submissions since yesterday".
        - **Resolved**: the issues already resolved through corrections, acceptances or
          error-source attributions, with "+N since …" for those resolved in the period,
          or "—" for checks that resolve nothing.
        - **Open →** or **Set up →**: go to the check.

        The statuses are:
        - **Flagged** (amber): the check has outstanding issues to review.
        - **No issues** (green): the check has nothing outstanding, or only describes the data, like Progress.
        - **Ready** (blue): the check is ready, but Summary does not count its issues yet,
          for example GPS Checks before outliers can be detected. Open it to see them.
        - **Not set up** (grey): the check needs settings first. Click **Set up →** to configure it.
        - **Not applicable** (grey): the check has nothing to work with on this page.
        - **Error** (red): the check or its numbers could not be computed; the row says why.

        Under **Compare with**, the **Comparison period** box above the rows sets what
        **Change** compares with: **Day** (the default, the end of yesterday), **7 days**, **Week** (the start of this
        week; choose **Week starts on**), **30 days**, or **Month** (the start of this month).
        The choice applies to every check page in the project.

        ##### Instructions for Demo:
        - The demo's latest submissions fall on yesterday and today, so with **Day**
          selected the **Progress** row shows today's new submissions under **Change**.
        - Open the **Comparison period** box and switch to **7 days** to see the changes grow.
        - Rows for checks you have not set up yet, such as Outliers & Constraints, show their
          numbers once you set them up. After you resolve the duplicate IDs on the
          **Duplicates** check, return here to see them move from **Outstanding** to **Resolved**.
        """,
        },
    }

    PROGRESS: ClassVar[dict] = {
        "progress_report": {
            "title": "Progress Report",
            "content": """
        ### Survey Progress Report
        This check provides detailed insights into the progress of your survey data collection.
        It includes metrics such as submission counts over time, progress by enumerator or selected categories, and overall submission trends.
        **Next**: Go to the :material/settings: settings icon to configure global settings for the Progress check.
        """,
        },
        "progress_report_settings": {
            "title": "Progress Settings",
            "content": f"""
        ##### Setup for Progress
        In this section, you can configure global settings for the Progress check, you will notice that some settings are pre-filled based on your check configuration.
        This check contains the following settings:
        - Survey ID: The main identifier for your survey respondents (e.g., {DemoColumn.HHID}).
        - Survey Date: The column indicating the date when the survey was conducted or submitted (e.g., {DemoColumn.SUBMISSIONDATE}).
        - Enumerator ID: The column indicating who collected the data (e.g., {DemoColumn.ENUM_NAME}).
        - Total Expected Interviews: The total number of survey interviews you expect to collect (e.g., 200).
        - Target Submissions Per Period: The number of submissions you aim to collect in each period shown on the Progress Over Time chart. This sets its threshold line.

        ##### Instructions for Demo:
        - Set **Total Expected Interviews** to **200**.
        - Set **Target Submissions Per Period** to **3**. The demo team averages a little over
          2 submissions a day, so some days meet this daily target and others fall short.

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
        - With the **Daily** pill selected, notice that some bars are green and some are red:
          red days fell short of the target of 3 submissions.
        - Switch to **Weekly** and **Monthly** using the pills above the chart. The same target
          applies to every period, so the weekly and monthly bars all meet it; a target is
          most useful for the period you track.
        - Set **Target Submissions Per Period** back to **0** in settings to compare each
          period with the average instead.

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
        """,
        },
        "display_progress_chart": {
            "title": "Consent and Completion Progress",
            "content": f"""
        ##### Consent and Completion Progress
        This section helps you monitor the consent and completion rates of your survey data collection, including:
        - Consent Rate: Percentage of respondents who provided consent.
        - Completion Rate: Percentage of respondents who completed the survey.

        ##### Instructions for Demo:
        For the demo, you will setup the consent and completion criteria as follows:
        - Consent Criteria: Select the "{DemoColumn.CONSENT}" column and set the value to "yes".
        - Completion Criteria: Select the "{DemoColumn.COMPLETION_STATUS}" column and set the value to "complete".
        **Next**: Explore the other checks for more data quality insights.
        """,
        },
    }

    DUPLICATES: ClassVar[dict] = {
        "duplicates_report_settings": {
            "title": "Duplicates Settings",
            "content": f"""
        ##### Duplicates Settings
        These settings control which columns identify a unique survey record and how
        duplicate detection is performed.

        - **Survey Key**: The unique row identifier for each submission (e.g., {DemoColumn.KEY}).
          Different from Survey ID — every submission has a unique key even if two share
          the same respondent ID.
        - **Survey ID**: The respondent or household identifier checked for duplicates
          (e.g., {DemoColumn.HHID}).
        - **Survey Date**: The submission or interview date column (e.g., {DemoColumn.SUBMISSIONDATE}).
        - **Enumerator ID**: The column identifying who collected the data (e.g., {DemoColumn.ENUM_NAME}).
        - **Duplicates Conditions**: Optional filter to restrict the check to a subset of
          records. Use the toggle to treat missing values as duplicates.

        ##### Instructions for Demo:
        Your settings are pre-filled from the check configuration you set up earlier.
        Confirm the following values are selected, then close the panel and explore the
        sections below:
        - Survey Key: **{DemoColumn.KEY}**
        - Survey ID: **{DemoColumn.HHID}**
        - Survey Date: **{DemoColumn.SUBMISSIONDATE}**
        - Enumerator ID: **{DemoColumn.ENUM_NAME}**
        """,
        },
    }
    MISSING: ClassVar[dict] = {
        "missing_summary": {
            "title": "Missing Values",
            "content": """
        This check helps you understand the extent and patterns of missing data in your survey dataset.

        **Start here**: At the top of this check, configure your **missing value codes** (the
        :material/add: **Add** / :material/edit: **Modify** / :material/delete: **Delete** buttons).
        These codes tell DataSure which numeric values in your data represent survey-specific
        non-responses (e.g., -99 = Don't Know).

        The check then provides six sections:
        - **Missing data**: Four summary metrics.
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
            - Column: Name of the column.
            - Total Missing: Total number of missing values in the column.
            - % Total Missing: Percentage of missing values in the column.
            - Null Values: Count of null or NaN values in the column.
            - % Null Values: Percentage of null or NaN values in the column.
            - One count and one percentage column for each missing code you added, named
              after its label (e.g., "Don't Know" and "% Don't Know").
        - The table can be sorted by any of the columns to help identify which columns have the highest or lowest missing data.
        - The table also includes a "Filter by % missing:" slider at the top right to allow you to filter the report based on a minimum percentage of missing data.

        ##### Instructions for Demo:
        For the demo, use the "Filter by % missing:" slider to filter the report to only show columns with 100% missing values.
        **Next**: Explore the **Compare missing data within groups** section below.
        """,
        },
        "missing_compare": {
            "title": "Compare Missing Data Within Groups",
            "content": f"""
        ##### Compare Missing Data Within Groups
        This section allows you to compare missing data patterns within different groups in your dataset, including:
        - A dropdown to select a categorical column (e.g., enumerator, region, etc.) to group the data by.
        - A dropdown to select columns to compare. By default, all columns will be used but an aggregate view will be shown.
        - A table showing the percentage of missing values for each selected column within each group.

        ##### Instructions for Demo:
        For the demo:
         - **first** - at the **Group by column** dropdown, choose "{DemoColumn.STATE}" to see how missing data varies across different states in the dataset.
         - **then** - at the **Compare columns** dropdown, choose "{DemoColumn.LAND_ACRE}", "{DemoColumn.CHILD_LOAN}" and "{DemoColumn.PVT_SCH}" to see how missing data varies for these specific columns across different states.
        **Next**: Explore the **Missingness over time** section below.
        """,
        },
        "missing_over_time": {
            "title": "Missingness Over Time",
            "content": f"""
        ##### Missingness Over Time
        This section visualizes missing data patterns over time, helping you identify trends and changes in data quality during the survey period, including:
        - An area chart showing the percentage of missing values over time.
        - A dropdown to select a specific date column to use for analysis.
        ##### Instructions for Demo:
        For the demo, at the **Select date column** dropdown, choose "{DemoColumn.SUBMISSIONDATE}" to see how missing data varies over the survey period.
        **Next**: Explore the **Nullity Correlation** section below.
        """,
        },
        "missing_correlation": {
            "title": "Nullity Correlation",
            "content": f"""
        ##### Nullity Correlation
        This section provides insights into the correlation of missing data between different columns in your dataset, helping you identify patterns and relationships in missingness, including:
        - A heatmap visualizing the correlation of missing values between columns.
        - Use the **All columns** toggle to include every column at once, or turn it off to
          manually select specific columns from the dropdown.

        ##### Instructions for Demo:
        For the demo:
        - Turn off the **All columns** toggle, then at the **Select columns for correlation** dropdown, choose "{DemoColumn.MIN_DIST}" and "{DemoColumn.TRAVEL_SCH}".
        - You will notice that whenever "{DemoColumn.MIN_DIST}" is missing, "{DemoColumn.TRAVEL_SCH}" is also missing. This makes sense: if the distance to school is not recorded, the mode of travel is also likely missing.

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
        """,
        },
    }
    OUTLIERS: ClassVar[dict] = {
        "outliers_report_settings": {
            "title": "Outliers & Constraints Settings",
            "content": f"""
        ##### Outliers & Constraints Settings
        These settings identify the key columns DataSure uses to contextualise flagged
        records in the report tables.

        - **Survey Key**: Unique row identifier for each submission (e.g., {DemoColumn.KEY}).
        - **Survey ID**: Respondent or household identifier (e.g., {DemoColumn.HHID}).
        - **Survey Date**: Submission or interview date column (e.g., {DemoColumn.SUBMISSIONDATE}).
        - **Enumerator ID**: Column identifying the data collector (e.g., {DemoColumn.ENUM_NAME}).
        - **Team ID**: Column identifying the team (e.g., {DemoColumn.TEAM_ID}).

        ##### Instructions for Demo:
        Your settings are pre-filled from the check configuration. Confirm the following
        are selected, then close the panel and proceed to configure outlier columns below:
        - Survey Key: **{DemoColumn.KEY}**
        - Survey ID: **{DemoColumn.HHID}**
        - Survey Date: **{DemoColumn.SUBMISSIONDATE}**
        - Enumerator ID: **{DemoColumn.ENUM_NAME}**
        - Team ID: **{DemoColumn.TEAM_ID}**
        """,
        },
    }
    ENUMERATORS: ClassVar[dict] = {
        "enumerator_report_settings": {
            "title": "Enumerator Statistics Settings",
            "content": f"""
        ##### Enumerator Statistics Settings
        These settings identify the key columns DataSure uses to track enumerator
        performance across the report.

        - **Survey Key**: Unique row identifier for each submission (e.g., {DemoColumn.KEY}).
        - **Survey ID**: Respondent or household identifier (e.g., {DemoColumn.HHID}).
        - **Survey Date**: Submission or interview date column (e.g., {DemoColumn.SUBMISSIONDATE}).
        - **Enumerator ID**: Column identifying the data collector (e.g., {DemoColumn.ENUM_NAME}).
        - **Team**: Column identifying the team (e.g., {DemoColumn.TEAM_ID}).
        - **Duration Column**: Column recording how long each interview took (e.g., {DemoColumn.DURATION}).
        - **Duration Unit**: Unit of the duration column — seconds, minutes, or hours.
        - **Form Version Column**: Column recording the form version used, if your form has one.
        - **Consent and Outcome Settings**: Configure which column and value indicate consent
          and which indicate a completed survey. The report uses them as soon as you change them.

        ##### Instructions for Demo:
        Your Survey Key, Survey ID, Survey Date, Enumerator ID, Team, and Duration Column
        are pre-filled from earlier configuration. Confirm them and complete the remaining fields:
        - Duration Column: **{DemoColumn.DURATION}**
        - Duration Unit: **seconds**
        - Team: **{DemoColumn.TEAM_ID}**
        - Form Version Column: leave empty, the demo data has no form version column
        - Consent Column: **{DemoColumn.CONSENT}** | Valid Consent Values: **yes**
        - Outcome Column: **{DemoColumn.COMPLETION_STATUS}** | Completed Survey Values: **complete**

        Then close the panel and explore the sections below.
        """,
        },
    }

    DESCRIPTIVE_STATS: ClassVar[dict] = {
        "descriptive_report": {
            "title": "Descriptive Statistics",
            "content": f"""
        This check lets you explore the distribution and characteristics of any column
        in your dataset. Use the **column selector** below to choose which columns to
        analyse, then explore three sections:

        - **Summary Stats**: Count, mean, median, standard deviation, min/max, quartiles,
          skewness, and kurtosis for each selected numeric column.
        - **Histogram**: Distribution chart for a selected numeric column, with mean and
          median lines marked. Use the **Bins** slider to adjust the resolution.
        - **Value Counts**: Frequency table showing how often each value appears.
          Switch between table and chart view, and toggle between count and percentage.

        ##### Instructions for Demo:
        1. In the **column selector**, check **{DemoColumn.AGE}** and **{DemoColumn.HOUSEHOLD_COUNT}** — or use the
           **Select by Type** pill and choose **Numeric** to select all numeric columns at once.
        2. Click **Apply Selection** to load the analysis.
        3. In **Summary Stats**, compare the mean and median for each column to spot skewed distributions.
        4. In **Histogram**, select **{DemoColumn.AGE}** and try adjusting the **Bins** slider.
        5. In **Value Counts**, switch the column to **{DemoColumn.STATE}** or **{DemoColumn.ENUM_NAME}** to see how
           responses are distributed across categories. Note that categorical columns like
           **{DemoColumn.STATE}** are only available here if you included them in your column selection —
           if you selected numeric columns only, go back to the column selector and add
           **{DemoColumn.STATE}** or **{DemoColumn.ENUM_NAME}**.
        """,
        },
    }
    BACKCHECKS: ClassVar[dict] = {
        "backchecks_report_settings": {
            "title": "Backcheck Analysis Settings",
            "content": f"""
        ##### Backcheck Analysis Settings
        These settings link your survey dataset to your backcheck dataset so DataSure
        can match records and compare values.

        - **Survey Key (required)**: Unique row identifier in the survey dataset (e.g., {DemoColumn.KEY}).
        - **Survey ID (required)**: Respondent or household identifier (e.g., {DemoColumn.HHID}).
        - **Survey Date**: Date column in the survey dataset (e.g., {DemoColumn.SUBMISSIONDATE}).
        - **Backcheck Date**: Date column in the backcheck dataset (e.g., {DemoBackcheckColumn.SUBMISSIONDATE}).
        - **Enumerator**: Column identifying the original data collector (e.g., {DemoColumn.ENUM_NAME}).
        - **Back Checker**: Column in the backcheck dataset identifying who conducted
          the back check (e.g., {DemoBackcheckColumn.BCER_NAME}).
        - **Backcheck target (%)**: Percentage of surveys to backcheck. Defaults to
          the page configuration target, or 10% if neither is set.
        - **Eligibility column** and **Eligible values**: Optional column and values that
          mark a survey eligible for backchecks (e.g., {DemoColumn.CONSENT} = yes).
        - **Additional Options**: No differences values, exclude values, and string
          comparison settings (case, trim spaces, ignore symbols). Records with a duplicated
          survey ID are left out of the comparison until the duplicate is resolved in the
          Duplicates check.

        ##### Instructions for Demo:
        Your Survey Key, Survey ID, Survey Date, Backcheck Date, Enumerator, and Back Checker
        are pre-filled from earlier configuration. Confirm they are set, then close the
        panel and proceed to the **Backchecks Columns Configuration** section below.
        """,
        },
    }

    GPSCHECKS: ClassVar[dict] = {
        "gpschecks_report_settings": {
            "title": "GPS Checks Settings",
            "content": f"""
        ##### GPS Checks Settings
        These settings identify the key columns DataSure uses to label records on maps
        and in report tables.

        - **Survey Key**: Unique row identifier for each submission (e.g., {DemoColumn.KEY}).
        - **Survey ID**: Respondent or household identifier (e.g., {DemoColumn.HHID}).
        - **Survey Date**: Submission or interview date column (e.g., {DemoColumn.SUBMISSIONDATE}).
        - **Enumerator ID**: Column identifying the data collector (e.g., {DemoColumn.ENUM_NAME}).
        - **Team**: Column identifying the team (e.g., {DemoColumn.TEAM_ID}).
        - **Mapbox API Token**: Required to render map visualizations. Enter your token
          in the **Mapbox API Token Configuration** section and click **Save Mapbox Token**.

        ##### Instructions for Demo:
        Your settings are pre-filled from the check configuration. Confirm the following
        are selected, then close the panel:
        - Survey Key: **{DemoColumn.KEY}**
        - Survey ID: **{DemoColumn.HHID}**
        - Survey Date: **{DemoColumn.SUBMISSIONDATE}**
        - Enumerator ID: **{DemoColumn.ENUM_NAME}**
        - Team: **{DemoColumn.TEAM_ID}**

        If you have a Mapbox API token, enter it under **Mapbox API Token Configuration**
        and click **Save Mapbox Token** to enable all map visualizations.
        """,
        },
    }

    @classmethod
    def get_onboarding_message(cls, tab: str, message_id: str) -> dict[str, str] | None:
        """Return the onboarding message for a tab's function, or None if absent."""
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
        return messages.get(tab, {}).get(message_id)


# (module, tab, function name) for every function decorated with
# demo_output_onboarding, so tests can check each one has a message.
DEMO_OUTPUT_FUNCTIONS: set[tuple[str, str, str]] = set()

# (tab, function name) pairs already warned about, so a missing message is
# logged once rather than on every Streamlit rerun.
_WARNED_MISSING_MESSAGES: set[tuple[str, str]] = set()


def demo_output_onboarding(tab: str):
    """Decorator to display onboarding messages for demo functions.

    Each decorated function is recorded in DEMO_OUTPUT_FUNCTIONS.
    """

    def decorator(func):
        DEMO_OUTPUT_FUNCTIONS.add((func.__module__, tab, func.__name__))

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if is_demo_project():
                message = OutputOnboardingInfo.get_onboarding_message(
                    tab, func.__name__
                )
                if message is None:
                    if (tab, func.__name__) not in _WARNED_MISSING_MESSAGES:
                        _WARNED_MISSING_MESSAGES.add((tab, func.__name__))
                        logger.warning(
                            "No demo guidance for %s on the %s check",
                            func.__name__,
                            tab,
                        )
                else:
                    demo_expander(message.get("title"), message.get("content"))
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
    """Show the next onboarding step.

    Nothing is shown after the last step: the demo's completion message is
    ``navigations_utils.show_demo_completion_message``.
    """
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


def unregister_demo_project() -> None:
    """Remove the demo project from ``projects.json``, leaving its folder."""
    projects_file = get_cache_path("projects.json")
    if not projects_file.exists():
        return
    with open(projects_file) as f:
        projects = json.load(f)
    if projects.pop(DEMO_PROJECT_ID, None) is None:
        return
    with open(projects_file, "w") as f:
        json.dump(projects, f, indent=4)


class InterviewTimes(NamedTuple):
    """When one demo interview started, ended and was submitted.

    Field names are the demo data's date columns.
    """

    starttime: datetime
    endtime: datetime
    submissiondate: datetime


class DemoDataGenerator:
    """Add seeded date, consent and completion fields to the demo data.

    Every load draws the same values from ``seed``, so the demo data is
    identical between loads apart from one whole-day offset: dates are laid
    out so the latest survey submission falls on ``today``. Backcheck rows
    are dated after the latest survey submission with the same ``hhid``.
    """

    DATE_COLUMNS: ClassVar[tuple[str, ...]] = InterviewTimes._fields
    DATE_FORMAT: ClassVar[str] = "%Y-%m-%d %H:%M:%S"
    SURVEY_ID: ClassVar[str] = "hhid"
    SPAN_DAYS: ClassVar[int] = 60

    def __init__(
        self,
        df: pl.DataFrame,
        today: date | None = None,
        seed: int = DEMO_SEED,
    ):
        self.df = df
        self.today = today or date.today()
        self.rng = random.Random(seed)

    def _interview_times(self, start: datetime) -> InterviewTimes:
        """Return start, end and submission times for an interview at ``start``."""
        end = start + timedelta(minutes=self.rng.randint(15, 136))
        submitted = end + timedelta(minutes=self.rng.randint(1, 30))
        return InterviewTimes(start, end, submitted)

    def _time_of_day(self) -> time:
        return time(self.rng.randint(7, 16), self.rng.randint(0, 59))

    def _survey_dates(self) -> list[InterviewTimes]:
        """Spread interviews over the last ``SPAN_DAYS`` days, latest today."""
        draws = [
            (self.rng.randint(0, self.SPAN_DAYS - 1), self._time_of_day())
            for _ in range(self.df.height)
        ]
        latest = min((days_ago for days_ago, _ in draws), default=0)
        return [
            self._interview_times(
                datetime.combine(self.today - timedelta(days=days_ago - latest), at)
            )
            for days_ago, at in draws
        ]

    def _backcheck_dates(self, survey_df: pl.DataFrame) -> list[InterviewTimes]:
        """Date each backcheck 1-5 days after its survey, never after today."""
        surveyed = dict(
            survey_df.select(
                self.SURVEY_ID,
                pl.col("submissiondate").str.to_datetime(self.DATE_FORMAT),
            )
            .group_by(self.SURVEY_ID)
            .agg(pl.col("submissiondate").max())
            .iter_rows()
        )
        fallback = iter(self._survey_dates())
        dates = []
        for survey_id in self.df[self.SURVEY_ID]:
            lag_days = self.rng.randint(1, 5)
            at = self._time_of_day()
            survey_submitted = surveyed.get(survey_id)
            if survey_submitted is None:
                dates.append(next(fallback))
                continue
            day = min(survey_submitted.date() + timedelta(days=lag_days), self.today)
            start = datetime.combine(day, at)
            if start <= survey_submitted:
                start = survey_submitted + timedelta(hours=1)
            dates.append(self._interview_times(start))
        return dates

    def _set_dates(self, dates: list[InterviewTimes]) -> None:
        self.df = self.df.with_columns(
            pl.Series(
                name, [getattr(row, name).strftime(self.DATE_FORMAT) for row in dates]
            )
            for name in self.DATE_COLUMNS
        )

    def _set_choice(self, name: str, values: list[str], weights: list[float]):
        self.df = self.df.with_columns(
            pl.Series(
                name,
                [self.rng.choices(values, weights)[0] for _ in range(self.df.height)],
            )
        )

    def add_demo_fields(
        self, datatype: str = "survey", survey_df: pl.DataFrame | None = None
    ) -> pl.DataFrame:
        """Add the date fields, plus consent and completion for survey data.

        Parameters
        ----------
        datatype : str
            ``"survey"`` or ``"backcheck"``.
        survey_df : pl.DataFrame | None
            For backcheck data, the survey data returned by
            ``add_demo_fields("survey")``. Backchecks are then dated after
            their survey; without it they are dated like surveys.
        """
        if (
            datatype == "backcheck"
            and survey_df is not None
            and self.SURVEY_ID in self.df.columns
        ):
            self._set_dates(self._backcheck_dates(survey_df))
        else:
            self._set_dates(self._survey_dates())
        if datatype == "survey":
            self._set_choice("consent", ["yes", "no"], [0.98, 0.02])
            self._set_choice(
                "completion_status", ["complete", "incomplete"], [0.95, 0.05]
            )
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


def load_demo_data(today: date | None = None) -> bool:
    """Load demo data files into the demo project.

    Parameters
    ----------
    today : date | None
        The day the latest demo survey submission falls on. Defaults to the
        current date; every other value in the data is the same on every load.
    """
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

    survey_df = DemoDataGenerator(survey_df, today=today).add_demo_fields()

    # Save to raw database (for import system)
    duckdb_save_table(DEMO_PROJECT_ID, survey_df, "demo_survey", "raw")

    # clean prep/corrected entries
    duckdb_remove_table(DEMO_PROJECT_ID, "demo_survey", "prep")
    duckdb_remove_table(DEMO_PROJECT_ID, "demo_survey", "corrected")

    backcheck_df = DemoDataGenerator(backcheck_df, today=today).add_demo_fields(
        "backcheck", survey_df=survey_df
    )

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


def demo_expander(title: str, content: str, expanded: bool = True):
    """Create a demo-specific expander with helpful information."""
    if not is_demo_project():
        return

    with st.expander(f"**Learn More: {title}**", expanded=expanded):
        demo_container(content)
