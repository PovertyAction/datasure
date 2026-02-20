"""Configuration utilities for check configuration management.

This module provides:
- Pydantic models for data validation
- Service layer for business logic
- UI components for Streamlit interface
"""

from pathlib import Path

import polars as pl
import streamlit as st
from pydantic import ValidationError

from datasure.models.schemas import (
    BackcheckColumnSelectors,
    CheckConfiguration,
    SurveyColumnSelections,
)
from datasure.utils.dataframe_utils import get_df_columns
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table

# ============================================================================
# CONSTANTS
# ============================================================================

PAGE_NAME_STR = "Page Name"

# ============================================================================
# SERVICE LAYER
# ============================================================================


class ConfigurationService:
    """Service for managing check configurations."""

    def __init__(self, project_id: str):
        """Initialize service with project ID."""
        self.project_id = project_id

    def get_all_configurations(self) -> pl.DataFrame:
        """Get all check configurations for the project."""
        return duckdb_get_table(
            project_id=self.project_id,
            alias="check_config",
            db_name="logs",
        )

    def get_page_names(self) -> list[str]:
        """Get list of existing page names."""
        config_df = self.get_all_configurations()
        if config_df.is_empty():
            return []
        return config_df["page_name"].to_list()

    def page_name_exists(self, page_name: str) -> bool:
        """Check if a page name already exists."""
        existing_pages = self.get_page_names()
        return page_name in existing_pages

    def validate_configuration(
        self, config_data: dict
    ) -> tuple[bool, str | None, CheckConfiguration | None]:
        """
        Validate configuration data.

        Returns
        -------
            tuple: (is_valid, error_message, validated_config)
        """
        try:
            config = CheckConfiguration(**config_data)

            # Check for duplicate page name
            if self.page_name_exists(config.page_name):
                return (
                    False,
                    f"Page name '{config.page_name}' already exists. Please choose a different name.",
                    None,
                )
            else:
                return True, None, config

        except ValidationError as e:
            error_msg = self._format_validation_error(e)
            return False, error_msg, None

    def _format_validation_error(self, error: ValidationError) -> str:
        """Format Pydantic validation error for user display."""
        errors = error.errors()
        if not errors:
            return "Validation error occurred"

        first_error = errors[0]
        field = first_error.get("loc", ["unknown"])[0]
        msg = first_error.get("msg", "Invalid value")

        return f"{field}: {msg}"

    def _add_page_file(self, page_number: int, replace: bool = False) -> None:
        """Create a new output view file for the configuration."""
        template_path = (
            Path(__file__).parent.parent / "views" / "output_view_template.py"
        )
        new_page_path = (
            Path(__file__).parent.parent / "views" / f"output_view_{page_number}.py"
        )

        # skip if file exists and not replacing
        if new_page_path.exists() and not replace:
            return

        with open(template_path) as template_file:
            template_content = template_file.read()

        with open(new_page_path, "w") as new_page_file:
            new_page_file.write(template_content)

    def add_configuration(self, config: CheckConfiguration) -> bool:
        """
        Add a new check configuration.

        Returns
        -------
            bool: True if successful, False otherwise
        """
        current_log = self.get_all_configurations()

        new_config_df = pl.DataFrame([config.to_dict()])

        if current_log.is_empty():
            config_log = new_config_df
        else:
            config_log = pl.concat([current_log, new_config_df], how="vertical")

        duckdb_save_table(
            self.project_id,
            config_log,
            alias="check_config",
            db_name="logs",
        )

        # Create new output view file
        page_number = config_log.height
        self._add_page_file(page_number)

        st.rerun()

        return True

    def _remove_page_file(self, page_number: int) -> None:
        """Remove the output view file for the configuration."""
        page_path = (
            Path(__file__).parent.parent / "views" / f"output_view_{page_number}.py"
        )

        if page_path.exists():
            page_path.unlink()

    def remove_configuration(self, page_name: str) -> bool:
        """
        Remove a check configuration by page name.

        Returns
        -------
            bool: True if successful, False otherwise
        """
        current_log = self.get_all_configurations()

        if current_log.is_empty():
            return False

        updated_log = current_log.filter(pl.col("page_name") != page_name)

        duckdb_save_table(
            self.project_id,
            updated_log,
            alias="check_config",
            db_name="logs",
        )

        # Get the number of pages left ater removal
        pages_after_removal = updated_log.height

        # remove output view file
        self._remove_page_file(pages_after_removal + 1)

        st.rerun()

        return True

    def get_page_configuration(self, row_index: int) -> dict:
        """
        Return configuration info for row

        Returns
        -------
            dict - dict of column names and values for specified row_index
        """
        config_df = self.get_all_configurations()
        if config_df.is_empty() or row_index >= config_df.height:
            return {}
        return config_df.row(row_index, named=True)

    def get_configuration_by_page_name(self, page_name: str) -> dict:
        """
        Return configuration info for a given page name.

        Returns
        -------
            dict - dict of column names and values, or empty dict if not found
        """
        config_df = self.get_all_configurations()
        if config_df.is_empty():
            return {}
        match = config_df.filter(pl.col("page_name") == page_name)
        if match.is_empty():
            return {}
        return match.row(0, named=True)

    def validate_edit_configuration(
        self, config_data: dict, original_page_name: str
    ) -> tuple[bool, str | None, CheckConfiguration | None]:
        """
        Validate configuration data for an edit operation.

        Allows the page name to remain the same as the original without
        raising a duplicate error.

        Returns
        -------
            tuple: (is_valid, error_message, validated_config)
        """
        try:
            config = CheckConfiguration(**config_data)

            if config.page_name != original_page_name and self.page_name_exists(
                config.page_name
            ):
                return (
                    False,
                    f"Page name '{config.page_name}' already exists. Please choose a different name.",
                    None,
                )

        except ValidationError as e:
            error_msg = self._format_validation_error(e)
            return False, error_msg, None
        else:
            return True, None, config

    def update_configuration(
        self, original_page_name: str, config: CheckConfiguration
    ) -> bool:
        """
        Update an existing check configuration in-place (preserves row order).

        Returns
        -------
            bool: True if successful, False otherwise
        """
        current_log = self.get_all_configurations()

        if current_log.is_empty():
            return False

        page_names = current_log["page_name"].to_list()
        if original_page_name not in page_names:
            return False

        row_idx = page_names.index(original_page_name)
        new_row_df = pl.DataFrame([config.to_dict()])

        before = current_log.slice(0, row_idx)
        after = current_log.slice(row_idx + 1)

        parts = [p for p in [before, new_row_df, after] if not p.is_empty()]
        updated_log = pl.concat(parts, how="vertical")

        duckdb_save_table(
            self.project_id,
            updated_log,
            alias="check_config",
            db_name="logs",
        )

        st.rerun()

        return True


class DatasetService:
    """Service for working with datasets and their columns."""

    def __init__(self, project_id: str):
        """Initialize service with project ID."""
        self.project_id = project_id

    def get_dataset_columns(
        self, dataset_alias: str
    ) -> tuple[list[str], list[str], list[str]]:
        """
        Get categorized columns from a dataset.

        Returns
        -------
            tuple: (string_columns, numeric_columns, datetime_columns)
        """
        survey_df = duckdb_get_table(
            project_id=self.project_id,
            alias=dataset_alias,
            db_name="prep",
            type="pd",
        )

        column_info = get_df_columns(survey_df)
        datetime_columns = column_info.datetime_columns
        numeric_columns = column_info.numeric_columns
        categorical_columns = column_info.categorical_columns

        return datetime_columns, numeric_columns, categorical_columns

    def get_available_aliases_excluding(
        self, all_aliases: list[str], exclude: list[str]
    ) -> list[str]:
        """Get list of aliases excluding specified ones."""
        return sorted([alias for alias in all_aliases if alias not in exclude])

    def validate_key_column(
        self, dataset_alias: str, column_name: str
    ) -> tuple[bool, str | None]:
        """
        Validate that a column has no missing values and all unique values.

        Returns
        -------
            tuple: (is_valid, error_message)
        """
        df = duckdb_get_table(
            project_id=self.project_id,
            alias=dataset_alias,
            db_name="prep",
            type="pd",
        )

        null_count = int(df[column_name].isna().sum())
        if null_count > 0:
            return (
                False,
                f"Key column '{column_name}' has {null_count} missing value(s). "
                "Please select a column with no missing values.",
            )

        total = len(df)
        unique_count = int(df[column_name].nunique())
        if unique_count < total:
            duplicate_count = total - unique_count
            return (
                False,
                f"Key column '{column_name}' has {duplicate_count} duplicate value(s). "
                "Please select a column with all unique values.",
            )

        return True, None


# ============================================================================
# UI COMPONENTS
# ============================================================================


class ConfigurationFormState:
    """Manages form state for configuration creation."""

    def __init__(self):
        """Initialize form state."""
        self.page_name: str | None = None
        self.survey_data_name: str | None = None
        self.columns: SurveyColumnSelections = SurveyColumnSelections()


def render_page_name_input() -> str | None:
    """
    Render page name input field.

    Returns
    -------
        Page name entered by user or None
    """
    return st.text_input(
        PAGE_NAME_STR,
        placeholder="eg. Household HFC, Individual HFC, etc.",
        help="This name will be used to create a new page for the checks.",
        max_chars=20,
        key="check_config_page_name_input",
    )


def render_survey_dataset_selector(alias_list: list[str]) -> str | None:
    """
    Render survey dataset selection dropdown.

    Args:
        alias_list: List of available dataset aliases

    Returns
    -------
        Selected dataset name or None
    """
    return st.selectbox(
        "Select Survey Dataset",
        options=sorted(alias_list),
        index=None,
        help="Select the survey dataset to check.",
    )


@st.fragment
def render_survey_column_selectors(
    datetime_columns: list[str] | None = None,
    numeric_columns: list[str] | None = None,
    categorical_columns: list[str] | None = None,
    project_id: str | None = None,
    dataset_alias: str | None = None,
) -> SurveyColumnSelections:
    """
    Render column selection inputs.

    Args:
        datetime_columns: List of datetime column names
        numeric_columns: List of numeric column names
        categorical_columns: List of categorical column names
        project_id: Project ID used to validate the key column against actual data
        dataset_alias: Dataset alias used to validate the key column against actual data

    Returns
    -------
        ColumnSelections object with user selections
    """
    with st.container(border=True):
        st.subheader("Select survey data columns")

        survey_key = st.selectbox(
            "Select Key Column (Required*)",
            options=categorical_columns,
            index=None,
            help="Select the column that uniquely identifies each record.",
        )

        if survey_key and project_id and dataset_alias:
            _key_valid, _key_error = DatasetService(project_id).validate_key_column(
                dataset_alias, survey_key
            )
            if not _key_valid:
                st.error(_key_error)

        survey_id = st.selectbox(
            "Select ID Column (Optional)",
            options=categorical_columns,
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
            options=categorical_columns,
            index=None,
            help="Select the column that contains the enumerator for each record.",
        )

        team = st.selectbox(
            "Select Team Column (Optional)",
            options=categorical_columns,
            index=None,
            help="Select the column that contains the team for each record.",
        )

        formversion = st.selectbox(
            "Select Form Version Column (Optional)",
            options=numeric_columns,
            index=None,
            help="Select the column that contains the form version for each record.",
        )

        duration = st.selectbox(
            "Select Duration Column (Optional)",
            options=numeric_columns,
            index=None,
            help="Select the column that contains the duration for each record.",
        )

        survey_target = st.number_input(
            "Enter Target Number of responses for the Survey (Optional)",
            min_value=0,
            step=1,
            help="Enter the target number of responses for the survey dataset.",
        )

        return SurveyColumnSelections(
            survey_key=survey_key,
            survey_id=survey_id,
            survey_date=survey_date,
            enumerator=enumerator,
            team=team,
            formversion=formversion,
            duration=duration,
            survey_target=survey_target,
        )


def render_backcheck_dataset_selector(
    alias_list: list[str], survey_data_name: str
) -> str | None:
    """
    Render backcheck dataset selection dropdown.

    Args:
        alias_list: List of available dataset aliases

    Returns
    -------
        Selected dataset name or None
    """
    dataset_service = DatasetService(project_id="")  # Project ID not needed here

    # Get backcheck options (exclude survey dataset)
    backcheck_data_options = dataset_service.get_available_aliases_excluding(
        alias_list, [survey_data_name]
    )

    return st.selectbox(
        "Select Backcheck Dataset",
        options=backcheck_data_options,
        index=None,
        help="Select the backcheck dataset to check.",
    )


@st.fragment
def render_backcheck_column_selectors(
    datetime_columns: list[str] | None = None,
    categorical_columns: list[str] | None = None,
) -> BackcheckColumnSelectors:
    """Render column selection inputs for backcheck dataset."""
    with st.container(border=True):
        st.subheader("Select backcheck data columns")

        backcheck_date = st.selectbox(
            "Select Backcheck Date Column (Optional)",
            options=datetime_columns,
            index=None,
            help="Select the column that contains the date for each record in backcheck dataset.",
        )

        backchecker = st.selectbox(
            "Select Backchecker Column (Optional)",
            options=categorical_columns,
            index=None,
            help="Select the column that contains the backchecker for each record in backcheck dataset.",
        )

        backchecker_team = st.selectbox(
            "Select Backchecker Team Column (Optional)",
            options=categorical_columns,
            index=None,
            help="Select the column that contains the team for each record in the backcheck dataset.",
        )

        backcheck_target_percent = st.number_input(
            "Enter Target Percentage of surveys to be Backchecked (Optional)",
            min_value=0,
            max_value=100,
            step=1,
            help="Enter the target percentage of surveys to be backchecked.",
        )

        return BackcheckColumnSelectors(
            backcheck_date=backcheck_date,
            backchecker=backchecker,
            backchecker_team=backchecker_team,
            backcheck_target_percent=backcheck_target_percent,
        )


@st.dialog(title="Add New Check Configuration", width="medium")
def add_check_configuration_form(
    project_id: str,
    alias_list: list[str],
) -> None:
    """
    Render the add check configuration form.

    Args:
        project_id: Current project ID
        alias_list: List of available dataset aliases
    """
    config_service = ConfigurationService(project_id)
    dataset_service = DatasetService(project_id)

    # Step 1: Page name input
    page_name = render_page_name_input()

    # Early validation of page name
    if not page_name:
        st.info("Enter a page name to continue")
        return

    # Check if page name is valid
    config_data = {"page_name": page_name}
    is_valid, error_msg, _ = config_service.validate_configuration(
        {**config_data, "survey_data_name": "temp", "survey_key": "temp"}
    )

    if not is_valid and "already exists" in (error_msg or ""):
        st.error(error_msg)
        return

    # Step 2: Survey dataset selection
    survey_data_name = render_survey_dataset_selector(alias_list)

    if not survey_data_name:
        return

    # Step 3: Get dataset columns
    datetime_cols, numeric_columns, categorical_cols = (
        dataset_service.get_dataset_columns(survey_data_name)
    )

    # Step 4: Survey Column selections
    survey_column_selections = render_survey_column_selectors(
        datetime_cols,
        numeric_columns,
        categorical_cols,
        project_id=project_id,
        dataset_alias=survey_data_name,
    )

    column_selections = dict(survey_column_selections)

    # Step 5: Backcheck dataset selection
    backcheck_data_name = render_backcheck_dataset_selector(
        alias_list, survey_data_name
    )

    if backcheck_data_name:
        # Get backcheck dataset columns
        (
            backcheck_datetime_cols,
            _,
            backcheck_categorical_cols,
        ) = dataset_service.get_dataset_columns(backcheck_data_name)
        # Step 6: Back Check Column Selectors
        backcheck_column_selections = render_backcheck_column_selectors(
            backcheck_datetime_cols, backcheck_categorical_cols
        )

        # merge survey and backcheck column selection
        column_selections = dict(survey_column_selections) | dict(
            backcheck_column_selections
        )

    # Step 6: Submit button
    add_button = st.button(
        "Add Check Configuration",
        type="primary",
        width="stretch",
        key="add_check_config_btn",
    )

    # merge survey and backcheck column selection
    if add_button:
        _handle_configuration_submission(
            config_service=config_service,
            column_selections=column_selections,
            page_name=page_name,
            survey_data_name=survey_data_name,
            backcheck_data_name=backcheck_data_name,
            project_id=project_id,
        )


def _handle_configuration_submission(
    config_service: ConfigurationService,
    column_selections: dict,
    page_name: str,
    survey_data_name: str,
    backcheck_data_name: str | None,
    project_id: str,
) -> None:
    """
    Handle form submission and save configuration.

    Args:
        config_service: Configuration service instance
        page_name: Page name for the configuration
        survey_data_name: Selected survey dataset name
        column_selections: User's column selections
        project_id: Project ID for key column validation
    """
    survey_key = column_selections.get("survey_key")
    if survey_key:
        is_key_valid, key_error = DatasetService(project_id).validate_key_column(
            survey_data_name, survey_key
        )
        if not is_key_valid:
            st.error(key_error)
            return

    # Build configuration data
    config_data = {
        "page_name": page_name,
        "survey_data_name": survey_data_name,
        "survey_key": column_selections.get("survey_key"),
        "survey_id": column_selections.get("survey_id"),
        "survey_date": column_selections.get("survey_date"),
        "enumerator": column_selections.get("enumerator"),
        "team": column_selections.get("team"),
        "formversion": column_selections.get("formversion"),
        "duration": column_selections.get("duration"),
        "survey_target": column_selections.get("survey_target"),
        "backcheck_data_name": backcheck_data_name,
        "backcheck_date": column_selections.get("backcheck_date"),
        "backchecker": column_selections.get("backchecker"),
        "backchecker_team": column_selections.get("backchecker_team"),
        "backcheck_target_percent": column_selections.get("backcheck_target_percent"),
        "tracking_data_name": column_selections.get("tracking_data_name"),
    }

    # Validate and save
    is_valid, error_msg, validated_config = config_service.validate_configuration(
        config_data
    )

    if not is_valid:
        st.error(error_msg)
        return

    if validated_config:
        success = config_service.add_configuration(validated_config)
        if success:
            st.success(f"Check configuration '{page_name}' added successfully.")
        else:
            st.error("Failed to add configuration. Please try again.")


def remove_check_configuration_form(project_id: str) -> None:
    """
    Render the remove check configuration form.

    Args:
        project_id: Current project ID
    """
    config_service = ConfigurationService(project_id)

    with st.popover(
        label="Remove Check Configuration",
        icon=":material/delete:",
        width="stretch",
    ):
        st.warning("This will remove the check configuration.")

        page_names = config_service.get_page_names()

        if not page_names:
            st.info("No check configurations found. Please add a check configuration.")
            return

        selected_page = st.selectbox(
            "Select Check Configuration to Remove",
            options=sorted(page_names),
            index=None,
        )

        remove_button = st.button(
            "Remove Check Configuration",
            type="primary",
            width="stretch",
            disabled=not selected_page,
        )

        if remove_button and selected_page:
            success = config_service.remove_configuration(selected_page)
            if success:
                st.success(
                    f"Check configuration '{selected_page}' removed successfully."
                )
            else:
                st.error("Failed to remove configuration. Please try again.")


def _get_index_or_none(value: str | None, options: list[str]) -> int | None:
    """Return the index of value in options, or None if absent."""
    if value and value in options:
        return options.index(value)
    return None


def render_configuration_table(config_df) -> None:
    """
    Render the configuration table display.

    Args:
        config_df: Polars DataFrame with configuration data
    """
    st.dataframe(
        config_df,
        width="stretch",
        hide_index=True,
        key="check_config_log",
        column_config={
            "page_name": st.column_config.TextColumn(PAGE_NAME_STR),
            "survey_data_name": st.column_config.TextColumn("Survey Dataset"),
            "survey_key": st.column_config.TextColumn("Key Column"),
            "survey_id": st.column_config.TextColumn("ID Column"),
            "survey_date": st.column_config.TextColumn("Date Column"),
            "enumerator": st.column_config.TextColumn("Enumerator Column"),
            "survey_target": st.column_config.NumberColumn("Target Survey Responses"),
            "backcheck_data_name": st.column_config.TextColumn("Backcheck Dataset"),
            "backcheck_date": st.column_config.TextColumn("Backcheck Date Column"),
            "backchecker": st.column_config.TextColumn("Backchecker Column"),
            "tracking_data_name": st.column_config.TextColumn("Tracking Dataset"),
            "backcheck_target_percent": st.column_config.NumberColumn(
                "Target Backcheck Percentage"
            ),
        },
    )


@st.fragment
def render_survey_column_selectors_edit(
    datetime_columns: list[str] | None = None,
    numeric_columns: list[str] | None = None,
    categorical_columns: list[str] | None = None,
    defaults: dict | None = None,
    project_id: str | None = None,
    dataset_alias: str | None = None,
) -> SurveyColumnSelections:
    """
    Render survey column selection inputs pre-populated with existing values.

    Args:
        datetime_columns: List of datetime column names
        numeric_columns: List of numeric column names
        categorical_columns: List of categorical column names
        defaults: Dict of current saved values keyed by field name
        project_id: Project ID used to validate the key column against actual data
        dataset_alias: Dataset alias used to validate the key column against actual data

    Returns
    -------
        SurveyColumnSelections with user selections
    """
    defaults = defaults or {}
    datetime_columns = datetime_columns or []
    numeric_columns = numeric_columns or []
    categorical_columns = categorical_columns or []

    with st.container(border=True):
        st.subheader("Select survey data columns")

        survey_key = st.selectbox(
            "Select Key Column (Required*)",
            options=categorical_columns,
            index=_get_index_or_none(defaults.get("survey_key"), categorical_columns),
            help="Select the column that uniquely identifies each record.",
            key="edit_survey_key",
        )

        if survey_key and project_id and dataset_alias:
            _key_valid, _key_error = DatasetService(project_id).validate_key_column(
                dataset_alias, survey_key
            )
            if not _key_valid:
                st.error(_key_error)

        survey_id = st.selectbox(
            "Select ID Column (Optional)",
            options=categorical_columns,
            index=_get_index_or_none(defaults.get("survey_id"), categorical_columns),
            help="Select the column that contains the ID for each record.",
            key="edit_survey_id",
        )

        survey_date = st.selectbox(
            "Select Date Column (Optional)",
            options=datetime_columns,
            index=_get_index_or_none(defaults.get("survey_date"), datetime_columns),
            help="Select the column that contains the date for each record.",
            key="edit_survey_date",
        )

        enumerator = st.selectbox(
            "Select Enumerator Column (Optional)",
            options=categorical_columns,
            index=_get_index_or_none(defaults.get("enumerator"), categorical_columns),
            help="Select the column that contains the enumerator for each record.",
            key="edit_enumerator",
        )

        team = st.selectbox(
            "Select Team Column (Optional)",
            options=categorical_columns,
            index=_get_index_or_none(defaults.get("team"), categorical_columns),
            help="Select the column that contains the team for each record.",
            key="edit_team",
        )

        formversion = st.selectbox(
            "Select Form Version Column (Optional)",
            options=numeric_columns,
            index=_get_index_or_none(defaults.get("formversion"), numeric_columns),
            help="Select the column that contains the form version for each record.",
            key="edit_formversion",
        )

        duration = st.selectbox(
            "Select Duration Column (Optional)",
            options=numeric_columns,
            index=_get_index_or_none(defaults.get("duration"), numeric_columns),
            help="Select the column that contains the duration for each record.",
            key="edit_duration",
        )

        survey_target = st.number_input(
            "Enter Target Number of responses for the Survey (Optional)",
            min_value=0,
            value=defaults.get("survey_target") or 0,
            step=1,
            help="Enter the target number of responses for the survey dataset.",
            key="edit_survey_target",
        )

        return SurveyColumnSelections(
            survey_key=survey_key,
            survey_id=survey_id,
            survey_date=survey_date,
            enumerator=enumerator,
            team=team,
            formversion=formversion,
            duration=duration,
            survey_target=survey_target,
        )


@st.fragment
def render_backcheck_column_selectors_edit(
    datetime_columns: list[str] | None = None,
    categorical_columns: list[str] | None = None,
    defaults: dict | None = None,
) -> BackcheckColumnSelectors:
    """
    Render backcheck column selection inputs pre-populated with existing values.

    Args:
        datetime_columns: List of datetime column names
        categorical_columns: List of categorical column names
        defaults: Dict of current saved values keyed by field name

    Returns
    -------
        BackcheckColumnSelectors with user selections
    """
    defaults = defaults or {}
    datetime_columns = datetime_columns or []
    categorical_columns = categorical_columns or []

    with st.container(border=True):
        st.subheader("Select backcheck data columns")

        backcheck_date = st.selectbox(
            "Select Backcheck Date Column (Optional)",
            options=datetime_columns,
            index=_get_index_or_none(defaults.get("backcheck_date"), datetime_columns),
            help="Select the column that contains the date for each record in backcheck dataset.",
            key="edit_backcheck_date",
        )

        backchecker = st.selectbox(
            "Select Backchecker Column (Optional)",
            options=categorical_columns,
            index=_get_index_or_none(defaults.get("backchecker"), categorical_columns),
            help="Select the column that contains the backchecker for each record in backcheck dataset.",
            key="edit_backchecker",
        )

        backchecker_team = st.selectbox(
            "Select Backchecker Team Column (Optional)",
            options=categorical_columns,
            index=_get_index_or_none(
                defaults.get("backchecker_team"), categorical_columns
            ),
            help="Select the column that contains the team for each record in the backcheck dataset.",
            key="edit_backchecker_team",
        )

        backcheck_target_percent = st.number_input(
            "Enter Target Percentage of surveys to be Backchecked (Optional)",
            min_value=0,
            max_value=100,
            value=defaults.get("backcheck_target_percent") or 0,
            step=1,
            help="Enter the target percentage of surveys to be backchecked.",
            key="edit_backcheck_target_percent",
        )

        return BackcheckColumnSelectors(
            backcheck_date=backcheck_date,
            backchecker=backchecker,
            backchecker_team=backchecker_team,
            backcheck_target_percent=backcheck_target_percent,
        )


@st.dialog(title="Edit Check Configuration", width="medium")
def edit_check_configuration_form(
    project_id: str,
    alias_list: list[str],
) -> None:
    """
    Render the edit check configuration form.

    Loads the existing configuration for the selected page and pre-populates
    all fields so users can update any value.

    Args:
        project_id: Current project ID
        alias_list: List of available dataset aliases
    """
    config_service = ConfigurationService(project_id)
    dataset_service = DatasetService(project_id)

    page_names = config_service.get_page_names()

    if not page_names:
        st.info(
            "No check configurations found. Please add a check configuration first."
        )
        return

    # Step 1: Select which configuration to edit
    selected_page = st.selectbox(
        "Select Check Configuration to Edit",
        options=sorted(page_names),
        index=None,
        key="edit_config_page_select",
    )

    if not selected_page:
        st.info("Select a configuration to edit.")
        return

    current_config = config_service.get_configuration_by_page_name(selected_page)

    if not current_config:
        st.error("Could not load configuration. Please try again.")
        return

    st.divider()

    # Step 2: Page name input (pre-filled, editable)
    page_name = st.text_input(
        PAGE_NAME_STR,
        value=current_config.get("page_name", ""),
        placeholder="eg. Household HFC, Individual HFC, etc.",
        help="This name will be used to identify the check page.",
        max_chars=20,
        key="edit_check_config_page_name_input",
    )

    if not page_name:
        st.info("Enter a page name to continue.")
        return

    # Step 3: Survey dataset selection (pre-selected)
    sorted_aliases = sorted(alias_list)
    current_survey = current_config.get("survey_data_name")
    survey_dataset_index = _get_index_or_none(current_survey, sorted_aliases)

    survey_data_name = st.selectbox(
        "Select Survey Dataset",
        options=sorted_aliases,
        index=survey_dataset_index,
        help="Select the survey dataset to check.",
        key="edit_survey_dataset",
    )

    if not survey_data_name:
        return

    # Step 4: Get dataset columns and render survey column selectors
    datetime_cols, numeric_cols, categorical_cols = dataset_service.get_dataset_columns(
        survey_data_name
    )

    survey_column_selections = render_survey_column_selectors_edit(
        datetime_cols,
        numeric_cols,
        categorical_cols,
        defaults=current_config,
        project_id=project_id,
        dataset_alias=survey_data_name,
    )

    column_selections = dict(survey_column_selections)

    # Step 5: Backcheck dataset selection (pre-selected if present)
    dataset_service_plain = DatasetService(project_id="")
    backcheck_options = dataset_service_plain.get_available_aliases_excluding(
        alias_list, [survey_data_name]
    )

    current_backcheck = current_config.get("backcheck_data_name")
    backcheck_dataset_index = _get_index_or_none(current_backcheck, backcheck_options)

    backcheck_data_name = st.selectbox(
        "Select Backcheck Dataset",
        options=backcheck_options,
        index=backcheck_dataset_index,
        help="Select the backcheck dataset to check.",
        key="edit_backcheck_dataset",
    )

    if backcheck_data_name:
        (
            bc_datetime_cols,
            _,
            bc_categorical_cols,
        ) = dataset_service.get_dataset_columns(backcheck_data_name)

        backcheck_column_selections = render_backcheck_column_selectors_edit(
            bc_datetime_cols, bc_categorical_cols, defaults=current_config
        )

        column_selections = dict(survey_column_selections) | dict(
            backcheck_column_selections
        )

    # Step 6: Submit button
    save_button = st.button(
        "Save Changes",
        type="primary",
        width="stretch",
        key="edit_check_config_save_btn",
    )

    if save_button:
        _handle_edit_configuration_submission(
            config_service=config_service,
            original_page_name=selected_page,
            column_selections=column_selections,
            page_name=page_name,
            survey_data_name=survey_data_name,
            backcheck_data_name=backcheck_data_name,
            project_id=project_id,
        )


def _handle_edit_configuration_submission(
    config_service: ConfigurationService,
    original_page_name: str,
    column_selections: dict,
    page_name: str,
    survey_data_name: str,
    backcheck_data_name: str | None,
    project_id: str,
) -> None:
    """
    Handle edit form submission and persist the updated configuration.

    Args:
        config_service: Configuration service instance
        original_page_name: The page name before editing (used to locate the row)
        column_selections: User's updated column selections
        page_name: New (or unchanged) page name
        survey_data_name: Selected survey dataset name
        backcheck_data_name: Selected backcheck dataset name, or None
        project_id: Project ID for key column validation
    """
    survey_key = column_selections.get("survey_key")
    if survey_key:
        is_key_valid, key_error = DatasetService(project_id).validate_key_column(
            survey_data_name, survey_key
        )
        if not is_key_valid:
            st.error(key_error)
            return

    config_data = {
        "page_name": page_name,
        "survey_data_name": survey_data_name,
        "survey_key": column_selections.get("survey_key"),
        "survey_id": column_selections.get("survey_id"),
        "survey_date": column_selections.get("survey_date"),
        "enumerator": column_selections.get("enumerator"),
        "team": column_selections.get("team"),
        "formversion": column_selections.get("formversion"),
        "duration": column_selections.get("duration"),
        "survey_target": column_selections.get("survey_target"),
        "backcheck_data_name": backcheck_data_name,
        "backcheck_date": column_selections.get("backcheck_date"),
        "backchecker": column_selections.get("backchecker"),
        "backchecker_team": column_selections.get("backchecker_team"),
        "backcheck_target_percent": column_selections.get("backcheck_target_percent"),
        "tracking_data_name": column_selections.get("tracking_data_name"),
    }

    is_valid, error_msg, validated_config = config_service.validate_edit_configuration(
        config_data, original_page_name
    )

    if not is_valid:
        st.error(error_msg)
        return

    if validated_config:
        success = config_service.update_configuration(
            original_page_name, validated_config
        )
        if success:
            st.success(f"Check configuration '{page_name}' updated successfully.")
        else:
            st.error("Failed to update configuration. Please try again.")
