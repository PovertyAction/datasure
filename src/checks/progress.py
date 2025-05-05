import io
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.utils import (
    donut_chart2,
    load_check_settings,
    save_check_settings,
)


def fig_to_streamlit(fig):
    """Convert a matplotlib figure to a format Streamlit can display"""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    buf.seek(0)
    return buf


#### Survey Progress ###
@st.cache_data
def load_default_progress_settings(setting_file: str, page_num: int) -> tuple:
    """Load default settings for progress report

    PARAMS:
    -------

    setting_file: str : path to the settings file
    page_num: int : page number

    Returns
    -------
    tuple : default settings for progress report
    """
    # load default settings in the following order:
    # - if settings file exists, load settings from file
    # - if settings file does not exist, load default settings from config
    if setting_file and os.path.exists(setting_file):
        default_settings = load_check_settings(setting_file, "progress_report")
        if default_settings:
            default_survey_id, default_survey_key, default_enumerator, default_date = (
                default_settings.get("survey_id"),
                default_settings.get("survey_key"),
                default_settings.get("enumerator"),
                default_settings.get("date"),
            )
            default_team, default_groupby, default_target = (
                default_settings.get("team"),
                default_settings.get("groupby"),
                default_settings.get("target"),
            )
        else:
            default_survey_id, default_survey_key, default_enumerator, default_date = (
                st.session_state["config_pages"]["Survey ID"][page_num - 1],
                st.session_state["config_pages"]["Survey KEY"][page_num - 1],
                st.session_state["config_pages"]["Enumerator"][page_num - 1],
                st.session_state["config_pages"]["Survey Date"][page_num - 1],
            )
            default_team, default_groupby, default_target = (
                None,
                None,
                None,
            )
    else:
        default_survey_id, default_survey_key, default_enumerator, default_date = (
            st.session_state["config_pages"]["Survey ID"][page_num - 1],
            st.session_state["config_pages"]["Survey KEY"][page_num - 1],
            st.session_state["config_pages"]["Enumerator"][page_num - 1],
            st.session_state["config_pages"]["Survey Date"][page_num - 1],
        )
        default_team, default_groupby, default_target = (
            None,
            None,
            None,
        )

    return (
        default_survey_id,
        default_survey_key,
        default_enumerator,
        default_date,
        default_team,
        default_groupby,
        default_target,
    )


def progress_report_settings(
    data: pd.DataFrame,
    setting_file: str,
    page_num: int,
) -> tuple:
    """
    Get settings for progress report

    Parameters
    ----------
    data: pd.DataFrame : data to display
    setting_file: str : path to the settings file
    page_num: int : page number

    Returns
    -------
    tuple : settings for progress report
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for progress report")

        (
            default_survey_id,
            default_survey_key,
            default_enumerator,
            default_date,
            default_team,
            default_groupby,
            default_target,
        ) = load_default_progress_settings(setting_file=setting_file, page_num=page_num)

        survey_cols = data.columns

        uc1, uc2, uc3 = st.columns(3)
        with uc1:
            default_survey_id_index = survey_cols.get_loc(default_survey_id)
            st.markdown("### Select survey ID column")
            survey_id = st.selectbox(
                "Survey ID",
                options=survey_cols,
                help="Column containing survey ID",
                key="surveyid_progress_settings",
                index=default_survey_id_index,
            )
        with uc2:
            default_survey_key_index = survey_cols.get_loc(default_survey_key)
            st.markdown("### Select survey key column")
            survey_key = st.selectbox(
                "Survey Key",
                options=survey_cols,
                help="Column containing survey key",
                key="surveykey_progress_settings",
                index=default_survey_key_index,
            )
        with uc3:
            default_date_index = survey_cols.get_loc(default_date)
            st.markdown("### Select survey date column")
            date = st.selectbox(
                label="Date",
                options=survey_cols,
                help="Column containing survey date",
                key="date_progress_settings",
                index=default_date_index,
            )
        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            default_enumerator_index = survey_cols.get_loc(default_enumerator)
            st.markdown("### Select enumerator column")
            enumerator = st.selectbox(
                "Enumerator",
                options=survey_cols,
                help="Column containing survey enumerator",
                key="enumerator_progress_settings",
                index=default_enumerator_index,
            )
        with bc2:
            default_team_index = (
                survey_cols.get_loc(default_team) if default_team else None
            )
            st.markdown("### Select team column")
            team = st.selectbox(
                "Team",
                options=survey_cols,
                help="Column containing survey team",
                key="team_progress_settings",
                index=default_team_index,
            )
        with bc3:
            default_groupby_index = (
                survey_cols.get_loc(default_groupby) if default_groupby else None
            )
            st.markdown("### Select group by column")
            groupby = st.selectbox(
                "Group by",
                options=survey_cols,
                help="Column to group summary report by",
                key="groupby_progress_settings",
                index=default_groupby_index,
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
                key="total_goal_progress_settings",
            )

        # add button for saving settings
        st.write("---")
        st.write("Save settings")
        st.button(
            label="Save settings",
            key="save_settings_progress",
            on_click=save_check_settings,
            args=(
                setting_file,
                "progress",
                {
                    "survey_id": survey_id,
                    "survey_key": survey_key,
                    "date": date,
                    "enumerator": enumerator,
                    "team": team,
                    "groupby": groupby,
                    "target": target,
                },
            ),
        )

    return survey_id, survey_key, date, enumerator, team, groupby, target


@st.cache_data
def compute_progress_summary(data: pd.DataFrame, target: int) -> tuple:
    """Compute summary statistics for progress report

    Parameters
    ----------
    data: pd.DataFrame : data to display
    target: int : target number of interviews

    Returns
    -------
    tuple : summary statistics for progress report
    - total_submitted: int : total number of submitted interviews
    - total_goal: int : total number of interviews expected
    - percentage of completed interviews
    """
    total_submitted = len(data)
    if target and target > 0:
        percentage_completed = (total_submitted / target) * 100
    else:
        percentage_completed = 0

    return total_submitted, target, percentage_completed


def display_progress_summary(data: pd.DataFrame, target: int) -> None:
    """Display summary statistics for progress report

    Parameters
    ----------
    total_submitted: int : total number of submitted interviews
    target: int : target number of interviews
    percentage_completed: float : percentage of completed interviews

    Returns
    -------
    None
    """
    total_submitted, target, percentage_completed = compute_progress_summary(
        data=data, target=target
    )
    mc1, mc2, mc3 = st.columns([0.5, 0.25, 0.25], border=True)
    with mc1:
        st.write("Submission progress")
        sp1, sp2 = st.columns([0.9, 0.1])
        # sp1.write(f"{percentage_completed:.2f}%")
        sp1.progress(value=percentage_completed / 100)
        sp2.write(f"{percentage_completed:.2f}%")
    mc2.metric(
        label="Target Interviews",
        value=target if (target and target > 0) else "N/A",
    )
    mc3.metric(label="Total Submitted Interviews", value=total_submitted)


@st.cache_data
def compute_progress_chart(
    data: pd.DataFrame,
    consent_col: str | None,
    consent_vals: list | None,
    outcome_col: str | None,
    outcome_vals: list | None,
) -> tuple:
    """Compute progress chart statistics

    Parameters
    ----------
    data: pd.DataFrame : dataset
    consent_col: str | None : column name for consent
    consent_vals: list | None : list of consent values
    outcome_col: str | None : column name for outcome
    outcome_vals: list | None : list of outcome values

    Returns
    -------
    tuple: progress chart statistics
    - consent_percentage: float : percentage of valid consents
    - completion_percentage: float : percentage of completed surveys
    """
    # count total valid consent. Count as valid consent if the value is in the
    # consent_vals list
    total_submitted = len(data)
    if consent_col and consent_vals:
        valid_consent_count = len(data[data[consent_col].isin(consent_vals)])
        consent_percentage = (
            (valid_consent_count / total_submitted) * 100 if total_submitted > 0 else 0
        )
    else:
        consent_percentage = 0

    if outcome_col and outcome_vals:
        # count total completed surveys. Count as completed if the value is in the
        # outcome_vals list
        completed_count = len(data[data[outcome_col].isin(outcome_vals)])
        completion_percentage = (
            (completed_count / total_submitted) * 100 if total_submitted > 0 else 0
        )
    else:
        completion_percentage = 0

    return consent_percentage, completion_percentage


def display_progress_chart(data: pd.DataFrame):
    """Display progress chart

    Parameters
    ----------
    data: pd.DataFrame : dataset

    Returns
    -------
    None
    """
    survey_cols = data.columns
    st.write("---")
    st.write("## Progress Chart")
    _, cc1, _, cc2, _ = st.columns([0.1, 0.35, 0.1, 0.35, 0.1])
    consent, consent_vals, outcome, outcome_vals = None, None, None, None
    with cc1, st.container(border=True):
        consent = st.selectbox(
            label="Select consent column",
            options=survey_cols,
            help="Column containing consent information",
            key="consent_progress_chart",
            index=None,
        )
        if consent:
            consent_vals = st.multiselect(
                label="Select consent values",
                options=data[consent].unique(),
                help="Values to consider as valid consent",
                key="consent_val_progress_chart",
            )
        else:
            st.warning("Please select a consent column first")
            consent_vals = None
    with cc2, st.container(border=True):
        outcome = st.selectbox(
            label="Select outcome column",
            options=survey_cols,
            help="Column containing outcome information",
            key="outcome_progress_chart",
            index=None,
        )
        if outcome:
            outcome_vals = st.multiselect(
                label="Select outcome values",
                options=data[outcome].unique(),
                help="Values to consider as completed surveys",
                key="outcome_val_progress_chart",
            )
        else:
            st.warning("Please select an outcome column first")
            outcome_vals = None
    consent_percentage, completion_percentage = compute_progress_chart(
        data=data,
        consent_col=consent,
        consent_vals=consent_vals,
        outcome_col=outcome,
        outcome_vals=outcome_vals,
    )

    perc_consent_chart = donut_chart2(
        actual_value=int(consent_percentage),
    )
    with cc1:
        st.markdown("**% consent**")
        st.pyplot(perc_consent_chart, use_container_width=True)

    perc_completion_chart = donut_chart2(
        actual_value=int(completion_percentage),
    )
    with cc2:
        st.markdown("**% completion**")
        st.pyplot(perc_completion_chart, use_container_width=True)


@st.cache_data
def compute_progress_overtime(
    data: pd.DataFrame, date: str, time_period: str, survey_id, enumerator: str
) -> tuple:
    """Compute progress over time

    Parameters
    ----------
    data: pd.DataFrame : dataset
    date_col: str : column name for date

    Returns
    -------
    pd.DataFrame : progress over time
    """
    # if time_period is day, week or month, create a new column with the time period
    if time_period == "Day":
        data["time_period"] = pd.to_datetime(data[date]).dt.date
    elif time_period == "Week":
        data["time_period"] = (
            pd.to_datetime(data[date]).dt.to_period("W").dt.start_time.dt.date
        )
    elif time_period == "Month":
        data["time_period"] = (
            pd.to_datetime(data[date]).dt.to_period("M").dt.start_time.dt.date
        )

    # group data by time period and count interviews and unique enumerators
    period_stats = (
        data.groupby("time_period")
        .agg(
            num_interviews=pd.NamedAgg(column=survey_id, aggfunc="count"),
            num_enumerators=pd.NamedAgg(column=enumerator, aggfunc="nunique"),
        )
        .reset_index()
    )
    # Calculate the average number of interviews
    average_interviews = period_stats["num_interviews"].mean()

    return period_stats, average_interviews


def display_progress_overtime(
    data: pd.DataFrame, date: str, enumerator: str, survey_id
) -> None:
    """Display progress over time

    Parameters
    ----------
    data: pd.DataFrame : dataset
    date_col: str : column name for date
    enumerator: str : column name for enumerator

    Returns
    -------
    None
    """
    st.write("---")
    st.write("## Progress Over Time")
    time_period = st.radio(
        label="Select time period:",
        options=["Day", "Week", "Month"],
        horizontal=True,
        key="time_period_progress_overtime",
        help="Select time period for progress report",
    )

    period_stats, average_interviews = compute_progress_overtime(
        data=data,
        date=date,
        enumerator=enumerator,
        time_period=time_period,
        survey_id=survey_id,
    )

    # Create the figure
    fig = go.Figure()

    # Add bar plot for interviews per time period with enumerator info in hover
    fig.add_trace(
        go.Bar(
            x=period_stats["time_period"],
            y=period_stats["num_interviews"],
            name="Interviews",
            marker_color="#2C5F2D",  # Dark green color
            hovertemplate="<b>%{x}</b><br>"
            + "Interviews: %{y}<br>"
            + "Enumerators: %{customdata}<extra></extra>",
            customdata=period_stats["num_enumerators"],  # Add enumerator data for hover
        )
    )

    # Add average interview line
    fig.add_trace(
        go.Scatter(
            x=[period_stats["time_period"].min(), period_stats["time_period"].max()],
            y=[average_interviews, average_interviews],
            mode="lines",
            name=f"Avg Interviews: {average_interviews:.2f}",
            line=dict(color="#4D5E90", width=1, dash="dash"),
        )
    )

    # Update layout
    fig.update_layout(
        title=f"Interview Progress by {time_period}",
        title_x=0,
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=400,
        margin=dict(t=50, b=50, l=50, r=50),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(
            title=time_period,
            showgrid=False,
            gridcolor="lightgrey",
            tickangle=-45,
            type="category",
        ),
        yaxis=dict(
            title_text="Number of Interviews",
            showgrid=False,
            gridcolor="lightgrey",
            zeroline=False,
        ),
    )

    st.plotly_chart(fig, theme=None, use_container_width=True)


def progress_report(data: pd.DataFrame, setting_file: str, page_num: int) -> None:
    """Display progress report

    Parameters
    ----------
    data: pd.DataFrame : data to display
    page_num: int : page number

    Returns
    -------
    None
    """
    survey_id, survey_key, date, enumerator, team, groupby, target = (
        progress_report_settings(
            data=data, setting_file=setting_file, page_num=page_num
        )
    )
    display_progress_summary(
        data=data,
        target=target,
    )
    display_progress_chart(data=data)
    display_progress_overtime(
        data=data,
        date=date,
        enumerator=enumerator,
        survey_id=survey_id,
    )
