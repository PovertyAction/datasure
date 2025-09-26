import json
from pathlib import Path

import polars as pl
import streamlit as st

from datasure.utils.cache_utils import get_cache_path
from datasure.utils.duckdb_utils import duckdb_save_table

DEMO_PROJECT_NAME = "DataSure Demo"
DEMO_PROJECT_ID = "demoproject"

ONBOARDING_STEPS = [
    {
        "step": 1,
        "title": "Start Here",
        "description": "Welcome to DataSure! Learn how to manage survey data quality.",
        "icon": "🏠",
        "page": "start_view.py",
    },
    {
        "step": 2,
        "title": "Import Data",
        "description": "Import your survey data from various sources.",
        "icon": "📥",
        "page": "import_view.py",
    },
    {
        "step": 3,
        "title": "Prepare Data",
        "description": "Clean and prepare your data for quality checks.",
        "icon": "🛠️",
        "page": "prep_view.py",
    },
    {
        "step": 4,
        "title": "Configure Checks",
        "description": "Set up data quality checks and validation rules.",
        "icon": "⚙️",
        "page": "config_view.py",
    },
    {
        "step": 5,
        "title": "Review Reports",
        "description": "Analyze data quality results and insights.",
        "icon": "📊",
        "page": "output_view_1.py",
    },
]


def is_demo_project() -> bool:
    """Check if the current session is using the demo project."""
    return st.session_state.get("st_project_id") == DEMO_PROJECT_ID


def get_current_step() -> int:
    """Get the current onboarding step based on the active page."""
    current_page = st.session_state.get("current_page", "start_view.py")
    for step_info in ONBOARDING_STEPS:
        if step_info["page"] == current_page:
            return step_info["step"]
    return 1


def set_onboarding_step(step: int):
    """Set the current onboarding step."""
    st.session_state["onboarding_step"] = step


def get_onboarding_step() -> int:
    """Get the current onboarding step."""
    return st.session_state.get("onboarding_step", 1)


def show_progress_indicator():
    """Display the onboarding progress indicator."""
    if not is_demo_project():
        return

    current_step = get_onboarding_step()

    st.markdown("### Demo Progress")

    cols = st.columns(len(ONBOARDING_STEPS))

    for i, step_info in enumerate(ONBOARDING_STEPS):
        with cols[i]:
            if step_info["step"] <= current_step:
                # Completed or current step
                if step_info["step"] == current_step:
                    st.markdown(
                        f"""
                    <div style="text-align: center; padding: 10px; border: 2px solid #1f77b4; border-radius: 10px; background-color: #e6f3ff;">
                        <div style="font-size: 24px;">{step_info["icon"]}</div>
                        <div style="font-size: 12px; font-weight: bold; color: #1f77b4;">Step {step_info["step"]}</div>
                        <div style="font-size: 10px;">{step_info["title"]}</div>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"""
                    <div style="text-align: center; padding: 10px; border: 1px solid #28a745; border-radius: 10px; background-color: #d4edda;">
                        <div style="font-size: 20px; color: #28a745;">✓</div>
                        <div style="font-size: 12px; color: #28a745;">Step {step_info["step"]}</div>
                        <div style="font-size: 10px;">{step_info["title"]}</div>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )
            else:
                # Future step
                st.markdown(
                    f"""
                <div style="text-align: center; padding: 10px; border: 1px solid #dee2e6; border-radius: 10px; background-color: #f8f9fa;">
                    <div style="font-size: 20px; color: #6c757d;">{step_info["icon"]}</div>
                    <div style="font-size: 12px; color: #6c757d;">Step {step_info["step"]}</div>
                    <div style="font-size: 10px; color: #6c757d;">{step_info["title"]}</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

    st.markdown("---")


def show_demo_banner():
    """Display the demo mode banner."""
    if not is_demo_project():
        return

    st.info("""
    **Demo Mode Active** - You're exploring DataSure with sample data!
    This guided tour will show you how to use DataSure for survey data quality management.
    """)


def show_step_guidance(step: int):
    """Show guidance for the current step."""
    if not is_demo_project():
        return

    guidance_map = {
        1: {
            "title": "Welcome to DataSure!",
            "content": """
            **What you'll learn in this demo:**
            - How to import survey data from different sources
            - How to run data quality checks
            - How to identify and fix data issues
            - How to generate quality reports

            **Demo scenario:** You're working with household survey data from rural communities in India.
            The data includes information about demographics, income, land ownership, and living conditions.
            """,
        },
        2: {
            "title": "Data Successfully Imported!",
            "content": """
            **✅ Your demo data is already loaded and ready!**

            In a real project, you would have just:
            - Connected to your SurveyCTO server, OR
            - Uploaded CSV/Excel files from your computer, OR
            - Run custom Python scripts to import data

            **What's been imported for you:**
            - **Survey Data**: 12 household survey responses from rural communities
            - **Backcheck Data**: 8 quality control validation records

            **Both datasets contain realistic data quality issues** including:
            - Missing GPS coordinates
            - Duplicate household IDs
            - Inconsistent income reporting
            - Missing demographic information

            **👉 Ready for the next step:** Now let's prepare this data for quality analysis!
            """,
        },
        3: {
            "title": "Data Preparation (Optional)",
            "content": """
            **✅ Your demo data is ready for analysis!**

            **What you're seeing:**
            - Your imported survey data displayed in tabs
            - Data metrics showing rows, columns, and missing values
            - Tools to transform, clean, and modify your data

            **This step is optional for the demo** because:
            - Your demo data is already properly formatted
            - Quality issues are intentionally preserved for learning
            - You can skip directly to "Configure Checks"

            **💡 Feel free to explore the data preparation tools:**
            - Transform columns (text manipulation, calculations)
            - Add new columns (calculations, constants, IDs)
            - Remove problematic rows or columns
            - View the change log to track modifications

            **👉 Ready to find data quality issues?** Continue to "Configure Quality Checks"!
            """,
        },
        4: {
            "title": "Configure Quality Checks",
            "content": """
            **🔧 Set up your data quality analysis!**

            **What you're doing in this step:**
            - Creating a "check configuration" that tells DataSure how to analyze your data
            - Mapping your data columns to specific quality checks
            - Connecting your survey data with backcheck data for validation

            **Demo Instructions:**
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

            **What DataSure will analyze:**
            - Duplicate household records and missing data patterns
            - Enumerator performance and data collection quality
            - Statistical outliers and data inconsistencies
            - Backcheck validation comparing survey responses to quality control visits

            **🎆 Next step:** View comprehensive quality analysis reports!
            """,
        },
        5: {
            "title": "Review Quality Reports",
            "content": """
            **In this step you'll:**
            - Analyze data quality results
            - Understand quality metrics
            - Learn how to act on findings

            **Final step:** Discover insights about your data quality and learn how to improve
            data collection processes based on the findings.
            """,
        },
    }

    if step in guidance_map:
        guidance = guidance_map[step]
        with st.expander(f"📖 **{guidance['title']}**", expanded=True):
            st.markdown(guidance["content"])


def show_next_steps(current_step: int):
    """Show next steps and navigation options."""
    if not is_demo_project():
        return

    if current_step < len(ONBOARDING_STEPS):
        next_step = ONBOARDING_STEPS[current_step]  # next_step is 0-indexed

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
        # Save to raw database (for import system)
        duckdb_save_table(DEMO_PROJECT_ID, survey_df, "demo_survey", "raw")

        # Load backcheck data with flexible CSV parsing
        backcheck_df = pl.read_csv(
            str(backcheck_path), truncate_ragged_lines=True, ignore_errors=True
        )
        # Save to raw database (for import system)
        duckdb_save_table(DEMO_PROJECT_ID, backcheck_df, "demo_backcheck", "raw")

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
    return get_onboarding_step() >= len(ONBOARDING_STEPS)


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
