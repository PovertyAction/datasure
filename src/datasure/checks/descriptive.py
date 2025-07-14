import os

import pandas as pd
import seaborn as sns
import streamlit as st

from datasure.utils import load_check_settings, save_check_settings, trigger_save


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

    default_col_list = default_settings.get("selected_cols") or []

    return (default_col_list,)


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
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for descriptive statistics")

        all_cols = data.columns.tolist()

        default_selected_cols = (
            load_default_summary_settings(setting_file=setting_file, page_num=page_num)
            or []
        )
        default_selected_cols = [
            col for col in default_selected_cols[0] if col in all_cols
        ]
        # survey_cols]

        # Let users select columns for analysis (max 10)
        selected_cols = st.multiselect(
            label="Select columns to include in descriptive statistics (maximum 10)",
            options=all_cols,
            default=default_selected_cols,
            key="selected_cols_key",
            max_selections=10,
            help="Select columns to include in descriptive statistics. Maximum of 10 columns can be selected.",
            on_change=trigger_save,
            kwargs={"state_name": "selected_cols_save"},
        )
        if (
            "selected_cols_save" in st.session_state
            and st.session_state.selected_cols_save
        ):
            save_check_settings(
                settings_file=setting_file,
                check_name="descriptive",
                check_settings={"selected_cols": selected_cols},
            )
            st.session_state.selected_cols_save = False

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


def plot_date_distribution(data: pd.DataFrame, date_col: str) -> None:
    """
    Plot the distribution of a date column.

    Parameters
    ----------
    data : pd.DataFrame
        The input dataframe.
    date_col : str
        The name of the date column to plot.
    """
    dd1, dd2, dd3 = st.columns(3)
    with dd1:
        output_type = st.selectbox(
            label="Select output type:",
            options=["Table", "Graph"],
            index=0,
            key=f"date_output_type_key_{date_col}",
        )
    date_format_str_pairs = {
        "2023-01-05": "%Y-%m-%d",
        "01-05-2023": "%d-%m-%Y",
        "05-01-2023": "%m-%d-%Y",
        "2023/01/05": "%Y/%m/%d",
        "01/05/2023": "%d/%m/%Y",
        "05/01/2023": "%m/%d/%Y",
        "January 05, 2023": "%B %d, %Y",
        "05 January 2023": "%d %B %Y",
        "2023-01-05 14:30:00": "%Y-%m-%d %H:%M:%S",
        "Locale date and time format": "%c",
        "Locale date format": "%x",
    }
    date_format_options = list(date_format_str_pairs.keys())
    with dd2:
        # Select date format for display
        date_format_sel = st.selectbox(
            label="Select date display format:",
            options=date_format_options,
            index=0,
            key=f"date_display_format_key{date_col}",
        )

    date_format_sel_str = date_format_str_pairs.get(date_format_sel)

    with dd3:
        period_format_pairs = {
            "Day": "D",
            "Week": "W",
            "Month": "M",
            "Quarter": "Q",
            "Year": "Y",
        }
        date_period_options = list(period_format_pairs.keys())
        date_period_sel = st.selectbox(
            label="Select date period for distribution:",
            options=date_period_options,
            index=0,
            key=f"date_period_key_{date_col}",
        )
        date_period_sel_str = period_format_pairs.get(date_period_sel)

    @st.cache_data
    def prepare_date_data(
        data: pd.DataFrame, date_col: str, date_display_format: str, date_period: str
    ) -> pd.DataFrame:
        """Prepare the data for plotting the distribution of a date column."""
        prepare_date_df = data[[date_col]].copy(deep=True)
        # If date-like string, convert it to datetime
        if pd.api.types.is_string_dtype(prepare_date_df[date_col]):
            prepare_date_df[date_col] = pd.to_datetime(
                prepare_date_df[date_col], errors="coerce"
            )

        prepare_date_df["DatePeriod"] = pd.to_datetime(
            prepare_date_df[date_col]
        ).dt.to_period(date_period)

        # get start date and end date from period for each row
        prepare_date_df["Start Date"] = prepare_date_df["DatePeriod"].apply(
            lambda x: x.start_time.strftime(date_display_format)
            if hasattr(x, "start_time")
            else x.strftime(date_display_format)
        )
        prepare_date_df["End Date"] = prepare_date_df["DatePeriod"].apply(
            lambda x: x.end_time.strftime(date_display_format)
            if hasattr(x, "end_time")
            else x.strftime(date_display_format)
        )

        return prepare_date_df

    @st.cache_data
    def table_date_distribution(
        prepped_date_data: pd.DataFrame, date_display_format: str
    ) -> pd.DataFrame:
        """Display the distribution of a date column in a table."""
        # aggregate the data by date period, keep start date, end date, and count frequency  # noqa: W505
        prepped_date_data["Date Period"] = prepped_date_data["DatePeriod"]
        date_distribution = (
            prepped_date_data.groupby(["Date Period", "Start Date", "End Date"])
            .agg({"DatePeriod": "count"})
            .reset_index()
            .rename(columns={"DatePeriod": "Frequency"})
        )
        date_distribution["Percentage"] = (
            date_distribution["Frequency"] / date_distribution["Frequency"].sum()
        ) * 100
        date_distribution.reset_index(drop=True, inplace=True)

        date_distribution["Date Period"] = date_distribution["Date Period"].dt.strftime(
            date_display_format
        )

        return date_distribution

    def display_table_date_distribution(
        prepped_date_data: pd.DataFrame, date_display_format: str
    ) -> None:
        """Display the distribution of a date column in a table."""
        st.write("### Date Distribution Table")
        cmap = sns.light_palette("pink", as_cmap=True)
        st.dataframe(
            prepped_date_data.style.format(
                {
                    "Frequency": "{:,.0f}",
                    "Percentage": "{:,.2f}%",
                }
            ).background_gradient(
                subset=["Frequency", "Percentage"],
                cmap=cmap,
                gmap=prepped_date_data["Frequency"],
            ),
            use_container_width=True,
            hide_index=True,
        )

    def display_graph_date_distribution(
        prepped_date_data: pd.DataFrame, date_display_format: str
    ) -> None:
        """Display the distribution of a date column in a graph."""
        st.write("### Date Distribution Graph")
        st.bar_chart(
            prepped_date_data.set_index("Start Date"),
            y="Frequency",
            use_container_width=True,
            height=300,
            color="#FF8000",
        )

    prepare_date_data_df = prepare_date_data(
        data=data,
        date_col=date_col,
        date_display_format=date_format_sel_str,
        date_period=date_period_sel_str,
    )
    date_distribution = table_date_distribution(
        prepped_date_data=prepare_date_data_df,
        date_display_format=date_format_sel_str,
    )
    if output_type == "Table":
        display_table_date_distribution(
            prepped_date_data=date_distribution,
            date_display_format=date_format_sel_str,
        )
    elif output_type == "Graph":
        display_graph_date_distribution(
            prepped_date_data=date_distribution,
            date_display_format=date_format_sel_str,
        )


def plot_categorical_distribution(data: pd.DataFrame, categorical_col: str) -> None:
    """
    Plot the distribution of a categorical column.

    Parameters
    ----------
    data : pd.DataFrame
        The input dataframe.
    categorical_col : str
        The name of the categorical column to plot.
    """
    ct1, ct2, ct3, ct4 = st.columns([0.1, 0.2, 0.35, 0.35])
    # check if column is a floating point
    continues_col = pd.api.types.is_float_dtype(data[categorical_col])
    with ct1:
        treat_as_continues = st.toggle(
            label="Basic Statistics",
            value=bool(continues_col),
            help="If the column is a floating point, it will be treated as continuous by default.",
            disabled=continues_col,
            key=f"treat_as_continuous_{categorical_col}",
        )

    cat_tab_type_options = (
        ["Basic Statistics"]
        if treat_as_continues
        else ["One-way Table", "Two-way Table (Cross Tabulation)", "Summary Statistics"]
    )
    with ct2:
        cat_tab_type = st.selectbox(
            label="Select table type:",
            options=cat_tab_type_options,
            index=0,
            key=f"cat_table_type_key_{categorical_col}",
        )

    if cat_tab_type == "Two-way Table (Cross Tabulation)":
        with ct3:
            # get categorical columns in data
            cat_cols_only = data.select_dtypes(
                include=["object", "category"]
            ).columns.tolist()
            cat_col_2 = st.selectbox(
                label="Select second column for cross tabulation:",
                options=cat_cols_only,
                index=0,
                key=f"cat_table_type_key_2_{categorical_col}",
            )
    if cat_tab_type == "Summary Statistics":
        with ct3:
            # get numeric columns in data
            num_cols_only = data.select_dtypes(
                include=["int64", "float64"]
            ).columns.tolist()
            num_col = st.multiselect(
                label="Select numeric columns for summary statistics:",
                options=num_cols_only,
                default=None,
                key=f"cat_table_type_key_3_{categorical_col}",
            )

        with ct4:
            summary_stat_type = st.multiselect(
                label="Select summary statistics type:",
                options=[
                    "min",
                    "max",
                    "mean",
                    "median",
                    "std",
                    "25th percentile",
                    "75th percentile",
                ],
                default=["min", "max", "mean", "median"],
                key=f"cat_table_type_key_4_{categorical_col}",
            )

    @st.cache_data
    def compute_one_way_table(data: pd.DataFrame, categorical_col: str) -> pd.DataFrame:
        """Compute one-way table for categorical column."""
        one_way_table = data[categorical_col].value_counts().reset_index()
        one_way_table.columns = [categorical_col, "Frequency"]
        one_way_table["Percentage"] = (
            one_way_table["Frequency"] / one_way_table["Frequency"].sum()
        ) * 100
        return one_way_table

    @st.cache_data
    def compute_two_way_table(
        data: pd.DataFrame, categorical_col: str, cat_col_2: str
    ) -> pd.DataFrame:
        """Compute two-way table for categorical columns."""
        two_way_table = pd.crosstab(data[categorical_col], data[cat_col_2])
        two_way_table["Total"] = two_way_table.sum(axis=1)
        two_way_table.loc["Total"] = two_way_table.sum()
        return two_way_table

    @st.cache_data
    def compute_summary_statistics_table(
        data: pd.DataFrame, categorical_col: str, num_cols: list, stats: list
    ) -> pd.DataFrame:
        """Compute summary statistics for categorical column and numeric columns."""
        summary_statistics = data.groupby(categorical_col)[num_cols].agg(stats)
        summary_statistics.columns = [
            "_".join(col).strip() for col in summary_statistics.columns.values
        ]
        return summary_statistics

    @st.cache_data
    def compute_basic_statistics(data: pd.DataFrame, numeric_col: str) -> pd.DataFrame:
        """Compute basic statistics for numeric column."""
        basic_statistics = data[numeric_col].describe()
        basic_statistics = pd.DataFrame(basic_statistics)
        basic_statistics.reset_index(inplace=True)
        # add number of missing values
        basic_statistics.loc[len(basic_statistics)] = [
            "Missing Values",
            data[numeric_col].isnull().sum(),
        ]
        # add number of unique values
        basic_statistics.loc[len(basic_statistics)] = [
            "Unique Values",
            data[numeric_col].nunique(),
        ]
        basic_statistics.rename(columns={"index": "Statistics", numeric_col: "Value"})

        return basic_statistics

    def display_one_way_table() -> None:
        """Display one-way table for categorical column."""
        one_way_table = compute_one_way_table(
            data=data, categorical_col=categorical_col
        )

        st.write("### One-way Table")
        cmap = sns.light_palette("pink", as_cmap=True)
        st.dataframe(
            one_way_table.style.format(
                {
                    "Frequency": "{:,.0f}",
                    "Percentage": "{:,.2f}%",
                }
            ).background_gradient(
                subset=["Frequency", "Percentage"],
                cmap=cmap,
                gmap=one_way_table["Frequency"],
            ),
            use_container_width=True,
            hide_index=True,
        )

    def display_two_way_table() -> None:
        """Display two-way table for categorical columns."""
        two_way_table = compute_two_way_table(
            data=data, categorical_col=categorical_col, cat_col_2=cat_col_2
        )
        # make index index a column
        two_way_table.reset_index(inplace=True)
        two_way_table.rename(columns={"index": categorical_col}, inplace=True)
        # remove total row
        two_way_table = two_way_table[two_way_table[categorical_col] != "Total"]
        format_cols = [
            col
            for col in two_way_table.columns
            if col != categorical_col and col != "Total"
        ]
        two_way_table = two_way_table[[categorical_col, "Total"] + format_cols]

        st.write("### Two-way Table")
        cmap = sns.light_palette("pink", as_cmap=True)
        st.dataframe(
            two_way_table.style.background_gradient(subset=format_cols, cmap=cmap),
            use_container_width=True,
            hide_index=True,
        )

    def display_basic_statistics(basic_statistics: pd.DataFrame) -> None:
        """Display basic statistics for numeric column."""
        st.write("### Basic Statistics")
        st.dataframe(
            basic_statistics,
            use_container_width=True,
            hide_index=True,
        )

    if cat_tab_type == "One-way Table":
        display_one_way_table()
    elif cat_tab_type == "Two-way Table (Cross Tabulation)":
        display_two_way_table()
    elif cat_tab_type == "Summary Statistics":
        if num_col and summary_stat_type:
            summary_statistics = compute_summary_statistics_table(
                data=data,
                categorical_col=categorical_col,
                num_cols=num_col,
                stats=summary_stat_type,
            )
            # make index index a column
            summary_statistics.reset_index(inplace=True)
            summary_statistics.rename(columns={"index": categorical_col}, inplace=True)
            # get a list of columns to format
            format_cols = [
                col for col in summary_statistics.columns if col != categorical_col
            ]
            cmap = sns.light_palette("pink", as_cmap=True)
            st.dataframe(
                summary_statistics.style.format(
                    {c: "{:,.2f}" for c in format_cols},
                ).background_gradient(subset=format_cols, cmap=cmap),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning("Please select a numeric column for summary statistics.")
            return
    elif cat_tab_type == "Basic Statistics":
        basic_statistics = compute_basic_statistics(
            data=data, numeric_col=categorical_col
        )
        display_basic_statistics(basic_statistics=basic_statistics)


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
    selected_cols, date_cols, numeric_cols, categorical_cols = (
        descriptive_report_settings(
            data=data,
            setting_file=setting_file,
            page_num=page_num,
        )
    )

    if not selected_cols:
        st.info(
            "Descriptive statistics requires at least one column to be selected. Go to the :material/settings: settings section above to select columns.",
        )
        return

    # loop through selected columns and create a summary report
    for col in selected_cols:
        st.write("---")
        st.markdown(f"### Descriptive Statistics for {col}")

        # check if column is date-like
        if col in date_cols[0]:
            plot_date_distribution(data=data, date_col=col)
        elif col in numeric_cols[0] or categorical_cols[0]:
            plot_categorical_distribution(data=data, categorical_col=col)
