import streamlit as st
<<<<<<< HEAD
<<<<<<< HEAD

from src.checks import (
    backchecks_report,
    descriptive_report,
    duplicates_report,
    enumerator_report,
    missing_report,
    outliers_report,
    progress_report,
    summary_report,
)
=======
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
from src.checks import missing_report, progress_report, summary_report
=======
from src.checks import missing_report, progress_report, summary_report, duplicates_report
>>>>>>> 0160683 (adding duplicates check file)
<<<<<<< HEAD
>>>>>>> fbd01f5 (adding duplicates check file)
=======
=======
from src.checks import missing_report, progress_report, summary_report, duplicates_report, outliers_report
>>>>>>> 5a9d5bd (adding outlier check)
<<<<<<< HEAD
>>>>>>> b597f57 (adding outlier check)
=======
=======

from src.checks import (
    missing_report, 
    progress_report, 
    summary_report, 
    duplicates_report, 
    outliers_report, 
    enumerator_report,
    descriptive_report, 
    backchecks_report
)
>>>>>>> 7beb6ff (added enumerator check)
>>>>>>> a57c513 (added enumerator check)

# define page number
page_number = 1
page_data_index = page_number - 1

st.title(st.session_state[f"config_page_{page_number}"])

<<<<<<< HEAD
<<<<<<< HEAD
(
    summary,
    survey_progress,
    duplicates,
    missing,
    outliers,
    enum_stats,
    desc_stats,
    back_checks,
) = st.tabs(
=======
<<<<<<< HEAD
<<<<<<< HEAD
import pandas as pd
from datetime import datetime
=======
=======
>>>>>>> 81f69f0 (format and lint pydms/src/views)
<<<<<<< HEAD
from src.checks import missing_report, progress_report, summary_report
>>>>>>> 00a502e (check_settings)
=======
summary, survey_progress, duplicates, missing, outliers, enum_stats, desc_stats = st.tabs(
=======
summary, survey_progress, duplicates, missing, outliers, enum_stats, desc_stats, back_checks = st.tabs(
>>>>>>> 1205bf5 (adding back check)
    (
        "Summary",
        "Survey Progress",
        "Duplicates",
        "Missing Data",
        "Outliers",
        "Enumerator Stats",
        "Descriptive Stats", 
        "Back Checks"
    )
)
>>>>>>> 3565c46 (adding descriptive stats check)

st.title(st.session_state.config_page_1)

summary, survey_progress, duplicates, enum_stats, missing, outliers = \
    st.tabs(("Summary", "Survey Progress", "Duplicates", "Enumerator Stats", "Missing Data", "Outliers"))

alias_list = list(filter(None, st.session_state.alias_list))
new_page_data = st.session_state[f'prepped_data{1}']

with summary:
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
    
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for summary report")

<<<<<<< HEAD
        survey_cols = st.session_state[f'prepped_data{1}'].columns

        st.write("---")
        st.markdown("### Select columns to include in summary report")
        
        formversion_col, enumerator_col, date_col = st.columns(3)
        formversion_col.selectbox("Form Version", options = survey_cols)
        enumerator_col.selectbox("Enumerator", options = survey_cols)
        date_col.selectbox("Date", options = survey_cols)
        by_col, consent_col, duration_col = st.columns(3)
        by_col.selectbox("Group by", options = survey_cols)
        consent_col.selectbox("Consent", options = survey_cols)
        duration_col.selectbox("Duration", options = "Duration")

        st.write("---")
        st.markdown("### Summary report options")

        enum_filter_col, team_filter_col, location_filter_col = st.columns(3)
        enum_filter_col.multiselect("Enumerator", options = survey_cols)
        team_filter_col.multiselect("Team", options = survey_cols)
        location_filter_col.multiselect("Location", options = survey_cols)

        date_filter = st.slider(
            "Select date range", 
                min_value= datetime(2024, 1, 1), max_value = datetime(2024, 12, 31), 
                format = "YYYY-MM-DD", value = (datetime(2024, 1, 1), datetime(2024, 12, 31))
        )

        




<<<<<<< HEAD
=======
=======
with missing:
    missing_report(st.session_state[f"prepped_data{page_number}"])

>>>>>>> b597f57 (adding outlier check)
=======
    summary_report(st.session_state[f"prepped_data{page_number}"])
    
with missing:
    missing_report(st.session_state[f"prepped_data{page_number}"])
    
>>>>>>> a57c513 (added enumerator check)
=======
    #summary_report(st.session_state[f"prepped_data{page_number}"])
    pass
with missing:
    #missing_report(st.session_state[f"prepped_data{page_number}"])
    pass
>>>>>>> 1205bf5 (adding back check)
=======
    summary_report(
        data=st.session_state[f"prepped_data{page_number}"], 
        page_num=page_number
    )

with missing:
    missing_report(
        data=st.session_state[f"prepped_data{page_number}"], 
        page_num=page_number
    )
    
>>>>>>> c8a436c (adding default values from config page)
with survey_progress:
<<<<<<< HEAD
<<<<<<< HEAD
    progress_report(st.session_state[f"prepped_data{page_number}"])
<<<<<<< HEAD
<<<<<<< HEAD
=======
import pandas as pd
from datetime import datetime
import seaborn as sns
import matplotlib.pyplot as plt

from src.checks import summary_report, missing_report, progress_report

=======
from src.checks import missing_report, progress_report, summary_report
>>>>>>> a5ebaa4 (format and lint pydms/src/views)

# define page number
page_number = 1

st.title(st.session_state[f"config_page_{page_number}"])

summary, survey_progress, duplicates, missing, outliers, enum_stats = st.tabs(
>>>>>>> 7f9f3dd (restructured files and folders)
    (
        "Summary",
        "Survey Progress",
        "Duplicates",
        "Missing Data",
        "Outliers",
        "Enumerator Stats",
<<<<<<< HEAD
        "Descriptive Stats",
        "Back Checks",
=======
>>>>>>> 7f9f3dd (restructured files and folders)
    )
)

alias_list = list(filter(None, st.session_state.alias_list))

# load data from

with summary:
<<<<<<< HEAD
    summary_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with missing:
    missing_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with survey_progress:
    progress_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with duplicates:
    duplicates_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with outliers:
    outliers_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with enum_stats:
    enumerator_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with desc_stats:
    descriptive_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with back_checks:
    backchecks_report(
        survey_data=st.session_state[f"prepped_data{page_data_index}"],
        backcheck_data=st.session_state[f"prepped_data{page_data_index}"],
        page_num=page_number,
    )
=======
    summary_report(st.session_state[f"prepped_data{page_number}"])


with missing:
    missing_report(st.session_state[f"prepped_data{page_number}"])


with survey_progress:
<<<<<<< HEAD
    
    progress_report(st.session_state[f'prepped_data{page_number}'])

<<<<<<< HEAD
>>>>>>> ff3f469 (check_settings)
<<<<<<< HEAD
>>>>>>> 00a502e (check_settings)
=======
=======
           
  
   
    
>>>>>>> e006032 (added_missing_check)
<<<<<<< HEAD
>>>>>>> dfddc4f (added_missing_check)
=======
=======
    progress_report(st.session_state[f"prepped_data{page_number}"])
>>>>>>> a5ebaa4 (format and lint pydms/src/views)
<<<<<<< HEAD
>>>>>>> 81f69f0 (format and lint pydms/src/views)
>>>>>>> 7f9f3dd (restructured files and folders)
=======
=======

with duplicates:
    duplicates_report(st.session_state[f"prepped_data{page_number}"])
<<<<<<< HEAD
>>>>>>> 0160683 (adding duplicates check file)
<<<<<<< HEAD
>>>>>>> fbd01f5 (adding duplicates check file)
=======
=======

<<<<<<< HEAD
>>>>>>> 2a401cd (replacing missing check with mx version)
<<<<<<< HEAD
>>>>>>> d267c72 (replacing missing check with mx version)
=======
=======
with outliers:
    outliers_report(st.session_state[f"prepped_data{page_number}"])
>>>>>>> 5a9d5bd (adding outlier check)
<<<<<<< HEAD
>>>>>>> b597f57 (adding outlier check)
=======
=======
    
=======
    #progress_report(st.session_state[f"prepped_data{page_number}"])
    pass
>>>>>>> d69d05e (adding back check)
=======
    progress_report(
        data=st.session_state[f"prepped_data{page_number}"], 
        page_num=page_number
    )
    
>>>>>>> fa264c2 (adding default values from config page)
with duplicates:
    duplicates_report(
        data=st.session_state[f"prepped_data{page_number}"], 
        page_num=page_number
    )
    
with outliers:
    outliers_report(
        data=st.session_state[f"prepped_data{page_number}"], 
        page_num=page_number
    )

with enum_stats:
<<<<<<< HEAD
<<<<<<< HEAD
    enumerator_report(st.session_state[f"prepped_data{page_number}"])
<<<<<<< HEAD
>>>>>>> 7beb6ff (added enumerator check)
<<<<<<< HEAD
>>>>>>> a57c513 (added enumerator check)
=======
=======
    

with desc_stats:
    descriptive_report(st.session_state[f"prepped_data{page_number}"])
>>>>>>> 602bf45 (adding descriptive stats check)
<<<<<<< HEAD
>>>>>>> 3565c46 (adding descriptive stats check)
=======
=======
    #enumerator_report(st.session_state[f"prepped_data{page_number}"])
    pass
=======
    enumerator_report(
        data=st.session_state[f"prepped_data{page_number}"], 
        page_num=page_number
    )
>>>>>>> fa264c2 (adding default values from config page)

with desc_stats:
    descriptive_report(
        data=st.session_state[f"prepped_data{page_number}"], 
        page_num=page_number
    )

with back_checks:
<<<<<<< HEAD
    backchecks_report(st.session_state[f"prepped_data{page_number}"], st.session_state[f"prepped_data{page_number}"])
>>>>>>> d69d05e (adding back check)
<<<<<<< HEAD
>>>>>>> 1205bf5 (adding back check)
=======
=======
    backchecks_report(
        survey_data=st.session_state[f"prepped_data{page_number}"], 
        backcheck_data=st.session_state[f"prepped_data{page_number}"], 
        page_num=page_number
    )
>>>>>>> fa264c2 (adding default values from config page)
>>>>>>> c8a436c (adding default values from config page)
