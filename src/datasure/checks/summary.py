import os

import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import seaborn as sns
import streamlit as st

from datasure.utils import (
    donut_chart2,
    get_check_config_settings,
    get_df_info,
    load_check_settings,
    save_check_settings,
    trigger_save,
)


def load_default_settings(project_id: str, setting_file: str, page_num: int) -> tuple:
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
    _, _, _, config_survey_id, config_survey_date, _, _, _ = get_check_config_settings(
        project_id=project_id,
        page_row_index=page_num - 1,
    )

    # load default settings in the following order:
    # - if settings file exists, load settings from file
    # - if settings file does not exist, load default settings from config
    if setting_file and os.path.exists(setting_file):
        default_settings = load_check_settings(setting_file, "summary") or {}
    else:
        default_settings = {}

    default_date = default_settings.get("date", config_survey_date)
    default_survey_id = default_settings.get("survey_id", config_survey_id)

    # if target is not set, return None
    default_target = default_settings.get("target")

    return default_date, default_target, default_survey_id


# define function to create summary report
def summary_settings(
    project_id: str, data: pd.DataFrame, setting_file: str, page_num
) -> tuple:
    """
    Get the settings for the summary report.

    Parameters
    ----------
    data : pd.DataFrame
            The survey data

    Returns
    -------
    tuple
            A tuple containing the settings for the summary report

    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for summary report")

        st.write("---")
        st.markdown("### Select columns to include in summary report")

        default_date, default_target, default_survey_id = load_default_settings(
            project_id=project_id, setting_file=setting_file, page_num=page_num
        )

        _, string_columns, numeric_columns, datetime_columns, _ = get_df_info(
            data, cols_only=True
        )
        with st.container(border=True):
            sc1, sc2, sc3 = st.columns(spec=3)

            with sc1:
                id_col_options = string_columns + numeric_columns
                default_survey_id_index = (
                    id_col_options.index(default_survey_id)
                    if default_survey_id and default_survey_id in id_col_options
                    else None
                )

                survey_id = st.selectbox(
                    label="Survey ID",
                    options=id_col_options,
                    help="Column containing survey ID",
                    index=default_survey_id_index,
                    key="survey_id_summary",
                    on_change=trigger_save,
                    kwargs={"state_name": "summary_survey_id"},
                )
                if (
                    "summary_survey_id" in st.session_state
                    and st.session_state.summary_survey_id
                ):
                    save_check_settings(
                        settings_file=setting_file,
                        check_name="summary",
                        check_settings={"survey_id": survey_id},
                    )
                    st.session_state.summary_survey_id = False

            with sc2:
                default_date_index = (
                    datetime_columns.index(default_date)
                    if default_date and default_date in datetime_columns
                    else None
                )
                date = st.selectbox(
                    label="Survey Date",
                    options=datetime_columns,
                    help="Column containing survey date",
                    index=default_date_index,
                    key="date_summary",
                    on_change=trigger_save,
                    kwargs={"state_name": "summary_date"},
                )
                if "summary_date" in st.session_state and st.session_state.summary_date:
                    save_check_settings(
                        settings_file=setting_file,
                        check_name="summary",
                        check_settings={"date": date},
                    )
                    st.session_state.summary_date = False

            with sc3:
                target = st.number_input(
                    label="Total Expected Interviews",
                    min_value=0,
                    value=default_target,
                    help="Total number of interviews expected",
                    key="total_goal_summary",
                    on_change=trigger_save,
                    kwargs={"state_name": "summary_target"},
                )
                if (
                    "summary_target" in st.session_state
                    and st.session_state.summary_target
                ):
                    save_check_settings(
                        settings_file=setting_file,
                        check_name="summary",
                        check_settings={"target": target},
                    )
                    st.session_state.summary_target = False

    return date, target, survey_id or None


@st.cache_data
def compute_summary_submissions(data: pd.DataFrame, date: str) -> tuple:
    """
    Compute values for summary submissions

    Parameters
    ----------
    data : pd.DataFrame
            The survey data

    date : str
            The date column in the survey data

    Returns
    -------
    tuple
            A tuple containing the summary values

    """
    summary_df = data[[date]].copy(deep=True)

    # return None and 0 if no data
    if summary_df.empty:
        return (
            None,
            None,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            pd.DataFrame(),
        )

    # check if date column is in the data
    # try convertting to datetime
    # and raise error if conversion fails
    if not pd.api.types.is_datetime64_any_dtype(summary_df[date]):
        summary_df[date] = pd.to_datetime(summary_df[date], errors="coerce")
        if not pd.api.types.is_datetime64_any_dtype(summary_df[date]):
            raise ValueError(f"Column {date} is not a datetime column")

    summary_df[date] = summary_df[date].dt.date
    # count number of submissions with missing date
    missing_date_count = max(summary_df[date].isnull().sum(), 0)
    summary_df = summary_df.dropna(subset=[date])
    # dataset is empty after dropping missing date return None
    if summary_df.empty:
        return (
            None,
            None,
            0,
            0,
            0,
            missing_date_count,
            0,
            0,
            0,
            pd.DataFrame(),
        )

    first_submission_date = summary_df[date].min()
    last_submission_date = summary_df[date].max()

    todays_date = pd.Timestamp.now().date()
    submissions_today = summary_df[summary_df[date] == todays_date].shape[0]

    yestedays_date = (pd.Timestamp.now().normalize() - pd.DateOffset(days=1)).date()
    submissions_yesterday = summary_df[summary_df[date] == yestedays_date].shape[0]

    this_week_start_date = (
        pd.Timestamp.now().normalize() - pd.DateOffset(weeks=1)
    ).date()
    submissions_this_week = summary_df[summary_df[date] >= this_week_start_date].shape[
        0
    ]

    lastweek_start_date = (
        pd.Timestamp.now().normalize() - pd.DateOffset(weeks=2)
    ).date()
    lastweek_end_date = (pd.Timestamp.now().normalize() - pd.DateOffset(weeks=1)).date()
    submissions_last_week = summary_df[
        (summary_df[date] >= lastweek_start_date)
        & (summary_df[date] < lastweek_end_date)
    ].shape[0]

    this_months_start_date = (
        pd.Timestamp.now().normalize() - pd.DateOffset(months=1)
    ).date()
    submissions_this_month = summary_df[
        summary_df[date] >= this_months_start_date
    ].shape[0]

    last_month_start_date = (
        pd.Timestamp.now().normalize() - pd.DateOffset(months=2)
    ).date()
    last_month_end_date = (
        pd.Timestamp.now().normalize() - pd.DateOffset(months=1)
    ).date()
    submissions_last_month = summary_df[
        (summary_df[date] >= last_month_start_date)
        & (summary_df[date] < last_month_end_date)
    ].shape[0]

    submissions_total = data.shape[0]

    submissions_today_delta = (
        ((submissions_today - submissions_yesterday) / submissions_yesterday) * 100
        if submissions_yesterday > 0
        else 0
    )
    submissions_this_week_delta = (
        ((submissions_this_week - submissions_last_week) / submissions_last_week) * 100
        if submissions_last_week > 0
        else 0
    )
    submissions_this_month_delta = (
        ((submissions_this_month - submissions_last_month) / submissions_last_month)
        * 100
        if submissions_last_month > 0
        else 0
    )

    submissions_by_date = (
        summary_df.groupby(date).size().reset_index(name="submissions")
    )

    return (
        first_submission_date,
        last_submission_date,
        submissions_today,
        submissions_this_week,
        submissions_this_month,
        submissions_total + missing_date_count,
        submissions_today_delta,
        submissions_this_week_delta,
        submissions_this_month_delta,
        submissions_by_date,
    )


def summary_submissions(data: pd.DataFrame, date: str | None = None) -> None:
    """
    Generates a summary report for the survey data

    Parameters
    ----------
    data : pd.DataFrame
            The survey data

    date : str
            The date column in the survey data

    Returns
    -------
    None
    """
    st.markdown("## Submission details")
    if date:
        (
            first_submission_date,
            last_submission_date,
            submissions_today,
            submissions_this_week,
            submissions_this_month,
            submissions_total,
            submissions_today_delta,
            submissions_this_week_delta,
            submissions_this_month_delta,
            submissions_by_date,
        ) = compute_summary_submissions(data=data, date=date)

        dc1, _, _, dc2 = st.columns(spec=4)
        dc1.metric(
            label="First Submission",
            value=str(first_submission_date),
            help="Date of the first submission",
        )
        dc2.metric(
            label="Last Submission",
            value=str(last_submission_date),
            help="Date of the last submission",
        )

        mc1, mc2, mc3, mc4 = st.columns(spec=4, border=True)

        mc1.metric(
            label="Today",
            value=f"{submissions_today:,}",
            delta=f"{submissions_today_delta:.2f}%",
            help="Number of submissions today. Delta is the percentage change from yesterday.",
        )
        mc2.metric(
            label="This week",
            value=f"{submissions_this_week:,}",
            delta=f"{submissions_this_week_delta:.2f}%",
            help="Number of submissions this week. Delta is the percentage change from last week.",
        )
        mc3.metric(
            label="This month",
            value=f"{submissions_this_month:,}",
            delta=f"{submissions_this_month_delta:.2f}%",
            help="Number of submissions this month. Delta is the percentage change from last month",
        )
        mc4.metric(
            label="Total",
            value=f"{submissions_total:,}",
            help="Total number of submissions",
        )

        fig = px.area(
            submissions_by_date,
            x=date,
            y="submissions",
            title="Submissions by date",
            color_discrete_sequence=["#e8848b"],
        )
        fig.update_layout(width=1000, height=500)
        fig.update_yaxes(tick0=0)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(
            "Submission details report requires a date column to be selected. Go to the :material/settings: settings section above."
        )


@st.cache_data
def compute_summary_progress(
    data: pd.DataFrame, date: str, target: int | None = None
) -> tuple:
    """
    Compute values for summary progress

    Parameters
    ----------
    data : pd.DataFrame
            The survey data

    date : str
            The date column in the survey data

    enumerator : str | None
            The enumerator column in the survey data

    target : int | None
            The target number of submissions

    Returns
    -------
    tuple
            A tuple containing the summary values

    """
    # if target is negative, or not an integer, raise error
    if target is not None and (not isinstance(target, int) or target < 0):
        raise ValueError("Target must be a positive integer")
    prog_summary_df = data[[date]].copy(deep=True)
    # return None and 0 if no data
    if prog_summary_df.empty:
        return (
            0,
            0,
            0,
            0,
        )
    # check if date column is datetime
    # try convertting to datetime
    # and raise error if conversion fails
    if not pd.api.types.is_datetime64_any_dtype(prog_summary_df[date]):
        prog_summary_df[date] = pd.to_datetime(prog_summary_df[date], errors="coerce")
        if not pd.api.types.is_datetime64_any_dtype(prog_summary_df[date]):
            raise ValueError(f"Column {date} is not a datetime column")

    # drop missing date
    prog_summary_df = prog_summary_df.dropna(subset=[date])
    # dataset is empty after dropping missing date return None
    if prog_summary_df.empty:
        return (
            0,
            0,
            0,
            0,
        )
    progress = (prog_summary_df.shape[0] / target) * 100 if target else 0
    average_submission_per_day = prog_summary_df[date].dt.date.value_counts().mean()
    prog_summary_df["week"] = prog_summary_df[date].dt.to_period("W").dt.to_timestamp()
    average_submission_per_week = prog_summary_df.groupby("week").size().mean()
    prog_summary_df["month"] = prog_summary_df[date].dt.to_period("M").dt.to_timestamp()
    average_submission_per_month = prog_summary_df.groupby("month").size().mean()

    return (
        progress,
        average_submission_per_day,
        average_submission_per_week,
        average_submission_per_month,
    )


@st.cache_data
def compute_summary_progress_by_col(
    data: pd.DataFrame,
    date: str,
    progress_by_col: str,
    progress_time_period: str,
) -> tuple:
    """
    Compute values for summary progress by column

    Parameters
    ----------
    data : pd.DataFrame
            The survey data

    date : str
            The date column in the survey data

    progress_by_col : str
            The column to compute progress by

    progress_time_period : str
            The time period to compute progress by

    Returns
    -------
    pd.DataFrame
            A DataFrame containing the summary values

    """
    if progress_time_period == "Auto":
        total_submissions = data.shape[0]
        if total_submissions > 0:
            if total_submissions < 20:
                progress_time_period_use = "Daily"
            elif total_submissions < 140:
                progress_time_period_use = "Weekly"
            else:
                progress_time_period_use = "Monthly"
    else:
        progress_time_period_use = progress_time_period

    progress_data = data[[date, progress_by_col]].copy(deep=True)
    # return None and 0 if no data
    if progress_data.empty:
        return (
            pd.DataFrame(),
            0,
            0,
            [],
        )
    # check if date column is datetime
    # try convertting to datetime
    # and raise error if conversion fails
    if not pd.api.types.is_datetime64_any_dtype(progress_data[date]):
        progress_data[date] = pd.to_datetime(progress_data[date], errors="coerce")
        if not pd.api.types.is_datetime64_any_dtype(progress_data[date]):
            raise ValueError(f"Column {date} is not a datetime column")

    progress_data["time period"] = data[date].dt.to_period("D").dt.to_timestamp()
    progress_data = (
        progress_data.groupby(["time period", progress_by_col])
        .size()
        .reset_index(name="count")
    )

    if progress_time_period_use == "Weekly":
        progress_data["time period"] = (
            progress_data["time period"].dt.to_period("W").dt.to_timestamp()
        )
        progress_data = (
            progress_data.groupby(["time period", progress_by_col])
            .sum("count")
            .reset_index()
        )
    elif progress_time_period_use == "Monthly":
        progress_data["time period"] = (
            progress_data["time period"].dt.to_period("M").dt.to_timestamp()
        )
        progress_data = (
            progress_data.groupby(["time period", progress_by_col])
            .sum("count")
            .reset_index()
        )

    progress_data["time period"] = progress_data["time period"].dt.date
    progress_data = progress_data.pivot(
        index=progress_by_col, columns="time period", values="count"
    ).fillna(0)

    vmin_val = progress_data.min().min()
    vmax_val = progress_data.max().max()

    format_cols = progress_data.columns

    return progress_data, vmin_val, vmax_val, format_cols


def summary_progress(
    data: pd.DataFrame,
    date: str,
    setting_file: str,
    target: int | None = None,
) -> None:
    """
    Generates a summary progress report for the survey data

    Parameters
    ----------
    data : pd.DataFrame
            The survey data

    enumerator : str
            The enumerator column in the survey data

    Returns
    -------
    None
    """
    st.write("---")
    st.markdown("## Progress")
    if not date:
        st.info(
            "Progress section requires a date column to be selected. go to the :material/settings: settings section above."
        )
        return

    (
        progress,
        average_submission_per_day,
        average_submission_per_week,
        average_submission_per_month,
    ) = compute_summary_progress(
        data=data,
        date=date,
        target=target,
    )

    mc1, mc2, mc3, mc4 = st.columns(spec=4, border=True)
    with mc1:
        st.write("Submission progress")
        if not target:
            st.info("Target not set. Progress cannot be computed.")
        else:
            sp1, sp2 = st.columns([0.80, 0.20])
            sp1.progress(value=int(progress))
            sp2.write(f"{progress:.2f}%")
    mc2.metric(
        label="Average submissions per day",
        value=f"{average_submission_per_day:,.2f}",
        help="Average number of submissions per day",
    )
    mc3.metric(
        label="Average submissions per week",
        value=f"{average_submission_per_week:,.2f}",
        help="Average number of submissions per week",
    )
    mc4.metric(
        label="Average submissions per month",
        value=f"{average_submission_per_month:,.2f}",
        help="Average number of submissions per month",
    )

    # load default settings if default values exist in setting_file
    default_settings = load_check_settings(setting_file, "summary") or {}

    # progress by column
    pc1, _ = st.columns([0.3, 0.7])
    with pc1:
        progress_by_col = default_settings.get("progress_by_col", None)
        progress_options = data.columns.tolist()
        progress_options.remove(date)
        progress_col_index = (
            progress_options.index(progress_by_col) if progress_by_col else None
        )
        progress_by_col = st.selectbox(
            label="Progress by",
            options=progress_options,
            index=progress_col_index,
            key="progress_by_col_key",
            help="Select a column to compute progress by",
            on_change=trigger_save,
            kwargs={"state_name": "progress_by_col"},
        )
        if "progress_by_col" in st.session_state and st.session_state.progress_by_col:
            save_check_settings(
                settings_file=setting_file,
                check_name="summary",
                check_settings={"progress_by_col": progress_by_col},
            )
            st.session_state.progress_by_col = False

    if progress_by_col:
        _, pil1 = st.columns([0.80, 0.20])
        with pil1:
            progress_time_period = default_settings.get("progress_time_period", None)
            progress_time_period = st.pills(
                label="Progress time period",
                options=["Auto", "Daily", "Weekly", "Monthly"],
                default=progress_time_period if progress_time_period else "Auto",
                help="Select a time period to compute progress by",
                key="progress_time_period",
            )

            if progress_time_period:
                save_check_settings(
                    settings_file=setting_file,
                    check_name="summary",
                    check_settings={
                        "progress_time_period": progress_time_period,
                    },
                )

        progress_data, vmin_val, vmax_val, format_cols = (
            compute_summary_progress_by_col(
                data=data,
                date=date,
                progress_by_col=progress_by_col,
                progress_time_period=progress_time_period,
            )
        )

        cmap = sns.light_palette("pink", as_cmap=True)

        st.dataframe(
            progress_data.style.format(
                subset=format_cols, precision=0
            ).background_gradient(
                subset=format_cols, cmap=cmap, axis=1, vmin=vmin_val, vmax=vmax_val
            ),
            use_container_width=True,
        )


@st.cache_data
def compute_summary_data_summary(data: pd.DataFrame) -> tuple:
    """
    Compute values for summary data summary

    Parameters
    ----------
    data : pd.DataFrame
            The survey data

    Returns
    -------
    tuple
            A tuple containing the summary values

    """
    num_str_cols = data.select_dtypes(include=["object"]).shape[1]
    num_num_cols = data.select_dtypes(include=["number"]).shape[1]
    num_date_cols = data.select_dtypes(include=["datetime"]).shape[1]
    col_count = data.shape[1]

    return num_str_cols, num_num_cols, num_date_cols, col_count


def summary_data_summary(data: pd.DataFrame) -> None:
    """
    Generates summary details of for the survey data

    Parameters
    ----------
    data : pd.DataFrame
            The survey data

    Returns
    -------
    None
    """
    st.write("---")
    st.markdown("## Data Summary")

    num_str_cols, num_num_cols, num_date_cols, col_count = compute_summary_data_summary(
        data=data
    )

    ds1, ds2, ds3, ds4 = st.columns(spec=4, border=True)
    ds1.metric(
        label="String Columns",
        value=f"{num_str_cols:,}",
        help="Number of string columns",
    )
    ds2.metric(
        label="Numeric Columns",
        value=f"{num_num_cols:,}",
        help="Number of numeric columns",
    )
    ds3.metric(
        label="Date Columns", value=f"{num_date_cols:,}", help="Number of date columns"
    )
    ds4.metric(
        label="Total Columns", value=f"{col_count:,}", help="Total number of columns"
    )


@st.cache_data
def compute_summary_data_quality(data: pd.DataFrame, survey_id: str | None) -> tuple:
    """
    Compute values for summary data quality

    Parameters
    ----------
    data : pd.DataFrame
            The survey data

    survey_id : str | None
            The survey ID column in the survey data

    Returns
    -------
    tuple
            A tuple containing the summary values

    """
    if survey_id:
        perc_duplicates = (
            data.duplicated(subset=[survey_id]).mean() * 100 if survey_id else 0
        )
    else:
        perc_duplicates = None
    perc_outliers = 0
    perc_missing = data.isnull().mean().mean() * 100
    perc_back_check_error_rate = 0

    return perc_duplicates, perc_outliers, perc_missing, perc_back_check_error_rate


def summary_data_quality(data: pd.DataFrame, survey_id: str | None) -> None:
    """
    Generates a summary report for the survey data

    Parameters
    ----------
    data : pd.DataFrame
            The survey data

    Returns
    -------
    None
    """
    st.write("---")
    st.markdown("## Data Quality")

    perc_duplicates, perc_outliers, perc_missing, perc_back_check_error_rate = (
        compute_summary_data_quality(
            data=data,
            survey_id=survey_id,
        )
    )

    if survey_id:
        perc_duplicates_chart = donut_chart2(
            actual_value=perc_duplicates,
        )
        plt.close(perc_duplicates_chart)
    perc_outliers_chart = donut_chart2(
        actual_value=perc_outliers,
    )
    plt.close(perc_outliers_chart)
    perc_missing_chart = donut_chart2(
        actual_value=perc_missing,
    )
    plt.close(perc_missing_chart)
    perc_back_check_error_rate_chart = donut_chart2(
        actual_value=perc_back_check_error_rate,
    )

    dq1, dq2, dq3, dq4 = st.columns(spec=4, border=True)
    with dq1:
        if perc_duplicates:
            st.markdown(f"**% of duplicates values on {survey_id}**")
            st.pyplot(perc_duplicates_chart)
        else:
            st.markdown("**% of duplicates values ID Column**")
            st.info(
                "Percentage of duplicate values requires a survey ID column to be selected. Go to the :material/settings: settings section above."
            )
    with dq2:
        st.markdown("**% of values flagged as outliers**")
        st.pyplot(perc_outliers_chart)
    with dq3:
        st.markdown("**% of missing values in survey dataset**")
        st.pyplot(perc_missing_chart)
    with dq4:
        st.markdown("**Back check error rate**")
        st.pyplot(perc_back_check_error_rate_chart)


def summary_report(
    project_id: str, data: pd.DataFrame, setting_file: str, page_num: int
) -> None:
    """
    Generates a summary report for the survey data

    Parameters
    ----------
    data : pd.DataFrame
            The survey data

    settings : dict
            The settings for the summary report

    Returns
    -------
    None
    """
    date, target, survey_id = summary_settings(project_id, data, setting_file, page_num)
    summary_data_summary(data=data)
    summary_submissions(
        data=data,
        date=date,
    )
    summary_progress(data=data, date=date, target=target, setting_file=setting_file)
    summary_data_quality(data=data, survey_id=survey_id)
