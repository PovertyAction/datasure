import polars as pl
import streamlit as st
from millify import prettify

from src.connectors import (
    get_import_cache,
    local_add_form,
    local_load_action,
    scto_add_form,
    scto_import_data,
    scto_login_form,
)
from src.utils import get_duckdb_table

# --- define project ID --- #
project_id = st.session_state.st_project_id


# add session state for raw dataset list
if "st_raw_dataset_list" not in st.session_state:
    st.session_state.st_raw_dataset_list = []


# --- removing import configuration --- #
def remove_import_configuration(project_id: str, alias: str) -> None:
    """Remove import configuration from the cache file.

    PARAMS:
    -------
    project_id: str : project ID
    alias: str : alias of the import configuration to remove

    Returns
    -------
    None
    """
    cache_file = get_import_cache(project_id)
    # filter out the row with the given alias
    updated_cache = cache_file.filter(pl.col("alias") != alias)
    # save the updated cache file
    updated_cache.write_json(f"cache/{project_id}/settings/import_cache.json")


def edit_import_configuration(project_id: str, alias: str) -> None:
    """Edit import configuration in the cache file.

    PARAMS:
    -------
    project_id: str : project ID

    Returns
    -------
    None
    """
    import_log = get_import_cache(project_id)

    source = import_log.filter(pl.col("alias") == alias).select("source").to_series()[0]
    if source == "local storage":
        current_filename = (
            import_log.filter(pl.col("alias") == alias)
            .select("filename")
            .to_series()[0]
        )
        current_sheet_name = (
            import_log.filter(pl.col("alias") == alias)
            .select("sheet_name")
            .to_series()[0]
        )
        defaults = {
            "alias": alias,
            "filename": current_filename,
            "sheet_name": current_sheet_name,
        }
        local_add_form(
            project_id=project_id,
            defaults=defaults,
            edit_mode=True,
        )


# --- modify import cache file --- #
def modify_import_cache_file(project_id: str, edited_import_log: pl.DataFrame) -> None:
    """Modify the import cache file to add or update import configurations.

    PARAMS:
    -------
    project_id: str : project ID

    Returns
    -------
    None
    """
    # write edited import log to the cache file
    edited_import_log.write_json(f"cache/{project_id}/settings/import_cache.json")


# --- load raw data list from import configurations --- #
def refresh_raw_data_list(project_id: str) -> None:
    """Refresh the raw dataset list from the import configurations.

    PARAMS:
    -------
    project_id: str : project ID

    Returns
    -------
    None
    """
    st.session_state.st_raw_dataset_list = []
    import_log = get_import_cache(project_id)
    import_log = import_log.filter(pl.col("load"))
    if import_log.is_empty():
        st.error("No import configurations found. Please add import configurations.")
        st.stop()
    for row in import_log.iter_rows(named=True):
        st.session_state.st_raw_dataset_list.append(row["alias"])


# --- Load raw dataset list from import configurations --- #
def load_raw_datasets(project_id: str) -> None:
    """Load raw dataset list from the cache file.

    PARAMS:
    -------
    project_id: str : project ID

    Returns
    -------
    None
    """
    import_log = get_import_cache(project_id)
    import_log = import_log.filter(pl.col("load"))
    if import_log.is_empty():
        st.error("No import configurations found. Please add import configurations.")
        st.stop()
    with st.status("Loading datasets ...", expanded=True) as status:
        for row in import_log.iter_rows(named=True):
            if row["source"] == "local storage":
                local_load_action(
                    project_id=project_id,
                    alias=row["alias"],
                    filename=row["filename"],
                    sheet_name=row["sheet_name"] if row["sheet_name"] else None,
                )
            elif row["source"] == "SurveyCTO":
                scto_import_data(
                    project_id=project_id,
                    alias=row["alias"],
                    form_id=row["form_id"],
                    refresh=row["refresh"],
                    key=row["private_key"],
                    saveas=row["save_to"],
                    attachments=row["attachments"],
                )

            st.session_state.st_raw_dataset_list.append(row["alias"]) if row[
                "alias"
            ] not in st.session_state.st_raw_dataset_list else None
        status.update(
            label="Data loaded successfully!", state="complete", expanded=False
        )


# --- CONFIGURE PAGE --- #

st.set_page_config("Import Data", page_icon=":sync:", layout="wide")
st.title("Import Data")
st.write("---")

# --- add login configuration ---#
lc1, _, _ = st.columns(3)
with st.container(border=True):
    st.subheader("Import Configuration")
    st.write("Configure the import connections for your project.")
    with (
        lc1,
        st.popover(
            "Add SurveyCTO Server", use_container_width=True, icon=":material/login:"
        ),
    ):
        st.session_state.st_scto = scto_login_form(project_id)

st.subheader("Import data from multiple sources")

# -- Add configurations for import data -- #
ac1, ac2, ac3 = st.columns([0.4, 0.4, 0.2])
with (
    ac1,
    st.popover(
        "Add Import Configuration", use_container_width=True, icon=":material/add:"
    ),
):
    import_type = st.selectbox(
        "Import Type", options=["local storage", "SurveyCTO"], index=None
    )
    if import_type == "local storage":
        local_add_form(project_id)
    elif import_type == "SurveyCTO":
        scto_add_form(project_id)
with (
    ac2,
    st.popover(
        "Edit Import Configuration", use_container_width=True, icon=":material/edit:"
    ),
):
    if st.session_state.st_raw_dataset_list:
        edit_config = st.selectbox(
            "Select Data to Edit",
            options=st.session_state.st_raw_dataset_list,
            index=None,
        )
        if edit_config:
            edit_import_configuration(project_id, edit_config)
    else:
        st.info("No import configurations found. Please add import configurations.")
with (
    ac3,
    st.popover(
        "Remove Import Configuration", use_container_width=True, icon=":material/clear:"
    ),
):
    st.warning("This will remove the import configuration.")
    remove_data = st.selectbox(
        "Select Data to Remove", options=st.session_state.st_raw_dataset_list
    )
    if st.button("Remove Data", type="primary", use_container_width=True):
        remove_import_configuration(project_id=project_id, alias=remove_data)
        refresh_raw_data_list(
            project_id=project_id,
        )

import_log = get_import_cache(project_id)
if not import_log.is_empty():
    edited_import_cache = st.data_editor(
        data=import_log,
        key="import_data_editor",
        use_container_width=True,
        column_config={
            "refresh": st.column_config.CheckboxColumn("Refresh"),
            "load": st.column_config.CheckboxColumn("Load"),
            "alias": st.column_config.TextColumn("Alias", disabled=True),
            "filename": st.column_config.TextColumn("Filename", disabled=True),
            "sheet_name": st.column_config.TextColumn("Sheet Name", disabled=True),
            "source": st.column_config.TextColumn("Source", disabled=True),
            "server": st.column_config.TextColumn("Server", disabled=True),
            "form_id": st.column_config.TextColumn("Form ID", disabled=True),
            "private_key": st.column_config.TextColumn("Private Key", disabled=True),
            "save_to": st.column_config.TextColumn("Save To", disabled=True),
            "attachments": st.column_config.CheckboxColumn(
                "Download Attachments?", disabled=True
            ),
        },
    )
    # -- Load data from import configurations -- #
    ld1, ld2 = st.columns([0.3, 0.7])
    with ld1:
        load_btn = st.button(
            "Load Data",
            type="primary",
            use_container_width=True,
            key="load_data_key",
        )
    with ld2:
        if load_btn:
            # update import_log with the edited import cache
            modify_import_cache_file(project_id, edited_import_cache)
            load_raw_datasets(project_id)

    # --- Preview imported data --- #
    if st.session_state.st_raw_dataset_list:
        # activate prep section
        st.session_state.show_prep_section = True

        st.subheader("Preview Imported Data")
        sb, _, mb1, mb2, mb3 = st.columns([0.3, 0.25, 0.15, 0.15, 0.15])
        with sb:
            selected_dataset = st.selectbox(
                "Select Dataset",
                options=st.session_state.st_raw_dataset_list,
                key="imported_data_select",
            )

        preview_data = get_duckdb_table(
            project_id,
            alias=selected_dataset,
            db_name="raw",
        )

        num_rows = preview_data.height
        mb1.metric(
            label="Rows",
            value=prettify(num_rows),
            help="Number of rows in the imported dataset.",
            border=True,
        )

        num_columns = preview_data.width
        mb2.metric(
            label="Columns",
            value=prettify(num_columns),
            help="Number of columns in the imported dataset.",
            border=True,
        )

        num_missing = preview_data.null_count().sum()
        num_missing = num_missing.with_columns(
            pl.sum_horizontal(pl.all()).alias("row_total")
        )
        perc_missing = (
            f"{(num_missing['row_total'][0] / (num_rows * num_columns)) * 100:.2f}%"
        )

        mb3.metric(
            label="Missing Data",
            value=perc_missing,
            help="Percentage of missing data in the imported dataset.",
            border=True,
        )

        st.dataframe(preview_data, use_container_width=True)

else:
    st.info("No import data found. Please add import configurations.")
