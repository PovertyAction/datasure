import pandas as pd
import plotly.express as px
import streamlit as st
from millify import millify


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
            survey_id = st.selectbox(  # noqa: F841
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
        total_goal = st.number_input(  # noqa: F841
            label="Total goal",
            min_value=0,
            help="Total number of interviews expected",
            label_visibility="collapsed",
            key="total_goal_summary",
        )

        # define a save settings button
        save_settings = st.button("Save settings")  # noqa: F841

    return date, enumerator


def summary_submissions(data: pd.DataFrame, date: str = None) -> None:  # noqa: RUF013
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
            delta=millify(submissions_today_delta, precision=2),
            help="Number of submissions today. Delta is the percentage change from yesterday.",
        )
        mc2.metric(
            label="This week",
            value=submissions_this_week,
            delta=millify(submissions_this_week_delta, precision=2),
            help="Number of submissions this week. Delta is the percentage change from last week.",
        )
        mc3.metric(
            label="This month",
            value=submissions_this_month,
            delta=millify(submissions_this_month_delta, precision=2),
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

    date, _ = summary_settings(data=data, setting_file=setting_file, page_num=page_num)
    summary_submissions(
        data=data, date=st.session_state["config_pages"]["Survey Date"][page_num - 1]
    )
