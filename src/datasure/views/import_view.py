import polars as pl
import streamlit as st

from datasure.connectors.local import load_local_data, render_local_file_form
from datasure.connectors.scto import (
    FormConfig,
    SurveyCTOUI,
    download_forms,
)
from datasure.utils.duckdb_utils import (
    duckdb_get_aliases,
    duckdb_get_imported_datasets,
    duckdb_get_table,
    duckdb_remove_table,
    duckdb_row_filter,
    duckdb_save_table,
    duckdb_table_exists,
)
from datasure.utils.navigations_utils import (
    add_demo_navigation,
    demo_callout,
    demo_sidebar_help,
    page_navigation,
    show_demo_next_action,
)
from datasure.utils.onboarding_utils import (
    DEMO_PROJECT_ID,
    ImportDemoInfo,
    demo_expander,
    is_demo_project,
)
from datasure.utils.secure_credentials import (
    delete_stored_credentials,
    list_stored_credentials,
    test_keyring_availability,
)
from datasure.utils.settings_utils import trigger_save

# --- Constants --- #
CREDENTIAL_TYPE = ("SurveyCTO Login", "SurveyCTO Private Key")

# --- CONFIGURE PAGE --- #

st.set_page_config("Import Data", page_icon=":sync:", layout="wide")

# Add demo navigation and guidance
add_demo_navigation("import_view.py", step=2)
demo_sidebar_help()

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

# Demo-specific setup
if (
    is_demo_project()
    and project_id == DEMO_PROJECT_ID
    and "demo_survey" not in st.session_state.st_raw_dataset_list
):
    # Ensure demo datasets are in the list
    st.session_state.st_raw_dataset_list.extend(["demo_survey", "demo_backcheck"])

if "st_prep_dataset_list" not in st.session_state:
    st.session_state.st_prep_dataset_list = None


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
    import_log = _get_filtered_import_log(project_id)

    if import_log.is_empty():
        st.error("No import configurations found. Please add import configurations.")
        return

    _process_import_log(project_id, import_log)


def _get_filtered_import_log(project_id: str) -> pl.DataFrame:
    """Get import log filtered by load flag."""
    import_log = duckdb_get_table(
        project_id=project_id,
        alias="import_log",
        db_name="logs",
    )
    return import_log.filter(pl.col("load"))


def _process_import_log(project_id: str, import_log: pl.DataFrame) -> None:
    """Process all rows in import log with status updates."""
    with st.status("Loading datasets ...", expanded=True) as status:
        for row in import_log.iter_rows(named=True):
            _process_single_import(project_id, row)
        status.update(
            label="Data loaded successfully!", state="complete", expanded=True
        )


def _process_single_import(project_id: str, row: dict) -> None:
    """Process a single import configuration row."""
    if row["refresh"]:
        _load_dataset_by_source(project_id, row)

    _add_to_session_state(row["alias"])


def _load_dataset_by_source(project_id: str, row: dict) -> None:
    """Load dataset based on source type."""
    if row["source"] == "local storage":
        _load_from_local_storage(project_id, row)
    elif row["source"] == "SurveyCTO":
        _load_from_surveycto(project_id, row)


def _load_from_local_storage(project_id: str, row: dict) -> None:
    """Load dataset from local storage."""
    load_local_data(
        project_id=project_id,
        alias=row["alias"],
        filename=row["filename"],
        sheet_name=row["sheet_name"] if row["sheet_name"] else None,
    )


def _load_from_surveycto(project_id: str, row: dict) -> None:
    """Load dataset from SurveyCTO."""
    form_configs = _create_form_config(row)
    download_forms(
        project_id=project_id,
        form_configs=[form_configs],
    )


def _create_form_config(row: dict) -> FormConfig:
    """Create FormConfig from import log row."""
    return FormConfig(
        alias=row["alias"],
        form_id=row["form_id"],
        server=row["server"],
        username=row["username"] if row["username"] else None,
        private_key=row["private_key"] if row["private_key"] else None,
        save_to=row["save_to"] if row["save_to"] else None,
        attachments=row["attachments"],
        refresh=row["refresh"],
    )


def _add_to_session_state(alias: str) -> None:
    """Add alias to session state if not already present."""
    if alias not in st.session_state.st_raw_dataset_list:
        st.session_state.st_raw_dataset_list.append(alias)

        # Demo success message
        if is_demo_project():
            demo_callout(ImportDemoInfo.get_info_message("add_to_session_info"))


# --- Update import log in the cache file --- #
def update_import_log(import_log: pl.DataFrame) -> None:
    """Update the import log in the cache file."""
    # reaarnge columns to match the import log structure
    import_log = import_log.select(
        [
            "refresh",
            "load",
            "alias",
            "filename",
            "sheet_name",
            "source",
            "server",
            "username",
            "form_id",
            "private_key",
            "save_to",
            "attachments",
        ]
    )
    edited_import_log = st.data_editor(
        data=import_log,
        key="import_data_editor",
        width="stretch",
        column_config={
            "refresh": st.column_config.CheckboxColumn("Refresh?"),
            "load": st.column_config.CheckboxColumn("Load?"),
            "alias": st.column_config.TextColumn("Alias", disabled=True),
            "filename": st.column_config.TextColumn("Filename", disabled=True),
            "sheet_name": st.column_config.TextColumn("Sheet Name", disabled=True),
            "source": st.column_config.TextColumn("Source", disabled=True),
            "server": st.column_config.TextColumn("Server", disabled=True),
            "username": st.column_config.TextColumn("Username", disabled=True),
            "form_id": st.column_config.TextColumn("Form ID", disabled=True),
            "private_key": st.column_config.TextColumn("Private Key", disabled=True),
            "save_to": st.column_config.TextColumn("Save To", disabled=True),
            "attachments": st.column_config.CheckboxColumn("Download Media?"),
        },
        on_change=trigger_save,
        kwargs={"state_name": "refresh_import_log"},
    )
    if "refresh_import_log" in st.session_state and st.session_state.refresh_import_log:
        # Save the edited import log to the database
        duckdb_save_table(
            project_id=project_id,
            table_data=edited_import_log,
            alias="import_log",
            db_name="logs",
        )
        st.session_state.refresh_import_log = False


# --- Credential Manager --- #
with st.container(border=True):
    st.subheader(":material/key: Manage Credentials")
    st.write("Import and manage your credentials for data import.")

    kc1, kc2, kc3 = st.columns([0.4, 0.3, 0.3])

    with (
        kc1,
        st.popover("Add Credentials", width="stretch", icon=":material/add:"),
    ):
        st.write("Add your credentials for data import.")
        select_cred_type = st.selectbox(
            "Select Credential Type",
            options=CREDENTIAL_TYPE,
            index=0,
            key="cred_type_select",
            disabled=True,
        )
        if select_cred_type == "SurveyCTO Login":
            SurveyCTOUI(project_id).render_login_form()

    with (
        kc2,
        st.popover("Remove Credentials", width="stretch", icon=":material/delete:"),
    ):
        st.write("**Remove Credentials**")
        saved_credentials = list_stored_credentials(project_id).get("credentials", {})
        select_credentials = st.selectbox(
            "Select Crendetials to Deleted",
            options=saved_credentials.keys(),
            index=None,
        )
        if st.button(
            "Delete Credentials",
            type="primary",
            width="stretch",
            disabled=not select_credentials,
        ):
            selected_server = saved_credentials[select_credentials].get("server", "")
            selected_type = saved_credentials[select_credentials].get("type", "")
            delete_stored_credentials(
                project_id=project_id,
                server=selected_type,
                credential_type=selected_type,
            )
            st.success(f"Credentials for {select_credentials} deleted successfully.")

    with (
        kc3,
        st.popover("Keyring Diagnostics", width="stretch", icon=":material/build:"),
    ):
        st.write("**Keyring Diagnostics**")
        if st.button("Test Keyring Availability", width="stretch"):
            keyring_status = test_keyring_availability()
            if keyring_status["success"]:
                st.success(
                    f":material/check: Keyring working: {keyring_status['backend']}"
                )
                st.info(keyring_status["message"])
            else:
                st.error(f":material/close: Keyring issue: {keyring_status['error']}")
                st.info("**Troubleshooting Tips:**")
                st.markdown("""
                - **Windows**: Ensure Windows Credential Manager is accessible
                - **macOS**: Check Keychain Access permissions
                - **Linux**: Install and configure a keyring backend (gnome-keyring, kwallet)
                """)

st.subheader("Import data from multiple sources")

# -- Add configurations for import data -- #
ac1, ac2, ac3 = st.columns([0.4, 0.4, 0.2])
aliases = duckdb_get_aliases(project_id, to_load=False)
with (
    ac1,
    st.popover("Add Import Configuration", width="stretch", icon=":material/add:"),
):
    import_type = st.selectbox(
        "Import Type", options=["local storage", "SurveyCTO"], index=None
    )
    if import_type == "local storage":
        render_local_file_form(project_id)
    elif import_type == "SurveyCTO":
        SurveyCTOUI(project_id).render_form_config()
with (
    ac2,
    st.popover(
        "Edit Import Configuration",
        width="stretch",
        icon=":material/edit:",
        disabled=not aliases,
    ),
):
    edit_config = st.selectbox(
        "Select Data to Edit",
        options=aliases,
        index=None,
    )
    if edit_config:
        import_log = duckdb_get_table(project_id, alias="import_log", db_name="logs")
        # -- Get the selected import configuration details -- #
        selected_config = import_log.filter(pl.col("alias") == edit_config).to_dicts()[
            0
        ]
        if selected_config["source"] == "local storage":
            render_local_file_form(project_id, edit_mode=True, defaults=selected_config)
        elif selected_config["source"] == "SurveyCTO":
            SurveyCTOUI(project_id).render_form_config(
                edit_mode=True, defaults=selected_config
            )
        else:
            st.error("Invalid import source.")
with (
    ac3,
    st.popover(
        "Remove Import Configuration",
        width="stretch",
        icon=":material/clear:",
        disabled=not aliases,
    ),
):
    st.warning("This will remove the import configuration.")
    remove_column_options = duckdb_get_aliases(project_id, to_load=False)
    remove_data = st.selectbox(
        "Select Data to Remove", options=remove_column_options, index=None
    )
    if st.button("Remove Data", type="primary", width="stretch"):
        duckdb_row_filter(
            project_id=project_id,
            alias="import_log",
            db_name="logs",
            filter_condition=f"alias != '{remove_data}'",
        )
        duckdb_remove_table(project_id, alias=remove_data, db_name="raw")
        # check if the table exist in prep, if yes remove it
        if duckdb_table_exists(project_id, alias=remove_data, db_name="prep"):
            duckdb_remove_table(project_id, alias=remove_data, db_name="prep")
        # check if the table exist in corrected db, if yes remove it
        if duckdb_table_exists(project_id, alias=remove_data, db_name="corrected"):
            duckdb_remove_table(project_id, alias=remove_data, db_name="corrected")
        st.session_state.st_raw_dataset_list = duckdb_get_aliases(project_id)

import_log = duckdb_get_table(project_id, alias="import_log", db_name="logs")
if not import_log.is_empty():
    # -- Update import log in the DB on change -- #
    update_import_log(import_log)

    # -- Load data from import configurations -- #
    ld1, ld2 = st.columns([0.3, 0.7])
    with ld1:
        load_btn = st.button(
            "Load Data",
            type="primary",
            width="stretch",
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

        # Demo guidance
        if is_demo_project():
            demo_callout(ImportDemoInfo.get_info_message("preview_data_info"))
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
        perc_missing = (num_missing["row_total"][0] / (num_rows * num_columns)) * 100

        mb3.metric(
            label="Missing Data",
            value=f"{perc_missing:.2f}%",
            help="Percentage of missing data in the imported dataset.",
            border=True,
        )

        st.dataframe(preview_data, width="stretch")

        # Demo expander with educational content
        if is_demo_project():
            demo_expander(
                "About Your Pre-loaded Demo Data",
                ImportDemoInfo.get_info_message("demo_data_info"),
                expanded=True,
            )

            # Demo next action
            st.write("---")
            show_demo_next_action(2, "st_prep_data_page", "Prepare Your Data")

else:
    st.info("No import data found. Please add import configurations.")

# Previous and next pages (import, prep) - only for non-demo projects
if not is_demo_project():
    page_navigation(
        next={
            "page_name": st.session_state.st_prep_data_page,
            "label": "Next: Prepare Data →",
        }
    )
