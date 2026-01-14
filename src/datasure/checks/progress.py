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
import plotly.graph_objects as go
import polars as pl
import seaborn as sns
import streamlit as st
from pydantic import BaseModel, Field, field_validator

from datasure.utils.chart_utils import donut_chart2
from datasure.utils.dataframe_utils import ColumnByType
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

TAB_NAME = "progress"

# Configure pandas styler for large dataframes (performance optimization)
pd.set_option("styler.render.max_elements", 1_000_000)


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
        ge=0, description="Percentage of target completed"
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
    number_of_unique_ids: int = Field(ge=0, description="Number of unique survey IDs")
    min_attempts: int = Field(ge=0, description="Minimum number of attempts")
    max_attempts: int = Field(ge=0, description="Maximum number of attempts")


class ProgressSettings(BaseModel):
    """Settings for progress report configuration."""

    survey_key: str = Field(None, description="Survey key column")
    survey_id: str | None = Field(..., min_length=1, description="Survey ID column")
    survey_date: str | None = Field(None, description="Survey date column")
    enumerator: str | None = Field(None, description="Enumerator ID column")
    survey_target: int | None = Field(
        None, ge=0, description="Target number of surveys"
    )
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

    attempted_interviews: Any = Field(
        description="DataFrame with attempted interviews data"
    )
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


@st.cache_data(ttl=60)
def load_default_settings(
    settings_file: str, config: ProgressSettings
) -> ProgressSettings:
    """Load and merge saved settings with default configuration.

    Loads previously saved progress report settings from the settings file
    and merges them with the provided default configuration. Saved settings
    take precedence over defaults.

    Cached for 60 seconds to reduce file I/O operations.

    Parameters
    ----------
    settings_file : str
        Path to the settings file containing saved progress configurations.
    config : ProgressSettings
        Default configuration to use as fallback for missing settings.

    Returns
    -------
    ProgressSettings
        Merged settings combining saved and default configurations.
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
    """Create and render the settings UI for progress report configuration.

    This function creates a comprehensive Streamlit UI for configuring
    progress report settings. It includes:
    - Survey identifiers (key and ID columns)
    - Survey date column selection
    - Enumerator ID column
    - Submission targets (total and per period)

    Settings are automatically saved to the settings file when changed
    and loaded from previous sessions if available.

    Parameters
    ----------
    settings_file : str
        Path to settings file for saving/loading configurations.
    config : ProgressSettings
        Default configuration used as fallback values.
    categorical_columns : list[str]
        Available categorical columns for selection (survey key, ID, enumerator).
    datetime_columns : list[str]
        Available datetime columns for date selection.

    Returns
    -------
    ProgressSettings
        User-configured settings from the UI.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for progress report")
        st.write("---")

        # Load default settings
        default_settings = load_default_settings(settings_file, config)

        st.write(default_settings)

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
        target_submissions_per_period=target_per_period
        if target_per_period > 0
        else None,
    )


# =============================================================================
# Progress Summary - Computation and Display
# =============================================================================


@st.cache_data
def compute_progress_summary(data: pl.DataFrame, target: int | None) -> ProgressSummary:
    """Compute summary statistics for progress report.

    Calculates the total number of submitted surveys and the percentage
    of the target completed. If no target is provided, percentage is 0.

    Parameters
    ----------
    data : pl.DataFrame
        Survey data containing all submitted interviews.
    target : int | None
        Target number of surveys to collect. If None, percentage is set to 0.

    Returns
    -------
    ProgressSummary
        Pydantic model containing total_submitted, target, and percentage_completed.
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
    """Display summary statistics and progress metrics in Streamlit UI.

    Renders three columns showing:
    - Progress bar with percentage completion (if target is set)
    - Target interviews metric
    - Total submitted interviews metric

    If no target is set, displays informational messages guiding users
    to configure settings.

    Parameters
    ----------
    data : pl.DataFrame
        Survey data containing all submitted interviews.
    target : int | None
        Target number of surveys to collect. If None, shows info messages.
    """
    progress_summary = compute_progress_summary(data, target)

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
        period_stats = (
            data.select(pl.col(date).cast(pl.Date).alias("time_period"))
            .group_by("time_period")
            .agg(pl.len().alias("num_interviews"))
            .sort("time_period")
        )
    elif validated_period == "Week":
        period_stats = (
            data.select(
                pl.col(date).cast(pl.Date).dt.truncate("1w").alias("time_period")
            )
            .group_by("time_period")
            .agg(pl.len().alias("num_interviews"))
            .sort("time_period")
        )
    elif validated_period == "Month":
        period_stats = (
            data.select(
                pl.col(date).cast(pl.Date).dt.truncate("1mo").alias("time_period")
            )
            .group_by("time_period")
            .agg(pl.len().alias("num_interviews"))
            .sort("time_period")
        )

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


def render_time_period_selector(
    settings_file: str, tab_name: str
) -> Literal["Day", "Week", "Month"]:
    """Render time period selector UI using Streamlit pills component.

    Creates a pills selector allowing users to choose the aggregation period
    for progress over time visualization (Daily, Weekly, or Monthly).
    The selected value is saved to settings and persisted across sessions.

    Parameters
    ----------
    settings_file : str
        Path to settings file for saving/loading the selected time period.
    tab_name : str
        Name of the tab for namespacing saved settings.

    Returns
    -------
    Literal["Day", "Week", "Month"]
        Selected time period for aggregation.
    """
    with st.container(horizontal_alignment="left"):
        options_map = {
            "Day": ":material/event: Daily",
            "Week": ":material/date_range: Weekly",
            "Month": ":material/calendar_month: Monthly",
        }

        saved_settings = load_check_settings(settings_file, tab_name) or {}
        default_time_period = saved_settings.get("time_period", "Day")

        time_period = st.pills(
            label="Time Period",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            key="time_period_progress_overtime",
            default=default_time_period,
            help="Select time period for aggregating progress data",
            selection_mode="single",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_time_period"},
        )

        save_check_settings(settings_file, TAB_NAME, {"time_period": time_period})

    return time_period


@demo_output_onboarding(TAB_NAME)
@st.fragment
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

    time_period = render_time_period_selector(setting_file, TAB_NAME)

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

    st.plotly_chart(fig, theme=None, width="stretch")


# =============================================================================
# Progress Chart - Consent and Completion
# =============================================================================


@st.cache_data
def compute_progress_chart(
    data: pl.DataFrame,
    consent_col: str | None,
    consent_vals: list[Any] | None,
    outcome_col: str | None,
    outcome_vals: list[Any] | None,
) -> tuple[float, float]:
    """Compute progress chart statistics using Polars for performance.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset (using Polars for better performance)
    consent_col : str | None
        Column name for consent
    consent_vals : list | None
        List of consent values indicating valid consent
    outcome_col : str | None
        Column name for outcome
    outcome_vals : list | None
        List of outcome values indicating survey completion

    Returns
    -------
    tuple[float, float]
        (consent_percentage, completion_percentage)
    """
    total_submitted = data.height

    # Calculate consent percentage using Polars
    if consent_col and consent_vals:
        valid_consent_count = data.filter(
            pl.col(consent_col).is_in(consent_vals)
        ).height
        consent_percentage = (
            (valid_consent_count / total_submitted) * 100 if total_submitted > 0 else 0
        )
    else:
        consent_percentage = 0.0

    # Calculate completion percentage using Polars
    if outcome_col and outcome_vals:
        completed_count = data.filter(pl.col(outcome_col).is_in(outcome_vals)).height
        completion_percentage = (
            (completed_count / total_submitted) * 100 if total_submitted > 0 else 0
        )
    else:
        completion_percentage = 0.0

    return consent_percentage, completion_percentage


@st.cache_data
def _get_unique_values(data: pl.DataFrame, column: str) -> list[Any]:
    """Get unique values from a Polars DataFrame column (cached for performance).

    Parameters
    ----------
    data : pl.DataFrame
        Dataset
    column : str
        Column name

    Returns
    -------
    list[Any]
        List of unique values
    """
    return data[column].unique().to_list()


def _render_column_value_selection(
    data: pl.DataFrame,
    setting_file: str,
    survey_cols: list[str],
    default_column: str | None,
    default_values: list[Any] | None,
    column_label: str,
    column_key: str,
    values_key: str,
    column_help: str,
    values_help: str,
    info_message: str,
) -> tuple[str | None, list[Any] | None]:
    """Render column and value selection UI with consistent behavior.

    Parameters
    ----------
    data : pl.DataFrame
        Survey data containing columns.
    setting_file : str
        Path to settings file for saving configurations.
    survey_cols : list[str]
        Available column options.
    default_column : str | None
        Default selected column.
    default_values : list[Any] | None
        Default selected values.
    column_label : str
        Label for column selection.
    column_key : str
        Streamlit key for column selectbox.
    values_key : str
        Streamlit key for values multiselect.
    column_help : str
        Help text for column selection.
    values_help : str
        Help text for values selection.
    info_message : str
        Message to display when no column is selected.

    Returns
    -------
    tuple[str | None, list[Any] | None]
        Selected column and values.
    """
    # Column selection
    column_index = (
        survey_cols.index(default_column)
        if default_column and default_column in survey_cols
        else None
    )
    selected_column = st.selectbox(
        label=column_label,
        options=survey_cols,
        help=column_help,
        key=column_key,
        index=column_index,
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + f"_{column_key.split('_')[-1]}"},
    )
    save_check_settings(
        setting_file, TAB_NAME, {column_key.split("_")[-1]: selected_column}
    )

    # Value selection (only if column is selected)
    if not selected_column:
        st.info(info_message)
        return selected_column, None

    value_options = _get_unique_values(data, selected_column)
    default_vals = (
        default_values if default_values and default_values in value_options else None
    )
    selected_values = st.multiselect(
        label=f"Select {column_label.lower()} values",
        options=value_options,
        help=values_help,
        key=values_key,
        default=default_vals,
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + f"_{values_key.split('_')[0]}_vals"},
    )
    save_check_settings(
        setting_file, TAB_NAME, {f"{values_key.split('_')[0]}_vals": selected_values}
    )

    return selected_column, selected_values


def _display_chart_if_configured(
    column: str | None,
    values: list[Any] | None,
    percentage: float,
    chart_title: str,
) -> None:
    """Display donut chart if column and values are configured.

    Parameters
    ----------
    column : str | None
        Selected column name.
    values : list[Any] | None
        Selected values for the column.
    percentage : float
        Percentage value to display in chart.
    chart_title : str
        Title to display above the chart.
    """
    if column and values:
        chart = donut_chart2(actual_value=int(percentage))
        st.markdown(f"**{chart_title}**")
        st.pyplot(chart, width="stretch")


@demo_output_onboarding(TAB_NAME)
def display_progress_chart(data: pl.DataFrame, setting_file: str) -> None:
    """Display consent and completion progress charts with interactive configuration.

    Renders two donut charts showing:
    - Percentage of valid consent (left chart)
    - Percentage of survey completion (right chart)

    Users can select consent and outcome columns via dropdowns, then
    specify which values indicate valid consent or completion. Settings
    are automatically saved and loaded across sessions.

    Parameters
    ----------
    data : pl.DataFrame
        Survey data containing consent and outcome columns (Polars for performance).
    setting_file : str
        Path to settings file for saving/loading configurations.
    """
    survey_cols = data.columns
    _, cc1, _, cc2, _ = st.columns([0.1, 0.35, 0.1, 0.35, 0.1])

    # Load default settings
    default_settings = (
        load_check_settings(settings_file=setting_file, check_name="progress") or {}
    )

    # Consent column and value selection
    with cc1, st.container(border=True):
        consent, consent_vals = _render_column_value_selection(
            data=data,
            setting_file=setting_file,
            survey_cols=survey_cols,
            default_column=default_settings.get("consent"),
            default_values=default_settings.get("consent_vals"),
            column_label="Select consent column",
            column_key="progress_consent_pie_chart",
            values_key="consent_vals_progress_chart",
            column_help="Column containing consent information",
            values_help="Values to consider as valid consent",
            info_message="Select consent column first and then select consent values to display the chart",
        )

    # Outcome column and value selection
    with cc2, st.container(border=True):
        outcome, outcome_vals = _render_column_value_selection(
            data=data,
            setting_file=setting_file,
            survey_cols=survey_cols,
            default_column=default_settings.get("outcome"),
            default_values=default_settings.get("outcome_vals"),
            column_label="Select outcome column",
            column_key="outcome_progress_chart",
            values_key="outcome_vals_progress_chart",
            column_help="Column containing outcome information",
            values_help="Values to consider as completed surveys",
            info_message="Select outcome column first and then select outcome values to display the chart",
        )

    # Compute percentages
    consent_percentage, completion_percentage = compute_progress_chart(
        data=data,
        consent_col=consent,
        consent_vals=consent_vals,
        outcome_col=outcome,
        outcome_vals=outcome_vals,
    )

    # Display charts
    with cc1:
        _display_chart_if_configured(
            consent, consent_vals, consent_percentage, "% consent"
        )

    with cc2:
        _display_chart_if_configured(
            outcome, outcome_vals, completion_percentage, "% completion"
        )


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
    return (
        data.group_by(survey_id)
        .agg(
            [
                pl.len().alias("num_interviews"),
                pl.col(date).max().alias("last_attempt_date"),
                pl.col(date).alias("attempt_dates"),
            ]
        )
        .sort(survey_id)
    )


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
    max_attempts = attempts_df.select(pl.col("attempt_dates").list.len().max()).item()

    # Explode attempt dates into separate columns
    # Use list.get with default=None to handle lists shorter than max_attempts
    for i in range(max_attempts):
        attempts_df = attempts_df.with_columns(
            pl.col("attempt_dates")
            .list.get(i, null_on_oob=True)
            .alias(f"Attempt Date {i + 1}")
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
    filled_data = sorted_data.with_columns(
        [
            pl.col(col).forward_fill().backward_fill().over(survey_id)
            for col in display_cols
        ]
    )

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

        # Reorder columns: survey_id, num_interviews, last_attempt_date,
        # display_cols, attempt dates
        attempt_date_cols = [
            col
            for col in attempted_interviews.columns
            if col.startswith("Attempt Date")
        ]
        ordered_cols = (
            [survey_id, "num_interviews", "last_attempt_date"]
            + display_cols
            + attempt_date_cols
        )
        attempted_interviews = attempted_interviews.select(ordered_cols)

    # Step 4: Calculate summary statistics
    num_unique, min_attempts, max_attempts = _compute_summary_stats(
        attempted_interviews
    )

    return AttemptedInterviewsResult(
        attempted_interviews=attempted_interviews,
        total_submitted=total_submitted,
        number_of_unique_ids=num_unique,
        min_attempts=min_attempts,
        max_attempts=max_attempts,
    )


@demo_output_onboarding(TAB_NAME)
@st.fragment
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
            kwargs=({"state_name": TAB_NAME + "_display_cols"}),
        )

        save_check_settings(
            setting_file,
            TAB_NAME,
            {"display_cols": display_cols},
        )

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
            attempted_interviews.group_by("num_interviews")
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

        # Convert attempts to strings for categorical axis
        num_interviews_str = [str(int(x)) for x in num_interviews_list]

        # Create custom hover text
        hover_text = [
            f"<b>{attempts} Attempts</b><br>Percentage: {pct:.1f}%<br>Frequency: {freq}"
            for attempts, pct, freq in zip(
                num_interviews_list, percentage_list, frequency_list, strict=False
            )
        ]

        # Create figure using go.Bar for better control
        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=percentage_list,
                y=num_interviews_str,
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
                "type": "category",
                "showgrid": False,
                "gridcolor": "lightgrey",
                "autorange": "reversed",
            },
        )
        st.plotly_chart(fig, width="stretch")

    with ai2:
        # Convert to pandas for styling (Streamlit doesn't support Polars styling yet)
        attempts_pd = attempted_interviews.to_pandas()
        # Dynamically set pd styler max elements based on DataFrame size
        pd.set_option("styler.render.max_elements", attempts_pd.size + 1)

        cmap = sns.light_palette("pink", as_cmap=True)
        vmin = attempts_pd["num_interviews"].min()
        vmax = attempts_pd["num_interviews"].max()

        st.dataframe(
            data=attempts_pd.style.background_gradient(
                subset=["num_interviews"],
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
            ),
            width="stretch",
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
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
    survey_columns: ColumnByType,
) -> None:
    """Display comprehensive progress tracking report with multiple sections.

    Main entry point for the progress report module. Renders a complete
    progress tracking dashboard including:
    - Settings configuration UI
    - Progress summary with target tracking
    - Progress over time visualization
    - Attempted interviews analysis

    The report supports both Pandas and Polars DataFrames, converts column
    information, and orchestrates all sub-components.

    Parameters
    ----------
    project_id : str
        Unique identifier for the current project.
    page_name_id : str
        Identifier for the current page/tab.
    data : pl.DataFrame
        Survey data to analyze and display.
    setting_file : str
        Path to settings file for configuration persistence.
    config : dict
        Default configuration dictionary to initialize ProgressSettings.
    survey_columns : ColumnByType
        Column names categorized by data type.
    """
    # get column info
    datetime_columns = survey_columns.datetime_columns
    categorical_columns = survey_columns.categorical_columns

    st.title("Progress Tracking")

    # Load settings
    config_settings = ProgressSettings(**config)
    progress_settings = progress_report_settings(
        setting_file, config_settings, categorical_columns, datetime_columns
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
