"""Enumerator performance analysis module for survey data quality checks.

This module provides comprehensive enumerator performance tracking with:
- Enumerator overview metrics and statistics
- Productivity tracking over time (daily, weekly, monthly)
- Summary tables with missing data, duration, consent, and outcome analysis
- Statistical analysis across enumerators
- Time-series analysis of enumerator performance
- Configurable settings with Pydantic validation
- Modular, testable architecture
- Polars-based data processing for performance
"""

from datetime import date as dt_date
from datetime import timedelta
from typing import Literal

import polars as pl
import streamlit as st
from pydantic import BaseModel, Field, field_validator

from datasure.checks import missing
from datasure.utils.dataframe_utils import ColumnByType
from datasure.utils.duckdb_utils import (
    duckdb_get_table,
    duckdb_save_table,
    load_missing_codes_from_db,
)
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

TAB_NAME: str = "enumerators"


# =============================================================================
# Pydantic Models for Data Validation
# =============================================================================


class EnumeratorSettings(BaseModel):
    """Settings for enumerator report configuration.

    Attributes
    ----------
    date : str | None
        Column name containing survey submission date.
    survey_id : str | None
        Column name containing survey ID.
    enumerator : str | None
        Column name containing enumerator identifier (required).
    formdef_version : str | None
        Column name containing form version.
    duration : str | None
        Column name containing survey duration in seconds.
    team : str | None
        Column name containing team identifier.
    consent : str | None
        Column name containing consent status.
    consent_vals : list[str] | None
        List of values indicating valid consent.
    outcome : str | None
        Column name containing survey outcome status.
    outcome_vals : list[str] | None
        List of values indicating completed surveys.
    """

    survey_key: str | None = Field(None, description="Survey key column")
    survey_id: str | None = Field(..., min_length=1, description="Survey ID column")
    survey_date: str | None = Field(None, description="Survey date column")
    enumerator: str | None = Field(None, description="Enumerator ID column")
    formversion: str | None = Field(None, description="Form version column")
    duration: str | None = Field(None, description="Duration column")
    duration_unit: str = Field("default='seconds'", description="Duration unit")
    team: str | None = Field(None, description="Team identifier column")


class ConsentOutcomeSettings(BaseModel):
    """Settings for consent and outcome configuration.

    Attributes
    ----------
    consent : str | None
        Column name containing consent status.
    consent_vals : list[str] | None
        List of values indicating valid consent.
    outcome : str | None
        Column name containing survey outcome status.
    outcome_vals : list[str] | None
        List of values indicating completed surveys.
    """

    consent: str | None = Field(None, description="Consent status column")
    consent_vals: list[str] | None = Field(None, description="Valid consent values")
    outcome: str | None = Field(None, description="Outcome status column")
    outcome_vals: list[str] | None = Field(None, description="Completed survey values")


class ProductivitySettings(BaseModel):
    """Settings for productivity analysis configuration.

    Attributes
    ----------
    view_option : str
        Time period for analysis: Daily, Weekly, or Monthly.
    weekstartday : str
        First day of the week for weekly analysis.
    """

    view_option: str = Field(default="Daily", description="Time period view")
    weekstartday: str = Field(default="Monday", description="Week start day")

    @field_validator("view_option")
    @classmethod
    def validate_view_option(cls, v: str) -> str:
        """Validate view option is one of the allowed values."""
        allowed = ["Daily", "Weekly", "Monthly"]
        if v not in allowed:
            raise ValueError(f"view_option must be one of {allowed}")
        return v

    @field_validator("weekstartday")
    @classmethod
    def validate_weekstartday(cls, v: str) -> str:
        """Validate weekstartday is one of the allowed values."""
        allowed = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        if v not in allowed:
            raise ValueError(f"weekstartday must be one of {allowed}")
        return v


# Constants for statistics options
ALLOWED_STATISTICS = [
    "count",
    "min",
    "mean",
    "median",
    "max",
    "std",
    "25th percentile",
    "75th percentile",
]
ALLOWED_STATISTICS_OVERTIME = ALLOWED_STATISTICS + ["missing"]
ALLOWED_TIME_PERIODS = ["Daily", "Weekly", "Monthly"]
WEEKDAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

# Maps weekday names to offset codes used in computation
WEEKDAY_OFFSET_MAP = {
    "Monday": "SUN",
    "Tuesday": "MON",
    "Wednesday": "TUE",
    "Thursday": "WED",
    "Friday": "THU",
    "Saturday": "FRI",
    "Sunday": "SAT",
}

# Maps offset codes to numeric values for week calculations
WEEKDAY_OFFSET_TO_NUMERIC = {
    "SUN": 0,
    "MON": 1,
    "TUE": 2,
    "WED": 3,
    "THU": 4,
    "FRI": 5,
    "SAT": 6,
}


class StatisticsSettings(BaseModel):
    """Settings for statistics analysis configuration.

    Attributes
    ----------
    statscols : list[str] | None
        Columns to compute statistics on.
    stats : list[str]
        Statistics to compute (count, mean, median, etc.).
    """

    statscols: list[str] | None = Field(None, description="Columns for statistics")
    stats: list[str] = Field(
        default=["count", "mean"], description="Statistics to compute"
    )

    @field_validator("stats")
    @classmethod
    def validate_stats(cls, v: list[str]) -> list[str]:
        """Validate that statistics are from allowed list."""
        for stat in v:
            if stat not in ALLOWED_STATISTICS:
                raise ValueError(
                    f"Invalid statistic: {stat}. Must be one of {ALLOWED_STATISTICS}"
                )
        return v


class StatisticsOvertimeSettings(BaseModel):
    """Settings for statistics over time analysis configuration.

    Attributes
    ----------
    period : str
        Time period for analysis (Daily, Weekly, Monthly).
    weekstartday : str
        First day of the week for weekly analysis.
    stat : str
        Statistic to compute over time.
    statscol : str | None
        Column to compute statistics on.
    """

    period_overtime: str = Field(default="Week", description="Time period for analysis")
    weekstartday: str = Field(default="Monday", description="Week start day")
    stat: str = Field(default="count", description="Statistic to compute")
    statscol: str | None = Field(None, description="Column for statistics")

    @field_validator("period_overtime")
    @classmethod
    def validate_period(cls, v: str) -> str:
        """Validate period is from allowed list."""
        if v not in ALLOWED_TIME_PERIODS:
            raise ValueError(
                f"Invalid period: {v}. Must be one of {ALLOWED_TIME_PERIODS}"
            )
        return v

    @field_validator("weekstartday")
    @classmethod
    def validate_weekstartday(cls, v: str) -> str:
        """Validate weekstartday is from allowed list."""
        if v not in WEEKDAY_NAMES:
            raise ValueError(
                f"Invalid weekstartday: {v}. Must be one of {WEEKDAY_NAMES}"
            )
        return v

    @field_validator("stat")
    @classmethod
    def validate_stat(cls, v: str) -> str:
        """Validate stat is from allowed list."""
        if v not in ALLOWED_STATISTICS_OVERTIME:
            raise ValueError(
                f"Invalid statistic: {v}. Must be one of {ALLOWED_STATISTICS_OVERTIME}"
            )
        return v


class EnumeratorOverviewMetrics(BaseModel):
    """Metrics for enumerator overview.

    Attributes
    ----------
    all_submissions : int
        Total number of submissions.
    num_active_enumerators : int
        Number of enumerators active in past 7 days.
    num_enumerators : int
        Total number of enumerators.
    num_teams : int | str
        Number of teams or 'n/a' if not available.
    min_submissions : int
        Minimum daily submissions.
    max_submissions : int
        Maximum daily submissions.
    avg_submissions : int
        Average daily submissions.
    pct_active_enumerators : str
        Percentage of active enumerators formatted as string.
    """

    all_submissions: int = Field(ge=0)
    num_active_enumerators: int = Field(ge=0)
    num_enumerators: int = Field(ge=0)
    num_teams: int | str
    min_submissions: int = Field(ge=0)
    max_submissions: int = Field(ge=0)
    avg_submissions: int = Field(ge=0)
    pct_active_enumerators: str


# =============================================================================
# Settings Management Functions
# =============================================================================


@st.cache_data(ttl=60)
def load_default_enumerator_settings(
    settings_file: str, config: EnumeratorSettings
) -> EnumeratorSettings:
    """Load and merge saved settings with default configuration.

    Loads previously saved duplicates report settings from the settings file
    and merges them with the provided default configuration. Saved settings
    take precedence over defaults.

    Cached for 60 seconds to reduce file I/O operations.

    Parameters
    ----------
    settings_file : str
        Path to the settings file containing saved configurations.
    config : DuplicatesSettings
        Default configuration to use as fallback for missing settings.

    Returns
    -------
    DuplicatesSettings
        Merged settings combining saved and default configurations.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME)

    default_settings: dict = dict(config)
    default_settings.update(saved_settings)

    return EnumeratorSettings(**default_settings)


def enumerator_report_settings(
    project_id: str,
    settings_file: str,
    data: pl.DataFrame,
    config: EnumeratorSettings,
    categorical_columns: list[str],
    datetime_columns: list[str],
) -> EnumeratorSettings:
    """Create and render the settings UI for duplicates report configuration.

    This function creates a comprehensive Streamlit UI for configuring
    duplicates report settings. It includes:
    - Survey identifiers (key and ID columns)
    - Survey date column selection
    - Enumerator ID column
    - Filtering conditions for targeted duplicate detection

    Settings are automatically saved to the settings file when changed
    and loaded from previous sessions if available.

    Parameters
    ----------
    project_id : str
        Unique project identifier for database operations.
    settings_file : str
        Path to settings file for saving/loading configurations.
    data : pl.DataFrame
        Dataset to analyze for duplicates.
    config : DuplicatesSettings
        Default configuration used as fallback values.
    categorical_columns : list[str]
        Available categorical columns for selection (survey key, ID, enumerator).
    datetime_columns : list[str]
        Available datetime columns for date selection.

    Returns
    -------
    DuplicatesSettings
        User-configured settings from the UI.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for enumerator report")
        st.write("---")

        default_settings = load_default_enumerator_settings(settings_file, config)

        # Survey Identifiers
        with st.container(border=True):
            st.subheader("Survey Identifiers")
            si1, si2, _ = st.columns(3)

            with si1:
                default_survey_key = default_settings.survey_key
                default_survey_key_index = (
                    categorical_columns.index(default_survey_key)
                    if default_survey_key and default_survey_key in categorical_columns
                    else None
                )
                survey_key = st.selectbox(
                    "Survey Key",
                    options=categorical_columns,
                    key="survey_key_enumerator",
                    help="Select the column that contains the survey key",
                    index=default_survey_key_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_key"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_key": survey_key})

            with si2:
                default_survey_id = default_settings.survey_id
                default_survey_id_index = (
                    categorical_columns.index(default_survey_id)
                    if default_survey_id and default_survey_id in categorical_columns
                    else None
                )
                survey_id = st.selectbox(
                    "Survey ID",
                    options=categorical_columns,
                    help="Select the column that contains the survey ID",
                    key="survey_id_enumerator",
                    index=default_survey_id_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_id"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_id": survey_id})

        with st.container(border=True):
            st.subheader("Survey Date")

            sd1, _, _ = st.columns(3)

            with sd1:
                default_survey_date = default_settings.survey_date
                default_survey_date_index = (
                    datetime_columns.index(default_survey_date)
                    if default_survey_date and default_survey_date in datetime_columns
                    else None
                )

                survey_date = st.selectbox(
                    "Survey Date",
                    options=datetime_columns,
                    help="Select the column that contains the survey date",
                    key="survey_date_enumerator",
                    index=default_survey_date_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_date"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"survey_date": survey_date}
                )

        with st.container(border=True):
            st.subheader("Enumerator")
            ec1, ec2, _ = st.columns(3)
            with ec1:
                default_enumerator = default_settings.enumerator
                default_enumerator_index = (
                    categorical_columns.index(default_enumerator)
                    if default_enumerator and default_enumerator in categorical_columns
                    else None
                )
                enumerator = st.selectbox(
                    "Enumerator ID",
                    options=categorical_columns,
                    key="enumerator_enumerator",
                    help="Select the column that contains the enumerator ID",
                    index=default_enumerator_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_enumerator"},
                )
                save_check_settings(settings_file, TAB_NAME, {"enumerator": enumerator})

            with ec2:
                default_team = default_settings.team
                default_team_index = (
                    categorical_columns.index(default_team)
                    if default_team and default_team in categorical_columns
                    else None
                )
                team = st.selectbox(
                    "Team",
                    options=categorical_columns,
                    key="team_enumerator",
                    help="Select the column that contains the team identifier",
                    index=default_team_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_team"},
                )
                save_check_settings(settings_file, TAB_NAME, {"team": team})

        with st.container(border=True):
            st.subheader("Survey Duration")
            dc1, dc2, _ = st.columns(3)
            with dc1:
                default_duration = default_settings.duration
                default_duration_index = (
                    categorical_columns.index(default_duration)
                    if default_duration and default_duration in categorical_columns
                    else None
                )
                duration = st.selectbox(
                    "Duration Column",
                    options=categorical_columns,
                    key="duration_enumerator",
                    help="Select the column that contains the survey duration in seconds",
                    index=default_duration_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_duration"},
                )
                save_check_settings(settings_file, TAB_NAME, {"duration": duration})

            with dc2:
                default_duration_unit = default_settings.duration_unit
                default_duration_unit_index = (
                    ["seconds", "minutes", "hours"].index(default_duration_unit)
                    if default_duration_unit in ["seconds", "minutes", "hours"]
                    else 0
                )
                duration_unit = st.selectbox(
                    "Duration Unit",
                    options=["seconds", "minutes", "hours"],
                    key="duration_unit_enumerator",
                    help="Select the unit for survey duration",
                    index=default_duration_unit_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_duration_unit"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"duration_unit": duration_unit}
                )

        with st.container(border=True):
            st.subheader("Form Version")
            fv1, _ = st.columns([1, 2])
            with fv1:
                default_formversion = default_settings.formversion
                default_formversion_index = (
                    categorical_columns.index(default_formversion)
                    if default_formversion
                    and default_formversion in categorical_columns
                    else None
                )
                formversion = st.selectbox(
                    "Form Version Column",
                    options=categorical_columns,
                    key="formversion_enumerator",
                    help="Select the column that contains the form version",
                    index=default_formversion_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_formversion"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"formversion": formversion}
                )

        with st.container(border=True):
            st.subheader("Consent and Outcome Settings")
            st.info(
                "Configure consent and outcome columns along with their valid values."
            )

            _render_consent_outcome_settings(
                project_id, data, categorical_columns, settings_file
            )
            if st.session_state.get("st_apply_consent_outcome_enumerator"):
                st.success("Consent and outcome settings applied successfully.")
                st.session_state["st_apply_consent_outcome_enumerator"] = False

    return EnumeratorSettings(
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        enumerator=enumerator,
        team=team,
        formversion=formversion,
        duration=duration,
        duration_unit=duration_unit,
    )


@st.fragment
def _render_consent_outcome_settings(
    project_id: str, data: pl.DataFrame, categorical_columns: list, settings_file: str
) -> ConsentOutcomeSettings:
    """Render consent and outcome settings UI.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    settings_file : str
        Path to settings file for saving/loading configurations.

    Returns
    -------
    ConsentOutcomeSettings
        User-configured consent and outcome settings.
    """
    default_settings = load_check_settings(settings_file, TAB_NAME)

    with st.container(border=True):
        st.subheader("Consent Settings")
        co1, co2 = st.columns([0.3, 0.7])
        with co1:
            default_consent_col = default_settings.get("consent")
            default_consent_index = (
                categorical_columns.index(default_consent_col)
                if default_consent_col and default_consent_col in categorical_columns
                else 0
            )
            consent_col = st.selectbox(
                "Consent Column",
                options=categorical_columns,
                help="Select the column that contains consent status",
                key="consent_enumerator",
                index=default_consent_index,
                on_change=trigger_save,
                kwargs={"state_name": TAB_NAME + "_consent"},
            )
            save_check_settings(settings_file, TAB_NAME, {"consent": consent_col})

        with co2:
            default_consent_vals = default_settings.get("consent_vals", [])
            consent_val_options = data[consent_col].unique().to_list()
            consent_vals = st.multiselect(
                "Valid Consent Values",
                options=consent_val_options,
                default=default_consent_vals,
                help="Select values that indicate valid consent",
                key="consent_vals_enumerator",
                on_change=trigger_save,
                kwargs={"state_name": TAB_NAME + "_consent_vals"},
            )
            save_check_settings(settings_file, TAB_NAME, {"consent_vals": consent_vals})

    with st.container(border=True):
        st.subheader("Outcome Settings")
        oo1, oo2 = st.columns([0.3, 0.7])
        with oo1:
            default_outcome_col = default_settings.get("outcome")
            default_outcome_index = (
                categorical_columns.index(default_outcome_col)
                if default_outcome_col and default_outcome_col in categorical_columns
                else 0
            )
            outcome_col = st.selectbox(
                "Outcome Column",
                options=categorical_columns,
                help="Select the column that contains survey outcome status",
                key="outcome_enumerator",
                index=default_outcome_index,
                on_change=trigger_save,
                kwargs={"state_name": TAB_NAME + "_outcome"},
            )
            save_check_settings(settings_file, TAB_NAME, {"outcome": outcome_col})

        with oo2:
            default_outcome_vals = default_settings.get("outcome_vals", [])
            outcome_val_options = data[outcome_col].unique().to_list()
            outcome_vals = st.multiselect(
                "Completed Survey Values",
                options=outcome_val_options,
                default=default_outcome_vals,
                help="Select values that indicate completed surveys",
                key="outcome_vals_enumerator",
                on_change=trigger_save,
                kwargs={"state_name": TAB_NAME + "_outcome_vals"},
            )
            save_check_settings(settings_file, TAB_NAME, {"outcome_vals": outcome_vals})

        config_dict = {
            "consent": consent_col,
            "consent_vals": consent_vals,
            "outcome": outcome_col,
            "outcome_vals": outcome_vals,
        }
        config = ConsentOutcomeSettings(**config_dict)

    if st.button(
        "Apply Consent and Outcome Settings",
        key="apply_consent_outcome_enumerator",
        type="primary",
        width="stretch",
    ):
        _create_enum_data_on_settings(project_id, data, config)
        _trigger_success_message("st_apply_consent_outcome_enumerator")
        st.rerun()


def _trigger_success_message(button_key: str) -> None:
    """Trigger a success message after button click.

    Parameters
    ----------
    button_key : str
        Unique key of the button to associate the success message with.
    """
    st.session_state[f"{button_key}"] = True


def _create_enum_data_on_settings(
    project_id: str,
    data: pl.DataFrame,
    config: ConsentOutcomeSettings,
) -> None:
    """Create enumerator data based on consent and outcome settings.

    Parameters
    ----------
    project_id : str
        Unique project identifier for database operations.
    data : pl.DataFrame
        DataFrame containing survey data.
    conditions : ConsentOutcomeSettings
        Consent and outcome configuration settings.
    """
    # If consent and consent values are provided, create a dummy column indicating
    # valid consent else set to 1

    if config.consent and config.consent_vals:
        enum_data = data.with_columns(
            pl.col(config.consent)
            .is_in(config.consent_vals)
            .cast(pl.Int32)
            .alias("consent_granted_agg_col")
        )
    else:
        enum_data = data.with_columns(
            pl.lit(1).cast(pl.Int32).alias("consent_granted_agg_col")
        )

    if config.outcome and config.outcome_vals:
        enum_data = enum_data.with_columns(
            pl.col(config.outcome)
            .is_in(config.outcome_vals)
            .cast(pl.Int32)
            .alias("completed_survey_agg_col")
        )
    else:
        enum_data = enum_data.with_columns(
            pl.lit(1).cast(pl.Int32).alias("completed_survey_agg_col")
        )

    # save to database
    duckdb_save_table(
        project_id,
        enum_data,
        "enumerator_data_with_consent_outcome",
        "intermediate",
    )


# =============================================================================
# Overview Computation Functions
# =============================================================================


def compute_enumerator_overview(
    data: pl.DataFrame, date: str, enumerator: str, team: str | None
) -> EnumeratorOverviewMetrics:
    """Compute enumerator overview metrics.

    Calculates key metrics including total submissions, active enumerators,
    team counts, and submission statistics.

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name (optional).

    Returns
    -------
    EnumeratorOverviewMetrics
        Overview metrics for enumerators including counts and statistics.
    """
    if data.is_empty():
        raise ValueError(
            "Input data is empty. Cannot compute enumerator overview metrics."
        )
    data = data.sort([enumerator, date])

    all_submissions = data.height

    # Calculate daily submissions
    data = data.with_row_index(name="TOKEN KEY")
    daily_submissions_sum = data.group_by([date, enumerator]).agg(
        pl.col("TOKEN KEY").count().alias("count")
    )

    # Calculate active enumerators (past 7 days)
    from datetime import date as dt_date
    from datetime import timedelta

    active_date_cut_off = dt_date.today() - timedelta(weeks=1)

    daily_submissions_sum = daily_submissions_sum.with_columns(
        (pl.col(date).cast(pl.Date) > active_date_cut_off).alias("active")
    )

    num_active_enumerators = (
        daily_submissions_sum.filter(pl.col("active"))
        .select(pl.col(enumerator).n_unique())
        .item()
    )

    num_enumerators = data[enumerator].n_unique()
    num_teams = data[team].n_unique() if team else "n/a"
    min_submissions = int(daily_submissions_sum["count"].min())
    max_submissions = int(daily_submissions_sum["count"].max())
    avg_submissions = int(daily_submissions_sum["count"].mean())

    pct_active_enumerators = f"{(num_active_enumerators / num_enumerators) * 100:.0f}%"

    return EnumeratorOverviewMetrics(
        all_submissions=all_submissions,
        num_active_enumerators=num_active_enumerators,
        num_enumerators=num_enumerators,
        num_teams=num_teams,
        min_submissions=min_submissions,
        max_submissions=max_submissions,
        avg_submissions=avg_submissions,
        pct_active_enumerators=pct_active_enumerators,
    )


def compute_enumerator_missing_table(
    data: pl.DataFrame, missing_codes_config: pl.DataFrame, group_by_col: list[str]
) -> pl.DataFrame:
    """Compute missing data statistics per enumerator.

    Calculates missing data counts and percentages for each enumerator
    based on provided missing codes configuration.

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    missing_settings_file : str
        Path to missing codes configuration file.
    enumerator : str
        Enumerator column name.

    Returns
    -------
    pl.DataFrame
        DataFrame with missing data statistics per enumerator.
    """
    # define columns to exclude from missing data stats
    columns_to_exclude = ["consent_granted_agg_col", "completed_survey_agg_col"]

    data_for_missing = data.select(
        [col for col in data.columns if col not in columns_to_exclude]
    )

    # Metadata for missing data calculation
    enum_data_missing = data_for_missing.select(group_by_col)

    # If missing_codes_config is empty, calculate only null missingness
    if missing_codes_config.is_empty():
        # Calculate overall null missingness per enumerator
        columns_to_check = [
            col for col in data_for_missing.columns if col not in group_by_col
        ]

        # Count nulls per row and calculate percentage
        missing_summary = data_for_missing.with_columns(
            [
                pl.sum_horizontal(
                    [pl.col(col).is_null().cast(pl.Int32) for col in columns_to_check]
                ).alias("_null_count"),
                pl.lit(len(columns_to_check)).alias("_total_fields"),
            ]
        ).with_columns(
            (pl.col("_null_count") / pl.col("_total_fields") * 100).alias(
                "% Null values"
            )
        )

        # Group by enumerator and calculate mean missingness rate
        result_df = missing_summary.group_by(group_by_col, maintain_order=True).agg(
            pl.col("% Null values").mean()
        )

        return result_df

    # If missing_codes_config is provided, calculate missingness by category
    # Get missing code pairs from the config
    missing_code_pairs = missing._get_missing_code_pairs(missing_codes_config)

    # Compute missing data with paired encoding
    missing_data_encoded = missing._compute_missing_data_paired(
        data_for_missing, missing_codes_config
    )

    # Get columns to check (exclude enumerator column)
    columns_to_check = [
        col for col in missing_data_encoded.columns if col not in group_by_col
    ]
    total_fields = len(columns_to_check)

    # Calculate counts for each missing category per row
    agg_expressions = []

    # Add null values count (encoded as 1)
    agg_expressions.append(
        pl.sum_horizontal(
            [(pl.col(col) == 1).cast(pl.Int32) for col in columns_to_check]
        ).alias("_null_count")
    )

    # Add count for each special missing code category (starting from 2)
    for idx, label in enumerate(missing_code_pairs.keys(), start=2):
        agg_expressions.append(
            pl.sum_horizontal(
                [(pl.col(col) == idx).cast(pl.Int32) for col in columns_to_check]
            ).alias(f"_{label}_count")
        )

    # Add total missing count (any value > 0)
    agg_expressions.append(
        pl.sum_horizontal(
            [(pl.col(col) > 0).cast(pl.Int32) for col in columns_to_check]
        ).alias("_total_missing_count")
    )

    # Add total fields count
    agg_expressions.append(pl.lit(total_fields).alias("_total_fields"))

    # Apply the aggregations
    missing_counts = missing_data_encoded.select(
        [pl.col(group_by_col)] + agg_expressions
    )

    # Calculate percentages
    percentage_expressions = []

    # Null values percentage
    percentage_expressions.append(
        (pl.col("_null_count") / pl.col("_total_fields") * 100).alias("% Null values")
    )

    # Special missing code category percentages
    for label in missing_code_pairs:
        percentage_expressions.append(
            (pl.col(f"_{label}_count") / pl.col("_total_fields") * 100).alias(
                f"% {label}"
            )
        )

    # Total missing percentage
    percentage_expressions.append(
        (pl.col("_total_missing_count") / pl.col("_total_fields") * 100).alias(
            "% Total Missing"
        )
    )

    missing_with_percentages = missing_counts.with_columns(percentage_expressions)

    # Group by enumerator and calculate mean percentages
    final_agg_expressions = [pl.col("% Null values").mean()]

    for label in missing_code_pairs:
        final_agg_expressions.append(pl.col(f"% {label}").mean())

    final_agg_expressions.append(pl.col("% Total Missing").mean())

    # drop enumerator column from missing_with_percentages
    missing_with_percentages = missing_with_percentages.select(
        [col for col in missing_with_percentages.columns if col not in group_by_col]
    )
    # merge missing_with_percentages with enumerator column
    missing_with_percentages = pl.concat(
        [enum_data_missing, missing_with_percentages], how="horizontal"
    )

    result_df = missing_with_percentages.group_by(
        group_by_col, maintain_order=True
    ).agg(final_agg_expressions)

    return result_df


def compute_enumerator_summary(
    project_id: str,
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    formversion: str | None,
    duration: str | None,
) -> pl.DataFrame:
    """Compute comprehensive enumerator summary statistics.

    Calculates submission counts, date ranges, duration statistics,
    form version tracking, consent rates, outcome rates, and missing data
    patterns for each enumerator.

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    missing_settings_file : str
        Path to missing codes configuration file.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    formdef_version : str | None
        Form version column name (optional).
    duration : str | None
        Duration column name (optional).
    consent : str | None
        Consent column name (optional).
    consent_vals : list[str] | None
        List of values indicating valid consent (optional).
    outcome : str | None
        Outcome column name (optional).
    outcome_vals : list[str] | None
        List of values indicating completed surveys (optional).

    Returns
    -------
    pl.DataFrame
        Comprehensive summary DataFrame with enumerator statistics.
    """
    group_by_cols = [enumerator, team] if team else [enumerator]
    # Format date column
    df = data.with_columns(pl.col(date).dt.strftime("%b %d, %Y").alias(date))

    # Basic summary aggregations
    summary_df = df.group_by(group_by_cols, maintain_order=True).agg(
        [
            pl.col(date).min().alias("first submission"),
            pl.col(date).max().alias("last submission"),
            pl.col(date).count().alias("# submissions"),
            pl.col(date).n_unique().alias("# unique dates"),
        ]
    )

    # Calculate time-based submissions
    today = dt_date.today()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    today_str = today.strftime("%b %d, %Y")
    week_str = start_of_week.strftime("%b %d, %Y")
    month_str = start_of_month.strftime("%b %d, %Y")

    df = df.with_columns(
        [
            (pl.col(date) == today_str).alias("submitted_today"),
            (pl.col(date) >= week_str).alias("submitted_this_week"),
            (pl.col(date) >= month_str).alias("submitted_this_month"),
        ]
    )

    lagged_df = df.group_by(group_by_cols, maintain_order=True).agg(
        [
            pl.col("submitted_today").sum().alias("# submissions today"),
            pl.col("submitted_this_week").sum().alias("# submissions this week"),
            pl.col("submitted_this_month").sum().alias("# submissions this month"),
        ]
    )

    summary_df = summary_df.join(lagged_df, on=group_by_cols, how="left")

    # Add missing data statistics
    missing_settings_file = load_missing_codes_from_db(project_id)
    enumerator_missing_df = compute_enumerator_missing_table(
        data, missing_settings_file, group_by_cols
    )
    summary_df = summary_df.join(enumerator_missing_df, on=group_by_cols, how="left")

    # Add duration statistics if available
    if duration:
        duration_df = df.group_by(group_by_cols, maintain_order=True).agg(
            [
                pl.col(duration).min().alias("min duration"),
                pl.col(duration).mean().alias("mean duration"),
                pl.col(duration).median().alias("median duration"),
                pl.col(duration).max().alias("max duration"),
            ]
        )
        summary_df = summary_df.join(duration_df, on=group_by_cols, how="left")

    # Add form version statistics if available
    if formversion:
        # Get latest form version per date
        formdef_outdated = df.group_by(date, maintain_order=True).agg(
            pl.col(formversion).max().alias("latest daily form version")
        )

        df = df.join(formdef_outdated, on=date, how="left")
        df = df.with_columns(
            (pl.col(formversion) != pl.col("latest daily form version")).alias(
                "outdated_form_version"
            )
        )

        formdef_outdated_df = df.group_by(group_by_cols, maintain_order=True).agg(
            pl.col("outdated_form_version").sum().alias("# of outdated form versions")
        )

        formdef_df = df.group_by(group_by_cols, maintain_order=True).agg(
            [
                pl.col(formversion).n_unique().alias("# form versions"),
                pl.col(formversion).max().alias("latest form version"),
            ]
        )

        latest_enum_formversion = df.group_by(group_by_cols, maintain_order=True).agg(
            pl.col(formversion).max().alias("last form version")
        )

        summary_df = summary_df.join(formdef_df, on=group_by_cols, how="left")
        summary_df = summary_df.join(formdef_outdated_df, on=group_by_cols, how="left")
        summary_df = summary_df.join(
            latest_enum_formversion, on=group_by_cols, how="left"
        )

    # Add consent statistics if available
    if "consent_granted_agg_col" in df.columns:
        consent_df = df.group_by(group_by_cols, maintain_order=True).agg(
            pl.col("consent_granted_agg_col").mean().alias("% consent")
        )
        summary_df = summary_df.join(consent_df, on=group_by_cols, how="left")

    # Add outcome statistics if available
    if "completed_survey_agg_col" in df.columns:
        outcome_df = df.group_by(group_by_cols, maintain_order=True).agg(
            pl.col("completed_survey_agg_col").mean().alias("% completed survey")
        )
        summary_df = summary_df.join(outcome_df, on=group_by_cols, how="left")

    return summary_df


# =============================================================================
# Productivity Computation Functions
# =============================================================================


def compute_enumerator_productivity(
    data: pl.DataFrame,
    date: str,
    group_by_cols: list[str],
    period: str,
    weekstartday: str,
) -> pl.DataFrame:
    """Compute enumerator productivity over time.

    Analyzes submission counts by enumerator across time periods (daily,
    weekly, or monthly).

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    period : str
        Time period: "Daily", "Weekly", "Monthly", "Day", "Week", or "Month".
    weekstartday : str
        Start day of the week (e.g., "SUN", "MON") for weekly analysis.

    Returns
    -------
    pl.DataFrame
        Pivoted DataFrame with enumerators as rows and time periods as columns.
    """
    prod_df = data.clone()

    # Normalize period values to handle both old and new formats
    period_normalized = period
    if period == "Day":
        period_normalized = "Daily"
    elif period == "Week":
        period_normalized = "Weekly"
    elif period == "Month":
        period_normalized = "Monthly"

    # Create time period column based on selection with user-friendly formatting
    if period_normalized == "Daily":
        # Format as "Jan 1, 2025"
        prod_df = prod_df.with_columns(
            pl.col(date).dt.strftime("%b %d, %Y").alias("TIME PERIOD")
        )
    elif period_normalized == "Weekly":
        # Calculate week start and end dates for user-friendly display
        offset = WEEKDAY_OFFSET_TO_NUMERIC.get(weekstartday, 1)

        # Calculate the week start date (beginning of the week containing this date)
        # weekday() returns 0=Monday, 6=Sunday
        prod_df = prod_df.with_columns(
            [
                # Calculate days since the start of the week
                ((pl.col(date).dt.weekday() - offset + 7) % 7).alias(
                    "_days_since_week_start"
                ),
            ]
        )

        # Calculate week_start_date by subtracting days_since_week_start
        prod_df = prod_df.with_columns(
            [
                (
                    pl.col(date) - pl.duration(days=pl.col("_days_since_week_start"))
                ).alias("_week_start"),
                (
                    pl.col(date)
                    - pl.duration(days=pl.col("_days_since_week_start"))
                    + pl.duration(days=6)
                ).alias("_week_end"),
            ]
        )

        # Format as "Jan 1, 2025 to Jan 7, 2025"
        prod_df = prod_df.with_columns(
            (
                pl.col("_week_start").dt.strftime("%b %d, %Y")
                + " to "
                + pl.col("_week_end").dt.strftime("%b %d, %Y")
            ).alias("TIME PERIOD")
        )
    elif period_normalized == "Monthly":
        # Format as "January 2025"
        prod_df = prod_df.with_columns(
            pl.col(date).dt.strftime("%B %Y").alias("TIME PERIOD")
        )

    # Count submissions per period and enumerator
    prod_df = prod_df.with_row_index(name="TOKEN KEY")
    prod_res = prod_df.group_by(
        ["TIME PERIOD"] + group_by_cols, maintain_order=True
    ).agg(pl.col("TOKEN KEY").count().alias("submissions"))

    # Pivot to wide format
    prod_res = prod_res.pivot(
        index=group_by_cols,
        on="TIME PERIOD",
        values="submissions",
    ).fill_null(0)

    return prod_res


# =============================================================================
# Statistics Computation Functions
# =============================================================================


@st.cache_data(ttl=300)
def compute_enumerator_statistics(
    data: pl.DataFrame,
    group_by_cols: list[str],
    statscols: list[str],
    stats: list[str],
) -> pl.DataFrame:
    """Compute enumerator statistics across specified columns.

    Calculates summary statistics (mean, median, std, etc.) for numeric
    columns grouped by enumerator (and optionally team).

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    group_by_cols : list[str]
        List of columns to group by (e.g., ["enumerator"] or ["enumerator", "team"]).
    statscols : list[str]
        List of columns to compute statistics on.
    stats : list[str]
        List of statistics to compute (e.g., ["mean", "median", "std"]).

    Returns
    -------
    pl.DataFrame
        DataFrame with enumerators (and teams) and computed statistics.
    """
    # Map stat names to Polars expressions
    stat_mapping = {
        "count": "count",
        "min": "min",
        "mean": "mean",
        "median": "median",
        "max": "max",
        "std": "std",
        "25th percentile": "quantile",
        "75th percentile": "quantile",
    }

    agg_exprs = []
    for col in statscols:
        for stat in stats:
            if stat == "25th percentile":
                agg_exprs.append(pl.col(col).quantile(0.25).alias(f"{col}_{stat}"))
            elif stat == "75th percentile":
                agg_exprs.append(pl.col(col).quantile(0.75).alias(f"{col}_{stat}"))
            else:
                method = stat_mapping.get(stat, stat)
                agg_exprs.append(getattr(pl.col(col), method)().alias(f"{col}_{stat}"))

    stats_res = data.group_by(group_by_cols, maintain_order=True).agg(agg_exprs)

    return stats_res


def compute_enumerator_statistics_overtime(
    data: pl.DataFrame,
    date: str,
    group_by_cols: list[str],
    statscol: str,
    stat: str,
    period: str,
    weekstartday: str,
) -> pl.DataFrame:
    """Compute enumerator statistics over time for a specific column.

    Analyzes how a specific statistic changes over time periods for each
    enumerator (and optionally team).

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    group_by_cols : list[str]
        List of columns to group by (e.g., ["enumerator"] or ["enumerator", "team"]).
    statscol : str
        Column to compute statistics on.
    stat : str
        Statistic to compute (e.g., "mean", "median", "missing").
    period : str
        Time period: "Daily", "Weekly", "Monthly", "Day", "Week", or "Month".
    weekstartday : str
        Start day of the week for weekly analysis.

    Returns
    -------
    pl.DataFrame
        Pivoted DataFrame with enumerators (and teams) as rows and time
        periods as columns.
    """
    stats_overtime_df = data.select([date] + group_by_cols + [statscol]).clone()

    # Normalize period values to handle both old and new formats
    period_normalized = period
    if period == "Day":
        period_normalized = "Daily"
    elif period == "Week":
        period_normalized = "Weekly"
    elif period == "Month":
        period_normalized = "Monthly"

    # Create time period column with user-friendly formatting
    if period_normalized == "Daily":
        # Format as "Jan 1, 2025"
        stats_overtime_df = stats_overtime_df.with_columns(
            pl.col(date).dt.strftime("%b %d, %Y").alias("TIME PERIOD")
        )
    elif period_normalized == "Weekly":
        # Calculate week start and end dates for user-friendly display
        offset = WEEKDAY_OFFSET_TO_NUMERIC.get(weekstartday, 1)

        # Calculate the week start date (beginning of the week containing this date)
        # weekday() returns 0=Monday, 6=Sunday
        stats_overtime_df = stats_overtime_df.with_columns(
            [
                # Calculate days since the start of the week
                ((pl.col(date).dt.weekday() - offset + 7) % 7).alias(
                    "_days_since_week_start"
                ),
            ]
        )

        # Calculate week_start_date by subtracting days_since_week_start
        stats_overtime_df = stats_overtime_df.with_columns(
            [
                (
                    pl.col(date) - pl.duration(days=pl.col("_days_since_week_start"))
                ).alias("_week_start"),
                (
                    pl.col(date)
                    - pl.duration(days=pl.col("_days_since_week_start"))
                    + pl.duration(days=6)
                ).alias("_week_end"),
            ]
        )

        # Format as "Jan 1, 2025 to Jan 7, 2025"
        stats_overtime_df = stats_overtime_df.with_columns(
            (
                pl.col("_week_start").dt.strftime("%b %d, %Y")
                + " to "
                + pl.col("_week_end").dt.strftime("%b %d, %Y")
            ).alias("TIME PERIOD")
        )
    elif period_normalized == "Monthly":
        # Format as "January 2025"
        stats_overtime_df = stats_overtime_df.with_columns(
            pl.col(date).dt.strftime("%B %Y").alias("TIME PERIOD")
        )

    # Calculate statistic
    if stat == "missing":
        stats_overtime_res = stats_overtime_df.group_by(
            ["TIME PERIOD"] + group_by_cols, maintain_order=True
        ).agg(pl.col(statscol).is_null().mean().alias("_STAT"))
    elif stat == "25th percentile":
        stats_overtime_res = stats_overtime_df.group_by(
            ["TIME PERIOD"] + group_by_cols, maintain_order=True
        ).agg(pl.col(statscol).quantile(0.25).alias("_STAT"))
    elif stat == "75th percentile":
        stats_overtime_res = stats_overtime_df.group_by(
            ["TIME PERIOD"] + group_by_cols, maintain_order=True
        ).agg(pl.col(statscol).quantile(0.75).alias("_STAT"))
    else:
        stats_overtime_res = stats_overtime_df.group_by(
            ["TIME PERIOD"] + group_by_cols, maintain_order=True
        ).agg(getattr(pl.col(statscol), stat)().alias("_STAT"))

    # Pivot to wide format
    stats_overtime_res = stats_overtime_res.pivot(
        index=group_by_cols, on="TIME PERIOD", values="_STAT"
    )

    return stats_overtime_res


# =============================================================================
# Display Functions - Overview
# =============================================================================


def _render_enumerator_overview_metrics(
    data: pl.DataFrame, date: str, enumerator: str, team: str | None
) -> None:
    """Display enumerator overview metrics.

    Shows key metrics including total submissions, active enumerators,
    team counts, and submission statistics in a grid layout.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name (optional).
    """
    if not (enumerator and date):
        st.info(
            "Enumerator overview requires a date and enumerator column to be selected. "
            "Go to the :material/settings: settings section above to select them."
        )
        return

    metrics: EnumeratorOverviewMetrics = compute_enumerator_overview(
        data, date, enumerator, team
    )

    tc1, tc2, tc3, tc4 = st.columns(4, border=True)
    num_enumerators_formatted = (
        f"{metrics.num_enumerators:,}"
        if isinstance(metrics.num_enumerators, int)
        else metrics.num_enumerators
    )
    tc1.metric(
        r"\# of enumerators",
        num_enumerators_formatted,
        help="Total unique enumerators in the dataset",
    )
    num_teams_formatted = (
        f"{metrics.num_teams:,}"
        if isinstance(metrics.num_teams, int)
        else metrics.num_teams
    )
    tc2.metric(
        r"\# of teams", num_teams_formatted, help="Total unique teams in the dataset"
    )
    num_active_enumerators_formatted = f"{metrics.num_active_enumerators:,}"
    tc3.metric(
        r"\# of Active enumerators (past 7 days)",
        num_active_enumerators_formatted,
        help="Number of enumerators with submissions in the past 7 days",
    )
    pct_active_enumerators_formatted = f"{metrics.pct_active_enumerators}"
    tc4.metric(
        "% of active enumerator (past 7 days)",
        pct_active_enumerators_formatted,
        help="Percentage of enumerators active in the past 7 days",
    )

    bc1, bc2, bc3, bc4 = st.columns(4, border=True)
    min_submissions_formatted = f"{metrics.min_submissions:,}"
    bc1.metric(
        "Fewest enumerator submissions",
        min_submissions_formatted,
        help="Minimum number of submissions by any enumerator",
    )
    max_submissions_formatted = f"{metrics.max_submissions:,}"
    bc2.metric(
        "Highest enumerator submissions",
        max_submissions_formatted,
        help="Maximum number of submissions by any enumerator",
    )
    avg_submissions_formatted = f"{metrics.avg_submissions:,}"
    bc3.metric(
        "Average enumerator submissions",
        avg_submissions_formatted,
        help="Average number of submissions per enumerator",
    )
    all_submissions_formatted = f"{metrics.all_submissions:,}"
    bc4.metric(
        "Total survey submissions",
        all_submissions_formatted,
        help="Total number of survey submissions in the dataset",
    )


@st.fragment
def _render_enumerator_summary_table(
    project_id: str,
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    formversion: str | None,
    duration: str | None,
) -> None:
    """Display enumerator summary table.

    Shows comprehensive enumerator statistics including submission counts,
    duration, missing data, consent rates, and outcome rates with styled
    formatting.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    missing_settings_file : str
        Path to missing codes configuration file.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    formdef_version : str | None
        Form version column name (optional).
    duration : str | None
        Duration column name (optional).
    consent : str | None
        Consent column name (optional).
    consent_vals : list[str] | None
        Valid consent values (optional).
    outcome : str | None
        Outcome column name (optional).
    outcome_vals : list[str] | None
        Completed survey values (optional).
    """
    if not (enumerator and date):
        st.info(
            "Enumerator summary requires a date and enumerator column to be selected. "
            "Go to the :material/settings: settings section above to select them."
        )
        return

    summary_df = compute_enumerator_summary(
        project_id,
        data,
        date,
        enumerator,
        team,
        formversion,
        duration,
    )

    options_map = {
        "submissions": ":material/arrow_upload_progress: Submissions",
        "missing": ":material/incomplete_circle: Missing Data",
        "duration": ":material/timer: Duration",
        "formversion": ":material/difference: Form Version",
        "consent_outcome": ":material/check_circle: Consent & Outcome",
    }
    with st.container(horizontal_alignment="left"):
        show_info = st.pills(
            "Select Summary Information to Display",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            key="show_info_enumerator",
            help="Select which summary information to display in the table",
            selection_mode="multi",
        )

    # Define column groups
    column_groups = {
        "submissions": [
            "first submission",
            "last submission",
            "# submissions",
            "# unique dates",
            "# submissions today",
            "# submissions this week",
            "# submissions this month",
        ],
        "missing": [
            col
            for col in summary_df.columns
            if "%" in col
            and (
                "Null" in col
                or "Missing" in col
                or any(
                    keyword in col
                    for keyword in ["Don't Know", "Refuse", "Not Applicable"]
                )
            )
        ],
        "duration": [
            "min duration",
            "mean duration",
            "median duration",
            "max duration",
        ],
        "formversion": [
            "# form versions",
            "latest form version",
            "last form version",
            "# of outdated form versions",
        ],
        "consent_outcome": [
            "% consent",
            "% completed survey",
        ],
    }

    # Always include enumerator and # submissions
    columns_to_show = (
        [enumerator, team, "# submissions"] if team else [enumerator, "# submissions"]
    )

    # Filter columns based on selection
    if show_info:
        # Add columns from selected categories
        for category in show_info:
            columns_to_show.extend(
                [
                    col
                    for col in column_groups[category]
                    if col in summary_df.columns and col not in columns_to_show
                ]
            )

        # Filter the dataframe
        filtered_df = summary_df.select(columns_to_show)
    else:
        # Show all columns if nothing is selected
        filtered_df = summary_df

    # Display using Streamlit's native dataframe display
    # create column config for enumerator and team conditionally
    # Build column configuration dynamically
    column_config = {
        enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
    }

    # Add team column if available
    if team:
        column_config[team] = st.column_config.TextColumn("Team", pinned=True)

    # Add remaining columns
    column_config.update(
        {
            "# submissions": st.column_config.NumberColumn(
                "# of Submissions", format="%d", pinned=True
            ),
            "# unique dates": st.column_config.NumberColumn("# of Days", format="%d"),
            "# submissions today": st.column_config.NumberColumn(
                "# submitted Today", format="%d"
            ),
            "# submissions this week": st.column_config.NumberColumn(
                "# submitted This Week", format="%d"
            ),
            "# submissions this month": st.column_config.NumberColumn(
                "# submitted This Month", format="%d"
            ),
            "% Null values": st.column_config.NumberColumn(
                "% Null Values", format="%.2f%%"
            ),
            "% Total Missing": st.column_config.NumberColumn(
                "% Total Missing", format="%.2f%%"
            ),
            "% consent": st.column_config.NumberColumn("% Consent", format="%.2f%%"),
            "% completed survey": st.column_config.NumberColumn(
                "% Completed", format="%.2f%%"
            ),
            "min duration": st.column_config.NumberColumn(
                "Min Duration (s)", format="%.2f"
            ),
            "mean duration": st.column_config.NumberColumn(
                "Mean Duration (s)", format="%.2f"
            ),
            "median duration": st.column_config.NumberColumn(
                "Median Duration (s)", format="%.2f"
            ),
            "max duration": st.column_config.NumberColumn(
                "Max Duration (s)", format="%.2f"
            ),
        }
    )

    st.dataframe(
        filtered_df,
        hide_index=True,
        width="stretch",
        column_config=column_config,
    )


# =============================================================================
# Display Functions - Productivity
# =============================================================================


def _render_enumerator_productivity(
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    settings_file: str,
) -> None:
    """Display enumerator productivity table.

    Shows submission counts by enumerator over time with configurable
    time periods (daily, weekly, monthly).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    if not (enumerator and date):
        st.info(
            "Enumerator productivity requires a date and enumerator column to be selected. "
            "Go to the :material/settings: settings section above to select them."
        )
        return

    _render_enumerator_productivity_table(data, date, enumerator, team, settings_file)


@st.fragment
def _render_enumerator_productivity_table(
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    settings_file: str,
) -> None:
    """Display enumerator productivity table.
    Shows submission counts by enumerator over time with configurable
    time periods (daily, weekly, monthly).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    time_period = _render_time_period_selector(settings_file, tab_name=TAB_NAME)
    if time_period == "Week":
        weekstartday = _render_weekday_selector(settings_file, tab_name=TAB_NAME)
    else:
        weekstartday = "MON"  # Default value, not used for non-weekly periods

    group_by_cols = [enumerator, team] if team else [enumerator]
    productivity_df = compute_enumerator_productivity(
        data, date, group_by_cols, time_period, weekstartday
    )

    if team:
        # Build column configuration dynamically
        column_config = {
            enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
            team: st.column_config.TextColumn("Team", pinned=True),
        }
    else:
        column_config = {
            enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
        }

    column_config.update(
        {
            col: st.column_config.NumberColumn(col, format="%d")
            for col in productivity_df.columns
            if col not in group_by_cols
        }
    )

    st.dataframe(
        productivity_df, hide_index=True, width="stretch", column_config=column_config
    )


def _render_time_period_selector(
    settings_file: str,
    tab_name: str = TAB_NAME,
) -> Literal["Day", "Week", "Month"]:
    """Render time period selector widget using pills interface.

    Displays a pills widget allowing users to choose the time aggregation period
    for productivity analysis (Day, Week, or Month).

    Parameters
    ----------
    settings_file : str
        Path to settings file for saving/loading configurations.
    tab_name : str
        Name of the tab for settings storage (default: TAB_NAME).

    Returns
    -------
    Literal["Day", "Week", "Month"]
        Selected time period.
    """
    options_map = {
        "Day": ":material/event: Daily",
        "Week": ":material/date_range: Weekly",
        "Month": ":material/calendar_month: Monthly",
    }

    saved_settings = load_check_settings(settings_file, tab_name) or {}
    default_time_period = saved_settings.get(
        "time_period_enumerator_productivity", "Day"
    )

    with st.container(horizontal_alignment="left"):
        time_period = st.pills(
            label="Time Period",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            key="time_period_enumerator_productivity_key",
            default=default_time_period,
            help="Select time period for aggregating productivity",
            selection_mode="single",
            on_change=trigger_save,
            kwargs={"state_name": tab_name + "_time_period"},
        )
        save_check_settings(settings_file, tab_name, {"time_period": time_period})

    return time_period or "Day"


def _render_weekday_selector(
    settings_file: str,
    tab_name: str = TAB_NAME,
) -> str:
    """Render weekday selector widget for productivity analysis.

    Displays a selectbox allowing users to choose the first day of the week
    for weekly productivity calculations.

    Parameters
    ----------
    settings_file : str
        Path to settings file for saving/loading configurations.
    tab_name : str
        Name of the tab for settings storage (default: TAB_NAME).

    Returns
    -------
    str
        Weekday offset code (e.g., "SUN", "MON") for calculations.
    """
    saved_settings = load_check_settings(settings_file, tab_name) or {}
    default_weekstartday_sel = saved_settings.get(
        "weekstartday_enumerator_productivity", "Monday"
    )
    default_weekstartday_sel_index = WEEKDAY_NAMES.index(default_weekstartday_sel)

    cl1, _ = st.columns([1, 3])
    with cl1:
        weekstartday_sel = st.selectbox(
            label="Select the first day of the week",
            options=WEEKDAY_NAMES,
            index=default_weekstartday_sel_index,
            key="week_start_day_enumerator_productivity_key",
            help="Select the first day of the week",
            on_change=trigger_save,
            kwargs={"state_name": tab_name + "_weekstartday"},
        )
    save_check_settings(settings_file, tab_name, {"weekstartday": weekstartday_sel})

    return WEEKDAY_OFFSET_MAP[weekstartday_sel]


# =============================================================================
# Display Functions - Statistics
# =============================================================================


def _load_statistics_settings(settings_file: str) -> StatisticsSettings:
    """Load and validate statistics settings from file.

    Parameters
    ----------
    settings_file : str
        Path to settings file.

    Returns
    -------
    StatisticsSettings
        Validated statistics settings.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME) or {}
    try:
        return StatisticsSettings(**saved_settings)
    except ValueError:
        # Return default settings if validation fails
        return StatisticsSettings()


def _get_numeric_columns(
    data: pl.DataFrame, exclude_cols: list[str] | None = None
) -> list[str]:
    """Extract numeric column names from DataFrame.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame to extract columns from.
    exclude_cols : list[str] | None
        Columns to exclude from the result.

    Returns
    -------
    list[str]
        List of numeric column names.
    """
    exclude_cols = exclude_cols or []
    return [
        col
        for col in data.columns
        if data[col].dtype in pl.NUMERIC_DTYPES and col not in exclude_cols
    ]


def _render_column_selector(
    numeric_cols: list[str],
    default_cols: list[str] | None,
    settings_file: str,
) -> list[str]:
    """Render column selection widget.

    Parameters
    ----------
    numeric_cols : list[str]
        Available numeric columns.
    default_cols : list[str] | None
        Default selected columns.
    settings_file : str
        Path to settings file.

    Returns
    -------
    list[str]
        Selected columns.
    """
    selected_cols = st.multiselect(
        label="Select columns:",
        options=numeric_cols,
        default=default_cols,
        help="Select columns to include in statistics",
        key="selected_columns_enumerator",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_statscols"},
    )
    save_check_settings(settings_file, TAB_NAME, {"statscols": selected_cols})
    return selected_cols


def _render_statistics_selector(
    default_stats: list[str],
    settings_file: str,
) -> list[str]:
    """Render statistics selection widget.

    Parameters
    ----------
    default_stats : list[str]
        Default selected statistics.
    settings_file : str
        Path to settings file.

    Returns
    -------
    list[str]
        Selected statistics.
    """
    selected_stats = st.multiselect(
        "Select statistics:",
        options=ALLOWED_STATISTICS,
        default=default_stats,
        help="Select statistics to calculate",
        key="statistics_options_enumerator",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_stats"},
    )
    save_check_settings(settings_file, TAB_NAME, {"stats": selected_stats})
    return selected_stats


@st.fragment
def _render_enumerator_statistics_table(
    data: pl.DataFrame,
    enumerator: str,
    team: str | None,
    settings_file: str,
) -> None:
    """Display enumerator statistics table with team support.

    Shows configurable summary statistics for selected numeric columns
    grouped by enumerator (and optionally team).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name (optional).
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    # Validate inputs
    if not enumerator:
        st.info(
            "Enumerator statistics requires an enumerator column to be selected. "
            "Go to the :material/settings: settings section above to select it."
        )
        return

    # Load and validate settings using Pydantic
    settings = _load_statistics_settings(settings_file)

    # Build exclusion list for numeric columns
    exclude_cols = [enumerator, "consent_granted_agg_col", "completed_survey_agg_col"]
    if team:
        exclude_cols.append(team)

    numeric_cols = _get_numeric_columns(data, exclude_cols=exclude_cols)

    # Render UI in two columns
    col1, col2 = st.columns(2)

    with col1:
        statscols = _render_column_selector(
            numeric_cols, settings.statscols, settings_file
        )

    with col2:
        stats = _render_statistics_selector(settings.stats, settings_file)

    # Compute and display statistics
    if statscols:
        group_by_cols = [enumerator, team] if team else [enumerator]
        stats_df = compute_enumerator_statistics(
            data=data,
            group_by_cols=group_by_cols,
            statscols=statscols,
            stats=stats,
        )

        # Build column configuration dynamically with pinning
        if team:
            column_config = {
                enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
                team: st.column_config.TextColumn("Team", pinned=True),
            }
        else:
            column_config = {
                enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
            }

        st.dataframe(
            stats_df, hide_index=True, width="stretch", column_config=column_config
        )
    else:
        st.info(
            "No columns selected for statistics calculation.", icon=":material/info:"
        )


def _render_enumerator_statistics(
    data: pl.DataFrame,
    enumerator: str,
    team: str | None,
    settings_file: str,
) -> None:
    """Display enumerator statistics table with team support.

    Shows configurable summary statistics for selected numeric columns
    grouped by enumerator (and optionally team).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name (optional).
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    # Validate inputs
    if not enumerator:
        st.info(
            "Enumerator statistics requires an enumerator column to be selected. "
            "Go to the :material/settings: settings section above to select it."
        )
        return

    _render_enumerator_statistics_table(
        data=data, enumerator=enumerator, team=team, settings_file=settings_file
    )


def _load_statistics_overtime_settings(
    settings_file: str,
) -> StatisticsOvertimeSettings:
    """Load and validate statistics overtime settings from file.

    Parameters
    ----------
    settings_file : str
        Path to settings file.

    Returns
    -------
    StatisticsOvertimeSettings
        Validated statistics overtime settings.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME) or {}
    try:
        return StatisticsOvertimeSettings(**saved_settings)
    except ValueError:
        # Return default settings if validation fails
        return StatisticsOvertimeSettings()


def _render_period_selector_overtime(
    settings_file: str,
    default_period: str = "Week",
) -> str:
    """Render time period selection widget.

    Parameters
    ----------
    default_period : str
        Default selected period.
    settings_file : str
        Path to settings file.

    Returns
    -------
    str
        Selected time period.
    """
    options_map = {
        "Day": ":material/event: Daily",
        "Week": ":material/date_range: Weekly",
        "Month": ":material/calendar_month: Monthly",
    }
    period = st.pills(
        label="Select Time Period:",
        options=options_map.keys(),
        format_func=lambda x: options_map[x],
        default=default_period,
        key="project_enumerator_statistics_overtime_period_pills",
        help="Select time period for aggregating statistics",
        selection_mode="single",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_period_overtime"},
    )
    save_check_settings(settings_file, TAB_NAME, {"period_overtime": period})
    return period or "Day"


def _render_weekday_selector_overtime(
    default_weekday: str,
    settings_file: str,
) -> str:
    """Render weekday selection widget (for weekly period).

    Parameters
    ----------
    default_weekday : str
        Default selected weekday.
    settings_file : str
        Path to settings file.

    Returns
    -------
    str
        Selected weekday offset code (e.g., "SUN", "MON").
    """
    default_weekday_index = WEEKDAY_NAMES.index(default_weekday)

    weekday_sel = st.selectbox(
        label="Select the first day of the week",
        options=WEEKDAY_NAMES,
        index=default_weekday_index,
        help="Select the first day of the week",
        key="project_week_start_day_enumerator_overtime",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_weekstartday_overtime"},
    )
    save_check_settings(settings_file, TAB_NAME, {"weekstartday": weekday_sel})

    return WEEKDAY_OFFSET_MAP[weekday_sel]


def _render_statistic_selector(
    default_stat: str,
    settings_file: str,
) -> str:
    """Render statistic selection widget.

    Parameters
    ----------
    default_stat : str
        Default selected statistic.
    settings_file : str
        Path to settings file.

    Returns
    -------
    str
        Selected statistic.
    """
    default_stat_index = ALLOWED_STATISTICS_OVERTIME.index(default_stat)

    stat = st.selectbox(
        label="Select statistic:",
        options=ALLOWED_STATISTICS_OVERTIME,
        index=default_stat_index,
        help="Select statistic to calculate over time",
        key="enumerator_statistics_overtime_stat",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_stat_overtime"},
    )
    save_check_settings(settings_file, TAB_NAME, {"stat": stat})
    return stat


def _render_column_selector_single(
    numeric_cols: list[str],
    default_col: str | None,
    settings_file: str,
) -> str | None:
    """Render single column selection widget.

    Parameters
    ----------
    numeric_cols : list[str]
        Available numeric columns.
    default_col : str | None
        Default selected column.
    settings_file : str
        Path to settings file.

    Returns
    -------
    str | None
        Selected column.
    """
    default_col_index = (
        numeric_cols.index(default_col)
        if default_col and default_col in numeric_cols
        else None
    )

    statscol = st.selectbox(
        label="Select column:",
        options=numeric_cols,
        index=default_col_index,
        help="Select column to include in statistics",
        key="enumerator_statistics_overtime_column",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_statscol_overtime"},
    )
    save_check_settings(settings_file, TAB_NAME, {"statscol": statscol})
    return statscol


@st.fragment
def _render_enumerator_statistics_overtime_table(
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    settings_file: str,
) -> None:
    """Display enumerator statistics over time table with team support.

    Shows how a specific statistic changes over time periods for each
    enumerator (and optionally team) with configurable time periods and statistics.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name (optional).
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    # Validate inputs
    if not (enumerator and date):
        return

    # Load and validate settings using Pydantic
    settings = _load_statistics_overtime_settings(settings_file)

    # Build exclusion list for numeric columns
    exclude_cols = [enumerator, "consent_granted_agg_col", "completed_survey_agg_col"]
    if team:
        exclude_cols.append(team)

    numeric_cols = _get_numeric_columns(data, exclude_cols=exclude_cols)

    # Render UI in three columns
    col1, col2, col3 = st.columns([0.3, 0.2, 0.5])

    with col1:
        statscol = _render_column_selector_single(
            numeric_cols, settings.statscol, settings_file
        )

    with col2:
        stat = _render_statistic_selector(settings.stat, settings_file)

    with col3:
        period = _render_period_selector_overtime(
            settings_file, settings.period_overtime
        )
        # Conditionally render weekday selector for weekly period
        weekstartday = "SAT"  # Default
        if period == "Week":
            weekstartday = _render_weekday_selector_overtime(
                settings.weekstartday, settings_file
            )

    # Compute and display statistics
    if statscol:
        group_by_cols = [enumerator, team] if team else [enumerator]
        stats_overtime_df = compute_enumerator_statistics_overtime(
            data=data,
            date=date,
            group_by_cols=group_by_cols,
            statscol=statscol,
            stat=stat,
            period=period,
            weekstartday=weekstartday,
        )

        # Build column configuration dynamically with pinning
        if team:
            column_config = {
                enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
                team: st.column_config.TextColumn("Team", pinned=True),
            }
        else:
            column_config = {
                enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
            }

        st.dataframe(
            stats_overtime_df,
            hide_index=True,
            width="stretch",
            column_config=column_config,
        )
    else:
        st.info(
            "No column selected for statistics calculation.", icon=":material/info:"
        )


def _render_enumerator_statistics_overtime(
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    settings_file: str,
) -> None:
    """Display enumerator statistics over time table with team support.

    Shows how a specific statistic changes over time periods for each
    enumerator (and optionally team) with configurable time periods and statistics.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name (optional).
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    # Validate inputs
    if not (enumerator and date):
        st.info(
            "Enumerator statistics over time requires a date and enumerator column to be selected. "
            "Go to the :material/settings: settings section above to select them."
        )
        return

    _render_enumerator_statistics_overtime_table(
        data=data,
        date=date,
        enumerator=enumerator,
        team=team,
        settings_file=settings_file,
    )


# =============================================================================
# Main Enumerator Report Function
# =============================================================================


def enumerator_report(
    project_id: str,
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
    survey_columns: ColumnByType,
) -> None:
    """Generate a comprehensive enumerator performance report.

    Creates a complete enumerator analysis report including:
    - Overview metrics and statistics
    - Comprehensive enumerator summary table
    - Productivity tracking over time
    - Statistical analysis across enumerators
    - Time-series analysis of performance

    Parameters
    ----------
    project_id : str
        Unique project identifier for configuration lookup.
    data : pl.DataFrame
        Dataset containing survey data to analyze.
    settings_file : str
        Path to settings file for persisting configurations.
    missing_settings_file : str
        Path to missing codes configuration file.
    page_num : int
        Page number for configuration defaults (1-indexed).
    """
    categorical_columns = survey_columns.categorical_columns
    datetime_columns = survey_columns.datetime_columns

    st.title("Enumerator Report")

    if data.is_empty():
        st.info(
            "No data available for the enumerator report. "
            "Please upload data to proceed."
        )
        return

    config_settings = EnumeratorSettings(**config)

    enumerator_settings = enumerator_report_settings(
        project_id,
        setting_file,
        data,
        config_settings,
        categorical_columns,
        datetime_columns,
    )

    # get data for enumerator report
    data_enum_report = duckdb_get_table(
        project_id,
        "enumerator_data_with_consent_outcome",
        "intermediate",
    )

    if data_enum_report.is_empty():
        data_enum_report = data

    _render_enumerator_overview_metrics(
        data_enum_report,
        enumerator_settings.survey_date,
        enumerator_settings.enumerator,
        enumerator_settings.team,
    )

    st.write("---")
    st.subheader("Enumerator Summary")

    _render_enumerator_summary_table(
        project_id,
        data_enum_report,
        enumerator_settings.survey_date,
        enumerator_settings.enumerator,
        enumerator_settings.team,
        enumerator_settings.formversion,
        enumerator_settings.duration,
    )

    st.write("---")
    st.subheader("Enumerator Productivity")

    _render_enumerator_productivity(
        data_enum_report,
        enumerator_settings.survey_date,
        enumerator_settings.enumerator,
        enumerator_settings.team,
        setting_file,
    )

    st.write("---")
    st.subheader("Column Statistics by Enumerator")

    _render_enumerator_statistics(
        data_enum_report,
        enumerator_settings.enumerator,
        enumerator_settings.team,
        setting_file,
    )

    st.write("---")
    st.subheader("Enumerator Statistics Over Time")

    _render_enumerator_statistics_overtime(
        data_enum_report,
        enumerator_settings.survey_date,
        enumerator_settings.enumerator,
        enumerator_settings.team,
        setting_file,
    )
