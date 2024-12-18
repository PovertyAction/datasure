<<<<<<< HEAD
<<<<<<< HEAD
from datetime import datetime

import numpy as np
import streamlit as st
=======
import streamlit as st
import numpy as np
import pandas as pd
=======
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)
from datetime import datetime
>>>>>>> ad3f479 (added summary report)

import numpy as np
import streamlit as st

st.write("""


# pyDMS - Data Management System

Data Management system for research data


""")

<<<<<<< HEAD
<<<<<<< HEAD
# Import survey data

survey = st.session_state["prepped_data1"]
=======
# Import survey data 

survey = st.session_state[f'prepped_data1']
>>>>>>> ad3f479 (added summary report)
=======
# Import survey data

survey = st.session_state["prepped_data1"]
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)


# Prepare Data

# submissiondate, starttime, endtime
<<<<<<< HEAD
<<<<<<< HEAD
datecols = {"submissiondate": "subdate", "starttime": "startdate", "endtime": "enddate"}
for col in datecols:
    survey[col] = survey[col].apply(lambda x: datetime.strptime(x, "%d%b%Y %H:%M:%S"))
=======
datecols = {'submissiondate':'subdate', 'starttime':'startdate', 'endtime':'enddate'}
for col in datecols:
    survey[col] = survey[col].apply(lambda x: datetime.strptime(x, '%d%b%Y %H:%M:%S'))
>>>>>>> ad3f479 (added summary report)
=======
datecols = {"submissiondate": "subdate", "starttime": "startdate", "endtime": "enddate"}
for col in datecols:
    survey[col] = survey[col].apply(lambda x: datetime.strptime(x, "%d%b%Y %H:%M:%S"))
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)
    survey[datecols[col]] = survey[col].dt.date


st.write("""


## Check 1: Form Versions

Check for surveys that were completed with older form versions

""")

<<<<<<< HEAD
<<<<<<< HEAD
# get a subset of the dataset
formv_data = survey[["formdef_version", "startdate", "a_enum_id", "a_enum_name"]]

# create a dataset of the latest form available for each day
check_version = formv_data.groupby("startdate").agg(
    formdef_version_max=("formdef_version", np.max)
)

# merge the grouped dataset back into the formv_data
formv_data = formv_data.merge(check_version, on="startdate")

# flag outdated submissions
formv_data["outdated"] = (
    formv_data["formdef_version"] < formv_data["formdef_version_max"]
)
formv_data["sub"] = 1
=======
# get a subset of the dataset 
formv_data = survey[['formdef_version', 'startdate', 'a_enum_id', 'a_enum_name']]
=======
# get a subset of the dataset
formv_data = survey[["formdef_version", "startdate", "a_enum_id", "a_enum_name"]]
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)

# create a dataset of the latest form available for each day
check_version = formv_data.groupby("startdate").agg(
    formdef_version_max=("formdef_version", np.max)
)

# merge the grouped dataset back into the formv_data
formv_data = formv_data.merge(check_version, on="startdate")

# flag outdated submissions
<<<<<<< HEAD
formv_data['outdated'] = formv_data['formdef_version'] < formv_data['formdef_version_max']
formv_data['sub'] = 1
>>>>>>> ad3f479 (added summary report)
=======
formv_data["outdated"] = (
    formv_data["formdef_version"] < formv_data["formdef_version_max"]
)
formv_data["sub"] = 1
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)

# Aggregate statistics by formdef_vers


<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)
outdated_stats = formv_data.groupby("formdef_version").agg(
    submissions=("sub", np.sum),
    outdated=("outdated", np.sum),
    firstdate=("startdate", np.min),
    lastdate=("startdate", np.max),
)
<<<<<<< HEAD
=======

outdated_stats = formv_data.groupby('formdef_version').agg(
                                        submissions = ('sub', np.sum),
                                        outdated = ('outdated', np.sum),
                                        firstdate = ('startdate', np.min),
                                        lastdate = ('startdate', np.max)
                                    )
>>>>>>> ad3f479 (added summary report)
=======
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)

# Show version information
st.write("""
	Information about form versions
	""")

<<<<<<< HEAD
<<<<<<< HEAD
# commenting out as this is not used
# outdated_stats
=======
outdated_stats
>>>>>>> ad3f479 (added summary report)
=======
# commenting out as this is not used
# outdated_stats
>>>>>>> c350dfc (linter clean-up)

st.write("""
	All surveys that were completed with outdated form version
	""")

# Show all observations with outdated form versions
<<<<<<< HEAD
<<<<<<< HEAD
formv_data[["startdate", "a_enum_id", "a_enum_name", "formdef_version"]][
    formv_data["outdated"] == True  # noqa: E712
]
=======
formv_data[['startdate', 'a_enum_id', 'a_enum_name', 'formdef_version']][formv_data['outdated'] == True]
>>>>>>> ad3f479 (added summary report)
=======
formv_data[["startdate", "a_enum_id", "a_enum_name", "formdef_version"]][
    formv_data["outdated"] == True  # noqa: E712
]
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)
