import streamlit as st

from src.processing import prep_apply_action, prep_load_log
from src.utils import (
    duckdb_get_aliases,
    duckdb_get_table,
    duckdb_save_table,
    get_df_info,
)

# -- DEFINE CONSTANTS FOR DATA PREP --#

# Data prep actions
DP_ACTIONS: tuple = (
    "transform column(s)",
    "add column",
    "remove column(s)",
    "remove row(s)",
)

DP_ADD_METHODS: tuple = (
    "constant",
    "sum",
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
    "diff",
    "quotient",
)

# Methods for deleting rows
DP_DEL_METHODS: tuple = ("by row index", "by condition")

DP_FUNCS: tuple = ("string", "numeric", "date")

DP_STR_FUNCS: tuple = (
    "substring",
    "replace",
    "strip",
    "lower",
    "upper",
    "string to number",
    "string to date",
    "string to datetime",
    "extract pattern",
    "get dummies",
)

DP_NUM_FUNCS: tuple = (
    "add",
    "multiple",
    "subtract",
    "divide",
    "round",
    "floor",
    "ceil",
    "abs",
)

DP_DATETIME_FUNCS: tuple = (
    "day",
    "week",
    "month",
    "quarter" "year",
    "second",
    "minute",
    "hour",
)

DP_ROW_CONDITIONS: tuple = (
    "value is missing",
    "value is not missing",
    "value is equal to",
    "value is not equal to",
    "value is greater than",
    "value is less than",
    "value is greater than or equal to",
    "value is less than or equal to",
    "value is between",
    "value is not between",
    "value is like",
    "value is not like",
)

# -- DATA PREP PAGE --#
# Creates page for data preprocessing

st.title("Prepare Data")
st.markdown("Make necessary adjustments to data before check")

# Get list of dataset alias
project_id: str = st.session_state.st_project_id
alias_list: list[str] = duckdb_get_aliases(project_id)

# show/hide data prep page

show_prep_page_info = False

try:
    tabs = st.tabs(sorted(alias_list))
    show_prep_page_info = True
except Exception as e:  # noqa: F841
    st.info(
        "No data available to prepare. Load a dataset from the import page to continue."
    )

if show_prep_page_info:
    for i, (label, tab) in enumerate(zip(alias_list, tabs, strict=False)):
        prep_log = duckdb_get_table(
            project_id=project_id,
            alias=f"prep_log_{label}",
            db_name="logs",
        ).to_pandas()

        prep_data = duckdb_get_table(
            project_id=project_id,
            alias=label,
            db_name="prep",
        ).to_pandas()

        if prep_data.empty:
            prep_data = duckdb_get_table(
                project_id=project_id,
                alias=label,
                db_name="raw",
            ).to_pandas()

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
            string_cols,
            num_cols,
            date_cols,
        ) = get_df_info(prep_data)

        # display tab features
        with tab:
            st.subheader("Apply Changes:")

            # create for text and form
            pt1, _ = st.columns((0.4, 0.6))

            # create a popver box to accept inputs for new prep actions
            with (
                pt1,
                st.popover(
                    ":material/add: Add data prep step", use_container_width=True
                ),
            ):
                st.markdown("*Add new data preparation steps*")

                # selectbox for action type
                dp_action = st.selectbox(
                    label="Select Action:",
                    options=DP_ACTIONS,
                    key=f"st_sb_dp_action{i}",
                )

                # selectbox for adding new columns functions
                if dp_action in ["add column"]:
                    dp_prep_add_col = st.text_input(
                        label="Enter column name",
                        help="Enter name of new column to add",
                        key=f"st_sb_add_col{i}",
                    )

                    if dp_prep_add_col:
                        # select method for adding new column
                        dp_prep_add_method = st.selectbox(
                            label="Select Method",
                            options=DP_ADD_METHODS,
                            key=f"st_sb_add_method{i}",
                        )

                        if dp_prep_add_method == "constant":
                            dp_prep_add_val = st.text_input(
                                label="Enter value",
                                help="Enter value to add to new column",
                                key=f"st_sb_add_val{i}",
                            )
                            description = f"Add column '{dp_prep_add_col}' with constant value '{dp_prep_add_val}'"
                        elif dp_prep_add_method in [
                            "sum",
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
                            "diff",
                        ]:
                            if dp_prep_add_method in ["quotient", "diff"]:
                                max_selections = 2
                            else:
                                max_selections = len(num_cols)

                            dp_prep_add_col_select = st.multiselect(
                                label="Select column",
                                options=num_cols,
                                key=f"st_sb_add_col_select{i}",
                                max_selections=max_selections,
                            )
                            description = f"Add column '{dp_prep_add_col}' with {dp_prep_add_method} of column {dp_prep_add_col_select}"

                    # selectbox for transforming columns functions
                    if dp_action in ["transform column(s)"]:
                        # select column to transform
                        dp_prep_trf_col = st.selectbox(
                            label="Select column to transform",
                            options=all_cols,
                            key=f"st_sb_trf_col{i}",
                        )

                        if dp_prep_trf_col:
                            # show functions based on column type
                            col_type = prep_data[dp_prep_trf_col].dtype
                            st.info(f"Column type: {col_type}")
                            if col_type in ["object", "string"]:
                                dp_prep_trf_func = st.selectbox(
                                    label="Select Function",
                                    options=DP_STR_FUNCS,
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
                                    description = f"Transform column '{dp_prep_trf_col}' to '{dp_prep_trf_func}' by replacing '{dp_prep_trf_old_val}' with '{dp_prep_trf_new_val}'"
                                elif dp_prep_trf_func == "substring":
                                    start_col, end_col = st.columns(2)
                                    with start_col:
                                        dp_prep_trf_start = st.number_input(
                                            label="Enter start index",
                                            help="Enter start index for substring",
                                            key=f"st_sb_trf_start{i}",
                                            step=1,
                                        )
                                    with end_col:
                                        dp_prep_trf_end = st.number_input(
                                            label="Enter end index",
                                            help="Enter end index for substring",
                                            key=f"st_sb_trf_end{i}",
                                            step=1,
                                        )
                                    if dp_prep_trf_start and dp_prep_trf_end:  # noqa: SIM102
                                        if dp_prep_trf_start > dp_prep_trf_end:
                                            st.error(
                                                "Start index cannot be greater than end index"
                                            )
                                    description = f"Transform column '{dp_prep_trf_col}' to '{dp_prep_trf_func}' by extracting substring from {dp_prep_trf_start} to {dp_prep_trf_end}"
                                elif dp_prep_trf_func == "extract pattern":
                                    dp_prep_trf_pattern = st.text_input(
                                        label="Enter pattern",
                                        help="Enter pattern to extract from column",
                                        key=f"st_sb_trf_pattern{i}",
                                    )
                                    description = f"Transform column '{dp_prep_trf_col}' to '{dp_prep_trf_func}' by extracting pattern '{dp_prep_trf_pattern}'"
                                else:
                                    description = f"Transform column '{dp_prep_trf_col}' to '{dp_prep_trf_func}'"
                            elif col_type == "int64" or col_type == "float64":
                                dp_prep_trf_func = st.selectbox(
                                    label="Select Function",
                                    options=DP_NUM_FUNCS,
                                    key=f"st_sb_trf_func{i}",
                                )
                                if dp_prep_trf_func in [
                                    "add",
                                    "multiple",
                                    "subtract",
                                    "divide",
                                ]:
                                    dp_prep_trf_val = st.number_input(
                                        label="Enter value",
                                        help="Enter value to perform operation on column",
                                        key=f"st_sb_trf_val{i}",
                                    )
                                    description = f"Transform column '{dp_prep_trf_col}' to '{dp_prep_trf_func}' by {dp_prep_trf_val}"
                                else:
                                    description = f"Transform column '{dp_prep_trf_col}' to '{dp_prep_trf_func}'"
                            elif col_type == "datetime64[ns]":
                                dp_prep_trf_func = st.selectbox(
                                    label="Select Function",
                                    options=DP_DATETIME_FUNCS,
                                    key=f"st_sb_trf_func{i}",
                                )
                                description = f"Transform column '{dp_prep_trf_col}' to '{dp_prep_trf_func}'"

                    # selectbox (multi) for deleting column functions
                    if dp_action in ["remove column(s)"]:
                        dp_prep_del_cols = st.multiselect(
                            label="Select columns to remove",
                            options=string_cols,
                            key=f"st_sb_del_cols{i}",
                        )

                        description = f"remove column(s) {dp_prep_del_cols}"

                    # selectbox (multi) for deleting rows functions
                    if dp_action in ["remove row(s)"]:
                        dp_prep_del_rows = st.selectbox(
                            label="Select Method",
                            options=DP_DEL_METHODS,
                            key=f"st_sb_del_rows{i}",
                        )

                        if dp_prep_del_rows == "by row index":
                            dp_prep_del_rows_idx = st.text_input(
                                label="Enter row index",
                                help="Enter row index to remove eg. 1, 2, 3, -5, 5:-2",
                                key=f"st_sb_del_rows_idx{i}",
                            )
                            if dp_prep_del_rows_idx:
                                dp_prep_del_rows_idx_list = (
                                    dp_prep_del_rows_idx.replace(" ", "").split(",")
                                )

                                description = f"remove row(s) by index {dp_prep_del_rows_idx_list}"

                        if dp_prep_del_rows == "by condition":
                            dp_prep_del_rows_cond = st.selectbox(
                                label="Enter condition",
                                options=DP_ROW_CONDITIONS,
                                help="Enter condition for removing rows",
                                key=f"st_sb_del_rows_cond{i}",
                            )
                            if dp_prep_del_rows_cond:
                                if dp_prep_del_rows_cond in [
                                    "value is equal to",
                                    "value is not equal to",
                                    "value is greater than",
                                    "value is less than",
                                    "value is greater than or equal to",
                                    "value is less than or equal to",
                                ]:
                                    max_selections = 1
                                else:
                                    max_selections = len(all_cols)

                                if dp_prep_del_rows_cond in [
                                    "value is greater than",
                                    "value is less than",
                                    "value is greater than or equal to",
                                    "value is less than or equal to",
                                    "value is between",
                                    "value is not between",
                                ]:
                                    col_options = num_cols + date_cols
                                else:
                                    col_options = all_cols

                                dp_prep_del_rows_cond_cols = st.multiselect(
                                    label="Select column to apply conditions to",
                                    options=col_options,
                                    help="Select column to apply conditions to, you may select multiple columns",
                                    key=f"st_sb_del_rows_cond_cols{i}",
                                    max_selections=max_selections,
                                )

                                description = f"remove row(s) by condition '{dp_prep_del_rows_cond}' on columns {dp_prep_del_rows_cond_cols}"

                                if dp_prep_del_rows_cond in [  # noqa: SIM102
                                    "value is equal to",
                                    "value is not equal to",
                                    "value is greater than",
                                    "value is less than",
                                    "value is greater than or equal to",
                                    "value is less than or equal to",
                                ]:
                                    if dp_prep_del_rows_cond_cols:
                                        # get a list of unique values in select column
                                        unique_vals = (
                                            prep_data[dp_prep_del_rows_cond_cols[0]]
                                            .unique()
                                            .tolist()
                                        )
                                        dp_prep_del_rows_cond_val = st.multiselect(
                                            label="Select value",
                                            options=sorted(unique_vals),
                                            help="Select value to compare",
                                            key=f"st_sb_del_rows_cond_val{i}",
                                        )

                                        description = f"remove row(s) by condition '{dp_prep_del_rows_cond}' on columns {dp_prep_del_rows_cond_cols} with value {dp_prep_del_rows_cond_val}"

                                if dp_prep_del_rows_cond in [
                                    "value is between",
                                    "value is not between",
                                ]:
                                    # check that all columns are of the same type
                                    disable_inputs = True
                                    col_types = (
                                        prep_data[dp_prep_del_rows_cond_cols]
                                        .dtypes.unique()
                                        .tolist()
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

                                    description = f"remove row(s) by condition '{dp_prep_del_rows_cond}' on columns {dp_prep_del_rows_cond_cols} with values {dp_prep_del_rows_cond_val_min} and {dp_prep_del_rows_cond_val_max}"
                                if dp_prep_del_rows_cond in [
                                    "value is like",
                                    "value is not like",
                                ]:
                                    dp_prep_del_rows_cond_val = st.text_input(
                                        label="Enter pattern",
                                        help="Enter pattern to match. You can use regular expressions",
                                        key=f"st_sb_del_rows_cond_val{i}",
                                    )

                                    description = f"remove row(s) by condition '{dp_prep_del_rows_cond}' on columns {dp_prep_del_rows_cond_cols} with pattern '{dp_prep_del_rows_cond_val}'"

                    # apply button
                    dp_prep_apply_btn = st.button(
                        label="Apply",
                        key=f"st_sb_del_button{i}",
                        use_container_width=True,
                    )

                    # if apply button is clicked add new action to log
                    if dp_prep_apply_btn:
                        prep_apply_action(dp_action, description, i)

            with st.container(border=True):
                st.subheader("Change Log:")

                st.session_state[f"prep_log{i}"] = prep_load_log(project_id, label)

                prep_logs_mod = st.data_editor(
                    data=st.session_state[f"prep_log{i}"],
                    use_container_width=True,
                    num_rows="dynamic",
                    key=label,
                    hide_index=True,
                    disabled=["_index"],
                    column_config={
                        "action": st.column_config.TextColumn(
                            "action",
                            help="Action to be logged",
                            disabled=True,
                        ),
                        "description": st.column_config.TextColumn(
                            "description of action",
                            help="Description of action",
                            disabled=True,
                        ),
                    },
                )

                # Save configuration File
                prep_save_config = st.button(
                    label="save & re-apply changes",
                    type="secondary",
                    key=f"prep_save_config_key{i}",
                    use_container_width=True,
                )
                if prep_save_config:
                    # save form information
                    prep_config_filename = f"cache/pyDMS_prep_cache_{i}.json"
                    prep_logs_mod.to_json(prep_config_filename)
                    st.session_state[f"prep_log{i}"] = prep_logs_mod

                    prep_apply_action(index=i)
                    st.success("Configuration saved successfully!")

            # display preview of peppered data
            with st.container(border=True):
                st.subheader("Preview Downloaded Data")
                st.write("---")

                mc1, mc2, mc3 = st.columns((0.3, 0.3, 0.4))

                mc1.metric(label="Rows", value=row_count, border=True)
                mc2.metric(label="Columns", value=col_count, border=True)
                mc3.metric(
                    label="Missing Values", value=f"{miss_perc:.2f}%", border=True
                )

                if len(prep_data) > 1000:
                    st.warning("Data preview limited to 1000 rows")
                    st.dataframe(prep_data[:1000])
                else:
                    st.dataframe(prep_data)
