import streamlit as st

from src.connectors import get_import_cache, local_add_form

# --- CONFIGURE PAGE --- #

st.set_page_config("Import Data", page_icon=":sync:", layout="wide")
st.title("Import Data")
st.markdown("Import data from multiple sources")

project_id = st.session_state.st_project_id

# -- Add configurations for import data -- #
ac1, ac2, ac3 = st.columns([0.4, 0.4, 0.2])
with (
    ac1,
    st.popover(
        "Add Import Configuration", use_container_width=True, icon=":material/add:"
    ),
):
    import_type = st.selectbox(
        "Import Type", options=["local", "SurveyCTO"], index=None
    )
    if import_type == "local":
        local_add_form(project_id)
with (
    ac2,
    st.popover(
        "Edit Import Configuration", use_container_width=True, icon=":material/edit:"
    ),
):
    st.warning("Edit configurations cleared.")
with (
    ac3,
    st.popover(
        "Remove Import Configuration", use_container_width=True, icon=":material/clear:"
    ),
):
    st.warning("Remove configurations cleared.")

import_log = get_import_cache(project_id)

if not import_log.is_empty():
    st.data_editor(
        data=import_log,
        key="import_data_editor",
        use_container_width=True,
        column_config={
            "refresh": st.column_config.CheckboxColumn("Refresh"),
            "type": st.column_config.SelectboxColumn(
                "Type", options=["local", "SuveyCTO"]
            ),
            "alias": st.column_config.TextColumn("Alias"),
            "source": st.column_config.TextColumn("Source"),
            "server": st.column_config.TextColumn("Server"),
            "form_id": st.column_config.TextColumn("Form ID"),
            "private_key": st.column_config.TextColumn("Private Key"),
            "save_to": st.column_config.TextColumn("Save To"),
            "attachments": st.column_config.CheckboxColumn("Download Attachments?"),
        },
    )
else:
    st.info("No import data found. Please add import configurations.")
