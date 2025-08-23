import polars as pl
import streamlit as st

from datasure.utils import (
    duckdb_get_aliases,
    duckdb_get_table,
    duckdb_save_table,
    get_df_info,
)

st.title("Configure Checks")
st.markdown("Add a page for each dataset you want to check")

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
    st.info("No check configurations found. Please add a check configuration to start.")
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
