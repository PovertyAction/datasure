import os

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from src.utils import load_check_settings


@st.cache_data
def load_default_summary_settings(setting_file: str, page_num: int) -> tuple:
    """
    Load default summary settings from a JSON file.

    Parameters
    ----------
    setting_file : str
        Path to the JSON file containing default settings.
    page_num : int
        Page number for the Streamlit app.

    Returns
    -------
    tuple
        A tuple containing the loaded settings and the page number.
    """
    # load default settings in the following order:
    # - if settings file exists, load settings from file
    # - if settings file does not exist, load default settings from config

    if setting_file and os.path.exists(setting_file):
        default_settings = load_check_settings(setting_file, "descriptive") or {}
    else:
        default_settings = {}

    default_col_list = default_settings.get("column_list") or []

    default_numeric_col_type = default_settings.get("numeric_col_type") or "Continuous"

    default_table_type = default_settings.get("table_type") or "One-way Table"
    default_display_type = default_settings.get("display_type") or "Table"

    return (
        default_col_list,
        default_numeric_col_type,
        default_table_type,
        default_display_type,
    )


def datetime_check(col: pd.Series) -> bool:
    """
    Check if column can be converted to date/datetime.

    Parameters
    ----------
    col : pd.Series
        The column to check.

    Returns
    -------
    bool
        True if the column is date-like, False otherwise.
    """
    if isinstance(col, str):
        try:
            pd.to_datetime(col, errors="raise")
            if pd.api.types.is_datetime64_any_dtype(col):
                return True
        except (ValueError, TypeError):
            return False

    return False


def descriptive_report_settings(
    data: pd.DataFrame, setting_file: str, page_num: int
) -> tuple:
    """
    Get the settings for the descriptive report.

    Parameters
    ----------
    data : pd.DataFrame
        The input dataframe to visualize.
    setting_file : str
        Path to the JSON file containing default settings.
    page_num : int
        Page number for the Streamlit app.

    Returns
    -------
    tuple
        A tuple containing the selected columns, treatment type, table type, and
        display type.
    """
    with st.expander("Descriptive Statistics Settings", expanded=True):
        st.markdown("## Configure settings for descriptive statistics")

        survey_cols = data.columns

        (
            default_selected_cols,
            default_treat_as_global,
            default_table_type_global,
            default_display_type_global,
        ) = load_default_summary_settings(setting_file=setting_file, page_num=page_num)

        # Let users select columns for analysis (max 10)
        selected_cols = st.multiselect(
            label="Select columns to include in descriptive statistics (maximum 10)",
            options=list(survey_cols),
            default=default_selected_cols,
            key="selected_cols_key",
            max_selections=10,
        )

        # return a list of date/datetime columns
        date_cols = [
            data[selected_cols]
            .select_dtypes(include=["datetime64", "datetime64[ns]"])
            .columns.tolist()
        ]
        # Check for columns that might be dates but not recognized as datetime
        potential_date_cols = (
            data[selected_cols]
            .apply(
                lambda col: datetime_check(col) if col.name not in date_cols else False
            )
            .any()
        )
        # Confirm which date columns should be treated as dates
        if potential_date_cols:
            st.markdown("### Date Column Detection")
            st.write(
                "The following columns might contain date values. Please select which ones to treat as dates:"
            )

            date_confirm = st.multiselect(
                label="Select columns to treat as dates",
                options=potential_date_cols,
                default=potential_date_cols,
            )
            if date_confirm:
                # Convert confirmed date columns to datetime
                for col in date_confirm:
                    try:
                        data[col] = pd.to_datetime(data[col])
                        if col not in date_cols:
                            date_cols.append(col)
                    except Exception as e:
                        st.warning(f"Could not convert '{col}' to datetime: {e}")

        # return a list of numeric columns
        numeric_cols = [
            data[selected_cols]
            .select_dtypes(include=["int64", "float64"])
            .columns.tolist()
        ]
        # return a list of categorical columns
        categorical_cols = [
            data[selected_cols]
            .select_dtypes(include=["object", "category"])
            .columns.tolist()
        ]

    return selected_cols, date_cols, numeric_cols, categorical_cols


# define function to create summary report
def descriptive_report(data: pd.DataFrame, setting_file: str, page_num: int) -> None:  # noqa: D417, RUF100
    """
    Visualize the distribution of categorical and numeric variables in the dataframe.

    Parameters
    ----------
    data : pd.DataFrame
        The input dataframe to visualize.

    Returns
    -------
    None

    """
    survey_cols = data.columns

    (
        default_selected_cols,
        default_treat_as_global,
        default_table_type_global,
        default_display_type_global,
    ) = load_default_summary_settings(setting_file=setting_file, page_num=page_num)

    selected_cols, date_cols, numeric_cols, categorical_cols = (
        descriptive_report_settings(
            data=data,
            setting_file=setting_file,
            page_num=page_num,
        )
    )

    # Only show settings if columns are selected
    if selected_cols:
        # Filter data to only include selected columns
        data_filtered = data[selected_cols]

        # Identify column types
        cat_vars = data_filtered.select_dtypes(
            include=["object", "category"]
        ).columns.tolist()
        num_vars = data_filtered.select_dtypes(
            include=["int64", "float64"]
        ).columns.tolist()
        date_vars = data_filtered.select_dtypes(
            include=["datetime64", "datetime64[ns]"]
        ).columns.tolist()

        # Check for columns that might be dates but not recognized as datetime
        potential_date_cols = []
        for col in selected_cols:
            if col not in cat_vars and col not in num_vars and col not in date_vars:
                # Check if column might be a date
                try:
                    # Attempt to parse the first non-null value
                    sample_val = data_filtered[col].dropna().iloc[0]
                    if isinstance(sample_val, str):
                        pd.to_datetime(sample_val)
                        potential_date_cols.append(col)
                except (ValueError, TypeError, IndexError):
                    pass

        # Confirm which date columns should be treated as dates
        if potential_date_cols:
            st.markdown("### Date Column Detection")
            st.write(
                "The following columns might contain date values. Please select which ones to treat as dates:"
            )

            date_confirm = st.multiselect(
                "Select columns to treat as dates",
                options=potential_date_cols,
                default=potential_date_cols,
            )

            # Convert confirmed date columns to datetime
            for col in date_confirm:
                try:
                    data_filtered[col] = pd.to_datetime(data_filtered[col])
                    if col in cat_vars:
                        cat_vars.remove(col)
                    date_vars.append(col)
                except Exception as e:
                    st.warning(f"Could not convert '{col}' to datetime: {e}")

        # For remaining columns that are in selected_cols but not categorized
        extra_cols = [
            col
            for col in selected_cols
            if col not in cat_vars and col not in num_vars and col not in date_vars
        ]

        if extra_cols:
            # Try to identify if these should be numeric or categorical
            for col in extra_cols:
                try:
                    # Convert to numeric if possible
                    data_filtered[col] = pd.to_numeric(data_filtered[col])
                    num_vars.append(col)
                except:
                    # Otherwise treat as categorical
                    cat_vars.append(col)

        # Date Variables Settings
        if len(date_vars) > 0:
            st.markdown("### Date Variables Settings")
            st.write(f"Found {len(date_vars)} date variables.")

            # Select date format for display
            date_format = st.selectbox(
                "Select date format for display:",
                options=[
                    "%Y-%m-%d",  # 2023-01-15
                    "%d/%m/%Y",  # 15/01/2023
                    "%m/%d/%Y",  # 01/15/2023
                    "%B %d, %Y",  # January 15, 2023
                    "%d %B %Y",  # 15 January 2023
                    "%Y-%m-%d %H:%M:%S",  # 2023-01-15 14:30:00
                ],
                index=0,
                key="date_format",
            )

            # Analysis type for date variables
            date_analysis_type = st.radio(
                "Analysis type for date variables:",
                options=["Frequency Table", "Distribution by Period"],
                key="date_analysis_type",
                horizontal=True,
            )

            # Period selection for distribution analysis
            date_period = None
            display_mode = None
            if date_analysis_type == "Distribution by Period":
                col1, col2 = st.columns(2)

                with col1:
                    # MODIFIED: Removed "Day of Week" from options
                    date_period = st.selectbox(
                        "Group dates by:",
                        options=["Year", "Month", "Quarter"],
                        key="date_period",
                    )

                with col2:
                    display_mode = st.radio(
                        "Display as:",
                        options=["Table", "Graph", "Both"],
                        key="date_display_mode",
                        horizontal=True,
                        index=2,
                    )

        # Categorical Variables Settings
        if len(cat_vars) > 0:
            st.markdown("### Categorical Variables Settings")
            st.write(f"Found {len(cat_vars)} categorical variables.")

            # Selection between one-way and two-way table
            analysis_type = st.radio(
                "Analysis type for all categorical variables:",
                options=["One-way Table", "Two-way Table (Cross-tabulation)"],
                key="cat_analysis_type",
                horizontal=True,
            )

            # For two-way tables, select a variable for cross-tabulation
            cross_tab_col = None
            if analysis_type == "Two-way Table (Cross-tabulation)":
                # Get all columns from the original dataset for cross-tabulation
                all_cols = data.columns.tolist()

                cross_tab_col = st.selectbox(
                    "Cross-tabulate all categorical variables with:",
                    options=all_cols,
                    key="cat_crosstab_global",
                )

        # Numeric Variables Settings
        if len(num_vars) > 0:
            st.markdown("### Numeric Variables Settings")
            st.write(f"Found {len(num_vars)} numeric variables.")

            # Global settings for numeric variables
            col1, col2 = st.columns(2)

            with col1:
                treat_as_global = st.radio(
                    "Treat all numeric variables as:",
                    options=["Continuous", "Categorical"],
                    key="num_treat_global",
                    horizontal=True,
                )

            with col2:
                if treat_as_global == "Continuous":
                    display_type_global = st.radio(
                        "Display type for all numeric variables:",
                        options=["Table", "Graph"],
                        key="num_display_global",
                        horizontal=True,
                    )
                else:
                    # For categorical, only show Table options
                    display_type_global = "Table"

            # For Table options, choose table type (oneway or twoway)
            table_type_global = None
            cross_tab_col_num = None

            if display_type_global == "Table":
                table_type_global = st.radio(
                    "Table type for all numeric variables:",
                    options=["One-way Table", "Two-way Table (Cross-tabulation)"],
                    key="num_table_global",
                    horizontal=True,
                )

                # For two-way tables, set up cross-tabulation
                if table_type_global == "Two-way Table (Cross-tabulation)":
                    # Get all columns from the original df for cross-tabulation
                    all_cols = data.columns.tolist()

                    cross_tab_col_num = st.selectbox(
                        "Cross-tabulate all numeric variables with:",
                        options=all_cols,
                        key="num_crosstab_global",
                    )

            # For continuous variables with statistics
            stats_to_show_global = None
            if (
                treat_as_global == "Continuous"
                and display_type_global == "Table"
                and table_type_global == "One-way Table"
            ):
                # Select statistics to display
                stats_to_show_global = st.multiselect(
                    "Statistics to display for all numeric variables:",
                    options=[
                        "Mean",
                        "Median",
                        "Standard Deviation",
                        "Min",
                        "Max",
                        "Quartiles",
                    ],
                    default=["Mean", "Median", "Standard Deviation", "Min", "Max"],
                    key="stats_global",
                )

    # Check if any columns were selected
    if not selected_cols:
        st.warning(
            "No columns selected. Please select up to 10 columns in the settings above."
        )
        return

    # RESULTS SECTIONS
    # Date Variables Section
    if "date_vars" in locals() and len(date_vars) > 0:
        st.header("Date Variables Analysis")
        st.write(f"Displaying analyses for {len(date_vars)} date variables.")

        # Process each date variable
        for var in date_vars:
            st.subheader(var)

            # Format dates for display
            formatted_dates = data_filtered[var].dt.strftime(date_format)

            if "date_analysis_type" in locals():
                if date_analysis_type == "Frequency Table":
                    # Calculate value counts with formatted dates
                    value_counts = (
                        data_filtered[var]
                        .dt.strftime(date_format)
                        .value_counts()
                        .reset_index()
                    )
                    value_counts.columns = [f"{var} ({date_format})", "Count"]
                    value_counts["Percentage"] = (
                        value_counts["Count"] / value_counts["Count"].sum() * 100
                    ).round(2)

                    # Sort by date
                    try:
                        # Convert formatted strings back to dates for sorting
                        temp_dates = pd.to_datetime(
                            value_counts[f"{var} ({date_format})"], format=date_format
                        )
                        value_counts = value_counts.iloc[temp_dates.argsort().values]
                    except:
                        # If conversion fails, keep as is
                        pass

                    # Display table
                    st.write("**Frequency Table**")
                    st.dataframe(value_counts, width=600)

                elif date_analysis_type == "Distribution by Period":
                    # Group by selected period
                    if date_period == "Year":
                        period_data = data_filtered[var].dt.year
                        period_name = "Year"
                    elif date_period == "Month":
                        period_data = data_filtered[var].dt.month_name()
                        period_name = "Month"
                    # MODIFIED: Removed Day of Week case
                    elif date_period == "Quarter":
                        period_data = data_filtered[var].dt.quarter
                        period_name = "Quarter"

                    # Calculate value counts
                    period_counts = period_data.value_counts().reset_index()
                    period_counts.columns = [period_name, "Count"]
                    period_counts["Percentage"] = (
                        period_counts["Count"] / period_counts["Count"].sum() * 100
                    ).round(2)

                    # Sort by period if numeric
                    if period_name in ["Year", "Quarter"]:
                        period_counts = period_counts.sort_values(by=period_name)
                    elif period_name == "Month":
                        # Create a categorical month order
                        month_order = [
                            "January",
                            "February",
                            "March",
                            "April",
                            "May",
                            "June",
                            "July",
                            "August",
                            "September",
                            "October",
                            "November",
                            "December",
                        ]
                        period_counts[period_name] = pd.Categorical(
                            period_counts[period_name],
                            categories=month_order,
                            ordered=True,
                        )
                        period_counts = period_counts.sort_values(by=period_name)
                    # MODIFIED: Removed Day of Week sorting

                    # Display based on the selected display mode
                    if display_mode in ["Table", "Both"]:
                        st.write(f"**Distribution by {period_name} (Table)**")
                        st.dataframe(period_counts, width=600)

                    if display_mode in ["Graph", "Both"]:
                        # Create bar chart
                        try:
                            st.write(f"**Distribution by {period_name} (Graph)**")
                            fig, ax = plt.subplots(figsize=(10, 6))

                            ax.bar(
                                period_counts[period_name],
                                period_counts["Count"],
                                color="#4C9A4C",
                                alpha=0.7,
                            )

                            # Set labels and title
                            ax.set_xlabel(period_name)
                            ax.set_ylabel("Count")
                            ax.set_title(f"Distribution of {var} by {period_name}")

                            # Format x-axis
                            plt.xticks(rotation=45)
                            plt.tight_layout()

                            # Remove top and right spines
                            ax.spines["top"].set_visible(False)
                            ax.spines["right"].set_visible(False)

                            st.pyplot(fig)

                        except Exception as e:
                            st.error(f"Error creating bar chart: {e}")

            # Show basic summary statistics
            with st.expander("View Date Summary Statistics", expanded=False):
                min_date = data_filtered[var].min()
                max_date = data_filtered[var].max()

                # Calculate range in days
                range_days = (max_date - min_date).days

                # Calculate time-related statistics
                date_stats = {
                    "Earliest Date": min_date.strftime(date_format),
                    "Latest Date": max_date.strftime(date_format),
                    "Range (days)": range_days,
                    "Most Common Date": data_filtered[var]
                    .value_counts()
                    .idxmax()
                    .strftime(date_format),
                    "Count of Most Common Date": data_filtered[var]
                    .value_counts()
                    .max(),
                    "Count of Unique Dates": data_filtered[var].nunique(),
                }

                stats_df = pd.DataFrame(
                    date_stats.items(), columns=["Statistic", "Value"]
                )
                st.dataframe(stats_df, width=600)

            st.markdown("---")

    # Categorical Variables Section
    if len(cat_vars) > 0:
        st.header("Categorical Variables Analysis")
        st.write(
            f"Displaying analyses for {len(cat_vars)} selected categorical variables."
        )

        # Process each categorical variable
        for var in cat_vars:
            st.subheader(var)

            if analysis_type == "One-way Table":
                # Calculate value counts
                value_counts = data_filtered[var].value_counts().reset_index()
                value_counts.columns = [var, "Count"]
                value_counts["Percentage"] = (
                    value_counts["Count"] / value_counts["Count"].sum() * 100
                ).round(2)

                # Display table
                st.dataframe(value_counts, width=600)

            else:  # Two-way Table (Cross-tabulation)
                # Skip cross-tabulation with itself
                if var == cross_tab_col:
                    st.warning(
                        f"Cannot cross-tabulate '{var}' with itself. Please select a different variable for cross-tabulation."
                    )
                    continue

                # Check if cross_tab_col is in the data
                if cross_tab_col not in data.columns:
                    st.error(f"Selected column '{cross_tab_col}' not found in dataset")
                    continue

                # Generate cross-tabulation
                try:
                    # Ensure both variables are in the filtered data
                    if cross_tab_col not in data_filtered.columns:
                        # Create a temporary df with both columns
                        temp_df = pd.DataFrame(
                            {
                                var: data_filtered[var],
                                cross_tab_col: data[cross_tab_col],
                            }
                        )

                        cross_tab = pd.crosstab(
                            temp_df[var],
                            temp_df[cross_tab_col],
                            margins=True,
                            margins_name="Total",
                        )
                    else:
                        cross_tab = pd.crosstab(
                            data_filtered[var],
                            data_filtered[cross_tab_col],
                            margins=True,
                            margins_name="Total",
                        )

                    st.write(f"Cross-tabulation of '{var}' with '{cross_tab_col}'")
                    st.dataframe(cross_tab)
                except Exception as e:
                    st.error(f"Error creating cross-tabulation: {e!s}")

            st.markdown("---")

    # Numeric Variables Section
    if len(num_vars) > 0:
        st.header("Numeric Variables Analysis")
        st.write(f"Displaying analyses for {len(num_vars)} selected numeric variables.")

        # Process each numeric variable
        for var in num_vars:
            st.subheader(var)

            # For Table option
            if display_type_global == "Table":
                if table_type_global == "One-way Table":
                    if treat_as_global == "Continuous":
                        # Calculate statistics based on global selection
                        stats_dict = {}

                        if "Mean" in stats_to_show_global:
                            stats_dict["Mean"] = data_filtered[var].mean()
                        if "Median" in stats_to_show_global:
                            stats_dict["Median"] = data_filtered[var].median()
                        if "Standard Deviation" in stats_to_show_global:
                            stats_dict["Standard Deviation"] = data_filtered[var].std()
                        if "Min" in stats_to_show_global:
                            stats_dict["Min"] = data_filtered[var].min()
                        if "Max" in stats_to_show_global:
                            stats_dict["Max"] = data_filtered[var].max()
                        if "Quartiles" in stats_to_show_global:
                            q1 = data_filtered[var].quantile(0.25)
                            q3 = data_filtered[var].quantile(0.75)
                            stats_dict["25% Quartile"] = q1
                            stats_dict["75% Quartile"] = q3
                            stats_dict["IQR"] = q3 - q1

                        # Display statistics as table
                        stats_df = pd.DataFrame(
                            stats_dict.items(), columns=["Statistic", "Value"]
                        )
                        st.dataframe(stats_df, width=600)
                    else:
                        # For categorical one-way table
                        cat_values = data_filtered[var].astype("category")
                        value_counts = cat_values.value_counts().reset_index()
                        value_counts.columns = [var, "Count"]
                        value_counts["Percentage"] = (
                            value_counts["Count"] / value_counts["Count"].sum() * 100
                        ).round(2)
                        st.dataframe(value_counts, width=600)

                else:  # Two-way Table (Cross-tabulation)
                    # Skip cross-tabulation with itself
                    if var == cross_tab_col_num:
                        st.warning(
                            f"Cannot cross-tabulate '{var}' with itself. Please select a different variable for cross-tabulation."
                        )
                        continue

                    # Check if cross_tab_col_num is in the data
                    if cross_tab_col_num not in data.columns:
                        st.error(
                            f"Selected column '{cross_tab_col_num}' not found in dataset"
                        )
                        continue

                    # Generate cross-tabulation
                    try:
                        # Ensure both variables are in the filtered data
                        if cross_tab_col_num not in data_filtered.columns:
                            # Create a temporary df with both columns
                            temp_df = pd.DataFrame(
                                {
                                    var: data_filtered[var],
                                    cross_tab_col_num: data[cross_tab_col_num],
                                }
                            )

                            cross_tab = pd.crosstab(
                                temp_df[var],
                                temp_df[cross_tab_col_num],
                                margins=True,
                                margins_name="Total",
                            )
                        else:
                            cross_tab = pd.crosstab(
                                data_filtered[var],
                                data_filtered[cross_tab_col_num],
                                margins=True,
                                margins_name="Total",
                            )

                        st.write(
                            f"Cross-tabulation of '{var}' with '{cross_tab_col_num}'"
                        )
                        st.dataframe(cross_tab)
                    except Exception as e:
                        st.error(f"Error creating cross-tabulation: {e!s}")

            # For Graph option - only available for continuous variables
            elif display_type_global == "Graph":
                # Creating histogram with green color scheme
                try:
                    fig, ax = plt.subplots(figsize=(10, 6))

                    counts, bins, patches = ax.hist(
                        data_filtered[var].dropna(),
                        bins=12,
                        color="#4C9A4C",
                        edgecolor="white",
                        alpha=0.7,
                    )

                    # Set labels and title
                    ax.set_xlabel(var)
                    ax.set_title(f"Distribution of {var}")

                    # Remove top and right spines
                    ax.spines["top"].set_visible(False)
                    ax.spines["right"].set_visible(False)

                    st.pyplot(fig)

                    # Calculate and display basic statistics alongside histogram
                    basic_stats = {
                        "Mean": data_filtered[var].mean(),
                        "Median": data_filtered[var].median(),
                        "Standard Deviation": data_filtered[var].std(),
                        "Min": data_filtered[var].min(),
                        "Max": data_filtered[var].max(),
                    }
                    stats_df = pd.DataFrame(
                        basic_stats.items(), columns=["Statistic", "Value"]
                    )
                    st.dataframe(stats_df, width=600)
                except Exception as e:
                    st.error(f"Error creating histogram: {e!s}")

            st.markdown("---")
