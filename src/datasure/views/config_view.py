import polars as pl
import streamlit as st

from datasure.utils import (
    duckdb_get_aliases,
    duckdb_get_table,
    duckdb_save_table,
    get_df_info,
)
from datasure.utils.navigations import (
    add_demo_navigation,
    demo_callout,
    demo_expander,
    demo_sidebar_help,
    page_navigation,
    show_demo_next_action,
)
from datasure.utils.onboarding_utils import is_demo_project

# Add demo navigation and guidance
add_demo_navigation("config_view.py", step=4)
demo_sidebar_help()

st.title("Configure Checks")
st.markdown("Add a page for each dataset you want to check")

# Demo guidance
if is_demo_project():
    demo_callout(
        "Time to configure your data quality checks! "
        "This step sets up which data quality issues DataSure will look for in your survey data."
    )

    demo_expander(
        "What are Data Quality Checks?",
        """
        **Data quality checks help you identify:**
        - **Duplicates**: Records that appear more than once
        - **Missing data**: Required fields that are empty
        - **GPS issues**: Invalid coordinates or locations
        - **Outliers**: Values that are unusually high or low
        - **Inconsistencies**: Data that doesn't match expected patterns
        - **Progress tracking**: Survey completion rates
        - **Backcheck validation**: Quality control comparisons

        **For your demo:**
        1. **Create a configuration** for your survey data below
        2. **Map your data columns** to tell DataSure what to check
        3. **Include backcheck data** for validation comparisons
        """,
        expanded=True,
    )

# get project ID
project_id: str = st.session_state.st_project_id

if not project_id:
    st.info(
        "Select a project from the Start page and import data. You can also create a new project from the Start page."
    )
    st.stop()

# get list of dataset aliases
alias_list = duckdb_get_aliases(project_id=project_id)


# --- Add new configuration --- #


def add_check_configuration(project_id: str) -> None:
    """Add a new check configuration for the given alias."""

    def valid_page_name(project_id: str, page_name: str | None) -> bool:
        """Check if the page name is valid."""
        if not page_name:
            st.error("Please enter a page name.")
            return False

        if len(page_name) > 20:
            st.error("Page name must be less than 20 characters.")
            return False

        # get the current page names and check if the page name already exists
        current_pages_df: pl.DataFrame = duckdb_get_table(
            project_id=project_id, alias="check_config", db_name="logs"
        )
        if current_pages_df.is_empty():
            return True

        current_pages: list = current_pages_df["page_name"].to_list()

        # check if the page name already exists
        if page_name in current_pages:
            st.error(
                f"Page name '{page_name}' already exists. Please choose a different name."
            )
            return False

        return True

    with st.popover(
        label="Add new check configuration",
        icon=":material/add:",
        use_container_width=True,
    ):
        page_name = st.text_input(
            "Page Name",
            placeholder="eg. Household HFC, Individual HFC, etc.",
            help="This name will be used to create a new page for the checks.",
        )
        if valid_page_name(project_id=project_id, page_name=page_name):
            survey_data_name = st.selectbox(
                "Select Survey Dataset",
                options=sorted(alias_list),
                index=None,
                help="Select the survey dataset to check.",
            )

            if survey_data_name:
                survey_df = duckdb_get_table(
                    project_id=project_id,
                    alias=survey_data_name,
                    db_name="prep",
                    type="pd",
                )

                _, string_columns, numeric_columns, datetime_columns, _ = get_df_info(
                    survey_df, cols_only=True
                )

                with st.container(border=True):
                    st.subheader("Select survey data columns")
                    survey_key = st.selectbox(
                        "Select Key Column (Required*)",
                        options=string_columns + numeric_columns,
                        index=None,
                        help="Select the column that uniquely identifies each record.",
                    )

                    survey_id = st.selectbox(
                        "Select ID Column (Optional)",
                        options=string_columns + numeric_columns,
                        index=None,
                        help="Select the column that contains the ID for each record.",
                    )

                    survey_date = st.selectbox(
                        "Select Date Column (Optional)",
                        options=datetime_columns,
                        index=None,
                        help="Select the column that contains the date for each record.",
                    )

                    enumerator = st.selectbox(
                        "Select Enumerator Column (Optional)",
                        options=string_columns + numeric_columns,
                        index=None,
                        help="Select the column that contains the enumerator for each record.",
                    )

                backcheck_aliases = sorted(
                    [alias for alias in alias_list if alias != survey_data_name]
                )
                backcheck_data_name = st.selectbox(
                    "Select Backcheck Dataset (Optional)",
                    options=sorted(backcheck_aliases),
                    index=None,
                    help="Select the backcheck dataset to compare with the survey dataset.",
                )

                if backcheck_aliases:
                    tracking_aliases = [
                        alias
                        for alias in alias_list
                        if alias != survey_data_name and alias != backcheck_data_name
                    ]
                else:
                    tracking_aliases = [
                        alias for alias in alias_list if alias != survey_data_name
                    ]

                tracking_data_name = st.selectbox(
                    "Select Tracking Dataset (Optional)",
                    options=sorted(tracking_aliases),
                    index=None,
                    help="Select the tracking dataset to compare with the survey dataset.",
                )

            add_new_config_btn = st.button(
                "Add Check Configuration",
                type="primary",
                use_container_width=True,
                key="add_check_config_btn",
            )

            if add_new_config_btn:
                if not survey_data_name:
                    st.error("Please select a survey dataset.")
                elif not survey_key:
                    st.error("Please select a key column.")
                else:
                    # Save the configuration
                    new_config = {
                        "page_name": page_name,
                        "survey_data_name": survey_data_name,
                        "survey_key": survey_key,
                        "survey_id": survey_id,
                        "survey_date": survey_date,
                        "enumerator": enumerator,
                        "backcheck_data_name": backcheck_data_name,
                        "tracking_data_name": tracking_data_name,
                    }
                    current_log = duckdb_get_table(
                        project_id,
                        alias="check_config",
                        db_name="logs",
                    )
                    if current_log.is_empty():
                        config_log = pl.DataFrame([new_config])
                    else:
                        config_log = pl.concat(
                            [current_log, pl.DataFrame([new_config])], how="vertical"
                        )
                    duckdb_save_table(
                        project_id,
                        config_log,
                        alias="check_config",
                        db_name="logs",
                    )

                    st.success(f"Check configuration '{page_name}' added successfully.")


def remove_check_configuration(project_id: str) -> None:
    """Remove an existing check configuration for the given project_id."""
    with st.popover(
        label="Remove Check Configuration",
        icon=":material/delete:",
        use_container_width=True,
    ):
        st.warning("This will remove the check configuration.")
        check_config_log = duckdb_get_table(
            project_id=project_id, alias="check_config", db_name="logs"
        )
        if check_config_log.is_empty():
            st.info("No check configurations found. Please add a check configuration.")
            return

        remove_data = st.selectbox(
            "Select Check Configuration to Remove",
            options=sorted(check_config_log["page_name"].to_list()),
            index=None,
        )

        if st.button(
            "Remove Check Configuration",
            type="primary",
            use_container_width=True,
            disabled=not remove_data,
        ):
            # Filter out the selected configuration
            updated_log = check_config_log.filter(pl.col("page_name") != remove_data)
            duckdb_save_table(
                project_id,
                updated_log,
                alias="check_config",
                db_name="logs",
            )
            st.success(f"Check configuration '{remove_data}' removed successfully.")


# --- Display check configurations --- #
st.subheader("Check Configurations")

# Demo guidance for check configurations
if is_demo_project():
    demo_callout(
        "📋 Create your first check configuration below! "
        "This tells DataSure which datasets to analyze and how to analyze them.",
        "info",
    )

cc1, cc2, _ = st.columns([0.4, 0.3, 0.3])
# --- Add new check configuration --- #
with cc1:
    add_check_configuration(project_id)

with cc2:
    remove_check_configuration(project_id)

# get log of check configurations
check_config_log = duckdb_get_table(
    project_id=project_id, alias="check_config", db_name="logs"
)

if check_config_log.is_empty():
    if is_demo_project():
        demo_expander(
            "Demo Instructions: Create Your First Configuration",
            """
            **Follow these steps to set up data quality checks:**

            **Step 1: Click "Add new check configuration"**
            - Give it a name like "Household Survey Checks"

            **Step 2: Select your survey dataset**
            - Choose "demo_survey" (your main household survey data)

            **Step 3: Configure key columns:**
            - **Key Column**: Choose "hhid" (Household ID) - this uniquely identifies each survey
            - **ID Column**: Choose "hhid" as well
            - **Enumerator Column**: Choose "enum_name" (shows who collected the data)
            - **Date Column**: Leave blank (demo data doesn't have proper date format)

            **Step 4: Add backcheck dataset**
            - **Backcheck Dataset**: Choose "demo_backcheck" (quality control data)

            **Step 5: Click "Add Check Configuration"**

            **🎆 What happens next:** DataSure will create a comprehensive quality analysis page!
            """,
            expanded=True,
        )
    else:
        st.info(
            "No check configurations found. Please add a check configuration to start."
        )
else:
    st.dataframe(
        check_config_log,
        use_container_width=True,
        hide_index=True,
        key="check_config_log",
        column_config={
            "page_name": st.column_config.TextColumn("Page Name"),
            "survey_data_name": st.column_config.TextColumn("Survey Dataset"),
            "survey_key": st.column_config.TextColumn("Key Column"),
            "survey_id": st.column_config.TextColumn("ID Column"),
            "survey_date": st.column_config.TextColumn("Date Column"),
            "enumerator": st.column_config.TextColumn("Enumerator Column"),
            "backcheck_data_name": st.column_config.TextColumn("Backcheck Dataset"),
            "tracking_data_name": st.column_config.TextColumn("Tracking Dataset"),
        },
    )

check_page_names = (
    check_config_log["page_name"].to_list() if not check_config_log.is_empty() else []
)

# Demo next action or regular navigation
if is_demo_project():
    st.write("---")

    if not check_config_log.is_empty():
        demo_callout(
            "Great! Your check configuration is ready. "
            "Now let's see the data quality analysis results!",
            "success",
        )
        show_demo_next_action(4, "st_output_page1", "View Quality Reports")
    else:
        demo_callout(
            "Please create a check configuration above to continue with the demo.",
            "warning",
        )
else:
    page_navigation(
        prev={
            "page_name": st.session_state.st_prep_data_page,
            "label": "← Back: Prepare Data",
        },
        next={
            "page_name": st.session_state.st_output_page1,
            "label": "Next: Output Page 1 →",
        },
    )
