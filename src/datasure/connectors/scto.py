import contextlib
import datetime
import json
import os
import re
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import polars as pl
import pysurveycto
import requests
import streamlit as st

from datasure.utils import duckdb_get_table, duckdb_save_table, get_cache_path

# --- SurveyCTO Server Connect Button Click Action --- #


# --- Get cache data for SurveyCTO serves --- #
def scto_get_server_cache(project_id: str) -> dict:
    """Get cache data for SurveyCTO server.

    PARAMS:
    -------
    servername: SurveyCTO server name

    Return:
    ------
    pandas dataframe of cached data or empty dataframe if file not found

    """
    try:
        scto_file = get_cache_path(project_id, "settings", "scto.json")
        with open(scto_file) as file:
            file = json.load(file)

    except FileNotFoundError:
        file = {}

    return file


def scto_server_connect(servername: str, username: str, password: str) -> str:
    """Validate SurveyCTO account details and load user data.

    PARAMS
    ------
    servername: SurveyCTO server name
    username: SurveyCTO account username (email address)
    password: SurveyCTO account password

    Return:
    ------
    SurveyCTO object

    """
    # check that required fields are not empty
    if not servername or not username or not password:
        st.warning("Complete all required fields.")
        st.stop()

    # check that servername is valid
    elif not re.fullmatch(r"^[a-z][a-z0-9]{1,63}$", servername):
        st.warning("Invalid server name.")
        st.stop()

    # check that user field is a valid email
    elif not re.fullmatch(
        r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,63}\.[A-Za-z]{2,7}$", username
    ):
        st.warning("Invalid email address")
        st.stop()

    # if all fields are valid, create SurveyCTO object
    # Future Improvements: After SurveyCTO API improvements, add try-except
    # block to catch connection errors
    else:
        scto = pysurveycto.SurveyCTOObject(servername, username, password)
        st.success("Connection successful")
        return scto


# --- SurveyCTO load form details --- #


def scto_load_forms(servername: str) -> pd.DataFrame:
    """Load saved form details from previous session.

    PARAMS:
    -------
    servername: SurveyCTO server name

    return: pandas dataframe of form details or empty dataframe if file not found
    """
    # load form details from last session
    try:
        cache_file = get_cache_path(f"{servername}_DataSure_forms_cache.json")
        file = pd.read_json(cache_file)
        form_inputs = file.to_dict()

        return pd.DataFrame(form_inputs)

    # if file not found, return empty dataframe
    except FileNotFoundError:
        return pd.DataFrame([])


# --- Import SurveyCTO KEY --- #


def scto_import_key(key_file: str) -> str:
    """Import SurveyCTO key from file.

    PARAMS:
    -------
    key_file: path to key file

    Return:
    ------
    key: SurveyCTO key

    """
    # check if key file exist
    try:
        with open(key_file) as file:
            key = file.read()
            return key

    except FileNotFoundError:
        st.warning("Key file not found.")
        st.stop()


# --- Load existing SurveyCTO in storage --- #


def scto_load_existing_data(saveas: str) -> tuple:
    """Load existing SurveyCTO data from storage.

    PARAMS:
    -------
    saveas: path to saved data

    Return:
    ------
    scto_data: pandas dataframe of existing data
    oldest_completion_date: datetime of oldest completion date in the dataset

    Returns tuple of (scto_data, oldest_completion_date)
    Returns empty dataframe and datetime(2024, 1, 1, 13, 40, 40) if file not
    found or saveas not specified

    """
    try:
        scto_data = pd.DataFrame(pd.read_csv(saveas))
    except FileNotFoundError:
        return (pd.DataFrame(), datetime.datetime(2024, 1, 1, 13, 40, 40))
    except pd.errors.EmptyDataError:
        return (pd.DataFrame(), datetime.datetime(2024, 1, 1, 13, 40, 40))
    else:
        # convert the SubmissionDate field to datetime
        scto_data["SubmissionDate"] = pd.to_datetime(scto_data["SubmissionDate"])

        # get the latest date in the dataset
        return (scto_data, scto_data["SubmissionDate"].max())


# --- Import SurveyCTO form definition --- #


def scto_get_xls(scto: object, form_id: str) -> tuple:
    """Import SurveyCTO form definition.

    PARAMS:
    -------
    scto: SurveyCTO object
    form_id: SurveyCTO form ID

    Return:
    ------
    questions: pandas dataframe of questions
    choices: pandas dataframe of choices

    Returns tuple of (questions, choices)

    """
    # download form definition
    try:
        scto_form = scto.get_form_definition(form_id)
    # if connection error, raise warning and stop
    except requests.ConnectionError as conn_err:
        st.warning(f"{conn_err}. Check your internet connection and try again.")
        st.stop()

    questions = pd.DataFrame(
        scto_form["fieldsRowsAndColumns"][1:],
        columns=scto_form["fieldsRowsAndColumns"][0],
    )

    choices = pd.DataFrame(
        scto_form["choicesRowsAndColumns"][1:],
        columns=scto_form["choicesRowsAndColumns"][0],
    )

    return (questions, choices)


# --- Get List of Repeat Fields in SurveyCTO Form --- #
def scto_get_repeat_fields(questions: pd.DataFrame) -> list:
    """Get list of repeat fields in SurveyCTO form.

    PARAMS:
    -------
    questions: pandas dataframe of questions

    Return:
    ------
    list of repeat fields

    """
    fields: pd.DataFrame = questions[["type", "name"]].copy(deep=True)

    repeat_fields = []
    begin_count = 0
    end_count = 0

    # Iterate through rows
    for _, row in fields.iterrows():
        if row["type"] == "begin repeat":
            begin_count += 1
            continue  # Skip to next row
        elif row["type"] == "end repeat":
            end_count += 1
            continue  # Skip to next row

        # if begin_count is greater than end_count, add field to repeat_fields
        if (
            len(row["name"]) > 1
            and (begin_count > end_count)
            and row["type"] not in ["begin group", "end group"]
        ):
            repeat_fields.append(row["name"])

    return repeat_fields


# --- Get repeat columns from repeat fields --- #


def scto_get_repeat_cols(field: str, data_cols: list) -> list:
    """Get repeat columns from repeat fields.

    PARAMS:
    -------
    field: field name
    repeat_fields: list of repeat fields

    Return:
    ------
    list of repeat columns

    """
    regex = r"\b" + field + r"_[0-9]+_{,1}[0-9]*_{,1}[0-9]*\b"
    cols = [x for x in data_cols if re.fullmatch(regex, x)]

    cols = cols or field.split()
    return cols


# --- Download SurveyCTO Media Files --- #


def scto_download_media(
    scto: object,
    media_fields: list,
    repeat_fields: list,
    new_data: pd.DataFrame,
    media_folder: str,
    key: str | None = None,
) -> None:
    """Download media files from SurveyCTO.

    PARAMS:
    -------
    scto: SurveyCTO object
    media_fields: list of media fields
    repeat_fields: list of repeat fields
    new_data: pandas dataframe of new data
    media_folder: path to save media files
    key: SurveyCTO encryption key (optional)

    Return:
    ------
    None

    """
    # loop through media fields and download media files
    for field in media_fields:
        # get repeat group columns
        cols = scto_get_repeat_cols(field, repeat_fields)

        # get media files
        for col in cols:
            media_data = new_data[new_data[col].notna()]
            media_data = media_data[[col, "KEY"]].reset_index()
            media_count = len(media_data.index)

            if media_count > 0:
                media_progress_bar = st.progress(
                    0, text=f"Downloading media files for {col} ..."
                )

                for j in range(0, len(media_data.index)):
                    # get url at index j or row['name']

                    url = media_data[col][j]
                    submission_key = media_data["KEY"][j].replace("uuid:", "")
                    fileext = url.split(".")[-1] or "csv"
                    filename = col + "_" + submission_key + "." + fileext
                    media_file = scto.get_attachment(url, key=key)

                    # save media files
                    with open(f"{media_folder}/{filename}", "wb") as file:
                        file.write(media_file)
                    progress = round(((j + 1) / media_count) * 100, 2)  # noqa: F841
                    media_progress_bar.progress(
                        (j + 1) / media_count,
                        text=f"Downloading media files for {col} ... % complete",
                    )


# Using pysurveycto library, import survey data from SurveyCTO
def scto_import_data(
    project_id: str,
    alias: str,
    form_id: str,
    refresh: bool = False,
    key: str | None = None,
    saveas: str | None = None,
    attachments: bool = False,
) -> int:
    """Import SurveyCTO data.

    Import SurveyCTO Data and save to file, adjust data types based on XLS
    form definition, and import media files.

    PARAMS:
    -------
    scto: SurveyCTO object
    form_id: SurveyCTO form ID
    key: SurveyCTO encryption key
    server_dataset: boolean, True if using server dataset
    saveas: string, path to save dataset
    media: boolean, True if downloading media files

    Return:
    ------
    scto_data: pandas dataframe of imported data
    new_data_count: number of new data imported

    Returns tuple of (scto_data, new_data_count)

    """
    scto_login = scto_get_server_cache(project_id)
    scto = scto_server_connect(
        servername=scto_login["server"],
        username=scto_login["user"],
        password=scto_login["password"],
    )
    # check if form id is for a server dataset
    try:
        scto_data = scto.get_server_dataset(form_id)
        scto_data = pl.read_csv(StringIO(scto_data), encoding="utf-8")

    except requests.HTTPError:
        # key is not missing, import encryption key from key file
        if key:
            key = scto_import_key(key)

        # if saves is not missing, check if file exist and load
        scto_data, oldest_completion_date = scto_load_existing_data(saveas)

        # if new data is not requested, return existing data
        if not refresh:
            return 0

        # Download new data (from the oldest completion date)
        try:
            new_data: json = scto.get_form_data(
                form_id=form_id,
                format="json",
                oldest_completion_date=oldest_completion_date,
                key=key,
            )
        except requests.ConnectionError as conn_err:
            st.warning(f"{conn_err}. Check your internet connection and try again.")
            st.stop()
        except requests.HTTPError as http_error:
            st.warning(f"{http_error}")
            if http_error.response.status_code == 401:
                st.warning("Unauthorized access. Check your credentials and try again.")
            elif http_error.response.status_code == 403:
                st.warning("Form not found. Check form ID and try again.")
            elif http_error.response.status_code == 500:
                st.warning("Server error. Try again later.")
            else:
                st.warning("An error occurred. Try again later.")

            st.stop()

        new_data: pd.DataFrame = pd.DataFrame(new_data)
        new_data_count = new_data.shape[0]

        # if scto_data is not empty, append new_data to scto_data, else set
        # scto_data to new_data
        if not scto_data.empty:
            scto_data = pd.concat([scto_data, new_data], ignore_index=True)
        else:
            scto_data = new_data
        new_data_count: int = len(new_data.index)

        # download form definition
        questions, _ = scto_get_xls(scto, form_id)
        questions = questions[questions["disabled"] != "yes"]

        # Mark all repeat fields in the XLS file

        repeat_fields = scto_get_repeat_fields(questions)

        # convert default str datetime cols to datetime
        for col in ["CompletionDate", "SubmissionDate", "starttime", "endtime"]:
            if col in scto_data.columns:
                with contextlib.suppress(ValueError, TypeError):
                    scto_data[col] = pd.to_datetime(scto_data[col], format="mixed")

        # convert default numeric variables to numeric
        for col in ["duration", "formdef_version"]:
            if col in scto_data.columns:
                with contextlib.suppress(ValueError, TypeError):
                    scto_data[col] = pd.to_numeric(scto_data[col])

        # loop through fields and convert numeric variables to appropriate
        # data types
        fields: pd.DataFrame = questions[["type", "name"]]
        scto_data_cols = list(scto_data.columns)
        for _, row in fields.iterrows():
            # check if field is a repeat group col, if yes, get all repeat
            # columns
            if row["name"] in repeat_fields:
                cols = scto_get_repeat_cols(field=row["name"], data_cols=scto_data_cols)
            else:
                cols = [row["name"]]
            cols = [col for col in cols if col in scto_data.columns]
            if not cols:
                continue  # skip if no columns found

            for col in cols:
                if row["type"] in ["date", "datetime", "time"]:
                    scto_data[col] = scto_data[col].astype("datetime64[ns]")
                elif row["type"] in ["integer", "decimal"]:
                    # check if column is numeric, if not, convert to numeric
                    if not pd.api.types.is_numeric_dtype(scto_data[col]):
                        scto_data[col] = pd.to_numeric(scto_data[col], errors="coerce")
                elif row["type"] == "note":
                    scto_data.drop(columns=col, axis=1, inplace=True)
                else:
                    # for all other types, ignore
                    pass

        # -- download media files --#

        # get a list of media fields form fields
        if attachments:
            media_fields = fields[
                fields["type"].isin(
                    [
                        "image",
                        "audio",
                        "video",
                        "file",
                        "comments",
                        "text audit",
                        "audio audit",
                        "sensor stream",
                    ]
                )
            ]["name"].tolist()

            # use default saveas folder as media folder, removing filename
            media_folder = saveas.split("/")
            media_folder = "/".join(media_folder[:-1]) + "/media"

            # check if director exist, create if not
            if not os.path.exists(media_folder):
                os.makedirs(media_folder)

            # download media files
            scto_download_media(
                scto, media_fields, repeat_fields, new_data, media_folder, key
            )

    # save dataset
    if saveas:
        scto_data.to_csv(saveas, index=False)

    # save dataset to DuckDB
    # save data to DuckDB
    duckdb_save_table(
        project_id,
        scto_data,
        alias=alias,
        db_name="raw",
    )

    return new_data_count


def scto_add_form(
    project_id: str,
    edit_mode: bool = False,
    defaults: dict | None = None,
) -> None:
    """Form for adding a SurveyCTO form to the project.

    PARAMS:
    -------
    project_id: str : project ID
    edit_mode: bool : True if editing an existing form
    defaults: dict : default values for the form fields

    Returns
    -------
    None

    """
    if edit_mode:
        # get default values from defaults dict
        default_server = defaults.get("server", "")
        default_form_id = defaults.get("form_id", "")
        default_key = defaults.get("key", "")
        default_saveas = defaults.get("saveas", "")

    # import server list from cache file
    try:
        scto_file = get_cache_path(project_id, "settings", "scto.json")
        with open(scto_file) as file:
            server_cache = json.load(file)
            server_list = server_cache.get("server", [])
    except FileNotFoundError:
        # if file not found, create empty list
        server_list = []

    if not server_list:
        st.warning(
            "No SurveyCTO servers found. Please connect to a server first or add a server."
        )
        return

    # create form for adding SurveyCTO form
    with st.form(key="scto_form"):
        # Get the path to the assets directory relative to the package
        assets_dir = Path(__file__).parent.parent / "assets"
        image_path = assets_dir / "SurveyCTO-Logo-CMYK.png"
        st.image(str(image_path), width=200)

        alias = st.text_input(
            label="Alias*",
            help="Enter alias for the form. eg. 'my_survey_form'",
        )

        scto_server = st.selectbox(
            label="Server*",
            options=server_list,
            index=0 if not edit_mode else default_server,
            help="Select SurveyCTO server",
        )

        scto_form_id = st.text_input(
            label="Form ID*",
            value=default_form_id if edit_mode else "",
            help="Enter SurveyCTO Form ID",
        )
        scto_key = st.text_input(
            label="Encryption Key",
            value=default_key if edit_mode else "",
            help="Enter SurveyCTO encryption key. Optional if using server dataset",
        )
        scto_saveas = st.text_input(
            label="Save as",
            value=default_saveas if edit_mode else "",
            help="Enter path to save dataset. eg. data/surveycto_data.csv",
        )

        # mark required fields
        st.markdown("**required*")

        # create submit button
        submit_button = st.form_submit_button(label="Add Form")

        if submit_button:
            # check that alias provided is not an exiting alias
            import_log = duckdb_get_table(
                project_id, alias="import_log", db_name="logs"
            )
            if alias in import_log["alias"].to_list():
                st.error(
                    f"Alias '{alias}' already exists. Please choose a different alias."
                )
            else:
                new_form = {
                    "refresh": True,
                    "load": True,
                    "source": "SurveyCTO",
                    "alias": alias,
                    "filename": "",
                    "sheet_name": "",
                    "server": scto_server,
                    "form_id": scto_form_id,
                    "private_key": scto_key,
                    "save_to": scto_saveas,
                    "attachments": False,
                }

                import_log = pl.concat(
                    [import_log, pl.DataFrame([new_form])],
                    how="vertical",
                )

                duckdb_save_table(
                    project_id=project_id,
                    table_data=import_log,
                    alias="import_log",
                    db_name="logs",
                )


def valid_server_name(servername: str) -> bool:
    """Check if server name is valid.

    PARAMS:
    -------
    servername: SurveyCTO server name

    Return:
    ------
    bool: True if server name is valid, False otherwise

    """
    return bool(re.fullmatch(r"\b[a-z][a-z0-9]+\b", servername))


def valid_email(email: str) -> bool:
    """Check if email is valid.

    PARAMS:
    -------
    email: SurveyCTO account email address

    Return:
    ------
    bool: True if email is valid, False otherwise

    """
    return bool(
        re.fullmatch(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", email)
    )


# Configure SurveyCTO form
def scto_login_form(project_id: str) -> None:
    """Create input form for SurveyCTO login.

    PARAMS:
    ------

    None

    Returns
    -------
    pd.DataFrame - Dataframe of forms from previous session or empty dataset

    """
    # define server details input
    with st.form(key="server_form"):
        # Get the path to the assets directory relative to the package
        assets_dir = Path(__file__).parent.parent / "assets"
        image_path = assets_dir / "SurveyCTO-Logo-CMYK.png"
        st.image(str(image_path), width=200)

        st.markdown("*Server Details:*")

        scto_server_name = st.text_input(
            label="Server name*",
            help="Enter SurveyCTO server name. eg. girlpower",
        )

        scto_server_user = st.text_input(
            label="Email address*",
            help="Enter valid email username",
        )

        scto_server_password = st.text_input(label="Password*", type="password")

        # mark required fields
        st.markdown("**required*")

        # create submit button
        submit_button = st.form_submit_button(
            label="Connect to server",
            help="Click to connect to SurveyCTO server",
        )

        if submit_button:
            # validae server name and email
            if not valid_server_name(scto_server_name):
                st.warning("Invalid server name. Please enter a valid server name.")
                st.stop()
            if not valid_email(scto_server_user):
                st.warning("Invalid email address. Please enter a valid email address.")
                st.stop()

            # update cache file dict with usernamr using scto_server_name as key
            server_details = {
                "server": scto_server_name,
                "user": scto_server_user,
                "password": scto_server_password,
            }

            # save server cache to file
            scto_file = get_cache_path(project_id, "settings", "scto.json")
            # Ensure parent directory exists
            scto_file.parent.mkdir(parents=True, exist_ok=True)
            with open(scto_file, "w") as file:
                json.dump(server_details, file)

            st.success(
                f"SurveyCTO Connection for {scto_server_name} added successfully"
            )


# --- SCTO Download button action --- #
def scto_download_action(project_id: str, form_inputs: pd.DataFrame) -> None:
    """Trigger Action to download SurveyCTO data based on form inputs.

    PARAMS:
    -------
    form_inputs: pandas dataframe of form inputs
    get_new_data: boolean, True if downloading new data

    Return:
    ------
    None

    """
    # Check data and flag errors
    if form_inputs.empty:
        st.warning("No data selected for download. Please select data to download")
        st.stop()

    form_inputs.reset_index(inplace=True)
    form_count = len(form_inputs.index)

    progress_bar = st.progress(0, text="Downloading from SurveyCTO ...")

    st.write(f"Downloading {form_count} datasets from SurveyCTO")

    # download data
    for i, row in enumerate(form_inputs.itertuples()):
        new_data_count = scto_import_data(
            project_id=project_id,
            alias=row.alias,
            form_id=row.form_id,
            refresh=row.refresh,
            key=row.private_key,
            saveas=row.save_to,
            attachments=row.attachments,
        )
        time.sleep(3)
        progress_bar.progress(
            (i + 1) / form_count,
            text=f"Download in progress...{i + 1}/{form_count}",
        )
        saveas = row.save_to
        if saveas is not None:
            st.write(
                f"{i + 1}/{form_count}: downloaded {new_data_count} new data successfully and saved as {saveas}"
            )
        else:
            st.write(f"{i + 1}/{form_count}: downloaded successfully")

    st.success("Data download complete")

    # modify session state for preview
    st.session_state.scto_show_preview = True
