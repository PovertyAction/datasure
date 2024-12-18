<<<<<<< HEAD
<<<<<<< HEAD
import os
import time

import pandas as pd
import streamlit as st

# --- Import details from prev session or create empty dataframe ---#


def script_load_files() -> pd.DataFrame:
    """Load files from last session or return empty dataframe.

    PARAMS:
    -------
    return: pandas dataframe of file list
    """
    # load form details from last session
    try:
        file = pd.read_json("cache/pyDMS_script_files_cache.json")
        form_inputs = file.to_dict()
        return pd.DataFrame(form_inputs)

    # if file not found, return empty dataframe
    except FileNotFoundError:
        return pd.DataFrame(columns=["alias", "load", "type", "filename", "dataset"])
=======
import streamlit as st
import pandas as pd
=======
>>>>>>> 291498b (format and lint pydms/src/connectors)
import os
import time

import pandas as pd
import streamlit as st

# --- Import details from prev session or create empty dataframe ---#


def script_load_files() -> pd.DataFrame:
<<<<<<< HEAD
	
	"""
	Load files from last session or return empty dataframe

	PARAMS:
	-------
	return: pandas dataframe of file list
	"""
	
	# load form details from last session
	try:
		file = pd.read_json('cache/pyDMS_script_files_cache.json')
		form_inputs = file.to_dict()
		return pd.DataFrame(form_inputs)

	# if file not found, return empty dataframe
	except FileNotFoundError:
		return pd.DataFrame(columns = ['alias', 'load', 'type', 'filename', 'dataset'])
>>>>>>> 495c39b (prep)
=======
    """Load files from last session or return empty dataframe.

    PARAMS:
    -------
    return: pandas dataframe of file list
    """
    # load form details from last session
    try:
        file = pd.read_json("cache/pyDMS_script_files_cache.json")
        form_inputs = file.to_dict()
        return pd.DataFrame(form_inputs)

    # if file not found, return empty dataframe
    except FileNotFoundError:
        return pd.DataFrame(columns=["alias", "load", "type", "filename", "dataset"])
>>>>>>> 291498b (format and lint pydms/src/connectors)


# --- FORM for adding new script --- #

<<<<<<< HEAD
<<<<<<< HEAD

def script_add_form() -> None:
    """Form for adding a new script.

    PARAMS:
    -------
    None

    Returns
    -------
    None

    """
    st.image("asserts/python.png", width=100)
    st.markdown("Add a python script")

    # input file alias
    script_alias = st.text_input(
        label="alias*", help="Enter a unique name for the file", key="script_alias_key"
    )

    # file uploader. Limit to 1 file and allow only file types selected
    added_script = st.text_input(
        label="file path*",
        help="Add full file name and path. eg. C:/data/kobo_import.py",
        key="added_script_key",
    )

    if added_script:
        # get file extension from filename
        added_script_ext = added_script.split(".")[-1]

        if not os.path.isfile(added_script):
            st.warning("File not found. Please enter a valid file path")
        elif added_script_ext != "py":
            st.warning("Invalid file type. Please upload a valid file type")

    # get name of dataset to input from script
    added_script_data = st.text_input(
        label="Dataset*",
        help="Specify the dataset to be loaded from script",
        key="added_script_data_key",
    )

    st.markdown("**required*")

    # add a submit button
    add_script_btn = st.button(
        "Add Script",
        type="primary",
        use_container_width=True,
        key="add_script_btn_key",
        disabled=not added_script or not script_alias or not added_script_data,
    )
    # add_file action
    if add_script_btn:
        new_script = pd.DataFrame(
            data=[
                [script_alias, True, added_script_ext, added_script, added_script_data]
            ],
            columns=["alias", "load", "type", "filename", "dataset"],
        )

        st.session_state.script_files = pd.concat(
            [st.session_state.script_files, new_script], ignore_index=True
        )


# --- Add Script Action --- #


def script_load_action(script_inputs: dict) -> None:
    """Load data from scripts based on the provided inputs.

    PARAMS:
    -------
    script_inputs: dict
        Dictionary containing script input details.

    Returns
    -------
    None

    """
    # remove empty rows
    script_inputs = script_inputs[script_inputs["load"] == True]  # noqa: E712

    # Check data and flag errors
    if script_inputs.empty:
        st.warning("No data selected for download. Please select data to download")
        st.stop()

    form_count = len(script_inputs.index)

    st.progress(0, text="Loading data From Script ...")

    st.write(f"Loading {form_count} datasets from Script")

    # download data
    for i in range(0, form_count):
        if f"script_raw_data{i}" in st.session_state:
            # get filename & path
            filename = script_inputs["filename"][i]
            # dataset = script_inputs["dataset"][i]

            with open(filename) as file:
                st.write("Name", exec(file.read()))

            # Check if the module has a DataFrame named {dataset}
            # if hasattr(exec_file, dataset):
            # st.session_state[f'script_raw_data{i}'] = getattr(exec_file, dataset)

            time.sleep(3)
            st.write(f"{i + 1}/{form_count}: Loaded successfully")

    st.success("Data load from scripts complete")

    # modify session state for preview
    st.session_state.scto_show_preview = True
=======
=======

>>>>>>> 291498b (format and lint pydms/src/connectors)
def script_add_form() -> None:
    """Form for adding a new script.

    PARAMS:
    -------
    None

    Returns
    -------
    None

    """
    st.image("asserts/python.png", width=100)
    st.markdown("Add a python script")

    # input file alias
    script_alias = st.text_input(
        label="alias*", help="Enter a unique name for the file", key="script_alias_key"
    )

    # file uploader. Limit to 1 file and allow only file types selected
    added_script = st.text_input(
        label="file path*",
        help="Add full file name and path. eg. C:/data/kobo_import.py",
        key="added_script_key",
    )

    if added_script:
        # get file extension from filename
        added_script_ext = added_script.split(".")[-1]

        if not os.path.isfile(added_script):
            st.warning("File not found. Please enter a valid file path")
        elif added_script_ext != "py":
            st.warning("Invalid file type. Please upload a valid file type")

    # get name of dataset to input from script
    added_script_data = st.text_input(
        label="Dataset*",
        help="Specify the dataset to be loaded from script",
        key="added_script_data_key",
    )

    st.markdown("**required*")

    # add a submit button
    add_script_btn = st.button(
        "Add Script",
        type="primary",
        use_container_width=True,
        key="add_script_btn_key",
        disabled=not added_script or not script_alias or not added_script_data,
    )
    # add_file action
    if add_script_btn:
        new_script = pd.DataFrame(
            data=[
                [script_alias, True, added_script_ext, added_script, added_script_data]
            ],
            columns=["alias", "load", "type", "filename", "dataset"],
        )

        st.session_state.script_files = pd.concat(
            [st.session_state.script_files, new_script], ignore_index=True
        )


# --- Add Script Action --- #


def script_load_action(script_inputs: dict) -> None:
    """Load data from scripts based on the provided inputs.

    PARAMS:
    -------
    script_inputs: dict
        Dictionary containing script input details.

    Returns
    -------
    None

    """
    # remove empty rows
    script_inputs = script_inputs[script_inputs["load"] == True]  # noqa: E712

    # Check data and flag errors
    if script_inputs.empty:
        st.warning("No data selected for download. Please select data to download")
        st.stop()

    form_count = len(script_inputs.index)

    st.progress(0, text="Loading data From Script ...")

    st.write(f"Loading {form_count} datasets from Script")

    # download data
    for i in range(0, form_count):
        if f"script_raw_data{i}" in st.session_state:
            # get filename & path
            filename = script_inputs["filename"][i]
            # dataset = script_inputs["dataset"][i]

            with open(filename) as file:
                st.write("Name", exec(file.read()))

            # Check if the module has a DataFrame named {dataset}
            # if hasattr(exec_file, dataset):
            # st.session_state[f'script_raw_data{i}'] = getattr(exec_file, dataset)

            time.sleep(3)
            st.write(f"{i + 1}/{form_count}: Loaded successfully")

    st.success("Data load from scripts complete")

<<<<<<< HEAD
	# modify session state for preview
	st.session_state.scto_show_preview = True
>>>>>>> 495c39b (prep)
=======
    # modify session state for preview
    st.session_state.scto_show_preview = True
>>>>>>> 291498b (format and lint pydms/src/connectors)
