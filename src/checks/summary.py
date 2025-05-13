import os

import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import seaborn as sns
import streamlit as st
from millify import millify, prettify

from src.utils import (
    donut_chart2,
    load_check_settings,
    save_check_settings,
    trigger_save,
)


@st.cache_data
def load_default_settings(setting_file: str, page_num: int) -> tuple:
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
    if setting_file and os.path.exists(setting_file):
        default_settings = load_check_settings(setting_file, "summary") or {}
    else:
        default_settings = {}

    default_date = default_settings.get(
        "date", st.session_state["config_pages"]["Survey Date"][page_num - 1]
    )
    default_enumerator = default_settings.get(
        "enumerator", st.session_state["config_pages"]["Enumerator"][page_num - 1]
    )
    default_target = default_settings.get("target", None)
    default_survey_id = default_settings.get(
        "survey_id", st.session_state["config_pages"]["Survey ID"][page_num - 1]
    )

    return default_date, default_enumerator, default_target, default_survey_id


# define function to create summary report
def summary_settings(data: pd.DataFrame, setting_file: str, page_num) -> tuple:
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

        survey_cols = data.columns

        st.write("---")
        st.markdown("### Select columns to include in summary report")

        default_date, default_enumerator, default_target, default_survey_id = (
            load_default_settings(setting_file=setting_file, page_num=page_num)
        )
        with st.container(border=True):
            sc1, sc2, sc3 = st.columns(spec=3)

            with sc1:
                default_date_index = (
                    survey_cols.get_loc(default_date) if default_date else 0
                )
                date = st.selectbox(
                    label="Date",
                    options=survey_cols,
                    help="Column containing survey date",
                    index=default_date_index,
                    key="date_summary",
                )

            with sc2:
                default_enumerator_index = (
                    survey_cols.get_loc(default_enumerator) if default_enumerator else 0
                )
                enumerator = st.selectbox(
                    label="Enumerator",
                    options=survey_cols,
                    index=default_enumerator_index,
                    key="enumerator_summary",
                )

            with sc3:
                default_survey_id_index = (
                    survey_cols.get_loc(default_survey_id) if default_survey_id else 0
                )
                survey_id = st.selectbox(
                    label="Survey ID",
                    options=survey_cols,
                    help="Column containing survey ID",
                    index=default_survey_id_index,
                    key="survey_id_summary",
                )

            st.write("---")
            tc1, tc2 = st.columns([0.4, 0.6])
            tc1.markdown("##### Target number of interviews")
            with tc2:
                target = st.number_input(
                    label="Total goal",
                    min_value=0,
                    value=default_target,
                    help="Total number of interviews expected",
                    label_visibility="collapsed",
                    key="total_goal_summary",
                )

        # define a save settings button
        st.button(
            label="Save settings",
            on_click=save_check_settings,
            key="save_summary_settings",
            kwargs={
                "settings_file": setting_file,
                "check_name": "summary",
                "check_settings": {
                    "date": date,
                    "enumerator": enumerator,
                    "target": target,
                    "survey_id": survey_id,
                },
            },
        )
    return date, enumerator, target, survey_id or None


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
    first_submission_date = data[date].min()
    last_submission_date = data[date].max()

    submissions_today = data[data[date] == pd.Timestamp.now().normalize()].shape[0]
    submissions_yesterday = data[
        data[date] == pd.Timestamp.now().normalize() - pd.DateOffset(days=1)
    ].shape[0]
    submissions_this_week = data[
        data[date] >= pd.Timestamp.now().normalize() - pd.DateOffset(weeks=1)
    ].shape[0]
    submissions_last_week = data[
        (data[date] >= pd.Timestamp.now().normalize() - pd.DateOffset(weeks=2))
        & (data[date] < pd.Timestamp.now().normalize() - pd.DateOffset(weeks=1))
    ].shape[0]
    submissions_this_month = data[
        data[date] >= pd.Timestamp.now().normalize() - pd.DateOffset(months=1)
    ].shape[0]
    submissions_last_month = data[
        (data[date] >= pd.Timestamp.now().normalize() - pd.DateOffset(months=2))
        & (data[date] < pd.Timestamp.now().normalize() - pd.DateOffset(months=1))
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

    data[date] = data[date].dt.date
    submissions_by_date = data.groupby(date).size().reset_index(name="submissions")

    return (
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
        ) = compute_summary_submissions(data, date)

        dc1, _, _, dc2 = st.columns(spec=4)
        dc1.metric(
            label="First Submission",
            value=str(first_submission_date.date()),
            help="Date of the first submission",
        )
        dc2.metric(
            label="Last Submission",
            value=str(last_submission_date.date()),
            help="Date of the last submission",
        )

        mc1, mc2, mc3, mc4 = st.columns(spec=4, border=True)

        mc1.metric(
            label="Today",
            value=submissions_today,
            delta=f"{prettify(millify(submissions_today_delta, precision=2))}%",
            help="Number of submissions today. Delta is the percentage change from yesterday.",
        )
        mc2.metric(
            label="This week",
            value=submissions_this_week,
            delta=f"{prettify(millify(submissions_this_week_delta, precision=2))}%",
            help="Number of submissions this week. Delta is the percentage change from last week.",
        )
        mc3.metric(
            label="This month",
            value=submissions_this_month,
            delta=f"{prettify(millify(submissions_this_month_delta, precision=2))}%",
            help="Number of submissions this month. Delta is the percentage change from last month",
        )
        mc4.metric(
            label="Total",
            value=f"{prettify(submissions_total)}",
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
        st.warning("Please select a date column to view submissions details")


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
    # compute progress values here if needed
    progress = (data.shape[0] / target) * 100 if target else 0
    average_submission_per_day = data[date].dt.date.value_counts().mean()
    data["week"] = data[date].dt.to_period("W").dt.to_timestamp()
    average_submission_per_week = data.groupby("week").size().mean()
    data["month"] = data[date].dt.to_period("M").dt.to_timestamp()
    average_submission_per_month = data.groupby("month").size().mean()

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

    progress_data = data[[date, progress_by_col]].copy()
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

    progress_data["trend"] = progress_data.apply(
        lambda col_val: ", ".join(map(str, col_val)), axis=1
    )
    format_cols = [col for col in progress_data.columns if col != "trend"]
    progress_data = progress_data[["trend"] + format_cols]

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
        sp1, sp2 = st.columns([0.80, 0.20])
        sp1.progress(value=int(progress))
        sp2.write(f"{progress:.2f}%")
    mc2.metric(
        label="Average submissions per day",
        value=f"{prettify(millify(average_submission_per_day, precision=2))}",
        help="Average number of submissions per day",
    )
    mc3.metric(
        label="Average submissions per week",
        value=f"{prettify(millify(average_submission_per_week, precision=2))}",
        help="Average number of submissions per week",
    )
    mc4.metric(
        label="Average submissions per month",
        value=f"{prettify(millify(average_submission_per_month, precision=2))}",
        help="Average number of submissions per month",
    )

    # load default settings if default values exist in setting_file
    default_settings = load_check_settings(setting_file, "summary") or {}

    # progress by column
    pc1, _ = st.columns([0.3, 0.7])
    with pc1:
        progress_by_col = default_settings.get("progress_by_col", None)
        progress_col_index = (
            data.columns.get_loc(progress_by_col) if progress_by_col else None
        )
        progress_options = data.columns.tolist()
        progress_options.remove(date)
        progress_by_col = st.selectbox(
            "Progress by",
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
            column_config={
                "trend": st.column_config.AreaChartColumn(
                    "Trend of submissions",
                    width="medium",
                    help="Trend of submissions over time",
                    y_min=vmin_val,
                    y_max=vmax_val,
                ),
            },
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
        label="String Columns", value=num_str_cols, help="Number of string columns"
    )
    ds2.metric(
        label="Numeric Columns", value=num_num_cols, help="Number of numeric columns"
    )
    ds3.metric(label="Date Columns", value=num_date_cols, help="Number of date columns")
    ds4.metric(label="Total Columns", value=col_count, help="Total number of columns")


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
    perc_duplicates = (
        data.duplicated(subset=[survey_id]).mean() * 100 if survey_id else 0
    )
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

    if survey_id:
        perc_duplicates, perc_outliers, perc_missing, perc_back_check_error_rate = (
            compute_summary_data_quality(
                data=data,
                survey_id=survey_id,
            )
        )

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
            st.markdown(f"**% of duplicates values on {survey_id}**")
            st.pyplot(perc_duplicates_chart)
        with dq2:
            st.markdown("**% of values in XX columns**")
            st.pyplot(perc_outliers_chart)
        with dq3:
            st.markdown("**% of missing values in survey dataset**")
            st.pyplot(perc_missing_chart)
        with dq4:
            st.markdown("**Back check error rate**")
            st.pyplot(perc_back_check_error_rate_chart)

    else:
        st.warning("Please select a survey ID column to view data quality details")


def summary_report(data: pd.DataFrame, setting_file: str, page_num: int) -> None:
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
    date, enumerator, target, survey_id = summary_settings(
        data=data, setting_file=setting_file, page_num=page_num
    )
    summary_submissions(
        data=data[[date]],
        date=date,
    )
    summary_progress(data=data, date=date, target=target, setting_file=setting_file)
    summary_data_summary(data=data)
    summary_data_quality(data=data, survey_id=survey_id)
