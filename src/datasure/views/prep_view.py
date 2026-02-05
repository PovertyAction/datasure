from enum import Enum

import pandas as pd
import polars as pl
import streamlit as st

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

# --- DEFINE CONSTANTS ---#

# --- COLUMN METHODS WITH VALUES ---#

class PrepActions(Enum):
    """Data model for preparation actions."""

    add_column: str = "add new column"
    transform_column: str = "transform column(s)"
    remove_column: str = "remove column(s)"
    remove_row: str = "remove row(s)"

class PrepMethods(Enum):
    """Data model for preparation methods."""

    row_index: str = "by row index"
    condition: str = "by condition"

class PrepFunctions(Enum):
    """Data model for preparation functions."""

    sum: str = "sum"
    diff: str = "diff"
    mean: str = "mean"
    median: str = "median"
    mode: str = "mode"
    min: str = "min"
    max: str = "max"
    std: str = "std"
    var: str = "var"
    first: str = "first"
    last: str = "last"
    count: str = "count"
    nunique: str = "nunique"
    product: str = "product"
    quotient: str = "quotient"
    index: str = "index"
    uuid: str = "uuid"
    random: str = "random"

class PrepRowConditions(Enum):
    """Data model for preparation conditions."""

    equal_to: str = "value is equal to"
    not_equal_to: str = "value is not equal to"
    greater_than: str = "value is greater than"
    less_than: str = "value is less than"
    greater_than_or_equal_to: str = "value is greater than or equal to"
    less_than_or_equal_to: str = "value is less than or equal to"
    between: str = "value is between"
    not_between: str = "value is not between"
    like: str = "value is like"
    not_like: str = "value is not like"

COL_MEDTHODS_WITH_VALUES = (
    PrepFunctions.sum,
    PrepFunctions.diff,
    PrepFunctions.mean,
    PrepFunctions.median,
    PrepFunctions.mode,
    PrepFunctions.min,
    PrepFunctions.max,
    PrepFunctions.std,
    PrepFunctions.var,
    PrepFunctions.first,
    PrepFunctions.last,
    PrepFunctions.count,
    PrepFunctions.nunique,
    PrepFunctions.product,
    PrepFunctions.quotient,
)


COL_METHODS_WITHOUT_VALUES = (
    PrepFunctions.index,
    PrepFunctions.uuid,
    PrepFunctions.random,
)

DEL_ROW_COND_MAX_1 = (
    PrepRowConditions.equal_to,
    PrepRowConditions.not_equal_to,
    PrepRowConditions.greater_than,
    PrepRowConditions.less_than,
    PrepRowConditions.greater_than_or_equal_to,
    PrepRowConditions.less_than_or_equal_to,
)

DEL_ROW_COND_NUM_ONLY = (
    PrepRowConditions.greater_than,
    PrepRowConditions.less_than,
    PrepRowConditions.greater_than_or_equal_to,
    PrepRowConditions.less_than_or_equal_to,
    PrepRowConditions.between,
    PrepRowConditions.not_between,
)

DEL_ROW_COND_STR_ONLY = (
    PrepRowConditions.like,
    PrepRowConditions.not_like,
)


DEL_COND_USE_VALS = (
    PrepRowConditions.equal_to,
    PrepRowConditions.not_equal_to,
    PrepRowConditions.greater_than,
    PrepRowConditions.less_than,
    PrepRowConditions.greater_than_or_equal_to,
)

DEL_ROW_COND_SAME_TYPE = (
    PrepRowConditions.between,
    PrepRowConditions.not_between,
)


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


# -- DATA PREP PAGE --#
# Creates page for data preprocessing

# Add demo navigation and guidance
add_demo_navigation("prep_view.py", step=3)
demo_sidebar_help()

st.title("Get Your Data Ready")
st.write(
    "Prepare your dataset for Data Quality Checks. Use these tools to transform, add and remove columns and rows in your dataset."
)

# Demo guidance
if is_demo_project():
    demo_expander(
        "Prepare Your Data for Quality Checks",
        ImportDemoInfo.get_info_message("prepare_data_info"),
        expanded=True,
    )

# Initialize configuration
config = PrepViewConfig()


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
    del_conditions = [val.value for val in DEL_ROW_COND_MAX_1]
    max_selections = 1 if condition in del_conditions else len(all_cols)

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
    inputs.equality_values = st.multiselect(
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
    elif inputs.condition in (PrepRowConditions.like, PrepRowConditions.not_like):
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
            value=0,
            step=1,
        )
    with end_col:
        inputs.end = st.number_input(
            label="Enter end index",
            help="Enter end index for substring",
            key=f"st_sb_trf_end{step_index}",
            value=0,
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

    arithmetic_ops = ("add", "multiply", "subtract", "divide")
    if inputs.func in arithmetic_ops:
        inputs.numeric_val = st.number_input(
            label="Enter value",
            help="Enter value to perform operation on column",
            key=f"st_sb_trf_val{step_index}",
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


def _build_transform_result(
    column: str | None, inputs: TransformInputs
) -> dict:
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


class PrepStepHandler:
    """Handles data preparation step operations."""

    def __init__(self, prep_data: pl.DataFrame | pd.DataFrame, step_index: int):
        self.prep_data = prep_data
        self.step_index = step_index
        self.config = PrepViewConfig()
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
                options=self.config.DP_ADD_METHODS,
                key=f"st_sb_add_col_method{self.step_index}",
                help="Select method to add new column",
            )

            if dp_prep_add_col_med == "constant":
                dp_prep_add_val = st.text_input(
                    label="Enter value",
                    help="Enter value to add to new column",
                    key=f"st_sb_add_val{self.step_index}",
                )

            elif dp_prep_add_col_med in COL_MEDTHODS_WITH_VALUES:
                if dp_prep_add_col_med in ["quotient", "diff"]:
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
            value = dp_prep_add_val if dp_prep_add_col_med == "constant" else None
            source_columns = (
                dp_prep_add_col_select
                if dp_prep_add_col_med in COL_MEDTHODS_WITH_VALUES
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
            inputs.condition, self.all_cols, self.num_cols, self.date_cols,
            self.string_cols
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
            _render_equality_value_inputs(
                self.prep_data, inputs, self.step_index
            )
        elif inputs.condition in DEL_ROW_COND_SAME_TYPE:
            _render_range_value_inputs(
                self.prep_data, inputs, self.step_index
            )
        elif inputs.condition in ("value is like", "value is not like"):
            _render_pattern_value_inputs(inputs, self.step_index)


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

        if prep_args is None:
            st.warning("Please complete the form to add a new preparation step.")
            return

        if st.button(
            label="Add",
            key=f"st_sb_add_confirm{step_index}",
            width="stretch",
            type="primary",
            help="Add the data preparation step to the log",
            disabled=(not prep_args or not dp_prep_action),
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
            st.warning("This will remove a data preparation step from the log.")
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

            # confirm removal
            dp_prep_remove_confirm = st.button(
                label="Remove",
                key=f"st_sb_remove_confirm{i}",
                width="stretch",
                type="primary",
                help="Remove the selected data preparation step from the log",
                disabled=(not dp_prep_remove_action),
            )

            if dp_prep_remove_confirm:
                # remove action from log, save log to database, and re-run
                # the entire prep log to reflect the changes
                dp_prep_remove_action_desc = prep_log.loc[
                    prep_log["action_index"] == dp_prep_remove_action, "description"
                ].values[0]

                duckdb_save_table(
                    project_id,
                    prep_log.drop(
                        index=prep_log[
                            prep_log["action_index"] == dp_prep_remove_action
                        ].index
                    ),
                    alias=f"prep_log_{label}",
                    db_name="logs",
                )

                prep_apply_action(project_id, label)
                st.success(
                    f"Action '{dp_prep_remove_action_desc}' removed successfully!"
                )

                # rerun to refresh page
                st.rerun()


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

            duckdb_save_table(
                project_id,
                prep_data,
                label,
                "prep",
            )

        # count rows, columns, number missing & percent missing
        row_count = prep_data.height
        col_count = prep_data.width
        miss_count = prep_data.null_count().sum().sum_horizontal()[0]
        total_values = row_count * col_count if row_count and col_count else 1
        miss_perc = (miss_count / total_values) * 100
        all_cols = prep_data.columns

        # display tab features
        with tab:
            st.subheader("Apply Changes:")

            # Demo guidance for apply changes section
            if is_demo_project():
                demo_callout(
                    "Optional: Use these tools to transform your data. info",
                )

            # create for text and form
            pt1, pt2, _ = st.columns((0.4, 0.3, 0.3))

            with pt1:
                prep_add_step(prep_data, step_index=i)

            with pt2:
                prep_remove_step()

            with st.container(border=True):
                st.subheader("Change Log:")

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
                st.subheader("Preview Downloaded Data")

                # Demo guidance for data preview
                if is_demo_project():
                    demo_callout(
                        f"Here's your {label} data! Notice the data quality issues like missing values ({miss_perc:.1f}% missing) "
                        "that we'll identify in the next step.",
                        "info",
                    )

                st.write("---")

                mc1, mc2, mc3 = st.columns((0.3, 0.3, 0.4))

                mc1.metric(label="Rows", value=f"{row_count:,}", border=True)
                mc2.metric(label="Columns", value=f"{col_count:,}", border=True)
                mc3.metric(
                    label="Percentage missing values",
                    value=f"{miss_perc:.2f}%",
                    border=True,
                )

                st.dataframe(prep_data, width="stretch", hide_index=False)

# Demo next action or regular navigation
if is_demo_project():
    st.write("---")

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

    if prep_log_survey.is_empty() or prep_log_backcheck.is_empty():
        demo_expander(
            "Add data preparation steps for the survey and backcheck datasets",
            ImportDemoInfo.get_info_message("add_prep_steps_info"),
            expanded=False,
        )
    else:
        demo_expander(
            "Optional: Try Data Preparation Features",
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
