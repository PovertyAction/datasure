import pandas as pd
import polars as pl
import streamlit as st

from datasure.processing.prep import prep_apply_action
from datasure.utils.dataframe_utils import get_df_info
from datasure.utils.duckdb_utils import (
    duckdb_get_aliases,
    duckdb_get_table,
    duckdb_save_table,
)
from datasure.utils.navigations import page_navigation
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

COL_MEDTHODS_WITH_VALUES = (
    "sum",
    "diff",
    "mean",
    "median",
    "mode",
    "min",
    "max",
    "std",
    "var",
    "first",
    "last",
    "count",
    "nunique",
    "product",
    "quotient",
)

COL_MEDTHODS_NO_VALUES = (
    "index",
    "uuid",
    "random",
)

DEL_ROW_COND_MAX_1 = (
    "value is equal to",
    "value is not equal to",
    "value is greater than",
    "value is less than",
    "value is greater than or equal to",
    "value is less than or equal to",
)

DEL_ROW_COND_NUM_ONLY = (
    "value is greater than",
    "value is less than",
    "value is greater than or equal to",
    "value is less than or equal to",
    "value is between",
    "value is not between",
)

DEL_ROW_COND_STR_ONLY = (
    "value is like",
    "value is not like",
)

DEL_COND_USE_VALS = (
    "value is equal to",
    "value is not equal to",
    "value is greater than",
    "value is less than",
    "value is greater than or equal to",
)

DEL_ROW_COND_SAME_TYPE = (
    "value is between",
    "value is not between",
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

st.title("Get Your Data Ready")
st.write(
    "Prepare your dataset for Data Quality Checks. Use these tools to transform, add and remove columns and rows in your dataset."
)

# Initialize configuration
config = PrepViewConfig()


class PrepStepHandler:
    """Handles data preparation step operations."""

    def __init__(self, prep_data: pl.DataFrame | pd.DataFrame, step_index: int):
        self.prep_data = prep_data
        self.step_index = step_index
        self.config = PrepViewConfig()
        self.all_cols, self.string_cols, self.num_cols, self.date_cols, _ = get_df_info(
            self.prep_data, cols_only=True
        )

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
                "action": "add new column",
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
        """Handle transform column UI and logic."""
        dp_prep_trf_col = st.selectbox(
            label="Select column to transform",
            options=self.all_cols,
            key=f"st_sb_trf_col{self.step_index}",
        )
        if dp_prep_trf_col:
            # show functions based on column type
            col_type = self.prep_data[dp_prep_trf_col].dtype
            st.info(f"Column type: {col_type}")

            # Initialize variables to avoid UnboundLocalError
            dp_prep_trf_func = None
            dp_prep_trf_old_val = None
            dp_prep_trf_new_val = None
            dp_prep_trf_pattern = None
            dp_prep_trf_start = None
            dp_prep_trf_end = None
            dp_prep_trf_val = None

            if col_type in ["object", "string"]:
                dp_prep_trf_func = st.selectbox(
                    label="Select Function",
                    options=config.DP_STR_FUNCS,
                    key=f"st_sb_trf_func{i}",
                )
                if dp_prep_trf_func == "replace":
                    dp_prep_trf_old_val = st.text_input(
                        label="Enter value",
                        help="Enter value to replace",
                        key=f"st_sb_trf_val{i}",
                    )
                    dp_prep_trf_new_val = st.text_input(
                        label="Enter new value",
                        help="Enter new value to replace with",
                        key=f"st_sb_trf_new_val{i}",
                    )
                elif dp_prep_trf_func == "substring":
                    start_col, end_col = st.columns(2)
                    with start_col:
                        dp_prep_trf_start = st.number_input(
                            label="Enter start index",
                            help="Enter start index for substring",
                            key=f"st_sb_trf_start{i}",
                            value=0,
                            step=1,
                        )
                    with end_col:
                        dp_prep_trf_end = st.number_input(
                            label="Enter end index",
                            help="Enter end index for substring",
                            key=f"st_sb_trf_end{i}",
                            value=0,
                            step=1,
                        )
                    if dp_prep_trf_start is not None and dp_prep_trf_end is not None:
                        if dp_prep_trf_start > dp_prep_trf_end:
                            st.error("Start index cannot be greater than end index")
                        elif dp_prep_trf_start == dp_prep_trf_end:
                            st.error("Start index cannot be equal to end index")

                elif dp_prep_trf_func == "extract pattern":
                    dp_prep_trf_pattern = st.text_input(
                        label="Enter pattern",
                        help="Enter pattern to extract from column",
                        key=f"st_sb_trf_pattern{i}",
                    )

            elif col_type == "int64" or col_type == "float64":
                dp_prep_trf_func = st.selectbox(
                    label="Select Function",
                    options=config.DP_NUM_FUNCS,
                    key=f"st_sb_trf_func{i}",
                )
                if dp_prep_trf_func in [
                    "add",
                    "multiply",
                    "subtract",
                    "divide",
                ]:
                    dp_prep_trf_val = st.number_input(
                        label="Enter value",
                        help="Enter value to perform operation on column",
                        key=f"st_sb_trf_val{i}",
                    )

            elif col_type == "datetime64[ns]":
                dp_prep_trf_func = st.selectbox(
                    label="Select Function",
                    options=config.DP_DATETIME_FUNCS,
                    key=f"st_sb_trf_func{i}",
                )

            source_columns = [dp_prep_trf_col] if dp_prep_trf_col else []
            if dp_prep_trf_func and dp_prep_trf_func in ["replace"]:
                value = [dp_prep_trf_old_val, dp_prep_trf_new_val]
            elif dp_prep_trf_func and dp_prep_trf_func in ["extract pattern"]:
                value = [dp_prep_trf_pattern]
            elif dp_prep_trf_func and dp_prep_trf_func in ["substring"]:
                value = [dp_prep_trf_start, dp_prep_trf_end]
            elif dp_prep_trf_func and dp_prep_trf_func in [
                "add",
                "multiply",
                "subtract",
                "divide",
            ]:
                value = [dp_prep_trf_val]
            else:
                value = []

            return {
                "action": "transform column(s)",
                "column_names": None,
                "affected_count": 0,
                "remaining_count": None,
                "value": value,
                "method": dp_prep_trf_func,
                "source_columns": source_columns,
                "condition": None,
                "failed_count": 0,
                "additional_info": None,
            }

    def remove_column_handler(self) -> dict | None:
        """Handle remove column UI and logic."""
        dp_prep_del_cols = st.multiselect(
            label="Select columns to remove",
            options=self.all_cols,
            key=f"st_sb_del_cols{i}",
        )

        return {
            "action": "remove column(s)",
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
        """Handle remove rows UI and logic."""
        indexes_to_remove = []
        dp_prep_del_rows_cond = None
        dp_prep_del_rows_cond_cols = None
        value = None
        dp_prep_del_rows = st.selectbox(
            label="Select Method",
            options=config.DP_DEL_METHODS,
            key=f"st_sb_del_rows{i}",
        )

        if dp_prep_del_rows == "by row index":
            dp_prep_del_rows_idx = st.text_input(
                label="Enter row index",
                help="Enter row index to remove eg. 1, 2, 3, -5, 5:-2",
                key=f"st_sb_del_rows_idx{i}",
            )
            if dp_prep_del_rows_idx:
                indexes_to_remove = dp_prep_del_rows_idx.replace(" ", "").split(",")

        if dp_prep_del_rows == "by condition":
            dp_prep_del_rows_cond = st.selectbox(
                label="Enter condition",
                options=config.DP_ROW_CONDITIONS,
                help="Enter condition for removing rows",
                key=f"st_sb_del_rows_cond{i}",
            )
            if dp_prep_del_rows_cond:
                if dp_prep_del_rows_cond in DEL_ROW_COND_MAX_1:
                    max_selections = 1
                else:
                    max_selections = len(all_cols)

                if dp_prep_del_rows_cond in DEL_ROW_COND_NUM_ONLY:
                    col_options = self.num_cols + self.date_cols
                elif dp_prep_del_rows_cond in DEL_ROW_COND_STR_ONLY:
                    col_options = self.string_cols
                else:
                    col_options = self.all_cols

                dp_prep_del_rows_cond_cols = st.multiselect(
                    label="Select column to apply conditions to",
                    options=col_options,
                    help="Select column to apply conditions to, you may select multiple columns",
                    key=f"st_sb_del_rows_cond_cols{i}",
                    max_selections=max_selections,
                )

                if (
                    dp_prep_del_rows_cond in DEL_COND_USE_VALS
                    and dp_prep_del_rows_cond_cols
                ):
                    # get a list of unique values in select column
                    unique_vals = (
                        prep_data[dp_prep_del_rows_cond_cols[0]].unique().tolist()
                    )
                    dp_prep_del_rows_cond_val = st.multiselect(
                        label="Select value",
                        options=sorted(unique_vals),
                        help="Select value to compare",
                        key=f"st_sb_del_rows_cond_val{i}",
                    )

                if dp_prep_del_rows_cond in DEL_ROW_COND_SAME_TYPE:
                    # check that all columns are of the same type
                    disable_inputs = True
                    col_types = (
                        prep_data[dp_prep_del_rows_cond_cols].dtypes.unique().tolist()
                    )
                    if len(col_types) > 1:
                        st.error(
                            "All selected columns must be of the same type for this condition"
                        )
                    else:
                        disable_inputs = False

                    # get a list of unique values in select columns
                    value_options = []
                    for col in dp_prep_del_rows_cond_cols:
                        value_options = prep_data[col].unique().tolist()
                    dp_prep_del_rows_cond_val_min = st.selectbox(
                        label="Select minimum value",
                        options=sorted(value_options),
                        help="Select minimum value to compare",
                        key=f"st_sb_del_rows_cond_val_min{i}",
                        disabled=disable_inputs,
                    )
                    dp_prep_del_rows_cond_val_max = st.selectbox(
                        label="Select maximum value",
                        options=sorted(value_options),
                        help="Select maximum value to compare",
                        key=f"st_sb_del_rows_cond_val_max{i}",
                        disabled=disable_inputs,
                    )

                if dp_prep_del_rows_cond in [
                    "value is like",
                    "value is not like",
                ]:
                    dp_prep_del_rows_cond_val = st.text_input(
                        label="Enter pattern",
                        help="Enter pattern to match. You can use regular expressions",
                        key=f"st_sb_del_rows_cond_val{i}",
                    )

        # get value
        if indexes_to_remove and dp_prep_del_rows == "by row index":
            value = indexes_to_remove
        elif (
            dp_prep_del_rows_cond
            and dp_prep_del_rows_cond_cols
            and dp_prep_del_rows == "by condition"
        ):
            if dp_prep_del_rows_cond in DEL_COND_USE_VALS:
                value = dp_prep_del_rows_cond_val
            elif dp_prep_del_rows_cond in DEL_ROW_COND_SAME_TYPE:
                value = [dp_prep_del_rows_cond_val_min, dp_prep_del_rows_cond_val_max]
            elif dp_prep_del_rows_cond in ["value is like", "value is not like"]:
                value = dp_prep_del_rows_cond_val
            else:
                value = None

        # get source columns
        source_columns = (
            dp_prep_del_rows_cond_cols
            if dp_prep_del_rows == "by condition" and dp_prep_del_rows_cond_cols
            else []
        )
        condition = (
            dp_prep_del_rows_cond
            if dp_prep_del_rows == "by condition" and dp_prep_del_rows_cond
            else None
        )

        return {
            "action": "remove row(s)",
            "column_names": None,
            "affected_count": 0,
            "remaining_count": None,
            "value": value,
            "method": dp_prep_del_rows,
            "source_columns": source_columns,
            "condition": condition,
            "failed_count": None,
            "additional_info": None,
        }


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

        if dp_prep_action == "add new column":
            prep_args = prep_handler.add_column_handler()

        elif dp_prep_action == "transform column(s)":
            prep_args = prep_handler.transform_column_handler()

        elif dp_prep_action == "remove column(s)":
            prep_args = prep_handler.remove_column_handler()

        elif dp_prep_action == "remove row(s)":
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
            project_id=project_id,
            alias=f"prep_log_{label}",
            db_name="logs",
            type="pd",
        )

        prep_data = duckdb_get_table(
            project_id=project_id,
            alias=label,
            db_name="prep",
            type="pd",
        )

        if prep_data.empty and prep_log.empty:
            prep_data = duckdb_get_table(
                project_id=project_id,
                alias=label,
                db_name="raw",
                type="pd",
            )

            duckdb_save_table(
                project_id,
                prep_data,
                alias=label,
                db_name="prep",
            )

        # count rows, columns, number missing & percent missing
        (
            row_count,
            col_count,
            miss_count,
            miss_perc,
            all_cols,
            _,
            _,
            _,
            _,
        ) = get_df_info(prep_data)

        # display tab features
        with tab:
            st.subheader("Apply Changes:")

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
                st.write("---")

                mc1, mc2, mc3 = st.columns((0.3, 0.3, 0.4))

                mc1.metric(label="Rows", value=f"{row_count:,}", border=True)
                mc2.metric(label="Columns", value=f"{col_count:,}", border=True)
                mc3.metric(
                    label="Percentage missing values",
                    value=f"{miss_perc:.2f}%",
                    border=True,
                )
                st.dataframe(
                    prep_data,
                    width="stretch",
                    hide_index=False,
                )

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
