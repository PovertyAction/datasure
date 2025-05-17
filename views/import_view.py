import pandas as pd
import streamlit as st

from src.connectors import (
    local_add_form,
    local_load_action,
    local_load_files,
    scto_download_action,
    scto_forms_edit,
    scto_login_form,
)

# --- CONFIGURE PAGE --- #

st.set_page_config("Import Data", page_icon=":sync:", layout="wide")
st.title("Import Data")
st.markdown("Import data from multiple sources")

# --- CONFIGURE CONNECTOR TABS ---#

# create tabs for different data sources
tabs = ["SurveyCTO", "Microsoft Azure", "Local Storage", "Python Script"]
scto, azure, local, script = st.tabs(tabs)

# --- INITIALIZING GLOBAL SESSION STATES --- #


# --- SURVEYCTO CONNECTOR ---#

# initiate alias list for SurveyCTO forms
if "scto_alias_list" not in st.session_state:
    st.session_state.scto_alias_list = []

# show/hide SurveyCTO forms
if "scto_show_forms" not in st.session_state:
    st.session_state.scto_show_forms = False
# enable/disable SurveyCTO download button
if "scto_disable_download_btn" not in st.session_state:
    st.session_state.scto_disable_download_btn = True
# Show/hide preview page
if "scto_show_preview" not in st.session_state:
    st.session_state.scto_show_preview = False
if "scto_forms" not in st.session_state:
    st.session_state.scto_forms = pd.DataFrame()


with scto:
    # tab description
    st.title("Sync your SurveyCTO")
    st.markdown(
        "Enter the details required for fetching your data from the SurveyCTO server"
    )

    # server & form details
    with st.container(border=True):
        # define cols fr server and form id
        scto_server_col, scto_forms_col = st.columns((0.4, 0.6))

        with scto_server_col:
            scto_form_inputs, scto_servername, scto_username = scto_login_form()
            st.session_state.scto_forms = scto_form_inputs

        with scto_forms_col:
            if st.session_state.scto_show_forms:
                # display forms and additional functions
                scto_forms_edit(scto_servername)

    # --- DOWNLOAD DATA FROM SURVEYCTO --- #

    scto_download_btn_col, scto_download_prog_col, _ = st.columns((0.1, 0.3, 0.6))

    with st.container(border=True):
        # Get data
        with scto_download_btn_col:
            scto_download_btn = st.button(
                "Download",
                type="primary",
                key="scto_download_btn_key",
                use_container_width=True,
                disabled=st.session_state.scto_disable_download_btn,
            )

        # import data
        with scto_download_prog_col:
            if scto_download_btn:
                st.session_state.scto_forms = st.session_state.scto_forms[
                    st.session_state.scto_forms["select"] == 1
                ].reset_index()
                scto_download_action(st.session_state.scto_forms)

    # --- PREVIEW SURVEYCTO DATA --- #
    if st.session_state.scto_show_preview:
        with st.container(border=True):
            st.subheader("Preview Downloaded Data")
            st.write("---")

            scto_prev_select_col, scto_prev_mc1, scto_prev_mc2, scto_prev_mc3, _ = (
                st.columns((0.2, 0.2, 0.2, 0.2, 0.2))
            )

            st.session_state.scto_alias_list = st.session_state.scto_forms[
                "alias"
            ].tolist()

            st.session_state.alias_list_index[0] = len(st.session_state.scto_alias_list)

            with scto_prev_select_col:
                scto_preview_data = st.selectbox(
                    "Select Dataset to preview:",
                    options=st.session_state.scto_alias_list,
                )

                if scto_preview_data is not None:
                    scto_row_num = st.session_state.scto_alias_list.index(
                        scto_preview_data
                    )

                    scto_row_count: int = len(
                        st.session_state[f"scto_raw_data{scto_row_num}"].index
                    )
                    scto_col_count: int = len(
                        st.session_state[f"scto_raw_data{scto_row_num}"].columns
                    )
                    scto_miss_count: int = (
                        st.session_state[f"scto_raw_data{scto_row_num}"]
                        .isnull()
                        .sum()
                        .sum()
                    )
                    scto_miss_perc: float = round(
                        (scto_miss_count / (scto_row_count * scto_col_count)) * 100, 2
                    )

                    scto_prev_mc1.metric(label="Rows", value=scto_row_count)
                    scto_prev_mc2.metric(label="Columns", value=scto_col_count)
                    scto_prev_mc3.metric(
                        label="Missing Values", value=f"{scto_miss_perc}%"
                    )

            if scto_preview_data is not None:
                if len(st.session_state[f"scto_raw_data{scto_row_num}"]) > 1000:
                    st.warning("Data preview is limited to 1000 rows.")
                    st.dataframe(
                        st.session_state[f"scto_raw_data{scto_row_num}"][:1000]
                    )
                else:
                    st.dataframe(st.session_state[f"scto_raw_data{scto_row_num}"])


# --- LOCAL STORAGE CONNECTOR ---#

# initiate data alias list for local data
if "local_alias_list" not in st.session_state:
    st.session_state.local_alias_list = []

# show/hide local files
if "local_show_files" not in st.session_state:
    st.session_state.local_show_files = False

# show/hide files page
if "local_show_files" not in st.session_state:
    st.session_state.local_show_files = False
# show/hide preview page
if "local_show_preview" not in st.session_state:
    st.session_state.local_show_preview = False
# enable/disable load data button
if "local_disable_load" not in st.session_state:
    st.session_state.local_disable_load = False
if "local_files" not in st.session_state:
    st.session_state.local_files = local_load_files()

with local:
    # tab description
    st.title("Sync data from Local Storage")
    st.markdown("Add multiple data files from your local storage")

    # define cols adding files and added files
    local_add_col, local_show_col = st.columns((0.4, 0.6))

    with local_add_col:
        local_files = local_add_form()

    with local_show_col, st.container(border=True):
        if len(st.session_state.local_files.index) > 0:
            st.session_state.local_disable_load = False

            local_inputs_mod = st.data_editor(
                data=st.session_state.local_files,
                use_container_width=True,
                num_rows="dynamic",
            )

            # Save configuration File
            local_save_config = st.button(
                "Save setting", type="secondary", key="local_save_config_key"
            )

            if local_save_config:
                # save form information
                local_config_filename = "cache/pyDMS_local_files_cache.json"
                local_inputs_mod.to_json(local_config_filename)

                st.session_state.local_files = local_inputs_mod

                st.success("Configuration saved successfully!")

    # --- LOAD DATA FROM LOCAL STORAGE --- #

    local_load_btn_col, local_load_prog_col, _ = st.columns((0.1, 0.3, 0.6))

    with local_load_btn_col:
        # Get data
        load_local_data = st.button(
            label="Load Data",
            type="primary",
            key="local_get_data_key",
            use_container_width=True,
            disabled=st.session_state.local_disable_load,
        )

    # import data
    if load_local_data:
        with local_load_prog_col:
            local_load_action(st.session_state.local_files)

    # --- PREVIEW LOCAL DATA --- #

    if st.session_state.local_show_preview:
        with st.container(border=True):
            st.subheader("Preview Loaded Data")
            st.write("---")

            local_select_col, local_prev_mc1, local_prev_mc2, local_prev_mc3, _ = (
                st.columns((0.2, 0.2, 0.2, 0.2, 0.2))
            )

            st.session_state.local_alias_list = st.session_state.local_files[
                "alias"
            ].tolist()
            st.session_state.alias_list_index[2] = len(
                st.session_state.local_alias_list
            )

            with local_select_col:
                local_preview_data = st.selectbox(
                    "Select Dataset to preview:",
                    options=st.session_state.local_alias_list,
                )
                local_row_num = st.session_state["local_alias_list"].index(
                    local_preview_data
                )

            local_row_count: int = len(
                st.session_state[f"local_raw_data{local_row_num}"].index
            )
            local_col_count: int = len(
                st.session_state[f"local_raw_data{local_row_num}"].columns
            )
            local_miss_count: int = (
                st.session_state[f"local_raw_data{local_row_num}"].isnull().sum().sum()
            )
            local_miss_perc: float = round(
                (local_miss_count / (local_row_count * local_col_count)) * 100, 2
            )

            local_prev_mc1.metric(label="Rows", value=local_row_count)
            local_prev_mc2.metric(label="Columns", value=local_col_count)
            local_prev_mc3.metric(label="Missing Values", value=f"{local_miss_perc}%")

            st.dataframe(st.session_state[f"local_raw_data{local_row_num}"])

# --- Collate List of Data Aliases --- #

st.session_state.alias_list = (
    st.session_state.scto_alias_list + st.session_state.local_alias_list
)
