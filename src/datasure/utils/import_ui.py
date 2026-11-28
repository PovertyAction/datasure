"""Import page UI: Connections, dataset rows and the add, edit and remove dialogs.

The page (``views/import_view.py``) lays these out. What each row shows comes
from :mod:`datasure.utils.dataset_list`, and every write goes through
:mod:`datasure.utils.import_log`. Adding or editing a dataset only registers
it; "Load data" on the page does the import.
"""

import logging
from collections.abc import Callable
from pathlib import Path

import duckdb
import streamlit as st
from pydantic import ValidationError

from datasure.connectors.local import (
    VALID_FILE_TYPES,
    XLS_NOT_SUPPORTED_MESSAGE,
    FileConfig,
    get_excel_sheet_names,
)
from datasure.connectors.scto import (
    FormConfig,
    ServerCredentials,
    SurveyCTOClient,
    SurveyCTOUI,
)
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.dataset_list import (
    LOCAL_SOURCE,
    SURVEYCTO_SOURCE,
    DatasetRow,
)
from datasure.utils.import_log import (
    alias_clash_message,
    remove_dataset,
    save_local_dataset,
    save_surveycto_dataset,
    set_dataset_flag,
)
from datasure.utils.names import (
    NAME_MAX_LENGTH,
    NAME_RULE_HELP,
    STORED_NAME,
    suggest_name,
    validation_message,
)
from datasure.utils.project_registry import read_registry
from datasure.utils.secure_credentials import (
    delete_stored_credentials,
    list_stored_credentials,
    retrieve_scto_credentials,
    test_keyring_availability,
)
from datasure.utils.ui_utils import confirm_dialog, queue_notice

logger = logging.getLogger(__name__)

DIALOG_STATE = "import_dataset_dialog"

# Messages queued before a rerun show at the top of the import page.
NOTICE_SCOPE = "import_page"

STEP_SOURCE = "source"
STEP_CONNECTION = "connection"
STEP_REVIEW = "review"
STEPS = (STEP_SOURCE, STEP_CONNECTION, STEP_REVIEW)
_STEP_LABELS = {
    STEP_SOURCE: "Source",
    STEP_CONNECTION: "Connection",
    STEP_REVIEW: "Review",
}

SOURCE_CHOICES = {SURVEYCTO_SOURCE: "SurveyCTO", LOCAL_SOURCE: "Local file"}

_SOURCE_BADGES = {
    SURVEYCTO_SOURCE: (":material/cloud:", "blue"),
    LOCAL_SOURCE: (":material/folder:", "gray"),
}

LOCAL_REFRESH_HINT = (
    "DataSure reads the file from this path each time the dataset is "
    "refreshed, so keep it in place. A synced folder works well."
)
REGISTER_ONLY_NOTE = (
    "Saving adds the dataset to the list. Click **Load data** on the page to import it."
)


# --- Project ---------------------------------------------------------------


def project_name(project_id: str) -> str:
    """Return the project's name from the registry, or its ID when unnamed."""
    projects = read_registry(get_cache_path("projects.json"))
    return projects.get(project_id, {}).get("name", project_id)


# --- Connections -----------------------------------------------------------


def saved_connections(project_id: str) -> dict[str, dict]:
    """Return the project's saved connections by display name."""
    return list_stored_credentials(project_id).get("credentials", {})


def connections_summary(connections: dict[str, dict]) -> str:
    """Say in a few words what is connected."""
    servers = sum(
        1
        for details in connections.values()
        if details.get("credential_type", "scto_login") == "scto_login"
    )
    if not servers:
        return "Nothing connected yet"
    return f"{servers} SurveyCTO server{'' if servers == 1 else 's'} connected"


def _remove_connection(project_id: str, name: str, details: dict) -> None:
    result = delete_stored_credentials(
        project_id=project_id,
        server=details.get("server", ""),
        credential_type=details.get("credential_type", "scto_login"),
    )
    if result["success"]:
        queue_notice(NOTICE_SCOPE, "success", f"Removed the connection {name}.")
    else:
        queue_notice(
            NOTICE_SCOPE,
            "error",
            f"Could not remove the connection {name}: {result['error']}",
        )


def _render_remove_connection(project_id: str, connections: dict[str, dict]) -> None:
    selected = st.selectbox(
        "Connection to remove",
        options=list(connections),
        index=None,
        key="import_remove_connection",
    )
    if st.button(
        "Remove connection",
        type="primary",
        width="stretch",
        disabled=not selected,
        icon=":material/delete:",
    ):
        details = connections[selected]
        confirm_dialog(
            f"Remove {selected}?",
            f"This removes the saved sign-in for **{selected}**, including its "
            "password in this computer's keyring. Datasets from this server "
            "stay on the list but can't be refreshed until you connect it again.",
            confirm_label="Remove",
            on_confirm=lambda: _remove_connection(project_id, selected, details),
        )


def _render_keyring_diagnostics() -> None:
    st.caption("Check that DataSure can store passwords in this computer's keyring.")
    if not st.button("Test keyring", width="stretch"):
        return
    status = test_keyring_availability()
    if status["success"]:
        st.success(f"Keyring working: {status['backend']}", icon=":material/check:")
        if status.get("message"):
            st.info(status["message"])
        if status.get("warning"):
            st.warning(status["warning"])
        return
    st.error(f"Keyring issue: {status['error']}", icon=":material/close:")
    st.markdown(
        "**Troubleshooting tips**\n"
        "- **Windows**: make sure Windows Credential Manager is accessible.\n"
        "- **macOS**: check Keychain Access permissions.\n"
        "- **Linux**: install and set up a keyring backend (gnome-keyring, "
        "kwallet).\n"
        "- **Headless server or container**: choose an encrypted backend with "
        '`PYTHON_KEYRING_BACKEND` (see "Running on a server" in the README).'
    )


def render_connections(project_id: str) -> None:
    """Render the Connections expander: saved connections, add, remove, diagnostics.

    It opens by itself only while nothing is connected.
    """
    connections = saved_connections(project_id)
    with st.expander(
        f"Connections · {connections_summary(connections)}",
        icon=":material/key:",
        expanded=not connections,
    ):
        if connections:
            for name, details in connections.items():
                st.caption(
                    f":material/cloud: **{name}** · SurveyCTO · "
                    f"{details.get('username', '')}"
                )
        else:
            st.caption(
                "Connect a SurveyCTO server to import its forms. Local files "
                "need no connection."
            )
        with st.container(horizontal=True):
            with st.popover("Add connection", icon=":material/add:"):
                st.caption(
                    "Connect a SurveyCTO server. The password is kept in "
                    "this computer's keyring."
                )
                SurveyCTOUI(project_id).render_login_form()
            with st.popover(
                "Remove connection",
                icon=":material/link_off:",
                disabled=not connections,
            ):
                _render_remove_connection(project_id, connections)
            with st.popover("Keyring diagnostics", icon=":material/troubleshoot:"):
                _render_keyring_diagnostics()


# --- Dataset rows ----------------------------------------------------------


def _toggle_key(alias: str, column: str, value: bool) -> str:
    # The stored value is part of the key, so the switch follows the import
    # log when an edit changes it.
    return f"import_flag_{alias}_{column}_{value}"


def _on_flag_change(project_id: str, alias: str, column: str, key: str) -> None:
    try:
        set_dataset_flag(project_id, alias, column, st.session_state[key])
    except (ValueError, duckdb.Error) as e:
        # UI boundary: keep the page up and say the switch wasn't saved.
        logger.exception("Could not save %s for %s", column, alias)
        st.error(f"Could not save the {column} switch for {alias}: {e}")


def _flag_toggle(
    project_id: str,
    row: DatasetRow,
    label: str,
    column: str,
    value: bool,
    *,
    help: str,
    disabled: bool = False,
) -> None:
    key = _toggle_key(row.alias, column, value)
    st.toggle(
        label,
        value=value,
        key=key,
        help=help,
        disabled=disabled,
        on_change=_on_flag_change,
        args=(project_id, row.alias, column, key),
    )


def render_dataset_row(
    project_id: str,
    row: DatasetRow,
    *,
    on_edit: Callable[[str], None],
    on_remove: Callable[[str], None],
) -> None:
    """Render one dataset: name, source, last load, switches and its menu."""
    icon, color = _SOURCE_BADGES.get(row.source, (":material/folder:", "gray"))
    with st.container(
        border=True, horizontal=True, vertical_alignment="center", gap="medium"
    ):
        with st.container(gap="small"):
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(f"**{row.alias}**")
                st.badge(row.source_label, icon=icon, color=color)
            detail = row.source_detail
            if row.row_count is not None:
                detail += f" · {row.row_count:,} rows"
            st.caption(detail)
            st.caption(row.last_loaded_label)
        with st.container(
            horizontal=True, width="content", vertical_alignment="center"
        ):
            # Load comes first: Refresh only acts on datasets marked Load.
            _flag_toggle(
                project_id,
                row,
                "Load",
                "load",
                row.load,
                help="Include this dataset when you click Load data.",
            )
            _flag_toggle(
                project_id,
                row,
                "Refresh",
                "refresh",
                row.refresh,
                help="Download or re-read this dataset from its source on "
                "the next Load data."
                if row.load
                else "Turn on Load to refresh this dataset.",
                disabled=not row.load,
            )
            _flag_toggle(
                project_id,
                row,
                "Media",
                "attachments",
                row.media,
                help=row.media_disabled_reason
                or "Download media files (images, audio) with the data.",
                disabled=row.media_disabled_reason is not None,
            )
        with st.popover(
            "", icon=":material/more_vert:", help=f"Actions for {row.alias}"
        ):
            if st.button(
                "Edit",
                icon=":material/edit:",
                key=f"import_edit_{row.alias}",
                width="stretch",
                type="tertiary",
                disabled=row.source not in SOURCE_CHOICES,
                help=None
                if row.source in SOURCE_CHOICES
                else "The demo datasets can't be edited.",
            ):
                on_edit(row.alias)
            if st.button(
                "Remove",
                icon=":material/delete:",
                key=f"import_remove_{row.alias}",
                width="stretch",
                type="tertiary",
            ):
                on_remove(row.alias)


# --- Remove ----------------------------------------------------------------


def remove_message(alias: str) -> str:
    """Say what removing a dataset deletes."""
    return (
        f"This permanently removes **{alias}** from the project: its import "
        "settings, its imported, prepared and corrected data, and any stored "
        "SurveyCTO form definitions. The source file or form is not changed. "
        "This cannot be undone."
    )


def open_remove_dialog(project_id: str, alias: str, on_removed=None) -> None:
    """Ask before removing a dataset, then remove it."""

    def _remove() -> None:
        remove_dataset(project_id, alias)
        queue_notice(NOTICE_SCOPE, "toast", f"Removed {alias}")
        if on_removed:
            on_removed(alias)

    confirm_dialog(
        f"Remove {alias}?",
        remove_message(alias),
        confirm_label="Remove",
        on_confirm=_remove,
    )


# --- Add and edit dialog ---------------------------------------------------

NEXT_LABEL = "Next"
REVIEW_LABEL = "Next: review"


class _StepError(Exception):
    """A step's answers can't be accepted; the message says why."""


def _state() -> dict:
    return st.session_state[DIALOG_STATE]


def _key(name: str) -> str:
    """Widget key for the open dialog; a fresh nonce per opening resets widgets."""
    return f"import_dlg_{_state()['nonce']}_{name}"


def _widget(name: str, default=None):
    """Return a dialog widget's current value from session state."""
    return st.session_state.get(_key(name), default)


def _start(state: dict) -> None:
    previous = st.session_state.get(DIALOG_STATE, {}).get("nonce", 0)
    st.session_state[DIALOG_STATE] = {**state, "nonce": previous + 1}


def _go(step: str) -> None:
    state = _state()
    state["step"] = step
    state.pop("error", None)


def _advance(project_id: str, collect: Callable[[str], dict]) -> None:
    """Accept the current step's answers and move on, or keep the error to show.

    Runs as the forward button's callback, so it reads widgets from session
    state and needs no rerun of its own.
    """
    state = _state()
    try:
        values = collect(project_id)
    except _StepError as e:
        state["error"] = str(e)
        return
    state["values"] = values
    _go(STEPS[STEPS.index(state["step"]) + 1])


def _render_stepper(step: str) -> None:
    current = STEPS.index(step)
    with st.container(horizontal=True, gap="medium"):
        for index, name in enumerate(STEPS):
            label = f"{index + 1} · {_STEP_LABELS[name]}"
            if index == current:
                st.markdown(f":orange[**{label}**]")
            else:
                st.markdown(f":gray[{label}]")
    st.progress((current + 1) / len(STEPS))


def _drafted(fields: dict[str, str]) -> dict:
    """Return the answers typed so far, by field, for widgets on screen.

    ``fields`` maps a field in ``state["values"]`` to its widget's name.
    Nothing is validated: a draft keeps incomplete answers too.
    """
    return {
        field: st.session_state[_key(name)]
        for field, name in fields.items()
        if _key(name) in st.session_state
    }


def _back(previous: str, draft: Callable[[], dict] | None) -> None:
    """Go back a step, keeping the current step's answers if it has a draft.

    Streamlit drops the state of widgets that aren't rendered, so without
    this the answers would be lost by the time the step is shown again.
    """
    state = _state()
    if draft:
        state["values"] = {**state["values"], **draft()}
    _go(previous)


def _render_back(draft: Callable[[], dict] | None = None) -> None:
    previous = STEPS[STEPS.index(_state()["step"]) - 1]
    st.button(
        "Back",
        icon=":material/arrow_back:",
        key=_key("back"),
        on_click=_back,
        args=(previous, draft),
    )


def _render_nav(
    project_id: str,
    collect: Callable[[str], dict],
    draft: Callable[[], dict],
    *,
    disabled: bool = False,
) -> None:
    """Render the step's error, Back, and Next: review."""
    if _state().get("error"):
        st.error(_state()["error"], icon=":material/error:")
    with st.container(horizontal=True, horizontal_alignment="distribute"):
        _render_back(draft)
        st.button(
            REVIEW_LABEL,
            type="primary",
            key=_key("next"),
            disabled=disabled,
            on_click=_advance,
            args=(project_id, collect),
        )


def _check_alias_free(project_id: str, alias: str) -> None:
    if _state()["edit"]:
        return
    clash = alias_clash_message(project_id, alias)
    if clash:
        raise _StepError(clash)


def _validated(model, data: dict):
    """Validate step answers against a config model, as a step error."""
    try:
        # A stored alias can't be edited, so it's kept as saved.
        return model.model_validate(
            data, context=STORED_NAME if _state()["edit"] else None
        )
    except ValidationError as e:
        raise _StepError(validation_message(e)) from e


# Source step


def _choose_source() -> None:
    state = _state()
    source = _widget("source")
    if source != state["source"]:
        # Answers for one source don't carry over to the other.
        state.update(source=source, values={})
    _go(STEP_CONNECTION)


def _render_source_step() -> None:
    state = _state()
    choices = list(SOURCE_CHOICES)
    source = st.radio(
        "Where does the data come from?",
        options=choices,
        format_func=SOURCE_CHOICES.get,
        captions=[
            "Download a form's submissions from a connected server.",
            "Read a CSV, Excel, Stata, Parquet or JSON file on this computer.",
        ],
        index=choices.index(state["source"]) if state["source"] else None,
        disabled=state["edit"],
        key=_key("source"),
    )
    if state["edit"]:
        st.caption("A dataset's source can't be changed. Remove it and add it again.")
    with st.container(horizontal=True, horizontal_alignment="right"):
        st.button(
            NEXT_LABEL,
            type="primary",
            key=_key("next"),
            disabled=source is None,
            on_click=_choose_source,
        )


def _alias_input(value: str, name: str) -> str:
    edit = _state()["edit"]
    return st.text_input(
        "Alias",
        value=value,
        help=f"A short, unique name for this dataset. {NAME_RULE_HELP}",
        disabled=edit,
        max_chars=None if edit else NAME_MAX_LENGTH,
        key=_key(name),
    )


# Local file connection step


def local_file_problem(path: str) -> str | None:
    """Say what's wrong with a local file path, or ``None`` when it can be read."""
    file_path = Path(path.strip())
    if not file_path.exists():
        return "There is no file at this path."
    if not file_path.is_file():
        return "This path is a folder, not a file."
    suffix = file_path.suffix.lower()
    if suffix == ".xls":
        return XLS_NOT_SUPPORTED_MESSAGE
    if suffix not in VALID_FILE_TYPES:
        supported = ", ".join(sorted(VALID_FILE_TYPES))
        return f"{suffix or 'These'} files aren't supported. Use {supported}."
    return None


def _render_file_checks(path: str, stored_sheet: str | None) -> bool:
    """Check the path as the user types; return whether it can be used."""
    if not path.strip():
        return False
    problem = local_file_problem(path)
    if problem:
        st.error(problem, icon=":material/error:")
        return False
    if Path(path.strip()).suffix.lower() != ".xlsx":
        st.success("File found.", icon=":material/check_circle:")
        return True
    sheets = get_excel_sheet_names(path.strip())
    if not sheets:
        st.error("DataSure found no sheets to read in this workbook.")
        return False
    st.selectbox(
        "Sheet",
        options=sheets,
        index=sheets.index(stored_sheet) if stored_sheet in sheets else 0,
        key=_key("local_sheet"),
    )
    return True


def _collect_local(project_id: str) -> dict:
    path = _widget("local_path", "")
    problem = local_file_problem(path)
    if problem:
        raise _StepError(problem)
    config = _validated(
        FileConfig,
        {
            "alias": _widget("local_alias", ""),
            "filename": path,
            "sheet_name": _widget("local_sheet"),
        },
    )
    _check_alias_free(project_id, config.alias)
    return {
        "alias": config.alias,
        "filename": config.filename,
        "sheet_name": config.sheet_name or "",
    }


def _draft_local() -> dict:
    return _drafted(
        {
            "alias": "local_alias",
            "filename": "local_path",
            "sheet_name": "local_sheet",
        }
    )


def _render_local_step(project_id: str) -> None:
    values = _state()["values"]
    _alias_input(values.get("alias", ""), "local_alias")
    path = st.text_input(
        "File path",
        value=values.get("filename", ""),
        placeholder="C:/data/survey.dta",
        help="The full path to the file on this computer.",
        key=_key("local_path"),
    )
    st.caption(f":material/sync: {LOCAL_REFRESH_HINT}")
    ready = _render_file_checks(path, values.get("sheet_name"))
    _render_nav(project_id, _collect_local, _draft_local, disabled=not ready)


# SurveyCTO connection step


def list_server_forms(
    project_id: str, server: str, username: str
) -> list[tuple[str, str, bool]]:
    """Return ``(form_id, title, encrypted)`` for each form on a saved server.

    Raises
    ------
    ConnectionError
        When the server can't be reached with the saved password.
    """
    stored = retrieve_scto_credentials(project_id, type="scto_login", server=server)
    password = (stored or {}).get("credentials", {}).get("password", "")
    credentials = ServerCredentials(server=server, user=username, password=password)
    info = SurveyCTOClient(project_id).connect(credentials, validate_permissions=True)
    return list(info["forms_list"])


def _surveycto_connections(project_id: str) -> dict[str, dict]:
    return {
        name: details
        for name, details in saved_connections(project_id).items()
        if details.get("credential_type", "scto_login") == "scto_login"
    }


def _server_forms(project_id: str, connection: dict) -> dict[str, tuple]:
    """Return a server's forms by ID, asking the server once per dialog."""
    server = connection["server"]
    cache = _state().setdefault("forms", {})
    if server not in cache:
        try:
            with st.spinner(f"Getting forms from {server}..."):
                forms = list_server_forms(
                    project_id, server, connection.get("username", "")
                )
        except Exception as e:
            # UI boundary: show the failure without crashing the dialog.
            logger.exception("Could not list forms on %s", server)
            st.error(f"Could not get the forms on {server}: {e}")
            return {}
        cache[server] = {form[0]: tuple(form) for form in forms}
    return cache[server]


def private_key_problem(encrypted: bool, path: str) -> str | None:
    """Say what's wrong with a private key path, or ``None`` when it's usable."""
    if not encrypted or not path:
        return None
    if not Path(path).exists():
        return "There is no key file at this path."
    if not path.endswith(".pem"):
        return "The private key must be a .pem file."
    return None


def _scto_alias_name(form_id: str) -> str:
    # In add mode the suggested alias follows the chosen form.
    return "scto_alias" if _state()["edit"] else f"scto_alias_{form_id}"


def _render_form_fields(form: tuple, values: dict) -> bool:
    """Render the chosen form's settings; return whether they can be used."""
    form_id, title, encrypted = form
    _alias_input(values.get("alias") or suggest_name(title), _scto_alias_name(form_id))
    key_path = st.text_input(
        "Private key file",
        value=values.get("private_key", ""),
        disabled=not encrypted,
        placeholder="C:/keys/form_PRIVATEKEY.pem",
        help="Needed to decrypt an encrypted form's fields.",
        key=_key("scto_key"),
    )
    if encrypted and not key_path:
        st.warning(
            "This form is encrypted. Without its private key, only published "
            "fields are downloaded."
        )
    problem = private_key_problem(encrypted, key_path)
    if problem:
        st.error(problem)
    st.text_input(
        "Also save a copy to (optional)",
        value=values.get("save_to", ""),
        placeholder="C:/data/survey.csv",
        key=_key("scto_save_to"),
    )
    st.toggle(
        "Download media",
        value=bool(values.get("attachments", False)),
        help="Download media files (images, audio) with the data.",
        key=_key("scto_media"),
    )
    return problem is None


def _collect_surveycto(project_id: str) -> dict:
    connection = _surveycto_connections(project_id)[_widget("scto_server")]
    form_id = _widget("scto_form")
    _, title, encrypted = _state()["forms"][connection["server"]][form_id]
    key_path = _widget("scto_key", "") if encrypted else ""
    problem = private_key_problem(encrypted, key_path)
    if problem:
        raise _StepError(problem)
    config = _validated(
        FormConfig,
        {
            "alias": _widget(_scto_alias_name(form_id), ""),
            "form_id": form_id,
            "server": connection["server"],
            "username": connection.get("username") or None,
            "private_key": key_path or None,
            "save_to": _widget("scto_save_to") or None,
            "attachments": bool(_widget("scto_media", False)),
        },
    )
    _check_alias_free(project_id, config.alias)
    return {**config.model_dump(), "form_title": title}


def _draft_surveycto(project_id: str) -> dict:
    draft = {}
    connection = _surveycto_connections(project_id).get(_widget("scto_server"))
    if connection:
        draft["server"] = connection["server"]
    form_id = _widget("scto_form")
    if form_id:
        draft["form_id"] = form_id
        draft |= _drafted(
            {
                "alias": _scto_alias_name(form_id),
                "private_key": "scto_key",
                "save_to": "scto_save_to",
                "attachments": "scto_media",
            }
        )
    return draft


def _render_form_choice(project_id: str, connection: dict, values: dict):
    """Render the form picker; return the chosen form or ``None``."""
    forms = _server_forms(project_id, connection)
    ids = list(forms)
    stored = values.get("form_id")
    form_id = st.selectbox(
        "Form",
        options=ids,
        index=ids.index(stored) if stored in ids else None,
        format_func=lambda fid: f"{fid} ({forms[fid][1]})",
        placeholder="Choose a form",
        key=_key("scto_form"),
    )
    return forms.get(form_id)


def _render_surveycto_step(project_id: str) -> None:
    values = _state()["values"]
    connections = _surveycto_connections(project_id)
    if not connections:
        st.warning(
            "No SurveyCTO server is connected. Close this dialog and add one "
            "under **Connections**.",
            icon=":material/key_off:",
        )
        _render_nav(project_id, _collect_surveycto, dict, disabled=True)
        return

    names = list(connections)
    default = next(
        (
            i
            for i, name in enumerate(names)
            if connections[name]["server"] == values.get("server")
        ),
        0 if len(names) == 1 else None,
    )
    name = st.selectbox("Server", options=names, index=default, key=_key("scto_server"))
    form = _render_form_choice(project_id, connections[name], values) if name else None
    ready = _render_form_fields(form, values) if form else False
    _render_nav(
        project_id,
        _collect_surveycto,
        lambda: _draft_surveycto(project_id),
        disabled=not ready,
    )


# Review step


def review_items(source: str, values: dict) -> list[tuple[str, str]]:
    """Return the Review step's summary as (label, value) pairs."""
    items = [("Source", SOURCE_CHOICES[source]), ("Alias", values["alias"])]
    if source == SURVEYCTO_SOURCE:
        title = values.get("form_title")
        form = f"{values['form_id']} ({title})" if title else values["form_id"]
        items += [
            ("Server", values["server"]),
            ("Form", form),
            ("Private key", values.get("private_key") or "None"),
            ("Also save to", values.get("save_to") or "Not saved elsewhere"),
            ("Media", "Downloaded" if values.get("attachments") else "Not downloaded"),
        ]
    else:
        items.append(("File", values["filename"]))
        if values.get("sheet_name"):
            items.append(("Sheet", values["sheet_name"]))
    return items


def _save(project_id: str) -> None:
    state = _state()
    values = state["values"]
    if state["source"] == SURVEYCTO_SOURCE:
        config = FormConfig.model_validate(values, context=STORED_NAME)
        save_surveycto_dataset(project_id, config, edit=state["edit"])
    else:
        config = FileConfig.model_validate(values, context=STORED_NAME)
        save_local_dataset(project_id, config, edit=state["edit"])


def _render_review_step(project_id: str) -> None:
    state = _state()
    with st.container(border=True):
        for label, value in review_items(state["source"], state["values"]):
            with st.container(horizontal=True, gap="medium"):
                st.markdown(f":gray[{label}]", width=120)
                st.markdown(value)
    st.caption(
        "Saving updates this dataset's settings."
        if state["edit"]
        else REGISTER_ONLY_NOTE
    )

    with st.container(horizontal=True, horizontal_alignment="distribute"):
        _render_back()
        saved = st.button(
            "Save changes" if state["edit"] else "Add dataset",
            type="primary",
            key=_key("save"),
        )
    if not saved:
        return
    alias = state["values"]["alias"]
    try:
        _save(project_id)
    except (ValidationError, ValueError, duckdb.Error) as e:
        logger.exception("Could not save dataset %s", alias)
        st.error(f"Could not save {alias}: {e}")
        return
    del st.session_state[DIALOG_STATE]
    queue_notice(
        NOTICE_SCOPE, "toast", f"{'Updated' if state['edit'] else 'Added'} {alias}"
    )
    # A full rerun closes the dialog and shows the new row.
    st.rerun()


def _render_dialog(project_id: str) -> None:
    state = _state()
    _render_stepper(state["step"])
    if state["step"] == STEP_SOURCE:
        _render_source_step()
    elif state["step"] == STEP_REVIEW:
        _render_review_step(project_id)
    elif state["source"] == SURVEYCTO_SOURCE:
        _render_surveycto_step(project_id)
    else:
        _render_local_step(project_id)


@st.dialog("Add dataset", width="large")
def _add_dialog(project_id: str) -> None:
    _render_dialog(project_id)


@st.dialog("Edit dataset", width="large")
def _edit_dialog(project_id: str) -> None:
    _render_dialog(project_id)


def open_add_dialog(project_id: str) -> None:
    """Open the add dialog at its first step."""
    _start({"step": STEP_SOURCE, "edit": False, "source": None, "values": {}})
    _add_dialog(project_id)


_EDIT_FIELDS = (
    "alias",
    "filename",
    "sheet_name",
    "server",
    "username",
    "form_id",
    "private_key",
    "save_to",
    "attachments",
)


def open_edit_dialog(project_id: str, entry: dict) -> None:
    """Open the dialog at its Connection step, filled in from an import-log row."""
    values = {
        field: "" if entry.get(field) is None else entry[field]
        for field in _EDIT_FIELDS
    }
    _start(
        {
            "step": STEP_CONNECTION,
            "edit": True,
            "source": entry["source"],
            "values": values,
        }
    )
    _edit_dialog(project_id)


def show_open_dialog(project_id: str) -> None:
    """Show the add or edit dialog again if one was opened and not saved.

    Streamlit reruns only the dialog while it's open, so the page doesn't need
    this. AppTest reruns the whole script, so tests call it to keep the dialog.
    """
    state = st.session_state.get(DIALOG_STATE)
    if state:
        (_edit_dialog if state["edit"] else _add_dialog)(project_id)
