import json
import os

import pandas as pd
import seaborn as sns
import streamlit as st

from datasure.utils import (
    get_check_config_settings,
    get_df_info,
    load_check_settings,
    save_check_settings,
    trigger_save,
)

##### Enumerator Statistics #####


def load_default_enumerator_settings(
    project_id: str, setting_file: str, page_num: str
) -> tuple:
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
    # Get config page defaults
    _, _, _, config_survey_id, config_survey_date, config_enumerator, _, _ = (
        get_check_config_settings(
            project_id=project_id,
            page_row_index=page_num - 1,
        )
    )
    if setting_file and os.path.exists(setting_file):
        default_settings = (
            load_check_settings(settings_file=setting_file, check_name="enumerator")
            or {}
        )
    else:
        default_settings = {}
    (
        date,
        survey_id,
        enumerator,
        formdef_version,
        duration,
        team,
        consent,
        consent_vals,
        outcome,
        outcome_vals,
    ) = (
        default_settings.get("date", config_survey_date),
        default_settings.get("survey_id", config_survey_id),
        default_settings.get("enumerator", config_enumerator),
        default_settings.get("formdef_version"),
        default_settings.get("duration"),
        default_settings.get("team"),
        default_settings.get("consent"),
        default_settings.get("consent_vals"),
        default_settings.get("outcome"),
        default_settings.get("outcome_vals"),
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


def enumerator_report_settings(
    project_id: str, data: str, setting_file: str, page_num: str
) -> tuple:
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

        all_cols, string_columns, numeric_columns, datetime_columns, _ = get_df_info(
            data, cols_only=True
        )

        string_numeric_cols = string_columns + numeric_columns

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
        ) = load_default_enumerator_settings(project_id, setting_file, page_num)
        uc1, uc2, uc3 = st.columns(3)
        with st.container(border=True):
            with uc1:
                default_date_index = (
                    datetime_columns.index(date)
                    if date and date in datetime_columns
                    else None
                )

                date = st.selectbox(
                    label="Date",
                    options=datetime_columns,
                    help="Column containing survey date",
                    key="date_enumerator",
                    index=default_date_index,
                    on_change=trigger_save,
                    kwargs={"state_name": "date_enumerator_save"},
                )
                if (
                    "date_enumerator_save" in st.session_state
                    and st.session_state.date_enumerator_save
                ):
                    save_check_settings(
                        settings_file=setting_file,
                        check_name="enumerator",
                        check_settings={"date": date},
                    )
                    st.session_state.date_enumerator_save = False
            with uc2:
                default_formdef_index = (
                    string_numeric_cols.index(formdef_version)
                    if formdef_version and formdef_version in string_numeric_cols
                    else None
                )
                formdef_version = st.selectbox(
                    label="Form Version",
                    options=string_numeric_cols,
                    help="Column containing survey form version",
                    key="formdef_version_enumerator",
                    index=default_formdef_index,
                    on_change=trigger_save,
                    kwargs={"state_name": "formdef_version_save"},
                )
                if (
                    "formdef_version_save" in st.session_state
                    and st.session_state.formdef_version_save
                ):
                    save_check_settings(
                        settings_file=setting_file,
                        check_name="enumerator",
                        check_settings={"formdef_version": formdef_version},
                    )
                    st.session_state.formdef_version_save = False
            with uc3:
                default_survey_id_index = (
                    string_numeric_cols.index(survey_id)
                    if survey_id and survey_id in string_numeric_cols
                    else None
                )
                survey_id = st.selectbox(
                    label="Survey ID",
                    options=string_numeric_cols,
                    help="Column containing survey ID",
                    key="survey_id_enumerator",
                    index=default_survey_id_index,
                    on_change=trigger_save,
                    kwargs={"state_name": "survey_id_enumerator_save"},
                )
                if (
                    "survey_id_enumerator_save" in st.session_state
                    and st.session_state.survey_id_enumerator_save
                ):
                    save_check_settings(
                        settings_file=setting_file,
                        check_name="enumerator",
                        check_settings={"survey_id": survey_id},
                    )
                    st.session_state.survey_id_enumerator_save = False
        with st.container(border=True):
            mc1, mc2, mc3 = st.columns(3)
            with mc1:
                default_duration_index = (
                    numeric_columns.index(duration)
                    if duration and duration in numeric_columns
                    else None
                )
                duration = st.selectbox(
                    label="Duration",
                    options=numeric_columns,
                    help="Column containing survey duration",
                    key="duration_enumerator",
                    index=default_duration_index,
                    on_change=trigger_save,
                    kwargs={"state_name": "duration_enumerator_save"},
                )
                if (
                    "duration_enumerator_save" in st.session_state
                    and st.session_state.duration_enumerator_save
                ):
                    save_check_settings(
                        settings_file=setting_file,
                        check_name="enumerator",
                        check_settings={"duration": duration},
                    )
                    st.session_state.duration_enumerator_save = False
            with mc2:
                default_enumerator_index = (
                    string_numeric_cols.index(enumerator)
                    if enumerator and enumerator in string_numeric_cols
                    else None
                )
                enumerator = st.selectbox(
                    label="Enumerator",
                    options=string_numeric_cols,
                    help="Column containing survey enumerator",
                    key="enumerator_enumerator",
                    index=default_enumerator_index,
                    on_change=trigger_save,
                    kwargs={"state_name": "enumerator_enumerator_save"},
                )
                if (
                    "enumerator_enumerator_save" in st.session_state
                    and st.session_state.enumerator_enumerator_save
                ):
                    save_check_settings(
                        settings_file=setting_file,
                        check_name="enumerator",
                        check_settings={"enumerator": enumerator},
                    )
                    st.session_state.enumerator_enumerator_save = False
            with mc3:
                default_team_index = (
                    string_numeric_cols.index(team)
                    if team and team in string_numeric_cols
                    else None
                )
                team = st.selectbox(
                    label="Team",
                    options=string_numeric_cols,
                    help="Column containing survey team",
                    key="team_enumerator",
                    index=default_team_index,
                    on_change=trigger_save,
                    kwargs={"state_name": "team_enumerator_save"},
                )
                if (
                    "team_enumerator_save" in st.session_state
                    and st.session_state.team_enumerator_save
                ):
                    save_check_settings(
                        settings_file=setting_file,
                        check_name="enumerator",
                        check_settings={"team": team},
                    )
                    st.session_state.team_enumerator_save = False
        bc1, _, bc2 = st.columns(3)
        with bc1, st.container(border=True):
            default_consent_index = (
                string_numeric_cols.index(consent)
                if consent and consent in string_numeric_cols
                else None
            )
            consent = st.selectbox(
                label="Consent",
                options=string_numeric_cols,
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
                    on_change=trigger_save,
                    kwargs={"state_name": "consent_val_enumerator_save"},
                )
                if (
                    "consent_val_enumerator_save" in st.session_state
                    and st.session_state.consent_val_enumerator_save
                ):
                    save_check_settings(
                        settings_file=setting_file,
                        check_name="enumerator",
                        check_settings={
                            "consent": consent,
                            "consent_vals": consent_vals,
                        },
                    )
                    st.session_state.consent_val_enumerator_save = False
        with bc2, st.container(border=True):
            default_outcome_index = (
                string_numeric_cols.get_loc(outcome)
                if outcome in string_numeric_cols
                else None
            )
            outcome = st.selectbox(
                label="Outcome",
                options=string_numeric_cols,
                help="Column containing survey outcome",
                key="outcome_enumerator",
                index=default_outcome_index,
                on_change=trigger_save,
                kwargs={"state_name": "outcome_enumerator_save"},
            )
            if (
                "outcome_enumerator_save" in st.session_state
                and st.session_state.outcome_enumerator_save
            ):
                save_check_settings(
                    settings_file=setting_file,
                    check_name="enumerator",
                    check_settings={"outcome": outcome},
                )
                st.session_state.outcome_enumerator_save = False
            if outcome:
                outcome_options = data[outcome].unique().tolist()
                outcome_vals = outcome_vals if outcome_vals in outcome_options else None
                outcome_vals = st.multiselect(
                    label="Outcome value(s)",
                    options=outcome_options,
                    help="Value(s) indicating completed survey",
                    key="outcome_val_enumerator",
                    default=outcome_vals,
                    on_change=trigger_save,
                    kwargs={"state_name": "outcome_val_enumerator_save"},
                )
                if (
                    "outcome_val_enumerator_save" in st.session_state
                    and st.session_state.outcome_val_enumerator_save
                ):
                    save_check_settings(
                        settings_file=setting_file,
                        check_name="enumerator",
                        check_settings={
                            "outcome": outcome,
                            "outcome_vals": outcome_vals,
                        },
                    )
                    st.session_state.outcome_val_enumerator_save = False

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
    if not (all([enumerator, date])):
        st.info(
            "Enumerator overview requires a date and enumerator column to be selected. Go to the :material/settings: settings section above to select them.",
        )
        return
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
    miss_cols : list
        List of missing label columns.
    """
    try:
        with open(missing_setting_file) as f:
            settings_dict = json.load(f)
            missing_codes = pd.DataFrame(settings_dict)

    except FileNotFoundError:
        # create new dataframe with default values
        missing_codes = pd.DataFrame([])

    data["% Null values"] = data.isnull().mean(axis=1)

    miss_cols = ["% Null values"]
    if not missing_codes.empty:
        for i in range(len(missing_codes)):
            miss_label = missing_codes["Missing Labels"][i]
            miss_codes = missing_codes["Missing Codes"][i].split(",")
            data[f"% {miss_label}"] = data.apply(
                lambda row, codes=miss_codes: any(
                    str(row[col]).strip() in codes for col in data.columns
                ),
                axis=1,
            ).astype(int)

            miss_cols.append(f"% {miss_label}")

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
    Tuple:
    pd.DataFrame
        DataFrame containing enumerator summary.
    """
    df = data.copy()
    df[date] = df[date].dt.strftime("%b %d, %Y")

    summary_df = (
        df.groupby(by=enumerator, dropna=False, as_index=False)
        .agg(
            {
                date: ["min", "max", "count", "nunique"],
            }
        )
        .reset_index(drop=True)
        .droplevel(0, axis=1)
        .rename(
            columns={
                "min": "first submission",
                "max": "last submission",
                "count": "# submissions",
                "nunique": "# unique dates",
            }
        )
    )
    summary_df = summary_df.rename(columns={summary_df.columns[0]: enumerator})

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
                "submitted_today": "# submissions today",
                "submitted_this_week": "# submissions this week",
                "submitted_this_month": "# submissions this month",
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
            .agg({formdef_version: "max"})
            .reset_index()
            .rename(columns={formdef_version: "latest daily form version"})
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
            "# form versions",
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
    if not (all([enumerator, date])):
        st.info(
            "Enumerator summary requires a date and enumerator column to be selected. Go to the :material/settings: settings section above to select them.",
        )
        return
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

    cmap = sns.light_palette("pink", as_cmap=True)

    perc_cols = [col for col in summary_df.columns if col.startswith("%")]
    summary_df = summary_df.style.format(subset=perc_cols, formatter="{:.2%}")
    num_cols = [col for col in summary_df.columns if col.startswith("#")]
    summary_df = summary_df.format(
        subset=num_cols,
        formatter="{:,.0f}",
    )
    if duration:
        summary_df = summary_df.format(
            subset=["min duration", "mean duration", "median duration", "max duration"],
            formatter="{:,.2f} sec",
        ).background_gradient(
            subset=["min duration", "mean duration", "median duration", "max duration"],
            cmap=cmap,
        )
    # set background gradient for percentage and numeric columns
    summary_df = summary_df.background_gradient(
        subset=perc_cols,
        cmap=cmap,
    ).background_gradient(
        subset=num_cols,
        cmap=cmap,
    )
    st.dataframe(summary_df, hide_index=True, use_container_width=True)


@st.cache_data
def compute_enumerator_productivity(
    data: pd.DataFrame, date: str, enumerator: str, period: str, weekstartday: str
) -> pd.DataFrame:
    """Compute enumerator productivity.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    period : str
        Period for productivity calculation.
    weekstartday : str
        Start day of the week.

    Returns
    -------
    pd.DataFrame
        DataFrame containing enumerator productivity.
    """
    prod_df = data.copy()
    # convert datetime to date
    prod_df[date] = pd.to_datetime(prod_df[date])
    if period == "Daily":
        prod_df["TIME PERIOD"] = prod_df[date].dt.to_period("D")
    elif period == "Weekly":
        prod_df["TIME PERIOD"] = prod_df[date].dt.to_period(f"W-{weekstartday}")
    elif period == "Monthly":
        prod_df["TIME PERIOD"] = prod_df[date].dt.to_period("M")

    # generate productivity table
    prod_df["TOKEN KEY"] = prod_df.index
    prod_res = (
        prod_df.groupby(["TIME PERIOD", enumerator], dropna=False, as_index=False).agg(
            {"TOKEN KEY": "count"}
        )
    ).rename(columns={"TOKEN KEY": "submissions"})

    # pivot table so enumerators dates values are columns
    prod_res = (
        prod_res.pivot(
            index=[enumerator],
            columns=["TIME PERIOD"],
            values="submissions",
        )
        .reset_index(drop=False)
        .fillna(0)
    )

    return prod_res


def display_enumerator_productivity(
    data: pd.DataFrame,
    date: str,
    enumerator: str,
    setting_file: str,
) -> None:
    """Display enumerator productivity.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.

    Returns
    -------
        None
    """
    st.write("---")
    st.markdown("## Enumerator Productivity")
    if not (all([enumerator, date])):
        st.info(
            "Enumerator productivity requires a date and enumerator column to be selected. Go to the :material/settings: settings section above to select them.",
        )
        return
    default_setting = (
        load_check_settings(settings_file=setting_file, check_name="enumerator") or {}
    )
    # Toggle for days, weeks, or months view
    st.markdown("##### Productivity")
    view_option_list = ("Daily", "Weekly", "Monthly")
    default_view = default_setting.get("view_option", "Daily")
    default_view_index = view_option_list.index(default_view)
    view_option = st.radio(
        label="Select View:",
        options=view_option_list,
        index=default_view_index,
        key="view_option_enumerator",
        horizontal=True,
        on_change=trigger_save,
        kwargs={"state_name": "view_option_enumerator_save"},
    )
    if (
        "view_option_enumerator_save" in st.session_state
    ) and st.session_state.view_option_enumerator_save:
        save_check_settings(
            settings_file=setting_file,
            check_name="enumerator",
            check_settings={"view_option": view_option},
        )
        st.session_state.view_option_enumerator_save = False

    weekstartday = "SAT"
    if view_option == "Weekly":
        day_list = (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        )
        default_weekstartday_sel = default_setting.get("weekstartday", "Monday")
        default_weekstartday_sel_index = day_list.index(default_weekstartday_sel)
        weekstartday_sel = st.selectbox(
            label="Select the first day of the week",
            options=day_list,
            index=default_weekstartday_sel_index,
            key="project_week_start_day",
            on_change=trigger_save,
            kwargs={"state_name": "project_week_start_day_enumerator_save"},
        )
        if (
            "project_week_start_day_enumerator_save" in st.session_state
        ) and st.session_state.project_week_start_day_enumerator_save:
            save_check_settings(
                settings_file=setting_file,
                check_name="enumerator",
                check_settings={"weekstartday": weekstartday_sel},
            )
            st.session_state.project_week_start_day_enumerator_save = False
        if weekstartday_sel:
            weekstart_adjust_dict = {
                "Monday": "SUN",
                "Tuesday": "MON",
                "Wednesday": "TUE",
                "Thursday": "WED",
                "Friday": "THU",
                "Saturday": "FRI",
                "Sunday": "SAT",
            }
            weekstartday = weekstart_adjust_dict[weekstartday_sel]
    productivity_df = compute_enumerator_productivity(
        data=data,
        date=date,
        enumerator=enumerator,
        period=view_option,
        weekstartday=weekstartday,
    )
    cmap = sns.light_palette("pink", as_cmap=True)
    format_cols = [col for col in productivity_df.columns if col not in [enumerator]]
    productivity_df = productivity_df.style.format(
        subset=format_cols,
        formatter="{:,.0f}",
    ).background_gradient(
        subset=format_cols,
        cmap=cmap,
    )
    st.dataframe(productivity_df, hide_index=True, use_container_width=True)


@st.cache_data
def compute_enumerator_statistics(
    data: pd.DataFrame,
    date: str,
    enumerator: str,
    statscols: list[str],
    stats: list[str],
) -> pd.DataFrame:
    """Compute enumerator statistics.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    statscols : list[str]
        List of columns to compute statistics on.
    stats : list[str]
        List of statistics to compute.

    Returns
    -------
    pd.DataFrame
        DataFrame containing enumerator statistics.
    """
    stats_df = data[[enumerator] + statscols].copy(deep=True)
    stats_dict = {col: stats for col in statscols}
    stats_res = stats_df.groupby(by=enumerator, dropna=False, as_index=False).agg(
        stats_dict
    )

    return stats_res


def display_enumerator_statistics(
    data: pd.DataFrame,
    date: str,
    enumerator: str,
    setting_file: str,
) -> None:
    """Display enumerator statistics.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    statscols : list[str]
        List of columns to compute statistics on.
    stats : list[str]
        List of statistics to compute.

    Returns
    -------
        None
    """
    st.write("---")
    st.markdown("## Enumerator Statistics")
    if not enumerator:
        st.info(
            "Enumerator statistics requires an enumerator column to be selected. Go to the :material/settings: settings section above to select it.",
        )
        return
    # create enumerator statistics
    default_setting = (
        load_check_settings(settings_file=setting_file, check_name="enumerator") or {}
    )
    st.markdown("##### Statistics")
    s1, s2 = st.columns(2)
    with s1:
        default_statscols = default_setting.get("statscols", None)
        statscols = st.multiselect(
            label="Select columns:",
            options=data.select_dtypes("number").columns,
            default=default_statscols,
            help="Select columns to include in statistics",
            key="selected_columns_enumerator",
            on_change=trigger_save,
            kwargs={"state_name": "selected_columns_enumerator_save"},
        )
        if (
            "selected_columns_enumerator_save" in st.session_state
        ) and st.session_state.selected_columns_enumerator_save:
            save_check_settings(
                settings_file=setting_file,
                check_name="enumerator",
                check_settings={"statscols": statscols},
            )
            st.session_state.selected_columns_enumerator_save = False
    with s2:
        default_stats = default_setting.get("stats", ["count", "mean"])
        stats = st.multiselect(
            "Select statistics:",
            options=[
                "count",
                "min",
                "mean",
                "median",
                "max",
                "std",
                "25th percentile",
                "75th percentile",
            ],
            default=default_stats,
            help="Select statistics to calculate",
            key="statistics_options_enumerator",
            on_change=trigger_save,
            kwargs={"state_name": "statistics_options_enumerator_save"},
        )
        if (
            "statistics_options_enumerator_save" in st.session_state
        ) and st.session_state.statistics_options_enumerator_save:
            save_check_settings(
                settings_file=st.session_state["settings_file"],
                check_name="enumerator",
                check_settings={"stats": stats},
            )
            st.session_state.statistics_options_enumerator_save = False
    if statscols:
        stats_df = compute_enumerator_statistics(
            data=data,
            date=date,
            enumerator=enumerator,
            statscols=statscols,
            stats=stats,
        )
        cmap = sns.light_palette("pink", as_cmap=True)
        # apply formatting to the statistics DataFrame
        stats_df = stats_df.style.format(
            subset=statscols,
            formatter="{:,.2f}",
        ).background_gradient(
            subset=statscols,
            cmap=cmap,
        )

        st.dataframe(stats_df, hide_index=True, use_container_width=True)
    else:
        st.info(
            "No columns selected for statistics calculation.", icon=":material/info:"
        )


def compute_enumerator_statistics_overtime(
    data: pd.DataFrame,
    date: str,
    enumerator: str,
    statscol: list[str],
    stat: list[str],
    period: str,
    weekstartday: str,
) -> pd.DataFrame:
    """Compute enumerator statistics over time.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    statscol : list[str]
        List of columns to compute statistics on.
    stat : list[str]
        List of statistics to compute.
    time_period : str
        Time period for statistics calculation.
    weekstartday : str
        Start day of the week.

    Returns
    -------
    pd.DataFrame
        DataFrame containing enumerator statistics over time.
    """
    stats_overtime_df = data[[date, enumerator, statscol]].copy(deep=True)
    stats_overtime_df[date] = pd.to_datetime(stats_overtime_df[date])
    if period == "Daily":
        stats_overtime_df["TIME PERIOD"] = stats_overtime_df[date].dt.to_period("D")
    elif period == "Weekly":
        stats_overtime_df["TIME PERIOD"] = stats_overtime_df[date].dt.to_period(
            f"W-{weekstartday}"
        )
    elif period == "Monthly":
        stats_overtime_df["TIME PERIOD"] = stats_overtime_df[date].dt.to_period("M")
    if stat == "missing":
        stats_overtime_df["_STAT"] = stats_overtime_df[statscol].isnull().mean()
        stats_overtime_res = stats_overtime_df.groupby(
            by=["TIME PERIOD", enumerator], dropna=False, as_index=False
        ).agg({"_STAT": "mean"})
    else:
        stats_overtime_res = (
            stats_overtime_df.groupby(
                by=["TIME PERIOD", enumerator], dropna=False, as_index=False
            )
            .agg({statscol: stat})
            .rename(columns={statscol: "_STAT"})
        )
    # pivot table so enumerators dates values are columns
    stats_overtime_res = stats_overtime_res.pivot(
        index=[enumerator],
        columns=["TIME PERIOD"],
        values="_STAT",
    ).reset_index(drop=False)

    return stats_overtime_res


def display_enumerator_statistics_overtime(
    data: pd.DataFrame,
    date: str,
    enumerator: str,
    setting_file: str,
) -> None:
    """Display enumerator statistics over time.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.

    Returns
    -------
        None
    """
    st.write("---")
    st.markdown("## Enumerator Statistics Over Time")
    if not (all([enumerator, date])):
        st.info(
            "Enumerator statistics over time requires a date and enumerator column to be selected. Go to the :material/settings: settings section above to select them.",
        )
        return
    # create enumerator statistics

    st.markdown("##### Statistics")
    default_setting = (
        load_check_settings(settings_file=setting_file, check_name="enumerator")
    ) or {}
    s1, s2, s3 = st.columns([0.2, 0.15, 0.75])
    with s1:
        period_list = ("Daily", "Weekly", "Monthly")
        default_period = default_setting.get("period", "Daily")
        default_period_index = period_list.index(default_period)
        period = st.radio(
            label="Select Time Period:",
            options=period_list,
            index=default_period_index,
            key="project_enumerator_statistics_overtime_period",
            horizontal=True,
            on_change=trigger_save,
            kwargs={"state_name": "project_enumerator_statistics_overtime_period_save"},
        )
        if (
            "project_enumerator_statistics_overtime_period_save" in st.session_state
        ) and st.session_state.project_enumerator_statistics_overtime_period_save:
            save_check_settings(
                settings_file=setting_file,
                check_name="enumerator",
                check_settings={"period": period},
            )
            st.session_state.project_enumerator_statistics_overtime_period_save = False
    weekstartday = "SAT"
    if period == "Weekly":
        day_list = (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        )
        default_weekstartday_sel = default_setting.get("weekstartday", "Monday")
        default_weekstartday_sel_index = day_list.index(default_weekstartday_sel)
        weekstartday = st.selectbox(
            label="Select the first day of the week",
            options=day_list,
            index=default_weekstartday_sel_index,
            help="Select the first day of the week",
            key="project_week_start_day_enumerator",
            on_change=trigger_save,
            kwargs={"state_name": "project_week_start_day_enumerator_save"},
        )
        if (
            "project_week_start_day_enumerator_save" in st.session_state
        ) and st.session_state.project_week_start_day_enumerator_save:
            save_check_settings(
                settings_file=setting_file,
                check_name="enumerator",
                check_settings={"weekstartday": weekstartday},
            )
            st.session_state.project_week_start_day_enumerator_save = False
        if weekstartday:
            weekstart_adjust_dict = {
                "Monday": "SUN",
                "Tuesday": "MON",
                "Wednesday": "TUE",
                "Thursday": "WED",
                "Friday": "THU",
                "Saturday": "FRI",
                "Sunday": "SAT",
            }
            weekstartday = weekstart_adjust_dict[weekstartday]
    with s2:
        stat_list = (
            "count",
            "min",
            "mean",
            "median",
            "max",
            "std",
            "25th percentile",
            "75th percentile",
            "missing",
        )
        default_stat = default_setting.get("stat", "count")
        default_stat_index = stat_list.index(default_stat)
        stat = st.selectbox(
            label="Select statistic:",
            options=stat_list,
            index=default_stat_index,
            help="Select statistics to calculate",
            key="enumerator_statistics_overtime_stat",
            on_change=trigger_save,
            kwargs={"state_name": "enumerator_statistics_overtime_stat_save"},
        )
        if (
            "enumerator_statistics_overtime_stat_save" in st.session_state
        ) and st.session_state.enumerator_statistics_overtime_stat_save:
            save_check_settings(
                settings_file=setting_file,
                check_name="enumerator",
                check_settings={"stat": stat},
            )
            st.session_state.enumerator_statistics_overtime_stat_save = False
    with s3:
        statscol_option_list = data.select_dtypes("number").columns
        default_statscol = default_setting.get("statscol", None)
        default_statscol_index = (
            statscol_option_list.tolist().index(default_statscol)
            if default_statscol in statscol_option_list
            else None
        )
        statscol = st.selectbox(
            label="Select column:",
            options=statscol_option_list,
            index=default_statscol_index,
            help="Select columns to include in statistics",
            key="enumerator_statistics_overtime_column",
        )
    if statscol:
        stats_overtime_df = compute_enumerator_statistics_overtime(
            data=data,
            date=date,
            enumerator=enumerator,
            statscol=statscol,
            stat=stat,
            period=period,
            weekstartday=weekstartday,
        )
        cmap = sns.light_palette("pink", as_cmap=True)
        # apply formatting to the statistics DataFrame
        format_cols = [
            col for col in stats_overtime_df.columns if col not in [enumerator]
        ]
        format = "{:,.2%}" if stat == "missing" else "{:,.2f}"
        stats_overtime_df = stats_overtime_df.style.format(
            subset=format_cols,
            formatter=format,
        ).background_gradient(
            subset=format_cols,
            cmap=cmap,
        )

        st.dataframe(stats_overtime_df, hide_index=True, use_container_width=True)
    else:
        st.info(
            "No columns selected for statistics calculation.", icon=":material/info:"
        )


def enumerator_report(
    project_id: str,
    data: pd.DataFrame,
    setting_file: str,
    missing_setting_file: str,
    page_num: int,
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
    ) = enumerator_report_settings(project_id, data, setting_file, page_num)
    display_enumerator_overview(
        data,
        date,
        enumerator,
        team,
    )

    display_enumerator_summary(
        data,
        missing_setting_file,
        date,
        enumerator,
        formdef_version,
        duration,
        consent,
        consent_vals,
        outcome,
        outcome_vals,
    )
    display_enumerator_productivity(
        data,
        date,
        enumerator,
        setting_file,
    )
    display_enumerator_statistics(
        data,
        date,
        enumerator,
        setting_file,
    )
    display_enumerator_statistics_overtime(
        data,
        date,
        enumerator,
        setting_file,
    )
