"""Configuration utilities for check configuration management.

This module provides:
- Pydantic models for data validation
- Service layer for business logic
- UI components for Streamlit interface
"""

from pathlib import Path

import polars as pl
import streamlit as st
from pydantic import BaseModel, Field, ValidationError, field_validator

from datasure.utils.dataframe_utils import get_df_columns
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table

# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class CheckConfiguration(BaseModel):
    """Model for check configuration validation."""

    page_name: str = Field(default=None, min_length=1, max_length=20)
    survey_data_name: str = Field(default=None, min_length=1)
    survey_key: str = Field(default=None, min_length=1)
    survey_id: str = Field(default=None, min_length=1)
    survey_date: str | None = Field(default=None, min_length=1)
    enumerator: str | None = Field(default=None, min_length=1)
    team: str | None = Field(default=None, min_length=1)
    formversion: str | None = Field(default=None, min_length=1)
    duration: str | None = Field(default=None, min_length=1)
    survey_target: int | None = Field(default=None, ge=0)
    backcheck_data_name: str | None = Field(default=None, min_length=1)
    backcheck_date: str | None = Field(default=None, min_length=1)
    backchecker: str | None = Field(default=None, min_length=1)
    backchecker_team: str | None = Field(default=None, min_length=1)
    backcheck_target_percent: int | None = Field(default=None, ge=0, le=100)
    tracking_data_name: str | None = Field(default=None, min_length=1)

    @field_validator("page_name")
    @classmethod
    def validate_page_name(cls, v: str) -> str:
        """Validate page name format."""
        if not v or not v.strip():
            raise ValueError("Page name cannot be empty")
        return v.strip()

    def to_dict(self) -> dict:
        """Convert model to dictionary for storage."""
        return self.model_dump()


class SurveyColumnSelections(BaseModel):
    """Model for Survey column selections in the UI."""

    survey_key: str | None = Field(..., min_length=1)
    survey_id: str | None = Field(default=None, min_length=1)
    survey_date: str | None = Field(default=None, min_length=1)
    enumerator: str | None = Field(default=None, min_length=1)
    team: str | None = Field(default=None, min_length=1)
    formversion: str | None = Field(default=None, min_length=1)
    duration: str | None = Field(default=None, min_length=1)
    survey_target: int | None = Field(default=None, ge=0)


class BackcheckColumnSelectors(BaseModel):
    """Model for back check column selections in UI."""

    backcheck_date: str | None = Field(default=None, min_length=1)
    backchecker: str | None = Field(default=None, min_length=1)
    backchecker_team: str | None = Field(default=None, min_length=1)
    backcheck_target_percent: int | None = Field(default=None, ge=0, le=100)


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
        "Page Name",
        placeholder="eg. Household HFC, Individual HFC, etc.",
        help="This name will be used to create a new page for the checks.",
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
) -> SurveyColumnSelections:
    """
    Render column selection inputs.

    Args:
        string_columns: List of string column names
        numeric_columns: List of numeric column names
        datetime_columns: List of datetime column names

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
        datetime_cols, numeric_columns, categorical_cols
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
        )


def _handle_configuration_submission(
    config_service: ConfigurationService,
    column_selections: dict,
    page_name: str,
    survey_data_name: str,
    backcheck_data_name: str | None,
) -> None:
    """
    Handle form submission and save configuration.

    Args:
        config_service: Configuration service instance
        page_name: Page name for the configuration
        survey_data_name: Selected survey dataset name
        column_selections: User's column selections
    """
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
            "page_name": st.column_config.TextColumn("Page Name"),
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
