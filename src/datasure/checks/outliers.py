import os
from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
import seaborn as sns
import streamlit as st

from datasure.utils import (
    get_check_config_settings,
    get_df_info,
    load_check_settings,
    save_check_settings,
    trigger_save,
)


def load_default_settings(project_id: str, settings_file: str, page_num: int) -> tuple:
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
    # Get config page defaults
    _, _, config_survey_key, config_survey_id, _, config_enumerator, _, _ = (
        get_check_config_settings(
            project_id=project_id,
            page_row_index=page_num - 1,
        )
    )
    # load default settings in the following order:
    # - if settings file exists, load settings from file
    # - if settings file does not exist, load default settings from config
    if settings_file and os.path.exists(settings_file):
        default_settings = load_check_settings(settings_file, "outliers") or {}
    else:
        default_settings = {}

    default_survey_id = default_settings.get("survey_id", config_survey_id)
    default_enumerator = default_settings.get("enumerator", config_enumerator)
    default_survey_key = default_settings.get("survey_key", config_survey_key)
    default_outlier_cols = default_settings.get("outlier_cols", [])
    default_outlier_method = default_settings.get("outlier_method", 0)
    default_sd_value = default_settings.get("sd_value", 3.0)
    default_iqr_value = default_settings.get("iqr_value", 1.5)
    default_selected_pattern = default_settings.get("selected_pattern", [])

    return (
        default_survey_id,
        default_enumerator,
        default_survey_key,
        default_outlier_cols,
        default_outlier_method,
        default_sd_value,
        default_iqr_value,
        default_selected_pattern,
    )


# Function for joint outlier detection: find variable patterns
@st.cache_data
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
@st.cache_data
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
                reshaped_joint_outliers_df = pd.melt(
                    df_subset,
                    id_vars=[survey_id],
                    value_vars=selected_cols,
                    var_name="name_variable",
                    value_name="new_var",
                )
                return base_pattern, selected_cols, reshaped_joint_outliers_df

    return None, None, None


# outliers check settings
def outliers_report_settings(
    project_id: str, data: pd.DataFrame, settings_file: str, page_num: int
) -> tuple:
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

        all_cols, string_columns, numeric_columns, datetime_columns, _ = get_df_info(
            data, cols_only=True
        )

        id_enum_col_options = string_columns + datetime_columns

        # load default settings
        (
            default_survey_id,
            default_enumerator,
            default_survey_key,
            default_outlier_cols,
            default_outlier_method,
            default_sd_value,
            default_iqr_value,
            default_selected_pattern,
        ) = load_default_settings(project_id, settings_file, page_num)

        var_col, method_col, survey_col = st.columns(spec=3, border=True)

        with var_col:
            outlier_cols = st.multiselect(
                "Columns to check for outliers",
                options=numeric_columns,
                default=default_outlier_cols,
                help="Columns to check for outliers",
                key="outlier_cols",
                on_change=trigger_save,
                kwargs={"state_name": "outlier_cols_save"},
            )
            if (
                "outlier_cols_save" in st.session_state
                and st.session_state.outlier_cols_save
            ):
                save_check_settings(
                    settings_file=settings_file,
                    check_name="outliers",
                    check_settings={"outlier_cols": outlier_cols},
                )
                st.session_state["outlier_cols_save"] = False
        with method_col:
            outlier_method_options = [
                "Interquartile Range (IQR)",
                "Standard Deviation (SD)",
            ]
            outlier_method = st.radio(
                label="Outlier Detection Method",
                options=outlier_method_options,
                index=default_outlier_method,
                on_change=trigger_save,
                kwargs={"state_name": "outlier_method_save"},
            )
            if (
                "outlier_method_save" in st.session_state
                and st.session_state.outlier_method_save
            ):
                save_check_settings(
                    settings_file=settings_file,
                    check_name="outliers",
                    check_settings={"outlier_method", outlier_method},
                )
                st.session_state.outlier_method_save = False

            if outlier_method == "Standard Deviation (SD)":
                sd_value = st.number_input(
                    "Number of Standard Deviations:",
                    value=3.0 if default_sd_value is None else default_sd_value,
                    key="sd_value_outliers",
                    help="The number of standard deviations from the mean to use for outlier detection.",
                    on_change=trigger_save,
                    kwargs={"state_name": "sd_value_save"},
                )
                if (
                    "sd_value_save" in st.session_state
                    and st.session_state.sd_value_save
                ):
                    save_check_settings(
                        settings_file=settings_file,
                        check_name="outliers",
                        check_settings={"sd_value": sd_value},
                    )
                    st.session_state.sd_value_save = False
            else:
                iqr_value = st.number_input(
                    "IQR Value:",
                    value=1.5 if default_iqr_value is None else default_iqr_value,
                    help="The IQR value is used to determine the range of values that are considered outliers.",
                    key="iqr_value_outliers",
                    on_change=trigger_save,
                    kwargs={"state_name": "iqr_value_save"},
                )
                if (
                    "iqr_value_save" in st.session_state
                    and st.session_state.iqr_value_save
                ):
                    save_check_settings(
                        settings_file=settings_file,
                        check_name="outliers",
                        check_settings={"iqr_value": iqr_value},
                    )
                    st.session_state.iqr_value_save = False
        with survey_col:
            default_survey_id_index = (
                id_enum_col_options.index(default_survey_id)
                if default_survey_id and default_survey_id in id_enum_col_options
                else None
            )
            survey_id = st.selectbox(
                "Survey ID",
                options=id_enum_col_options,
                help="Select the column that contains the survey ID",
                key="survey_id_outliers",
                index=default_survey_id_index,
                on_change=trigger_save,
                kwargs={"state_name": "survey_id_save"},
            )
            if "survey_id_save" in st.session_state and st.session_state.survey_id_save:
                save_check_settings(
                    settings_file=settings_file,
                    check_name="outliers",
                    check_settings={"survey_id": survey_id},
                )
                st.session_state.survey_id_save = False

            default_enumerator_index = (
                id_enum_col_options.index(default_enumerator)
                if default_enumerator and default_enumerator in id_enum_col_options
                else None
            )
            enumerator = st.selectbox(
                "Enumerator ID",
                options=id_enum_col_options,
                key="enumerator_outliers",
                help="Select the column that contains the enumerator ID",
                index=default_enumerator_index,
                on_change=trigger_save,
                kwargs={"state_name": "enumerator_save"},
            )
            if (
                "enumerator_save" in st.session_state
                and st.session_state.enumerator_save
            ):
                save_check_settings(
                    settings_file=settings_file,
                    check_name="outliers",
                    check_settings={"enumerator": enumerator},
                )
                st.session_state.enumerator_save = False

            default_survey_key_index = (
                id_enum_col_options.index(default_survey_key)
                if default_survey_key and default_survey_key in id_enum_col_options
                else None
            )
            survey_key = st.selectbox(
                "Survey Key",
                options=id_enum_col_options,
                key="survey_key_outliers",
                help="Select the column that contains the survey key",
                index=default_survey_key_index,
                on_change=trigger_save,
                kwargs={"state_name": "survey_key_save"},
            )
            if (
                "survey_key_save" in st.session_state
                and st.session_state.survey_key_save
            ):
                save_check_settings(
                    settings_file=settings_file,
                    check_name="outliers",
                    check_settings={"survey_key": survey_key},
                )
                st.session_state.survey_key_save = False

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
            options=numeric_columns,
            default=default_selected_pattern,
            key="selected_pattern",
            help="""Choose a group of related variables to analyze.
                    Only numeric variables are shown.
                    """,
            on_change=trigger_save,
            kwargs={"state_name": "selected_pattern_save"},
        )
        if (
            "selected_pattern_save" in st.session_state
            and st.session_state.selected_pattern_save
        ):
            save_check_settings(
                settings_file=settings_file,
                check_name="outliers",
                check_settings={"selected_pattern": selected_pattern},
            )
            st.session_state.selected_pattern_save = False

        if selected_pattern:
            # find variable patterns
            pattern_groups = find_variable_patterns(numeric_columns)

            # show pattern selection
            base_pattern, selected_cols, reshaped_joint_outliers_df = (
                show_pattern_selection(
                    data, survey_id, pattern_groups, selected_pattern
                )
            )
            if selected_cols:
                with st.container():
                    st.write(
                        f"Below are selected variables for the selected pattern: '{base_pattern}'"
                    )
                    st.write(", ".join(selected_cols))

        return (
            outlier_cols,
            survey_id,
            enumerator,
            survey_key,
            outlier_method,
            sd_value if outlier_method == "Standard Deviation (SD)" else None,
            iqr_value if outlier_method == "Interquartile Range (IQR)" else None,
            selected_cols if selected_pattern else [],
            reshaped_joint_outliers_df if selected_pattern else None,
        )


# Function to detect outliers
@st.cache_data
def detect_outliers(
    df: pd.DataFrame,
    survey_key: str,
    survey_id: str,
    enumerator: str,
    cols: list,
    method: str,
    iqr_value: float,
    sd_value: float,
) -> pd.DataFrame:
    """Detect outliers in specified columns using either IQR or Standard Deviation
    method.

    Args:
        df (pd.DataFrame): Input dataframe containing survey data
        survey_key (str): Column name for survey key
        survey_id (str): Column name for survey ID
        enumerator (str): Column name for enumerator ID
        cols (list): List of columns to check for outliers
        method (str): Outlier detection method ("Interquartile Range (IQR)" or
        "Standard Deviation (SD)")
        iqr_value (float): Multiplier for IQR calculation
        sd_value (float): Number of standard deviations from mean

    Returns
    -------
        pd.DataFrame: DataFrame containing detected outliers with their details
    """
    # get list of optional admin columns to include in the outliers report
    existing_vars = []
    if survey_id:
        existing_vars.append(survey_id)
    if enumerator:
        existing_vars.append(enumerator)
    results = []
    series_df = df[[survey_key] + existing_vars + cols].dropna(subset=cols)
    for col in cols:
        series = series_df[col].astype("float64", errors="raise")
        # Drop NaN and missing values
        series = series.dropna()
        dk_refused_to_answer_vals = [-999, 0.999, -888, 0.888, -777, 0.777]
        series = series[~series.isin(dk_refused_to_answer_vals)]
        mean, std = series.mean(), series.std()

        if method == "Interquartile Range (IQR)":
            Q1, Q3 = series.quantile([0.25, 0.75])
            IQR = Q3 - Q1
            lower, upper = Q1 - iqr_value * IQR, Q3 + iqr_value * IQR
        else:  # Standard Deviation method
            lower, upper = mean - sd_value * std, mean + sd_value * std

        mask = (series < lower) | (series > upper)
        if mask.any():
            outliers = pd.DataFrame(
                {
                    survey_key: series_df.loc[mask.index[mask], survey_key],
                    "variable": col,
                    "value": series[mask],
                    "mean": mean,
                    "std": std,
                    "lower_bound": lower,
                    "upper_bound": upper,
                }
            )
            # optionally include enumerator and survey_id columns
            if survey_id:
                outliers[survey_id] = series_df.loc[mask.index[mask], survey_id]
            if enumerator:
                outliers[enumerator] = series_df.loc[mask.index[mask], enumerator]
            results.append(outliers)
    results_df = (
        pd.concat(results).reset_index(drop=True) if results else pd.DataFrame()
    )

    if existing_vars and not results_df.empty:
        # Reorder columns to have survey_key first, then enumerator/survey_id if present
        cols_order = (
            [survey_key]
            + existing_vars
            + [
                "variable",
                "value",
                "mean",
                "std",
                "lower_bound",
                "upper_bound",
            ]
        )
        results_df = results_df[cols_order]

    return results_df


# function to create outlier distribution
@st.cache_data
def create_violin_plot(data: pd.Series, title: str) -> go.Figure:
    """Create a violin plot using plotly.

    Args:
        data (pd.Series): Data series to plot
        title (str): Title for the plot

    Returns
    -------
        go.Figure: Plotly figure object containing the violin plot
    """
    return go.Figure(
        data=go.Violin(
            y=data,
            box_visible=True,
            line_color="black",
            meanline_visible=True,
            fillcolor="darkgreen",
            opacity=0.6,
            x0=title,
        )
    )


# plot outlier distribution
@st.cache_data
def plot_outlier_distributions(
    data, outliers_summary: pd.DataFrame, cols: list
) -> None:
    """Plot distribution of outliers for selected columns.

    Args:
        data: DataFrame containing the survey data
        outliers_summary: DataFrame containing the outlier summary
        cols: List of columns to plot distributions for

    Returns
    -------
        None
    """
    if outliers_summary.empty or data.empty or cols is None:
        return
    no_outlier_vars = []
    for var in cols:
        if var in outliers_summary["variable"].values:
            col1, col2 = st.columns([4, 1], vertical_alignment="center")
            with col1:
                fig = create_violin_plot(data[var], var)
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                outlier_pct = (
                    len(outliers_summary[outliers_summary["variable"] == var])
                    / data[var].count()
                    * 100
                )
                st.metric(value=f"{outlier_pct:.2f}%", label="Share of outliers")
        else:
            no_outlier_vars.append(var)

    if no_outlier_vars:
        st.write(
            "No outliers detected for the following variables according to the selected method and threshold"
        )
        # Split the list into chunks of 3
        n = 3
        no_outliers_vars_list = [
            no_outlier_vars[i : i + n] for i in range(0, len(no_outlier_vars), n)
        ]
        no_outliers_df = pd.DataFrame(no_outliers_vars_list).fillna("")
        st.dataframe(
            no_outliers_df,
            hide_index=True,
            use_container_width=True,
        )


# Function to display outlier metrics
@st.cache_data
def display_outlier_metrics(
    outliers_summary: pd.DataFrame, outlier_cols: list | None, enumerator: str | None
) -> None:
    """Display metrics related to outliers in a summary format.
    Args:
    outliers_summary (pd.DataFrame): DataFrame containing outlier summary.
    outlier_cols (list): List of columns checked for outliers.
    enumerator (str): Column name for enumerator ID.
    """
    st.markdown("## Outliers Overview")
    if not outlier_cols:
        st.info(
            "Outlier columns are required to display metrics. Go to the :material/settings: settings section above to select columns."
        )
        return
    col1, col2, col3, col4 = st.columns(spec=4, border=True)

    cols_checked_outliers = len(outlier_cols)
    total_outliers = len(outliers_summary)
    at_least_one_outlier = (
        outliers_summary["variable"].nunique() if not outliers_summary.empty else 0
    )
    total_enumerators = (
        outliers_summary[enumerator].nunique()
        if enumerator and not outliers_summary.empty
        else 0
    )

    col1.metric(
        label="Variables checked",
        value=f"{cols_checked_outliers}",
        help="Columns checked for outlier values",
    )

    col2.metric(
        label="Outlier variables",
        value=f"{at_least_one_outlier}",
        help="Variables with at least one outlier",
    )

    col3.metric(
        label="Number of outliers",
        value=f"{total_outliers}",
        help="Total number of identified outliers",
    )

    if enumerator:
        col4.metric(
            label="Number of enumerators",
            value=f"{total_enumerators}",
            help="Number of enumerators with outliers flagged",
        )
    else:
        with col4:
            st.write("Number of enumerators")
            st.info(
                "Enumerator column is not selected. Go to the :material/settings: settings section above to select the enumerator column."
            )

    # Display the outliers summary table
    if not outliers_summary.empty:
        cmap = sns.light_palette("pink", as_cmap=True)

        num_cols = ["value", "mean", "std", "lower_bound", "upper_bound"]
        outliers_summary = outliers_summary.style.format(
            subset=num_cols, formatter="{:,.2f}"
        ).background_gradient(subset=num_cols, cmap=cmap)
        st.dataframe(outliers_summary, use_container_width=True, hide_index=True)

    else:
        st.success("No outliers detected in the selected variables.")


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


# Function to calculate joint outlier distribution
@st.cache_data
def compute_joint_outlier_distribution(
    data, selected_cols, survey_id, outlier_method, iqr_value, sd_value
) -> pd.DataFrame:
    """
    Calculate the joint outlier distribution for a set of selected columns using the
    specified outlier detection method.

    Args:
        data (pd.DataFrame): Melted DataFrame containing the variables to analyze.
        selected_cols (list): List of selected variable columns.
        survey_id (str): Column name for survey ID.
        outlier_method (str): Outlier detection method ("Interquartile Range (IQR)" or
        "Standard Deviation (SD)").
        iqr_value (float): IQR multiplier for IQR method.
        sd_value (float): Number of standard deviations for SD method.

    Returns
    -------
        pd.DataFrame: DataFrame containing outlier joint outlier distribution.
    """
    series = data["new_var"].dropna()

    if outlier_method == "Interquartile Range (IQR)":
        Q1 = series.quantile(0.25)
        Q3 = series.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - iqr_value * IQR
        upper_bound = Q3 + iqr_value * IQR
    else:
        mean = series.mean()
        std_dev = series.std()
        lower_bound = mean - sd_value * std_dev
        upper_bound = mean + sd_value * std_dev

    outliers = series[(series < lower_bound) | (series > upper_bound)]
    outliers_df = data[data["new_var"].isin(outliers)]

    table_data = outliers_df[[survey_id, "name_variable"]].copy()
    table_data["new_var"] = outliers_df["new_var"].round(2)
    table_data["mean"] = round(series.mean(), 2)
    table_data["lower_bound"] = round(lower_bound, 2)
    table_data["upper_bound"] = round(upper_bound, 2)

    return table_data, outliers_df


# display joint outlier distribution summary
@st.cache_data
def display_joint_outlier_summary(joint_outlier_summary):
    """Display the joint outlier distribution summary.
    Args:
        joint_outlier_summary (pd.DataFrame): DataFrame containing
        joint outlier summary.
    """
    st.subheader("Joint Outlier Distribution")
    st.dataframe(
        joint_outlier_summary,
        hide_index=True,
        use_container_width=True,
        column_config={
            "id": st.column_config.Column("ID", width="small"),
            "name_variable": st.column_config.Column("Variable Name"),
            "new_var": st.column_config.NumberColumn(
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


# calculate joint outliers metrics
@st.cache_data
def calculate_joint_outliers_percentage(
    outliers_df: pd.DataFrame, selected_cols: list
) -> tuple:
    """
    Calculate metrics for joint outliers.

    Args:
        outliers_df (pd.DataFrame): DataFrame containing outlier data.
        selected_cols (list): List of selected variable columns.

    Returns
    -------
        tuple: A tuple containing the number of outliers, total count,
        and percentage of outliers.
    """
    if outliers_df.empty:
        return "0.00%"

    outlier_count = len(outliers_df)
    total_count = len(outliers_df[selected_cols].dropna())
    outlier_percentage = (outlier_count / total_count) * 100 if total_count > 0 else 0.0
    formatted_outlier_percentage = f"{outlier_percentage:.2f}%"

    return formatted_outlier_percentage


# plot joint outliers distribution
def plot_joint_outliers_distribution(reshaped_joint_outliers_df, selected_cols):
    """Plot the joint outliers distribution for selected columns.
    Args:
        reshaped_joint_outliers_df (pd.DataFrame): Melted DataFrame
        containing the variables to analyze.
        selected_cols (list): List of selected variable columns.
    """
    # Get common prefix
    x_axis_label = common_prefix(selected_cols)

    fig = go.Figure(
        data=go.Violin(
            y=reshaped_joint_outliers_df["new_var"],
            box_visible=True,
            line_color="black",
            meanline_visible=True,
            fillcolor="forestgreen",
            opacity=0.6,
            x0=x_axis_label,
        )
    )

    st.plotly_chart(fig, theme="streamlit", use_container_width=True)


# define function to create outliers report
def outliers_report(
    project_id: str, data: pd.DataFrame, setting_file: str, page_num: int
) -> None:
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
        selected_cols,
        reshaped_joint_outliers_df,
    ) = outliers_report_settings(project_id, data, setting_file, page_num)

    # Check that required options have been selected. If not, display a info message
    # Check for outliers
    table_data = detect_outliers(
        data,
        survey_key,
        survey_id,
        enumerator,
        outlier_cols,
        outlier_method,
        iqr_value,
        sd_value,
    )

    # display outlier metrics
    display_outlier_metrics(table_data, outlier_cols, enumerator)

    # plot outliers
    if not table_data.empty:
        plot_outlier_distributions(data, table_data, outlier_cols)

    # joint outlier distribution
    if selected_cols and reshaped_joint_outliers_df is not None:
        joint_outlier_summary = compute_joint_outlier_distribution(
            reshaped_joint_outliers_df,
            selected_cols,
            outlier_method,
            iqr_value,
            sd_value,
        )
        if not joint_outlier_summary.empty:
            # Display the joint outlier distribution summary
            display_joint_outlier_summary(joint_outlier_summary)

            # Calculate joint outliers percentage
            joint_outlier_percentage = calculate_joint_outliers_percentage(
                joint_outlier_summary, selected_cols
            )
            st.metric(value=joint_outlier_percentage, label="Share of outliers")

            # Plot joint outliers distribution
            plot_joint_outliers_distribution(reshaped_joint_outliers_df, selected_cols)
