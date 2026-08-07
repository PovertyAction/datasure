"""Report-rendering UI for the outliers report."""

from collections.abc import Callable

import polars as pl
import streamlit as st
from pydantic import BaseModel, ValidationError

from datasure.checks.outliers.compute import (
    _build_include_cols,
    _compute_constraint_metrics,
    _compute_outlier_metrics,
    _create_box_plot,
    _create_descriptive_stats,
    _update_unlocked_cols,
    compute_constraint_violations,
    compute_outlier_output,
    expand_col_names,
)
from datasure.checks.outliers.models import (
    TAB_NAME,
    ConstraintBounds,
    ConstraintMetrics,
    OutlierMethod,
    OutlierMetrics,
    OutlierMultipliers,
    OutlierOptionsConfig,
    OutlierSettings,
    OutlierThresholds,
    SearchType,
)
from datasure.checks.outliers.settings_ui import outliers_report_settings
from datasure.utils.dataframe_utils import ColumnByType, sanitize_df_for_join
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.navigations_utils import demo_callout
from datasure.utils.onboarding_utils import is_demo_project
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

# =============================================================================
# Streamlit UI - Metrics Display
# =============================================================================


def _render_constraint_metrics(
    violation_data: pl.DataFrame,
) -> None:
    """Render constraint violation metrics using Streamlit.

    Parameters
    ----------
    violation_data : pl.DataFrame
        DataFrame containing constraint violation data.
    """
    metrics: ConstraintMetrics = _compute_constraint_metrics(violation_data)

    _, _, uc3, uc4 = st.columns(4)
    with uc3, st.container(border=True):
        st.metric(
            label="Number of columns checked",
            value=f"{metrics.columns_checked:,}",
            help="Number of columns checked for constraint violations",
        )
    with uc4, st.container(border=True):
        st.metric(
            label="Total Violations",
            value=f"{metrics.total_violations:,}",
            help="Total number of constraint violations detected",
        )

    lc1, lc2, lc3, lc4 = st.columns(4, border=True)
    lc1.metric(
        label="Hard Min Violations",
        value=f"{metrics.hard_min_violations:,}",
        help="Number of violations below hard minimum",
    )
    lc2.metric(
        label="Soft Min Violations",
        value=f"{metrics.soft_min_violations:,}",
        help="Number of violations below soft minimum",
    )
    lc3.metric(
        label="Soft Max Violations",
        value=f"{metrics.soft_max_violations:,}",
        help="Number of violations above soft maximum",
    )
    lc4.metric(
        label="Hard Max Violations",
        value=f"{metrics.hard_max_violations:,}",
        help="Number of violations above hard maximum",
    )


def _render_outlier_metrics(
    outliers_data: pl.DataFrame,
    settings: OutlierSettings,
) -> None:
    """Render outlier metrics using Streamlit.

    Parameters
    ----------
    outliers_data : pl.DataFrame
        DataFrame containing outlier data.
    settings : OutlierSettings
        Outlier settings configuration.
    """
    metrics: OutlierMetrics = _compute_outlier_metrics(
        outliers_data, settings.enumerator
    )

    uc1, uc2, uc3, uc4 = st.columns(4, border=True)
    uc1.metric(
        label="Number of columns checked",
        value=f"{metrics.columns_checked:,}",
        help="Number of columns checked for outliers",
    )
    uc2.metric(
        label="Columns with Outliers",
        value=f"{metrics.columns_with_outliers:,}",
        help="Number of columns that have outliers detected",
    )
    uc3.metric(
        label="Total Outliers",
        value=f"{metrics.total_outliers:,}",
        help="Total number of outliers detected",
    )
    if settings.enumerator:
        uc4.metric(
            label="Enumerators with Outliers",
            value=f"{metrics.enumerators_with_outliers:,}",
            help="Number of unique enumerators with outliers detected",
        )


# =============================================================================
# Streamlit UI - Table Display
# =============================================================================


def _render_display_columns_expander(
    setting_file: str,
    settings_key: str,
    widget_key: str,
    display_options: list[str],
    info_message: str,
) -> list[str]:
    """Render the "Show more columns" expander and return the selected columns.

    Shared by ``_render_constraint_violations_table`` and ``_render_outlier_table``,
    which both let users add extra context columns to a results table, persisting
    the selection to the settings file under ``settings_key``.

    Parameters
    ----------
    setting_file : str
        Path to settings file.
    settings_key : str
        Key under which the selected columns are persisted in settings, and
        used as the suffix for the ``trigger_save`` state name.
    widget_key : str
        Streamlit widget key for the multiselect.
    display_options : list[str]
        Columns available for selection.
    info_message : str
        Help text shown above the multiselect.

    Returns
    -------
    list[str]
        Columns selected by the user.
    """
    saved_settings = load_check_settings(setting_file, TAB_NAME)
    cols = saved_settings.get(settings_key, [])
    default_display_cols = [col for col in cols if col in display_options]

    with st.expander(":material/clarify: Show more columns in report", expanded=False):
        st.info(info_message)
        display_cols = st.multiselect(
            label="Select columns to display",
            options=display_options,
            default=default_display_cols,
            key=widget_key,
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_" + settings_key},
        )
        save_check_settings(setting_file, TAB_NAME, {settings_key: display_cols})

    return display_cols


def _render_constraint_violations_table(
    data: pl.DataFrame,
    violation_data: pl.DataFrame,
    settings: OutlierSettings,
    setting_file: str,
) -> None:
    """Render constraint violations table using Streamlit.

    Parameters
    ----------
    data : pl.DataFrame
        Original survey data.
    violation_data : pl.DataFrame
        DataFrame containing constraint violation data.
    settings : OutlierSettings
        Outlier settings configuration.
    setting_file : str
        Path to settings file.
    """
    if violation_data.is_empty():
        st.info("No constraint violations detected.")
        return

    all_columns = data.columns

    include_cols = _build_include_cols(
        survey_key=settings.survey_key,
        survey_id=settings.survey_id,
        survey_date=settings.survey_date,
        enumerator=settings.enumerator,
        team=settings.team,
    )

    display_options = [col for col in all_columns if col not in include_cols]

    constraint_display_cols = _render_display_columns_expander(
        setting_file,
        "constraint_display_cols",
        "constraint_violation_display_cols",
        display_options,
        "Select additional columns to include in the constraint violations report.",
    )

    if constraint_display_cols:
        include_cols.extend(constraint_display_cols)

    # select columns to display from data
    display_df = data.select(include_cols)
    # sanitize violation_data to avoid column name conflicts
    violation_df = sanitize_df_for_join(
        main_df=display_df,
        join_df=violation_data,
        join_key=settings.survey_key,
    )

    display_df = display_df.join(
        violation_df,
        on=settings.survey_key,
        how="inner",
    )

    # show only rows with violations
    violations_df = display_df.filter(pl.col("violation reason") != "no violation")

    # add violation type column ie. "Soft Min", "Soft Max", "Hard Min", "Hard Max"
    violation_type_expr = (
        pl.when(pl.col("violation reason").str.contains("below hard minimum"))
        .then(pl.lit("Hard Min"))
        .when(pl.col("violation reason").str.contains("below soft minimum"))
        .then(pl.lit("Soft Min"))
        .when(pl.col("violation reason").str.contains("above soft maximum"))
        .then(pl.lit("Soft Max"))
        .when(pl.col("violation reason").str.contains("above hard maximum"))
        .then(pl.lit("Hard Max"))
        .otherwise(pl.lit("Unknown"))
    )

    violations_df = violations_df.with_columns(
        violation_type_expr.alias("violation type")
    )

    st.dataframe(violations_df)


def _render_outlier_table(
    data: pl.DataFrame,
    outliers_data: pl.DataFrame,
    settings: OutlierSettings,
    setting_file: str,
) -> None:
    """Render outlier data table using Streamlit.

    Parameters
    ----------
    data : pl.DataFrame
        Original survey data.
    outliers_data : pl.DataFrame
        DataFrame containing outlier data.
    settings : OutlierSettings
        Outlier settings configuration.
    setting_file : str
        Path to settings file.
    """
    if outliers_data.is_empty():
        st.info("No outliers detected in the selected columns.")
        return

    all_columns = data.columns

    include_cols = _build_include_cols(
        survey_key=settings.survey_key,
        survey_id=settings.survey_id,
        survey_date=settings.survey_date,
        enumerator=settings.enumerator,
        team=settings.team,
    )

    display_options = [col for col in all_columns if col not in include_cols]

    outlier_display_cols = _render_display_columns_expander(
        setting_file,
        "outlier_display_cols",
        "outlier_display_cols",
        display_options,
        "Select additional columns to include in the outlier report.",
    )

    if outlier_display_cols:
        include_cols.extend(outlier_display_cols)

    # select columns to display from data
    display_df = data.select(include_cols)
    outliers_df = sanitize_df_for_join(display_df, outliers_data, settings.survey_key)
    display_df = display_df.join(
        outliers_df,
        on=settings.survey_key,
        how="inner",
    )

    # show only rows with outliers
    outlier_show_df = display_df.filter(pl.col("outlier reason") != "no outlier")

    st.dataframe(outlier_show_df)


def _render_outlier_column_inspection(
    data: pl.DataFrame,
    outliers_data: pl.DataFrame,
    settings: OutlierSettings,
    setting_file: str,
) -> None:
    """Inspect outlier columns in the DataFrame.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing the survey data.
    outliers_data : pl.DataFrame
        DataFrame containing outlier detection results.
    settings : OutlierSettings
        Outlier settings configuration.
    setting_file : str
        Path to settings file.
    """
    if outliers_data.is_empty():
        st.info(
            "No outlier columns selected. Please select outlier columns to inspect."
        )
        return

    all_columns = data.columns

    include_cols = _build_include_cols(
        survey_key=settings.survey_key,
        survey_id=settings.survey_id,
        survey_date=settings.survey_date,
        enumerator=settings.enumerator,
        team=settings.team,
    )

    # list of outlier columns checked
    columns_checked_list = (
        outliers_data.select("column name").unique().to_series().to_list()
    )

    ic1, _ = st.columns([0.2, 0.8])

    with ic1:
        # get saved settings
        saved_settings = load_check_settings(setting_file, TAB_NAME)
        default_selected_col = saved_settings.get("selected_col", None)
        default_selected_col_index = (
            columns_checked_list.index(default_selected_col)
            if default_selected_col and default_selected_col in columns_checked_list
            else None
        )
        selected_col = st.selectbox(
            label="Select outlier columns to inspect",
            options=columns_checked_list,
            index=default_selected_col_index,
            key="outlier_inspect_col",
            help="Select the outlier columns to inspect. "
            "You can only select one column at a time.",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_selected_col"},
        )
        save_check_settings(setting_file, TAB_NAME, {"selected_col": selected_col})

        if not selected_col:
            st.info("Select an outlier column to inspect.")
            return

        if selected_col not in data.columns:
            raise ValueError(
                f"Selected column '{selected_col}' is not present in the data. "
                "Please select a valid column."
            )
        else:
            include_cols.append(selected_col)

    # create a subset of the data
    column_data = data.select([selected_col])

    st.subheader(f"Details/Distribution for {selected_col} values")
    dc1, _, dc3 = st.columns([0.3, 0.1, 0.6])
    with dc1:
        desc_stats = _create_descriptive_stats(column_data)
        st.dataframe(desc_stats)

    with dc3:
        box_plot = _create_box_plot(
            data=column_data[selected_col].to_pandas(),
            title=selected_col,
        )
        st.plotly_chart(box_plot, width="stretch")

    with st.expander(":material/clarify: Show more columns in report", expanded=False):
        st.info(
            "Select additional columns to include in the outlier inspection report."
        )
        display_options = [
            col
            for col in all_columns
            if col not in include_cols and col != selected_col
        ]
        inspect_display_cols = st.multiselect(
            label="Select columns to display",
            options=display_options,
            default=None,
            help="Select the columns to display in the inspection table.",
            disabled=not selected_col,
        )

        if inspect_display_cols:
            include_cols.extend(inspect_display_cols)

    # select columns to display from data
    display_df = data.select(include_cols)
    outliers_df = sanitize_df_for_join(display_df, outliers_data, settings.survey_key)
    display_df = display_df.join(
        outliers_df,
        on=settings.survey_key,
        how="inner",
    )

    st.dataframe(
        display_df,
        width="stretch",
        hide_index=False,
    )


# =============================================================================
# Streamlit UI - Column Search/Configuration Widgets
# =============================================================================


def _create_search_type_info(search_type_param: str) -> None:
    """Display info based on the selected search type.

    Parameters
    ----------
    search_type_param : str
        The search type to display info for.
    """
    info_messages = {
        SearchType.EXACT.value: "Select columns that match the exact name. "
        "You may select multiple columns.",
        SearchType.STARTSWITH.value: "Select columns that start with the specified pattern. "
        "You will have to enter the pattern in the input box below.",
        SearchType.ENDSWITH.value: "Select columns that end with the specified pattern. "
        "You will have to enter the pattern in the input box below.",
        SearchType.CONTAINS.value: "Select columns that contain the specified pattern. "
        "You will have to enter the pattern in the input box below.",
        SearchType.REGEX.value: "Select columns that match the specified regex pattern. "
        "You will have to enter the pattern in the input box below.",
    }

    st.info(info_messages.get(search_type_param, "Unknown search type."))


def _render_search_type_selection(
    numeric_columns: list[str],
) -> tuple[str, str | None, list[str], bool]:
    """Render search type selection UI.

    Parameters
    ----------
    numeric_columns : list[str]
        List of numeric columns.

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

    _create_search_type_info(search_type)

    if search_type == SearchType.EXACT.value:
        outlier_cols_sel = st.multiselect(
            label="Select columns to check",
            options=numeric_columns,
            default=None,
            help="Select column or group of columns to check for outliers.",
        )
        pattern, lock_cols = None, None
        return search_type, pattern, outlier_cols_sel, lock_cols
    else:
        pattern = st.text_input(
            label="Enter pattern to match column names",
            placeholder="Enter pattern to match column names",
            help="Enter the pattern to match column names based on the "
            "selected search type.",
        )
        if pattern:
            outlier_cols_patt = expand_col_names(
                numeric_columns, pattern, search_type=search_type
            )
        else:
            outlier_cols_patt = []

        st.write(
            "**Columns Selected:** ",
            ", ".join(outlier_cols_patt) if outlier_cols_patt else "None",
        )
        return search_type, pattern, outlier_cols_patt, None


def _render_column_grouping_options(
    outlier_cols: list[str], search_type: str
) -> tuple[bool, bool]:
    """Render column grouping and locking options.

    Parameters
    ----------
    outlier_cols : list[str]
        Selected outlier columns.
    search_type : str
        Search type used.

    Returns
    -------
    tuple[bool, bool]
        Group columns flag and lock columns flag.
    """
    gc1, gc2 = st.columns([0.5, 0.5])
    with gc1:
        group_cols = st.toggle(
            label="Group columns",
            key="group_outlier_cols",
            help="Group selected columns together for outlier detection.",
            disabled=not outlier_cols or len(outlier_cols) < 2,
        )
    with gc2:
        lock_cols = st.toggle(
            label="Lock column selection",
            key="outlier_cols_lock",
            help="Lock the selected columns to prevent changes.",
            disabled=not outlier_cols
            or len(outlier_cols) < 2
            or search_type == SearchType.EXACT.value,
        )
    return group_cols, lock_cols


def _render_outlier_options() -> tuple[bool, dict | None, bool]:
    """Render outlier detection options UI.

    Returns
    -------
    tuple[bool, dict | None, bool]
        Enable outliers flag, outlier settings dict, and validation status.
    """
    with st.container(border=True):
        st.write("**Outlier Options:**")
        enable_outliers = st.toggle(
            "Enable Outlier Checks", key="enable_coutlier", value=True
        )
        if enable_outliers:
            oc1, oc2 = st.columns([0.5, 0.5])
            with oc1:
                outlier_method = st.selectbox(
                    label="Select outlier detection method",
                    options=[e.value for e in OutlierMethod],
                    index=0,
                    help="Select the method to use for outlier detection.",
                    key="outlier_method",
                )
            with oc2:
                default_multiplier = (
                    OutlierMultipliers.IQR.value
                    if outlier_method == OutlierMethod.IQR.value
                    else OutlierMultipliers.SD.value
                )
                outlier_multiplier = st.number_input(
                    label="Select multiplier for outlier detection",
                    min_value=0.1,
                    max_value=10.0,
                    value=default_multiplier,
                    step=0.1,
                    help="Select the multiplier to use for outlier detection.",
                    key="outlier_multiplier",
                )

            outlier_threshold_default = (
                OutlierThresholds.SD.value
                if outlier_method == OutlierMethod.SD.value
                else OutlierThresholds.IQR.value
            )
            outlier_threshold = st.number_input(
                label="Outlier threshold (%)",
                min_value=1,
                value=outlier_threshold_default,
                help="Set the minimum number values required to flag outliers in the column.",
                key="outlier_threshold",
            )

            outlier_settings, valid_outlier = _validate_outlier_settings(
                {
                    "outlier_method": outlier_method,
                    "outlier_multiplier": outlier_multiplier,
                    "outlier_threshold": outlier_threshold,
                }
            )
            return enable_outliers, outlier_settings, valid_outlier
        else:
            return False, None, True


def _render_constraint_options() -> tuple[dict, bool]:
    """Render constraint bounds options UI.

    Returns
    -------
    tuple[dict, bool]
        Constraint settings dict and validation status.
    """
    with st.container(border=True):
        st.write("**Constraint Options:**")

        hc1, hc2 = st.columns(2)
        with hc1:
            hard_min = st.number_input(
                label="(OPTIONAL) Hard minimum",
                help="(OPTIONAL) Hard minimum value for outlier detection.",
                value=None,
            )
        with hc2:
            hard_max = st.number_input(
                label="(OPTIONAL) Hard maximum",
                help="(OPTIONAL) Hard maximum value for outlier detection.",
                value=None,
            )

        sc1, sc2 = st.columns(2)
        with sc1:
            soft_min = st.number_input(
                label="(OPTIONAL) Soft minimum",
                help="(OPTIONAL) Soft minimum value for outlier detection.",
                value=None,
            )
        with sc2:
            soft_max = st.number_input(
                label="(OPTIONAL) Soft maximum",
                help="(OPTIONAL) Soft maximum value for outlier detection.",
                value=None,
            )

        return _validate_constraint_settings(
            {
                "hard_min": hard_min,
                "soft_min": soft_min,
                "soft_max": soft_max,
                "hard_max": hard_max,
            }
        )


# =============================================================================
# Streamlit UI - Column Configuration (CRUD)
# =============================================================================
#
# NOTE: although these functions read as "settings" (they configure outlier
# columns), they are only ever invoked from `outliers_report` via
# `_render_outlier_column_actions` -- never from `outliers_report_settings` --
# so they live here in report_ui rather than in settings_ui.


def _render_outlier_column_actions(
    project_id: str, page_name_id: str, numeric_columns: list[str]
) -> None:
    """Render the outlier column configuration UI.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    numeric_columns : list[str]
        List of numeric columns.
    """
    outlier_settings = duckdb_get_table(
        project_id,
        f"outliers_{page_name_id}",
        "logs",
    )

    os1, os2, _ = st.columns([0.4, 0.3, 0.3])
    with os1:
        st.button(
            "Add Outlier/Constraint Column",
            key="add_outlier_column",
            help="Add a new outlier column configuration.",
            width="stretch",
            type="primary",
            on_click=_add_outlier_column,
            args=(
                project_id,
                page_name_id,
                numeric_columns,
            ),
        )
    with os2:
        _delete_outlier_column(project_id, page_name_id, outlier_settings)

    if outlier_settings.is_empty():
        st.info(
            "Use the :material/add: button to add columns to check for outliers and the "
            ":material/delete: button to remove columns."
        )
    else:
        _render_outlier_settings_table(outlier_settings)


@st.dialog("Add Outlier & Constraint Column(s)", width="medium")
def _add_outlier_column(
    project_id: str, page_name_id: str, numeric_columns: list[str]
) -> None:
    """Dialog to add a new outlier column configuration.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    numeric_columns : list[str]
        List of numeric columns.
    """
    # Render search type selection
    search_type, pattern, outlier_cols, lock_cols_initial = (
        _render_search_type_selection(numeric_columns)
    )

    if outlier_cols:
        # Render grouping options
        group_cols, lock_cols = _render_column_grouping_options(
            outlier_cols, search_type
        )
        if lock_cols_initial is not None:
            lock_cols = lock_cols_initial

        # Render outlier options
        enable_outliers, outlier_settings, valid_outlier = _render_outlier_options()

        # Render constraint options
        constraint_settings, valid_constraint = _render_constraint_options()

        button_disabled = (
            not outlier_cols
            or (enable_outliers and not valid_outlier)
            or not valid_constraint
        )
        if st.button(
            "Add Outlier & Constraint Configuration",
            key="confirm_add_outlier_column",
            type="primary",
            width="stretch",
            disabled=button_disabled,
        ):
            _update_outlier_column_config(
                project_id,
                page_name_id,
                search_type,
                pattern,
                outlier_cols,
                group_cols,
                lock_cols,
                enable_outliers,
                outlier_settings,
                constraint_settings,
            )

            st.success("Outlier & Constraint configuration added successfully.")
            st.rerun()


def _validate_settings(
    settings: dict,
    model_cls: type[BaseModel],
    format_error: Callable[[ValidationError], str],
) -> tuple[BaseModel | None, bool]:
    """Validate a settings dict against a Pydantic model, showing errors via st.error.

    Shared by ``_validate_constraint_settings`` and ``_validate_outlier_settings``,
    which differ only in which model and error formatter they use.

    Parameters
    ----------
    settings : dict
        Dictionary of settings to validate.
    model_cls : type[BaseModel]
        Pydantic model class to validate against.
    format_error : Callable[[ValidationError], str]
        Function that converts a ValidationError into a user-friendly message.

    Returns
    -------
    tuple[BaseModel | None, bool]
        Validated model instance and validation status.
    """
    try:
        return model_cls(**settings), True
    except ValidationError as e:
        st.error(format_error(e))
        return None, False


def _validate_constraint_settings(
    constraint_settings: dict,
) -> tuple[ConstraintBounds | None, bool]:
    """Validate constraint settings using Pydantic model.

    Parameters
    ----------
    constraint_settings : dict[str, Any]
        Dictionary containing constraint settings.

    Returns
    -------
    tuple[ConstraintBounds | None, bool]
        Validated constraint settings and validation status.
    """
    return _validate_settings(
        constraint_settings, ConstraintBounds, _format_constraint_validation_error
    )


def _validate_outlier_settings(
    outlier_settings: dict,
) -> tuple[OutlierOptionsConfig | None, bool]:
    """Validate outlier settings using Pydantic model.

    Parameters
    ----------
    outlier_settings : dict[str, Any]
        Dictionary containing outlier settings.

    Returns
    -------
    tuple[OutlierOptionsConfig | None, bool]
        Validated outlier settings and validation status.
    """
    return _validate_settings(
        outlier_settings, OutlierOptionsConfig, _format_outlier_validation_error
    )


def _format_constraint_validation_error(e: ValidationError) -> str:
    """Convert Pydantic ValidationError to user-friendly message.

    Parameters
    ----------
    e : ValidationError
        Pydantic validation error.

    Returns
    -------
    str
        User-friendly error message.
    """
    errors = []
    for error in e.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        msg = error["msg"]

        # Customize messages based on error type
        if error["type"] == "float_not_finite":
            errors.append(
                f"• {field}: Value must be a finite number (not NaN or infinity)"
            )
        elif error["type"] == "value_error":
            errors.append(f"• {msg}")  # Your custom validation messages
        else:
            errors.append(f"• {field}: {msg}")

    return "Invalid constraint configuration:\n" + "\n".join(errors)


def _format_outlier_validation_error(e: ValidationError) -> str:
    """Convert Pydantic ValidationError to user-friendly message.

    Parameters
    ----------
    e : ValidationError
        Pydantic validation error.

    Returns
    -------
    str
        User-friendly error message.
    """
    errors = []
    for error in e.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        msg = error["msg"]

        # Customize messages based on error type
        if error["type"] == "value_error.number.not_ge":
            errors.append(
                f"• {field}: Value must be greater than or equal to the minimum allowed."
            )
        elif error["type"] == "value_error.number.not_le":
            errors.append(
                f"• {field}: Value must be less than or equal to the maximum allowed."
            )
        else:
            errors.append(f"• {field}: {msg}")

    return "Invalid outlier configuration:\n" + "\n".join(errors)


def _update_outlier_column_config(
    project_id: str,
    page_name_id: str,
    search_type: str,
    pattern: str | None,
    outlier_cols: list[str],
    group_cols: bool,
    lock_cols: bool,
    outlier_enabled: bool,
    outlier_settings: OutlierOptionsConfig | None,
    constraint_settings: ConstraintBounds | None,
) -> None:
    """Update the outlier column configuration in the database.

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
    outlier_cols : list[str]
        Selected columns.
    group_cols : bool
        Whether to group columns.
    lock_cols : bool
        Whether to lock column selection.
    outlier_enabled : bool
        Whether outlier detection is enabled.
    outlier_settings : OutlierOptionsConfig | None
        Outlier detection settings.
    constraint_settings : ConstraintBounds | None
        Constraint bounds settings.
    """
    # get existing config
    existing_config = duckdb_get_table(
        project_id,
        f"outliers_{page_name_id}",
        db_name="logs",
    )

    # Prepare new configurations
    new_config = {
        "search_type": search_type,
        "pattern": pattern,
        "column_name": [outlier_cols],
        "grouped_columns": group_cols,
        "locked": lock_cols,
        "outlier_enabled": outlier_enabled,
        "outlier_method": outlier_settings.outlier_method if outlier_settings else None,
        "outlier_multiplier": outlier_settings.outlier_multiplier
        if outlier_settings
        else None,
        "outlier_threshold": outlier_settings.outlier_threshold
        if outlier_settings
        else None,
        "hard_min": constraint_settings.hard_min if constraint_settings else None,
        "soft_min": constraint_settings.soft_min if constraint_settings else None,
        "soft_max": constraint_settings.soft_max if constraint_settings else None,
        "hard_max": constraint_settings.hard_max if constraint_settings else None,
    }

    schema = {
        "search_type": pl.Utf8,
        "pattern": pl.Utf8,
        "column_name": pl.List(pl.Utf8),
        "grouped_columns": pl.Boolean,
        "locked": pl.Boolean,
        "outlier_enabled": pl.Boolean,
        "outlier_method": pl.Utf8,
        "outlier_multiplier": pl.Float64,
        "outlier_threshold": pl.Int64,
        "hard_min": pl.Float64,
        "soft_min": pl.Float64,
        "soft_max": pl.Float64,
        "hard_max": pl.Float64,
    }

    # Append new configurations to existing polars DataFrame
    new_config_df = pl.DataFrame(new_config, schema=schema)
    if not existing_config.is_empty():
        formatted_existing_config = _ensure_column_formats(existing_config)
        updated_config = pl.concat(
            [formatted_existing_config, new_config_df], how="vertical"
        )
    else:
        updated_config = new_config_df

    # Save updated configurations back to the database
    duckdb_save_table(
        project_id,
        updated_config,
        f"outliers_{page_name_id}",
        db_name="logs",
    )


def _ensure_column_formats(
    outlier_settings: pl.DataFrame,
) -> pl.DataFrame:
    """Ensure correct data types for outlier settings DataFrame.

    Parameters
    ----------
    outlier_settings : pl.DataFrame
        Outlier settings configuration.

    Returns
    -------
    pl.DataFrame
        DataFrame with ensured data types.
    """
    return outlier_settings.with_columns(
        [
            pl.col("search_type").cast(pl.Utf8),
            pl.col("pattern").cast(pl.Utf8),
            pl.col("column_name").cast(pl.List(pl.Utf8)),
            pl.col("grouped_columns").cast(pl.Boolean),
            pl.col("locked").cast(pl.Boolean),
            pl.col("outlier_enabled").cast(pl.Boolean),
            pl.col("outlier_method").cast(pl.Utf8),
            pl.col("outlier_multiplier").cast(pl.Float64),
            pl.col("outlier_threshold").cast(pl.Int64),
            pl.col("hard_min").cast(pl.Float64),
            pl.col("soft_min").cast(pl.Float64),
            pl.col("soft_max").cast(pl.Float64),
            pl.col("hard_max").cast(pl.Float64),
        ]
    )


def _render_outlier_settings_table(outlier_settings: pl.DataFrame) -> None:
    """Render the outlier settings table in Streamlit.

    Parameters
    ----------
    outlier_settings : pl.DataFrame
        Outlier settings configuration.
    """
    with st.expander("Outlier & Constraint Column Settings", expanded=False):
        st.dataframe(
            outlier_settings,
            width="stretch",
            hide_index=True,
            column_config={
                "search_type": st.column_config.Column("Search Type"),
                "pattern": st.column_config.Column("Pattern"),
                "column_name": st.column_config.Column("Column Name(s)"),
                "grouped_columns": st.column_config.CheckboxColumn("Grouped Columns"),
                "locked": st.column_config.CheckboxColumn("Locked"),
                "outlier_enabled": st.column_config.CheckboxColumn("Outlier Enabled"),
                "outlier_method": st.column_config.Column("Outlier Method"),
                "outlier_multiplier": st.column_config.NumberColumn(
                    "Outlier Multiplier"
                ),
                "outlier_threshold": st.column_config.NumberColumn("Outlier Threshold"),
                "hard_min": st.column_config.NumberColumn("Hard Min"),
                "soft_min": st.column_config.NumberColumn("Soft Min"),
                "soft_max": st.column_config.NumberColumn("Soft Max"),
                "hard_max": st.column_config.NumberColumn("Hard Max"),
            },
        )


def _delete_outlier_column(
    project_id: str, page_name_id: str, outliers_settings: pl.DataFrame
) -> None:
    """Render delete outlier column button and handle deletion.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    outliers_settings : pl.DataFrame
        Current outlier settings.
    """
    with (
        st.popover(
            label=":material/delete: Delete outlier column",
            width="stretch",
        ),
    ):
        st.markdown("#### Remove outlier columns")

        if outliers_settings.is_empty():
            st.info("No outlier columns have been added yet. ")
        else:
            outliers_settings = outliers_settings.with_row_index().with_columns(
                (
                    pl.col("index").cast(pl.Utf8)
                    + " - "
                    + pl.col("search_type")
                    + " - "
                    + pl.col("pattern").fill_null("")
                ).alias("composite_index")
            )

            unique_index = (
                outliers_settings["composite_index"]
                .unique(maintain_order=True)
                .to_list()
            )

            selected_index = st.selectbox(
                label="Select outlier column to remove",
                options=unique_index,
                help="Select the outlier column to remove from the list.",
            )

            if st.button(
                label="Confirm deletion",
                type="primary",
                width="stretch",
                help="Click to confirm deletion of the selected outlier column.",
                key="confirm_delete_outlier_column",
                disabled=not selected_index,
            ):
                updated_settings = outliers_settings.filter(
                    pl.col("composite_index") != selected_index
                ).drop("composite_index")

                duckdb_save_table(
                    project_id,
                    updated_settings,
                    f"outliers_{page_name_id}",
                    "logs",
                )

                st.rerun()


# =============================================================================
# Main Report Function
# =============================================================================


def outliers_report(
    project_id: str,
    page_name_id: str,
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
    survey_columns: ColumnByType,
) -> None:
    """Create a comprehensive outliers report.

    Parameters
    ----------
    project_id : str
        The project identifier.
    page_name_id : str
        Page name identifier.
    data : pd.DataFrame
        DataFrame containing the survey data.
    setting_file : str
        Path to settings file.
    config : dict
        Configuration dictionary.
    """
    # get column info
    categorical_columns = survey_columns.categorical_columns
    datetime_columns = survey_columns.datetime_columns
    numeric_columns = survey_columns.numeric_columns

    st.title("Outliers and Constraints Report")

    if is_demo_project():
        demo_callout(
            "This tab checks your survey data against two types of rules:\n\n"
            "- **Constraint Violations**: Records that breach hard or soft numeric bounds "
            "you define (e.g., age below 0 or above 120).\n"
            "- **Outliers**: Records flagged by a statistical method (IQR or Standard "
            "Deviation) as unusually high or low.\n\n"
            "Start by reviewing the :material/settings: **settings** panel — your columns "
            "are pre-filled. Then use **Add Outlier/Constraint Column** to configure "
            "which columns to check."
        )

    # Load settings
    config_settings = OutlierSettings(**config)
    outliers_settings = outliers_report_settings(
        setting_file, config_settings, categorical_columns, datetime_columns
    )

    # Outlier columns configuration
    st.subheader("Outlier/Constraint Columns Configuration")

    if is_demo_project():
        demo_callout(
            "Click **Add Outlier/Constraint Column** to select which numeric columns to "
            "analyse. In the dialog that opens:\n\n"
            "1. Leave **Search type** as **exact** and select **age** and "
            "**household_count** from the column list.\n"
            "2. Under **Outlier Options**, keep the default IQR method (multiplier 1.5, "
            "threshold 20).\n"
            "3. Under **Constraint Options**, optionally enter bounds — for example, "
            "for **age** set **Hard Min = 0**, **Soft Min = 15**, **Soft Max = 60**, "
            "**Hard Max = 100**. Hard bounds flag impossible values; soft bounds flag "
            "values that are unusual but may be legitimate.\n"
            "4. Click **Add Outlier & Constraint Configuration** to save.\n\n"
            "Repeat the steps to add **land_acre** as a second column."
        )

    _render_outlier_column_actions(project_id, page_name_id, numeric_columns)

    # get outlier column config
    outliers_column_config = duckdb_get_table(
        project_id,
        f"outliers_{page_name_id}",
        "logs",
    )

    if outliers_column_config.is_empty():
        return

    # update lock columns if needed
    outliers_column_config = _update_unlocked_cols(
        outliers_column_config,
        categorical_columns,
    )

    # save updated config
    duckdb_save_table(
        project_id,
        outliers_column_config,
        f"outliers_{page_name_id}",
        db_name="logs",
    )

    # Show constraint violations
    st.write("---")
    st.title("Constraint Violations")

    if is_demo_project():
        demo_callout(
            "This section shows records that breach the **hard or soft bounds** you set "
            "when configuring columns above.\n\n"
            "- **Hard Min / Hard Max**: Absolute limits — any value outside these is an "
            "unambiguous error (e.g., age < 0 or age > 120).\n"
            "- **Soft Min / Soft Max**: Advisory range — values outside these are "
            "unexpected but may be legitimate (e.g., a very large land holding).\n\n"
            "Six metrics show how many records breach each bound type. "
            "Use **:material/clarify: Show more columns in report** to add context "
            "columns such as **enum_name** or **state** to the violations table."
        )

    # compute constraint violations
    constraint_violations = compute_constraint_violations(
        data,
        outliers_settings,
        outliers_column_config,
    )

    if constraint_violations.is_empty():
        st.info("No constraint violations detected.")

    else:
        # show constraint metrics
        _render_constraint_metrics(constraint_violations)

        # show constraint violations table
        st.subheader("Constraint Violations Details")
        _render_constraint_violations_table(
            data,
            constraint_violations,
            outliers_settings,
            setting_file,
        )

    # show outliers metrics
    st.write("---")
    st.title("Outliers")

    if is_demo_project():
        demo_callout(
            "This section flags records that fall outside the **statistical bounds** "
            "computed by the method you chose (IQR or Standard Deviation).\n\n"
            "Four metrics summarise the findings: **Columns Checked**, "
            "**Columns with Outliers**, **Total Outliers**, and "
            "**Enumerators with Outliers**.\n\n"
            "Under **Inspect Columns**, select a column from the dropdown to see "
            "its descriptive statistics and a **box plot** showing where flagged values "
            "sit relative to the distribution. Expand "
            "**:material/clarify: Show more columns in report** to add context columns "
            "to the record table below the chart."
        )

    # Compute outliers
    outlier_data = compute_outlier_output(
        data,
        outliers_settings,
        outliers_column_config,
    )

    if outlier_data.is_empty():
        st.info("No outliers detected.")

    else:
        # show outlier metrics
        _render_outlier_metrics(outlier_data, outliers_settings)

        # show outlier column inspection
        st.subheader("Inspect Columns")

        _render_outlier_column_inspection(
            data,
            outlier_data,
            outliers_settings,
            setting_file,
        )

    demo_callout(
        "**Next**: :material/arrow_upward: Scroll up and select the **GPS Checks** tab."
    )
