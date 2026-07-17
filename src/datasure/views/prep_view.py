import logging

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
from datasure.processing import pii
from datasure.processing.prep import prep_apply_action
from datasure.utils.dataframe_utils import ColumnByType, get_df_columns
from datasure.utils.duckdb_utils import (
    duckdb_get_aliases,
    duckdb_get_table,
    duckdb_save_table,
)
from datasure.utils.navigations_utils import (
    add_demo_navigation,
    demo_callout,
    demo_sidebar_help,
    page_navigation,
    show_demo_next_action,
)
from datasure.utils.onboarding_utils import (
    ImportDemoInfo,
    demo_expander,
    is_demo_project,
)
from datasure.utils.prep_utils import (
    PrepActionResult,
    PrepDescriptions,
)
from datasure.utils.ui_utils import (
    confirm_dialog,
    metric_row,
    page_header,
    section_header,
)

logger = logging.getLogger(__name__)

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

# === FORM VALIDATION HELPERS === #


def _has_none_values(values: list | None) -> bool:
    """Check if a list is None, empty, or contains None values."""
    return values is None or not values or any(v is None for v in values)


def _is_add_column_incomplete(prep_args: dict) -> bool:
    """Check if add column action is missing required fields."""
    if not prep_args.get("column_names"):
        return True
    method = prep_args.get("method")
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
        PrepActions.redact_column.value: lambda args: not args.get("source_columns"),
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
    return sorted(value_options)


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
                if dp_prep_add_col_med == PrepFunctions.constant.value
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

    def redact_column_handler(self) -> dict | None:
        """Handle redact column UI and logic (PII masking)."""
        dp_prep_redact_cols = st.multiselect(
            label="Select columns to redact",
            options=self.all_cols,
            help=(
                "All values in the selected columns are replaced with the "
                "redaction label. Use the PII Review section above to see "
                "which columns are suspected to contain PII."
            ),
            key=f"st_sb_redact_cols{self.step_index}",
        )
        dp_prep_redact_label = st.text_input(
            label="Redaction label",
            value="*****",
            help="The label written in place of every value, e.g. [PERSON]",
            key=f"st_sb_redact_label{self.step_index}",
        )

        return {
            "action": PrepActions.redact_column.value,
            "column_names": None,
            "affected_count": len(dp_prep_redact_cols) if dp_prep_redact_cols else 0,
            "remaining_count": self.prep_data.shape[1],
            "value": [dp_prep_redact_label or "*****"] * len(dp_prep_redact_cols)
            if dp_prep_redact_cols
            else [],
            "method": None,
            "source_columns": dp_prep_redact_cols if dp_prep_redact_cols else [],
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


# --- Add Preparation Step ---#
def prep_add_step(prep_data: pl.DataFrame | pd.DataFrame, step_index: int):
    """Add a data preparation step."""
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

        elif dp_prep_action == PrepActions.redact_column.value:
            prep_args = prep_handler.redact_column_handler()

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
            prep_apply_action(project_id, label, PrepActionResult(**prep_args))

            st.success("Preparation step added successfully!")
            st.rerun()


# --- Remove Preparation Step ---#
def prep_remove_step():
    """Remove a data preparation step."""
    with st.popover(":material/delete: Remove data prep step", width="stretch"):
        prep_log = duckdb_get_table(
            project_id=project_id,
            alias=f"prep_log_{label}",
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
                key=f"st_sb_remove_action{i}",
                index=None,
                help="Select the action you want to remove from the log",
            )

            def _remove_prep_step(action_index: str, log=prep_log, alias=label):
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
                prep_apply_action(project_id, alias)
                st.success(f"Action '{action_desc}' removed successfully!")

            if st.button(
                label="Remove",
                key=f"st_sb_remove_confirm{i}",
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


# --- PII Review ---#


def _pii_model_controls(section_index: int) -> tuple[str, bool]:
    """Render language/model controls; return (language, model_installed)."""
    models = pii.installed_models()
    lang_col, status_col = st.columns((0.3, 0.7))

    with lang_col:
        language = (
            st.selectbox(
                label="Detection language",
                options=list(pii.PII_LANGUAGES),
                format_func=lambda code: pii.PII_LANGUAGES[code],
                key=f"st_pii_lang_{section_index}",
                help="Language of the survey responses, used for value scanning",
            )
            or "en"
        )

    model_name = pii.PII_MODEL_OPTIONS[language]
    model_ready = models.get(language, False)

    with status_col:
        if model_ready:
            st.caption(
                f":material/check_circle: NER model **{model_name}** installed — "
                "column names and values will both be scanned."
            )
        else:
            st.caption(
                f"NER model **{model_name}** is not installed — only column-name "
                "heuristics will run. Download the model to enable value scanning."
            )
            if st.button(
                ":material/download: Download model",
                key=f"st_pii_download_{section_index}",
            ):
                with st.spinner(f"Downloading {model_name}..."):
                    success, message = pii.download_model(language)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

    return language, model_ready


def _apply_pii_decisions_as_prep_steps(
    flags: pl.DataFrame, prep_columns: list[str], alias: str
) -> int:
    """Convert mask/drop decisions into prep actions; return steps applied."""
    mask_cols: list[str] = []
    mask_labels: list[str] = []
    drop_cols: list[str] = []
    for row in flags.iter_rows(named=True):
        if row["column"] not in prep_columns:
            continue
        if row["decision"] == "mask":
            mask_cols.append(row["column"])
            mask_labels.append(row["mask_label"] or pii.DEFAULT_MASK)
        elif row["decision"] == "drop":
            drop_cols.append(row["column"])

    steps = 0
    if mask_cols:
        prep_apply_action(
            project_id,
            alias,
            PrepActionResult(
                action=PrepActions.redact_column.value,
                source_columns=mask_cols,
                value=mask_labels,
            ),
        )
        steps += 1
    if drop_cols:
        prep_apply_action(
            project_id,
            alias,
            PrepActionResult(
                action=PrepActions.remove_column.value,
                source_columns=drop_cols,
            ),
        )
        steps += 1
    return steps


def pii_review_section(prep_data: pl.DataFrame, alias: str, section_index: int) -> None:
    """Render the PII Review section for one dataset tab."""
    with st.container(border=True):
        section_header("PII Review", icon=":material/shield:")
        st.caption(
            "Scan this dataset for columns and values suspected to contain "
            "personally identifiable information (PII), then decide per column: "
            "**mask** (replace values with a label), **hash** (salted "
            "pseudonyms — deterministic tokens that keep categorical analysis "
            "working), **code** (readable category codes like VILLAGE_001), "
            "**drop** (remove the column), or **keep**. Mask and drop can be "
            "applied as prep steps; hash and code are applied at export time."
        )

        language, model_ready = _pii_model_controls(section_index)

        if st.button(
            ":material/search: Scan for PII",
            key=f"st_pii_scan_{section_index}",
            type="secondary",
        ):
            with st.spinner("Scanning for PII..."):
                try:
                    new_flags = pii.run_pii_scan(
                        prep_data, language=language, use_value_scan=model_ready
                    )
                    merged = pii.merge_with_existing(
                        new_flags, pii.load_pii_flags(project_id, alias)
                    )
                    pii.save_pii_flags(project_id, alias, merged)
                    st.success(
                        f"Scan complete — {merged.height} column(s) flagged."
                        if merged.height
                        else "Scan complete — no columns flagged."
                    )
                except Exception as e:
                    # UI boundary: a failed scan must not crash the page.
                    logger.exception("PII scan failed for alias %s", alias)
                    st.error(f"PII scan failed: {e}")

        flags = pii.load_pii_flags(project_id, alias)
        if flags.is_empty():
            st.info(
                "No PII flags yet. Click **Scan for PII** to check column names"
                + (" and values." if model_ready else ".")
            )
            return

        edited = st.data_editor(
            flags,
            column_config={
                "column": st.column_config.TextColumn("Column"),
                "source": st.column_config.TextColumn(
                    "Flagged by", help="Detection pass that flagged this column"
                ),
                "entity_type": st.column_config.TextColumn("Entity"),
                "hit_rate": st.column_config.NumberColumn("Hit rate", format="%.2f"),
                "sample_matches": st.column_config.TextColumn("Sample flagged values"),
                "decision": st.column_config.SelectboxColumn(
                    "Decision", options=list(pii.FLAG_DECISIONS), required=True
                ),
                "mask_label": st.column_config.TextColumn(
                    "Mask label", help="Label written in place of masked values"
                ),
                "scanned_at": None,
            },
            disabled=["column", "source", "entity_type", "hit_rate", "sample_matches"],
            hide_index=True,
            width="stretch",
            key=f"st_pii_editor_{section_index}",
        )

        save_col, apply_col = st.columns(2)
        with save_col:
            if st.button(
                "Save decisions",
                key=f"st_pii_save_{section_index}",
                width="stretch",
            ):
                pii.save_pii_flags(project_id, alias, pl.DataFrame(edited))
                st.success("PII decisions saved.")
        with apply_col:
            if st.button(
                "Apply mask/drop decisions as prep steps",
                key=f"st_pii_apply_{section_index}",
                width="stretch",
                type="primary",
                help=(
                    "Masks and column drops are added to the change log below, "
                    "so they are replayable and removable like any prep step."
                ),
            ):
                try:
                    edited_flags = pl.DataFrame(edited)
                    pii.save_pii_flags(project_id, alias, edited_flags)
                    deferred = edited_flags.filter(
                        pl.col("decision").is_in(["hash", "code"])
                    ).height
                    if deferred:
                        st.info(
                            f"{deferred} hash/code decision(s) saved — they are "
                            "applied at export time on the Export Replication "
                            "Package page, not as prep steps."
                        )
                    steps = _apply_pii_decisions_as_prep_steps(
                        edited_flags, prep_data.columns, alias
                    )
                    if steps:
                        st.success(f"{steps} preparation step(s) added.")
                        st.rerun()
                    elif not deferred:
                        st.info("No mask or drop decisions to apply.")
                except Exception as e:
                    # UI boundary: surface and log, never crash the page.
                    logger.exception(
                        "Applying PII decisions failed for alias %s", alias
                    )
                    st.error(f"Applying PII decisions failed: {e}")

        st.warning(
            "De-identification is not anonymization: even with direct "
            "identifiers masked or dropped, subjects may remain identifiable "
            "through combinations of remaining variables (e.g. age, location, "
            "occupation). Review before sharing any export.",
            icon=":material/warning:",
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
    tabs = st.tabs(sorted(alias_list))
    for i, (label, tab) in enumerate(zip(sorted(alias_list), tabs, strict=False)):
        prep_log = duckdb_get_table(
            project_id,
            f"prep_log_{label}",
            "logs",
        )

        prep_data = duckdb_get_table(
            project_id,
            label,
            "prep",
        )

        if prep_data.is_empty() and prep_log.is_empty():
            prep_data = duckdb_get_table(
                project_id,
                label,
                "raw",
            )

            if not prep_data.is_empty():
                duckdb_save_table(
                    project_id,
                    prep_data,
                    label,
                    "prep",
                )

        # display tab features
        with tab:
            if prep_data.is_empty():
                st.warning(
                    "No data available to prepare. Please upload a dataset in the Import Data step."
                )
                continue

            # count rows, columns, number missing & percent missing
            row_count = prep_data.height
            col_count = prep_data.width
            miss_count = prep_data.null_count().sum().sum_horizontal()[0]
            total_values = row_count * col_count if row_count and col_count else 1
            miss_perc = (miss_count / total_values) * 100
            all_cols = prep_data.columns

            section_header("Apply Changes")

            # Demo guidance for apply changes section
            if is_demo_project():
                demo_callout(
                    "Use **:material/add: Add data prep step** to transform your data. "
                    "The only required step is converting **submissiondate** to datetime — "
                    "all other transformations are optional.",
                )

            # create for text and form
            pt1, pt2, _ = st.columns((0.4, 0.3, 0.3))

            with pt1:
                prep_add_step(prep_data, step_index=i)

            with pt2:
                prep_remove_step()

            pii_review_section(prep_data, label, section_index=i)

            with st.container(border=True):
                section_header("Change Log")

                prep_log: pl.DataFrame = duckdb_get_table(
                    project_id=project_id,
                    alias=f"prep_log_{label}",
                    db_name="logs",
                )

                if prep_log.is_empty():
                    st.info(
                        "No changes added yet. Click on the **Add**(:material/add:) button above to add a new data preparation step."
                    )
                else:
                    prep_logs_mod = st.dataframe(
                        prep_log[["action", "description"]],
                        width="stretch",
                        key=label,
                        hide_index=False,
                    )

            # display preview of peppered data
            with st.container(border=True):
                section_header("Preview Prepared Data")

                # Demo guidance for data preview
                if is_demo_project():
                    demo_callout(
                        f"Here's your **{label}** data. Notice the data quality issues like missing values "
                        f"({miss_perc:.1f}% missing) that we'll identify in **Configure Quality Checks**.",
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

                st.dataframe(prep_data, width="stretch", hide_index=False)

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
        pattern = r'"submissiondate"\s+updated\s+using\s+string\s+to\s+datetime'
        if prep_log_survey["description"].str.contains(pattern).any():
            enable_next_count += 1

        if prep_log_backcheck["description"].str.contains(pattern).any():
            enable_next_count += 1

    if enable_next_count < 2:
        demo_callout(
            "The **Configure Quality Checks** button will be enabled once you have converted "
            "the **submissiondate** column to datetime in both **demo_survey** and **demo_backcheck**. "
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
