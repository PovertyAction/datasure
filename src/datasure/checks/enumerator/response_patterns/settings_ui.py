"""Settings UI for the enumerator report's Response Patterns section."""

import logging

import polars as pl
import streamlit as st
from pydantic import ValidationError

from datasure.checks import missing
from datasure.checks.enumerator.models import TAB_NAME
from datasure.checks.enumerator.response_patterns.compute import (
    infer_variable_types,
)
from datasure.checks.enumerator.response_patterns.models import (
    MODERATE_MARGIN,
    SETTINGS_KEY,
    THRESHOLD_LEVELS,
    VARIABLE_TYPES,
    ResponsePatternSettings,
)
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

logger = logging.getLogger(__name__)

# Session state flag save_check_settings checks before writing the settings
SAVE_STATE: str = f"{TAB_NAME}_{SETTINGS_KEY}"
DP_THRESHOLD_KEY = "rp_dp_threshold"
_EDITOR_KEY = "rp_variable_editor"
_EDITOR_BASE_KEY = "rp_variable_editor_base"


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
            "Inferred type": list(inferred.values()),
            "Type": [saved.type_overrides.get(v, t) for v, t in inferred.items()],
        }
    )


def _render_variable_editor(
    settings_file: str, inferred: dict[str, str], saved: ResponsePatternSettings
) -> tuple[list[str], dict[str, str]]:
    """Render the variable editor and return the selection and type overrides.

    The editor starts from the saved settings each time it appears, such as
    on returning to the page, and keeps that starting frame while it stays
    on screen, so saving an edit does not reset it. Streamlit drops the
    editor's edits when it leaves the screen, so a kept frame would show
    stale choices on return. When the candidate variables change it starts
    again from the saved settings, dropping edits made to the old rows.
    Saved choices for variables not in the current data are kept.
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
        disabled=["Variable", "Inferred type"],
        column_config={
            "Select": st.column_config.CheckboxColumn(
                "Include", help="Check to run the response pattern checks on it"
            ),
            "Variable": st.column_config.TextColumn("Variable"),
            "Inferred type": st.column_config.TextColumn(
                "Inferred type",
                help="Integer if every value is a whole number, otherwise "
                "continuous. Text columns are categorical.",
            ),
            "Type": st.column_config.SelectboxColumn(
                "Type",
                options=VARIABLE_TYPES,
                required=True,
                help="Change the type if the inferred one is wrong. Digit "
                "Preference uses integer and continuous variables.",
            ),
        },
        on_change=mark_settings_changed,
    )

    absent = [v for v in saved.selected_variables if v not in inferred]
    selected = edited.filter(pl.col("Select"))["Variable"].to_list() + absent
    overrides = {v: t for v, t in saved.type_overrides.items() if v not in inferred} | {
        row["Variable"]: row["Type"]
        for row in edited.iter_rows(named=True)
        if row["Type"] != row["Inferred type"]
    }
    return selected, overrides


def digit_preference_description(threshold: int) -> str:
    """Explain what flagging Digit Preference at ``threshold`` means."""
    ratio = f"{1 + threshold / 100:.2f}".rstrip("0").rstrip(".")
    return (
        f"Flags an enumerator when their answers end in 0 or 5 at least "
        f"{ratio} times as often as the rest of the team's (score "
        f"{threshold} or more)."
    )


def _render_threshold_level(label: str, key: str, default: int) -> int:
    """Render a check's flag-threshold levels and return the chosen threshold."""
    return st.segmented_control(
        label,
        options=list(THRESHOLD_LEVELS),
        format_func=THRESHOLD_LEVELS.get,
        default=default,
        required=True,
        key=key,
        help="Higher sensitivity flags enumerators at a lower score. "
        f"Enumerators within {MODERATE_MARGIN} points below the threshold "
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
    if missing_codes is not None:
        data = missing.mask_missing_codes(data, data.columns, missing_codes)
    inferred = infer_variable_types(data, exclude=exclude_cols)

    with st.expander("Response pattern settings", icon=":material/tune:"):
        st.markdown(
            "Select the survey questions to check. Each check uses the "
            "selected variables of its type."
        )
        selected, overrides = _render_variable_editor(settings_file, inferred, saved)

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
                "get no result (N/A).",
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

        st.markdown("**Flag thresholds**")
        dp_threshold = _render_threshold_level(
            "Digit Preference sensitivity",
            DP_THRESHOLD_KEY,
            saved.digit_preference_threshold,
        )
        st.caption(digit_preference_description(dp_threshold))

    settings = saved.model_copy(
        update={
            "selected_variables": selected,
            "type_overrides": overrides,
            "min_sample": int(min_sample),
            "warn_sample": int(warn_sample),
            "digit_preference_threshold": dp_threshold,
        }
    )
    save_response_pattern_settings(settings_file, settings)
    return settings
