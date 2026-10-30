"""Report UI for the enumerator report's Response Patterns section.

Renders the results model from ``compute_response_patterns``; no scoring
happens here.
"""

import plotly.graph_objects as go
import polars as pl
import streamlit as st

from datasure.checks.enumerator.compute import COMPLETED_FLAG, CONSENT_FLAG
from datasure.checks.enumerator.models import EnumeratorSettings
from datasure.checks.enumerator.response_patterns.compute import (
    ROUND_DIGITS,
    compute_response_patterns,
)
from datasure.checks.enumerator.response_patterns.models import (
    MODERATE_MARGIN,
    Badge,
    CheckCondition,
    DigitPreferenceEnumerator,
    DigitPreferenceResult,
    PageCondition,
    ResponsePatternResults,
    SampleBand,
)
from datasure.checks.enumerator.response_patterns.settings_ui import (
    mark_settings_changed,
    response_pattern_settings,
    save_response_pattern_settings,
)
from datasure.utils.ui_utils import metric_row, section_header

DP_THRESHOLD_KEY = "rp_dp_threshold"
DP_ENUMERATOR_KEY = "rp_dp_enumerator"

BADGE_COLORS: dict[Badge, str] = {
    Badge.NA: "gray",
    Badge.LOW: "green",
    Badge.MODERATE: "orange",
    Badge.HIGH: "red",
}
_ENUM_COLOR = "#1f4e79"
_TEAM_COLOR = "#b8bec9"
_FLAG_COLOR = "#d62728"

INFO_ICON = ":material/info:"
LOW_SAMPLE_WARNING = "Low sample size — treat results with caution."

# Enumerators shown before the list scrolls
_LIST_ROWS = 10


# =============================================================================
# Shared pieces
# =============================================================================


def _badge(badge: Badge, score: float | None) -> str:
    """Return the Markdown badge for a score."""
    label = badge.value if score is None else f"{badge.value} {score:.0f}"
    return f":{BADGE_COLORS[badge]}-badge[{label}]"


def _render_page_condition(condition: PageCondition) -> None:
    """Show why no check in the section can run."""
    if condition == PageCondition.NO_VARIABLES_SELECTED:
        st.info(
            "Select one or more variables in the response pattern settings "
            "above to run these checks.",
            icon=INFO_ICON,
        )
    elif condition == PageCondition.SINGLE_ENUMERATOR:
        st.info(
            "Response patterns compare each enumerator with the rest of the "
            "team, so they need at least 2 enumerators.",
            icon=INFO_ICON,
        )


def _render_skipped(skipped: dict[str, str]) -> None:
    """Note each variable a check left out, and why."""
    for variable, reason in skipped.items():
        st.caption(f":material/info: Skipped **{variable}**: {reason}.")


def _render_enumerator_list(
    enumerators: list[DigitPreferenceEnumerator], key: str
) -> str:
    """Render the enumerator list and return the selected enumerator.

    The list is sorted highest score first, so the default selection is
    the enumerator most in need of attention.
    """
    labels = {
        e.enumerator: (
            f"**{e.enumerator}** · {e.interviews:,} interviews "
            f"{_badge(e.badge, e.score)}"
        )
        for e in enumerators
    }
    height = 420 if len(enumerators) > _LIST_ROWS else "content"
    with st.container(height=height, border=True):
        return st.radio(
            "Enumerator",
            options=list(labels),
            format_func=labels.get,
            key=key,
            label_visibility="collapsed",
        )


# =============================================================================
# Digit Preference
# =============================================================================


def _threshold_description(threshold: int) -> str:
    """Explain what flagging at ``threshold`` means, in plain terms."""
    ratio = f"{1 + threshold / 100:.2f}".rstrip("0").rstrip(".")
    return (
        f"Flags an enumerator when their answers end in 0 or 5 at least "
        f"{ratio} times as often as the rest of the team's ({threshold}% more "
        f"often). A score of 100 means twice as often."
    )


def _digit_chart(e: DigitPreferenceEnumerator, flagged: bool) -> go.Figure:
    """Return the 0-9 terminal digit chart, enumerator against the team."""
    digits = [str(d) for d in range(10)]
    enum_colors = [
        _FLAG_COLOR
        if flagged and d in ROUND_DIGITS and e.enum_digit_pct[d] > e.team_digit_pct[d]
        else _ENUM_COLOR
        for d in range(10)
    ]
    fig = go.Figure(
        [
            go.Bar(
                x=digits,
                y=e.enum_digit_pct,
                name=e.enumerator,
                marker_color=enum_colors,
                hovertemplate="Digit %{x}: %{y:.1f}%<extra></extra>",
            ),
            go.Bar(
                x=digits,
                y=e.team_digit_pct,
                name="Rest of team",
                marker_color=_TEAM_COLOR,
                hovertemplate="Digit %{x}: %{y:.1f}%<extra></extra>",
            ),
        ]
    )
    fig.update_layout(
        barmode="group",
        xaxis_title="Terminal digit",
        yaxis_title="Share of responses (%)",
        legend={"orientation": "h", "y": 1.12},
        margin={"t": 30, "b": 40, "l": 40, "r": 10},
        height=340,
    )
    return fig


def _render_digit_detail(e: DigitPreferenceEnumerator, min_sample: int) -> None:
    """Render one enumerator's Digit Preference detail panel."""
    if e.sample_band == SampleBand.INSUFFICIENT:
        st.info(
            f"Not enough responses to run this check for {e.enumerator}: "
            f"{e.n_responses:,} of the {min_sample:,} needed.",
            icon=INFO_ICON,
        )
        return
    if e.score is None:
        st.info(
            "The rest of the team has no responses to compare with.",
            icon=INFO_ICON,
        )
        return

    flagged = e.badge == Badge.HIGH
    st.markdown(
        f"##### {e.enumerator}: terminal digits · score **{e.score:.0f}** "
        f"{_badge(e.badge, None)}"
    )
    st.plotly_chart(_digit_chart(e, flagged), width="stretch")
    metric_row(
        [
            (f"Ending in 0 or 5: {e.enumerator}", f"{e.enum_pct:.1f}%"),
            ("Ending in 0 or 5: rest of team", f"{e.team_pct:.1f}%"),
            (
                "Responses",
                f"{e.n_responses:,}",
                "Non-missing responses pooled across the checked variables",
            ),
        ]
    )
    if e.sample_band == SampleBand.LOW:
        st.warning(LOW_SAMPLE_WARNING, icon=":material/warning:")
    if flagged:
        st.warning(
            f"{e.enumerator}'s responses end in 0 or 5 notably more often than "
            "the rest of the team's. Consider reviewing their interviews.",
            icon=":material/flag:",
        )
    else:
        st.success(
            f"{e.enumerator}'s digit distribution is consistent with the rest "
            "of the team.",
            icon=":material/check_circle:",
        )


def _render_digit_threshold(default: int) -> None:
    """Render the Digit Preference flag-threshold slider and its description."""
    threshold = st.slider(
        "Flag threshold",
        min_value=10,
        max_value=90,
        value=default,
        key=DP_THRESHOLD_KEY,
        help="Enumerators scoring at or above this are flagged High; within "
        f"{MODERATE_MARGIN} points below it, Moderate.",
        on_change=mark_settings_changed,
    )
    st.caption(_threshold_description(threshold))


def _render_digit_preference(result: DigitPreferenceResult, min_sample: int) -> None:
    """Render the Digit Preference sub-tab."""
    st.markdown(
        "Are an enumerator's numeric answers ending in 0 or 5 more often than "
        "the rest of the team's? Terminal digits are pooled across the "
        "selected integer and continuous variables."
    )
    _render_digit_threshold(result.threshold)

    if result.condition == CheckCondition.NO_APPLICABLE_VARIABLES:
        st.info(
            "None of the selected variables are numeric (integer or "
            "continuous), so Digit Preference has nothing to check. Select "
            "numeric variables or change their type in the settings above.",
            icon=INFO_ICON,
        )
        return
    _render_skipped(result.skipped_variables)
    if result.condition == CheckCondition.NO_ELIGIBLE_VARIABLES:
        st.info(
            "None of the selected numeric variables can be checked for digit "
            "preference. See the notes above.",
            icon=INFO_ICON,
        )
        return
    if result.condition == CheckCondition.ALL_BELOW_MINIMUM:
        st.info(
            f"Every enumerator has fewer than {min_sample:,} responses on the "
            "selected variables, so Digit Preference can't run yet. Lower "
            "the minimum in the settings above or wait for more data.",
            icon=INFO_ICON,
        )
        return

    left, right = st.columns([1, 2], gap="medium")
    with left:
        selected = _render_enumerator_list(result.enumerators, DP_ENUMERATOR_KEY)
    with right:
        by_name = {e.enumerator: e for e in result.enumerators}
        _render_digit_detail(by_name[selected], min_sample)


# =============================================================================
# Section
# =============================================================================


def _excluded_columns(enumerator_settings: EnumeratorSettings) -> list[str]:
    """Return the configured ID, enumerator and report helper columns."""
    configured = [
        enumerator_settings.survey_key,
        enumerator_settings.survey_id,
        enumerator_settings.enumerator,
        enumerator_settings.team,
    ]
    return [c for c in configured if c] + [CONSENT_FLAG, COMPLETED_FLAG]


@st.fragment
def render_response_patterns(
    data: pl.DataFrame,
    settings_file: str,
    enumerator_settings: EnumeratorSettings,
    missing_codes: pl.DataFrame | None,
) -> None:
    """Render the Response Patterns section of the enumerator report.

    A fragment: changing its settings, thresholds or selected enumerator
    reruns only this section.

    Parameters
    ----------
    data : pl.DataFrame
        The report's survey data.
    settings_file : str
        Path to the page's settings file.
    enumerator_settings : EnumeratorSettings
        The report's settings, for the enumerator and ID columns.
    missing_codes : pl.DataFrame | None
        The project's missing codes, excluded before scoring.
    """
    st.divider()
    section_header("Response Patterns", icon=":material/troubleshoot:")
    st.caption(
        "Compare each enumerator's answers with the rest of the team to spot "
        "patterns such as rounding."
    )

    enumerator_col = enumerator_settings.enumerator
    if not enumerator_col or enumerator_col not in data.columns:
        st.info(
            "Response patterns require an enumerator column. Go to the "
            ":material/settings: settings section above to select it.",
            icon=INFO_ICON,
        )
        return

    settings = response_pattern_settings(
        settings_file, data, _excluded_columns(enumerator_settings), missing_codes
    )
    # The slider renders inside its sub-tab after scoring, so read its value
    # from this run's session state
    settings.digit_preference_threshold = st.session_state.get(
        DP_THRESHOLD_KEY, settings.digit_preference_threshold
    )
    save_response_pattern_settings(settings_file, settings)

    results: ResponsePatternResults = compute_response_patterns(
        data, settings, enumerator_col, missing_codes
    )
    if results.condition is not None:
        _render_page_condition(results.condition)
        return

    (digit_tab,) = st.tabs(["Digit Preference"])
    with digit_tab:
        _render_digit_preference(results.digit_preference, results.min_sample)
