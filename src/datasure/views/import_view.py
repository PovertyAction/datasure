import polars as pl
import streamlit as st

from datasure.connectors import (
    local_add_form,
    local_load_action,
    scto_add_form,
    scto_import_data,
    scto_login_form,
)
from datasure.utils import (
    duckdb_get_aliases,
    duckdb_get_imported_datasets,
    duckdb_get_table,
    duckdb_row_filter,
    duckdb_save_table,
)

# --- CONFIGURE PAGE --- #

st.set_page_config("Import Data", page_icon=":sync:", layout="wide")
st.title("Import Data")
st.write("---")

# --- define project ID --- #
project_id = st.session_state.st_project_id

if not project_id:
    st.info(
        "Please select a project from the Start page to import data. "
        "You can also create a new project from the Start page."
    )
    st.stop()

# add session state for raw dataset list
if "st_raw_dataset_list" not in st.session_state:
    st.session_state.st_raw_dataset_list = duckdb_get_aliases(project_id, to_load=True)

if "st_prep_dataset_list" not in st.session_state:
    st.session_state.st_prep_dataset_list = None


def edit_import_configuration(project_id: str, alias: str) -> None:
    """Edit import configuration in the cache file.

    PARAMS:
    -------
    project_id: str : project ID

    Returns
    -------
    None
    """
    import_log = duckdb_get_table(project_id, alias="import_log", db_name="logs")

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
    import_log = duckdb_get_table(
        project_id=project_id,
        alias="import_log",
        db_name="logs",
    )
    import_log = import_log.filter(pl.col("load"))
    if import_log.is_empty():
        st.error("No import configurations found. Please add import configurations.")
    else:
        with st.status("Loading datasets ...", expanded=True) as status:
            for row in import_log.iter_rows(named=True):
                if row["source"] == "local storage" and row["refresh"] is True:
                    local_load_action(
                        project_id=project_id,
                        alias=row["alias"],
                        filename=row["filename"],
                        sheet_name=row["sheet_name"] if row["sheet_name"] else None,
                    )
                elif row["source"] == "SurveyCTO" and row["refresh"] is True:
                    scto_import_data(
                        project_id=project_id,
                        alias=row["alias"],
                        form_id=row["form_id"],
                        refresh=row["refresh"],
                        key=row["private_key"],
                        saveas=row["save_to"],
                        attachments=row["attachments"],
                    )

                if row["alias"] not in st.session_state.st_raw_dataset_list:
                    st.session_state.st_raw_dataset_list.append(row["alias"])
            status.update(
                label="Data loaded successfully!", state="complete", expanded=False
            )


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
    remove_column_options = duckdb_get_aliases(project_id, to_load=False)
    remove_data = st.selectbox(
        "Select Data to Remove", options=remove_column_options, index=None
    )
    if st.button("Remove Data", type="primary", use_container_width=True):
        duckdb_row_filter(
            project_id=project_id,
            alias="import_log",
            db_name="logs",
            filter_condition=f"alias != '{remove_data}'",
        )
        st.session_state.st_raw_dataset_list = duckdb_get_aliases(project_id)

import_log = duckdb_get_table(project_id, alias="import_log", db_name="logs")
if not import_log.is_empty():
    # -- Update import log in the DB on change -- #
    def update_import_log():
        """Update the import log in the cache file."""
        duckdb_save_table(
            project_id,
            edited_import_log,
            alias="import_log",
            db_name="logs",
        )

    edited_import_log = st.data_editor(
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
        on_change=update_import_log,
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

    if load_btn:
        with ld2:
            # Load raw datasets from import configurations
            load_raw_datasets(project_id)
            preview_options = duckdb_get_imported_datasets(project_id)
            st.session_state.st_prep_dataset_list = preview_options

        # display success message and link to the prep section
        with st.container(border=True):
            st.success(
                "Data loaded successfully! You can now preview the imported data in the Prep section."
            )

    preview_options = duckdb_get_imported_datasets(project_id)
    if preview_options:
        # --- Preview imported data --- #
        # activate prep section

        st.subheader("Preview Imported Data")
        sb, _, mb1, mb2, mb3 = st.columns([0.3, 0.25, 0.15, 0.15, 0.15])
        with sb:
            selected_dataset = st.selectbox(
                "Select Dataset",
                options=sorted(preview_options),
                key="imported_data_select",
            )

        preview_data = duckdb_get_table(
            project_id,
            alias=selected_dataset,
            db_name="raw",
        )

        num_rows = preview_data.height
        mb1.metric(
            label="Rows",
            value=f"{num_rows:,}",
            help="Number of rows in the imported dataset.",
            border=True,
        )

        num_columns = preview_data.width
        mb2.metric(
            label="Columns",
            value=f"{num_columns:,}",
            help="Number of columns in the imported dataset.",
            border=True,
        )

        num_missing = preview_data.null_count().sum()
        num_missing = num_missing.with_columns(
            pl.sum_horizontal(pl.all()).alias("row_total")
        )
        perc_missing = (
            (num_missing['row_total'][0] / (num_rows * num_columns)) * 100
        )

        mb3.metric(
            label="Missing Data",
            value=f"{perc_missing:.2f}%",
            help="Percentage of missing data in the imported dataset.",
            border=True,
        )

        st.dataframe(preview_data, use_container_width=True)

else:
    st.info("No import data found. Please add import configurations.")
