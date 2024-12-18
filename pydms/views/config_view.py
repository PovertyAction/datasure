import pandas as pd
import streamlit as st

st.title("Configure Checks")
st.markdown("Add a page for each dataset you want to check")

if "config_tabs" not in st.session_state:
    st.session_state.config_pages = ""

alias_list = list(filter(None, st.session_state.alias_list))

add_page, check_pages = st.columns((0.35, 0.65))

with add_page:  # noqa: SIM117
    with st.container(border=True):
        new_page_name = st.text_input("Page Name")
        new_page_data = st.selectbox(
            label="Select Dataset", options=alias_list, index=None
        )

        if new_page_data:
            # get index for the dataset
            row_num = alias_list.index(new_page_data)

            # get list of columns in the selected dataset
            all_cols = st.session_state[f"prepped_data{row_num}"].columns
            # get list if all date columns
            all_date_cols = (
                st.session_state[f"prepped_data{row_num}"]
                .select_dtypes(include=["datetime64"])
                .columns
            )

            if new_page_data:
                new_page_key = st.selectbox(
                    label="Select KEY column*:",
                    options=all_cols,
                    help="Select dataset unique identifier column",
                )

                new_page_id = st.selectbox(
                    label="Select Survey ID column*:",
                    options=all_cols,
                    help="Select survey ID column",
                )
                new_page_enum = st.selectbox(
                    label="Select Enumerator column:",
                    options=all_cols,
                    help="Select enumerator column",
                )
                new_page_date = st.selectbox(
                    label="Select Survey Date",
                    options=all_date_cols,
                    help="Select date column",
                )

                new_page_tracking_data = st.selectbox(
                    label="Select Tracking Dataset", options=alias_list, index=None
                )

        submit_button = st.button(
            "Add Page",
            key="submit_button",
            type="primary",
            use_container_width=True,
            disabled=not new_page_name or not new_page_data,
        )


with check_pages:  # noqa: SIM117
    with st.container(border=True):
        try:
            st.session_state.config_pages = pd.read_json(
                "cache/pyDMS_config_tabs_cache.json"
            )

        except Exception:
            st.session_state.config_pages = pd.DataFrame(
                columns=[
                    "Page Name",
                    "Data",
                    "Tracking Data",
                    "KEY",
                    "ID",
                    "Enumerator",
                    "Date",
                ]
            )

        check_page_mod = st.data_editor(
            data=st.session_state.config_pages,
            use_container_width=True,
            num_rows="dynamic",
        )

        # Save configuration File
        save_check_config = st.button(
            "Save setting", type="secondary", key="save_check_config_key"
        )

        if save_check_config:
            check_page_mod.to_json("cache/pyDMS_config_tabs_cache.json")

            for i in range(len(st.session_state.config_pages)):
                page_num = i + 1
                st.session_state[f"config_page_{page_num}"] = (
                    st.session_state.config_pages["Page Name"][i]
                )
                st.session_state[f"show_checks_page_{page_num}"] = True

# load existing pages


if submit_button:
    if new_page_name == "":
        st.warning("Please enter a name for the new check page")
    elif new_page_data == "":
        st.warning("Please select a dataset for the new check page")

    new_page = pd.DataFrame(
        data=[
            [
                new_page_name,
                new_page_data,
                new_page_tracking_data,
                new_page_key,
                new_page_id,
                new_page_enum,
                new_page_date,
            ]
        ],
        columns=[
            "Page Name",
            "Data",
            "Tracking Data",
            "KEY",
            "ID",
            "Enumerator",
            "Date",
        ],
    )

    config_pages = pd.concat(
        [st.session_state.config_pages, new_page], ignore_index=True
    )

    config_pages.to_json("cache/pyDMS_config_tabs_cache.json")
