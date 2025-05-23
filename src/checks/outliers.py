import os
from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_extras.stylable_container import stylable_container

from src.utils import (
    load_check_settings,
    save_check_settings,
)


# @st.cache_data
def load_default_settings(settings_file: str, page_num: int) -> tuple:
    """
    Load the default settings for the summary report.

    Parameters
    ----------
    setting_file : str
            The settings file to load.

    page_num : int
            The page number of the report.

    Returns
    -------
    tuple
            A tuple containing the default settings for the summary report.

    """
    # load default settings in the following order:
    # - if settings file exists, load settings from file
    # - if settings file does not exist, load default settings from config
    if settings_file and os.path.exists(settings_file):
        default_settings = load_check_settings(settings_file, "outliers") or {}
    else:
        default_settings = {}

    default_survey_id = default_settings.get(
        "survey_id", st.session_state["config_pages"]["Survey ID"][page_num - 1]
    )
    default_enumerator = default_settings.get(
        "enumerator", st.session_state["config_pages"]["Enumerator"][page_num - 1]
    )
    default_survey_key = default_settings.get(
        "survey_key", st.session_state["config_pages"]["Survey KEY"][page_num - 1]
    )
    default_outlier_cols = default_settings.get("outlier_cols", [])
    default_outlier_method = default_settings.get("outlier_method", 0)
    default_sd_value = default_settings.get("sd_value", 3)
    default_iqr_value = default_settings.get("iqr_value", 1.5)

    return (
        default_survey_id,
        default_enumerator,
        default_survey_key,
        default_outlier_cols,
        default_outlier_method,
        default_sd_value,
        default_iqr_value,
    )


# Function for joint outlier detection: find variable patterns
# @st.cache_data
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


# Function for joint outlier detection: show pattern selection
# @st.cache_data
def show_pattern_selection(df, survey_id, pattern_groups, selected_patterns):
    """Generate a pattern from selected variable names and
    return the selected columns and melted DataFrame.
    """
    if pattern_groups:
        # Create pattern options for display
        pattern_options = [
            f"{pattern} ({len(cols)} variables)"
            for pattern, cols in pattern_groups.items()
        ]

        # Create mapping from display name to base pattern
        pattern_to_base = {  # noqa: F841
            display: pattern
            for pattern, display in zip(
                pattern_groups.keys(), pattern_options, strict=False
            )
        }

        # Handle selected patterns
        if selected_patterns:
            # Get all columns from selected patterns
            selected_cols = []
            base_patterns = []
            for pattern in selected_patterns:
                if pattern in pattern_groups:
                    selected_cols.extend(pattern_groups[pattern])
                    base_patterns.append(pattern)

            if selected_cols:
                base_pattern = " & ".join(base_patterns)  # Combine pattern names
                df_subset = df[[survey_id] + selected_cols]
                df_melted = pd.melt(
                    df_subset,
                    id_vars=[survey_id],
                    value_vars=selected_cols,
                    var_name="name_variable",
                    value_name="new_var",
                )
                return base_pattern, selected_cols, df_melted

    return None, None, None


# outliers check settings
def outliers_settings(data: pd.DataFrame, settings_file: str, page_num: int) -> tuple:
    """
    Function to create a report on survey duplicates
    Args:
        data: DataFrame
    Returns:

    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for outliers report")

        st.write("---")
        st.markdown(
            "###### Select columns and the outlier detection method to include in the report"
        )

        numeric_cols = data.select_dtypes(include="number").columns.tolist()
        survey_cols = data.columns

        # load default settings
        (
            default_survey_id,
            default_enumerator,
            default_survey_key,
            default_outlier_cols,
            default_outlier_method,
            default_sd_value,
            default_iqr_value,
        ) = load_default_settings(settings_file, page_num)

        var_col, method_col, survey_col = st.columns(spec=3, border=True)

        with var_col:
            outlier_cols = st.multiselect(
                "Columns to check for outliers",
                options=numeric_cols,
                default=default_outlier_cols,
                help="Columns to check for outliers",
                key="outlier_cols",
            )
        with method_col:
            outlier_method_options = [
                "Interquartile Range (IQR)",
                "Standard Deviation (SD)",
            ]
            outlier_method = st.radio(
                label="Outlier Detection Method",
                options=outlier_method_options,
                index=default_outlier_method,
            )

            if outlier_method == "Standard Deviation (SD)":
                sd_value = st.number_input(
                    "Number of Standard Deviations:",
                    value=default_sd_value,
                    key="sd_value_outliers",
                    help="The number of standard deviations from the mean to use for outlier detection.",
                )
            else:
                iqr_value = st.number_input(
                    "IQR Value:",
                    value=default_iqr_value,
                    help="The IQR value is used to determine the range of values that are considered outliers.",
                    key="iqr_value_outliers",
                )
        with survey_col:
            default_survey_id_index = (
                survey_cols.get_loc(default_survey_id) if default_survey_id else None
            )
            survey_id = st.selectbox(
                "Survey ID",
                options=survey_cols,
                help="Select the column that contains the survey ID",
                key="survey_id_outliers",
                index=default_survey_id_index,
            )

            default_enumerator_index = (
                survey_cols.get_loc(default_enumerator) if default_enumerator else None
            )
            enumerator = st.selectbox(
                "Enumerator ID",
                options=survey_cols,
                key="enumerator_outliers",
                help="Select the column that contains the enumerator ID",
                index=default_enumerator_index,
            )

            default_survey_key_index = (
                survey_cols.get_loc(default_survey_key) if default_survey_key else None
            )
            survey_key = st.selectbox(
                "Survey Key",
                options=survey_cols,
                key="survey_key_outliers",
                help="Select the column that contains the survey key",
                index=default_survey_key_index,
            )

        # joint outlier detection
        st.write("---")
        st.markdown("###### Joint Outlier Detection")
        st.write(
            """If you'd like to detect outliers based on a joint
            distribution of several variables (for example,
            same variable corresponding to different household
            members), please select the set of variables""",
        )
        selected_pattern = st.multiselect(
            "Please select the set of variables",
            options=numeric_cols,
            help="""Choose a group of related variables to analyze.
                    Only numeric variables are shown.
                    """,
        )

        if selected_pattern:
            # find variable patterns
            pattern_groups = find_variable_patterns(numeric_cols)

            # show pattern selection
            base_pattern, selected_cols, df_melted = show_pattern_selection(
                data, survey_id, pattern_groups, selected_pattern
            )
            if selected_cols:
                with st.container():
                    st.write(
                        f"Below are selected variables for the selected pattern: '{base_pattern}'"
                    )
                    st.write(", ".join(selected_cols))

        # save settings
        st.write("---")
        st.write("Save settings")

        outliers_check_settings = {
            "outlier_cols": outlier_cols if outlier_cols else [],
            "outlier_method": outlier_method_options.index(outlier_method),
            "sd_value": sd_value
            if outlier_method == "Standard Deviation (SD)"
            else None,
            "iqr_value": iqr_value
            if outlier_method == "Interquartile Range (IQR)"
            else None,
            "survey_id": survey_id,
            "enumerator": enumerator,
            "survey_key": survey_key,
        }

        save_outliers_settings = st.button(
            label="Save settings", key="save_outliers_settings"
        )

        if save_outliers_settings:
            if outlier_cols:
                save_check_settings(settings_file, "outliers", outliers_check_settings)
            else:
                st.warning("Please select at least one column to check for outliers.")

        return (
            outlier_cols,
            survey_id,
            enumerator,
            survey_key,
            outlier_method,
            sd_value if outlier_method == "Standard Deviation (SD)" else None,
            iqr_value if outlier_method == "Interquartile Range (IQR)" else None,
        )


# Function to flag outliers
@st.cache_data
def flag_outliers(col, outlier_method, sd_value, iqr_value):
    """Flag outliers in a column based on specified method and thresholds."""
    if pd.isna(col):  # Handle NaN values
        return 0

    # Calculate bounds based on the entire column
    if outlier_method == "Interquartile Range (IQR)":
        Q1 = col.quantile(0.25)
        Q3 = col.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - iqr_value * IQR
        upper_bound = Q3 + iqr_value * IQR
    else:  # Standard Deviation method
        mean = col.mean()
        std = col.std()
        lower_bound = mean - sd_value * std
        upper_bound = mean + sd_value * std

    # Return 1 for outliers, 0 for non-outliers
    return 1 if (col < lower_bound) or (col > upper_bound) else 0


# Function to check for outliers
@st.cache_data
def check_outliers(
    data,
    outlier_cols,
    survey_id,
    survey_key,
    enumerator,
    outlier_method,
    sd_value,
    iqr_value,
):
    """Check for outliers in selected columns."""
    # Create base dataframe with ID columns
    ids = data[[survey_id, survey_key, enumerator]].copy()
    # Initialize results storage
    outliers_list = []

    # Process each column
    for col in outlier_cols:
        series = data[col].copy()

        # Calculate outlier flags
        outlier_flags = pd.Series(False, index=series.index)
        non_null_mask = ~series.isna()

        if outlier_method == "Interquartile Range (IQR)":
            Q1 = series[non_null_mask].quantile(0.25)
            Q3 = series[non_null_mask].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - iqr_value * IQR
            upper_bound = Q3 + iqr_value * IQR
        else:  # Standard Deviation method
            mean = series[non_null_mask].mean()
            std = series[non_null_mask].std()
            lower_bound = mean - sd_value * std
            upper_bound = mean + sd_value * std

        # Flag outliers
        outlier_flags[non_null_mask] = (series[non_null_mask] < lower_bound) | (
            series[non_null_mask] > upper_bound
        )

        # Create outlier records
        outlier_records = ids[outlier_flags].copy()
        outlier_records["variable"] = col
        outlier_records["value"] = series[outlier_flags]
        outlier_records["mean"] = series[non_null_mask].mean()
        outlier_records["std"] = series[non_null_mask].std()
        outlier_records["lower_bound"] = lower_bound
        outlier_records["upper_bound"] = upper_bound

        outliers_list.append(outlier_records)

    # Combine all outliers
    if outliers_list:
        table_data = pd.concat(outliers_list, ignore_index=True)
        return table_data
    else:
        return pd.DataFrame()


# define function to create outliers report
def outliers_report(data: pd.DataFrame, setting_file: str, page_num: int) -> None:  # noqa: D417, RUF100"
    """
    Function to create a report on survey duplicates
    Args:
        data: DataFrame
    Returns:

    """
    # outliers settings
    (
        outlier_cols,
        survey_id,
        enumerator,
        survey_key,
        outlier_method,
        sd_value,
        iqr_value,
    ) = outliers_settings(data, setting_file, page_num)

    # Check that required options have been selected. If not, display a info message

    if not all([outlier_cols, outlier_method, survey_id, enumerator, survey_key]):
        st.info("Please select all required options to generate the outliers report")
        return

    st.markdown("## Outliers")

    # Check for outliers
    table_data = check_outliers(
        data,
        outlier_cols,
        survey_id,
        survey_key,
        enumerator,
        outlier_method,
        sd_value,
        iqr_value,
    )

    with stylable_container(
        key="outlier_metrics",
        css_styles="""
            {
                background-color: #F9F9F9;
                border: 1px solid rgba(49, 51, 63, 0.2);
                border-radius: 0.5rem;
                padding: calc(1em - 1px)
            }
            """,
    ):
        col1, col2, col3, col4 = st.columns(4)

        cols_checked_outliers = len(outlier_cols)
        at_least_one_outlier = table_data["variable"].nunique()
        total_outliers = len(table_data)

        col1.metric(
            label="VARIABLES CHECKED",
            value=f"{cols_checked_outliers}",
            help="Columns checked for outlier values",
        )

        col2.metric(
            label="OUTLIER VARIABLES",
            value=f"{at_least_one_outlier}",
            help="Variables with at least one outlier",
        )

        col3.metric(
            label="TOTAL NUMBER OR OUTLIERS",
            value=f"{total_outliers}",
            help="Total number of identified outliers",
        )

        col4.metric(
            label="Placeholder",
            value=f"{total_outliers}",
            help="x",
        )

    # Display using st.dataframe with proper formatting
    st.dataframe(
        table_data,
        hide_index=True,
        use_container_width=True,
        column_config={
            "variable_value": st.column_config.NumberColumn(
                "Value", format="%.2f", width="small"
            ),
            "mean": st.column_config.NumberColumn("Mean", format="%.2f", width="small"),
            "lower_bound": st.column_config.NumberColumn(
                "Lower Bound", format="%.2f", width="small"
            ),
            "upper_bound": st.column_config.NumberColumn(
                "Upper Bound", format="%.2f", width="small"
            ),
        },
    )

    with stylable_container(
        key="plots",
        css_styles="""
        {
            background-color: #F9F9F9;
            border: 1px solid rgba(49, 51, 63, 0.2);
            border-radius: 0.5rem;
            padding: calc(1em - 1px)
        }
        """,
    ):
        for var in outlier_cols:
            st.subheader(var)
            if var in table_data["variable"].values:
                col1, col2 = st.columns([4, 1], vertical_alignment="center")
                with col1:
                    # Plot outliers
                    fig = go.Figure(
                        data=go.Violin(
                            y=data[var],
                            box_visible=True,
                            line_color="black",
                            meanline_visible=True,
                            fillcolor="darkgreen",
                            opacity=0.6,
                            x0=var,
                        )
                    )
                    st.plotly_chart(fig, theme="streamlit", use_container_width=True)
                with col2:
                    # Calculate percentage of outliers within variable non-missing vals
                    outlier_count = len(table_data[table_data["variable"] == var])
                    total_nonmissing = data[var].count()
                    outlier_percentage = (outlier_count / total_nonmissing) * 100
                    formatted_outlier_percentage = f"{outlier_percentage:.2f}%"
                    st.metric(
                        value=formatted_outlier_percentage, label="Share of outliers"
                    )
            else:
                st.write(
                    "No outliers found on this variable according to the selected method and threshold."
                )

        ## NEXT PR:
        # if selected_cols and df_melted is not None:
        #     series = df_melted["new_var"].dropna()
        #     total_count = len(series)

        #     if outlier_method == "Interquartile Range (IQR)":
        #         Q1 = series.quantile(0.25)
        #         Q3 = series.quantile(0.75)
        #         IQR = Q3 - Q1
        #         lower_bound = Q1 - 1.5 * IQR
        #         upper_bound = Q3 + 1.5 * IQR
        #     elif outlier_method == "Standard Deviation (+/-)":
        #         mean = series.mean()
        #         std_dev = series.std()
        #         lower_bound = mean - sd_value * std_dev
        #         upper_bound = mean + sd_value * std_dev

        #     outliers = series[(series < lower_bound) | (series > upper_bound)]
        #     outliers_df = df_melted[df_melted["new_var"].isin(outliers)]

        #     table_data = outliers_df[[survey_id, "name_variable"]].copy()
        #     table_data["new_var"] = outliers_df["new_var"].round(2)
        #     table_data["mean"] = round(series.mean(), 2)
        #     table_data["lower_bound"] = round(lower_bound, 2)
        #     table_data["upper_bound"] = round(upper_bound, 2)

        #     st.dataframe(
        #         table_data,
        #         hide_index=True,
        #         use_container_width=True,
        #         column_config={
        #             "id": st.column_config.Column("ID", width="small"),
        #             "name_variable": st.column_config.Column("Variable Name"),
        #             "new_var": st.column_config.NumberColumn(
        #                 "Value", format="%.2f", width="small"
        #             ),
        #             "mean": st.column_config.NumberColumn(
        #                 "Mean", format="%.2f", width="small"
        #             ),
        #             "lower_bound": st.column_config.NumberColumn(
        #                 "Lower Bound", format="%.2f", width="small"
        #             ),
        #             "upper_bound": st.column_config.NumberColumn(
        #                 "Upper Bound", format="%.2f", width="small"
        #             ),
        #         },
        #     )

        # # Check if outliers_df is not empty
        # if outliers_df.empty:
        #     st.write(
        #         "No outliers found according to the selected method and threshold"
        #     )
        # else:
        #     # Calculate percentage of outliers
        #     outlier_count = len(outliers)
        #     outlier_percentage = (outlier_count / total_count) * 100
        #     formatted_outlier_percentage = f"{outlier_percentage:.2f}%"

        #     st.metric(value=formatted_outlier_percentage, label="Share of outliers")

        # # Function to find the common prefix
        # def common_prefix(strs):
        #     """Find the longest common prefix string amongst an array
        #     of strings.

        #     Args:
        #         strs (list): List of strings.

        #     Returns
        #     -------
        #         str: The longest common prefix.

        #     """
        #     if not strs:
        #         return ""
        #     prefix = strs[0]
        #     for s in strs[1:]:
        #         while not s.startswith(prefix):
        #             prefix = prefix[:-1]
        #             if not prefix:
        #                 return ""
        #     return prefix

        # # Get common prefix
        # x_axis_label = common_prefix(selected_cols)

        # fig = go.Figure(
        #     data=go.Violin(
        #         y=df_melted["new_var"],
        #         box_visible=True,
        #         line_color="black",
        #         meanline_visible=True,
        #         fillcolor="forestgreen",
        #         opacity=0.6,
        #         x0=x_axis_label,
        #     )
        # )

        # st.plotly_chart(fig, theme="streamlit", use_container_width=True)
