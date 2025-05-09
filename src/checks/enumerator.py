import json
import os

import pandas as pd
import streamlit as st

from src.utils import (
    load_check_settings,
)

##### Enumerator Statistics #####


@st.cache_data
def load_default_enumerator_settings(setting_file: str, page_num: str) -> tuple:
    """Load default settings for enumerator report.

    Parameters
    ----------
    setting_file : str
        Path to the settings file.
    page_num : str
        Page number for the report.


    Returns
    -------
    tuple
        Default settings for enumerator report.

       date : str - date column name
       formdef_version : str - form version column name
       survey_id : str - survey ID column name
       duration : str - duration column name
       enumerator : str - enumerator column name
       team : str - team column name
       consent : str - consent column name
       consent_vals : list - consent values
       outcome : str - outcome column name
       outcome_vals : list - outcome values
    """
    if setting_file and os.path.exists(setting_file):
        default_settings = load_check_settings(
            settings_file=setting_file, check_name="enumerator"
        )
        if default_settings:
            (
                date,
                formdef_version,
                survey_id,
                enumerator,
                team,
                consent,
                consent_vals,
                outcome,
                outcome_vals,
            ) = (
                default_settings.get("date"),
                default_settings.get("formdef_version"),
                default_settings.get("survey_id"),
                default_settings.get("enumerator"),
                default_settings.get("team"),
                default_settings.get("consent"),
                default_settings.get("consent_vals"),
                default_settings.get("outcome"),
                default_settings.get("outcome_vals"),
            )
        else:
            date, survey_id, enumerator = (
                st.session_state["config_pages"]["Survey Date"][page_num - 1],
                st.session_state["config_pages"]["Survey ID"][page_num - 1],
                st.session_state["config_pages"]["Enumerator"][page_num - 1],
            )
            (
                formdef_version,
                duration,
                team,
                consent,
                consent_vals,
                outcome,
                outcome_vals,
            ) = (None, None, None, None, None, None, None)
        return (
            date,
            formdef_version,
            survey_id,
            duration,
            enumerator,
            team,
            consent,
            consent_vals,
            outcome,
            outcome_vals,
        )


def enumerator_report_settings(data: str, setting_file: str, page_num: str) -> tuple:
    """Load default settings for enumerator report.

    Parameters
    ----------
    data : str
        Path to the settings file.
    setting_file : str
        Path to the settings file.
    page_num : str
        Page number for the report.

    Returns
    -------
    tuple
        Default settings for enumerator report.

       date : str - date column name
       formdef_version : str - form version column name
       survey_id : str - survey ID column name
       duration : str - duration column name
       enumerator : str - enumerator column name
       team : str - team column name
       consent : str - consent column name
       consent_vals : list - consent values
       outcome : str - outcome column name
       outcome_vals : list - outcome values
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for enumerator report")
        st.write("---")
        survey_cols = data.columns
        (
            date,
            formdef_version,
            survey_id,
            duration,
            enumerator,
            team,
            consent,
            consent_vals,
            outcome,
            outcome_vals,
        ) = load_default_enumerator_settings(
            setting_file=setting_file, page_num=page_num
        )
        uc1, uc2, uc3 = st.columns(3)
        with st.container(border=True):
            with uc1:
                default_date_index = (
                    survey_cols.get_loc(date) if date in survey_cols else None
                )
                date = st.selectbox(
                    label="Date",
                    options=data.columns,
                    help="Column containing survey date",
                    key="date_enumerator",
                    index=default_date_index,
                )
            with uc2:
                default_formdef_index = (
                    survey_cols.get_loc(formdef_version)
                    if formdef_version in survey_cols
                    else None
                )
                formdef_version = st.selectbox(
                    label="Form Version",
                    options=data.columns,
                    help="Column containing survey form version",
                    key="formdef_version_enumerator",
                    index=default_formdef_index,
                )
            with uc3:
                default_survey_id_index = (
                    survey_cols.get_loc(survey_id) if survey_id in survey_cols else None
                )
                survey_id = st.selectbox(
                    label="Survey ID",
                    options=data.columns,
                    help="Column containing survey ID",
                    key="survey_id_enumerator",
                    index=default_survey_id_index,
                )
        with st.container(border=True):
            mc1, mc2, mc3 = st.columns(3)
            with mc1:
                default_duration_index = (
                    survey_cols.get_loc(duration) if duration in survey_cols else None
                )
                duration = st.selectbox(
                    label="Duration",
                    options=data.columns,
                    help="Column containing survey duration",
                    key="duration_enumerator",
                    index=default_duration_index,
                )
            with mc2:
                default_enumerator_index = (
                    survey_cols.get_loc(enumerator)
                    if enumerator in survey_cols
                    else None
                )
                enumerator = st.selectbox(
                    label="Enumerator",
                    options=data.columns,
                    help="Column containing survey enumerator",
                    key="enumerator_enumerator",
                    index=default_enumerator_index,
                )
            with mc3:
                default_team_index = (
                    survey_cols.get_loc(team) if team in survey_cols else None
                )
                team = st.selectbox(
                    label="Team",
                    options=data.columns,
                    help="Column containing survey team",
                    key="team_enumerator",
                    index=default_team_index,
                )
        bc1, _, bc2 = st.columns(3)
        with bc1, st.container(border=True):
            default_consent_index = (
                survey_cols.get_loc(consent) if consent in survey_cols else None
            )
            consent = st.selectbox(
                label="Consent",
                options=survey_cols,
                help="Column containing survey consent",
                key="consent_enumerator",
                index=default_consent_index,
            )
            if consent:
                consent_options = data[consent].unique().tolist()
                consent_vals = st.multiselect(
                    label="Consent value(s)",
                    options=consent_options,
                    help="Value(s) indicating valid consent",
                    key="consent_val_enumerator",
                    default=consent_vals,
                )
        with bc2, st.container(border=True):
            default_outcome_index = (
                survey_cols.get_loc(outcome) if outcome in survey_cols else None
            )
            outcome = st.selectbox(
                label="Outcome",
                options=survey_cols,
                help="Column containing survey outcome",
                key="outcome_enumerator",
                index=default_outcome_index,
            )
            if outcome:
                outcome_options = data[outcome].unique().tolist()
                outcome_vals = st.multiselect(
                    label="Outcome value(s)",
                    options=outcome_options,
                    help="Value(s) indicating completed survey",
                    key="outcome_val_enumerator",
                    default=outcome_vals,
                )
    return (
        date,
        formdef_version,
        survey_id,
        duration,
        enumerator,
        team,
        consent,
        consent_vals,
        outcome,
        outcome_vals,
    )


@st.cache_data
def compute_enumerator_overview(
    data: pd.DataFrame, date: str, enumerator: str, team: str
) -> tuple:
    """Compute enumerator overview metrics.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    team : str
        Team column name.

    Returns
    -------
    tuple:
        Overview metrics for enumerators.
    """
    data = data.sort_values(by=[enumerator, date])
    data[date] = data[date].dt.strftime("%b %d, %Y")

    all_submissions = len(data)

    # Calculate daily submissions
    data["TOKEN KEY"] = data.index
    daily_submissions_sum = (
        data.groupby([date, enumerator])["TOKEN KEY"]
        .count()
        .rename("count")
        .reset_index()
    )
    active_date_cut_off = pd.to_datetime("today").date() - pd.Timedelta(weeks=1)
    daily_submissions_sum["active"] = pd.to_datetime(data[date]) > pd.to_datetime(
        active_date_cut_off
    )
    num_active_enumerators = daily_submissions_sum[daily_submissions_sum["active"]][
        enumerator
    ].nunique()

    num_enumerators = data[enumerator].nunique()
    num_teams = data[team].nunique() if team else "n/a"
    min_submissions = daily_submissions_sum["count"].min()
    max_submissions = daily_submissions_sum["count"].max()
    avg_submissions = int(daily_submissions_sum["count"].mean())

    pct_active_enumerators = f"{(num_active_enumerators / num_enumerators) * 100:.0f}%"

    return (
        all_submissions,
        num_active_enumerators,
        num_enumerators,
        num_teams,
        min_submissions,
        max_submissions,
        avg_submissions,
        pct_active_enumerators,
    )


def display_enumerator_overview(
    data: pd.DataFrame, date: str, enumerator: str, team: str
) -> None:
    """Display enumerator overview metrics.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    team : str
        Team column name.

    Returns
    -------
        None
    """
    st.write("---")
    st.markdown("## Enumerator Overview")
    (
        all_submissions,
        num_active_enumerators,
        num_enumerators,
        num_teams,
        min_submissions,
        max_submissions,
        avg_submissions,
        pct_active_enumerators,
    ) = compute_enumerator_overview(
        data=data, date=date, enumerator=enumerator, team=team
    )

    tc1, tc2, tc3, tc4 = st.columns(4, border=True)
    tc1.metric("Total number of enumerators", num_enumerators)
    tc2.metric("Total number of teams", num_teams)
    tc3.metric("Active enumerators (past 7 days)", num_active_enumerators)
    tc4.metric("Percentage of active enumerator (past 7 days)", pct_active_enumerators)

    bc1, bc2, bc3, bc4 = st.columns(4, border=True)
    bc1.metric("Minimum number of submissions", min_submissions)
    bc2.metric("Highest number of submissions", max_submissions)
    bc3.metric("Average number of submissions", avg_submissions)
    bc4.metric("Total number of submissions", all_submissions)


@st.cache_data
def compute_enumerator_missing_table(
    data: pd.DataFrame, missing_setting_file: str, enumerator: str
) -> pd.DataFrame:
    """Compute enumerator missing table.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing survey data.
    settings_file : str
        Path to the settings file.
    enumerator : str
        Enumerator column name.

    Returns
    -------
    pd.DataFrame
        DataFrame containing enumerator missing table.
    """
    try:
        with open(missing_setting_file) as f:
            settings_dict = json.load(f)
            missing_codes = pd.DataFrame(settings_dict)

    except FileNotFoundError:
        # create new dataframe with default values
        missing_codes = None

    data["Null values"] = data.isnull().mean(axis=1)

    miss_cols = ["Null values"]
    if not missing_codes.empty:
        for i in range(len(missing_codes)):
            miss_label = missing_codes["Missing Labels"][i]
            miss_codes = missing_codes["Missing Codes"][i].split(",")
            data[miss_label] = data[enumerator].isin(miss_codes).astype(int)

            miss_cols.append(miss_label)

    mv_data = data[[enumerator] + miss_cols].copy(deep=True)
    mv_data = (
        mv_data.groupby(by=enumerator, dropna=False, as_index=False)
        .agg({col: "mean" for col in miss_cols})
        .reset_index(drop=True)
        .reset_index(drop=True)
    )

    return mv_data


@st.cache_data
def compute_enumerator_summary(
    data: pd.DataFrame,
    missing_setting_file: str,
    date: str,
    enumerator: str,
    formdef_version: str | None,
    duration: str | None,
    consent: str | None,
    consent_vals: str | None,
    outcome: str | None,
    outcome_vals: str | None,
) -> pd.DataFrame:
    """Compute enumerator summary table.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    formdef_version : str | None
        Form version column name.
    duration : str | None
        Duration column name.
    consent : str | None
        Consent column name.
    consent_vals : str | None
        Consent values.
    outcome : str | None
        Outcome column name.
    outcome_vals : str | None
        Outcome values.

    Returns
    -------
    pd.DataFrame
        DataFrame containing enumerator summary.
    """
    df = data.copy()
    df[date] = df[date].dt.strftime("%b %d, %Y")

    summary_df = df.groupby(by=enumerator, dropna=False, as_index=False).date.agg(
        {
            "first date": "min",
            "last date": "max",
            "# of submissions": "count",
            "# of days worked": "nunique",
        }
    )

    today = pd.to_datetime("today").date()
    start_of_week = today - pd.Timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    df["submitted_today"] = df[date] == today.strftime("%b %d, %Y")
    df["submitted_this_week"] = df[date] >= start_of_week.strftime("%b %d, %Y")
    df["submitted_this_month"] = df[date] >= start_of_month.strftime("%b %d, %Y")

    lagged_df = (
        df.groupby(by=enumerator, dropna=False, as_index=False)
        .agg(
            {
                "submitted_today": "sum",
                "submitted_this_week": "sum",
                "submitted_this_month": "sum",
            }
        )
        .reset_index(drop=True)
        .rename(
            columns={
                "submitted_today": "submissions today",
                "submitted_this_week": "submissions this week",
                "submitted_this_month": "submissions this month",
            }
        )
    )

    summary_df = pd.merge(
        summary_df,
        lagged_df,
        how="left",
        left_on=enumerator,
        right_on=enumerator,
    )

    enumerator_missing_df = compute_enumerator_missing_table(
        data=df, missing_setting_file=missing_setting_file, enumerator=enumerator
    )

    summary_df = pd.merge(
        summary_df,
        enumerator_missing_df,
        how="left",
        left_on=enumerator,
        right_on=enumerator,
    )

    if duration:
        duration_df = df.groupby(by=enumerator, dropna=False, as_index=False).agg(
            {duration: ["min", "mean", "median", "max"]}
        )
        duration_df.columns = [
            enumerator,
            "min duration",
            "mean duration",
            "median duration",
            "max duration",
        ]
        summary_df = pd.merge(
            summary_df,
            duration_df,
            how="left",
            left_on=enumerator,
            right_on=enumerator,
        )

    if formdef_version:
        formdef_outdated = df[[date, formdef_version]].copy(deep=True)
        formdef_outdated = (
            formdef_outdated.groupby(by=date, dropna=False, as_index=False)
            .formdef_version.agg({"latest daily form version": "max"})
            .reset_index()
        )
        df = pd.merge(
            df,
            formdef_outdated,
            how="left",
            left_on=[date],
            right_on=[date],
        )
        df["outdated_form_version"] = (
            df[formdef_version] != df["latest daily form version"]
        )
        formdef_outdated_df = (
            df.groupby(by=enumerator, dropna=False, as_index=False)
            .outdated_form_version.agg({"# of outdated form versions": "sum"})
            .reset_index(drop=True)
        )

        formdef_df = (
            df.groupby(by=enumerator, dropna=False, as_index=False)
            .formdef_version.agg({formdef_version: ["nunique", "max"]})
            .reset_index(drop=True)
        )
        formdef_df.columns = [
            enumerator,
            "number of form versions",
            "latest form version",
        ]
        summary_df.merge(
            formdef_df,
            how="left",
            left_on=enumerator,
            right_on=enumerator,
        )
        summary_df = pd.merge(
            summary_df,
            formdef_outdated_df,
            how="left",
            left_on=enumerator,
            right_on=enumerator,
        )
        latest_enum_formversion = (
            df.groupby(by=enumerator, dropna=False, as_index=False)
            .formdef_version.agg({"last form version": "max"})
            .reset_index(drop=True)
        )

        summary_df = pd.merge(
            summary_df,
            latest_enum_formversion,
            how="left",
            left_on=enumerator,
            right_on=enumerator,
        )
    if consent and consent_vals:
        df["consent_granted_agg_col"] = df[consent].isin(consent_vals).astype(int)
        consent_df = (
            df.groupby(by=enumerator, dropna=False, as_index=False)
            .consent_granted_agg_col.agg({"% consent": "mean"})
            .reset_index(drop=True)
        )
        summary_df = pd.merge(
            summary_df,
            consent_df,
            how="left",
            left_on=enumerator,
            right_on=enumerator,
        )
    if outcome and outcome_vals:
        df["completed_survey_agg_col"] = df[outcome].isin(outcome_vals).astype(int)
        outcome_df = (
            df.groupby(by=enumerator, dropna=False, as_index=False)
            .completed_survey_agg_col.agg({"% completed survey": "mean"})
            .reset_index(drop=True)
        )
        summary_df = pd.merge(
            summary_df,
            outcome_df,
            how="left",
            left_on=enumerator,
            right_on=enumerator,
        )

    return summary_df


def display_enumerator_summary(
    data: pd.DataFrame,
    missing_setting_file: str,
    date: str,
    enumerator: str,
    formdef_version: str | None,
    duration: str | None,
    consent: str | None,
    consent_vals: str | None,
    outcome: str | None,
    outcome_vals: str | None,
) -> pd.DataFrame:
    """Display enumerator summary table.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing summary data frame.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    formdef_version : str | None
        Form version column name.
    duration : str | None
        Duration column name.
    consent : str | None
        Consent column name.
    consent_vals : str | None
        Consent values.
    outcome : str | None
        Outcome column name.
    outcome_vals : str | None
        Outcome values.
    """
    st.write("---")
    st.markdown("## Enumerator Summary")
    summary_df = compute_enumerator_summary(
        data=data,
        missing_setting_file=missing_setting_file,
        date=date,
        enumerator=enumerator,
        formdef_version=formdef_version,
        duration=duration,
        consent=consent,
        consent_vals=consent_vals,
        outcome=outcome,
        outcome_vals=outcome_vals,
    )
    st.dataframe(summary_df, hide_index=True, use_container_width=True)


def enumerator_report(
    data: pd.DataFrame, setting_file: str, page_num: int, page_name: str
) -> None:
    """Generate enumerator report.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing survey data.
    setting_file : str
        Path to the settings file.
    page_num : int
        Page number for the report.

    Returns
    -------
        None
    """
    missing_setting_file = f"cache/settings/pyDMS_missing_settings_{page_name}.json"

    (
        date,
        formdef_version,
        survey_id,
        duration,
        enumerator,
        team,
        consent,
        consent_vals,
        outcome,
        outcome_vals,
    ) = enumerator_report_settings(
        data=data, setting_file=setting_file, page_num=page_num
    )
    display_enumerator_overview(
        data=data,
        date=date,
        enumerator=enumerator,
        team=team,
    )

    display_enumerator_summary(
        data=data,
        date=date,
        enumerator=enumerator,
        formdef_version=formdef_version,
        duration=duration,
        consent=consent,
        consent_vals=consent_vals,
        outcome=outcome,
        outcome_vals=outcome_vals,
        missing_setting_file=missing_setting_file,
    )
