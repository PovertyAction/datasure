import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import seaborn as sns
import streamlit as st
from millify import millify

from src.utils import donut_chart2


# define function to create summary report
def summary_settings(data: pd.DataFrame, setting_file: str, page_num) -> tuple:
    """
    Generates a summary report for the survey data

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

        meta_col, enum_col, agg_col = st.columns(spec=3, border=True)

        with meta_col:
            duration = st.selectbox(  # noqa: F841
                label="Duration",
                options=survey_cols,
                help="Column containing survey duration",
                index=None,
                key="duration_summary",
            )

            # get date column name from dataset & get index
            default_date = st.session_state["config_pages"]["Survey Date"][page_num - 1]
            default_date_index = survey_cols.get_loc(default_date)
            date = st.selectbox(
                label="Date",
                options=survey_cols,
                help="Column containing survey date",
                index=default_date_index,
                key="date_summary",
            )

            formversion = st.selectbox(  # noqa: F841
                label="Form Version",
                options=survey_cols,
                help="Column containing survey form version",
                index=None,
                key="formversion_summary",
            )

        with enum_col:
            by = st.selectbox(  # noqa: F841
                label="Group by",
                options=survey_cols,
                help="Column to group summary report by by",
                index=None,
                key="by_summary",
            )

            # get enumerator column name from dataset & get index
            default_enumerator = st.session_state["config_pages"]["Enumerator"][
                page_num - 1
            ]
            default_enumerator_index = survey_cols.get_loc(default_enumerator)
            enumerator = st.selectbox(
                label="Enumerator",
                options=survey_cols,
                index=default_enumerator_index,
                key="enumerator_summary",
            )
            team = st.selectbox("Team", options=survey_cols, index=None)  # noqa: F841

        with agg_col:
            # get survey id column name from dataset & get index
            default_survey_id = st.session_state["config_pages"]["Survey ID"][
                page_num - 1
            ]
            default_survey_id_index = survey_cols.get_loc(default_survey_id)
            survey_id = st.selectbox(
                label="Survey ID",
                options=survey_cols,
                help="Column containing survey ID",
                index=default_survey_id_index,
                key="survey_id_summary",
            )

            consent = st.selectbox(
                label="Consent",
                options=survey_cols,
                help="Column containing survey consent",
                index=None,
                key="consent_summary",
            )

            if consent:
                consent_options = data[consent].unique().tolist()
                consent_val = st.multiselect(  # noqa: F841
                    label="Consent value(s)",
                    options=consent_options,
                    help="Value(s) indicating valid consent",
                    key="consent_val_summary",
                )

            outcome = st.selectbox(
                label="Outcome",
                options=survey_cols,
                help="Column containing survey outcome",
                index=None,
            )
            if outcome:
                outcome_options = data[outcome].unique().tolist()
                outcome_val = st.multiselect(  # noqa: F841
                    label="Outcome value(s)",
                    options=outcome_options,
                    help="Value(s) indicating completed survey",
                    key="outcome_val_summary",
                )

        st.write("---")
        st.markdown("### Additional Options")

        # number of interviews expected
        st.markdown("##### Target number of interviews")
        target = st.number_input(
            label="Total goal",
            min_value=0,
            help="Total number of interviews expected",
            label_visibility="collapsed",
            key="total_goal_summary",
        )

        # define a save settings button
        save_settings = st.button("Save settings")  # noqa: F841

    return date, enumerator, target, survey_id or None


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
        first_submission_date = data[date].min()
        last_submission_date = data[date].max()

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
            ((submissions_this_week - submissions_last_week) / submissions_last_week)
            * 100
            if submissions_last_week > 0
            else 0
        )
        submissions_this_month_delta = (
            ((submissions_this_month - submissions_last_month) / submissions_last_month)
            * 100
            if submissions_last_month > 0
            else 0
        )

        mc1.metric(
            label="Today",
            value=submissions_today,
            delta=f"{millify(submissions_today_delta, precision=2)}%",
            help="Number of submissions today. Delta is the percentage change from yesterday.",
        )
        mc2.metric(
            label="This week",
            value=submissions_this_week,
            delta=f"{millify(submissions_this_week_delta, precision=2)}%",
            help="Number of submissions this week. Delta is the percentage change from last week.",
        )
        mc3.metric(
            label="This month",
            value=submissions_this_month,
            delta=f"{millify(submissions_this_month_delta, precision=2)}%",
            help="Number of submissions this month. Delta is the percentage change from last month",
        )
        mc4.metric(
            label="Total", value=submissions_total, help="Total number of submissions"
        )

        submissions_by_date = data.groupby(date).size().reset_index(name="submissions")
        fig = px.area(
            submissions_by_date,
            x=date,
            y="submissions",
            title="Submissions by date",
            color_discrete_sequence=["#e8848b"],
        )
        fig.update_layout(width=1000, height=500)
        fig.update_yaxes(tick0=0, dtick=1)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Please select a date column to view submissions details")


def summary_progress(
    data: pd.DataFrame,
    date: str,
    enumerator: str | None = None,
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

    progress = (data.shape[0] / target) * 100 if target else 0
    average_submission_per_day = data[date].value_counts().mean()
    data["week"] = data[date].dt.to_period("W").dt.to_timestamp()
    average_submission_per_week = data.groupby("week").size().mean()
    data["month"] = data[date].dt.to_period("M").dt.to_timestamp()
    average_submission_per_month = data.groupby("month").size().mean()

    mc1, mc2, mc3, mc4 = st.columns(spec=4, border=True)
    with mc1:
        st.write("Submission progress")
        sp1, sp2 = st.columns([0.80, 0.20])
        sp1.progress(value=int(progress))
        sp2.write(f"{progress:.2f}%")
    mc2.metric(
        label="Average submissions per day",
        value=f"{average_submission_per_day:.2f}",
        help="Average number of submissions per day",
    )
    mc3.metric(
        label="Average submissions per week",
        value=f"{average_submission_per_week:.2f}",
        help="Average number of submissions per week",
    )
    mc4.metric(
        label="Average submissions per month",
        value=f"{average_submission_per_month:.2f}",
        help="Average number of submissions per month",
    )

    # progress by column
    pc1, _ = st.columns([0.3, 0.7])
    with pc1:
        progress_options = data.columns.tolist()
        progress_options.remove(date)
        progress_by_col = st.selectbox(
            "Progress by", options=progress_options, index=None, key="progress_by_col"
        )

    if progress_by_col:
        _, pil1 = st.columns([0.80, 0.20])
        with pil1:
            progress_time_period = st.pills(
                label="Progress time period",
                options=["Auto", "Daily", "Weekly", "Monthly"],
                default="Auto",
                key="progress_time_period",
            )

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

        cmap = sns.light_palette("pink", as_cmap=True)
        vmin_val = progress_data.min().min()
        vmax_val = progress_data.max().max()

        progress_data["trend"] = progress_data.apply(
            lambda col_val: ", ".join(map(str, col_val)), axis=1
        )
        format_cols = [col for col in progress_data.columns if col != "trend"]
        progress_data = progress_data[["trend"] + format_cols]

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

    num_str_cols = data.select_dtypes(include=["object"]).shape[1]
    num_num_cols = data.select_dtypes(include=["number"]).shape[1]
    num_date_cols = data.select_dtypes(include=["datetime"]).shape[1]
    col_count = data.shape[1]

    ds1, ds2, ds3, ds4 = st.columns(spec=4, border=True)
    ds1.metric(
        label="String Columns", value=num_str_cols, help="Number of string columns"
    )
    ds2.metric(
        label="Numeric Columns", value=num_num_cols, help="Number of numeric columns"
    )
    ds3.metric(label="Date Columns", value=num_date_cols, help="Number of date columns")
    ds4.metric(label="Total Columns", value=col_count, help="Total number of columns")


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
        # calculate number of duplicates in survey id column
        perc_duplicates = data.duplicated(subset=[survey_id]).mean() * 100
        perc_outliers = 0
        perc_missing = data.isnull().mean().mean() * 100
        perc_back_check_error_rate = 0

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


def summary_report(data: pd.DataFrame, page_num: int) -> None:
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
    page_name = st.session_state.config_pages["Page Name"][page_num - 1]
    setting_file = f"cache/settings/pyDMS_hfc_settings_{page_name}.json"

    date, enumerator, target, survey_id = summary_settings(
        data=data, setting_file=setting_file, page_num=page_num
    )
    summary_submissions(
        data=data[[date]],
        date=date,
    )
    summary_progress(data=data, date=date, enumerator=enumerator, target=target)
    summary_data_summary(data=data)
    summary_data_quality(data=data, survey_id=survey_id)
