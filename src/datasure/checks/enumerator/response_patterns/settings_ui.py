"""Settings UI for the enumerator report's Response Patterns section."""

import logging

import polars as pl
import streamlit as st
from pydantic import ValidationError

from datasure.checks import missing
from datasure.checks.enumerator.models import TAB_NAME
from datasure.checks.enumerator.response_patterns.compute import infer_variable_types
from datasure.checks.enumerator.response_patterns.models import (
    CATEGORICAL_LEVELS,
    DIGIT_PREFERENCE_LEVELS,
    RANGE_COMPRESSION_LEVELS,
    SETTINGS_KEY,
    VARIABLE_TYPES,
    ResponsePatternSettings,
    Sensitivity,
)
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

logger = logging.getLogger(__name__)

# Session state flag save_check_settings checks before writing the settings
SAVE_STATE: str = f"{TAB_NAME}_{SETTINGS_KEY}"
DP_SENSITIVITY_KEY = "rp_dp_sensitivity"
RC_SENSITIVITY_KEY = "rp_rc_sensitivity"
CAT_SENSITIVITY_KEY = "rp_cat_sensitivity"
_EDITOR_KEY = "rp_variable_editor"
_EDITOR_BASE_KEY = "rp_variable_editor_base"
_INFERRED_TYPE_COL = "Inferred type"


def load_response_pattern_settings(settings_file: str) -> ResponsePatternSettings:
    """Return the saved Response Patterns settings, or the defaults.

    Settings that no longer validate fall back to the defaults rather than
    breaking the report.
    """
    saved = load_check_settings(settings_file, TAB_NAME).get(SETTINGS_KEY) or {}
    try:
        return ResponsePatternSettings(**saved)
    except ValidationError:
        logger.warning(
            "Saved response pattern settings in %s are not valid; using the defaults",
            settings_file,
            exc_info=True,
        )
        return ResponsePatternSettings()


def save_response_pattern_settings(
    settings_file: str, settings: ResponsePatternSettings
) -> None:
    """Save the settings, when a widget changed them on this run."""
    save_check_settings(
        settings_file, TAB_NAME, {SETTINGS_KEY: settings.model_dump(mode="json")}
    )


def mark_settings_changed() -> None:
    """Widget callback: save the settings at the end of this run."""
    trigger_save(SAVE_STATE)


def _editor_frame(
    inferred: dict[str, str], saved: ResponsePatternSettings
) -> pl.DataFrame:
    """Return one editor row per candidate variable, from the saved settings."""
    return pl.DataFrame(
        {
            "Select": [v in saved.selected_variables for v in inferred],
            "Variable": list(inferred),
            _INFERRED_TYPE_COL: list(inferred.values()),
            "Type": [saved.type_overrides.get(v, t) for v, t in inferred.items()],
        }
    )


def _render_variable_editor(
    settings_file: str,
    inferred: dict[str, str],
    saved: ResponsePatternSettings,
    columns: list[str],
) -> tuple[list[str], dict[str, str]]:
    """Render the variable editor and return the selection and type overrides.

    The editor starts from the saved settings each time it appears, such as
    on returning to the page, and keeps that starting frame while it stays
    on screen, so saving an edit does not reset it. Streamlit drops the
    editor's edits when it leaves the screen, so a kept frame would show
    stale choices on return. When the candidate variables change it starts
    again from the saved settings, dropping edits made to the old rows.
    Saved choices for variables not in the current data are kept; those
    for columns in the data but no longer candidates, such as a column since
    set as the survey ID, are dropped.
    """
    bases = st.session_state.setdefault(_EDITOR_BASE_KEY, {})
    base = bases.get(settings_file)
    if (
        base is None
        or _EDITOR_KEY not in st.session_state
        or base["Variable"].to_list() != list(inferred)
    ):
        base = _editor_frame(inferred, saved)
        bases[settings_file] = base
        st.session_state.pop(_EDITOR_KEY, None)

    edited = st.data_editor(
        base,
        key=_EDITOR_KEY,
        hide_index=True,
        width="stretch",
        height=min(400, 38 + 35 * max(len(inferred), 1)),
        disabled=["Variable", _INFERRED_TYPE_COL],
        column_config={
            "Select": st.column_config.CheckboxColumn(
                "Include", help="Check to run the response pattern checks on it"
            ),
            "Variable": st.column_config.TextColumn("Variable"),
            _INFERRED_TYPE_COL: st.column_config.TextColumn(
                _INFERRED_TYPE_COL,
                help="Integer if every value is a whole number, otherwise "
                "continuous. Text columns are categorical.",
            ),
            "Type": st.column_config.SelectboxColumn(
                "Type",
                options=VARIABLE_TYPES,
                required=True,
                help="Change the type if the inferred one is wrong. Digit "
                "Preference and Range Compression use integer and continuous "
                "variables; Categorical Response Patterns uses categorical "
                "ones, such as numerically coded single-choice questions.",
            ),
        },
        on_change=mark_settings_changed,
    )

    return _choices(edited, saved, columns)


def _choices(
    frame: pl.DataFrame, saved: ResponsePatternSettings, columns: list[str]
) -> tuple[list[str], dict[str, str]]:
    """Return the selection and type overrides an editor ``frame`` holds.

    Saved choices for variables not in ``columns`` are kept after the
    frame's.
    """
    absent = [v for v in saved.selected_variables if v not in columns]
    selected = frame.filter(pl.col("Select"))["Variable"].to_list() + absent
    overrides = {v: t for v, t in saved.type_overrides.items() if v not in columns} | {
        row["Variable"]: row["Type"]
        for row in frame.iter_rows(named=True)
        if row["Type"] != row[_INFERRED_TYPE_COL]
    }
    return selected, overrides


def _candidates(
    data: pl.DataFrame, exclude_cols: list[str], missing_codes: pl.DataFrame | None
) -> tuple[pl.DataFrame, dict[str, str]]:
    """Return ``data`` with missing codes masked, and its candidate variables."""
    if missing_codes is not None:
        data = missing.mask_missing_codes(data, data.columns, missing_codes)
    return data, infer_variable_types(data, exclude=exclude_cols)


def effective_response_pattern_settings(
    settings_file: str,
    data: pl.DataFrame,
    exclude_cols: list[str],
    missing_codes: pl.DataFrame | None,
) -> ResponsePatternSettings:
    """Return the settings the section would run on, without rendering it.

    The saved settings, with the saved choices for columns in ``data`` that
    are no longer candidates dropped, as the section's variable editor
    drops them (such as a column since set as the team or survey ID). Takes
    the parameters of `response_pattern_settings`, so the Needs attention
    list and the section run the checks on the same settings.
    """
    saved = load_response_pattern_settings(settings_file)
    data, inferred = _candidates(data, exclude_cols, missing_codes)
    selected, overrides = _choices(_editor_frame(inferred, saved), saved, data.columns)
    return saved.model_copy(
        update={"selected_variables": selected, "type_overrides": overrides}
    )


# The "x" in a ratio such as 1.5x
TIMES = "\N{MULTIPLICATION SIGN}"


def format_ratio(ratio: float) -> str:
    """Return ``ratio`` as a multiplier, such as 1.5x or 1.25x."""
    return f"{ratio:.2f}".rstrip("0").rstrip(".") + TIMES


def digit_preference_description(sensitivity: Sensitivity) -> str:
    """Explain what flagging Digit Preference at ``sensitivity`` means."""
    level = DIGIT_PREFERENCE_LEVELS[sensitivity]
    text = (
        f"Flags an enumerator when their answers end in 0 or 5 at least "
        f"{format_ratio(level.ratio)} as often as the rest of the team's."
    )
    if level.min_responses:
        text += (
            f" Small differences need more evidence, so each enumerator needs "
            f"at least {level.min_responses:,} responses."
        )
    return text


def format_sd_ratio(ratio: float) -> str:
    """Return an SD ratio without trailing zeros, such as 0.5 or 0.65."""
    return f"{ratio:.2f}".rstrip("0").rstrip(".")


def range_compression_description(sensitivity: Sensitivity) -> str:
    """Explain what flagging Range Compression at ``sensitivity`` means."""
    ratio = format_sd_ratio(RANGE_COMPRESSION_LEVELS[sensitivity].max_sd_ratio)
    return (
        f"Flags an enumerator when, on any checked variable, their answers "
        f"spread at most {ratio} times as widely as the rest of the team's "
        f"(SD ratio {ratio} or less)."
    )


def categorical_description(sensitivity: Sensitivity) -> str:
    """Explain what flagging Categorical Response Patterns at ``sensitivity`` means."""
    gap = f"{CATEGORICAL_LEVELS[sensitivity].min_gap:g}"
    return (
        f"Flags an enumerator when, on any checked question, their share of "
        f"one answer option differs from the rest of the team's by at least "
        f"{gap} percentage points."
    )


def _render_sensitivity(
    label: str, key: str, default: Sensitivity, levels: dict
) -> Sensitivity:
    """Render a check's sensitivity ``levels`` and return the chosen one."""
    return st.segmented_control(
        label,
        options=list(levels),
        format_func=lambda s: levels[s].label,
        default=default,
        required=True,
        key=key,
        help="Higher sensitivity flags smaller differences from the rest of "
        "the team. Enumerators who would be flagged one level more sensitive "
        "are marked Moderate.",
        on_change=mark_settings_changed,
    )


def response_pattern_settings(
    settings_file: str,
    data: pl.DataFrame,
    exclude_cols: list[str],
    missing_codes: pl.DataFrame | None,
) -> ResponsePatternSettings:
    """Render the shared settings expander and return the current settings.

    Saves the settings when a widget changed them on this run.

    Parameters
    ----------
    settings_file : str
        Path to the page's settings file.
    data : pl.DataFrame
        The survey data, used to list candidate variables and their types.
    exclude_cols : list[str]
        Columns that are never candidates, such as the ID and enumerator.
    missing_codes : pl.DataFrame | None
        The project's missing codes, masked before inferring types, as the
        checks do before scoring.

    Returns
    -------
    ResponsePatternSettings
        The saved settings with this run's edits applied.
    """
    saved = load_response_pattern_settings(settings_file)
    data, inferred = _candidates(data, exclude_cols, missing_codes)

    with st.expander("Response pattern settings", icon=":material/tune:"):
        st.markdown(
            "Select the survey questions to check. Each check uses the "
            "selected variables of its type."
        )
        selected, overrides = _render_variable_editor(
            settings_file, inferred, saved, data.columns
        )

        st.markdown("**Minimum responses**")
        c1, c2, _ = st.columns(3)
        with c1:
            min_sample = st.number_input(
                "Hide results below",
                min_value=1,
                step=1,
                value=saved.min_sample,
                key="rp_min_sample",
                help="Enumerators with fewer non-missing responses than this "
                "get no result (N/A). Digit Preference's High sensitivity "
                "raises this to "
                f"{DIGIT_PREFERENCE_LEVELS[Sensitivity.HIGH].min_responses:,}.",
                on_change=mark_settings_changed,
            )
        with c2:
            warn_sample = st.number_input(
                "Warn below",
                min_value=1,
                step=1,
                value=saved.warn_sample,
                key="rp_warn_sample",
                help="Results with fewer responses than this are marked "
                "low sample size.",
                on_change=mark_settings_changed,
            )

        st.markdown("**Flag sensitivity**")
        dp_sensitivity = _render_sensitivity(
            "Digit Preference sensitivity",
            DP_SENSITIVITY_KEY,
            saved.digit_preference_sensitivity,
            DIGIT_PREFERENCE_LEVELS,
        )
        st.caption(digit_preference_description(dp_sensitivity))
        rc_sensitivity = _render_sensitivity(
            "Range Compression sensitivity",
            RC_SENSITIVITY_KEY,
            saved.range_compression_sensitivity,
            RANGE_COMPRESSION_LEVELS,
        )
        st.caption(range_compression_description(rc_sensitivity))
        cat_sensitivity = _render_sensitivity(
            "Categorical Response Patterns sensitivity",
            CAT_SENSITIVITY_KEY,
            saved.categorical_sensitivity,
            CATEGORICAL_LEVELS,
        )
        st.caption(categorical_description(cat_sensitivity))

    settings = saved.model_copy(
        update={
            "selected_variables": selected,
            "type_overrides": overrides,
            "min_sample": int(min_sample),
            "warn_sample": int(warn_sample),
            "digit_preference_sensitivity": dp_sensitivity,
            "range_compression_sensitivity": rc_sensitivity,
            "categorical_sensitivity": cat_sensitivity,
        }
    )
    save_response_pattern_settings(settings_file, settings)
    return settings
