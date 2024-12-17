import streamlit as st
import pandas as pd
from datetime import datetime
import seaborn as sns
import matplotlib.pyplot as plt

from src.checks import summary_report, missing_report


# define page number
page_number = 1

st.title(st.session_state[f'config_page_{page_number}'])

summary, survey_progress, duplicates, missing, outliers, enum_stats = \
    st.tabs(("Summary", "Survey Progress", "Duplicates", "Missing Data", "Outliers", "Enumerator Stats"))

alias_list = list(filter(None, st.session_state.alias_list))

# load data from 

with summary:
    
    summary_report(st.session_state[f'prepped_data{page_number}']) 


with missing:

    missing_report(st.session_state[f'prepped_data{page_number}'])


                    


           
  
   
    