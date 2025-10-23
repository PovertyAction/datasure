import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import ClassVar

import polars as pl
import streamlit as st

from datasure.utils.cache_utils import get_cache_path
from datasure.utils.duckdb_utils import duckdb_remove_table, duckdb_save_table

DEMO_PROJECT_NAME = "DataSure Demo"
DEMO_PROJECT_ID = "demoproject"


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

    PREPARE_DATA_INFO: ClassVar[str] ="""
        What is Data Preparation?

        ##### Data preparation is a crucial step that:
        - Cleans and standardizes your survey data for data quality analysis
        - Handles missing values and inconsistencies
        - Creates new variables for analysis
        - Removes problematic rows or columns

        ##### For this demo, you can:
        1. **Explore your data**: Alternate between the **demo_survey** and **demo_backcheck**
        tabs below to see your survey data and backcheck data.
        2. **Transform date column**: Add data preparation steps if you want to experiment.
        Do the following:
            - Select the **demo_survey** tab
            - Click on the "Add Preparation Step" button
            - Under "Select Action", choose "Transform Column"
            - For "Select Column to Transform", choose "submissiondate"
            - For "select function", choose "string to datetime". Note that the functions
              available depend on the type of column selected.
            - Click on "Add" to save the preparation step.
            - Review the "submissiondate" column to see the changes.
        3. **Apply same step to backcheck data**: Select the **demo_backcheck** tab and repeat
        the same steps to transform the "submissiondate" column there as well.,


        **Ready to continue?** Preview and data and additional transformations.
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

    @classmethod
    def get_info_message(cls, message_id: str) -> str:
        """Retrieve demo messages based on type."""
        demo_messages = {
            "add_to_session_info": cls.ADD_TO_SESSION_INFO,
            "prepare_data_info": cls.PREPARE_DATA_INFO,
            "preview_data_info": cls.PREVIEW_DATA_INFO,
            "proceed_to_config_info": cls.PROCEED_TO_CONFIG_INFO,
            "demo_data_info": cls.DEMO_DATA_INFO,
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
        ##### 🔧 Set up your data quality analysis!

        ##### What you're doing in this step:
        - Creating a "check configuration" that tells DataSure how to analyze your data
        - Mapping your data columns to specific quality checks
        - Connecting your survey data with backcheck data for validation

        ##### Demo Instructions:
        1. **Click "Add new check configuration"**
        2. **Name it**: "Household Survey Checks" or similar
        3. **Select Survey Dataset**: Choose "demo_survey"
        4. **Configure Key Columns**:
            - **Key Column**: "hhid" (Household ID - uniquely identifies each survey)
            - **ID Column**: "hhid" (same as key column)
            - **Enumerator Column**: "enum_name" (tracks data collector performance)
            - **Date Column**: Leave blank (demo data format issue)
        5. **Add Backcheck Dataset**: Choose "demo_backcheck"
        6. **Click "Add Check Configuration"**

        ##### What DataSure will analyze:
        - Duplicate household records and missing data patterns
        - Enumerator performance and data collection quality
        - Statistical outliers and data inconsistencies
        - Backcheck validation comparing survey responses to quality control visits

        **🎆 Next step:** View comprehensive quality analysis reports!
        """,
    }

    REVIEW: ClassVar[dict] = {
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

    @classmethod
    def get_step_info(cls, step: str) -> dict:
        """Retrieve step information based on step name."""
        steps = {
            "start": cls.START,
            "import": cls.IMPORT,
            "prepare": cls.PREPARE,
            "configure": cls.CONFIGURE,
            "review": cls.REVIEW,
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
            cls.REVIEW,
        ]

    @classmethod
    def get_guidance(cls, step: int) -> None:
        """Retrieve guidance for a specific step."""
        steps = {
            1: cls.START,
            2: cls.IMPORT,
            3: cls.PREPARE,
            4: cls.CONFIGURE,
            5: cls.REVIEW,
        }
        guidance = steps.get(step, {})
        if not guidance:
            raise ValueError(f"Invalid step: {step}")
        with st.expander(f"📖 **{guidance['guidance_title']}**", expanded=True):
            demo_container(guidance["guidance_content"])


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

    def gen_starttime(self) -> pl.DataFrame:
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

    def gen_endtime(self) -> pl.DataFrame:
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

    def gen_submissiondate(self) -> pl.DataFrame:
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

    def gen_dates(self) -> pl.DataFrame:
        """Generate all date columns."""
        self.gen_starttime()
        self.gen_endtime()
        self.gen_submissiondate()

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


def load_demo_data():
    """Load demo data files into the demo project."""
    # Get asset paths
    assets_dir = Path(__file__).parent.parent / "assets"
    survey_path = assets_dir / "demo_survey.csv"
    backcheck_path = assets_dir / "demo_backcheck.csv"

    if not survey_path.exists() or not backcheck_path.exists():
        st.error("Demo data files not found. Please check the installation.")
        return False

    try:
        # Load survey data with flexible CSV parsing
        survey_df = pl.read_csv(
            str(survey_path), truncate_ragged_lines=True, ignore_errors=True
        )

        survey_df = DemoDataGenerator(survey_df).gen_dates()

        # Save to raw/prep database (for import system)
        duckdb_save_table(DEMO_PROJECT_ID, survey_df, "demo_survey", "raw")
        duckdb_save_table(DEMO_PROJECT_ID, survey_df, "demo_survey", "prep")

        # Load backcheck data with flexible CSV parsing
        backcheck_df = pl.read_csv(
            str(backcheck_path), truncate_ragged_lines=True, ignore_errors=True
        )

        backcheck_df = DemoDataGenerator(backcheck_df).gen_dates()

        # Save to raw/prep database (for import system)
        duckdb_save_table(DEMO_PROJECT_ID, backcheck_df, "demo_backcheck", "raw")
        duckdb_save_table(DEMO_PROJECT_ID, backcheck_df, "demo_backcheck", "prep")

        # clean log entries
        duckdb_remove_table(DEMO_PROJECT_ID, "prep_log_demo_survey", "logs")
        duckdb_remove_table(DEMO_PROJECT_ID, "prep_log_demo_backcheck", "logs")

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
            duckdb_save_table(
                DEMO_PROJECT_ID, empty_prep_log, f"prep_log_{alias}", "logs"
            )

        # Update session state with loaded datasets
        st.session_state.st_raw_dataset_list = ["demo_survey", "demo_backcheck"]

    except Exception as e:
        st.error(f"Error loading demo data: {e}")
        # Try alternative approach with pandas if polars fails
        try:
            import pandas as pd

            survey_df = pl.from_pandas(pd.read_csv(str(survey_path)))
            duckdb_save_table(DEMO_PROJECT_ID, survey_df, "demo_survey", "raw")

            backcheck_df = pl.from_pandas(pd.read_csv(str(backcheck_path)))
            duckdb_save_table(DEMO_PROJECT_ID, backcheck_df, "demo_backcheck", "raw")

            # Create import log entries for fallback method too
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

            # Create empty prep logs for each dataset (fallback method)
            for alias in ["demo_survey", "demo_backcheck"]:
                empty_prep_log = pl.DataFrame({"action": [], "description": []})
                duckdb_save_table(
                    DEMO_PROJECT_ID, empty_prep_log, f"prep_log_{alias}", "logs"
                )

            st.session_state.st_raw_dataset_list = ["demo_survey", "demo_backcheck"]
            st.success("Demo data loaded successfully using fallback method!")

        except Exception as fallback_e:
            st.error(f"Failed to load demo data with fallback method: {fallback_e}")
            return False
    else:
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
        if st.button("Restart Demo", use_container_width=True):
            set_onboarding_step(1)
            st.rerun()

    with col2:
        if st.button("Create Real Project", type="primary", use_container_width=True):
            st.session_state.st_project_id = ""
            st.session_state.pop("onboarding_step", None)
            st.switch_page("pages/start_view.py")
