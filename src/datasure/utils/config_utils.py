"""Configuration utilities for check configuration management.

This module provides:
- Pydantic models for data validation
- Service layer for business logic
- UI components for Streamlit interface
"""

import polars as pl
import streamlit as st
from pydantic import BaseModel, Field, ValidationError, field_validator

from datasure.utils import duckdb_get_table, duckdb_save_table, get_df_info

# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class CheckConfiguration(BaseModel):
    """Model for check configuration validation."""

    page_name: str = Field(..., min_length=1, max_length=20)
    survey_data_name: str = Field(..., min_length=1)
    survey_key: str = Field(..., min_length=1)
    survey_id: str | None = None
    survey_date: str | None = None
    enumerator: str | None = None
    backcheck_data_name: str | None = None
    tracking_data_name: str | None = None

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


class ColumnSelections(BaseModel):
    """Model for column selections in the UI."""

    survey_key: str | None = None
    survey_id: str | None = None
    survey_date: str | None = None
    enumerator: str | None = None
    backcheck_data_name: str | None = None
    tracking_data_name: str | None = None

    def is_valid_for_submission(self) -> bool:
        """Check if minimum required fields are selected."""
        return self.survey_key is not None


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
        return True

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

        _, string_columns, numeric_columns, datetime_columns, _ = get_df_info(
            survey_df, cols_only=True
        )

        return string_columns, numeric_columns, datetime_columns

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
        self.columns: ColumnSelections = ColumnSelections()


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


def render_column_selectors(
    string_columns: list[str],
    numeric_columns: list[str],
    datetime_columns: list[str],
) -> ColumnSelections:
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

        key_options = string_columns + numeric_columns

        survey_key = st.selectbox(
            "Select Key Column (Required*)",
            options=key_options,
            index=None,
            help="Select the column that uniquely identifies each record.",
        )

        survey_id = st.selectbox(
            "Select ID Column (Optional)",
            options=key_options,
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
            options=key_options,
            index=None,
            help="Select the column that contains the enumerator for each record.",
        )

        return ColumnSelections(
            survey_key=survey_key,
            survey_id=survey_id,
            survey_date=survey_date,
            enumerator=enumerator,
        )


def render_additional_dataset_selectors(
    all_aliases: list[str],
    survey_data_name: str,
) -> tuple[str | None, str | None]:
    """
    Render backcheck and tracking dataset selectors.

    Args:
        all_aliases: All available dataset aliases
        survey_data_name: Currently selected survey dataset

    Returns
    -------
        tuple: (backcheck_data_name, tracking_data_name)
    """
    dataset_service = DatasetService(project_id="")  # Project ID not needed here

    # Get backcheck options (exclude survey dataset)
    backcheck_options = dataset_service.get_available_aliases_excluding(
        all_aliases, [survey_data_name]
    )

    backcheck_data_name = st.selectbox(
        "Select Backcheck Dataset (Optional)",
        options=backcheck_options,
        index=None,
        help="Select the backcheck dataset to compare with the survey dataset.",
    )

    # Get tracking options (exclude both survey and backcheck)
    exclude_list = [survey_data_name]
    if backcheck_data_name:
        exclude_list.append(backcheck_data_name)

    tracking_options = dataset_service.get_available_aliases_excluding(
        all_aliases, exclude_list
    )

    tracking_data_name = st.selectbox(
        "Select Tracking Dataset (Optional)",
        options=tracking_options,
        index=None,
        help="Select the tracking dataset to compare with the survey dataset.",
    )

    return backcheck_data_name, tracking_data_name


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

    with st.popover(
        label="Add new check configuration",
        icon=":material/add:",
        width="stretch",
    ):
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
        string_cols, numeric_cols, datetime_cols = dataset_service.get_dataset_columns(
            survey_data_name
        )

        # Step 4: Column selections
        column_selections = render_column_selectors(
            string_cols, numeric_cols, datetime_cols
        )

        # Step 5: Additional datasets
        backcheck_name, tracking_name = render_additional_dataset_selectors(
            alias_list, survey_data_name
        )

        # Update column selections with additional datasets
        column_selections.backcheck_data_name = backcheck_name
        column_selections.tracking_data_name = tracking_name

        # Step 6: Submit button
        add_button = st.button(
            "Add Check Configuration",
            type="primary",
            width="stretch",
            key="add_check_config_btn",
        )

        if add_button:
            _handle_configuration_submission(
                config_service=config_service,
                page_name=page_name,
                survey_data_name=survey_data_name,
                column_selections=column_selections,
            )


def _handle_configuration_submission(
    config_service: ConfigurationService,
    page_name: str,
    survey_data_name: str,
    column_selections: ColumnSelections,
) -> None:
    """
    Handle form submission and save configuration.

    Args:
        config_service: Configuration service instance
        page_name: Page name for the configuration
        survey_data_name: Selected survey dataset name
        column_selections: User's column selections
    """
    # Validate minimum requirements
    if not column_selections.is_valid_for_submission():
        st.error("Please select a key column.")
        return

    # Build configuration data
    config_data = {
        "page_name": page_name,
        "survey_data_name": survey_data_name,
        "survey_key": column_selections.survey_key,
        "survey_id": column_selections.survey_id,
        "survey_date": column_selections.survey_date,
        "enumerator": column_selections.enumerator,
        "backcheck_data_name": column_selections.backcheck_data_name,
        "tracking_data_name": column_selections.tracking_data_name,
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
            "backcheck_data_name": st.column_config.TextColumn("Backcheck Dataset"),
            "tracking_data_name": st.column_config.TextColumn("Tracking Dataset"),
        },
    )
