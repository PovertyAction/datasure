import logging
from typing import NamedTuple

import pandas as pd
import polars as pl
import streamlit as st

from datasure.models.enums import (
    COL_FUNC_WITH_VALUES,
    DEL_COND_USE_VALS,
    DEL_ROW_COND_MAX_1,
    DEL_ROW_COND_NUM_ONLY,
    DEL_ROW_COND_SAME_TYPE,
    DEL_ROW_COND_STR_ONLY,
    PrepActions,
    PrepFunctions,
    PrepMethods,
    PrepOperations,
    PrepRowConditions,
)
from datasure.processing.corrections import CorrectionProcessor
from datasure.processing.prep import (
    OperationError,
    ValidationError,
    prep_apply_action,
)
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.dataframe_utils import (
    ColumnByType,
    TableState,
    get_df_columns,
    get_table_state,
)
from datasure.utils.duckdb_utils import (
    duckdb_get_aliases,
    duckdb_get_table,
    duckdb_save_table,
)
from datasure.utils.nav_ui import (
    draw_nav,
    guarded_status,
    project_nav_key,
    resolve_selection,
    run_guarded,
)
from datasure.utils.navigation import (
    READY,
    CheckStatus,
    NavItem,
    StatusResult,
)
from datasure.utils.navigations_utils import (
    add_demo_navigation,
    demo_callout,
    demo_sidebar_help,
    page_navigation,
    show_demo_next_action,
)
from datasure.utils.onboarding_utils import (
    DemoBackcheckColumn,
    DemoColumn,
    ImportDemoInfo,
    demo_expander,
    is_demo_project,
)
from datasure.utils.prep_utils import (
    PrepActionResult,
    PrepDescriptions,
)
from datasure.utils.reapply_utils import (
    ReapplyFailure,
    format_reapply_failures,
    highlight_status,
)
from datasure.utils.ui_utils import (
    confirm_dialog,
    metric_row,
    page_header,
    queue_notice,
    section_header,
    show_queued_notices,
)
from datasure.utils.view_state import (
    ViewState,
    reset_filters_beside,
    save_selection,
    saved_selection,
)

logger = logging.getLogger(__name__)

# The dataset navigation's session state key (before ``project_nav_key``) and
# URL query parameter, and the
# settings file holding the remembered dataset (its view_state section).
PREP_NAV_KEY = "prep_nav"
DATASET_PARAM = "dataset"
PREP_SETTINGS_FILE = "prep_view_settings.json"


class PrepTables(NamedTuple):
    """A dataset's prep data and log, loaded once per run."""

    data: pl.DataFrame
    log: pl.DataFrame
    state: TableState


# === PAGE GUARDS === #

# Get project id
project_id: str = st.session_state.st_project_id

if not project_id:
    st.info(
        "Select a project from the Start page and import data. You can also create a new project from the Start page."
    )
    st.stop()

# get list of database aliases
alias_list: list[str] = duckdb_get_aliases(project_id=project_id)
# show/hide data prep page
show_prep_page_info = len(alias_list) > 0
if not show_prep_page_info:
    st.info(
        "No data prep page available. Please import data from the Import Data page or create a new project."
    )
    st.stop()

# === CONFIGURATION & DATA CONTAINERS === #


class PrepViewConfig:
    """Configuration constants for data preparation view."""

    def __init__(self):
        """Initialize configuration using PrepDescriptions."""
        self.descriptions = PrepDescriptions()

        # Get actions from prep_utils
        self.DP_ACTIONS = tuple(self.descriptions.MAIN_ACTIONS.keys())

        # Get add methods from prep_utils
        self.DP_ADD_METHODS = tuple(self.descriptions.ADD_METHODS.keys())

        # Get row deletion methods from prep_utils
        self.DP_DEL_METHODS = tuple(self.descriptions.DEL_METHODS.keys())

        # Get function categories from prep_utils
        self.DP_FUNCS = tuple(self.descriptions.FUNC_CATEGORIES.keys())

        # Get string functions from prep_utils
        self.DP_STR_FUNCS = tuple(self.descriptions.STRING_FUNCTIONS.keys())

        # Get numeric functions from prep_utils
        self.DP_NUM_FUNCS = tuple(self.descriptions.NUMERIC_FUNCTIONS.keys())

        # Get datetime functions from prep_utils
        self.DP_DATETIME_FUNCS = tuple(self.descriptions.DATETIME_FUNCTIONS.keys())

        # Functions for date-only columns
        self.DP_CONVERSION_FUNCS = tuple(self.descriptions.CONVERSION_FUNCTIONS.keys())

        # Functions for boolean columns
        self.DP_BOOLEAN_FUNCS = tuple(self.descriptions.BOOLEAN_FUNCTIONS.keys())

        # Get row conditions from prep_utils
        self.DP_ROW_CONDITIONS = tuple(self.descriptions.ROW_CONDITIONS.keys())


class TransformInputs:
    """Container for transform column input values."""

    def __init__(self):
        self.func: str | None = None
        self.old_val: str | None = None
        self.new_val: str | None = None
        self.pattern: str | None = None
        self.start: int | None = None
        self.end: int | None = None
        self.numeric_val: float | None = None


class RemoveRowsInputs:
    """Container for remove rows input values."""

    def __init__(self):
        self.method: str | None = None
        self.condition: str | None = None
        self.selected_columns: list[str] = []
        self.indexes_to_remove: list[str] = []
        self.equality_values: list = []
        self.min_value: any = None
        self.max_value: any = None
        self.pattern_value: str | None = None


# Initialize configuration
config = PrepViewConfig()

# Concat's separator choices and the separator each one stores. "Specify"
# stores the text the user typed instead.
CONCAT_SEPARATORS = {
    "None": "",
    "Space": " ",
    "Comma": ",",
    "Underscore": "_",
    "Hyphen": "-",
}
CONCAT_SPECIFY = "Specify"


def _concat_separator(choice: str, custom: str) -> str | None:
    """Return the separator a concat step stores for the user's choice.

    "Specify" keeps the typed text exactly, spaces included. An empty box
    gives None, which marks the form incomplete rather than silently
    meaning no separator.
    """
    if choice == CONCAT_SPECIFY:
        return custom or None
    return CONCAT_SEPARATORS[choice]


# === FORM VALIDATION HELPERS === #


def _has_none_values(values: list | None) -> bool:
    """Check if a list is None, empty, or contains None values."""
    return values is None or not values or any(v is None for v in values)


def _is_add_column_incomplete(prep_args: dict) -> bool:
    """Check if add column action is missing required fields."""
    if not prep_args.get("column_names"):
        return True
    method = prep_args.get("method")
    if method == PrepFunctions.concat.value:
        return (
            len(prep_args.get("source_columns") or []) < 2
            or prep_args.get("value") is None
        )
    if method == PrepFunctions.quotient.value:
        return (
            method in COL_FUNC_WITH_VALUES
            and len(prep_args.get("source_columns", [])) != 2
        )
    return method in COL_FUNC_WITH_VALUES and not prep_args.get("source_columns")


def _is_transform_column_incomplete(prep_args: dict) -> bool:
    """Check if transform column action is missing required fields."""
    if not prep_args.get("source_columns") or not prep_args.get("method"):
        return True

    value = prep_args.get("value")
    # No values required (trim, strip, lower, upper, etc.) — complete
    if not value:
        return False
    # Values required — incomplete if any are None or empty string
    return any(v is None or v == "" for v in value)


def _is_remove_row_incomplete(prep_args: dict) -> bool:
    """Check if remove row action is missing required fields."""
    method = prep_args.get("method")

    if method == PrepMethods.row_index.value:
        return not prep_args.get("value")

    if method != PrepMethods.condition.value:
        return True

    condition = prep_args.get("condition")
    value = prep_args.get("value")

    if condition in DEL_ROW_COND_SAME_TYPE:
        return _has_none_values(value)

    # DEL_COND_USE_VALS, like, not_like conditions
    conditions_requiring_value = DEL_COND_USE_VALS + (
        PrepRowConditions.like.value,
        PrepRowConditions.not_like.value,
    )
    if condition in conditions_requiring_value:
        return not value

    return False


def _is_prep_form_incomplete(action: str, prep_args: dict) -> bool:
    """Check if the preparation form is incomplete and the Add button should
    be disabled.

    Args:
        action: The selected preparation action
        prep_args: The arguments for the preparation action

    Returns
    -------
        True if the form is incomplete (Add button should be disabled), False otherwise
    """
    validators = {
        PrepActions.add_column.value: _is_add_column_incomplete,
        PrepActions.transform_column.value: _is_transform_column_incomplete,
        PrepActions.remove_column.value: lambda args: not args.get("source_columns"),
        PrepActions.remove_row.value: _is_remove_row_incomplete,
    }

    validator = validators.get(action)
    return validator(prep_args) if validator else False


# === TRANSFORM COLUMN UI HELPERS === #


def _render_string_function_inputs(
    step_index: int, inputs: TransformInputs
) -> TransformInputs:
    """Render UI inputs for string transformation functions.

    Args:
        step_index: Current step index for unique widget keys
        inputs: TransformInputs object to populate

    Returns
    -------
        Updated TransformInputs with user selections
    """
    inputs.func = st.selectbox(
        label="Select Function",
        options=config.DP_STR_FUNCS,
        key=f"st_sb_trf_func{step_index}",
    )

    if inputs.func == "replace":
        inputs.old_val = st.text_input(
            label="Enter value",
            help="Enter value to replace",
            key=f"st_sb_trf_val{step_index}",
        )
        inputs.new_val = st.text_input(
            label="Enter new value",
            help="Enter new value to replace with",
            key=f"st_sb_trf_new_val{step_index}",
        )
    elif inputs.func == "substring":
        _render_substring_inputs(step_index, inputs)
    elif inputs.func == "extract pattern":
        inputs.pattern = st.text_input(
            label="Enter pattern",
            help="Enter pattern to extract from column",
            key=f"st_sb_trf_pattern{step_index}",
        )

    return inputs


def _render_substring_inputs(step_index: int, inputs: TransformInputs) -> None:
    """Render and validate substring start/end inputs.

    Args:
        step_index: Current step index for unique widget keys
        inputs: TransformInputs object to populate with start/end values
    """
    start_col, end_col = st.columns(2)
    with start_col:
        inputs.start = st.number_input(
            label="Enter start index",
            help="Enter start index for substring",
            key=f"st_sb_trf_start{step_index}",
            value=None,
            step=1,
        )
    with end_col:
        inputs.end = st.number_input(
            label="Enter end index",
            help="Enter end index for substring",
            key=f"st_sb_trf_end{step_index}",
            value=None,
            step=1,
        )

    if inputs.start is not None and inputs.end is not None:
        if inputs.start > inputs.end:
            st.error("Start index cannot be greater than end index")
        elif inputs.start == inputs.end:
            st.error("Start index cannot be equal to end index")


def _render_numeric_function_inputs(
    step_index: int, inputs: TransformInputs
) -> TransformInputs:
    """Render UI inputs for numeric transformation functions.

    Args:
        step_index: Current step index for unique widget keys
        inputs: TransformInputs object to populate

    Returns
    -------
        Updated TransformInputs with user selections
    """
    inputs.func = st.selectbox(
        label="Select Function",
        options=config.DP_NUM_FUNCS,
        key=f"st_sb_trf_func{step_index}",
    )

    arithmetic_ops = (
        PrepOperations.add.value,
        PrepOperations.multiply.value,
        PrepOperations.subtract.value,
        PrepOperations.divide.value,
    )
    if inputs.func in arithmetic_ops:
        inputs.numeric_val = st.number_input(
            label="Enter value",
            help="Enter value to perform operation on column",
            key=f"st_sb_trf_val{step_index}",
            value=None,
        )

    return inputs


def _render_datetime_function_inputs(
    step_index: int, inputs: TransformInputs
) -> TransformInputs:
    """Render UI inputs for datetime transformation functions.

    Args:
        step_index: Current step index for unique widget keys
        inputs: TransformInputs object to populate

    Returns
    -------
        Updated TransformInputs with user selections
    """
    inputs.func = st.selectbox(
        label="Select Function",
        options=config.DP_DATETIME_FUNCS,
        key=f"st_sb_trf_func{step_index}",
    )
    return inputs


def _render_conversion_function_inputs(
    step_index: int, inputs: TransformInputs, options: tuple[str, ...]
) -> TransformInputs:
    """Render UI inputs for date-only and boolean columns.

    Args:
        step_index: Current step index for unique widget keys
        inputs: TransformInputs object to populate
        options: Conversion functions offered for the column type

    Returns
    -------
        Updated TransformInputs with user selections
    """
    inputs.func = st.selectbox(
        label="Select Function",
        options=options,
        key=f"st_sb_trf_func{step_index}",
    )
    return inputs


def _build_transform_value(inputs: TransformInputs) -> list:
    """Build the value list from transform inputs based on selected function.

    Args:
        inputs: TransformInputs containing user selections

    Returns
    -------
        List of values appropriate for the selected function
    """
    if not inputs.func:
        return []

    value_builders = {
        "replace": lambda: [inputs.old_val, inputs.new_val],
        "extract pattern": lambda: [inputs.pattern],
        "substring": lambda: [inputs.start, inputs.end],
        "add": lambda: [inputs.numeric_val],
        "multiply": lambda: [inputs.numeric_val],
        "subtract": lambda: [inputs.numeric_val],
        "divide": lambda: [inputs.numeric_val],
    }

    builder = value_builders.get(inputs.func)
    return builder() if builder else []


def _build_transform_result(column: str | None, inputs: TransformInputs) -> dict:
    """Build the result dictionary for a transform column action.

    Args:
        column: The column being transformed
        inputs: TransformInputs containing user selections

    Returns
    -------
        Dictionary with transform action parameters
    """
    source_columns = [column] if column else []
    value = _build_transform_value(inputs)

    return {
        "action": PrepActions.transform_column.value,
        "column_names": None,
        "affected_count": 0,
        "remaining_count": None,
        "value": value,
        "method": inputs.func,
        "source_columns": source_columns,
        "condition": None,
        "failed_count": 0,
        "additional_info": None,
    }


# === REMOVE ROWS UI HELPERS === #


def _get_column_options_for_condition(
    condition: str,
    all_cols: list[str],
    num_cols: list[str],
    date_cols: list[str],
    string_cols: list[str],
) -> tuple[list[str], int]:
    """Determine column options and max selections based on condition type.

    Args:
        condition: The selected row removal condition
        all_cols: List of all column names
        num_cols: List of numeric column names
        date_cols: List of datetime column names
        string_cols: List of string column names

    Returns
    -------
        Tuple of (column_options, max_selections)
    """
    max_selections = 1 if condition in DEL_ROW_COND_MAX_1 else len(all_cols)

    if condition in DEL_ROW_COND_NUM_ONLY:
        col_options = num_cols + date_cols
    elif condition in DEL_ROW_COND_STR_ONLY:
        col_options = string_cols
    else:
        col_options = all_cols

    return col_options, max_selections


def _render_equality_value_inputs(
    prep_data: pl.DataFrame,
    inputs: "RemoveRowsInputs",
    step_index: int,
) -> None:
    """Render value selection for equality conditions.

    Args:
        prep_data: The DataFrame to get unique values from
        inputs: RemoveRowsInputs object to populate
        step_index: Current step index for unique widget keys
    """
    unique_vals = prep_data[inputs.selected_columns[0]].unique().to_list()
    inputs.equality_values = st.selectbox(
        label="Select value",
        options=unique_vals,
        help="Select value to compare",
        key=f"st_sb_del_rows_cond_val{step_index}",
    )


def _validate_column_types_for_range(
    prep_data: pl.DataFrame, columns: list[str]
) -> tuple[bool, set]:
    """Validate that all selected columns have the same data type.

    Args:
        prep_data: The DataFrame to check column types
        columns: List of column names to validate

    Returns
    -------
        Tuple of (is_valid, set_of_column_types)
    """
    if not columns:
        return False, set()
    col_types = set(prep_data[columns].dtypes)
    is_valid = len(col_types) == 1
    return is_valid, col_types


def _get_unique_values_from_columns(
    prep_data: pl.DataFrame, columns: list[str]
) -> list:
    """Get sorted unique values from multiple columns.

    Args:
        prep_data: The DataFrame to get values from
        columns: List of column names

    Returns
    -------
        Sorted list of unique values across all specified columns
    """
    value_options = []
    for col in columns:
        value_options.extend(prep_data[col].unique().to_list())
    return sorted(v for v in value_options if v is not None)


def _render_range_value_inputs(
    prep_data: pl.DataFrame,
    inputs: "RemoveRowsInputs",
    step_index: int,
) -> None:
    """Render min/max value selection for range conditions.

    Args:
        prep_data: The DataFrame to get unique values from
        inputs: RemoveRowsInputs object to populate
        step_index: Current step index for unique widget keys
    """
    is_valid, col_types = _validate_column_types_for_range(
        prep_data, inputs.selected_columns
    )
    disable_inputs = not is_valid

    if not is_valid and col_types:
        st.error(
            "All selected columns must be of the same type for this condition. "
            f"You have selected the following types: {', '.join(str(ct) for ct in col_types)}"
        )

    value_options = _get_unique_values_from_columns(prep_data, inputs.selected_columns)

    inputs.min_value = st.selectbox(
        label="Select minimum value",
        options=value_options,
        help="Select minimum value to compare",
        key=f"st_sb_del_rows_cond_val_min{step_index}",
        disabled=disable_inputs,
    )
    inputs.max_value = st.selectbox(
        label="Select maximum value",
        options=value_options,
        help="Select maximum value to compare",
        key=f"st_sb_del_rows_cond_val_max{step_index}",
        disabled=disable_inputs,
    )


def _render_pattern_value_inputs(
    inputs: "RemoveRowsInputs",
    step_index: int,
) -> None:
    """Render pattern input for like/not like conditions.

    Args:
        inputs: RemoveRowsInputs object to populate
        step_index: Current step index for unique widget keys
    """
    inputs.pattern_value = st.text_input(
        label="Enter pattern",
        help="Enter pattern to match. You can use regular expressions",
        key=f"st_sb_del_rows_cond_val{step_index}",
    )


def _build_remove_rows_value(inputs: "RemoveRowsInputs") -> list | str | None:
    """Build the value field from remove rows inputs.

    Args:
        inputs: RemoveRowsInputs containing user selections

    Returns
    -------
        The appropriate value based on method and condition
    """
    if inputs.method == PrepMethods.row_index.value and inputs.indexes_to_remove:
        return inputs.indexes_to_remove

    if inputs.method != PrepMethods.condition.value or not inputs.condition:
        return None

    if not inputs.selected_columns:
        return None

    if inputs.condition in DEL_COND_USE_VALS:
        return inputs.equality_values
    elif inputs.condition in DEL_ROW_COND_SAME_TYPE:
        return [inputs.min_value, inputs.max_value]
    elif inputs.condition in (
        PrepRowConditions.like.value,
        PrepRowConditions.not_like.value,
    ):
        return inputs.pattern_value

    return None


def _build_remove_rows_result(inputs: "RemoveRowsInputs") -> dict:
    """Build the result dictionary for a remove rows action.

    Args:
        inputs: RemoveRowsInputs containing user selections

    Returns
    -------
        Dictionary with remove rows action parameters
    """
    value = _build_remove_rows_value(inputs)

    source_columns = (
        inputs.selected_columns
        if inputs.method == PrepMethods.condition.value and inputs.selected_columns
        else []
    )
    condition = (
        inputs.condition
        if inputs.method == PrepMethods.condition.value and inputs.condition
        else None
    )

    return {
        "action": PrepActions.remove_row.value,
        "column_names": None,
        "affected_count": 0,
        "remaining_count": None,
        "value": value,
        "method": inputs.method,
        "source_columns": source_columns,
        "condition": condition,
        "failed_count": None,
        "additional_info": None,
    }


# === PREP STEP HANDLER === #


class PrepStepHandler:
    """Handles data preparation step operations."""

    def __init__(self, prep_data: pl.DataFrame | pd.DataFrame, step_index: int):
        self.prep_data = prep_data
        self.step_index = step_index
        df_columns: ColumnByType = get_df_columns(self.prep_data)
        self.all_cols: list[str] = df_columns.all_columns
        self.string_cols: list[str] = df_columns.string_columns
        self.num_cols: list[str] = df_columns.numeric_columns
        self.date_cols: list[str] = df_columns.datetime_columns

    def add_column_handler(self) -> dict | None:
        """Handle adding new column UI and logic."""
        dp_prep_add_col = st.text_input(
            label="Enter column name",
            help="Enter name of new column to add",
            key=f"st_sb_add_col{self.step_index}",
        )

        if dp_prep_add_col:
            # select method to add column
            dp_prep_add_col_med = st.selectbox(
                label="Select Method",
                options=config.DP_ADD_METHODS,
                key=f"st_sb_add_col_method{self.step_index}",
                help="Select method to add new column",
            )

            if dp_prep_add_col_med == PrepFunctions.constant.value:
                dp_prep_add_val = st.text_input(
                    label="Enter value",
                    help="Enter value to add to new column",
                    key=f"st_sb_add_val{self.step_index}",
                )

            elif dp_prep_add_col_med == PrepFunctions.concat.value:
                dp_prep_add_col_select, dp_prep_add_val = self._concat_inputs()

            elif dp_prep_add_col_med in COL_FUNC_WITH_VALUES:
                if dp_prep_add_col_med in [
                    PrepFunctions.quotient.value,
                    PrepFunctions.diff.value,
                ]:
                    max_selections = 2
                else:
                    max_selections = len(self.num_cols)

                dp_prep_add_col_select = st.multiselect(
                    label="Select column",
                    options=self.num_cols,
                    key=f"st_sb_add_col_select{self.step_index}",
                    max_selections=max_selections,
                )

            # define custom message values
            value = (
                dp_prep_add_val
                if dp_prep_add_col_med
                in (PrepFunctions.constant.value, PrepFunctions.concat.value)
                else None
            )
            source_columns = (
                dp_prep_add_col_select
                if dp_prep_add_col_med in COL_FUNC_WITH_VALUES
                else []
            )

            return {
                "action": PrepActions.add_column.value,
                "column_names": dp_prep_add_col,
                "affected_count": None,
                "remaining_count": self.prep_data.shape[1] + 1,
                "value": value,
                "method": dp_prep_add_col_med,
                "source_columns": source_columns,
                "condition": None,
                "failed_count": None,
                "additional_info": None,
            }

        return None

    def _concat_inputs(self) -> tuple[list[str], str | None]:
        """Render concat's column picker and separator choice.

        Only text columns are offered: other columns are converted with the
        "to string" transform first. The selection order is the join order.

        Returns
        -------
            The selected columns and the separator to store, or None when
            "Specify" is chosen with an empty box.
        """
        columns = st.multiselect(
            label="Select columns to join",
            options=self.string_cols,
            key=f"st_sb_add_col_concat_select{self.step_index}",
            help="Columns are joined in the order you select them. Only text "
            "columns are listed: convert other columns with the 'to string' "
            "transform first.",
        )
        choice = st.selectbox(
            label="Separator",
            options=(*CONCAT_SEPARATORS, CONCAT_SPECIFY),
            key=f"st_sb_add_col_concat_sep{self.step_index}",
            help="Text placed between joined values",
        )
        custom = ""
        if choice == CONCAT_SPECIFY:
            custom = st.text_input(
                label="Enter separator",
                help="Used exactly as typed, including spaces",
                key=f"st_sb_add_col_concat_custom{self.step_index}",
            )
        return columns, _concat_separator(choice, custom)

    def transform_column_handler(self) -> dict | None:
        """Handle transform column UI and logic.

        Renders the column selection and appropriate function inputs based on
        the selected column's data type (String, Numeric, or Datetime).

        Returns
        -------
            Dictionary with transform action parameters, or None if no column selected
        """
        selected_column = st.selectbox(
            label="Select column to transform",
            options=self.all_cols,
            key=f"st_sb_trf_col{self.step_index}",
        )

        if not selected_column:
            return None

        col_type = self.prep_data[selected_column].dtype
        st.info(f"Column type: {col_type}")

        inputs = TransformInputs()
        inputs = self._render_transform_inputs_by_type(col_type, inputs)

        return _build_transform_result(selected_column, inputs)

    def _render_transform_inputs_by_type(
        self, col_type: pl.DataType, inputs: TransformInputs
    ) -> TransformInputs:
        """Render appropriate transform inputs based on column data type.

        Args:
            col_type: The Polars data type of the selected column
            inputs: TransformInputs object to populate

        Returns
        -------
            Updated TransformInputs with user selections
        """
        if col_type == pl.String:
            return _render_string_function_inputs(self.step_index, inputs)
        elif col_type == pl.Datetime:
            return _render_datetime_function_inputs(self.step_index, inputs)
        elif hasattr(col_type, "is_numeric") and col_type.is_numeric():
            return _render_numeric_function_inputs(self.step_index, inputs)
        elif col_type == pl.Date:
            return _render_conversion_function_inputs(
                self.step_index, inputs, config.DP_CONVERSION_FUNCS
            )
        elif col_type == pl.Boolean:
            return _render_conversion_function_inputs(
                self.step_index, inputs, config.DP_BOOLEAN_FUNCS
            )
        return inputs

    def remove_column_handler(self) -> dict | None:
        """Handle remove column UI and logic."""
        dp_prep_del_cols = st.multiselect(
            label="Select columns to remove",
            options=self.all_cols,
            key=f"st_sb_del_cols{self.step_index}",
        )

        return {
            "action": PrepActions.remove_column.value,
            "column_names": None,
            "affected_count": len(dp_prep_del_cols) if dp_prep_del_cols else 0,
            "remaining_count": self.prep_data.shape[1] - len(dp_prep_del_cols)
            if dp_prep_del_cols
            else self.prep_data.shape[1],
            "value": None,
            "method": None,
            "source_columns": dp_prep_del_cols if dp_prep_del_cols else [],
            "condition": None,
            "failed_count": None,
            "additional_info": None,
        }

    def remove_rows_handler(self) -> dict | None:
        """Handle remove rows UI and logic.

        Renders method selection and appropriate inputs based on the selected
        removal method (by row index or by condition).

        Returns
        -------
            Dictionary with remove rows action parameters
        """
        method = st.selectbox(
            label="Select Method",
            options=config.DP_DEL_METHODS,
            key=f"st_sb_del_rows{self.step_index}",
        )

        inputs = RemoveRowsInputs()
        inputs.method = method

        if method == PrepMethods.row_index.value:
            self._render_row_index_inputs(inputs)
        elif method == PrepMethods.condition.value:
            self._render_condition_inputs(inputs)

        return _build_remove_rows_result(inputs)

    def _render_row_index_inputs(self, inputs: "RemoveRowsInputs") -> None:
        """Render UI inputs for removing rows by index.

        Args:
            inputs: RemoveRowsInputs object to populate
        """
        row_index_text = st.text_input(
            label="Enter row index",
            help="Enter row index to remove eg. 1, 2, 3, -5, 5:-2",
            key=f"st_sb_del_rows_idx{self.step_index}",
        )
        if row_index_text:
            inputs.indexes_to_remove = row_index_text.replace(" ", "").split(",")

    def _render_condition_inputs(self, inputs: "RemoveRowsInputs") -> None:
        """Render UI inputs for removing rows by condition.

        Args:
            inputs: RemoveRowsInputs object to populate
        """
        inputs.condition = st.selectbox(
            label="Enter condition",
            options=config.DP_ROW_CONDITIONS,
            help="Enter condition for removing rows",
            key=f"st_sb_del_rows_cond{self.step_index}",
        )

        if not inputs.condition:
            return

        col_options, max_selections = _get_column_options_for_condition(
            inputs.condition,
            self.all_cols,
            self.num_cols,
            self.date_cols,
            self.string_cols,
        )

        inputs.selected_columns = st.multiselect(
            label="Select column to apply conditions to",
            options=col_options,
            help="Select column to apply conditions to, you may select multiple columns",
            key=f"st_sb_del_rows_cond_cols{self.step_index}",
            max_selections=max_selections,
        )

        if not inputs.selected_columns:
            return

        self._render_condition_value_inputs(inputs)

    def _render_condition_value_inputs(self, inputs: "RemoveRowsInputs") -> None:
        """Render value inputs based on the selected condition type.

        Args:
            inputs: RemoveRowsInputs object to populate with values
        """
        if inputs.condition in DEL_COND_USE_VALS:
            _render_equality_value_inputs(self.prep_data, inputs, self.step_index)
        elif inputs.condition in DEL_ROW_COND_SAME_TYPE:
            _render_range_value_inputs(self.prep_data, inputs, self.step_index)
        elif inputs.condition in (
            PrepRowConditions.like.value,
            PrepRowConditions.not_like.value,
        ):
            _render_pattern_value_inputs(inputs, self.step_index)


# === STEP MANAGEMENT === #


# --- Next-Run Notices ---#
# Both step handlers end in a rerun, which would clear any message rendered
# straight away, so their messages are queued and shown on the next run.
def _notice_scope(alias: str) -> str:
    """Return the queued-notice scope for a dataset on Prepare Data."""
    return f"prep_{alias}"


def _queue_reapply_failures(
    alias: str, failures: list[ReapplyFailure], context: str
) -> None:
    """Queue a warning listing reapply failures, if there are any."""
    if failures:
        queue_notice(
            _notice_scope(alias), "warning", format_reapply_failures(failures, context)
        )


def _refresh_corrected_data(alias: str) -> None:
    """Rebuild the alias's corrected table after its prep data changed."""
    # UI boundary: the prep change is already saved, so a failed rebuild is
    # reported rather than allowed to crash the page.
    try:
        failures = CorrectionProcessor(project_id).refresh_existing_corrected_data(
            alias
        )
    except Exception as e:
        logger.exception("Failed to rebuild corrected data for %s", alias)
        queue_notice(
            _notice_scope(alias),
            "error",
            f"The preparation change was saved, but corrected data could not be "
            f"rebuilt: {e!s}",
        )
        return
    _queue_reapply_failures(
        alias, failures, "Some corrections could not be reapplied to the new prep data"
    )


# --- Add Preparation Step ---#
def prep_add_step(
    prep_data: pl.DataFrame | pd.DataFrame, step_index: int, alias: str
) -> None:
    """Add a data preparation step to a dataset.

    Parameters
    ----------
    prep_data : pl.DataFrame | pd.DataFrame
        The dataset's prep data.
    step_index : int
        The dataset's position in the sorted dataset list; namespaces widget keys.
    alias : str
        The dataset.
    """
    with st.popover(":material/add: Add data prep step", width="stretch"):
        st.info("Add a new data preparation step to the log.")
        prep_handler = PrepStepHandler(prep_data, step_index)

        dp_prep_action = st.selectbox(
            label="Select Action",
            options=config.DP_ACTIONS,
            key=f"st_sb_action{step_index}",
            index=None,
            help="Select the data preparation action you want to perform",
        )

        prep_args = None

        if dp_prep_action == PrepActions.add_column.value:
            prep_args = prep_handler.add_column_handler()

        elif dp_prep_action == PrepActions.transform_column.value:
            prep_args = prep_handler.transform_column_handler()

        elif dp_prep_action == PrepActions.remove_column.value:
            prep_args = prep_handler.remove_column_handler()

        elif dp_prep_action == PrepActions.remove_row.value:
            prep_args = prep_handler.remove_rows_handler()

        if prep_args is None:
            st.warning("Please complete the form to add a new preparation step.")
            return

        disable_add = _is_prep_form_incomplete(dp_prep_action, prep_args)

        if st.button(
            label="Add",
            key=f"st_sb_add_confirm{step_index}",
            width="stretch",
            type="primary",
            help="Add the data preparation step to the log",
            disabled=disable_add,
        ):
            # apply action and re-run
            try:
                prep_apply_action(project_id, alias, PrepActionResult(**prep_args))
            except (ValidationError, OperationError) as e:
                st.error(f"Error adding preparation step: {e!s}")
            else:
                queue_notice(
                    _notice_scope(alias),
                    "success",
                    "Preparation step added successfully!",
                )
                _refresh_corrected_data(alias)
                st.rerun()


# --- Remove Preparation Step ---#
def prep_remove_step(alias: str, step_index: int) -> None:
    """Remove a data preparation step from a dataset.

    Parameters
    ----------
    alias : str
        The dataset.
    step_index : int
        The dataset's position in the sorted dataset list; namespaces widget keys.
    """
    with st.popover(":material/delete: Remove data prep step", width="stretch"):
        prep_log = duckdb_get_table(
            project_id=project_id,
            alias=f"prep_log_{alias}",
            db_name="logs",
        ).to_pandas()

        if prep_log.empty:
            st.info("No preparation steps to remove.")
        else:
            # get unique index + actions
            prep_log["action_index"] = (
                prep_log.index.astype(str)
                + " - "
                + prep_log["action"]
                + " - "
                + prep_log["description"]
            )
            unique_actions = prep_log["action_index"].unique().tolist()
            dp_prep_remove_action = st.selectbox(
                label="Select Action to Remove",
                options=unique_actions,
                key=f"st_sb_remove_action{step_index}",
                index=None,
                help="Select the action you want to remove from the log",
            )

            def _remove_prep_step(action_index: str, log=prep_log):
                """Remove a prep step from the log and reapply remaining steps."""
                action_desc = log.loc[
                    log["action_index"] == action_index, "description"
                ].values[0]
                duckdb_save_table(
                    project_id,
                    log.drop(index=log[log["action_index"] == action_index].index),
                    alias=f"prep_log_{alias}",
                    db_name="logs",
                )
                failures = prep_apply_action(project_id, alias)
                queue_notice(
                    _notice_scope(alias),
                    "success",
                    f"Action '{action_desc}' removed successfully!",
                )
                _queue_reapply_failures(
                    alias, failures, "Some preparation steps could not be reapplied"
                )
                _refresh_corrected_data(alias)

            if st.button(
                label="Remove",
                key=f"st_sb_remove_confirm{step_index}",
                width="stretch",
                type="primary",
                help="Remove the selected data preparation step from the log",
                disabled=(not dp_prep_remove_action),
            ):
                confirm_dialog(
                    "Remove data preparation step",
                    "This removes the selected preparation step from the log and "
                    "reapplies the remaining steps. This cannot be undone.",
                    confirm_label="Remove",
                    on_confirm=lambda: _remove_prep_step(dp_prep_remove_action),
                )


# === DATASET NAVIGATION === #


def seed_prep_from_raw(project_id: str, alias: str) -> PrepTables:
    """Load a dataset's prep table, copying raw data into it when needed.

    With no steps logged, prep must match raw, so it is seeded from raw. A
    zero-row prep table with steps logged is a step's result: keep it.
    Configure Checks and the replication package read columns only from
    prep, so this runs for every dataset, not just the selected one.
    """
    prep_log = duckdb_get_table(project_id, f"prep_log_{alias}", "logs")
    prep_data = duckdb_get_table(project_id, alias, "prep")
    prep_state = get_table_state(prep_data)
    if prep_state is not TableState.HAS_ROWS and prep_log.is_empty():
        prep_data = duckdb_get_table(project_id, alias, "raw")
        prep_state = get_table_state(prep_data)
        if prep_state is TableState.HAS_ROWS:
            duckdb_save_table(project_id, prep_data, alias, "prep")
    return PrepTables(prep_data, prep_log, prep_state)


def dataset_status(tables: PrepTables) -> StatusResult:
    """Return whether a dataset has rows to prepare, and why not.

    A table whose rows a step removed stays ready, so the step can be
    removed again.
    """
    if tables.state is TableState.MISSING:
        return StatusResult(
            CheckStatus.NOT_SET_UP,
            "No data imported yet. Import this dataset on the Import Data page.",
        )
    if tables.state is TableState.NO_ROWS and tables.log.is_empty():
        return StatusResult(
            CheckStatus.NOT_SET_UP,
            "This dataset has no rows. Import data with rows on the Import Data page.",
        )
    return READY


def dataset_nav_items(
    datasets: list[str], tables: dict[str, PrepTables]
) -> list[NavItem]:
    """Return one navigation item per dataset, dimmed when it has no rows.

    A status that raises gives that dataset the error status.
    """
    items = []
    for alias in datasets:
        status, reason = guarded_status(
            alias, lambda alias=alias: dataset_status(tables[alias])
        )
        items.append(
            NavItem(
                slug=alias,
                label=alias,
                icon=":material/table_chart:",
                status=status,
                reason=reason,
            )
        )
    return items


def render_dataset(item: NavItem, step_index: int, tables: PrepTables) -> None:
    """Render the preparation UI of one dataset.

    ``item`` is the dataset's navigation item, whose status was computed
    once for the navigation.
    """
    alias = item.slug
    prep_data, prep_log, prep_state = tables

    # Before the empty check: a step that removes every row still
    # queued messages for this run.
    show_queued_notices(_notice_scope(alias))

    if item.status is CheckStatus.ERROR:
        st.error(
            f"Could not check whether **{alias}** is ready. {item.reason}",
            icon=":material/error:",
        )
    elif item.dimmed:
        st.warning(item.reason)
    # A table with no rows had every row removed by a step, which must
    # stay removable, so only a missing table skips the controls.
    if prep_state is TableState.MISSING:
        return
    if prep_state is TableState.NO_ROWS and not prep_log.is_empty():
        st.warning(
            "Your preparation steps removed every row. Remove the step "
            "that caused this from the Change Log to restore the data."
        )

    # count rows, columns, number missing & percent missing
    row_count = prep_data.height
    col_count = prep_data.width
    miss_count = prep_data.null_count().sum().sum_horizontal()[0]
    total_values = row_count * col_count if row_count and col_count else 1
    miss_perc = (miss_count / total_values) * 100

    section_header("Apply Changes")

    # Demo guidance for apply changes section
    if is_demo_project():
        demo_callout(
            "Use **:material/add: Add data prep step** to transform your data. "
            f"The only required step is converting **{DemoColumn.SUBMISSIONDATE}** "
            "to datetime — "
            "all other transformations are optional.",
        )

    # create for text and form
    pt1, pt2, _ = st.columns((0.4, 0.3, 0.3))

    with pt1:
        prep_add_step(prep_data, step_index=step_index, alias=alias)

    with pt2:
        prep_remove_step(alias=alias, step_index=step_index)

    with st.container(border=True):
        section_header("Change Log")

        prep_log = duckdb_get_table(
            project_id=project_id,
            alias=f"prep_log_{alias}",
            db_name="logs",
        )

        if prep_log.is_empty():
            st.info(
                "No changes added yet. Click on the **Add**(:material/add:) button above to add a new data preparation step."
            )
        else:
            if "status" not in prep_log.columns:
                prep_log = prep_log.with_columns(pl.lit("Successful").alias("status"))

            change_log = prep_log[["action", "status", "description"]].to_pandas()
            st.dataframe(
                change_log.style.map(highlight_status, subset=["status"]),
                width="stretch",
                key=alias,
                hide_index=False,
            )

    # display preview of peppered data
    with st.container(border=True):
        # The preview's column choice is the dataset's only saved view state.
        view = ViewState(
            get_cache_path(project_id, "settings", PREP_SETTINGS_FILE), alias
        )
        with reset_filters_beside(view, vertical_alignment="center"):
            section_header("Preview Prepared Data")

        # Demo guidance for data preview
        if is_demo_project():
            demo_callout(
                f"Here's your **{alias}** data. Notice the data quality issues like missing values "
                f"({miss_perc:.1f}% missing) that the quality reports will find once "
                "you configure your checks.",
                "info",
            )

        st.divider()

        metric_row(
            [
                ("Rows", f"{row_count:,}"),
                ("Columns", f"{col_count:,}"),
                ("Percentage missing values", f"{miss_perc:.2f}%"),
            ]
        )

        shown_columns = st.multiselect(
            "Columns to show",
            options=prep_data.columns,
            placeholder="All columns",
            **view.bind(
                f"prep_preview_columns_{step_index}",
                options=prep_data.columns,
                multi=True,
            ),
        )
        st.dataframe(
            prep_data.select(shown_columns) if shown_columns else prep_data,
            width="stretch",
            hide_index=False,
        )


# === PAGE LAYOUT === #

# -- DATA PREP PAGE --#
# Creates page for data preprocessing

# Add demo navigation and guidance
add_demo_navigation("prep_view.py", step=3)
demo_sidebar_help()

page_header(
    "Prepare Data",
    "Transform, add, and remove columns and rows to get your dataset ready for Data Quality Checks.",
)


if show_prep_page_info:
    # The step index namespaces widget keys: a dataset's position in the
    # sorted list, whichever dataset is selected.
    datasets = sorted(alias_list)
    prep_tables = {alias: seed_prep_from_raw(project_id, alias) for alias in datasets}
    prep_settings_file = get_cache_path(project_id, "settings", PREP_SETTINGS_FILE)

    # The pills sit above the dataset but are drawn after it, so a dataset
    # that fails while rendering is already marked in them.
    nav_slot = st.container()
    nav_key = project_nav_key(PREP_NAV_KEY, project_id)
    nav_state = resolve_selection(
        dataset_nav_items(datasets, prep_tables),
        key=nav_key,
        param=DATASET_PARAM,
        saved=saved_selection(prep_settings_file),
    )
    save_selection(prep_settings_file, nav_state.selected)
    selected_alias = nav_state.selected
    run_guarded(
        nav_key,
        nav_state.selected_item,
        lambda: render_dataset(
            nav_state.selected_item,
            datasets.index(selected_alias),
            prep_tables[selected_alias],
        ),
    )
    with nav_slot:
        draw_nav(nav_state, key=nav_key, param=DATASET_PARAM, label="Dataset")


# Demo next action or regular navigation
if is_demo_project():
    st.divider()

    enable_next_count = 0

    prep_log_survey: pl.DataFrame = duckdb_get_table(
        project_id=project_id,
        alias="prep_log_demo_survey",
        db_name="logs",
    )

    prep_log_backcheck: pl.DataFrame = duckdb_get_table(
        project_id=project_id,
        alias="prep_log_demo_backcheck",
        db_name="logs",
    )

    if not prep_log_survey.is_empty() and not prep_log_backcheck.is_empty():
        # check that the correct prep steps have been added
        for prep_log, date_column in (
            (prep_log_survey, DemoColumn.SUBMISSIONDATE),
            (prep_log_backcheck, DemoBackcheckColumn.SUBMISSIONDATE),
        ):
            pattern = rf'"{date_column}"\s+updated\s+using\s+string\s+to\s+datetime'
            if prep_log["description"].str.contains(pattern).any():
                enable_next_count += 1

    if enable_next_count < 2:
        demo_callout(
            "The **Configure Quality Checks** button will be enabled once you have converted "
            f"the **{DemoColumn.SUBMISSIONDATE}** column to datetime in both "
            "**demo_survey** and **demo_backcheck**. "
            "Follow the guidance at the top of the page to complete this step.",
            "warning",
        )
    else:
        demo_expander(
            "Optional: Try more data preparation features",
            ImportDemoInfo.get_info_message("proceed_to_config_info"),
            expanded=False,
        )

    show_demo_next_action(
        3,
        "st_config_checks_page",
        "Configure Quality Checks",
        disabled=enable_next_count < 2,
    )
else:
    page_navigation(
        prev={
            "page_name": st.session_state.st_import_data_page,
            "label": "← Back: Import Data",
        },
        next={
            "page_name": st.session_state.st_config_checks_page,
            "label": "Next: Configure Checks →",
        },
    )
