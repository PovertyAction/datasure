"""Report UI for the enumerator report's Response Patterns section.

Renders the results model from ``compute_response_patterns``; no scoring
happens here.
"""

import pandas as pd
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
    THRESHOLD_LEVELS,
    Badge,
    CheckCondition,
    DigitPreferenceEnumerator,
    DigitPreferenceResult,
    PageCondition,
    ResponsePatternResults,
    SampleBand,
)
from datasure.checks.enumerator.response_patterns.settings_ui import (
    response_pattern_settings,
)
from datasure.utils.ui_utils import metric_row, section_header, styled_dataframe

DP_TABLE_KEY = "rp_dp_enumerators"

BADGE_COLORS: dict[Badge, str] = {
    Badge.NA: "gray",
    Badge.LOW: "green",
    Badge.MODERATE: "orange",
    Badge.HIGH: "red",
}

# IPA brand colors: the emphasis palette (Dark Green against Dark Gray) for
# enumerator against team, Red-Orange for flagged rounding
IPA_DARK_GREEN = "#155240"
IPA_DARK_GRAY = "#c9c9c8"
IPA_RED_ORANGE = "#f26529"
_ENUM_COLOR = IPA_DARK_GREEN
_TEAM_COLOR = IPA_DARK_GRAY
_FLAG_COLOR = IPA_RED_ORANGE

# Flag cells in the enumerator table look like the st.badge pills on the
# Summary page's check health table: Streamlit's light-theme badge text
# colour on a 10% tint of the badge colour, keyed by BADGE_COLORS.
_PILL_STYLES: dict[str, tuple[str, str]] = {
    "gray": ("rgba(49, 51, 63, 0.6)", "rgba(49, 51, 63, 0.1)"),
    "green": ("#158237", "rgba(33, 195, 84, 0.1)"),
    "orange": ("#e2660c", "rgba(255, 135, 0, 0.1)"),
    "red": ("#bd4043", "rgba(255, 43, 43, 0.1)"),
}

INFO_ICON = ":material/info:"
LOW_SAMPLE_WARNING = "Low sample size — treat results with caution."

# Enumerators shown before the table scrolls
_TABLE_ROWS = 10
_ROW_HEIGHT = 35


# =============================================================================
# Shared pieces
# =============================================================================


def _badge(badge: Badge) -> str:
    """Return the Markdown badge for a score's band."""
    return f":{BADGE_COLORS[badge]}-badge[{badge.value}]"


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


def _flag_style(flag: str) -> str:
    """Return the badge-like style for a Flag value."""
    text, fill = _PILL_STYLES[BADGE_COLORS[Badge(flag)]]
    return f"color: {text}; background-color: {fill}; font-weight: 600"


# =============================================================================
# Digit Preference
# =============================================================================


def _render_digit_table(
    enumerators: list[DigitPreferenceEnumerator], key: str
) -> DigitPreferenceEnumerator:
    """Render the enumerator table and return the selected enumerator.

    Rows are sorted highest score first and the first row is selected by
    default, so the detail shows the enumerator most in need of attention.
    Clearing the selection falls back to that enumerator.
    """
    table = pd.DataFrame(
        {
            "Enumerator": [e.enumerator for e in enumerators],
            "Interviews": [e.interviews for e in enumerators],
            "Responses": [e.n_responses for e in enumerators],
            "Ending in 0 or 5 (%)": [e.enum_pct for e in enumerators],
            "Rest of team (%)": [e.team_pct for e in enumerators],
            "Score": [e.score for e in enumerators],
            "Flag": [e.badge.value for e in enumerators],
        }
    )
    styler = table.style.map(_flag_style, subset=["Flag"]).format(
        {
            "Interviews": "{:,}",
            "Responses": "{:,}",
            "Ending in 0 or 5 (%)": "{:.1f}",
            "Rest of team (%)": "{:.1f}",
            "Score": "{:.0f}",
        },
        na_rep="—",
    )
    visible_rows = min(len(enumerators), _TABLE_ROWS)
    event = styled_dataframe(
        styler,
        key=key,
        on_select="rerun",
        selection_mode="single-row",
        selection_default={"selection": {"rows": [0]}},
        hide_index=True,
        width="stretch",
        height=_ROW_HEIGHT * (visible_rows + 1) + 3,
        column_config={
            "Enumerator": st.column_config.TextColumn(pinned=True),
            "Responses": st.column_config.Column(
                help="Non-missing responses pooled across the checked variables"
            ),
            "Ending in 0 or 5 (%)": st.column_config.Column(
                help="Share of the enumerator's responses ending in 0 or 5"
            ),
            "Rest of team (%)": st.column_config.Column(
                help="The same share for every other enumerator"
            ),
            "Score": st.column_config.Column(
                help="0-100. 100 means answers end in 0 or 5 at least twice "
                "as often as the rest of the team's."
            ),
        },
    )
    rows = event.selection.rows
    return enumerators[rows[0] if rows else 0]


def _digit_chart(e: DigitPreferenceEnumerator, flagged: bool) -> go.Figure:
    """Return the 0-9 terminal digit chart, enumerator against the team."""
    digits = [str(d) for d in range(10)]
    enum_colors = [
        _FLAG_COLOR
        if flagged and d in ROUND_DIGITS and e.enum_digit_pct[d] > e.team_digit_pct[d]
        else _ENUM_COLOR
        for d in range(10)
    ]
    hover = "Digit %{x}: %{y:.1f}%<extra></extra>"
    fig = go.Figure(
        [
            go.Bar(
                x=digits,
                y=e.enum_digit_pct,
                name=e.enumerator,
                marker_color=enum_colors,
                hovertemplate=hover,
            ),
            go.Bar(
                x=digits,
                y=e.team_digit_pct,
                name="Rest of team",
                marker_color=_TEAM_COLOR,
                hovertemplate=hover,
            ),
        ]
    )
    fig.update_layout(
        barmode="group",
        xaxis_title="Terminal digit",
        yaxis_title="Share of responses (%)",
        # Always 0-100%, so charts compare at a glance across enumerators
        yaxis={"range": [0, 100], "fixedrange": True, "ticksuffix": "%"},
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
        f"{_badge(e.badge)}"
    )
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
    st.plotly_chart(_digit_chart(e, flagged), width="stretch")


def _render_digit_preference(result: DigitPreferenceResult, min_sample: int) -> None:
    """Render the Digit Preference sub-tab."""
    st.markdown(
        "Are an enumerator's numeric answers ending in 0 or 5 more often than "
        "the rest of the team's? Terminal digits are pooled across the "
        "selected integer and continuous variables."
    )
    st.caption(
        f"Sensitivity: **{THRESHOLD_LEVELS[result.threshold]}** (flagged at a "
        f"score of {result.threshold} or more). Change it in the settings above."
    )

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

    st.caption("Select an enumerator to see their terminal digits.")
    selected = _render_digit_table(result.enumerators, DP_TABLE_KEY)
    _render_digit_detail(selected, min_sample)


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

    A fragment: changing its settings or selected enumerator reruns only
    this section.

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
    results: ResponsePatternResults = compute_response_patterns(
        data, settings, enumerator_col, missing_codes
    )
    if results.condition is not None:
        _render_page_condition(results.condition)
        return

    (digit_tab,) = st.tabs(["Digit Preference"])
    with digit_tab:
        _render_digit_preference(results.digit_preference, results.min_sample)
