import os
import re
import tempfile
import zipfile

import duckdb
import pandas as pd
import polars as pl
import streamlit as st

from src.connectors import get_import_cache

# --- Get List of sheet from excel ---#


def get_excel_sheet_names(file_path: str) -> list:
    """Import an excel file and return the list of sheet names.

    SOURCES:
    Code is from the following source:
    https://stackoverflow.com/questions/20105118/extracting-list-of-sheet-names-from-openpyxl

    PARAMS:
    -------
    file_path: str : path to the excel file
    """
    sheets = []
    with zipfile.ZipFile(file_path, "r") as zip_ref:
        xml = zip_ref.read("xl/workbook.xml").decode("utf-8")
    for s_tag in re.findall("<sheet [^>]*", xml):
        sheets.append(re.search('name="[^"]*', s_tag).group(0)[6:])
    return sheets


# --- Create empty Dataframe ---#


def local_load_files() -> pd.DataFrame:
    """Load files from last session or return empty dataframe.

    PARAMS:
    -------
    return: pandas dataframe of file list
    """
    # load form details from last session
    try:
        file = pd.read_json("cache/settings/pyDMS_local_files_cache.json")
        form_inputs = file.to_dict()
        return pd.DataFrame(form_inputs)

    # if file not found, return empty dataframe
    except FileNotFoundError:
        return pd.DataFrame(columns=["alias", "load", "type", "filename", "sheet name"])


# --- Read data from file ---#


def local_read_data(filename: str, sheet_name: str | None = None) -> pl.DataFrame:
    """Import data from a file.

    PARAMS:
    -------
    filename: str : path to the file
    sheet_name: str : name of the sheet to import (only for excel files)

    Returns
    -------
    data: pd.DataFrame : imported data

    """
    # get file extension
    fileext = filename.split(".")[-1]

    # import file depending on the file extension
    if fileext == "csv":
        data = pd.read_csv(filename, encoding="utf-8")
    elif fileext in ["xlsx", "xls"]:
        data = pd.read_excel(filename, sheet_name=sheet_name, engine="openpyxl")
    elif fileext == "json":
        data = pd.read_json(filename, encoding="utf-8")
    elif fileext == "dta":
        data = pd.read_stata(filename)

    return data


# --- get file name and path from st.file_uploader ---#


def get_file_path(file_uploader: object) -> str:
    """Get file path from st.file_uploader.

    PARAMS:
    -------
    file_uploader: object : st.file_uploader object

    Returns
    -------
    file_path: str : path to the file

    """
    temp_dir = tempfile.mkdtemp()
    path = os.path.join(temp_dir, file_uploader.name)

    return path


# --- FORM for Adding file from local storage ---#


def local_add_form(
    project_id: str, edit_mode: bool = False, defaults: dict | None = None
) -> None:
    """Form for adding a file from local storage.

    PARAMS:
    -------
    None

    Returns
    -------
    None

    """
    mode = "edit" if edit_mode else "add"

    def valid_alias(alias: str) -> bool:
        """Validate alias for uniqueness and length."""
        if not alias:
            st.error("Alias cannot be empty")
            return False
        if len(alias) > 20:
            st.error("Alias must be a maximum of 20 characters")
            return False
        return True

    def valid_file_path(file_path: str) -> bool:
        """Validate file path for existence and type."""
        if not file_path:
            st.error("File path cannot be empty")
            return False
        if not os.path.isfile(file_path):
            st.error("File not found. Please check the file path")
            return False
        valid_extensions = ["csv", "xlsx", "xls", "json", "dta"]
        if file_path.split(".")[-1] not in valid_extensions:
            st.error("Invalid file type. Please upload a valid file type")
            return False
        return True

    st.image("assets/hard-disk.png", width=100)
    st.subheader("Add File from Local Storage")

    if edit_mode:
        st.info("You are in edit mode. Please modify the file details below.")
        # load the current file details from the defaults
        default_local_file_alias = defaults.get("alias", "")
        default_local_added_file = defaults.get("filename", "")
        default_local_added_file_sheet_name = defaults.get("sheet_name", "")

    local_file_alias = st.text_input(
        label="alias*",
        help="Enter a unique, short, descriptive name for the file",
        placeholder=default_local_file_alias if edit_mode else "",
        disabled=edit_mode,
    )
    if local_file_alias:
        valid_alias(local_file_alias)

    # file uploader. Limit to 1 file and allow only file types selected
    local_added_file = st.text_input(
        label="file path*",
        help="Add full file name and path. eg. C:/data/survey.dta",
        placeholder=default_local_added_file if edit_mode else "",
    )

    if local_added_file and valid_file_path(local_added_file):
        local_added_file_ext = local_added_file.split(".")[-1]

        if local_added_file_ext in ["xlsx", "xls"]:
            sheets = get_excel_sheet_names(local_added_file)

            # check if default sheetname exists in the list of sheets
            if (
                default_local_added_file_sheet_name
                and default_local_added_file_sheet_name in sheets
            ):
                # get index of the default sheet name or set to first sheet
                default_sheet_index = sheets.index(default_local_added_file_sheet_name)
            else:
                default_sheet_index = 0

            local_added_file_sheet_name = st.selectbox(
                label="Sheet Name",
                options=sheets,
                index=default_sheet_index,
            )
        else:
            local_added_file_sheet_name = ""
    else:
        local_added_file_sheet_name = ""

    # add a submit button
    local_add_btn = st.button(
        "Add File",
        type="primary",
        use_container_width=True,
        key=f"add_file_key{mode}",
        disabled=not local_added_file and not local_file_alias,
    )

    st.markdown("**required*")

    # if submit (local_add_file) button is clicked
    if local_add_btn:
        cache_file = get_import_cache(project_id)
        if edit_mode:
            # update the row in the cache file
            cache_file = cache_file.with_columns(
                pl.when(pl.col("alias") == default_local_file_alias)
                .then(pl.lit(local_added_file))
                .otherwise(pl.col("filename"))
                .alias("filename"),
            )

        else:
            # create a new row with the file details
            new_row = {
                "refresh": True,
                "load": True,
                "source": "local storage",
                "alias": local_file_alias,
                "filename": local_added_file,
                "sheet_name": local_added_file_sheet_name,
                "server": "",
                "form_id": "",
                "private_key": "",
                "save_to": "",
                "attachments": None,
            }

            # append the new row to the cache file
            cache_file = pl.concat(
                [cache_file, pl.DataFrame([new_row])], how="vertical"
            )

        # save the updated cache file
        cache_file.write_json(f"cache/{project_id}/settings/import_cache.json")


# --- Load data from local storage ---#


def local_load_action(
    project_id: str, data_index: int, alias: str, filename: str, sheet_name: str | None
) -> None:
    """Load data from local storage.

    PARAMS:
    -------
    project_id: str : project ID
    data_index: int : index of the data to load
    alias: str : alias for the data
    filename: str : path to the file
    sheet_name: str : name of the sheet to import (if applicable)

    Returns
    -------
    None
    """
    # read data from file
    data: pl.DataFrame = local_read_data(filename, sheet_name)  # noqa: F841

    # create a new duckdb database in the cache folder and write the data to it
    db_path: str = f"cache/{project_id}/data"
    with duckdb.connect(f"{db_path}/raw.duckdb") as conn:
        conn.execute(f"CREATE OR REPLACE TABLE raw{data_index} AS SELECT * FROM data")
    st.success(f"Data loaded successfully from {filename} into {alias} table.")
