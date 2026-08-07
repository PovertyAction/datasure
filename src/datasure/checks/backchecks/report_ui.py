"""Report-rendering UI for the backchecks report."""

from typing import Literal

import polars as pl
import streamlit as st

from datasure.checks.backchecks.compute import (
    compute_backcheck_analysis,
    compute_backchecker_productivity,
    compute_column_stats,
    compute_enumerator_backchecker_stats,
    expand_col_names,
)
from datasure.checks.backchecks.models import (
    TAB_NAME,
    WEEKDAY_NAMES,
    WEEKDAY_OFFSET_MAP,
    BackcheckSettings,
    BackcheckTestOptions,
    OkRangeOptions,
    OkRangeType,
    OkRangeValues,
    SearchType,
)
from datasure.checks.backchecks.settings_ui import backchecks_report_settings
from datasure.utils.dataframe_utils import ColumnByType
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.navigations_utils import demo_callout, show_demo_next_action
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

# ==============================================================================
# COLUMN CONFIGURATION FUNCTIONS
# ==============================================================================


def _get_ok_range_value(ok_range_type: OkRangeType) -> OkRangeValues:
    """Get the OK range value based on the selected type."""
    okr1, okr2 = st.columns(2)
    if ok_range_type == "number":
        okr_neg = okr1.number_input(
            "Negative Range Value",
            max_value=0.0,
            value=0.0,
            step=1.0,
            help="Enter the negative range value",
        )
        okr_pos = okr2.number_input(
            "Positive Range Value",
            min_value=0.0,
            value=0.0,
            step=1.0,
            help="Enter the positive range value",
        )

    else:
        okr_neg = okr1.number_input(
            "Negative Range Value (%)",
            min_value=-100.0,
            max_value=0.0,
            value=0.0,
            step=1.0,
            help="Enter the negative range percentage",
        )
        okr_pos = okr2.number_input(
            "Positive Range Value (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            help="Enter the positive range percentage",
        )

    return OkRangeValues(ok_range_neg=okr_neg, ok_range_pos=okr_pos)


def _render_backchecks_column_actions(
    project_id: str,
    page_name_id: str,
    survey_data,
    backcheck_data,
    common_columns: list[str],
) -> None:
    """Render the backcheck column configuration UI.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    common_columns : list[str]
        List of columns common to both survey and backcheck data.
    """
    backcheck_settings = duckdb_get_table(
        project_id,
        f"backchecks_{page_name_id}",
        "logs",
    )

    os1, os2, _ = st.columns([0.4, 0.3, 0.3])
    with os1:
        st.button(
            "Add Backcheck Column",
            key="add_backcheck_column",
            help="Add a new backcheck column configuration.",
            width="stretch",
            type="primary",
            on_click=_add_backcheck_column,
            args=(
                project_id,
                page_name_id,
                survey_data,
                backcheck_data,
                common_columns,
            ),
        )
    with os2:
        _delete_backcheck_column(project_id, page_name_id, backcheck_settings)

    if backcheck_settings.is_empty():
        st.info(
            "Use the :material/add: button to add columns for backcheck comparison and the "
            ":material/delete: button to remove columns."
        )
    else:
        _render_backcheck_settings_table(backcheck_settings)


@st.dialog("Add Backcheck Column(s)", width="medium")
def _add_backcheck_column(
    project_id: str,
    page_name_id: str,
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    common_columns: list[str],
) -> None:
    """Dialog to add a new backcheck column configuration.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    common_columns : list[str]
        List of columns common to both survey and backcheck data.
    """
    # Render search type selection
    search_type, pattern, backcheck_cols, _lock_cols_initial = (
        _render_search_type_selection(common_columns)
    )

    if backcheck_cols:
        # Render backcheck category
        backcheck_category = _render_backcheck_category_options()

        if backcheck_category:
            # Render OK range options
            # Check if columns are numeric in both datasets
            cols_numeric_in_survey = all(
                survey_data.schema[col].is_numeric()
                for col in backcheck_cols
                if col in survey_data.columns
            )

            cols_numeric_in_backcheck = all(
                backcheck_data.schema[col].is_numeric()
                for col in backcheck_cols
                if col in backcheck_data.columns
            )

            # Only show OK range options for numeric columns
            if cols_numeric_in_survey and cols_numeric_in_backcheck:
                ok_range_options: OkRangeOptions = _render_ok_range_options()
                backcheck_test_options: BackcheckTestOptions = (
                    _render_backcheck_test_options(backcheck_category)
                )
            else:
                ok_range_options = OkRangeOptions(
                    ok_range_type=None, ok_range_values=None
                )
                backcheck_test_options = BackcheckTestOptions(
                    ttest=False, prtest=False, signrank=False, reliability=False
                )

            if st.button(
                "Add Backcheck Column Configuration",
                key="confirm_add_backcheck_column",
                type="primary",
                width="stretch",
                disabled=not backcheck_cols or not backcheck_category,
            ):
                _update_backcheck_column_config(
                    project_id,
                    page_name_id,
                    search_type,
                    pattern,
                    backcheck_cols,
                    backcheck_category,
                    ok_range_options,
                    backcheck_test_options,
                )

                st.success("Backcheck column configuration added successfully.")
                st.rerun()


def _update_backcheck_column_config(
    project_id: str,
    page_name_id: str,
    search_type: str,
    pattern: str | None,
    backcheck_cols: list[str],
    backcheck_category: int,
    ok_range_options: OkRangeOptions,
    backcheck_test_options: BackcheckTestOptions,
) -> None:
    """Update the backcheck column configuration in the database.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    search_type : str
        Search type used.
    pattern : str | None
        Pattern for column matching.
    backcheck_cols : list[str]
        Selected columns.
    category : int
        Backcheck category (1, 2, or 3).
    ok_range : str
        OK range value.
    comparison_condition : str
        Comparison condition.
    """
    # Get existing config
    existing_config = duckdb_get_table(
        project_id=project_id,
        alias=f"backchecks_{page_name_id}",
        db_name="logs",
    )

    # Prepare new configuration
    new_config = {
        "search_type": search_type,
        "pattern": pattern,
        "column_name": [backcheck_cols],
        "category": backcheck_category,
        "ok_range_type": ok_range_options.ok_range_type if ok_range_options else None,
        "ok_range_values": ok_range_options.ok_range_values
        if ok_range_options
        else None,
        "ttest": backcheck_test_options.ttest,
        "prtest": backcheck_test_options.prtest,
        "signrank": backcheck_test_options.signrank,
        "reliability": backcheck_test_options.reliability,
    }

    schema = {
        "search_type": pl.Utf8,
        "pattern": pl.Utf8,
        "column_name": pl.List(pl.Utf8),
        "category": pl.Int64,
        "ok_range_type": pl.Utf8,
        "ok_range_values": pl.List(pl.Float64),
        "ttest": pl.Boolean,
        "prtest": pl.Boolean,
        "signrank": pl.Boolean,
        "reliability": pl.Boolean,
    }

    # Append new configuration to existing polars DataFrame
    new_config_df = pl.DataFrame(new_config, schema=schema)
    if not existing_config.is_empty():
        updated_config = pl.concat([existing_config, new_config_df], how="vertical")
    else:
        updated_config = new_config_df

    # Save updated configuration back to the database
    duckdb_save_table(
        project_id,
        updated_config,
        f"backchecks_{page_name_id}",
        db_name="logs",
    )


def _delete_backcheck_column(
    project_id: str, page_name_id: str, backcheck_settings: pl.DataFrame
) -> None:
    """Render delete backcheck column button and handle deletion.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    backcheck_settings : pl.DataFrame
        Current backcheck settings.
    """
    with st.popover(
        label=":material/delete: Delete backcheck column",
        width="stretch",
    ):
        st.markdown("#### Remove backcheck columns")

        if backcheck_settings.is_empty():
            st.info("No backcheck columns have been added yet.")
        else:
            backcheck_settings_indexed = (
                backcheck_settings.with_row_index().with_columns(
                    (
                        pl.col("index").cast(pl.Utf8)
                        + " - "
                        + pl.col("search_type")
                        + " - "
                        + pl.col("pattern").fill_null("")
                    ).alias("composite_index")
                )
            )

            unique_index = (
                backcheck_settings_indexed["composite_index"]
                .unique(maintain_order=True)
                .to_list()
            )

            selected_index = st.selectbox(
                label="Select backcheck column to remove",
                options=unique_index,
                help="Select the backcheck column to remove from the list.",
            )

            if st.button(
                label="Confirm deletion",
                type="primary",
                width="stretch",
                key="confirm_delete_backcheck_column",
                help="Click to remove the selected backcheck column configuration.",
                disabled=not selected_index,
            ):
                updated_settings = backcheck_settings_indexed.filter(
                    pl.col("composite_index") != selected_index
                ).drop("composite_index", "index")

                duckdb_save_table(
                    project_id,
                    updated_settings,
                    f"backchecks_{page_name_id}",
                    "logs",
                )

                st.rerun()


def _render_backcheck_settings_table(backcheck_settings: pl.DataFrame) -> None:
    """Render the backcheck settings table in Streamlit.

    Parameters
    ----------
    backcheck_settings : pl.DataFrame
        Backcheck settings configuration.
    """
    with st.expander("Backcheck Column Settings", expanded=False):
        st.dataframe(
            backcheck_settings,
            width="stretch",
            hide_index=True,
            column_config={
                "search_type": st.column_config.Column("Search Type"),
                "pattern": st.column_config.Column("Pattern"),
                "column_name": st.column_config.Column("Column Name(s)"),
                "category": st.column_config.NumberColumn("Category"),
                "ok_range_type": st.column_config.Column("OK Range Type"),
                "ok_range_values": st.column_config.Column("OK Range Values"),
                "ttest": st.column_config.CheckboxColumn("t-test"),
                "prtest": st.column_config.CheckboxColumn("prtest"),
                "signrank": st.column_config.CheckboxColumn("Sign Rank Test"),
                "reliability": st.column_config.CheckboxColumn("Reliability Analysis"),
            },
        )


# =============================================================================
# Backcheck Column Actions - UI Configuration
# =============================================================================


def _render_search_type_selection(
    common_columns: list[str],
) -> tuple[str, str | None, list[str], bool]:
    """Render search type selection UI for backcheck columns.

    Parameters
    ----------
    common_columns : list[str]
        List of columns common to both survey and backcheck data.

    Returns
    -------
    tuple[str, str | None, list[str], bool]
        Search type, pattern, selected columns, and lock_cols flag.
    """
    search_type_options = [e.value for e in SearchType]
    search_type = st.selectbox(
        label="Search type",
        options=search_type_options,
        index=0,
        help="Select the type of search to perform on the column names.",
    )

    if search_type == SearchType.EXACT.value:
        backcheck_cols_sel = st.multiselect(
            label="Select columns to configure for backcheck",
            options=common_columns,
            default=None,
            help="Select column or group of columns to configure for backcheck comparison.",
        )
        pattern, lock_cols = None, None
        return search_type, pattern, backcheck_cols_sel, lock_cols
    else:
        pattern = st.text_input(
            label="Enter pattern to match column names",
            placeholder="Enter pattern to match column names",
            help="Enter the pattern to match column names based on the "
            "selected search type.",
        )
        if pattern:
            backcheck_cols_patt = expand_col_names(
                common_columns, pattern, search_type=search_type
            )
        else:
            backcheck_cols_patt = []

        st.write(
            "**Columns Selected:** ",
            ", ".join(backcheck_cols_patt) if backcheck_cols_patt else "None",
        )
        return search_type, pattern, backcheck_cols_patt, None


def _render_backcheck_category_options() -> int:
    """Render backcheck category selection UI.

    Returns
    -------
    int
        Selected category (1, 2, or 3).
    """
    with st.container(border=True):
        st.markdown("##### Backcheck Category Selection")
        options_map = {
            1: ":material/looks_one: Category 1",
            2: ":material/looks_two: Category 2",
            3: ":material/looks_3: Category 3",
        }

        category = st.pills(
            "Select Backcheck Category",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            selection_mode="single",
            default=None,
            help="Select the backcheck category for the column(s).",
        )
    return category


def _render_ok_range_options() -> OkRangeOptions:
    """Render OK range options UI.

    Returns
    -------
    tuple[str, str]
        OK range type and OK range value.
    """
    with st.container(border=True):
        st.markdown("##### OK Range Selection")
        options_map = {
            "number": ":material/123: Value Range",
            "percentage": ":material/percent: Percentage Range",
        }
        ok_range_type = st.pills(
            "Select OK Range Type",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            selection_mode="single",
            default=None,
            help="Select the type of OK range condition for the column(s).",
            key="ok_range_type_backchecks_pills",
        )
        if ok_range_type:
            ok_range_value: OkRangeValues = _get_ok_range_value(
                OkRangeType(ok_range_type)
            )
        else:
            ok_range_value = OkRangeValues(ok_range_neg=0.0, ok_range_pos=0.0)

    return OkRangeOptions(ok_range_type=ok_range_type, ok_range_value=ok_range_value)


def _render_backcheck_test_options(backcheck_category: int) -> BackcheckTestOptions:
    """Render backcheck test condition selection UI.

    Returns
    -------
    str
        Selected Back Check Test
    """
    with st.container(border=True):
        st.markdown("##### Statistical Test")
        with st.expander("Statisical Test Information", expanded=False):
            st.write(
                """
                Select the statistical test to apply for backcheck comparisons.

                - **ttest**: run paired two-sample mean-comparison tests for values in the back check and survey data.
                - **prtest**: run two-sample test of equality of proportions in the back check and survey data for dichotmous variables.
                - **signrank**: run Wilcoxon signed-rank tests for values in the back check and survey data.
                - **reliability**: calculate the simple response variance (SRV) and reliability ratio for type 2 and 3 variables.
                """
            )
        options_map = {
            "ttest": "t-test",
            "prtest": "prtest",
            "signrank": "sign rank test",
            "reliability": "reliability analysis",
        }

        # dont show reliability if category 1 is selected
        if backcheck_category == 1:
            options_map.pop("reliability")

        backcheck_test = st.pills(
            "Select Backcheck Statistical Test",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            selection_mode="multi",
            default="ttest",
            help="Select the statistical test to apply for backcheck comparisons.",
            key="backcheck_test_backchecks_pills",
        )

    return BackcheckTestOptions(
        ttest="ttest" in backcheck_test,
        prtest="prtest" in backcheck_test,
        signrank="signrank" in backcheck_test,
        reliability="reliability" in backcheck_test,
    )


# ==============================================================================
# RESULTS DISPLAY RENDER FUNCTIONS
# ==============================================================================


def _render_backcheck_summary(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    backcheck_analysis: pl.DataFrame,
    backcheck_settings: BackcheckSettings,
) -> None:
    """Render summary metrics for backcheck analysis.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    backcheck_analysis : pl.DataFrame
        Results from compute_backcheck_analysis.
    backcheck_settings : BackcheckSettings
        Backcheck settings including enumerator and backchecker columns.
    """
    # Calculate basic metrics
    n_survey_obs = len(survey_data)
    n_backcheck_obs = len(backcheck_data)

    # Calculate percentage of surveys with backcheck responses
    # Get unique survey keys that have backchecks
    survey_key = backcheck_settings.survey_key
    if survey_key and not backcheck_analysis.is_empty():
        unique_backchecked_surveys = backcheck_analysis[survey_key].n_unique()
        backcheck_coverage_pct = (
            (unique_backchecked_surveys / n_survey_obs * 100) if n_survey_obs > 0 else 0
        )
    else:
        backcheck_coverage_pct = 0

    # Count unique enumerators and back checkers
    enumerator_col = backcheck_settings.enumerator
    backchecker_col = backcheck_settings.backchecker

    if enumerator_col and enumerator_col in survey_data.columns:
        n_enumerators = survey_data[enumerator_col].n_unique()
    else:
        n_enumerators = 0

    if backchecker_col and backchecker_col in backcheck_data.columns:
        n_backcheckers = backcheck_data[backchecker_col].n_unique()
    else:
        n_backcheckers = 0

    # Display metrics in columns
    uc1, uc2, uc3, _ = st.columns(4)
    lc1, lc2, _, _ = st.columns(4)

    with uc1, st.container(border=True):
        st.metric("Survey Observations", f"{n_survey_obs:,}")

    with uc2, st.container(border=True):
        st.metric("Backcheck Observations", f"{n_backcheck_obs:,}")

    with uc3, st.container(border=True):
        st.metric(
            "Backcheck Coverage",
            f"{backcheck_coverage_pct:.1f}%",
        )

    with lc1, st.container(border=True):
        st.metric(
            "Total Enumerators", f"{n_enumerators:,}" if n_enumerators > 0 else "N/A"
        )

    with lc2, st.container(border=True):
        st.metric(
            "Total Back Checkers",
            f"{n_backcheckers:,}" if n_backcheckers > 0 else "N/A",
        )


def _render_backchecker_productivity(
    data: pl.DataFrame,
    date: str,
    backchecker: str,
    settings_file: str,
) -> None:
    """Display backchecker productivity table.

    Shows backcheck submission counts by backchecker over time with configurable
    time periods (daily, weekly, monthly).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing backcheck data.
    date : str
        Date column name.
    backchecker : str
        Backchecker column name.
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    if not (backchecker and date):
        st.info(
            "Backchecker productivity requires a date and backchecker column to be selected. "
            "Go to the :material/settings: settings section above to select them."
        )
        return

    _render_backchecker_productivity_table(data, date, backchecker, settings_file)


@st.fragment
def _render_backchecker_productivity_table(
    data: pl.DataFrame,
    date: str,
    backchecker: str,
    settings_file: str,
) -> None:
    """Display backchecker productivity table.

    Shows backcheck submission counts by backchecker over time with configurable
    time periods (daily, weekly, monthly).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing backcheck data.
    date : str
        Date column name.
    backchecker : str
        Backchecker column name.
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    time_period = _render_time_period_selector_backchecks(settings_file)
    if time_period == "Week":
        weekstartday = _render_weekday_selector_backchecks(settings_file)
    else:
        weekstartday = "MON"  # Default value, not used for non-weekly periods

    group_by_cols = [backchecker]
    productivity_df = compute_backchecker_productivity(
        data, date, group_by_cols, time_period, weekstartday
    )

    column_config = {
        backchecker: st.column_config.TextColumn("Back Checker", pinned=True),
    }

    column_config.update(
        {
            col: st.column_config.NumberColumn(col, format="%d")
            for col in productivity_df.columns
            if col not in group_by_cols
        }
    )

    st.dataframe(
        productivity_df,
        hide_index=True,
        width="stretch",
        column_config=column_config,
    )


def _render_time_period_selector_backchecks(
    settings_file: str,
) -> Literal["Day", "Week", "Month"]:
    """Render time period selector widget using pills interface for backchecks.

    Displays a pills widget allowing users to choose the time aggregation period
    for backchecker productivity analysis (Day, Week, or Month).

    Parameters
    ----------
    settings_file : str
        Path to settings file for saving/loading configurations.

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

    saved_settings = load_check_settings(settings_file, TAB_NAME) or {}
    default_time_period = saved_settings.get(
        "time_period_backchecker_productivity", "Day"
    )

    with st.container(horizontal_alignment="left"):
        time_period = st.pills(
            label="Time Period",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            key="time_period_backchecker_productivity_key",
            default=default_time_period,
            help="Select time period for aggregating backchecker productivity",
            selection_mode="single",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_time_period_backchecker"},
        )
        save_check_settings(
            settings_file,
            TAB_NAME,
            {"time_period_backchecker_productivity": time_period},
        )

    return time_period or "Day"


def _render_weekday_selector_backchecks(
    settings_file: str,
) -> str:
    """Render weekday selector widget for backchecker productivity analysis.

    Displays a selectbox allowing users to choose the first day of the week
    for weekly productivity calculations.

    Parameters
    ----------
    settings_file : str
        Path to settings file for saving/loading configurations.

    Returns
    -------
    str
        Weekday offset code (e.g., "SUN", "MON") for calculations.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME) or {}
    default_weekstartday_sel = saved_settings.get(
        "weekstartday_backchecker_productivity", "Monday"
    )
    default_weekstartday_sel_index = WEEKDAY_NAMES.index(default_weekstartday_sel)

    cl1, _ = st.columns([1, 3])
    with cl1:
        weekstartday_sel = st.selectbox(
            label="Select the first day of the week",
            options=WEEKDAY_NAMES,
            index=default_weekstartday_sel_index,
            key="week_start_day_backchecker_productivity_key",
            help="Select the first day of the week",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_weekstartday_backchecker"},
        )
    save_check_settings(
        settings_file,
        TAB_NAME,
        {"weekstartday_backchecker_productivity": weekstartday_sel},
    )

    return WEEKDAY_OFFSET_MAP[weekstartday_sel]


def _render_enum_bcer_stats(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    backcheck_analysis: pl.DataFrame,
    backcheck_settings: BackcheckSettings,
    settings_file: str,
) -> None:
    """Render enumerator and backchecker error rate statistics.

    Displays statistics tables showing error rates by category for either
    enumerators or backcheckers, with a pills selector to switch between views.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    backcheck_analysis : pl.DataFrame
        Results from compute_backcheck_analysis.
    backcheck_settings : BackcheckSettings
        Backcheck settings.
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    if backcheck_analysis.is_empty():
        st.info(
            "No backcheck analysis results available. Configure backcheck columns in the settings section above."
        )
        return

    # Check if required columns are configured
    enumerator_col = backcheck_settings.enumerator
    backchecker_col = backcheck_settings.backchecker

    if not enumerator_col and not backchecker_col:
        st.info(
            "Enumerator and backchecker columns are required. "
            "Go to the :material/settings: settings section above to configure them."
        )
        return

    _render_enum_bcer_stats_table(
        survey_data,
        backcheck_data,
        backcheck_analysis,
        backcheck_settings,
        settings_file,
    )


@st.fragment
def _render_enum_bcer_stats_table(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    backcheck_analysis: pl.DataFrame,
    backcheck_settings: BackcheckSettings,
    settings_file: str,
) -> None:
    """Render enumerator and backchecker statistics table with pills selector.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    backcheck_analysis : pl.DataFrame
        Results from compute_backcheck_analysis.
    backcheck_settings : BackcheckSettings
        Backcheck settings.
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    # Determine available options
    enumerator_col = backcheck_settings.enumerator
    backchecker_col = backcheck_settings.backchecker

    options = ["Enumerator", "Backchecker"]

    # Pills selector
    saved_settings = load_check_settings(settings_file, TAB_NAME) or {}
    default_view = saved_settings.get("enum_bcer_stats_view", options[0])

    view_selection = st.pills(
        label="View Statistics",
        options=options,
        default=default_view,
        key="enum_bcer_stats_view_key",
        help="Select which statistics to view",
        selection_mode="single",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_enum_bcer_stats_view"},
    )
    save_check_settings(
        settings_file, TAB_NAME, {"enum_bcer_stats_view": view_selection}
    )

    # Compute and display statistics
    staff_type = "enumerator" if view_selection == "Enumerator" else "backchecker"
    stats_df = compute_enumerator_backchecker_stats(
        survey_data, backcheck_data, backcheck_analysis, backcheck_settings, staff_type
    )

    if stats_df.is_empty():
        st.info(f"No {view_selection.lower()} statistics available.")
        return

    # Get staff column name for display
    staff_col = enumerator_col if staff_type == "enumerator" else backchecker_col

    # Configure columns for wide format
    column_config = {
        staff_col: st.column_config.TextColumn(view_selection, pinned=True),
        "Surveys": st.column_config.NumberColumn("Surveys", format="%d"),
        "Backchecks": st.column_config.NumberColumn("Backchecks", format="%d"),
        "Avg Days": st.column_config.NumberColumn("Avg Days", format="%.1f"),
    }

    # Add category-specific columns
    for category in [1, 2, 3]:
        column_config[f"Non-Missing Survey (Cat {category})"] = (
            st.column_config.NumberColumn(
                f"Survey Values (Cat {category})", format="%d"
            )
        )
        column_config[f"Non-Missing Backcheck (Cat {category})"] = (
            st.column_config.NumberColumn(
                f"Backcheck Values (Cat {category})", format="%d"
            )
        )
        column_config[f"Values Compared (Cat {category})"] = (
            st.column_config.NumberColumn(f"Compared (Cat {category})", format="%d")
        )
        column_config[f"Mismatches (Cat {category})"] = st.column_config.NumberColumn(
            f"Mismatches (Cat {category})", format="%d"
        )
        column_config[f"Error Rate % (Cat {category})"] = st.column_config.NumberColumn(
            f"Error % (Cat {category})", format="%.2f"
        )

    # Add total columns
    column_config["Non-Missing Survey (Total)"] = st.column_config.NumberColumn(
        "Survey Values (Total)", format="%d"
    )
    column_config["Non-Missing Backcheck (Total)"] = st.column_config.NumberColumn(
        "Backcheck Values (Total)", format="%d"
    )
    column_config["Values Compared (Total)"] = st.column_config.NumberColumn(
        "Compared (Total)", format="%d"
    )
    column_config["Mismatches (Total)"] = st.column_config.NumberColumn(
        "Mismatches (Total)", format="%d"
    )
    column_config["Error Rate % (Total)"] = st.column_config.NumberColumn(
        "Error % (Total)", format="%.2f"
    )

    st.dataframe(
        stats_df, hide_index=True, width="stretch", column_config=column_config
    )


def _render_column_stats(
    survey_data: pl.DataFrame,
    backcheck_analysis: pl.DataFrame,
) -> None:
    """Render column statistics for backcheck analysis.

    Displays a table showing statistics for each column configured
    for backcheck analysis.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_analysis : pl.DataFrame
        Results from compute_backcheck_analysis.
    """
    if backcheck_analysis.is_empty():
        st.info(
            "No backcheck analysis results available. Configure backcheck columns in the settings section above."
        )
        return

    # Compute column statistics
    stats_df = compute_column_stats(survey_data, backcheck_analysis)

    if stats_df.is_empty():
        st.info("No column statistics available.")
        return

    # Configure columns
    column_config = {
        "Column Name": st.column_config.TextColumn("Column Name", pinned=True),
        "Category": st.column_config.NumberColumn("Category", format="%d"),
        "Data Type": st.column_config.TextColumn("Data Type"),
        "# of Values": st.column_config.NumberColumn("# of Values", format="%d"),
        "Values Compared": st.column_config.NumberColumn(
            "Values Compared", format="%d"
        ),
        "Mismatches": st.column_config.NumberColumn("Mismatches", format="%d"),
        "Error Rate (%)": st.column_config.NumberColumn(
            "Error Rate (%)", format="%.2f"
        ),
        "Test Results": st.column_config.TextColumn("Test Results", width="large"),
    }

    st.dataframe(
        stats_df, hide_index=True, width="stretch", column_config=column_config
    )


@st.fragment
def _get_available_additional_columns(
    data: pl.DataFrame,
    survey_key: str,
    survey_id: str,
    backcheck_analysis: pl.DataFrame,
) -> list[str]:
    """Get available additional columns for display.

    Parameters
    ----------
    data : pl.DataFrame
        Source data (survey or backcheck).
    survey_key : str
        Survey key column name.
    survey_id : str
        Survey ID column name.
    backcheck_analysis : pl.DataFrame
        Backcheck analysis results.

    Returns
    -------
    list[str]
        List of available additional columns.
    """
    excluded_columns = {
        survey_key,
        survey_id,
        "column_name",
        "survey_value",
        "backcheck_value",
        "match_status",
        "category",
    }

    return sorted(
        [
            col
            for col in data.columns
            if col not in excluded_columns and col not in backcheck_analysis.columns
        ]
    )


def _render_additional_columns_selector(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    survey_key: str,
    survey_id: str,
    backcheck_analysis: pl.DataFrame,
) -> tuple[list[str], list[str]]:
    """Render additional columns selector UI.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    survey_key : str
        Survey key column name.
    survey_id : str
        Survey ID column name.
    backcheck_analysis : pl.DataFrame
        Backcheck analysis results.

    Returns
    -------
    tuple[list[str], list[str]]
        Selected survey and backcheck extra columns.
    """
    with st.expander("Show Additional Columns", expanded=False):
        col1, col2 = st.columns(2)

        survey_additional_cols = _get_available_additional_columns(
            survey_data, survey_key, survey_id, backcheck_analysis
        )
        backcheck_additional_cols = _get_available_additional_columns(
            backcheck_data, survey_key, survey_id, backcheck_analysis
        )

        with col1:
            survey_extra_cols = st.multiselect(
                "Additional Survey Columns",
                options=survey_additional_cols,
                help="Select additional columns from survey data to display",
            )

        with col2:
            backcheck_extra_cols = st.multiselect(
                "Additional Backcheck Columns",
                options=backcheck_additional_cols,
                help="Select additional columns from backcheck data to display",
            )

    return survey_extra_cols, backcheck_extra_cols


def _apply_backcheck_filters(
    backcheck_analysis: pl.DataFrame,
    match_filter: str,
    selected_columns: list[str],
) -> pl.DataFrame:
    """Apply filters to backcheck analysis data.

    Parameters
    ----------
    backcheck_analysis : pl.DataFrame
        Backcheck analysis results.
    match_filter : str
        Match status filter option.
    selected_columns : list[str]
        Selected column names.

    Returns
    -------
    pl.DataFrame
        Filtered data.
    """
    filtered_data = backcheck_analysis.clone()

    # Filter by match status
    if match_filter == "Mismatches Only":
        filtered_data = filtered_data.filter(pl.col("match_status") == "mismatch")

    # Filter by selected columns
    if selected_columns:
        filtered_data = filtered_data.filter(
            pl.col("column_name").is_in(selected_columns)
        )

    return filtered_data


def _join_extra_columns(
    filtered_data: pl.DataFrame,
    source_data: pl.DataFrame,
    survey_key: str,
    join_key: str,
    extra_cols: list[str],
    suffix_label: str,
) -> pl.DataFrame:
    """Join extra display columns from survey or backcheck data onto results.

    Shared by `_add_extra_survey_columns` and `_add_extra_backcheck_columns`,
    which both select extra columns keyed by `survey_key` from a source
    dataset, suffix them with a label identifying their origin, and left-join
    them onto the filtered comparison results - differing only in which
    dataset they read from, which key they join on, and the suffix label.

    Parameters
    ----------
    filtered_data : pl.DataFrame
        Filtered backcheck analysis data.
    source_data : pl.DataFrame
        Source dataset to pull extra columns from (survey or backcheck).
    survey_key : str
        Survey key column name, used to look up rows in `source_data`.
    join_key : str
        Column name in `filtered_data` to join on (the survey key for
        survey columns, or the suffixed backcheck key for backcheck columns).
    extra_cols : list[str]
        Extra columns to add from `source_data`.
    suffix_label : str
        Label appended to each extra column name, e.g. "Survey" or
        "Backcheck".

    Returns
    -------
    pl.DataFrame
        Data with extra columns added.
    """
    if not extra_cols or join_key not in filtered_data.columns:
        return filtered_data

    # Prepare extra columns with unique names
    cols_to_add = source_data.select([survey_key] + extra_cols).unique(
        subset=[survey_key]
    )

    # Rename to match the target join key if it differs from survey_key
    if join_key != survey_key:
        cols_to_add = cols_to_add.rename({survey_key: join_key})

    # Suffix columns to avoid conflicts
    rename_map = {col: f"{col} ({suffix_label})" for col in extra_cols}
    cols_to_add = cols_to_add.rename(rename_map)

    return filtered_data.join(cols_to_add, on=join_key, how="left")


def _add_extra_survey_columns(
    filtered_data: pl.DataFrame,
    survey_data: pl.DataFrame,
    survey_key: str,
    survey_extra_cols: list[str],
) -> pl.DataFrame:
    """Add extra survey columns to filtered data.

    Parameters
    ----------
    filtered_data : pl.DataFrame
        Filtered backcheck analysis data.
    survey_data : pl.DataFrame
        Survey dataset.
    survey_key : str
        Survey key column name.
    survey_extra_cols : list[str]
        Extra columns to add from survey.

    Returns
    -------
    pl.DataFrame
        Data with extra survey columns added.
    """
    return _join_extra_columns(
        filtered_data, survey_data, survey_key, survey_key, survey_extra_cols, "Survey"
    )


def _add_extra_backcheck_columns(
    filtered_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    survey_key: str,
    backcheck_key: str,
    backcheck_extra_cols: list[str],
) -> pl.DataFrame:
    """Add extra backcheck columns to filtered data.

    Parameters
    ----------
    filtered_data : pl.DataFrame
        Filtered backcheck analysis data.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    survey_key : str
        Survey key column name.
    backcheck_key : str
        Backcheck key column name.
    backcheck_extra_cols : list[str]
        Extra columns to add from backcheck.

    Returns
    -------
    pl.DataFrame
        Data with extra backcheck columns added.
    """
    return _join_extra_columns(
        filtered_data,
        backcheck_data,
        survey_key,
        backcheck_key,
        backcheck_extra_cols,
        "Backcheck",
    )


def _build_display_columns(
    filtered_data: pl.DataFrame,
    survey_key: str,
    survey_id: str,
    backcheck_key: str,
) -> list[str]:
    """Build list of columns to display.

    Parameters
    ----------
    filtered_data : pl.DataFrame
        Filtered data.
    survey_key : str
        Survey key column name.
    survey_id : str
        Survey ID column name.
    backcheck_key : str
        Backcheck key column name.

    Returns
    -------
    list[str]
        Ordered list of columns to display.
    """
    display_columns = [
        "column_name",
        "survey_value",
        "backcheck_value",
        "match_status",
        "category",
    ]

    # Add survey_id if it exists
    if survey_id and survey_id in filtered_data.columns:
        display_columns.insert(0, survey_id)

    # Add survey_key if it exists
    if survey_key in filtered_data.columns:
        display_columns.insert(1 if survey_id in display_columns else 0, survey_key)

    # Add backcheck_key if it exists
    if backcheck_key in filtered_data.columns:
        display_columns.insert(2 if survey_id in display_columns else 1, backcheck_key)

    # Add any additional columns requested
    for col in filtered_data.columns:
        if col not in display_columns and (
            col.endswith("(Survey)") or col.endswith("(Backcheck)")
        ):
            display_columns.append(col)

    # Filter to only include columns that exist in the data
    return [col for col in display_columns if col in filtered_data.columns]


def _prepare_display_data(
    filtered_data: pl.DataFrame, display_columns: list[str]
) -> pl.DataFrame:
    """Prepare data for display by selecting columns and removing empty rows.

    Parameters
    ----------
    filtered_data : pl.DataFrame
        Filtered data.
    display_columns : list[str]
        Columns to display.

    Returns
    -------
    pl.DataFrame
        Prepared display data.
    """
    # Select only the display columns
    display_data = filtered_data.select(display_columns)

    # Remove rows where both survey_value and backcheck_value are null
    display_data = display_data.filter(
        ~(pl.col("survey_value").is_null() & pl.col("backcheck_value").is_null())
    )

    return display_data


def _build_column_config(
    survey_key: str, survey_id: str, backcheck_key: str, filtered_data: pl.DataFrame
) -> dict:
    """Build column configuration for dataframe display.

    Parameters
    ----------
    survey_key : str
        Survey key column name.
    survey_id : str
        Survey ID column name.
    backcheck_key : str
        Backcheck key column name.
    filtered_data : pl.DataFrame
        Filtered data.

    Returns
    -------
    dict
        Column configuration dictionary.
    """
    column_config = {
        "column_name": st.column_config.TextColumn("Column Name"),
        "survey_value": st.column_config.TextColumn("Survey Value"),
        "backcheck_value": st.column_config.TextColumn("Backcheck Value"),
        "match_status": st.column_config.TextColumn("Match Status"),
        "category": st.column_config.NumberColumn("Category", format="%d"),
    }

    # Add survey_id to config if it exists (pinned)
    if survey_id and survey_id in filtered_data.columns:
        column_config[survey_id] = st.column_config.TextColumn(survey_id, pinned=True)

    # Add survey_key to config if it exists
    if survey_key in filtered_data.columns:
        column_config[survey_key] = st.column_config.TextColumn("Survey Key")

    # Add backcheck key to config if it exists
    if backcheck_key in filtered_data.columns:
        column_config[backcheck_key] = st.column_config.TextColumn("Backcheck Key")

    return column_config


def _render_backcheck_comparison_results(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    backcheck_analysis: pl.DataFrame,
    backcheck_settings: BackcheckSettings,
) -> None:
    """Render detailed backcheck comparison results with filtering options.

    Displays a table showing each individual comparison with options to filter
    by match status, select specific columns, and add additional data columns.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    backcheck_analysis : pl.DataFrame
        Results from compute_backcheck_analysis.
    backcheck_settings : BackcheckSettings
        Backcheck configuration settings.
    """
    if backcheck_analysis.is_empty():
        st.info(
            "No backcheck comparison results available. Configure backcheck columns in the settings section above."
        )
        return

    # Extract settings
    survey_key = backcheck_settings.survey_key
    survey_id = backcheck_settings.survey_id
    backcheck_key = f"{survey_key}__BCCL"

    # Get available columns from backcheck_analysis
    available_columns = sorted(
        backcheck_analysis["column_name"].unique().drop_nulls().to_list()
    )

    if not available_columns:
        st.info("No comparison results available.")
        return

    # Render filter controls
    selected_columns = st.multiselect(
        "Filter by Columns",
        options=available_columns,
        default=available_columns,
        help="Select which columns to show comparison results for",
    )

    survey_extra_cols, backcheck_extra_cols = _render_additional_columns_selector(
        survey_data, backcheck_data, survey_key, survey_id, backcheck_analysis
    )

    match_filter = st.pills(
        "Filter by Match Status",
        options=["All Results", "Mismatches Only"],
        default="All Results",
        selection_mode="single",
    )

    # Apply filters and add extra columns
    filtered_data = _apply_backcheck_filters(
        backcheck_analysis, match_filter, selected_columns
    )

    if filtered_data.is_empty():
        st.info("No results match the selected filters.")
        return

    filtered_data = _add_extra_survey_columns(
        filtered_data, survey_data, survey_key, survey_extra_cols
    )
    filtered_data = _add_extra_backcheck_columns(
        filtered_data, backcheck_data, survey_key, backcheck_key, backcheck_extra_cols
    )

    # Build display columns and prepare data
    display_columns = _build_display_columns(
        filtered_data, survey_key, survey_id, backcheck_key
    )
    display_data = _prepare_display_data(filtered_data, display_columns)

    if display_data.is_empty():
        st.info("No results match the selected filters.")
        return

    # Display results
    st.caption(f"Showing {len(display_data):,} comparison records")

    column_config = _build_column_config(
        survey_key, survey_id, backcheck_key, display_data
    )

    st.dataframe(
        display_data,
        hide_index=True,
        width="stretch",
        column_config=column_config,
    )


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================


def backchecks_report(
    project_id: str,
    page_name_id: str,
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    setting_file: str,
    config: dict,
    survey_columns: ColumnByType,
    backcheck_columns: ColumnByType,
) -> None:
    """
    Generate and display backchecks report.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    survey_data : pl.DataFrame
        Survey data.
    backcheck_data : pl.DataFrame
        Backcheck data.
    setting_file : str
        Path to the settings file.
    config : dict
        Configuration dictionary.
    """
    st.title("Backchecks Report")

    demo_callout(
        """
        This tab compares original survey responses against back check responses to
        identify discrepancies.

        It has five sections:
        - **Backchecks Columns Configuration**: Define which columns to compare and
          how to categorise them.
        - **Backchecks Summary**: High-level metrics on coverage and backchecker
          productivity.
        - **Enumerator Backchecker Error Statistics**: Error rates broken down by
          enumerator and backchecker.
        - **Column Statistics**: Per-column comparison results and error rates.
        - **Comparison Results Details**: Row-level table of every comparison made.

        **Start here**: Open the :material/settings: settings panel above to confirm
        your column selections, then configure your backcheck columns below.
        """
    )

    # Convert Polars DataFrames to Pandas for compatibility
    survey_data_pd = survey_data.to_pandas()
    backcheck_data_pd = backcheck_data.to_pandas()

    # Get column information for settings UI
    survey_categorical_columns = survey_columns.categorical_columns
    survey_datetime_columns = survey_columns.datetime_columns

    backcheck_categorical_columns = backcheck_columns.categorical_columns
    backcheck_datetime_columns = backcheck_columns.datetime_columns

    # Configure settings
    config_settings = BackcheckSettings(**config)
    backcheck_settings = backchecks_report_settings(
        project_id,
        setting_file,
        survey_data_pd,
        backcheck_data_pd,
        config_settings,
        survey_categorical_columns,
        survey_datetime_columns,
        backcheck_categorical_columns,
        backcheck_datetime_columns,
    )

    # Outlier columns configuration
    st.subheader("Backchecks Columns Configuration")

    demo_callout(
        """
        ##### Backchecks Columns Configuration
        Use the :material/add: **Add Backcheck Column** button to configure which
        columns to compare between the survey and backcheck datasets. For each column
        you can set:
        - **Category**: A numeric group (e.g., 1 for critical questions, 2 for
          secondary questions) used to aggregate error rates in the summary.
        - **OK Range**: An acceptable difference threshold for numeric columns.
        - **Comparison Condition**: How to handle missing values
          (e.g., ignore_missing_values).

        ##### Instructions for Demo:
        Add the following columns using the :material/add: **Add Backcheck Column** button:

        | Column          | Category | OK Range | Comparison Condition  |
        |-----------------|----------|----------|-----------------------|
        | age             | 1        | 1        | ignore_missing_values |
        | household_count | 2        | None     | ignore_missing_values |
        | minc_pri        | 1        | None     | ignore_missing_values |
        | npinc_out       | 1        | None     | ignore_missing_values |
        | no_save         | 1        | None     | ignore_missing_values |
        | pri_govt_sch    | 1        | None     | ignore_missing_values |
        """
    )

    common_columns = list(
        set(survey_categorical_columns).intersection(set(backcheck_categorical_columns))
    )
    _render_backchecks_column_actions(
        project_id, page_name_id, survey_data, backcheck_data, common_columns
    )

    # Compute backcheck analysis
    backcheck_column_settings = duckdb_get_table(
        project_id,
        f"backchecks_{page_name_id}",
        "logs",
    )
    _backcheck_analysis = compute_backcheck_analysis(
        survey_data, backcheck_data, backcheck_settings, backcheck_column_settings
    )

    st.subheader("Backchecks Summary")

    demo_callout(
        """
        ##### Backchecks Summary
        Five metrics appear here: Survey Observations, Backcheck Observations,
        Backcheck Coverage %, Total Enumerators, and Total Back Checkers.

        Below the metrics, a **Backchecker Productivity** table shows submission
        counts per backchecker over time. Use the **Daily / Weekly / Monthly** pills
        to change the time granularity.
        """
    )

    _render_backcheck_summary(
        survey_data, backcheck_data, _backcheck_analysis, backcheck_settings
    )

    _render_backchecker_productivity(
        backcheck_data,
        backcheck_settings.backcheck_date,
        backcheck_settings.backchecker,
        setting_file,
    )

    st.subheader("Enumerator Backchecker Error Statistics")

    demo_callout(
        """
        ##### Enumerator Backchecker Error Statistics
        Use the **Enumerator / Backchecker** pills to switch between two views.
        Each view shows a table with submission counts, values compared, number of
        mismatches, and error rate — broken down by category — for either the
        original enumerator or the backchecker.
        """
    )

    _render_enum_bcer_stats(
        survey_data,
        backcheck_data,
        _backcheck_analysis,
        backcheck_settings,
        setting_file,
    )

    st.subheader("Column Statistics")

    demo_callout(
        """
        ##### Column Statistics
        A table showing per-column comparison results for every column you configured
        above. Columns include: Column Name, Category, Data Type, # of Values,
        Values Compared, Mismatches, Error Rate (%), and Test Results.
        """
    )

    _render_column_stats(survey_data, _backcheck_analysis)

    st.subheader("Comparison Results Details")

    demo_callout(
        """
        ##### Comparison Results Details
        A row-level table of every comparison made between the survey and backcheck
        datasets. Use the **Filter by Columns** multiselect to focus on specific
        columns, and the **Filter by Match Status** pills to show all results or
        mismatches only. You can also add extra columns from the survey or backcheck
        dataset to provide more context alongside each comparison.

        You have reached the end of the DataSure demo. You now have a full picture of
        how DataSure tracks data quality across your survey — from progress and
        missingness through to GPS validation, enumerator performance, and back check
        verification.
        """,
        type="success",
    )

    _render_backcheck_comparison_results(
        survey_data, backcheck_data, _backcheck_analysis, backcheck_settings
    )

    st.write("---")
    demo_callout(
        "You have now explored all the data quality check tabs — Summary, Descriptive Statistics, "
        "Progress Tracking, Missing Values, Duplicates, Outliers & Constraints, GPS Checks, "
        "Enumerator Statistics, and Backcheck Analysis.\n\n"
        "The next step is the **Correct Data** page, where you will learn how to apply targeted "
        "corrections to your survey data based on the quality findings from these checks.\n\n"
        "To get there, click **Correct Data** in the sidebar or use the **Proceed to Correct Data** "
        "button below.",
        type="success",
    )
    show_demo_next_action(5, "st_corr_page", "Proceed to Correct Data")
