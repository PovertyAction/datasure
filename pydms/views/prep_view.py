import pandas as pd
import streamlit as st
from src.processing import prep_load_log

# -- DEFINE CONSTANTS FOR DATA PREP --#

# Data prep actions
DP_ACTIONS: tuple = (
    "transform column(s)",
    "add column",
    "delete column(s)",
    "delete row(s)",
)

# Methods for deleting rows
DP_DEL_METHODS: tuple = ("by row index", "by condition")

DP_FUNCS: tuple = ("string", "numeric", "date")

DP_STR_FUNCS: tuple = (
    "substr",
    "subinstr",
    "strip",
    "lower",
    "upper",
    "sting to number",
    "string to date",
    "str to datetime",
    "extract pattern",
    "get dummies",
)

DP_NUM_FUNCS: tuple = (
    "add",
    "multiple",
    "subtract",
    "divide",
    "number to string",
    "string to date",
    "string to datetime",
    "extract pattern",
)

DP_DATETIME_FUNCS: tuple = ("day", "week", "month", "year", "second", "minute", "hour")

# -- DATA PREP PAGE --#
# Creates page for data preprocessing

st.title("Prepare Data")
st.markdown("Make necessary adjustments to data before check")

# Get list of dataset alias
alias_list: list[str] = list(filter(None, st.session_state.alias_list))
alias_index: list[int] = st.session_state.alias_list_index

# create new tab for each dataset
tabs = st.tabs(alias_list)

for i, (label, tab) in enumerate(zip(alias_list, tabs)):
    # get index for the dataset
    if i < sum(alias_index[0:1]):
        d_i = st.session_state["scto_alias_list"].index(label)
        data_name = f"scto_raw_data{d_i}"
    elif i < sum(alias_index[0:2]):
        d_i = st.session_state["azure_alias_list"].index(label)
        data_name = f"azure_raw_data{d_i}"
    elif i < sum(alias_index[0:3]):
        d_i = st.session_state["local_alias_list"].index(label)
        data_name = f"local_raw_data{d_i}"
    else:
        d_i = st.session_state["script_alias_list"].index(label)
        data_name = f"script_raw_data{d_i}"

    # save a copy of the raw dataset as the initial prepped dataset
    st.session_state[f"prepped_data{i}"] = st.session_state[f"{data_name}"].copy()

    # count rows, columns, number missing & percent missing
    row_count: int = len(st.session_state[f"prepped_data{i}"].index)
    col_count: int = len(st.session_state[f"prepped_data{i}"].columns)
    miss_count: int = st.session_state[f"prepped_data{i}"].isnull().sum().sum()
    miss_perc: float = round((miss_count / (row_count * col_count)) * 100, 2)

    # collate all string columns in dataset
    string_cols = (
        st.session_state[f"prepped_data{i}"].select_dtypes(include=["object"]).columns
    )
    all_cols = st.session_state[f"prepped_data{i}"].columns

    # display tab features
    with tab:
        # create columns for change log (& actions) & data view
        prep_task_col, prep_log_view_col = st.columns((0.3, 0.7))

        # populate actions and change log
        with prep_task_col, st.container(border=True):
            st.subheader("Apply Changes:")
            st.write("---")

            # create a popver box to accept inputs for new prep actions
            with st.popover(
                ":material/add: Add data prep step", use_container_width=True
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

                    dp_prep_add_col_val = st.text_input(
                        label="Enter value",
                        help="Enter value to populate new column",
                        key=f"st_sb_add_col_val{i}",
                    )

                # selectbox for transforming columns functions
                if dp_action in ["transform column(s)"]:
                    # select column to transform
                    dp_prep_trf_col = st.selectbox(
                        label="Select column to transform",
                        options=st.session_state[f"prepped_data{i}"].columns,
                        key=f"st_sb_trf_col{i}",
                    )

                    if dp_prep_trf_col:
                        # show functions based on column type
                        col_type = st.session_state[f"prepped_data{i}"][
                            dp_prep_trf_col
                        ].dtype
                        st.write(f"Column type: {col_type}")
                        if col_type == "object":
                            dp_prep_trf_func = st.selectbox(
                                label="Select Function",
                                options=DP_STR_FUNCS,
                                key=f"st_sb_trf_func{i}",
                            )
                        elif col_type == "int64" or col_type == "float64":
                            dp_prep_trf_func = st.selectbox(
                                label="Select Function",
                                options=DP_NUM_FUNCS,
                                key=f"st_sb_trf_func{i}",
                            )
                        elif col_type == "datetime64":
                            dp_prep_trf_func = st.selectbox(
                                label="Select Function",
                                options=DP_DATETIME_FUNCS,
                                key=f"st_sb_trf_func{i}",
                            )

                # selectbox (multi) for deleting column functions
                if dp_action in ["delete column(s)"]:
                    dp_prep_del_cols = st.multiselect(
                        label="Select columns to delete",
                        options=string_cols,
                        key=f"st_sb_del_cols{i}",
                    )

                # selectbox (multi) for deleting rows functions
                if dp_action in ["delete row(s)"]:
                    dp_prep_del_rows = st.selectbox(
                        label="Select Method",
                        options=DP_DEL_METHODS,
                        key=f"st_sb_del_rows{i}",
                    )

                    if dp_prep_del_rows == "by row index":
                        dp_prep_del_rows_idx = st.text_input(
                            label="Enter row index",
                            help="Enter row index to delete eg. 1, 2, 3, -5, 5:-2",
                            key=f"st_sb_del_rows_idx{i}",
                        )

                    if dp_prep_del_rows == "by condition":
                        dp_prep_del_rows_cond = st.text_input(
                            label="Enter condition",
                            help="Enter condition to delete rows eg. 'column_name == value'",
                            key=f"st_sb_del_rows_cond{i}",
                        )

                # apply button
                dp_prep_apply_btn = st.button(
                    label="Apply",
                    key=f"st_sb_del_button{i}",
                    use_container_width=True,
                )

                # if apply button is clicked add new action to log
                if dp_prep_apply_btn:
                    st.session_state[f"prep_log{i}"] = st.session_state.get(
                        f"prep_log{i}", []
                    )

                    new_file = pd.DataFrame(
                        data=[[dp_action, f"Applied {dp_action}"]],
                        columns=["action", "description"],
                    )

                    st.session_state.local_files = pd.concat(
                        [st.session_state[f"prep_log{i}"], new_file],
                        ignore_index=True,
                    )

                    # save log to file
                    log = pd.DataFrame(st.session_state[f"prep_log{i}"])
                    log.to_json(f"cache/pyDMS_prep_cache_{label}.json")

        with prep_log_view_col, st.container(border=True):
            st.subheader("Change Log:")
            st.write("---")

            st.session_state[f"prep_log{i}"] = prep_load_log(label)

            prep_logs_mod = st.data_editor(
                data=st.session_state[f"prep_log{i}"],
                use_container_width=True,
                num_rows="dynamic",
                key=label,
            )

        # display preview of peppered data
        with st.container(border=True):
            st.subheader("Preview Downloaded Data")
            st.write("---")

            mc1, mc2, mc3 = st.columns((0.3, 0.3, 0.4))

            mc1.metric(label="Rows", value=row_count)
            mc2.metric(label="Columns", value=col_count)
            mc3.metric(label="Missing Values", value=f"{miss_perc}%")

            st.dataframe(st.session_state[f"prepped_data{i}"])
