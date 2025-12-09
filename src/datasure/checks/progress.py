"""Progress tracking module for survey data quality checks.

This module provides comprehensive progress tracking functionality with:
- Survey submission progress monitoring
- Progress over time analysis
- Attempted interviews tracking
- Consent and completion tracking
- Modular, testable architecture
"""

from typing import Any, Literal

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import seaborn as sns
import streamlit as st
from pydantic import BaseModel, Field, field_validator

from datasure.utils.chart_utils import donut_chart2
from datasure.utils.dataframe_utils import get_df_info
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

TAB_NAME = "progress"


# =============================================================================
# Pydantic Models for Data Validation
# =============================================================================


class ProgressSummary(BaseModel):
    """Summary statistics for progress tracking."""

    total_submitted: int = Field(ge=0, description="Total number of submitted surveys")
    target: int | None = Field(
        None, ge=0, description="Target number of surveys to collect"
    )
    percentage_completed: float = Field(
        ge=0, le=100, description="Percentage of target completed"
    )


class ProgressChartMetrics(BaseModel):
    """Metrics for consent and completion progress."""

    consent_percentage: float = Field(
        ge=0, le=100, description="Percentage of valid consent"
    )
    completion_percentage: float = Field(
        ge=0, le=100, description="Percentage of completed surveys"
    )


class AttemptedInterviewsMetrics(BaseModel):
    """Summary metrics for attempted interviews."""

    total_submitted: int = Field(ge=0, description="Total number of submissions")
    number_of_unique_ids: int = Field(
        ge=0, description="Number of unique survey IDs"
    )
    min_attempts: int = Field(ge=0, description="Minimum number of attempts")
    max_attempts: int = Field(ge=0, description="Maximum number of attempts")


class ProgressSettings(BaseModel):
    """Settings for progress report configuration."""

    survey_key: str = Field(None, description="Survey key column")
    survey_id: str | None = Field(..., min_length=1, description="Survey ID column")
    survey_date: str | None = Field(None, description="Survey date column")
    enumerator: str | None = Field(None, description="Enumerator ID column")
    survey_target: int | None = Field(None, ge=0, description="Target number of surveys")
    target_submissions_per_period: int | None = Field(
        None, ge=0, description="Target number of submissions per time period"
    )

    @field_validator("survey_target", "target_submissions_per_period")
    @classmethod
    def validate_target(cls, v: int | None) -> int | None:
        """Validate target is positive if provided."""
        if v is not None and v < 0:
            raise ValueError("Target must be a positive number")
        return v

class ProgressSummary(BaseModel):
    """Summary statistics for progress tracking."""

    total_submitted: int = Field(ge=0, description="Total number of submitted surveys")
    target: int | None = Field(
        None, ge=0, description="Target number of surveys to collect"
    )
    percentage_completed: float = Field(
        ge=0, le=100, description="Percentage of target completed"
    )


class TimePeriodConfig(BaseModel):
    """Configuration for time period aggregation."""

    time_period: Literal["Day", "Week", "Month"] = Field(
        description="Time period for aggregating progress data"
    )

    @field_validator("time_period")
    @classmethod
    def validate_time_period(cls, v: str) -> str:
        """Validate that time period is one of the allowed values."""
        valid_periods = {"Day", "Week", "Month"}
        if v not in valid_periods:
            raise ValueError(
                f"Invalid time period '{v}'. Must be one of: {', '.join(valid_periods)}"
            )
        return v


class AttemptedInterviewsResult(BaseModel):
    """Result model for attempted interviews computation."""

    attempted_interviews: Any = Field(description="DataFrame with attempted interviews data")
    total_submitted: int = Field(ge=0, description="Total number of submissions")
    number_of_unique_ids: int = Field(ge=0, description="Number of unique survey IDs")
    min_attempts: int = Field(ge=0, description="Minimum number of attempts")
    max_attempts: int = Field(ge=0, description="Maximum number of attempts")

    class Config:
        """Pydantic config."""
        arbitrary_types_allowed = True


# =============================================================================
# Settings and Configuration Functions
# =============================================================================

def load_default_settings(
    settings_file: str, config: ProgressSettings
) -> ProgressSettings:
    """Load the default settings for the progress report.

    Parameters
    ----------
    settings_file : str
        The settings file to load.
    config : ProgressSettings
        Default configuration.

    Returns
    -------
    ProgressSettings
        Merged settings.
    """
    # Load saved settings
    saved_settings = load_check_settings(settings_file, TAB_NAME)

    default_settings: dict = dict(config)
    default_settings.update(saved_settings)

    # Merge with defaults
    return ProgressSettings(**default_settings)


@demo_output_onboarding(TAB_NAME)
def progress_report_settings(
    settings_file: str,
    config: ProgressSettings,
    categorical_columns: list[str],
    datetime_columns: list[str],
) -> ProgressSettings:
    """Create a settings UI for progress report configuration.

    This function creates the comprehensive Streamlit UI for configuring
    outlier detection settings. Due to its complexity (UI rendering),
    it maintains a higher cognitive complexity but is well-structured.

    Parameters
    ----------
    settings_file : str
        Path to settings file.
    config : ProgressSettings
        Default configuration.
    categorical_columns : list[str]
        List of categorical columns.
    datetime_columns : list[str]
        List of datetime columns.

    Returns
    -------
    ProgressSettings
        User-configured settings.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for progress report")
        st.write("---")

        # Load default settings
        default_settings = load_default_settings(settings_file, config)

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
                    key="survey_key_progress",
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
                    key="survey_id_progress",
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
                    key="survey_date_progress",
                    index=default_survey_date_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_date"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"survey_date": survey_date}
                )

        with st.container(border=True):
            st.subheader("Enumerator")
            ec1, _, _ = st.columns(3)
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
                    key="enumerator_progress",
                    help="Select the column that contains the enumerator ID",
                    index=default_enumerator_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_enumerator"},
                )
                save_check_settings(settings_file, TAB_NAME, {"enumerator": enumerator})

        with st.container(border=True):
            st.subheader("Submission Targets")
            tc1, tc2, _ = st.columns(spec=3)
            default_target = default_settings.survey_target
            default_target_per_period = default_settings.target_submissions_per_period

            # Total target selection
            with tc1:
                target = st.number_input(
                    label="Total Expected Interviews",
                    min_value=0,
                    value=default_target,
                    help="Total number of interviews expected",
                    key="total_goal_progress",
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_target"},
                )
                save_check_settings(settings_file, TAB_NAME, {"target": target})

            # Target per period selection
            with tc2:
                target_per_period = st.number_input(
                    label="Target Submissions Per Period",
                    min_value=0,
                    value=default_target_per_period if default_target_per_period else 0,
                    help="Target number of submissions per time period (Day/Week/Month)",
                    key="target_per_period_progress",
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_target_per_period"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"target_per_period": target_per_period}
                )

    return ProgressSettings(
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        enumerator=enumerator,
        survey_target=target,
        target_submissions_per_period=target_per_period if target_per_period > 0 else None,
    )



# =============================================================================
# Progress Summary - Computation and Display
# =============================================================================


@st.cache_data
def compute_progress_summary(
    data: pl.DataFrame, target: int | None
) -> ProgressSummary:
    """Compute summary statistics for progress report.

    Parameters
    ----------
    data : pd.DataFrame
        Data to display
    target : int | None
        Target number of interviews

    Returns
    -------
    tuple
        (total_submitted, target, percentage_completed)
    """
    total_submitted = data.height

    if target and target > 0:
        percentage_completed = (total_submitted / target) * 100
    else:
        percentage_completed = 0.0

    return ProgressSummary(
        total_submitted=total_submitted,
        target=target,
        percentage_completed=percentage_completed,
    )


@demo_output_onboarding(TAB_NAME)
def display_progress_summary(data: pl.DataFrame, target: int | None) -> None:
    """Display summary statistics for progress report.

    Parameters
    ----------
    data : pd.DataFrame
        Data to display
    target : int | None
        Target number of interviews
    """
    progress_summary = compute_progress_summary(
        data, target
    )

    mc1, mc2, mc3 = st.columns([0.5, 0.25, 0.25], border=True)

    with mc1:
        st.write("Submission progress")
        sp1, sp2 = st.columns([0.8, 0.2])

        if not target:
            sp1.info(
                "Target number of interviews is not set. Go to :material/settings: "
                "settings to set it."
            )
        else:
            progress_val = min(progress_summary.percentage_completed / 100, 1.0)
            sp1.progress(value=progress_val)
            sp2.write(f"{progress_summary.percentage_completed:.2f}%")

    if not target:
        with mc2:
            st.write("Target Interviews")
            st.info(
                "Target number of interviews is not set. Go to :material/settings: "
                "settings to set it."
            )
    else:
        formatted_target = f"{target:,}" if target > 0 else "Invalid Target"
        mc2.metric(
            label="Target Interviews",
            value=formatted_target,
        )

    formatted_submitted = f"{progress_summary.total_submitted:,}"
    mc3.metric(label="Total Submitted Interviews", value=formatted_submitted)


# =============================================================================
# Progress Over Time - Computation and Display
# =============================================================================


@st.cache_data
def compute_progress_overtime(
    data: pl.DataFrame,
    date: str,
    time_period: Literal["Day", "Week", "Month"],
) -> pl.DataFrame:
    """Compute progress over time statistics.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset
    date : str
        Column name for date
    time_period : Literal["Day", "Week", "Month"]
        Time period aggregation (Day, Week, or Month)

    Returns
    -------
    pl.DataFrame
        DataFrame with time_period and num_interviews columns

    Raises
    ------
    ValueError
        If time_period is not one of: Day, Week, Month
    """
    # Validate time period using Pydantic model
    validated_config = TimePeriodConfig(time_period=time_period)
    validated_period = validated_config.time_period

    # Create time period column based on selection
    if validated_period == "Day":
        period_stats = data.select(
            pl.col(date).cast(pl.Date).alias("time_period")
        ).group_by("time_period").agg(
            pl.len().alias("num_interviews")
        ).sort("time_period")
    elif validated_period == "Week":
        period_stats = data.select(
            pl.col(date).cast(pl.Date).dt.truncate("1w").alias("time_period")
        ).group_by("time_period").agg(
            pl.len().alias("num_interviews")
        ).sort("time_period")
    elif validated_period == "Month":
        period_stats = data.select(
            pl.col(date).cast(pl.Date).dt.truncate("1mo").alias("time_period")
        ).group_by("time_period").agg(
            pl.len().alias("num_interviews")
        ).sort("time_period")

    return period_stats


@st.cache_data
def compute_average_interviews(period_stats: pl.DataFrame) -> float:
    """Compute average number of interviews across time periods.

    Parameters
    ----------
    period_stats : pl.DataFrame
        DataFrame with num_interviews column

    Returns
    -------
    float
        Average number of interviews per period
    """
    return period_stats["num_interviews"].mean()

def render_time_period_selector() -> Literal["Day", "Week", "Month"]:
    """Render time period selector UI.

    Returns
    -------
    Literal["Day", "Week", "Month"]
        Selected time period
    """
    _, tp_col = st.columns([0.8, 0.2])
    with tp_col:

        options_map = {"Day": ":material/event: Daily", "Week": ":material/date_range: Weekly", "Month": ":material/calendar_month: Monthly"}

        time_period = st.pills(
            label="Time Period",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            key="time_period_progress_overtime",
            help="Select time period for aggregating progress data",
            selection_mode="single",
        )

    return time_period

@demo_output_onboarding(TAB_NAME)
def display_progress_overtime(
    data: pl.DataFrame,
    date: str | None,
    setting_file: str,
    target_per_period: int | None = None,
) -> None:
    """Display progress over time.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset
    date : str | None
        Column name for date
    setting_file : str
        Path to settings file
    target_per_period : int | None
        Target number of submissions per period
    """
    if not date:
        st.info(
            "Progress over time report requires a date column to be selected. "
            "To add a date column, go to the :material/settings: settings section above."
        )
        return

    time_period = render_time_period_selector()

    if st.session_state.get("time_period_progress_overtime_save"):
        save_check_settings(
            settings_file=setting_file,
            check_name="progress",
            check_settings={"time_period": time_period},
        )
        st.session_state["time_period_progress_overtime_save"] = False

    period_stats = compute_progress_overtime(
        data=data,
        date=date,
        time_period=time_period,
    )

    average_interviews = compute_average_interviews(period_stats)

    # Convert time_period and num_interviews to lists for plotting
    time_periods = period_stats["time_period"].to_list()
    num_interviews = period_stats["num_interviews"].to_list()

    # Determine threshold for coloring bars (target or average)
    threshold = target_per_period if target_per_period else average_interviews

    # Create color list based on threshold
    bar_colors = [
        "#2ECC71" if count >= threshold else "#f87171" for count in num_interviews
    ]

    # Create the figure
    fig = go.Figure()

    # Add bar plot for interviews per time period with conditional coloring
    fig.add_trace(
        go.Bar(
            x=time_periods,
            y=num_interviews,
            name="Interviews",
            marker_color=bar_colors,
            hovertemplate="<b>%{x}</b><br>" + "Interviews: %{y}<br>",
        )
    )

    # Add threshold line (target or average)
    threshold_label = (
        f"Target: {threshold}"
        if target_per_period
        else f"Avg Interviews: {threshold:.2f}"
    )
    fig.add_trace(
        go.Scatter(
            x=[time_periods[0], time_periods[-1]],
            y=[threshold, threshold],
            mode="lines",
            name=threshold_label,
            line={"color": "#4D5E90", "width": 2, "dash": "dash"},
        )
    )

    # Update layout with transparent background
    fig.update_layout(
        title=f"Interview Progress by {time_period}",
        title_x=0,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=400,
        margin={"t": 50, "b": 50, "l": 50, "r": 50},
        showlegend=True,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        xaxis={
            "title": time_period,
            "showgrid": False,
            "gridcolor": "lightgrey",
            "tickangle": -45,
            "type": "category",
        },
        yaxis={
            "title_text": "Number of Interviews",
            "showgrid": False,
            "gridcolor": "lightgrey",
            "zeroline": False,
        },
    )

    st.plotly_chart(fig, theme=None, use_container_width=True)


# =============================================================================
# Progress Chart - Consent and Completion
# =============================================================================


@st.cache_data
def compute_progress_chart(
    data: pd.DataFrame,
    consent_col: str | None,
    consent_vals: list[Any] | None,
    outcome_col: str | None,
    outcome_vals: list[Any] | None,
) -> tuple[float, float]:
    """Compute progress chart statistics.

    Parameters
    ----------
    data : pd.DataFrame
        Dataset
    consent_col : str | None
        Column name for consent
    consent_vals : list | None
        List of consent values
    outcome_col : str | None
        Column name for outcome
    outcome_vals : list | None
        List of outcome values

    Returns
    -------
    tuple
        (consent_percentage, completion_percentage)
    """
    total_submitted = len(data)

    # Calculate consent percentage
    if consent_col and consent_vals:
        valid_consent_count = len(data[data[consent_col].isin(consent_vals)])
        consent_percentage = (
            (valid_consent_count / total_submitted) * 100 if total_submitted > 0 else 0
        )
    else:
        consent_percentage = 0.0

    # Calculate completion percentage
    if outcome_col and outcome_vals:
        completed_count = len(data[data[outcome_col].isin(outcome_vals)])
        completion_percentage = (
            (completed_count / total_submitted) * 100 if total_submitted > 0 else 0
        )
    else:
        completion_percentage = 0.0

    return consent_percentage, completion_percentage


@demo_output_onboarding(TAB_NAME)
def display_progress_chart(data: pd.DataFrame, setting_file: str) -> None:
    """Display progress chart.

    Parameters
    ----------
    data : pd.DataFrame
        Dataset
    setting_file : str
        Path to settings file
    """
    survey_cols = data.columns
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

    # Consent column selection
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

        if st.session_state.get("progress_consent_pie_chart_save"):
            save_check_settings(
                settings_file=setting_file,
                check_name="progress",
                check_settings={"consent": consent},
            )
            st.session_state["progress_consent_pie_chart_save"] = False

        if consent:
            consent_val_options = data[consent].unique()
            default_consent_vals = (
                consent_vals if consent_vals and consent_vals in consent_val_options else None
            )
            consent_vals = st.multiselect(
                label="Select consent values",
                options=consent_val_options,
                help="Values to consider as valid consent",
                key="consent_vals_progress_chart",
                default=default_consent_vals,
                on_change=trigger_save,
                kwargs=({"state_name": "consent_vals_progress_chart_save"}),
            )

            if st.session_state.get("consent_vals_progress_chart_save"):
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

    # Outcome column selection
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

        if st.session_state.get("outcome_progress_chart_save"):
            save_check_settings(
                settings_file=setting_file,
                check_name="progress",
                check_settings={"outcome": outcome},
            )
            st.session_state["outcome_progress_chart_save"] = False

        if outcome:
            outcome_val_options = data[outcome].unique()
            default_outcome_vals = (
                outcome_vals if outcome_vals and outcome_vals in outcome_val_options else None
            )
            outcome_vals = st.multiselect(
                label="Select outcome values",
                options=outcome_val_options,
                help="Values to consider as completed surveys",
                key="outcome_vals_progress_chart",
                default=default_outcome_vals,
                on_change=trigger_save,
                kwargs=({"state_name": "outcome_vals_progress_chart_save"}),
            )

            if st.session_state.get("outcome_vals_progress_chart_save"):
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

    # Compute percentages
    consent_percentage, completion_percentage = compute_progress_chart(
        data=data,
        consent_col=consent,
        consent_vals=consent_vals,
        outcome_col=outcome,
        outcome_vals=outcome_vals,
    )

    # Create and display charts
    perc_consent_chart = donut_chart2(actual_value=int(consent_percentage))
    perc_completion_chart = donut_chart2(actual_value=int(completion_percentage))

    with cc1:
        if consent and consent_vals:
            st.markdown("**% consent**")
            st.pyplot(perc_consent_chart, use_container_width=True)

    with cc2:
        if outcome and outcome_vals:
            st.markdown("**% completion**")
            st.pyplot(perc_completion_chart, use_container_width=True)


# =============================================================================
# Attempted Interviews - Computation and Display
# =============================================================================


def _aggregate_attempts_by_survey_id(
    data: pl.DataFrame, survey_id: str, date: str
) -> pl.DataFrame:
    """Aggregate interview attempts by survey ID.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset
    survey_id : str
        Column name for survey ID
    date : str
        Column name for date

    Returns
    -------
    pl.DataFrame
        Aggregated attempts with num_interviews, last_attempt_date, and attempt_dates
    """
    return data.group_by(survey_id).agg([
        pl.len().alias("num_interviews"),
        pl.col(date).max().alias("last_attempt_date"),
        pl.col(date).alias("attempt_dates"),
    ]).sort(survey_id)


def _expand_attempt_dates(attempts_df: pl.DataFrame) -> pl.DataFrame:
    """Expand attempt dates list into separate columns.

    Parameters
    ----------
    attempts_df : pl.DataFrame
        DataFrame with attempt_dates column containing lists

    Returns
    -------
    pl.DataFrame
        DataFrame with expanded attempt date columns
    """
    # Get the maximum number of attempts to determine how many columns we need
    max_attempts = attempts_df.select(
        pl.col("attempt_dates").list.len().max()
    ).item()

    # Explode attempt dates into separate columns
    # Use list.get with default=None to handle lists shorter than max_attempts
    for i in range(max_attempts):
        attempts_df = attempts_df.with_columns(
            pl.col("attempt_dates").list.get(i, null_on_oob=True).alias(f"Attempt Date {i + 1}")
        )

    return attempts_df.drop("attempt_dates")


def _prepare_display_columns(
    data: pl.DataFrame, survey_id: str, date: str, display_cols: list[str]
) -> pl.DataFrame:
    """Prepare display columns with forward and backward fill.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset
    survey_id : str
        Column name for survey ID
    date : str
        Column name for date
    display_cols : list[str]
        List of columns to display

    Returns
    -------
    pl.DataFrame
        DataFrame with filled display columns, one row per survey ID
    """
    if not display_cols:
        return pl.DataFrame({survey_id: data[survey_id].unique()})

    # Sort and select relevant columns
    cols_to_select = [survey_id, date] + display_cols
    sorted_data = data.select(cols_to_select).sort([survey_id, date])

    # Forward fill and backward fill within each group
    filled_data = sorted_data.with_columns([
        pl.col(col).forward_fill().backward_fill().over(survey_id)
        for col in display_cols
    ])

    # Keep only one row per survey ID (the first one after sorting)
    return filled_data.unique(subset=[survey_id], keep="first")


def _compute_summary_stats(attempts_df: pl.DataFrame) -> tuple[int, int, int]:
    """Compute summary statistics for attempted interviews.

    Parameters
    ----------
    attempts_df : pl.DataFrame
        DataFrame with attempted interviews data

    Returns
    -------
    tuple
        (number_of_unique_ids, min_attempts, max_attempts)
    """
    num_unique = attempts_df.height
    min_attempts = attempts_df["num_interviews"].min()
    max_attempts = attempts_df["num_interviews"].max()

    return num_unique, min_attempts, max_attempts


@st.cache_data
def compute_attempted_interviews(
    data: pl.DataFrame, survey_id: str, date: str, display_cols: list[str]
) -> AttemptedInterviewsResult:
    """Compute attempted interviews statistics.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset
    survey_id : str
        Column name for survey ID
    date : str
        Column name for date
    display_cols : list[str]
        List of columns to display

    Returns
    -------
    AttemptedInterviewsResult
        Pydantic model containing attempted interviews data and summary statistics
    """
    total_submitted = data.height

    # Step 1: Aggregate attempts by survey ID
    attempted_interviews = _aggregate_attempts_by_survey_id(data, survey_id, date)

    # Step 2: Expand attempt dates into separate columns
    attempted_interviews = _expand_attempt_dates(attempted_interviews)

    # Step 3: Prepare display columns if any
    if display_cols:
        display_data = _prepare_display_columns(data, survey_id, date, display_cols)

        # Merge display columns with attempted interviews
        attempted_interviews = attempted_interviews.join(
            display_data.drop([date]), on=survey_id, how="left"
        )

        # Reorder columns: survey_id, num_interviews, last_attempt_date, display_cols, attempt dates
        attempt_date_cols = [
            col for col in attempted_interviews.columns if col.startswith("Attempt Date")
        ]
        ordered_cols = (
            [survey_id, "num_interviews", "last_attempt_date"]
            + display_cols
            + attempt_date_cols
        )
        attempted_interviews = attempted_interviews.select(ordered_cols)

    # Step 4: Calculate summary statistics
    num_unique, min_attempts, max_attempts = _compute_summary_stats(attempted_interviews)

    return AttemptedInterviewsResult(
        attempted_interviews=attempted_interviews,
        total_submitted=total_submitted,
        number_of_unique_ids=num_unique,
        min_attempts=min_attempts,
        max_attempts=max_attempts,
    )


@demo_output_onboarding(TAB_NAME)
def display_attempted_interviews(
    data: pl.DataFrame, survey_id: str | None, date: str | None, setting_file: str
) -> None:
    """Display attempted interviews report.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset
    survey_id : str | None
        Column name for survey ID
    date : str | None
        Column name for date
    setting_file : str
        Path to settings file
    """
    if not (all([survey_id, date])):
        st.info(
            "Attempted interviews report requires survey ID and date columns to be selected. "
            "To add these columns, go to the :material/settings: settings section above."
        )
        return


    default_settings = load_check_settings(
        settings_file=setting_file, check_name="progress"
    )
    display_cols = default_settings.get("display_cols") if default_settings else None

    with st.expander(":material/clarify: Show more columns in report", expanded=False):
        st.info(
            "Select additional columns to include in the table displaying attempted interviews. "
        )
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

    # Compute attempted interviews using Polars
    result = compute_attempted_interviews(
        data=data,
        survey_id=survey_id,
        date=date,
        display_cols=display_cols,
    )

    # Display metrics
    _display_metrics(result)

    # Display chart and table
    _display_chart_and_table(result.attempted_interviews, survey_id)


def _display_metrics(result: AttemptedInterviewsResult) -> None:
    """Display summary metrics for attempted interviews.

    Parameters
    ----------
    result : AttemptedInterviewsResult
        Result containing attempted interviews data and statistics
    """
    cm1, cm2, cm3, cm4 = st.columns(4, border=True)
    total_submissions_formatted = f"{result.total_submitted:,}"
    cm1.metric(label="Total Submitted Interviews", value=total_submissions_formatted)
    number_of_unique_ids_formatted = f"{result.number_of_unique_ids:,}"
    cm2.metric(label="Number of Unique IDs", value=number_of_unique_ids_formatted)
    min_attempts_formatted = f"{result.min_attempts:,}"
    cm3.metric(label="Min Attempts", value=min_attempts_formatted)
    max_attempts_formatted = f"{result.max_attempts:,}"
    cm4.metric(label="Max Attempts", value=max_attempts_formatted)


def _display_chart_and_table(
    attempted_interviews: pl.DataFrame, survey_id: str
) -> None:
    """Display frequency chart and detailed table.

    Parameters
    ----------
    attempted_interviews : pl.DataFrame
        DataFrame with attempted interviews data
    survey_id : str
        Column name for survey ID
    """
    ai1, ai2 = st.columns([0.4, 0.6])

    with ai1:
        # Aggregate attempted interviews into frequency counts
        attempted_frequency = (
            attempted_interviews
            .group_by("num_interviews")
            .agg(pl.len().alias("frequency"))
            .sort("num_interviews")
        )

        # Calculate total and percentage
        total_surveys = attempted_frequency["frequency"].sum()
        attempted_frequency = attempted_frequency.with_columns(
            (pl.col("frequency") / total_surveys * 100).alias("percentage")
        )

        # Convert to list for plotting
        num_interviews_list = attempted_frequency["num_interviews"].to_list()
        percentage_list = attempted_frequency["percentage"].to_list()
        frequency_list = attempted_frequency["frequency"].to_list()

        # Create custom hover text
        hover_text = [
            f"<b>{attempts} Attempts</b><br>"
            f"Percentage: {pct:.1f}%<br>"
            f"Frequency: {freq}"
            for attempts, pct, freq in zip(num_interviews_list, percentage_list, frequency_list, strict=False)
        ]

        # Create figure using go.Bar for better control
        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=percentage_list,
                y=num_interviews_list,
                orientation="h",
                marker_color="#f87171",
                hovertemplate="%{customdata}<extra></extra>",
                customdata=hover_text,
            )
        )

        fig.update_layout(
            title="Attempted Interviews Distribution",
            title_x=0.5,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=400,
            margin={"t": 50, "b": 50, "l": 50, "r": 50},
            hovermode="closest",
            xaxis={
                "title": "Percentage (%)",
                "showgrid": False,
                "gridcolor": "lightgrey",
            },
            yaxis={
                "title": "Number of Attempts",
                "showgrid": False,
                "gridcolor": "lightgrey",
                "autorange": "reversed",
            },
        )
        st.plotly_chart(fig, use_container_width=True)

    with ai2:
        # Convert to pandas for styling (Streamlit doesn't support Polars styling yet)
        attempts_pd = attempted_interviews.to_pandas()

        cmap = sns.light_palette("pink", as_cmap=True)
        vmin = attempts_pd["num_interviews"].min()
        vmax = attempts_pd["num_interviews"].max()

        styler_limit = attempts_pd.shape[0] * attempts_pd.shape[1]
        pd.set_option("styler.render.max_elements", styler_limit)

        st.dataframe(
            data=attempts_pd.style.background_gradient(
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


# =============================================================================
# Main Report Function
# =============================================================================


@demo_output_onboarding(TAB_NAME)
def progress_report(
    project_id: str,
    page_name_id: str,
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
) -> None:
    """Display progress report.

    Parameters
    ----------
    project_id : str
        Project identifier
    data : pd.DataFrame
        Data to display
    setting_file : str
        Path to settings file
    page_num : int
        Page number
    """
    # get column info
    _, string_columns, numeric_columns, datetime_columns, _ = get_df_info(
        data, cols_only=True
    )

    string_numeric_cols = list(set(string_columns + numeric_columns))

    st.title("Progress Tracking")

    # Load settings
    config_settings = ProgressSettings(**config)
    progress_settings = progress_report_settings(
        setting_file, config_settings, string_numeric_cols, datetime_columns
    )

    st.write("---")
    st.subheader("Progress Summary")
    display_progress_summary(data, progress_settings.survey_target)

    st.write("---")
    st.subheader("Progress Over Time")
    display_progress_overtime(
        data,
        progress_settings.survey_date,
        setting_file,
        progress_settings.target_submissions_per_period,
    )

    st.write("---")
    st.subheader("Attempted Interviews")
    display_attempted_interviews(
        data,
        progress_settings.survey_id,
        progress_settings.survey_date,
        setting_file,
    )


    """"
    st.write("---")
    st.write("## Attempted Interviews")
    display_attempted_interviews(
        data=data,
        survey_id=survey_id,
        date=date,
        setting_file=setting_file,
    )

    st.write("---")
    st.write("## Consent and Completion Progress Chart")
    display_progress_chart(data=data, setting_file=setting_file)
    """
