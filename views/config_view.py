<<<<<<< HEAD
import pandas as pd
import streamlit as st
=======
<<<<<<< HEAD
<<<<<<< HEAD
import streamlit as st
import pandas as pd

=======
=======
>>>>>>> 81f69f0 (format and lint pydms/src/views)
<<<<<<< HEAD
import pandas as pd
import streamlit as st
=======
import streamlit as st
import pandas as pd

>>>>>>> 1d12b2d (prep)
<<<<<<< HEAD
>>>>>>> 495c39b (prep)
=======
=======
import pandas as pd
import streamlit as st
>>>>>>> a5ebaa4 (format and lint pydms/src/views)
>>>>>>> 81f69f0 (format and lint pydms/src/views)
>>>>>>> 7f9f3dd (restructured files and folders)

st.title("Configure Checks")
st.markdown("Add a page for each dataset you want to check")

<<<<<<< HEAD
if "config_tabs" not in st.session_state:
    st.session_state.config_pages = ""

alias_list = list(filter(None, st.session_state.alias_list))

# define column names
column_names = {
    "Page Name": "",
    "Survey Data": "",
    "Survey KEY": "",
    "Survey ID": "",
    "Enumerator": "",
    "Survey Date": "",
    "Back check data": "",
    "Back Checker": "",
    "Tracking Data": "",
}
=======
<<<<<<< HEAD
<<<<<<< HEAD
if 'config_tabs' not in st.session_state:
	st.session_state.config_pages = ''
=======
=======
>>>>>>> 81f69f0 (format and lint pydms/src/views)
<<<<<<< HEAD
if "config_tabs" not in st.session_state:
    st.session_state.config_pages = ""
>>>>>>> 495c39b (prep)

alias_list = list(filter(None, st.session_state.alias_list))

add_page, check_pages = st.columns((0.35,0.65))

new_page_data = ''

survey_cols = ['enum_id', 'enum_name']

with add_page:
	with st.form(key = "new_tab"):
		st.markdown("*New Check Tab:*")

		new_page_name = st.text_input(label = "Page name*", 
			help = "Enter the name of the new check page. eg. Household Survey")
		
		new_page_data = st.selectbox("Dataset*:", options = alias_list)

		i = alias_list.index(new_page_data)
		survey_cols = st.session_state[f'prepped_data{i}'].columns
		
		if new_page_data != '':

			new_page_tracking_data = st.selectbox("Tracking Data:", options = alias_list)

			new_page_key = st.selectbox("Survey KEY*:", options = survey_cols)
			new_page_id = st.selectbox("Survey ID:", options = survey_cols)
			new_page_enum = st.selectbox("Enumerator ID:", options = survey_cols)
			new_page_date = st.selectbox("Date:", options = survey_cols)

		submit_button = st.form_submit_button(label="Create checks page")

# load existing pages

try:
	st.session_state.config_pages = pd.read_json('cache/pyDMS_config_tabs_cache.json')
except:
	st.session_state.config_pages = pd.DataFrame(columns = ['Page Name', 'Data', 'Tracking Data', 'KEY', 'ID', 'Enumerator', 'Date'])

if submit_button:
<<<<<<< HEAD
	
	if new_page_name == '':
		st.warning("Please enter a name for the new check page")
	elif new_page_data == '':
		st.warning("Please select a dataset for the new check page")

	new_page = pd.DataFrame(data = [[new_page_name, new_page_data, new_page_tracking_data, new_page_key, new_page_id, new_page_enum, new_page_date]], 
									columns = ['Page Name', 'Data', 'Tracking Data', 'KEY', 'ID', 'Enumerator', 'Date'])
	
	config_pages = pd.concat([st.session_state.config_pages, new_page], ignore_index = True)

	config_pages.to_json(f'cache/pyDMS_config_tabs_cache.json')


for i in range(len(st.session_state.config_pages)):
	st.session_state[f'config_page_{i}'] = st.session_state.config_pages['Page Name'][i]
	st.session_state[f'show_checks_page_{i}'] = True


=======
    if new_page_name == "":
        st.warning("Please enter a name for the new check page")
    elif new_page_data == "":
        st.warning("Please select a dataset for the new check page")

    new_page = pd.DataFrame(
        data=[
            [
                new_page_name,
                new_page_data,
                new_page_tracking_data,
                new_page_key,
                new_page_id,
                new_page_enum,
                new_page_date,
            ]
        ],
        columns=[
            "Page Name",
            "Data",
            "Tracking Data",
            "KEY",
            "ID",
            "Enumerator",
            "Date",
        ],
    )

    config_pages = pd.concat(
        [st.session_state.config_pages, new_page], ignore_index=True
    )

    config_pages.to_json("cache/pyDMS_config_tabs_cache.json")
=======
if 'config_tabs' not in st.session_state:
	st.session_state.config_pages = ''

alias_list = list(filter(None, st.session_state.alias_list))

add_page, check_pages = st.columns((0.35,0.65))

with add_page:
	
	with st.container(border=True):
		
		new_page_name = st.text_input("Page Name")
		new_page_data = st.selectbox(label = "Select Dataset", options = alias_list, index = None)

		if new_page_data:
			# get index for the dataset
			row_num = alias_list.index(new_page_data)

			# get list of columns in the selected dataset
			all_cols = st.session_state[f'prepped_data{row_num}'].columns
			# get list if all date columns
			all_date_cols = st.session_state[f'prepped_data{row_num}'].select_dtypes(include=['datetime64']).columns
			
			if new_page_data:
			
				new_page_key = st.selectbox(label = "Select KEY column*:", options = all_cols, help = "Select dataset unique identifier column")
				
				new_page_id = st.selectbox(label = "Select Survey ID column*:", options = all_cols, help = "Select survey ID column")
				new_page_enum = st.selectbox(label = "Select Enumerator column:", options = all_cols, help = "Select enumerator column")	
				new_page_date = st.selectbox(label = "Select Survey Date", options = all_date_cols, help = "Select date column")

				new_page_tracking_data = st.selectbox(label = "Select Tracking Dataset", options = alias_list, index = None)

		submit_button = st.button("Add Page", key = 'submit_button', type='primary', use_container_width=True, disabled = not new_page_name or not new_page_data)
	

with check_pages:

	with st.container(border=True):
	
		try:
			st.session_state.config_pages = pd.read_json('cache/pyDMS_config_tabs_cache.json')

		except:
			st.session_state.config_pages = pd.DataFrame(columns = ['Page Name', 'Data', 'Tracking Data', 'KEY', 'ID', 'Enumerator', 'Date'])

		check_page_mod = st.data_editor(data = st.session_state.config_pages, 
										 			use_container_width = True, 
													num_rows = "dynamic")
			
		# Save configuration File
		save_check_config = st.button("Save setting", type="secondary", 
				  key = "save_check_config_key")
		
		if save_check_config:
			check_page_mod.to_json(f'cache/pyDMS_config_tabs_cache.json')

<<<<<<< HEAD
		submit_button = st.form_submit_button(label="Create checks page")
<<<<<<< HEAD
>>>>>>> 1d12b2d (prep)
<<<<<<< HEAD
>>>>>>> 495c39b (prep)
=======
=======
=======
			for i in range(len(st.session_state.config_pages)):
				page_num = i + 1
				st.session_state[f'config_page_{page_num}'] = st.session_state.config_pages['Page Name'][i]
				st.session_state[f'show_checks_page_{page_num}'] = True
>>>>>>> eb8223d (before integration)
=======
if "config_tabs" not in st.session_state:
    st.session_state.config_pages = ""

alias_list = list(filter(None, st.session_state.alias_list))
>>>>>>> 7f9f3dd (restructured files and folders)

add_page, check_pages = st.columns((0.35, 0.65))

with add_page, st.container(border=True):
    new_page_name = st.text_input("Page Name")
<<<<<<< HEAD
    new_page_survey_data = st.selectbox(
        label="Select Dataset", options=alias_list, index=None
    )

    if new_page_survey_data:
        # get index for the dataset
        row_num = alias_list.index(new_page_survey_data)
=======
    new_page_data = st.selectbox(label="Select Dataset", options=alias_list, index=None)

    if new_page_data:
        # get index for the dataset
        row_num = alias_list.index(new_page_data)
>>>>>>> 7f9f3dd (restructured files and folders)

        # get list of columns in the selected dataset
        all_cols = st.session_state[f"prepped_data{row_num}"].columns
        # get list if all date columns
        all_date_cols = (
            st.session_state[f"prepped_data{row_num}"]
            .select_dtypes(include=["datetime64"])
            .columns
        )

<<<<<<< HEAD
        new_page_key = st.selectbox(
            label="Select KEY column*:",
            options=all_cols,
            help="Select dataset unique identifier column",
            index=None,
        )

        new_page_id = st.selectbox(
            label="Select Survey ID column*:",
            options=all_cols,
            help="Select survey ID column",
            index=None,
        )

        # define default values for options
        (
            new_page_enum,
            new_page_date,
            new_page_backcheck_data,
            new_page_bcer,
            new_page_tracking_data,
        ) = (None, None, None, None, None)

        new_page_enum = st.selectbox(
            label="Select Enumerator column:",
            options=all_cols,
            help="Select enumerator column",
            index=None,
        )

        new_page_date = st.selectbox(
            label="Select Survey Date",
            options=all_date_cols,
            help="Select date column",
            index=None,
        )

        # define additional details for the page
        new_page_backcheck_data = st.selectbox(
            label="Select Back Check Data",
            options=alias_list,
            help="Select back check data",
            index=None,
        )

        if new_page_backcheck_data:
            # get index for the dataset
            bc_row_num = alias_list.index(new_page_backcheck_data)

            # get list of columns in the selected dataset
            all_bc_cols = st.session_state[f"prepped_data{row_num}"].columns

            new_page_bcer = st.selectbox(
                label="Select Back Checker column",
                options=all_bc_cols,
                help="Select back checker column",
                index=None,
            )

        new_page_tracking_data = st.selectbox(
            label="Select Tracking Dataset", options=alias_list, index=None
        )
=======
        if new_page_data:
            new_page_key = st.selectbox(
                label="Select KEY column*:",
                options=all_cols,
                help="Select dataset unique identifier column",
            )

            new_page_id = st.selectbox(
                label="Select Survey ID column*:",
                options=all_cols,
                help="Select survey ID column",
            )
            new_page_enum = st.selectbox(
                label="Select Enumerator column:",
                options=all_cols,
                help="Select enumerator column",
            )
            new_page_date = st.selectbox(
                label="Select Survey Date",
                options=all_date_cols,
                help="Select date column",
            )

            new_page_tracking_data = st.selectbox(
                label="Select Tracking Dataset", options=alias_list, index=None
            )
>>>>>>> 7f9f3dd (restructured files and folders)

    submit_button = st.button(
        "Add Page",
        key="submit_button",
        type="primary",
        use_container_width=True,
<<<<<<< HEAD
        disabled=not new_page_name or not new_page_survey_data,
=======
        disabled=not new_page_name or not new_page_data,
>>>>>>> 7f9f3dd (restructured files and folders)
    )


with check_pages, st.container(border=True):
    try:
        st.session_state.config_pages = pd.read_json(
<<<<<<< HEAD
            "cache/settings/pyDMS_config_pages_cache.json"
=======
            "cache/pyDMS_config_tabs_cache.json"
>>>>>>> 7f9f3dd (restructured files and folders)
        )

    except Exception:
        st.session_state.config_pages = pd.DataFrame(
<<<<<<< HEAD
            columns=column_names,
=======
            columns=[
                "Page Name",
                "Data",
                "Tracking Data",
                "KEY",
                "ID",
                "Enumerator",
                "Date",
            ]
>>>>>>> 7f9f3dd (restructured files and folders)
        )

    check_page_mod = st.data_editor(
        data=st.session_state.config_pages,
        use_container_width=True,
        num_rows="dynamic",
    )

    # Save configuration File
    save_check_config = st.button(
        "Save setting", type="secondary", key="save_check_config_key"
    )

    if save_check_config:
<<<<<<< HEAD
        check_page_mod.to_json("cache/settings/pyDMS_config_pages_cache.json")

=======
        check_page_mod.to_json("cache/pyDMS_config_tabs_cache.json")

<<<<<<< HEAD
            for i in range(len(st.session_state.config_pages)):
                page_num = i + 1
                st.session_state[f"config_page_{page_num}"] = (
                    st.session_state.config_pages["Page Name"][i]
                )
                st.session_state[f"show_checks_page_{page_num}"] = True
>>>>>>> a5ebaa4 (format and lint pydms/src/views)
=======
>>>>>>> 7f9f3dd (restructured files and folders)
        for i in range(len(st.session_state.config_pages)):
            page_num = i + 1
            st.session_state[f"config_page_{page_num}"] = st.session_state.config_pages[
                "Page Name"
            ][i]
            st.session_state[f"show_checks_page_{page_num}"] = True
<<<<<<< HEAD
=======
>>>>>>> a88010e (simplify SIM117 checks)
>>>>>>> 7f9f3dd (restructured files and folders)

# load existing pages


if submit_button:
<<<<<<< HEAD
    if new_page_name == "":
        st.warning("Please enter a name for the new check page")
    elif new_page_survey_data == "":
=======
<<<<<<< HEAD
	
	if new_page_name == '':
		st.warning("Please enter a name for the new check page")
	elif new_page_data == '':
		st.warning("Please select a dataset for the new check page")

	new_page = pd.DataFrame(data = [[new_page_name, new_page_data, new_page_tracking_data, new_page_key, new_page_id, new_page_enum, new_page_date]], 
									columns = ['Page Name', 'Data', 'Tracking Data', 'KEY', 'ID', 'Enumerator', 'Date'])
	
	config_pages = pd.concat([st.session_state.config_pages, new_page], ignore_index = True)

<<<<<<< HEAD
	config_pages.to_json(f'cache/pyDMS_config_tabs_cache.json')


for i in range(len(st.session_state.config_pages)):
	st.session_state[f'config_page_{i}'] = st.session_state.config_pages['Page Name'][i]
	st.session_state[f'show_checks_page_{i}'] = True


>>>>>>> ff3f469 (check_settings)
<<<<<<< HEAD
>>>>>>> 00a502e (check_settings)
=======
=======
	config_pages.to_json(f'cache/pyDMS_config_tabs_cache.json')
>>>>>>> eb8223d (before integration)
<<<<<<< HEAD
>>>>>>> 9ad363e (before integration)
=======
=======
    if new_page_name == "":
        st.warning("Please enter a name for the new check page")
    elif new_page_data == "":
>>>>>>> 7f9f3dd (restructured files and folders)
        st.warning("Please select a dataset for the new check page")

    new_page = pd.DataFrame(
        data=[
            [
                new_page_name,
<<<<<<< HEAD
                new_page_survey_data,
=======
                new_page_data,
                new_page_tracking_data,
>>>>>>> 7f9f3dd (restructured files and folders)
                new_page_key,
                new_page_id,
                new_page_enum,
                new_page_date,
<<<<<<< HEAD
                new_page_backcheck_data,
                new_page_bcer,
                new_page_tracking_data,
            ]
        ],
        columns=column_names,
=======
            ]
        ],
        columns=[
            "Page Name",
            "Data",
            "Tracking Data",
            "KEY",
            "ID",
            "Enumerator",
            "Date",
        ],
>>>>>>> 7f9f3dd (restructured files and folders)
    )

    config_pages = pd.concat(
        [st.session_state.config_pages, new_page], ignore_index=True
    )

<<<<<<< HEAD
    config_pages.to_json("cache/settings/pyDMS_config_pages_cache.json")
=======
    config_pages.to_json("cache/pyDMS_config_tabs_cache.json")
>>>>>>> a5ebaa4 (format and lint pydms/src/views)
>>>>>>> 81f69f0 (format and lint pydms/src/views)
>>>>>>> 7f9f3dd (restructured files and folders)
