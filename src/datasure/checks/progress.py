import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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


#### Survey Progress ###
def load_default_progress_settings(
    project_id: str, setting_file: str, page_num: int
) -> tuple:
    """Load default settings for progress report

    PARAMS:
    -------

    setting_file: str : path to the settings file
    page_num: int : page number

    Returns
    -------
    tuple : default settings for progress report
    """
    # Get config page defaults
    _, _, _, config_survey_id, config_survey_date, config_enumerator, _, _ = (
        get_check_config_settings(
            project_id=project_id,
            page_row_index=page_num - 1,
        )
    )
    # load default settings in the following order:
    # - if settings file exists, load settings from file
    # - if settings file does not exist, load default settings from config
    if setting_file and os.path.exists(setting_file):
        default_settings = load_check_settings(setting_file, "progress") or {}
        summary_settings = load_check_settings(setting_file, "progress") or {}
    else:
        default_settings = {}
        summary_settings = {}

    default_survey_id, default_enumerator, default_date, default_target = (
        default_settings.get("survey_id", config_survey_id),
        default_settings.get("enumerator", config_enumerator),
        default_settings.get("date", config_survey_date),
        default_settings.get("target"),
    )

    # for default target, get the value in summary page if there is
    # no default for the progress page
    if not default_target:
        default_target = summary_settings.get("target")

    return (
        default_survey_id,
        default_enumerator,
        default_date,
        default_target,
    )


def progress_report_settings(
    project_id: str,
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
            default_enumerator,
            default_date,
            default_target,
        ) = load_default_progress_settings(project_id, setting_file, page_num)

        _, string_columns, numeric_columns, datetime_columns, _ = get_df_info(
            data, cols_only=True
        )

        id_enum_col_options = string_columns + numeric_columns
        uc1, uc2, uc3 = st.columns(3)
        with uc1:
            default_survey_id_index = (
                id_enum_col_options.index(default_survey_id)
                if default_survey_id and default_survey_id in id_enum_col_options
                else None
            )
            survey_id = st.selectbox(
                "Survey ID",
                options=id_enum_col_options,
                help="Column containing survey ID",
                key="surveyid_progress_settings",
                index=default_survey_id_index,
                on_change=trigger_save,
                kwargs=({"state_name": "progress_surveyid"}),
            )
            if (
                "progress_surveyid" in st.session_state
                and st.session_state.progress_surveyid
            ):
                save_check_settings(
                    settings_file=setting_file,
                    check_name="progress",
                    check_settings={"survey_id": survey_id},
                )
                st.session_state["progress_surveyid"] = False
        with uc2:
            default_date_index = (
                datetime_columns.index(default_date)
                if default_date and default_date in datetime_columns
                else None
            )
            date = st.selectbox(
                label="Date",
                options=datetime_columns,
                help="Column containing survey date",
                key="date_progress_settings",
                index=default_date_index,
                on_change=trigger_save,
                kwargs=({"state_name": "progress_date"}),
            )
            if "progress_date" in st.session_state and st.session_state.progress_date:
                save_check_settings(
                    settings_file=setting_file,
                    check_name="progress",
                    check_settings={"date": date},
                )
                st.session_state["progress_date"] = False
        with uc3:
            default_enumerator_index = (
                id_enum_col_options.index(default_enumerator)
                if default_enumerator and default_enumerator in id_enum_col_options
                else None
            )
            enumerator = st.selectbox(
                "Enumerator",
                options=id_enum_col_options,
                help="Column containing survey enumerator",
                key="enumerator_progress_settings",
                index=default_enumerator_index,
                on_change=trigger_save,
                kwargs=({"state_name": "progress_enumerator"}),
            )
            if (
                "progress_enumerator" in st.session_state
                and st.session_state.progress_enumerator
            ):
                save_check_settings(
                    settings_file=setting_file,
                    check_name="progress",
                    check_settings={"enumerator": enumerator},
                )
                st.session_state["progress_enumerator"] = False

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
                on_change=trigger_save,
                kwargs=({"state_name": "progress_total_goal"}),
            )
            if (
                "progress_total_goal" in st.session_state
                and st.session_state.progress_total_goal
            ):
                save_check_settings(
                    settings_file=setting_file,
                    check_name="progress",
                    check_settings={"target": target},
                )
                st.session_state["progress_total_goal"] = False

    return survey_id, date, enumerator, target


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
        if not target:
            sp1.info(
                "Target number of interviews is not set. Got to :material/settings: settings to set it."
            )
        else:
            sp1.progress(value=percentage_completed / 100)
            sp2.write(f"{percentage_completed:.2f}%")
    if not target:
        with mc2:
            st.write("Target Interviews")
            st.info(
                "Target number of interviews is not set. Got to :material/settings: settings to set it."
            )
    else:
        mc2.metric(
            label="Target Interviews",
            value=target if (target and target > 0) else "Invalid Target",
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


def display_progress_chart(data: pd.DataFrame, setting_file: str) -> None:
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
    st.write("## Consent and Completion Progress Chart")
    _, cc1, _, cc2, _ = st.columns([0.1, 0.35, 0.1, 0.35, 0.1])
    default_settings = (
        load_check_settings(settings_file=setting_file, check_name="progress") or {}
    )
    consent, consent_vals, outcome, outcome_vals = (
        default_settings.get("consent", None),
        default_settings.get("consent_vals", None),
        default_settings.get("outcome", None),
        default_settings.get("outcome_vals", None),
    )
    with cc1, st.container(border=True):
        consent_index = (
            survey_cols.get_loc(consent) if consent and consent in survey_cols else None
        )
        consent = st.selectbox(
            label="Select consent column",
            options=survey_cols,
            help="Column containing consent information",
            key="progress_consent_pie_chart",
            index=consent_index,
            on_change=trigger_save,
            kwargs=({"state_name": "progress_consent_pie_chart_save"}),
        )
        if (
            "progress_consent_pie_chart_save" in st.session_state
        ) and st.session_state.progress_consent_pie_chart_save:
            save_check_settings(
                settings_file=setting_file,
                check_name="progress",
                check_settings={"consent": consent},
            )
            st.session_state["progress_consent_pie_chart_save"] = False
        if consent:
            consent_val_options = data[consent].unique()
            if consent_vals and consent_vals in consent_val_options:
                default_consent_vals = consent_vals
            else:
                default_consent_vals = None
            consent_vals = st.multiselect(
                label="Select consent values",
                options=consent_val_options,
                help="Values to consider as valid consent",
                key="consent_vals_progress_chart",
                default=default_consent_vals,
                on_change=trigger_save,
                kwargs=({"state_name": "consent_vals_progress_chart_save"}),
            )
            if (
                "consent_vals_progress_chart_save" in st.session_state
            ) and st.session_state.consent_vals_progress_chart_save:
                save_check_settings(
                    settings_file=setting_file,
                    check_name="progress",
                    check_settings={"consent_vals": consent_vals},
                )
                st.session_state["consent_vals_progress_chart_save"] = False
        else:
            st.info(
                "Select consent column first and then select consent values to display the chart"
            )
            consent_vals = None
    with cc2, st.container(border=True):
        outcome_index = (
            survey_cols.get_loc(outcome) if outcome and outcome in survey_cols else None
        )
        outcome = st.selectbox(
            label="Select outcome column",
            options=survey_cols,
            help="Column containing outcome information",
            key="outcome_progress_chart",
            index=outcome_index,
            on_change=trigger_save,
            kwargs=({"state_name": "outcome_progress_chart_save"}),
        )
        if (
            "outcome_progress_chart_save" in st.session_state
        ) and st.session_state.outcome_progress_chart_save:
            save_check_settings(
                settings_file=setting_file,
                check_name="progress",
                check_settings={"outcome": outcome},
            )
            st.session_state["outcome_progress_chart_save"] = False
        if outcome:
            outcome_val_options = data[outcome].unique()
            if outcome_vals and outcome_vals in outcome_val_options:
                default_outcome_vals = outcome_vals
            else:
                default_outcome_vals = None
            outcome_vals = st.multiselect(
                label="Select outcome values",
                options=outcome_val_options,
                help="Values to consider as completed surveys",
                key="outcome_vals_progress_chart",
                default=default_outcome_vals,
                on_change=trigger_save,
                kwargs=({"state_name": "outcome_vals_progress_chart_save"}),
            )
            if (
                "outcome_vals_progress_chart_save" in st.session_state
            ) and st.session_state.outcome_vals_progress_chart_save:
                save_check_settings(
                    settings_file=setting_file,
                    check_name="progress",
                    check_settings={"outcome_vals": outcome_vals},
                )
                st.session_state["outcome_vals_progress_chart_save"] = False
        else:
            st.info(
                "Select outcome column first and then select outcome values to display the chart"
            )
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
    perc_completion_chart = donut_chart2(
        actual_value=int(completion_percentage),
    )
    with cc1:
        if consent and consent_vals:
            st.markdown("**% consent**")
            st.pyplot(perc_consent_chart, use_container_width=True)

    with cc2:
        if outcome and outcome_vals:
            st.markdown("**% completion**")
            st.pyplot(perc_completion_chart, use_container_width=True)


@st.cache_data
def compute_progress_overtime(
    data: pd.DataFrame,
    date: str,
    time_period: str,
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

    # group data by time period and count number of interviews
    period_stats = (
        data[["time_period"]]
        .groupby("time_period")
        .agg({"time_period": "count"})
        .rename(columns={"time_period": "num_interviews"})
        .reset_index()
    )

    # Calculate the average number of interviews
    average_interviews = period_stats["num_interviews"].mean()

    return period_stats, average_interviews


def display_progress_overtime(data: pd.DataFrame, date: str, setting_file: str) -> None:
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
    if not date:
        st.info(
            "Progress over time report requires a date column to be selected. To add a date column, go the :material/settings: settings section above."
        )
        return
    time_period = st.radio(
        label="Select time period:",
        options=["Day", "Week", "Month"],
        horizontal=True,
        key="time_period_progress_overtime",
        help="Select time period for progress report",
        on_change=trigger_save,
        kwargs=({"state_name": "time_period_progress_overtime_save"}),
    )
    if (
        "time_period_progress_overtime_save" in st.session_state
        and st.session_state.time_period_progress_overtime_save
    ):
        save_check_settings(
            settings_file=setting_file,
            check_name="progress",
            check_settings={"time_period": time_period},
        )
        st.session_state["time_period_progress_overtime_save"] = False

    period_stats, average_interviews = compute_progress_overtime(
        data=data,
        date=date,
        time_period=time_period,
    )

    # Create the figure
    fig = go.Figure()

    # Add bar plot for interviews per time period with enumerator info in hover
    fig.add_trace(
        go.Bar(
            x=period_stats["time_period"],
            y=period_stats["num_interviews"],
            name="Interviews",
            marker_color="#F28C28",  # Dark green color [Alt. Orange #F28C28]
            hovertemplate="<b>%{x}</b><br>" + "Interviews: %{y}<br>",
        )
    )

    # Add average interview line
    fig.add_trace(
        go.Scatter(
            x=[period_stats["time_period"].min(), period_stats["time_period"].max()],
            y=[average_interviews, average_interviews],
            mode="lines",
            name=f"Avg Interviews: {average_interviews:.2f}",
            line=dict(color="#4D5E90", width=2, dash="dash"),
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


@st.cache_data
def compute_attempted_interviews(
    data: pd.DataFrame, survey_id: str, date: str, display_cols: list
) -> tuple:
    """Compute attempted interviews

    Parameters
    ----------
    data: pd.DataFrame : dataset
    survey_id: str : column name for survey ID
    enumrator_id: str : column name for enumerator ID
    date: str : column name for date
    display_cols: list : list of columns to display

    Returns
    -------
    pd.Dataframe : Dataset with the number of interviews attempted for each survey ID
    and additional columns
    """
    total_submitted = len(data)
    # calculate the number of interviews attempted for each survey ID
    # create a dataframe with the following information:
    # survey_id, count of interviews per survey_id, last attempt date, attempt dates for
    # each survey_id
    attempted_interviews = (
        data.groupby(survey_id)
        .agg(
            num_interviews=pd.NamedAgg(column=survey_id, aggfunc="count"),
            last_attempt_date=pd.NamedAgg(column=date, aggfunc="max"),
            attempt_dates=pd.NamedAgg(column=date, aggfunc=lambda x: list(x)),
        )
        .reset_index()
    )
    attempt_dates_df = attempted_interviews["attempt_dates"].apply(pd.Series)
    attempt_dates_df.columns = [
        f"Attempt Date {i + 1}" for i in range(attempt_dates_df.shape[1])
    ]
    attempted_interviews = pd.concat([attempted_interviews, attempt_dates_df], axis=1)
    attempted_interviews.drop(columns=["attempt_dates"], inplace=True)
    display_cols_use = display_cols + [survey_id]
    # sort data by survey_id and date
    data = data.sort_values(by=[survey_id, date])
    display_data = data[display_cols_use].copy()
    # for columns in display_cols, aggregate by survey_id keep the last value
    for col in display_cols:
        display_data[col] = display_data.groupby(survey_id)[col].transform(
            lambda x: x.ffill().bfill()
        )
    display_data = display_data.drop_duplicates(subset=[survey_id])
    # merge the display data with the attempted interviews data
    attempted_interviews = pd.merge(
        attempted_interviews,
        display_data,
        how="left",
        on=survey_id,
    )

    # order columns
    cols = [survey_id] + ["num_interviews", "last_attempt_date"] + display_cols
    cols += list(attempt_dates_df.columns)
    attempted_interviews = attempted_interviews[cols]

    # count number of unique ID, min number of attempts and max number of attempts
    number_of_unique_ids = attempted_interviews[survey_id].nunique()
    min_attempts = attempted_interviews["num_interviews"].min()
    max_attempts = attempted_interviews["num_interviews"].max()

    return (
        attempted_interviews,
        total_submitted,
        number_of_unique_ids,
        min_attempts,
        max_attempts,
    )


def display_attempted_interviews(
    data: pd.DataFrame, survey_id: str, date: str, setting_file: str
) -> None:
    """Display attempted interviews

    Parameters
    ----------
    data: pd.DataFrame : dataset
    survey_id: str : column name for survey ID
    date: str : column name for date

    Returns
    -------
    None
    """
    st.write("---")
    st.write("## Attempted Interviews")
    if not (all([survey_id, date])):
        st.info(
            "Attempted interviews report requires survey ID and date columns to be selected. To add these columns, go to the :material/settings: settings section above."
        )
        return

    st.markdown("### Select columns to display")
    default_settings = load_check_settings(
        settings_file=setting_file, check_name="progress"
    )
    display_cols = default_settings.get("display_cols") if default_settings else None
    display_cols = st.multiselect(
        label="",
        options=data.columns,
        help="Columns to display in the attempted interviews report",
        key="attempted_interviews_display_cols",
        default=display_cols,
        on_change=trigger_save,
        kwargs=({"state_name": "attempted_interviews_display_cols_save"}),
    )
    if st.session_state.get("attempted_interviews_display_cols_save"):
        save_check_settings(
            settings_file=setting_file,
            check_name="progress",
            check_settings={"display_cols": display_cols},
        )
        st.session_state["attempted_interviews_display_cols_save"] = False
    (
        attempted_interviews,
        total_submitted,
        number_of_unique_ids,
        min_attempts,
        max_attempts,
    ) = compute_attempted_interviews(
        data=data,
        survey_id=survey_id,
        date=date,
        display_cols=display_cols,
    )
    cmap = sns.light_palette("pink", as_cmap=True)
    vmin = attempted_interviews["num_interviews"].min()
    vmax = attempted_interviews["num_interviews"].max()
    cm1, cm2, cm3, cm4 = st.columns(4, border=True)
    cm1.metric(label="Total Submitted Interviews", value=total_submitted)
    cm2.metric(label="Number of Unique IDs", value=number_of_unique_ids)
    cm3.metric(label="Min Attempts", value=min_attempts)
    cm4.metric(label="Max Attempts", value=max_attempts)
    pd.set_option("display.max_columns", None)

    ai1, ai2 = st.columns([0.4, 0.6])
    with ai1:
        # aggregted attempted interviews into attempted_frequency
        attempted_frequency = (
            attempted_interviews.groupby("num_interviews")
            .size()
            .reset_index(name="frequency")
        )
        fig = px.bar(
            attempted_frequency, x="frequency", y="num_interviews", orientation="h"
        )
        fig.update_layout(
            title="Attempted Interviews Frequency",
            title_x=0.5,
            height=400,
            margin=dict(t=50, b=50, l=50, r=50),
            hovermode="x",
            xaxis=dict(
                title="Frequency",
                showgrid=False,
                gridcolor="lightgrey",
            ),
            yaxis=dict(
                title="Number of Attempts",
                showgrid=False,
                gridcolor="lightgrey",
                autorange="reversed",
            ),
        )
        fig.update_traces(
            marker_color="#F28C28",
            hovertemplate="<b>Attempts: %{y}</b><br>"
            + "Frequency: %{x}<extra></extra>",
        )
        st.plotly_chart(fig, use_container_width=True)

    with ai2:
        st.dataframe(
            data=attempted_interviews.style.background_gradient(
                subset=["num_interviews"],
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
            ),
            use_container_width=True,
            column_config={
                survey_id: st.column_config.Column(pinned=True),
                "num_interviews": st.column_config.Column(
                    pinned=True, label="Number of Interviews"
                ),
                "last_attempt_date": st.column_config.DateColumn(
                    pinned=True, label="Last Attempt Date"
                ),
            },
            hide_index=True,
        )


def progress_report(
    project_id: str, data: pd.DataFrame, setting_file: str, page_num: int
) -> None:
    """Display progress report

    Parameters
    ----------
    data: pd.DataFrame : data to display
    page_num: int : page number

    Returns
    -------
    None
    """
    survey_id, date, enumerator, target = progress_report_settings(
        project_id, data, setting_file, page_num
    )
    display_progress_summary(
        data=data,
        target=target,
    )
    display_progress_overtime(
        data=data,
        date=date,
        setting_file=setting_file,
    )
    display_attempted_interviews(
        data=data,
        survey_id=survey_id,
        date=date,
        setting_file=setting_file,
    )
    display_progress_chart(data=data, setting_file=setting_file)
