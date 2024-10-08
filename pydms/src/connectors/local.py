<<<<<<< HEAD
import os
import re
import tempfile
import time
import zipfile

import pandas as pd
import streamlit as st

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
<<<<<<< HEAD
=======
from io import StringIO
import streamlit as st
import pandas as pd
import os
import re
import zipfile

# --- Get List of sheet from excel ---#

def get_excel_sheet_names(file_path: str) -> list:
    
	"""
	SOURCES:
	Code is from the following source:
	https://stackoverflow.com/questions/20105118/extracting-list-of-sheet-names-from-openpyxl

	Import an excel file and return the list of sheet names

	PARAMS:
	-------
	file_path: str : path to the excel file
    """
>>>>>>> a279fb4 (restructured)

	sheets = []
	with zipfile.ZipFile(file_path, 'r') as zip_ref: xml = zip_ref.read("xl/workbook.xml").decode("utf-8")
	for s_tag in  re.findall("<sheet [^>]*", xml) : sheets.append(  re.search('name="[^"]*', s_tag).group(0)[6:])
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
	return sheets
=======
	return sheets
>>>>>>> fa2837e (restructured)
=======
	return sheets
=======
    sheets = []
    with zipfile.ZipFile(file_path, "r") as zip_ref:
        xml = zip_ref.read("xl/workbook.xml").decode("utf-8")
    for s_tag in re.findall("<sheet [^>]*", xml):
        sheets.append(re.search('name="[^"]*', s_tag).group(0)[6:])
    return sheets
>>>>>>> 5efff5e (format and lint pydms/src/connectors)


# --- Create empty Dataframe ---#


def local_load_files() -> pd.DataFrame:
    """Load files from last session or return empty dataframe.

    PARAMS:
    -------
    return: pandas dataframe of file list
    """
    # load form details from last session
    try:
        file = pd.read_json("cache/pyDMS_local_files_cache.json")
        form_inputs = file.to_dict()
        return pd.DataFrame(form_inputs)

    # if file not found, return empty dataframe
    except FileNotFoundError:
        return pd.DataFrame(columns=["alias", "load", "type", "filename", "sheet name"])


# --- Read data from file ---#


def local_read_data(filename: str, sheet_name: str = None) -> pd.DataFrame:
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
        data = pd.read_csv(filename)
    elif fileext in ["xlsx", "xls"]:
        data = pd.read_excel(filename, sheet_name=sheet_name)
    elif fileext == "json":
        data = pd.read_json(filename)
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


def local_add_form() -> None:
    """Form for adding a file from local storage.

    PARAMS:
    -------
    None

    Returns
    -------
    None

    """
    st.image("asserts/storage.png", width=100)

    st.markdown("Add a new file")
    # input file alias
    local_file_alias = st.text_input(
        label="alias*", help="Enter a unique name for the file"
    )

    # file uploader. Limit to 1 file and allow only file types selected
    local_added_file = st.text_input(
        label="file path*", help="Add full file name and path. eg. C:/data/survey.dta"
    )

    if local_added_file:
        # get file extension from filename
        local_added_file_ext = local_added_file.split(".")[-1]

        # check file validity
        if not os.path.isfile(local_added_file):
            st.warning("File not found. Please check the file path")
        elif local_added_file_ext not in ["csv", "xlsx", "xls", "json", "dta"]:
            st.warning("Invalid file type. Please upload a valid file type")
        elif local_added_file_ext in ["xlsx", "xls"]:
            sheets = get_excel_sheet_names(local_added_file)
            local_added_file_sheet_name = st.selectbox(
                label="Sheet Name", options=sheets
            )
        else:
            local_added_file_sheet_name = None

    # add a submit button
    local_add_file = st.button(
        "Add File",
        type="primary",
        use_container_width=True,
        key="add_file_key",
        disabled=not local_added_file and not local_file_alias,
    )

    st.markdown("**required*")

    # if submit (local_add_file) button is clicked

    if local_add_file:
        new_file = pd.DataFrame(
            data=[
                [
                    local_file_alias,
                    True,
                    local_added_file_ext,
                    local_added_file,
                    local_added_file_sheet_name,
                ]
            ],
            columns=["alias", "load", "type", "filename", "sheet name"],
        )

        # cst.write(new_file)

        st.session_state.local_files = pd.concat(
            [st.session_state.local_files, new_file], ignore_index=True
        )


# --- Load data from local storage ---#


def local_load_action(local_inputs: pd.DataFrame) -> None:
    """Load data from local storage.

    PARAMS:
    -------
    local_inputs: pd.DataFrame : file list dataframe

    Returns
    -------
    None

    """
    # remove empty rows
    local_inputs = local_inputs[local_inputs["load"] == True]  # noqa: E712

    # Check data and flag errors
    if local_inputs.empty:
        st.warning("No data selected for download. Please select data to download")
        st.stop()

    else:
        local_files_count = len(local_inputs.index)

        # download data
        for i in range(0, local_files_count):
            if f"local_raw_data{i}" in st.session_state:
                local_filename = local_inputs["filename"][i]
                local_sheet_name = local_inputs["sheet name"][i]

                st.session_state[f"local_raw_data{i}"] = local_read_data(
                    local_filename, local_sheet_name
                )
                time.sleep(1)

        # modify session state for preview
        st.session_state.local_show_preview = True

<<<<<<< HEAD
		st.success(f'{local_files_count} Datasets loaded from local storage')
>>>>>>> 9b1a5b9 (prep)
=======
        st.success(f"{local_files_count} Datasets loaded from local storage")
>>>>>>> 5efff5e (format and lint pydms/src/connectors)
=======
	return sheets
>>>>>>> a279fb4 (restructured)
