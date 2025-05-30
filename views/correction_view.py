import polars as pl
import streamlit as st

from src.processing.corrections import (
    load_corrections_log,
)

# DEFINE CONSTANTS FOR CORRECTION'

ID_CORRECTION_ACTIONS = ("modify id", "remove row")
OTHER_CORRECTION_ACTIONS = ("modify value", "remove value", "remove row")

# -- DATA CORERCTIONS PAGE --#
# Creates page for data preprocessing

st.title("Correct Data")
st.markdown("Make necessary corrections to data based on issues identified in checks.")

# Get list of dataset alias
alias_list: list[str] = list(filter(None, st.session_state.alias_list))
alias_index: list[int] = st.session_state.alias_list_index

# show/hide data prep page

show_corr_page_info = False
try:
    tabs = st.tabs(alias_list)
    show_corr_page_info = True
except:
    st.info(
        "No data available to prepare. Load a dataset from the import page to continue."
    )

if show_corr_page_info:
    for i, name in enumerate(alias_list):
        with tabs[i]:
            st.subheader(f"{name}")
    page_name = st.session_state.config_pages["Page Name"][i]
    setting_file = f"cache/pyDMS_hfc_correction_log_{page_name}.json"

    if f"prepped_data{i}" in st.session_state:
        corrected_data = pl.from_pandas(st.session_state[f"prepped_data{i}"])
    else:
        st.error(
            "No prepped data available. Please prepare the data before making corrections."
        )

    # load corrections log
    id_correction_log = load_corrections_log(setting_file, "id")

    st.subheader("ID Duplicates Corrections")
    st.write(
        "Correct ID duplicates by either modifying the ID or removing the row. "
        "Select the action from the dropdown and provide the necessary input."
    )

    st.data_editor(
        id_correction_log,
        use_container_width=True,
        key=f"corrected_data_{i}",
        num_rows="dynamic",
    )

    st.write("---")
    st.subheader("Other Corrections")
    st.write(
        "Correct other issues by modifying the value, removing the value, or removing the row. "
        "Select the action from the dropdown and provide the necessary input."
    )

    # load other corrections log
    other_correction_log = load_corrections_log(setting_file, "other")

    row_count: int = corrected_data.shape[0]
    col_count: int = corrected_data.shape[1]
    # calculate missing values percentage
    miss_count = corrected_data.select(pl.all().is_null().sum())
    miss_count = miss_count.with_columns(
        sum_of_missing_values=pl.sum_horizontal(pl.all())
    )
    miss_perc = round(
        (miss_count["sum_of_missing_values"][0] / (row_count * col_count)) * 100, 2
    )

    # display preview of peppered data
    with st.container(border=True):
        st.subheader("Preview Corrected Data")
        st.write("---")

        mc1, mc2, mc3 = st.columns((0.3, 0.3, 0.4))

        mc1.metric(label="Rows", value=row_count)
        mc2.metric(label="Columns", value=col_count)
        mc3.metric(label="Missing Values", value=f"{miss_perc}%")

        # display data
        st.dataframe(corrected_data, use_container_width=True)
