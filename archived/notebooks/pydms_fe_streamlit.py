import datetime
from collections import defaultdict
from datetime import datetime  # noqa: F811
from io import BytesIO

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import seaborn as sns
import streamlit as st
from plotly.subplots import make_subplots

st.set_page_config(layout="wide")
st.title("PyDMS Dashboard")
st.logo(
    "notebooks/IPA-primary-color-CMYK.jpg", size="large", link=None, icon_image=None
)

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs(
    [
        "Data",
        "Summary",
        "Survey Progress",
        "Duplicates",
        "Enumerator Statistics",
        "Missing Data",
        "Outliers",
        "Back Checks",
        "Descriptive Statistics",
    ]
)

with tab1:
    ##### Survey Data #####
    def load_dataframe(file_path):
        """Load a dataframe from a given file path or URL.

        Args:
            file_path (str): The path or URL to the file.

        Returns
        -------
            pd.DataFrame: The loaded dataframe.

        Raises
        ------
            ValueError: If the file format is unsupported.
            requests.exceptions.RequestException: If there is an error
            downloading the file.

        """
        if file_path.startswith("http"):
            # For GitHub URLs
            if "github.com" in file_path:
                file_path = file_path.replace("github.com", "raw.githubusercontent.com")
                file_path = file_path.replace("/blob/", "/")

            # Download the file content
            response = requests.get(file_path)
            response.raise_for_status()  # Raise an exception for bad responses
            content = BytesIO(response.content)

            # Determine file type from the URL (csv, xls, xlsx and dta)
            if file_path.endswith(".csv"):
                return pd.read_csv(content)
            elif file_path.endswith((".xls", ".xlsx")):
                return pd.read_excel(content, engine="openpyxl")
            elif file_path.endswith(".dta"):
                return pd.read_stata(content)
            else:
                raise ValueError(
                    "Unsupported file format. Please provide a CSV, XLS, XLSX, or DTA file."
                )
        else:
            # Handle local files
            if file_path.endswith(".csv"):
                return pd.read_csv(file_path)
            elif file_path.endswith((".xls", ".xlsx")):
                return pd.read_excel(file_path, engine="openpyxl")
            elif file_path.endswith(".dta"):
                return pd.read_stata(file_path)
            else:
                raise ValueError(
                    "Unsupported file format. Please provide a CSV, XLS, XLSX, or DTA file."
                )

    # Header
    st.subheader("Survey Data")

    # Input field for file path
    file_path = st.text_input("Insert URL or Path (from GitHub or local): ")

    # Check if the input is empty and handle it
    if file_path:
        try:
            df_original = load_dataframe(file_path)
            st.success("Data Loaded Successfully!")

        except ValueError as ve:
            st.error(str(ve))
        except FileNotFoundError:
            st.error("File not found. Please check the URL or path.")
        except pd.errors.EmptyDataError:
            st.error("No data found in the file.")
        except pd.errors.ParserError:
            st.error("Error parsing the file. Please check its format.")
        except requests.exceptions.RequestException as req_err:
            st.error(f"Error downloading the file: {req_err}")

        # Basic set up
        df = df_original.copy()

        # Change all variables names to lower case
        df.columns = df.columns.str.lower()

        # NOTE: In the following please replace with your own variables

        # Select "CONSENT" variable (either numeric or categorical)
        # Define a mapping from categorical to numeric. NOTE: The default is
        # english, but might change depending on the language (eg. Sí, No in
        # Spanish)
        mapping = {"No": 0, "Yes": 1}

        if pd.api.types.is_numeric_dtype(df["c_consent"]):
            df["consent"] = df["c_consent"]  # If numeric
        else:
            df["consent"] = df["c_consent"].map(mapping)  # If categorical

        # Select "ID" variable
        id_variable = "hhid"
        df["id"] = df[id_variable]

        # Select "ENUMERATOR ID" variable
        enumid_var = "a_enum_id"
        df["enumid"] = df[enumid_var]

        # NOTE: For consent variables including recording and gps consent
        # please use "#" to comment them if there are no such variables in the
        # working df.

        # Select "RECORDING CONSENT" variable (if any)
        if pd.api.types.is_numeric_dtype(df["aud_consent"]):
            df["recording_consent"] = df["aud_consent"]  # If numeric
        else:
            df["recording_consent"] = df["aud_consent"].map(
                {"Yes": 1, "No": 0}
            )  # If categorical

        # Select "GPS CONSENT" variable (if any)
        # if pd.api.types.is_numeric_dtype(df['gps_consent']):  # If numeric
        #    df['gps_consent'] = df['gps_consent']
        # else: # If categorical
        #    df['gps_consent'] = df['gps_consent'].map({'Yes': 1, 'No': 0})

        # Select "SUBMISSION DATE" variable
        df["submissiondate"] = df["submissiondate"]

        # Select "DURATION" variable
        df["duration"] = df["duration"]

        # Insert variable with unique values for each interview
        df["key"] = df["key"]

        # Insert variable that identifies the enumerator doing back checks
        enum_bcer = ["a_bcer_id"]

        # Define codes, both numeric and labels for "Don't Know" and "Refuse to Answer"
        codes = [-999, -888]
        labels = ["Don't know", "Refuses to Answer"]

        # Define total number of interviews expected (target number of interviews)
        total_goal = 950

        # Define percentage of completed interviews that should be flagged. For
        # example, write 50 if less than 50% of the interviews are complete and
        # should be flagged as warning
        warning_finished = 50

        # Define flagged percentage of missing. For example, write 50 if there
        # are more than 50% of missing and should be flagged as warning
        percentage_warning = 50

        ##### Changes to data #####

        # Transform date variable to a valid format
        def convert_submission_date(date_series):
            """Convert a series of date strings to datetime objects.

            Args:
                date_series (pd.Series): Series of date strings.

            Returns
            -------
                pd.Series: Series of datetime objects.

            """

            def parse_spanish_date(date_string):
                month_map = {  # Change months accordingly if they are not in english
                    "ene": "01",
                    "feb": "02",
                    "mar": "03",
                    "abr": "04",
                    "may": "05",
                    "jun": "06",
                    "jul": "07",
                    "ago": "08",
                    "sep": "09",
                    "oct": "10",
                    "nov": "11",
                    "dic": "12",
                }

                try:
                    day, month, rest = date_string.split("-")
                    year, time = rest.split(" ")
                    month_num = month_map[month.lower()]
                    return f"{day}-{month_num}-{year} {time}"  # noqa: TRY300
                except ValueError:
                    return date_string

            def parse_date(date_string):
                formats = [
                    "%d/%m/%Y, %H:%M:%S",  # DD/MM/YYYY, HH:MM:SS
                    "%d-%m-%Y %H:%M:%S",  # DD-MM-YYYY HH:MM:SS
                    "%Y-%m-%d %H:%M:%S",  # YYYY-MM-DD HH:MM:SS
                    "%d-%b-%Y %H:%M:%S",  # DD-Mon-YYYY HH:MM:SS (English abbreviation)
                ]

                for fmt in formats:
                    try:
                        return pd.to_datetime(date_string, format=fmt)
                    except ValueError:
                        pass

                # If none of the above formats work, try the Spanish format
                try:
                    parsed = parse_spanish_date(date_string)
                    return pd.to_datetime(parsed, format="%d-%m-%Y %H:%M:%S")
                except ValueError:
                    pass

            return date_series.apply(parse_date)

        # Apply the function to the column
        df["submissiondate"] = convert_submission_date(df["submissiondate"])

        # Create a new variable only with the date, without time stamp
        df["date_only"] = df["submissiondate"].dt.date

        # Create a variable of duration in minutes
        if pd.api.types.is_numeric_dtype(df["duration"]):
            df["duration_mins"] = df["duration"] / 60
        else:
            # Change variable to numeric
            df["duration"] = pd.to_numeric(df["duration"], errors="coerce")

        # Create a variable of duration to minutes
        df["duration_mins"] = df["duration"] / 60

        # Change "consent" variable to numeric in a new data frame
        df1 = df.copy()

        # Verify if "consent" is numeric
        if not pd.api.types.is_numeric_dtype(df1["consent"]):
            # Change to numeric if it's not already
            df1["consent"] = pd.to_numeric(df1["consent"], errors="coerce")

        # Filter rows where "consent" is not NA
        df1 = df1[df1["consent"].notna()]

        # Note: Enter all validity conditions to filter data. Comment if not
        # in use, add new conditions in the form of varname_filter = value if
        # needed.

        # Define filters (add any here)
        consent_filter = 1  # Consent value (1 for "Yes")
        # age_filter = 18             # Minimum age for consent
        # sex_filter = 'Mujer'        # Sex
        recording_consent_filter = 1  # Recording consent (1 for "Yes")
        # gps_consent_filter = 1      # Recording consent (1 for "Yes")

        # Create new filtered df. Eliminate conditions not in use, add new
        # conditions using & (df[newvar] == varname_filter) where
        # varname_filter should be previously defined
        filtered_df = df[
            (df["consent"] == consent_filter)
            # &
            # (df['recording_consent'] == recording_consent_filter)
        ]

        df3 = filtered_df
        df4 = filtered_df

        # Eliminate duplicates
        df_sorted = filtered_df.sort_values(by="submissiondate", ascending=False)

        # Eliminate id duplicates, keeping the most recent interview
        df6 = df_sorted.drop_duplicates(subset="id", keep="first")

        ##### Back Check Data #####
        def load_dataframe(file_path):
            """Load a dataframe from a given file path or URL.

            Args:
            file_path (str): The path or URL to the file.

            Returns
            -------
            pd.DataFrame: The loaded dataframe.

            """
            # Loading dataframe based on URL or local path
            if file_path.startswith("http"):
                # For GitHub URLs
                if "github.com" in file_path:
                    file_path = file_path.replace(
                        "github.com", "raw.githubusercontent.com"
                    )
                    file_path = file_path.replace("/blob/", "/")

                # Download the file content
                response = requests.get(file_path)
                response.raise_for_status()
                content = BytesIO(response.content)

                # Determine file type
                if file_path.endswith(".csv"):
                    return pd.read_csv(content)
                elif file_path.endswith((".xls", ".xlsx")):
                    return pd.read_excel(content, engine="openpyxl")
                elif file_path.endswith(".dta"):
                    return pd.read_stata(content)
                else:
                    raise ValueError(
                        "Unsupported file format. Please provide a CSV, XLS, XLSX, or DTA file."
                    )
            else:
                # Handle local files
                if file_path.endswith(".csv"):
                    return pd.read_csv(file_path)
                elif file_path.endswith((".xls", ".xlsx")):
                    return pd.read_excel(file_path, engine="openpyxl")
                elif file_path.endswith(".dta"):
                    return pd.read_stata(file_path)
                else:
                    raise ValueError(
                        "Unsupported file format. Please provide a CSV, XLS, XLSX, or DTA file."
                    )

        # With existing_df being the dataframe loaded earlier
        existing_df = df6

        st.subheader("Backcheck Data")
        file_path = st.text_input(
            "Insert valid URL or Path for backcheck data (from GitHub or local) if any: "
        )

        try:
            if file_path:
                backcheck_df = load_dataframe(file_path)
                st.success("Backcheck Data Loaded Successfully!")

                # Ensure 'enumid' is only in the existing_df
                enumid_var = "enumid"
                if enumid_var not in existing_df.columns:
                    st.error(f"Column {enumid_var} is missing in existing_df")

                # Select merge variable
                merge_variable = st.selectbox(
                    "Select unique identifier in both datasets:",
                    [col for col in backcheck_df.columns if col in existing_df.columns],
                    index=0,
                )

                if merge_variable:
                    # Add a "Calculate Backchecks" button
                    if st.button("Calculate Backchecks"):
                        # Create copies of the DataFrames to avoid modifying
                        # the originals
                        existing_df_copy = existing_df.copy()
                        backcheck_df_copy = backcheck_df.copy()

                        # Before merging, create backup columns for the values
                        # we want to preserve (ids of enumerators and backcheckers)
                        existing_df_copy["original_enum_id"] = existing_df_copy[
                            enumid_var
                        ]
                        backcheck_df_copy["original_bcer_id"] = backcheck_df_copy[
                            enum_bcer
                        ]

                        # Columns to exclude from prefixing
                        exclude_columns = {merge_variable, enumid_var, *enum_bcer}

                        # Add prefixes to columns except merge_variable,
                        # enumid and enum_bcer
                        existing_df_columns = {
                            col: f"svy_{col}"
                            for col in existing_df_copy.columns
                            if col not in exclude_columns and col != "original_enum_id"
                        }
                        backcheck_df_columns = {
                            col: f"back_{col}"
                            for col in backcheck_df_copy.columns
                            if col not in exclude_columns and col != "original_bcer_id"
                        }

                        # Rename columns with prefixes
                        existing_df_copy.rename(
                            columns=existing_df_columns, inplace=True
                        )
                        backcheck_df_copy.rename(
                            columns=backcheck_df_columns, inplace=True
                        )

                        # Merge datasets
                        merged_df = pd.merge(
                            existing_df_copy,
                            backcheck_df_copy,
                            on=[merge_variable],
                            how="inner",
                        )

                        # Restore the original IDs
                        merged_df[enumid_var] = merged_df["original_enum_id"]
                        merged_df["enum_bcer"] = merged_df["original_bcer_id"]

                        # Drop the backup columns
                        merged_df = merged_df.drop(
                            ["original_enum_id", "original_bcer_id"], axis=1
                        )

                        # Store merged_df for use later
                        st.session_state.merged_df = merged_df
                        st.session_state.existing_df = existing_df

                        st.success("Calculations ready!")

                else:
                    st.warning("No backcheck data uploaded")
        except Exception as e:
            st.error(f"An error occurred: {e}")

        ##### Summary #####
        with tab2:
            ### Value box 1 ###
            # Define any validity condition
            valid_interviews = df1["consent"].sum()

            # Calculate porcentage of finished interviews
            percentage_finished = (valid_interviews / total_goal) * 100

            # Format of percentage
            formatted_percentage_finished = f"{percentage_finished:.2f}%"

            ### Value box 2 ###
            # Identify the date of the first interview
            earliest_date = df["submissiondate"].min()

            # Todays date
            today = pd.Timestamp.now()

            # Calculate the number of days since the first interview/launch
            days_since_start = (today - earliest_date).days

            # Set the color
            color = "black"

            ### Value box 3 ###
            # Percentage of missing ID's
            total_values = df.size

            # Define ID variable
            column_name = "id"

            missing_values = df[column_name].isnull().sum()
            missing_percentage = (missing_values / total_values) * 100

            # Format the percentage
            formatted_missing_percentage = f"{missing_percentage:.2f}%"

            ### Value box 4 ###
            # Group by date and count number of IDs
            count_by_date = df1.groupby("date_only").size()

            # Calculate the average number of interviews per day
            average_interviews_per_day = count_by_date.mean()

            # Round number of interviews per day
            rounded_average_day = round(average_interviews_per_day, 2)

            #### Create first row of value boxes ####
            # Define color codes
            color_completed = (
                "#FFA500" if percentage_finished <= percentage_warning else "#4CAF50"
            )
            color_missing = (
                "#FFA500" if missing_percentage > percentage_warning else "#4CAF50"
            )

            # Include Font Awesome
            st.markdown(
                '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">',
                unsafe_allow_html=True,
            )

            # Create columns for value boxes
            col1, col2, col3, col4 = st.columns(4)

            # Value box: Completed interviews
            with col1:
                st.markdown(
                    f"""
                <div style="display: flex; align-items: center; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
                    <i class="fas fa-bullseye" style="font-size: 70px; color: {color_completed}; margin-right: 10px;"></i>
                    <div style="flex-grow: 1;">
                        <h3 style="margin: 0; font-size: 25px; text-align: center;">Completed Interviews</h3>
                        <p style="font-size: 53px; color: {color_completed}; margin: 0; text-align: center;">{formatted_percentage_finished}</p>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            # Value box: Number of days since launch
            with col2:
                st.markdown(
                    f"""
                <div style="display: flex; align-items: center; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
                    <i class="fas fa-calendar-week" style="font-size: 70px; color: black; margin-right: 10px;"></i>
                    <div style="flex-grow: 1;">
                        <h3 style="margin: 0; font-size: 25px; text-align: center;">Number of Days since Launch</h3>
                        <p style="font-size: 53px; color: black; margin: 0; text-align: center;">{days_since_start}</p>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            # Value box: % of missing IDs
            with col3:
                st.markdown(
                    f"""
                <div style="display: flex; align-items: center; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
                    <i class="fas fa-percent" style="font-size: 70px; color: {color_missing}; margin-right: 10px;"></i>
                    <div style="flex-grow: 1;">
                        <h3 style="margin: 0; font-size: 25px; text-align: center;">Percentage of Missing IDs</h3>
                        <p style="font-size: 53px; color: {color_missing}; margin: 0; text-align: center;">{formatted_missing_percentage}</p>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            # Value box 4: Average Interviews per Day
            with col4:
                st.markdown(
                    f"""
                <div style="display: flex; align-items: center; padding: 5px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
                    <i class="fas fa-calendar-alt" style="font-size: 73px; color: black; margin-right: 10px;"></i>
                    <div style="flex-grow: 1;">
                        <h3 style="font-size: 28px; margin: 0; text-align: center;"> Average Interviews per Day</h3>
                        <p style="font-size: 53px; color: black; margin: 0; text-align: center;">{rounded_average_day}</p>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            ### Value box 5 ###
            # Count number of enumerators
            unique_enumerators = df["enumid"].nunique()

            ### Value box 6 ###
            # Count the number of interviews per interviewer
            interviews_per_interviewer = (
                df.groupby("enumid", observed=False)
                .size()
                .reset_index(name="interviews_count")
            )

            # Calculate the average number of interviews per enumerator
            average_interviews_per_interviewer = interviews_per_interviewer[
                "interviews_count"
            ].mean()

            # Round the number of interviews per enumerator
            rounded_average = round(average_interviews_per_interviewer, 2)

            ### Value box 7 ###
            average_interviews_per_day_per_enumerator = (
                average_interviews_per_day / (unique_enumerators)
                if unique_enumerators > 0
                else 0
            )
            rounded_average_day_per_enumerator = round(
                average_interviews_per_day_per_enumerator, 2
            )

            ### Value box 8 ###
            # Calculate interviews left
            interviews_left = total_goal - valid_interviews

            #### Create second row of value boxes
            # Create columns for the value boxes
            col5, col6, col7, col8 = st.columns(4)

            # Value box 5: Number of Enumerators
            with col5:
                st.markdown(
                    f"""
                <div style="display: flex; align-items: center; padding: 21px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
                    <i class="fas fa-user" style="font-size: 73px; color: black; margin-right: 10px;"></i>
                    <div style="flex-grow: 1;">
                        <h3 style="margin: 0; font-size: 23px; text-align: center;">Number of Enumerators</h3>
                        <p style="font-size: 50px; color: black; margin: 0; text-align: center;">{unique_enumerators}</p>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            # Value box 6: Average Interviews per Enumerator
            with col6:
                st.markdown(
                    f"""
                <div style="display: flex; align-items: center; padding: 10px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
                    <i class="fas fa-chart-line" style="font-size: 75px; color: black; margin-right: 10px;"></i>
                    <div style="flex-grow: 1;">
                        <h3 style="margin: 0; font-size: 25px; text-align: center;">Average Interviews per Enumerator</h3>
                        <p style="font-size: 47px; color: black; margin: 0; text-align: center;">{rounded_average}</p>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            # Value box 7: Avg interviews per day per enumerator
            with col7:
                st.markdown(
                    f"""
                <div style="display: flex; align-items: center; justify-content: center; padding: 5px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
                    <i class="fas fa-calendar-check" style="font-size: 75px; color: black; margin-right: 10px;"></i>
                    <div style="flex-grow: 1; text-align: center;">
                        <h3 style="margin: 0; font-size: 24px;">Average Interviews per Day per Enumerator</h3>
                        <p style="font-size: 50px; color: black; margin: 0;">{rounded_average_day_per_enumerator}</p>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            # Value box 8: Interviews Left
            with col8:
                st.markdown(
                    f"""
                <div style="display: flex; align-items: center; justify-content: center; padding: 1px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
                    <i class="fas fa-pen-to-square" style="font-size: 70px; color: black; margin-right: 10px;"></i>
                    <div style="flex-grow: 1; text-align: center;">
                        <h3 style="margin: 0; font-size: 25px;">Number of Interviews Left to Reach Goal</h3>
                        <p style="font-size: 50px; color: black; margin: 0;">{interviews_left}</p>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            # Calculate todays date
            today = datetime.now().strftime(
                "%B %d, %Y"
            )  # Format: Month day, year (e.g., August 22, 2024)

            # Creat text
            last_updated_text = f"Last update: {today}"

            # Show text
            st.write(last_updated_text)

        ##### Survey Progress #####
        with tab3:
            df2 = df

            col1, col2, col3 = st.columns(3)

            with col1:
                # Add CSS to ensure table width matches selectbox
                st.markdown(
                    """
                    <style>
                        .stDataFrame {
                            width: 100%;
                        }
                        .dataframe {
                            width: 100%;
                        }
                    </style>
                """,
                    unsafe_allow_html=True,
                )

                consent_col = st.selectbox(
                    "Select your consent variable",
                    options=df2.columns,
                    index=df2.columns.get_loc("consent"),
                )

                summary = df2.groupby(consent_col)["id"].nunique().reset_index()
                summary.columns = ["Consent Status", "Unique ID Count"]

                st.table(summary)

                # Modify consent variable - Define values of consent/no consent
                mapping = {1: "Consent", 0: "No Consent"}
                df2["consent"] = df2["consent"].map(mapping)

                # Group by 'id' and count unique values of "key"
                unique_counts = df.groupby("id")["key"].nunique().reset_index()
                unique_counts.columns = ["id", "unique_key_count"]

                # Count unique ids from the new df
                count_unique_ids = unique_counts["id"].nunique()

            with col2:
                # Group by 'id' and count unique values of "key"
                unique_counts = df.groupby("id")["key"].nunique().reset_index()
                unique_counts.columns = ["id", "unique_key_count"]

                # Count unique ids by number of counts from the new df
                count_unique_ids = (
                    unique_counts.groupby("unique_key_count").count().reset_index()
                )

                # Show result
                st.write("Unique IDs by number of attempts:")

                # Define the color scale
                colors = [
                    "#2C5F2D",
                    "#74AA76",
                    "#9ECED7",
                    "#4D5E90",
                    "#DE9461",
                    "#B9ABE6",
                    "#E0C97D",
                    "#636892",
                ]

                # Create the Plotly figure
                fig = go.Figure(
                    data=[
                        go.Pie(
                            labels=count_unique_ids.unique_key_count,
                            values=count_unique_ids["id"],
                            hole=0.3,
                            marker=dict(colors=colors),
                        )
                    ]
                )

                # Update the layout
                fig.update_layout(
                    title="Unique IDs by number of attempts",
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    font_color="black",
                    font_family="Arial",
                    font_size=14,
                )

                st.plotly_chart(fig, theme="streamlit", use_container_width=True)

            # Group by date and count number of IDs
            count_by_date = (
                df.groupby("date_only").size().reset_index(name="num_interviews")
            )

            # Calculate the average of interviews per day
            average_interviews_per_day = count_by_date["num_interviews"].mean()

            # Create the figure with secondary y-axis
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            with col3:
                # Create a new DataFrame for the table
                table_data = df[["id", "submissiondate", "consent"]].copy()
                table_data["number_of_attempts"] = table_data["id"].map(
                    unique_counts.set_index("id")["unique_key_count"]
                )

                # Reorder the columns
                table_data = table_data[
                    ["number_of_attempts", "id", "submissiondate", "consent"]
                ]

                # Add text filter
                query = st.text_input("Filter by number of attempts")
                if query:
                    try:
                        query_num = int(query)
                        filtered_table = table_data[
                            table_data["number_of_attempts"] >= query_num
                        ]
                    except ValueError:
                        st.warning("Please enter a valid number")
                        filtered_table = table_data
                else:
                    filtered_table = table_data

                # Display the table
                st.write("Detailed Information Table:")
                st.dataframe(filtered_table, use_container_width=True)

                # Show the count of filtered results
                st.write(f"Number of entries shown: {len(filtered_table)}")

            # Add bar plot
            fig.add_trace(
                go.Bar(
                    x=count_by_date["date_only"],
                    y=count_by_date["num_interviews"],
                    name="Interviews",
                    marker_color="forestgreen",
                    hovertemplate=(
                        "Date: %{x|%Y-%m-%d}<br>"
                        "Interviews: %{y}<br>"
                        f"Overall Average: {average_interviews_per_day:.2f}<extra></extra>"
                    ),
                ),
                secondary_y=False,
            )

            # Add a line for the average
            fig.add_trace(
                go.Scatter(
                    x=[
                        count_by_date["date_only"].min(),
                        count_by_date["date_only"].max(),
                    ],
                    y=[average_interviews_per_day, average_interviews_per_day],
                    mode="lines",
                    name=f"Average: {average_interviews_per_day:.2f}",
                    line=dict(color="red", width=2, dash="dash"),
                    hoverinfo="name+y",
                ),
                secondary_y=False,
            )

            # Update layout
            fig.update_layout(
                title="Interviews per Day",
                xaxis_title="Date",
                yaxis_title="Number of Interviews",
                hovermode="closest",
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
                ),
            )

            # Update x-axis
            fig.update_xaxes(tickangle=-45, tickformat="%Y-%m-%d")

            # Update y-axis
            fig.update_yaxes(gridcolor="lightgrey", griddash="dot")
            fig.update_layout(
                xaxis=dict(type="category", categoryorder="category ascending")
            )
            # Show graph
            st.plotly_chart(fig, theme="streamlit", use_container_width=True)

        ##### Duplicates #####
        with tab4:
            # Add CSS for consistent width
            st.markdown(
                """
                <style>
                    .stDataFrame {
                        width: 100%;
                    }
                    .dataframe {
                        width: 100%;
                    }
                </style>
            """,
                unsafe_allow_html=True,
            )

            selected_col = st.selectbox(
                "Select a variable by which you'd like identify duplicates (id, phone number, etc.)",
                df4.columns,
            )

            # Count duplicates by ID
            df4["num_dups"] = df4[selected_col].map(df4[selected_col].value_counts())

            # Filter rows with duplicates and without missing
            df_duplicates = df4[
                (df4["num_dups"] > 1)
                & (df4[selected_col].notna())
                & (df4[selected_col] != "")
            ]

            if df_duplicates.empty:
                st.write("No duplicates")
            else:
                # Sort by num_dups in descending order
                df_duplicates = df_duplicates.sort_values("num_dups", ascending=[False])

                # Include the selected column in the result
                if selected_col == "id" or selected_col == id_variable:
                    result = df_duplicates[["id", "num_dups", "submissiondate", "key"]]
                else:
                    result = df_duplicates[
                        ["id", selected_col, "num_dups", "submissiondate", "key"]
                    ]

                # Display using st.dataframe with configurations for better display
                st.dataframe(
                    result,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "id": st.column_config.Column(
                            label=id_variable, width="medium"
                        ),
                        selected_col: st.column_config.Column(width="medium"),
                        "num_dups": st.column_config.NumberColumn(
                            "Number of Duplicates", width="small"
                        ),
                        "submissiondate": st.column_config.DateColumn(
                            "Submission Date", width="medium"
                        ),
                        "key": st.column_config.Column(width="medium"),
                    },
                )

        ##### Enumerator Statistics #####
        with tab5:
            col1, col2 = st.columns(2)

            with col1:
                df3["date"] = pd.to_datetime(df3["date_only"])

                # Radio button for calculations
                calculation_type = st.radio(
                    "Select calculation type:",
                    ("Graph with Overall Results", "Graph with Results per Date"),
                )

                # Date input for filtering if "Calculations per Date" is selected
                if calculation_type == "Graph with Results per Date":
                    date_filter = st.date_input("Select date")
                    filtered_df = df3[df3["date"] == pd.to_datetime(date_filter)]
                else:
                    filtered_df = df3

                # Calculate average duration time per enumerator
                if filtered_df.shape[0] > 0:
                    average_duration = (
                        filtered_df.groupby("enumid", observed=False)
                        .agg(avg_duration=("duration_mins", "mean"))
                        .reset_index()
                    )

                    # Sort values by avg_duration
                    average_duration = average_duration.sort_values(
                        by="avg_duration", ascending=True
                    )

                    # Calculate overall average duration
                    overall_avg_duration = average_duration["avg_duration"].mean()

                    # Calculate standard deviation
                    std_dev = average_duration["avg_duration"].std()

                    # Calculate how many standard deviations away each average
                    # is from the overall average
                    average_duration["std_dev_away"] = (
                        average_duration["avg_duration"] - overall_avg_duration
                    ) / std_dev

                    # Create the plot with different colors for each bar
                    fig = px.bar(
                        average_duration,
                        x="enumid",
                        y="avg_duration",
                        title="Average Duration per Enumerator",
                        labels={
                            "avg_duration": "Average Duration (minutes)",
                            "enumid": "Enumerator ID",
                        },
                        color="std_dev_away",  # Color by how many std dev away from the mean
                        color_continuous_scale=px.colors.sequential.Viridis[::-1],
                    )

                    fig.update_xaxes(tickangle=90, tickmode="auto")

                    # Customize hover template
                    fig.update_traces(
                        hovertemplate="<b>Enumerator ID:</b> %{x}<br>"
                        + "<b>Average Duration:</b> %{y} minutes<br>"
                        + f"<b>Overall Average:</b> {overall_avg_duration:.2f} minutes<br>"
                        + "<b>Standard Deviations Away:</b> %{customdata:.2f}",
                        customdata=average_duration["std_dev_away"].values,
                    )

                    # Add overall average line
                    fig.add_hline(
                        y=overall_avg_duration, line_color="red", line_dash="dash"
                    )

                    fig.update_layout(xaxis=dict(type="category"))

                    # Show the figure
                    st.plotly_chart(fig, theme="streamlit", use_container_width=True)
                else:
                    st.warning("No data available for the selected criteria.")

            with col2:
                # Add CSS for consistent width
                st.markdown(
                    """
                <style>
                    .stDataFrame {
                        width: 100%;
                    }
                    .dataframe {
                        width: 25%;
                    }
                </style>
                """,
                    unsafe_allow_html=True,
                )

                # Checkbox for calculations
                calculation_type = st.radio(
                    "Select calculation type:",
                    ("Calculations per Period", "Calculations per Date"),
                )

                # Date input for filtering
                if calculation_type == "Calculations per Date":
                    date_filter = st.date_input("Select a date")
                    df1["date"] = pd.to_datetime(df1["date_only"])
                    filtered_df = df1[df1["date"] == pd.to_datetime(date_filter)]
                else:
                    filtered_df = df1

                if filtered_df.shape[0] > 0:
                    # Summary calculation for consent data
                    summary = (
                        filtered_df.groupby("enumid", observed=False)
                        .agg(
                            total_persons=("id", "size"),
                            consented_persons=("consent", lambda x: (x == 1).sum()),
                        )
                        .reset_index()
                    )

                    # Convert to numeric and calculate consent percentage
                    summary["consented_persons"] = pd.to_numeric(
                        summary["consented_persons"], errors="coerce"
                    )
                    summary["total_persons"] = pd.to_numeric(
                        summary["total_persons"], errors="coerce"
                    )
                    summary["consent_percentage"] = (
                        summary["consented_persons"] / summary["total_persons"]
                    ) * 100

                    # Rename columns for consent data
                    summary.rename(
                        columns={
                            "enumid": "Enumerator ID",
                            "total_persons": "Total Interviews",
                            "consented_persons": "Consented Interviews",
                            "consent_percentage": "Consent Percentage",
                        },
                        inplace=True,
                    )

                    # Backcheck analysis
                    if "merged_df" in locals():
                        # Calculate statistics for original enumerators
                        survey_counts = (
                            df1.groupby("enumid")
                            .size()
                            .reset_index(name="Total Surveys")
                        )

                        # Count how many times each enumerator's work was backchecked
                        backcheck_counts = (
                            merged_df.groupby("enumid")
                            .size()
                            .reset_index(name="Backchecked Interviews")
                        )

                        # Get comparable variables
                        comparable_vars = []
                        prefix_pairs = []
                        svy_cols = [
                            col for col in merged_df.columns if col.startswith("svy_")
                        ]

                        for svy_col in svy_cols:
                            base_var = svy_col[4:]
                            back_col = f"back_{base_var}"
                            if back_col in merged_df.columns:
                                comparable_vars.append(base_var)
                                prefix_pairs.append((svy_col, back_col))

                        # Count mismatches for each enumerator
                        def count_mismatches(group):
                            """Count mismatches between survey and backcheck
                            values for a given group.

                            Args:
                                group (pd.DataFrame): DataFrame containing
                                survey and backcheck values.

                            Returns
                            -------
                                int: Number of mismatches.

                            """
                            mismatch_count = 0
                            for svy_col, back_col in prefix_pairs:
                                svy_values = group[svy_col].astype(str)
                                back_values = group[back_col].astype(str)
                                svy_values = svy_values.replace("nan", "")
                                back_values = back_values.replace("nan", "")
                                mismatch_count += (svy_values != back_values).sum()
                            return mismatch_count

                        if len(comparable_vars) > 0:
                            try:
                                # Calculate mismatches by enumerator
                                mismatch_counts = (
                                    merged_df.groupby("enumid")
                                    .apply(count_mismatches)
                                    .reset_index(name="Total Mismatches")
                                )

                                # Calculate backcheck metrics
                                backcheck_data = survey_counts.merge(
                                    backcheck_counts, on="enumid", how="left"
                                )

                                # Fill NaN values with 0 for enumerators with
                                # no backchecks
                                backcheck_data["Backchecked Interviews"] = (
                                    backcheck_data["Backchecked Interviews"]
                                    .fillna(0)
                                    .astype(int)
                                )

                                # Calculate total surveys that can be compared
                                backcheck_data["Values Compared"] = (
                                    backcheck_data["Backchecked Interviews"]
                                    * len(comparable_vars)
                                ).astype(int)

                                # Merge with mismatch counts
                                backcheck_data = backcheck_data.merge(
                                    mismatch_counts, on="enumid", how="left"
                                )

                                # Fill NaN values for mismatches
                                backcheck_data["Total Mismatches"] = (
                                    backcheck_data["Total Mismatches"]
                                    .fillna(0)
                                    .astype(int)
                                )

                                # Calculate percentages
                                backcheck_data["Backchecked Percentage"] = (
                                    backcheck_data["Backchecked Interviews"]
                                    / backcheck_data["Total Surveys"]
                                    * 100
                                ).round(2)

                                backcheck_data["Mismatch Percentage"] = (
                                    backcheck_data["Total Mismatches"]
                                    / backcheck_data["Values Compared"]
                                    * 100
                                ).round(2)

                                # Merge consent summary with backcheck data
                                combined_summary = summary.merge(
                                    backcheck_data,
                                    left_on="Enumerator ID",
                                    right_on="enumid",
                                    how="outer",
                                )

                                # Clean up the merged dataframe
                                combined_summary = combined_summary.drop(
                                    ["enumid", "Total Surveys"], axis=1
                                )

                                # Format percentage columns
                                combined_summary["Consent Percentage"] = (
                                    combined_summary["Consent Percentage"].round(2)
                                )
                                combined_summary["Backchecked Percentage"] = (
                                    combined_summary["Backchecked Percentage"].round(2)
                                )
                                combined_summary["Mismatch Percentage"] = (
                                    combined_summary["Mismatch Percentage"].round(2)
                                )

                                # Define the desired column order
                                column_order = [
                                    "Enumerator ID",
                                    "Total Interviews",
                                    "Consented Interviews",
                                    "Consent Percentage",
                                    "Backchecked Interviews",
                                    "Backchecked Percentage",
                                    "Values Compared",
                                    "Total Mismatches",
                                    "Mismatch Percentage",
                                ]

                                # Reorder the columns in the combined_summary DataFrame
                                combined_summary = combined_summary[column_order]

                                # Display combined summary with the new column order
                                st.dataframe(
                                    combined_summary,
                                    hide_index=True,
                                    use_container_width=True,
                                    column_config={
                                        "Enumerator ID": st.column_config.Column(
                                            width="small"
                                        ),
                                        "Total Interviews": st.column_config.NumberColumn(
                                            format="%d", width="small"
                                        ),
                                        "Consented Interviews": st.column_config.NumberColumn(
                                            format="%d", width="small"
                                        ),
                                        "Consent Percentage": st.column_config.NumberColumn(
                                            format="%.2f%%", width="small"
                                        ),
                                        "Backchecked Interviews": st.column_config.NumberColumn(
                                            format="%d", width="small"
                                        ),
                                        "Backchecked Percentage": st.column_config.NumberColumn(
                                            format="%.2f%%", width="small"
                                        ),
                                        "Values Compared": st.column_config.NumberColumn(
                                            format="%d", width="small"
                                        ),
                                        "Total Mismatches": st.column_config.NumberColumn(
                                            format="%d", width="small"
                                        ),
                                        "Mismatch Percentage": st.column_config.NumberColumn(
                                            format="%.2f%%", width="small"
                                        ),
                                    },
                                )

                                # Display number of comparable variables
                                st.write(
                                    f"Note: For backchecks calculations there were found {len(comparable_vars)} comparable variables."
                                )

                            except Exception as e:
                                st.error(f"Error calculating combined metrics: {e!s}")
                        else:
                            st.warning(
                                "No comparable variables found for backcheck analysis."
                            )
                    else:
                        st.warning(
                            "No backcheck data available. Displaying only consent data."
                        )
                        st.dataframe(
                            summary,
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "Enumerator ID": st.column_config.Column(width="small"),
                                "Total Interviews": st.column_config.NumberColumn(
                                    format="%d", width="small"
                                ),
                                "Consent Percentage": st.column_config.NumberColumn(
                                    format="%.2f%%", width="small"
                                ),
                            },
                        )
                else:
                    st.warning("No data available for the selected criteria.")

            col3 = st.columns(1)[0]

            with col3:
                df5 = df3[["date_only", "enumid", "key", "duration_mins"]].copy()

                # Rename columns for consistency
                df5["date"] = pd.to_datetime(df5["date_only"])

                # Ensure enumid is of type string
                df5["enumid"] = df5["enumid"].astype(str)

                # Calculate average duration time per enumerator
                average_duration = (
                    df5.groupby("enumid", observed=False)
                    .agg(avg_duration=("duration_mins", "mean"))
                    .reset_index()
                )

                # Calculate overall average duration
                current_avg_duration = average_duration["avg_duration"].mean()

                # Compute cumulative count of surveys by enumerator and date
                df5 = (
                    df5.groupby(["date", "enumid"])
                    .agg({"key": "nunique", "duration_mins": "mean"})
                    .reset_index()
                )
                df5 = df5.sort_values(["enumid", "date"], ascending=[False, True])
                df5["cumsum_surveys"] = df5.groupby(["enumid"])["key"].cumsum()
                df5 = df5.sort_values("date", ascending=True)

                # Calculate the min and max of the duration variable
                y_min = df5["duration_mins"].min()
                y_max = df5["duration_mins"].max()

                # Create cross join of dates and enumerators
                dates = pd.DataFrame({"date": df5["date"].unique()}).sort_values(
                    "date", ascending=True
                )
                enums = pd.DataFrame({"enumid": df5["enumid"].unique()}).sort_values(
                    "enumid", ascending=True
                )
                crossjoin = dates.merge(enums, how="cross")

                # Merge the cross join with the original data
                merged = crossjoin.merge(
                    df5, how="left", on=["date", "enumid"]
                ).sort_values(["enumid", "date"], ascending=[False, True])
                merged.update(merged.groupby(["enumid"]).ffill())

                # Fill remaining NaN values with 0
                merged = merged.fillna(0)

                # Ensure all columns are of the correct type
                merged["cumsum_surveys"] = merged["cumsum_surveys"].astype(float)
                merged["duration_mins"] = merged["duration_mins"].astype(float)

                # Calculate the min and max of the cumulative count
                x_min = df5["cumsum_surveys"].min()
                x_max = df5["cumsum_surveys"].max()

                # Create a new format for the date
                merged["display_date"] = pd.to_datetime(merged["date"]).dt.strftime(
                    "%m/%d"
                )

                # Create scatter plot
                fig = px.scatter(
                    merged,
                    x="cumsum_surveys",
                    y="duration_mins",
                    animation_frame="display_date",
                    color="enumid",
                    animation_group="enumid",
                    size="cumsum_surveys",
                    hover_name="enumid",
                    range_x=[x_min, x_max],
                    range_y=[y_min, y_max],
                    width=1300,
                    height=600,
                )

                # Update layout to set axis titles and hide legend
                fig.update_layout(
                    xaxis_title="Cumulative Surveys",
                    yaxis_title="Average Duration (minutes)",
                    showlegend=False,
                    sliders=[
                        {
                            "currentvalue": {
                                "font": {"size": 8},
                                "prefix": "Date: ",
                                "xanchor": "right",
                                "offset": 10,
                            },
                            "pad": {"t": 40},
                            "len": 0.9,
                            "x": 0.1,
                            "y": 0,
                        }
                    ],
                )

                # Add a dashed line for the overall average duration
                fig.add_shape(
                    type="line",
                    x0=0,
                    y0=current_avg_duration,
                    x1=30,
                    y1=current_avg_duration,
                    line=dict(color="red", width=2, dash="dash"),
                    name="Overall Average",
                )

                # Add notes to the shape
                fig.add_annotation(
                    x=x_max,
                    y=current_avg_duration,
                    text=f"Overall Average: {current_avg_duration:.2f}",
                    showarrow=False,
                    font=dict(color="red"),
                )

                st.plotly_chart(fig, theme="streamlit", use_container_width=True)

        #####  Missing #####
        with tab6:

            def analyze_missing_values(df6, codes, labels):
                """Analyze missing values in the dataframe and display the results.

                Args:
                    df6 (pd.DataFrame): The dataframe to analyze.
                    codes (list): List of codes representing missing values.
                    labels (list): List of labels corresponding to the codes.

                Returns
                -------
                    None

                """
                # Initialize empty lists to store results
                results = []

                for column in df6.columns:
                    # Count not coded missing (NA, empty spaces, empty strings)
                    not_coded = (
                        df6[column].isna().sum()
                        + (df6[column] == " ").sum()
                        + (df6[column] == "").sum()
                    )

                    # Initialize dictionary for the row
                    row_dict = {
                        "Variable": column,
                        "Total Missing": not_coded,  # Initialize with not_coded
                        "Not Coded": not_coded,
                    }

                    # Add counts and update total for each code/label pair
                    for code, label in zip(codes, labels, strict=False):
                        count = (df6[column] == code).sum()
                        row_dict[f"{label} ({code})"] = count
                        row_dict["Total Missing"] += count  # Add to total

                    # Calculate and add percentages
                    total_rows = len(df6)
                    row_dict["Total Missing (%)"] = (
                        row_dict["Total Missing"] / total_rows
                    ) * 100
                    row_dict["Not Coded (%)"] = (not_coded / total_rows) * 100

                    # Add percentages for each code/label pair
                    for code, label in zip(codes, labels, strict=False):
                        count = row_dict[f"{label} ({code})"]
                        row_dict[f"{label} ({code}) (%)"] = (count / total_rows) * 100

                    results.append(row_dict)

                # Create DataFrame from results
                missing_data = pd.DataFrame(results)

                # Create the slider
                missing_threshold = st.slider(
                    "Variables with % of missing values above:", 0, 100, 1
                )

                # Filter based on total missing percentage
                missing_data_filtered = missing_data[
                    missing_data["Total Missing (%)"] >= missing_threshold
                ]

                if not missing_data_filtered.empty:
                    # Create two tabs
                    tab1, tab2 = st.tabs(["Percentages", "Total Count"])

                    with tab1:
                        # Create list of columns for percentages
                        pct_columns = [
                            "Variable",
                            "Total Missing (%)",
                            "Not Coded (%)",
                        ]
                        pct_columns.extend(
                            [
                                f"{label} ({code}) (%)"
                                for code, label in zip(codes, labels, strict=False)
                            ]
                        )

                        # Display percentages DataFrame
                        percentages_df = missing_data_filtered[pct_columns]

                        # Create column config for percentages
                        pct_config = {
                            "Variable": st.column_config.Column(width="medium")
                        }

                        # Add percentage format for all percentage columns
                        for col in pct_columns[1:]:  # Skip 'Column'
                            pct_config[col] = st.column_config.NumberColumn(
                                format="%.1f%%", width="small"
                            )

                        st.dataframe(
                            percentages_df,
                            hide_index=True,
                            use_container_width=True,
                            column_config=pct_config,
                        )

                    with tab2:
                        # Create list of columns for counts
                        count_columns = ["Variable", "Total Missing", "Not Coded"]
                        count_columns.extend(
                            [
                                f"{label} ({code})"
                                for code, label in zip(codes, labels, strict=False)
                            ]
                        )

                        # Display counts DataFrame
                        counts_df = missing_data_filtered[count_columns]

                        # Create column config for counts
                        count_config = {
                            "Variable": st.column_config.Column(width="medium")
                        }

                        # Add number format for all count columns
                        for col in count_columns[1:]:  # Skip 'Column'
                            count_config[col] = st.column_config.NumberColumn(
                                format="%d", width="small"
                            )

                        st.dataframe(
                            counts_df,
                            hide_index=True,
                            use_container_width=True,
                            column_config=count_config,
                        )

                else:
                    st.write(
                        "There are no variables with more than",
                        missing_threshold,
                        "% missing values.",
                    )

            analyze_missing_values(df6, codes, labels)
            st.write(
                "Note: The calculations for 'Not Coded' includes values of ' . ', 'NA' and empty cells."
            )

        ##### Outliers #####
        with tab7:
            col1, col2 = st.columns(2)

            with col1:
                outlier_method = st.radio(
                    "Select your preferred method for outlier detection:",
                    options=["Interquartile Range (IQR)", "Standard Deviation (+/-)"],
                )

                if outlier_method == "Standard Deviation (+/-)":
                    sd_value = st.number_input("Number of Standard Deviations:")

                numeric_columns = df.select_dtypes(include=[np.number]).columns.tolist()

                selected_col = st.selectbox(
                    "Select a variable to check for outliers", numeric_columns
                )

                # Define bounds
                series = df[selected_col].dropna()
                total_count = len(series)

                if outlier_method == "Interquartile Range (IQR)":
                    Q1 = series.quantile(0.25)
                    Q3 = series.quantile(0.75)
                    IQR = Q3 - Q1
                    lower_bound = Q1 - 1.5 * IQR
                    upper_bound = Q3 + 1.5 * IQR
                elif outlier_method == "Standard Deviation (+/-)":
                    mean = series.mean()
                    std_dev = series.std()
                    lower_bound = mean - sd_value * std_dev
                    upper_bound = mean + sd_value * std_dev

                # Find outliers
                outliers = series[(series < lower_bound) | (series > upper_bound)]
                outliers_df = df[df[selected_col].isin(outliers)]

                # Prepare data for the table
                table_data = outliers_df[["id", "enumid"]].copy()
                table_data["variable_value"] = outliers_df[selected_col].round(2)
                table_data["mean"] = round(series.mean(), 2)
                table_data["lower_bound"] = round(lower_bound, 2)
                table_data["upper_bound"] = round(upper_bound, 2)

                # Display using st.dataframe with proper formatting
                st.dataframe(
                    table_data,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "id": st.column_config.Column("ID", width="small"),
                        "enumid": st.column_config.Column("Enumid", width="small"),
                        "variable_value": st.column_config.NumberColumn(
                            "Value", format="%.2f", width="small"
                        ),
                        "mean": st.column_config.NumberColumn(
                            "Mean", format="%.2f", width="small"
                        ),
                        "lower_bound": st.column_config.NumberColumn(
                            "Lower Bound", format="%.2f", width="small"
                        ),
                        "upper_bound": st.column_config.NumberColumn(
                            "Upper Bound", format="%.2f", width="small"
                        ),
                    },
                )

            with col2:
                # Calculate percentage of outliers
                if outliers_df.empty:
                    st.write(
                        "No outliers found on this variable according to the selected method and threshold."
                    )
                else:
                    outlier_count = len(outliers)
                    outlier_percentage = (outlier_count / total_count) * 100
                    formatted_outlier_percentage = f"{outlier_percentage:.2f}%"

                    st.metric(
                        value=formatted_outlier_percentage, label="Share of outliers"
                    )

                fig = go.Figure(
                    data=go.Violin(
                        y=df[selected_col],
                        box_visible=True,
                        line_color="black",
                        meanline_visible=True,
                        fillcolor="darkgreen",
                        opacity=0.6,
                        x0=selected_col,
                    )
                )

                st.plotly_chart(fig, theme="streamlit", use_container_width=True)

            col1, col2 = st.columns(2)

            with col1:

                def find_variable_patterns(columns):
                    """Identify patterns in variable names based on underscores.

                    Args:
                        columns (list): List of column names.

                    Returns
                    -------
                        dict: Dictionary with base patterns as keys and lists
                        of matching columns as values.

                    """
                    patterns = defaultdict(list)
                    for col in columns:
                        # Split the column name on underscores
                        parts = col.split("_")

                        # Identify the base pattern
                        base = "_".join(parts[:-1])

                        # Append the column to the list for this base pattern
                        patterns[base].append(col)

                    # Filter out single-variable patterns
                    return {k: v for k, v in patterns.items() if len(v) > 1}

                def show_pattern_selection(df, numeric_columns):
                    """Display a pattern selection dropdown for variable names
                    and return the selected columns and melted DataFrame.

                    Args:
                        df (pd.DataFrame): The input DataFrame.
                        numeric_columns (list): List of numeric column names.

                    Returns
                    -------
                        tuple: A tuple containing the selected columns and the
                        melted DataFrame.

                    """
                    pattern_groups = find_variable_patterns(numeric_columns)
                    if not pattern_groups:
                        return None, None

                    pattern_options = [
                        f"{pattern} ({len(cols)} variables)"
                        for pattern, cols in pattern_groups.items()
                    ]
                    pattern_to_base = {
                        display: pattern
                        for pattern, display in zip(
                            pattern_groups, pattern_options, strict=False
                        )
                    }

                    selected_pattern = st.selectbox(
                        """If you'd like to detect outliers based on a joint
                        distribution of several variables (for example,
                        same variable corresponding to different household
                        members), please select the set of variables""",
                        options=sorted(pattern_options),
                        help="""Choose a group of related variables to analyze.
                                Only numeric variables are shown.
                             """,
                    )

                    if selected_pattern:
                        base_pattern = pattern_to_base[selected_pattern]
                        selected_cols = pattern_groups[base_pattern]

                        with st.expander(
                            f"Show selected variables for '{base_pattern}'"
                        ):
                            st.write(", ".join(selected_cols))

                        df_subset = df[["id", *selected_cols]]
                        df_melted = pd.melt(
                            df_subset,
                            id_vars=["id"],
                            value_vars=selected_cols,
                            var_name="name_variable",
                            value_name="new_var",
                        )
                        return selected_cols, df_melted

                    return None, None

                selected_cols, df_melted = show_pattern_selection(df, numeric_columns)

                if selected_cols and df_melted is not None:
                    series = df_melted["new_var"].dropna()
                    total_count = len(series)

                    if outlier_method == "Interquartile Range (IQR)":
                        Q1 = series.quantile(0.25)
                        Q3 = series.quantile(0.75)
                        IQR = Q3 - Q1
                        lower_bound = Q1 - 1.5 * IQR
                        upper_bound = Q3 + 1.5 * IQR
                    elif outlier_method == "Standard Deviation (+/-)":
                        mean = series.mean()
                        std_dev = series.std()
                        lower_bound = mean - sd_value * std_dev
                        upper_bound = mean + sd_value * std_dev

                    outliers = series[(series < lower_bound) | (series > upper_bound)]
                    outliers_df = df_melted[df_melted["new_var"].isin(outliers)]

                    table_data = outliers_df[["id", "name_variable"]].copy()
                    table_data["new_var"] = outliers_df["new_var"].round(2)
                    table_data["mean"] = round(series.mean(), 2)
                    table_data["lower_bound"] = round(lower_bound, 2)
                    table_data["upper_bound"] = round(upper_bound, 2)

                    st.dataframe(
                        table_data,
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "id": st.column_config.Column("ID", width="small"),
                            "name_variable": st.column_config.Column("Variable Name"),
                            "new_var": st.column_config.NumberColumn(
                                "Value", format="%.2f", width="small"
                            ),
                            "mean": st.column_config.NumberColumn(
                                "Mean", format="%.2f", width="small"
                            ),
                            "lower_bound": st.column_config.NumberColumn(
                                "Lower Bound", format="%.2f", width="small"
                            ),
                            "upper_bound": st.column_config.NumberColumn(
                                "Upper Bound", format="%.2f", width="small"
                            ),
                        },
                    )

            with col2:
                # Check if outliers_df is not empty
                if outliers_df.empty:
                    st.write(
                        "No outliers found on this variable according to the selected method and threshold."
                    )
                else:
                    # Calculate percentage of outliers
                    outlier_count = len(outliers)
                    outlier_percentage = (outlier_count / total_count) * 100
                    formatted_outlier_percentage = f"{outlier_percentage:.2f}%"

                    st.metric(
                        value=formatted_outlier_percentage, label="Share of outliers"
                    )

                # Function to find the common prefix
                def common_prefix(strs):
                    """Find the longest common prefix string amongst an array
                    of strings.

                    Args:
                        strs (list): List of strings.

                    Returns
                    -------
                        str: The longest common prefix.

                    """
                    if not strs:
                        return ""
                    prefix = strs[0]
                    for s in strs[1:]:
                        while not s.startswith(prefix):
                            prefix = prefix[:-1]
                            if not prefix:
                                return ""
                    return prefix

                # Get common prefix
                x_axis_label = common_prefix(selected_cols)

                fig = go.Figure(
                    data=go.Violin(
                        y=df_melted["new_var"],
                        box_visible=True,
                        line_color="black",
                        meanline_visible=True,
                        fillcolor="forestgreen",
                        opacity=0.6,
                        x0=x_axis_label,
                    )
                )

                st.plotly_chart(fig, theme="streamlit", use_container_width=True)

        ##### Back Checks #####
        with tab8:
            if "merged_df" in st.session_state:
                st.subheader("Select Variables and Perform Comparison")

                # Check if merged_df exists in session state
                merged_df = st.session_state.merged_df
                existing_df = st.session_state.existing_df

                # Find matching variable pairs (survey and backcheck variables)
                svy_vars = [col for col in merged_df.columns if col.startswith("svy_")]
                back_vars = [
                    col for col in merged_df.columns if col.startswith("back_")
                ]

                # Create pairs of variables that exist in both datasets
                var_pairs = []
                for svy in svy_vars:
                    base_name = svy[4:]
                    back_name = f"back_{base_name}"
                    if back_name in back_vars:
                        var_pairs.append(base_name)

                # Allow the user to select variables to compare
                selected_vars = st.multiselect(
                    "Select variables to compare:", var_pairs
                )

                # Create tabs for each selected variable
                if selected_vars:
                    tabs = st.tabs(
                        [
                            "General Results",
                            "Enumerator Statistics",
                            "Backchecker Statistics",
                            *selected_vars,
                        ]
                    )
                    var_summary = {}
                    mismatches_dict = {}

                    # First get the data types for each variable
                    var_types = {}
                    for var in selected_vars:
                        svy_col = f"svy_{var}"
                        # Check if all values can be converted to numeric
                        try:
                            test_series = merged_df[svy_col].copy()
                            pd.to_numeric(test_series, errors="raise")
                            var_types[var] = "Numeric"
                        except (ValueError, TypeError):
                            var_types[var] = "String"

                    # First tab for "General Results"
                    with tabs[0]:
                        # Given that enum_bcer is a list, access the first element
                        enum_bcer_column = (
                            enum_bcer[0] if isinstance(enum_bcer, list) else enum_bcer
                        )

                        for var in selected_vars:
                            svy_col = f"svy_{var}"
                            back_col = f"back_{var}"

                            comparison_df = pd.DataFrame(
                                {
                                    "Unique Identifier": merged_df[merge_variable],
                                    "Enumerator id": merged_df[enumid_var],
                                    "Backchecker id": merged_df[enum_bcer_column]
                                    if enum_bcer_column in merged_df.columns
                                    else pd.Series([None] * len(merged_df)),
                                    "Survey Value": merged_df[svy_col].astype(str),
                                    "Backcheck Value": merged_df[back_col].astype(str),
                                }
                            )

                            comparison_df["Comparison"] = comparison_df.apply(
                                lambda x: "Match"
                                if str(x["Survey Value"]).strip()
                                == str(x["Backcheck Value"]).strip()
                                else "Mismatch",
                                axis=1,
                            )

                            mismatches_df = comparison_df[
                                comparison_df["Comparison"] == "Mismatch"
                            ]

                            var_summary[var] = {
                                "Variable Type": var_types[var],
                                "total_surveys": len(existing_df),
                                "total_backchecks": len(backcheck_df),
                                "compared": len(comparison_df),
                                "mismatches": len(mismatches_df),
                                "mismatch_percentage": (
                                    len(mismatches_df) / len(comparison_df) * 100
                                )
                                if len(comparison_df) > 0
                                else 0,
                            }

                        # Create the General results table from var_summary
                        enumerator_stats = pd.DataFrame.from_dict(
                            var_summary, orient="index"
                        )
                        enumerator_stats = enumerator_stats.reset_index()
                        enumerator_stats.columns = [
                            "Selected Variables",
                            "Variable Type",
                            "Total Surveys",
                            "Total Backchecks",
                            "# Compared",
                            "# Different",
                            "% Different",
                        ]

                        # Format the "% different" column
                        enumerator_stats["% Different"] = (
                            enumerator_stats["% Different"].round(2)
                        ).astype(str) + "%"

                        # Display the general results table
                        st.subheader("General Results")
                        st.dataframe(enumerator_stats, use_container_width=True)

                    # New tab for "Enumerator Statistics"
                    with tabs[1]:
                        st.subheader("Enumerator Statistics")

                        # Calculate statistics per enumerator
                        enumerator_detailed_stats = {}

                        # First get total surveys per enumerator from existing_df
                        total_surveys = existing_df[enumid_var].value_counts().to_dict()

                        # For each enumerator in the original dataset
                        for enum_id in existing_df[enumid_var].unique():
                            enumerator_detailed_stats[enum_id] = {
                                "total_surveys": total_surveys.get(enum_id, 0),
                                "total_backchecks": 0,
                                "total_compared": 0,
                                "total_different": 0,
                            }

                        # Calculate backchecks and comparisons
                        for var in selected_vars:
                            svy_col = f"svy_{var}"
                            back_col = f"back_{var}"

                            # Create comparison data for this variable
                            comparison = pd.DataFrame(
                                {
                                    "enumerator_id": merged_df[enumid_var],
                                    "survey_value": merged_df[svy_col].astype(str),
                                    "backcheck_value": merged_df[back_col].astype(str),
                                }
                            )

                            # Mark matches/mismatches
                            comparison["is_different"] = comparison.apply(
                                lambda x: str(x["survey_value"]).strip()
                                != str(x["backcheck_value"]).strip(),
                                axis=1,
                            )

                            # Group by enumerator and update statistics
                            for enum_id in comparison["enumerator_id"].unique():
                                if enum_id not in enumerator_detailed_stats:
                                    # Handle case where enumerator is in
                                    # backcheck but not in original data
                                    enumerator_detailed_stats[enum_id] = {
                                        "total_surveys": 0,
                                        "total_backchecks": 0,
                                        "total_compared": 0,
                                        "total_different": 0,
                                    }

                                enum_data = comparison[
                                    comparison["enumerator_id"] == enum_id
                                ]

                                # Only update backcheck count once per variable loop
                                if var == selected_vars[0]:  # First variable only
                                    enumerator_detailed_stats[enum_id][
                                        "total_backchecks"
                                    ] = len(enum_data)

                                enumerator_detailed_stats[enum_id][
                                    "total_compared"
                                ] += len(enum_data)
                                enumerator_detailed_stats[enum_id][
                                    "total_different"
                                ] += enum_data["is_different"].sum()

                        # Create DataFrame from enumerator statistics
                        enumerator_detailed_df = pd.DataFrame.from_dict(
                            enumerator_detailed_stats, orient="index"
                        )
                        enumerator_detailed_df = enumerator_detailed_df.reset_index()
                        enumerator_detailed_df.columns = [
                            "Enumerator ID",
                            "Total Surveys",
                            "Total Backchecks",
                            "Total Values Compared",
                            "Total Different",
                        ]

                        # Calculate percentages
                        enumerator_detailed_df["% Backchecked"] = (
                            enumerator_detailed_df["Total Backchecks"]
                            / enumerator_detailed_df["Total Surveys"]
                            * 100
                        ).round(2)

                        enumerator_detailed_df["% Different"] = (
                            enumerator_detailed_df["Total Different"]
                            / enumerator_detailed_df["Total Values Compared"]
                            * 100
                        ).round(2)

                        # Handle division by zero
                        enumerator_detailed_df["% Backchecked"] = (
                            enumerator_detailed_df["% Backchecked"].fillna(0)
                        )
                        enumerator_detailed_df["% Different"] = enumerator_detailed_df[
                            "% Different"
                        ].fillna(0)

                        # Convert percentages to strings with % symbol
                        enumerator_detailed_df["% Backchecked"] = (
                            enumerator_detailed_df["% Backchecked"].astype(str) + "%"
                        )
                        enumerator_detailed_df["% Different"] = (
                            enumerator_detailed_df["% Different"].astype(str) + "%"
                        )

                        # Create DataFrame from enumerator statistics
                        enumerator_detailed_df = pd.DataFrame.from_dict(
                            enumerator_detailed_stats, orient="index"
                        )
                        enumerator_detailed_df = enumerator_detailed_df.reset_index()
                        enumerator_detailed_df.columns = [
                            "Enumerator ID",
                            "Total Surveys",
                            "Total Backchecks",
                            "Total Values Compared",
                            "Total Different",
                        ]

                        # Calculate percentages
                        enumerator_detailed_df["% Backchecked"] = (
                            enumerator_detailed_df["Total Backchecks"]
                            / enumerator_detailed_df["Total Surveys"]
                            * 100
                        ).round(2)

                        enumerator_detailed_df["% Different"] = (
                            enumerator_detailed_df["Total Different"]
                            / enumerator_detailed_df["Total Values Compared"]
                            * 100
                        ).round(2)

                        # Handle division by zero
                        enumerator_detailed_df["% Backchecked"] = (
                            enumerator_detailed_df["% Backchecked"].fillna(0)
                        )
                        enumerator_detailed_df["% Different"] = enumerator_detailed_df[
                            "% Different"
                        ].fillna(0)

                        # Convert percentages to strings with % symbol
                        enumerator_detailed_df["% Backchecked"] = (
                            enumerator_detailed_df["% Backchecked"].astype(str) + "%"
                        )
                        enumerator_detailed_df["% Different"] = (
                            enumerator_detailed_df["% Different"].astype(str) + "%"
                        )

                        # Reorder columns as requested
                        column_order = [
                            "Enumerator ID",
                            "Total Surveys",
                            "Total Backchecks",
                            "% Backchecked",
                            "Total Values Compared",
                            "Total Different",
                            "% Different",
                        ]

                        enumerator_detailed_df = enumerator_detailed_df[column_order]

                        # Selection filter by enumid
                        selected_enumerators = st.multiselect(
                            "Filter enumerators:",
                            enumerator_detailed_df["Enumerator ID"].unique(),
                        )

                        if selected_enumerators:
                            filtered_enumerator_stats = enumerator_detailed_df[
                                enumerator_detailed_df["Enumerator ID"].isin(
                                    selected_enumerators
                                )
                            ]
                        else:
                            filtered_enumerator_stats = enumerator_detailed_df

                        # Display the filtered enumerator statistics table
                        st.dataframe(
                            filtered_enumerator_stats,
                            use_container_width=True,
                            column_config={
                                "Enumerator ID": st.column_config.Column(width="small"),
                                "Total Surveys": st.column_config.NumberColumn(
                                    format="%d", width="small"
                                ),
                                "Total Backchecks": st.column_config.NumberColumn(
                                    format="%d", width="small"
                                ),
                                "% Backchecked": st.column_config.Column(width="small"),
                                "Total Values Compared": st.column_config.NumberColumn(
                                    format="%d", width="small"
                                ),
                                "Total Different": st.column_config.NumberColumn(
                                    format="%d", width="small"
                                ),
                                "% Different": st.column_config.Column(width="small"),
                            },
                        )

                    # New tab for "Backchecker Statistics"
                    with tabs[2]:
                        # Initialize dictionary to store backchecker statistics
                        backchecker_stats = {}

                        # Given that enum_bcer is a list, access the first
                        # element
                        enum_bcer_column = (
                            enum_bcer[0] if isinstance(enum_bcer, list) else enum_bcer
                        )

                        # For each selected variable, calculate statistics per
                        # backchecker
                        for var in selected_vars:
                            svy_col = f"svy_{var}"
                            back_col = f"back_{var}"

                            # Create comparison data for this variable
                            comparison = pd.DataFrame(
                                {
                                    "backchecker_id": merged_df[enum_bcer_column],
                                    "survey_value": merged_df[svy_col].astype(str),
                                    "backcheck_value": merged_df[back_col].astype(str),
                                }
                            )

                            # Mark matches/mismatches
                            comparison["is_different"] = comparison.apply(
                                lambda x: str(x["survey_value"]).strip()
                                != str(x["backcheck_value"]).strip(),
                                axis=1,
                            )

                            # Group by backchecker and calculate statistics
                            for backchecker_id in comparison["backchecker_id"].unique():
                                if backchecker_id not in backchecker_stats:
                                    backchecker_stats[backchecker_id] = {
                                        "total_backchecks": len(
                                            comparison[
                                                comparison["backchecker_id"]
                                                == backchecker_id
                                            ]
                                        ),
                                        "total_compared": 0,
                                        "total_different": 0,
                                    }

                                backchecker_data = comparison[
                                    comparison["backchecker_id"] == backchecker_id
                                ]
                                backchecker_stats[backchecker_id]["total_compared"] += (
                                    len(backchecker_data)
                                )
                                backchecker_stats[backchecker_id][
                                    "total_different"
                                ] += backchecker_data["is_different"].sum()

                        # Create DataFrame from backchecker statistics
                        backchecker_df = pd.DataFrame.from_dict(
                            backchecker_stats, orient="index"
                        )
                        backchecker_df = backchecker_df.reset_index()
                        backchecker_df.columns = [
                            "Backchecker ID",
                            "Total Backchecks",
                            "Total Values Compared",
                            "Total Different",
                        ]

                        # Calculate percentage different
                        backchecker_df["% Different"] = (
                            backchecker_df["Total Different"]
                            / backchecker_df["Total Values Compared"]
                            * 100
                        ).round(2).astype(str) + "%"

                        st.subheader("Backchecker Statistics")
                        selected_backcheckers = st.multiselect(
                            "Filter backcheckers:",
                            backchecker_df["Backchecker ID"].unique(),
                        )

                        if selected_backcheckers:
                            filtered_backchecker_stats = backchecker_df[
                                backchecker_df["Backchecker ID"].isin(
                                    selected_backcheckers
                                )
                            ]
                        else:
                            filtered_backchecker_stats = backchecker_df

                        # Display the filtered backchecker statistics table
                        st.dataframe(
                            filtered_backchecker_stats,
                            use_container_width=True,
                            column_config={
                                "Backchecker ID": st.column_config.Column(
                                    width="medium"
                                ),
                                "Total Backchecks": st.column_config.NumberColumn(
                                    format="%d", width="medium"
                                ),
                                "Total Values Compared": st.column_config.NumberColumn(
                                    format="%d", width="medium"
                                ),
                                "Total Different": st.column_config.NumberColumn(
                                    format="%d", width="medium"
                                ),
                                "% Different": st.column_config.Column(width="medium"),
                            },
                        )

                    # Process the selected variables
                    for tab, var in zip(tabs[3:], selected_vars, strict=False):
                        with tab:
                            st.subheader(f"Mismatches for {var}")

                            svy_col = f"svy_{var}"
                            back_col = f"back_{var}"
                            is_numeric = var_types[var] == "Numeric"

                            # Create base comparison dataframe
                            comparison_df = pd.DataFrame(
                                {
                                    "Unique Identifier": merged_df[merge_variable],
                                    "Enumerator id": merged_df[enumid_var],
                                    "Backchecker id": merged_df[enum_bcer_column]
                                    if enum_bcer_column in merged_df.columns
                                    else pd.Series([None] * len(merged_df)),
                                    "Selected Variable": var,
                                    "Survey Value": merged_df[svy_col].astype(str),
                                    "Backcheck Value": merged_df[back_col].astype(str),
                                }
                            )

                            # Calculate difference for numeric variables
                            if is_numeric:
                                try:
                                    # Create separate numeric columns for calculation
                                    survey_numeric = pd.to_numeric(
                                        merged_df[svy_col], errors="coerce"
                                    )
                                    backcheck_numeric = pd.to_numeric(
                                        merged_df[back_col], errors="coerce"
                                    )

                                    # Add difference column
                                    comparison_df["Difference"] = (
                                        survey_numeric - backcheck_numeric
                                    )

                                    # Format difference to handle NaN values
                                    comparison_df["Difference"] = comparison_df[
                                        "Difference"
                                    ].apply(
                                        lambda x: f"{x:.2f}" if pd.notnull(x) else "N/A"
                                    )
                                except Exception as e:
                                    st.warning(
                                        f"Could not calculate differences for {var}. Error: {e!s}"
                                    )

                            # Add comparison column
                            comparison_df["Comparison"] = comparison_df.apply(
                                lambda x: "Match"
                                if str(x["Survey Value"]).strip()
                                == str(x["Backcheck Value"]).strip()
                                else "Mismatch",
                                axis=1,
                            )

                            # Filter for mismatches only
                            mismatches_df = comparison_df[
                                comparison_df["Comparison"] == "Mismatch"
                            ]

                            # Allow the user to filter the mismatches by enumerator ID
                            selected_enumerators = st.multiselect(
                                f"Filter mismatches for {var} by enumerator:",
                                mismatches_df["Enumerator id"].unique(),
                            )
                            if selected_enumerators:
                                filtered_mismatches = mismatches_df[
                                    mismatches_df["Enumerator id"].isin(
                                        selected_enumerators
                                    )
                                ]
                            else:
                                filtered_mismatches = mismatches_df

                            # Display the filtered mismatches
                            st.dataframe(filtered_mismatches, use_container_width=True)

            else:
                st.info(
                    "There was no backcheck data frame found. Please upload the backcheck data first."
                )

        ##### Descriptive Statistics #####
        with tab9:

            def visualize_data_distribution(df6):
                """Visualize the distribution of categorical and numeric
                variables in the dataframe.

                Args:
                    df6 (pd.DataFrame): The dataframe containing the data to
                    visualize.

                """
                # Separate categorical and numeric columns
                cat_vars = df6.select_dtypes(include=["object", "category"]).columns
                num_vars = df6.select_dtypes(include=["int64", "float64"]).columns

                # Create tabs for categorical and numeric plots
                tab1, tab2 = st.tabs(["Categorical Variables", "Numeric Variables"])

                with tab1:
                    st.header("Categorical Variables Distribution")

                    # Select-multiple for categorical variables
                    selected_cat_vars = st.multiselect(
                        "Select Categorical Variables to Visualize",
                        options=list(cat_vars),
                        default=[],
                    )

                    for var in selected_cat_vars:
                        # Check if the column has any values
                        value_counts = df6[var].value_counts()
                        if not value_counts.empty:
                            st.subheader(var)
                            # Use Plotly for interactive bar chart
                            fig = px.bar(
                                x=value_counts.index,
                                y=value_counts.values,
                                labels={"x": var, "y": "Count"},
                                title=f"Distribution of {var}",
                            )
                            fig.update_traces(marker_color="forestgreen")
                            st.plotly_chart(fig)
                        else:
                            st.write(f"No data to plot for {var}")

                with tab2:
                    st.header("Numeric Variables Distribution")

                    # Plot all numeric variables
                    for var in num_vars:
                        st.subheader(var)
                        fig, ax = plt.subplots(figsize=(6, 3))
                        sns.histplot(df6[var], kde=True, ax=ax, color="forestgreen")
                        ax.set_xlabel(var)
                        ax.set_ylabel("Density")
                        try:
                            ax.set_xlim(0, df6[var].max() * 1.2)
                        except ValueError:
                            ax.set_xlim(0, 100)
                        plt.tight_layout()
                        st.pyplot(fig)

            # Main Streamlit app
            st.title("Data Distribution Visualization")
            visualize_data_distribution(df6)

    else:
        st.info("Please enter a file path or URL to begin")
