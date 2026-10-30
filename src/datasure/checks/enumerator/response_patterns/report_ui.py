"""Report UI for the enumerator report's Response Patterns section.

Renders the results model from ``compute_response_patterns``; no scoring
happens here.
"""

from itertools import pairwise

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
    CategoricalEnumerator,
    CategoricalQuestion,
    CategoricalResult,
    CheckCondition,
    DigitPreferenceEnumerator,
    DigitPreferenceResult,
    PageCondition,
    RangeCompressionEnumerator,
    RangeCompressionResult,
    RangeVariable,
    ResponsePatternResults,
    SampleBand,
)
from datasure.checks.enumerator.response_patterns.settings_ui import (
    response_pattern_settings,
)
from datasure.utils.ui_utils import metric_row, section_header, styled_dataframe

DP_TABLE_KEY = "rp_dp_enumerators"
RC_TABLE_KEY = "rp_rc_enumerators"
CAT_TABLE_KEY = "rp_cat_enumerators"
# Prefix of each enumerator's Range Compression variable selector
RC_VARIABLE_KEY = "rp_rc_variable"
# Prefix of each question's Categorical Response Patterns chart
CAT_CHART_KEY = "rp_cat_chart"

BADGE_COLORS: dict[Badge, str] = {
    Badge.NA: "gray",
    Badge.LOW: "green",
    Badge.MODERATE: "orange",
    Badge.HIGH: "red",
}

# IPA brand colors: the emphasis palette (Dark Green against Dark Gray) for
# enumerator against team, Red-Orange for flagged rounding and Yellow (amber)
# for flagged compression
IPA_DARK_GREEN = "#155240"
IPA_DARK_GRAY = "#c9c9c8"
IPA_RED_ORANGE = "#f26529"
IPA_YELLOW = "#f5cb57"
_ENUM_COLOR = IPA_DARK_GREEN
_TEAM_COLOR = IPA_DARK_GRAY
_FLAG_COLOR = IPA_RED_ORANGE
_COMPRESSED_COLOR = IPA_YELLOW

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
_CAPPED_NOTE = (
    "Each side's values are capped at its own 5th and 95th percentiles "
    "first, so one extreme answer can't dominate."
)
LOW_SAMPLE_WARNING = "Low sample size — treat results with caution."

# How condition messages describe the variables each kind of check uses
_KIND_TYPES: dict[str, str] = {
    "numeric": "numeric (integer or continuous)",
    "categorical": "categorical",
}

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


def _render_enumerator_table(
    table: pd.DataFrame,
    formats: dict[str, str],
    column_help: dict[str, str],
    key: str,
) -> int:
    """Render a check's enumerator table and return the selected row.

    Rows come sorted highest score first and the first row is selected by
    default, so the detail shows the enumerator most in need of attention.
    Clearing the selection falls back to that enumerator.
    """
    styler = table.style.map(_flag_style, subset=["Flag"]).format(formats, na_rep="—")
    visible_rows = min(len(table), _TABLE_ROWS)
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
            **{
                col: st.column_config.Column(help=text)
                for col, text in column_help.items()
            },
        },
    )
    rows = event.selection.rows
    return rows[0] if rows else 0


def _render_check_conditions(
    result: DigitPreferenceResult | RangeCompressionResult | CategoricalResult,
    check: str,
    min_sample: int,
    kind: str = "numeric",
) -> bool:
    """Show why a check can't list enumerators; return True if it can't.

    ``kind`` names the variables the check uses: numeric or categorical.
    """
    if result.condition == CheckCondition.NO_APPLICABLE_VARIABLES:
        st.info(
            f"None of the selected variables are {_KIND_TYPES[kind]}, so "
            f"{check} has nothing to check. Select {kind} variables or change "
            "their type in the settings above.",
            icon=INFO_ICON,
        )
        return True
    _render_skipped(result.skipped_variables)
    if result.condition == CheckCondition.NO_ELIGIBLE_VARIABLES:
        st.info(
            f"None of the selected {kind} variables can be checked for "
            f"{check}. See the notes above.",
            icon=INFO_ICON,
        )
        return True
    if result.condition == CheckCondition.ALL_BELOW_MINIMUM:
        st.info(
            f"Every enumerator has fewer than {min_sample:,} responses on the "
            f"selected variables, so {check} can't run yet. Lower the minimum "
            "in the settings above or wait for more data.",
            icon=INFO_ICON,
        )
        return True
    return False


def _render_sensitivity(threshold: int) -> None:
    """Note the check's flag threshold and where to change it."""
    st.caption(
        f"Sensitivity: **{THRESHOLD_LEVELS[threshold]}** (flagged at a "
        f"score of {threshold} or more). Change it in the settings above."
    )


# =============================================================================
# Digit Preference
# =============================================================================


def _render_digit_table(
    enumerators: list[DigitPreferenceEnumerator], key: str
) -> DigitPreferenceEnumerator:
    """Render the enumerator table and return the selected enumerator."""
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
    row = _render_enumerator_table(
        table,
        {
            "Interviews": "{:,}",
            "Responses": "{:,}",
            "Ending in 0 or 5 (%)": "{:.1f}",
            "Rest of team (%)": "{:.1f}",
            "Score": "{:.0f}",
        },
        {
            "Responses": "Non-missing responses pooled across the checked variables",
            "Ending in 0 or 5 (%)": "Share of the enumerator's responses ending "
            "in 0 or 5",
            "Rest of team (%)": "The same share for every other enumerator",
            "Score": "0-100. 100 means answers end in 0 or 5 at least twice "
            "as often as the rest of the team's.",
        },
        key,
    )
    return enumerators[row]


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
            (
                "Ending in 0 or 5",
                f"{e.enum_pct:.1f}%",
                f"Share of {e.enumerator}'s responses ending in 0 or 5",
                f"Rest of team: {e.team_pct:.1f}%",
            ),
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
    _render_sensitivity(result.threshold)
    if _render_check_conditions(result, "Digit Preference", min_sample):
        return

    st.caption("Select an enumerator to see their terminal digits.")
    selected = _render_digit_table(result.enumerators, DP_TABLE_KEY)
    _render_digit_detail(selected, min_sample)


# =============================================================================
# Range Compression
# =============================================================================


def _num(value: float) -> str:
    """Format a mean or standard deviation for a tile."""
    return f"{value:,.2f}"


def _render_range_table(
    enumerators: list[RangeCompressionEnumerator], key: str
) -> RangeCompressionEnumerator:
    """Render the enumerator table and return the selected enumerator."""
    top = [e.variables[0] if e.variables else None for e in enumerators]
    table = pd.DataFrame(
        {
            "Enumerator": [e.enumerator for e in enumerators],
            "Interviews": [e.interviews for e in enumerators],
            "Top variable": [v.variable if v else None for v in top],
            "SD ratio": [v.sd_ratio if v else None for v in top],
            "Score": [e.score for e in enumerators],
            "Signal": [
                e.signal.value.capitalize() if e.signal else None for e in enumerators
            ],
            "Flag": [e.badge.value for e in enumerators],
        }
    )
    row = _render_enumerator_table(
        table,
        {"Interviews": "{:,}", "SD ratio": "{:.2f}", "Score": "{:.0f}"},
        {
            "Top variable": "The variable with the enumerator's highest score",
            "SD ratio": "The enumerator's standard deviation on the top "
            "variable over the rest of the team's. Under 1 means a narrower "
            "spread.",
            "Score": "0-100, the highest score across the checked variables. "
            "50 means half the team's spread or a mean about 1.5 standard "
            "deviations away.",
            "Signal": "Compression: answers spread less widely than the "
            "team's. Shift: answers sit above or below the team's.",
        },
        key,
    )
    return enumerators[row]


def _bucket_label(low: float, high: float, width: float) -> str:
    """Return a histogram bucket's range, as precise as its width needs."""
    spec = ",.0f" if width >= 1 else ",.2f"
    return f"{low:{spec}} to {high:{spec}}"


def _range_histogram(v: RangeVariable, enumerator: str, compressed: bool) -> go.Figure:
    """Return the histogram of one variable, enumerator against the team.

    Both series share the buckets; the enumerator's bars are amber when they
    are flagged for compression on this variable.
    """
    edges = v.bucket_edges
    width = edges[1] - edges[0]
    buckets = [_bucket_label(lo, hi, width) for lo, hi in pairwise(edges)]
    hover = "%{x}: %{y:.1f}%<extra></extra>"
    fig = go.Figure(
        [
            go.Bar(
                x=buckets,
                y=v.enum_bucket_pct,
                name=enumerator,
                marker_color=[_COMPRESSED_COLOR if compressed else _ENUM_COLOR]
                * len(buckets),
                hovertemplate=hover,
            ),
            go.Bar(
                x=buckets,
                y=v.team_bucket_pct,
                name="Rest of team",
                marker_color=_TEAM_COLOR,
                hovertemplate=hover,
            ),
        ]
    )
    fig.update_layout(
        barmode="group",
        xaxis_title=f"{v.variable} (the end buckets include values beyond "
        "the rest of the team's 1st and 99th percentiles)",
        yaxis_title="Share of responses (%)",
        yaxis={"range": [0, 100], "fixedrange": True, "ticksuffix": "%"},
        legend={"orientation": "h", "y": 1.12},
        margin={"t": 30, "b": 40, "l": 40, "r": 10},
        height=340,
    )
    return fig


def _variables_text(names: list[str]) -> str:
    """Return bold variable names joined for a sentence."""
    bold = [f"**{n}**" for n in names]
    return bold[0] if len(bold) == 1 else ", ".join(bold[:-1]) + " and " + bold[-1]


def _render_range_verdicts(e: RangeCompressionEnumerator) -> None:
    """Show the compression and shift verdicts, compression first."""
    if e.compression_variables:
        st.warning(
            f"{e.enumerator}'s answers on "
            f"{_variables_text(e.compression_variables)} spread much less "
            "widely than the rest of the team's. They may be anchoring on a "
            "typical value; consider reviewing their interviews.",
            icon=":material/flag:",
        )
    if e.shift_variables:
        by_variable = {v.variable: v for v in e.variables}
        above = [
            n
            for n in e.shift_variables
            if by_variable[n].enum_mean > by_variable[n].team_mean
        ]
        below = [n for n in e.shift_variables if n not in above]
        parts = [
            f"well {direction} the rest of the team's on {_variables_text(names)}"
            for direction, names in (("above", above), ("below", below))
            if names
        ]
        st.warning(
            f"{e.enumerator}'s answers sit {', and '.join(parts)}. Check "
            "whether they record answers systematically high or low.",
            icon=":material/flag:",
        )
    if not e.compression_variables and not e.shift_variables:
        st.success(
            f"{e.enumerator}'s answers are spread and centred like the rest "
            "of the team's.",
            icon=":material/check_circle:",
        )


def _render_range_detail(e: RangeCompressionEnumerator, min_sample: int) -> None:
    """Render one enumerator's Range Compression detail panel."""
    if e.sample_band == SampleBand.INSUFFICIENT:
        st.info(
            f"Not enough responses to run this check for {e.enumerator}: "
            f"every checked variable has fewer than the {min_sample:,} needed.",
            icon=INFO_ICON,
        )
        return
    if e.score is None:
        st.info(
            f"None of the checked variables could be scored for {e.enumerator}.",
            icon=INFO_ICON,
        )
        _render_skipped(e.skipped_variables)
        return

    top = e.variables[0]
    st.markdown(
        f"##### {e.enumerator}: spread and level · score **{e.score:.0f}** "
        f"{_badge(e.badge)}"
    )
    st.markdown(
        f"Score set by {top.signal.value} on **{top.variable}** (compression "
        f"{top.compression_score:.0f}, shift {top.shift_score:.0f}; the "
        "higher sets the score)."
    )
    _render_range_verdicts(e)
    variable = st.selectbox(
        "Variable",
        options=[v.variable for v in e.variables],
        key=f"{RC_VARIABLE_KEY}_{e.enumerator}",
        help="Variables are listed highest score first.",
    )
    v = next(v for v in e.variables if v.variable == variable)
    metric_row(
        [
            (
                "Mean",
                _num(v.enum_mean),
                f"{e.enumerator}'s mean on {v.variable}. {_CAPPED_NOTE}",
                f"Rest of team: {_num(v.team_mean)}",
            ),
            (
                "Standard deviation",
                _num(v.enum_sd),
                f"{e.enumerator}'s standard deviation on {v.variable}. {_CAPPED_NOTE}",
                f"Rest of team: {_num(v.team_sd)}",
            ),
            (
                "SD ratio",
                f"{v.sd_ratio:.2f}",
                "Under 1 means a narrower spread than the rest of the team's",
            ),
        ]
    )
    if v.sample_band == SampleBand.LOW:
        st.warning(LOW_SAMPLE_WARNING, icon=":material/warning:")
    st.plotly_chart(
        _range_histogram(v, e.enumerator, v.variable in e.compression_variables),
        width="stretch",
    )
    _render_skipped(e.skipped_variables)


def _render_range_compression(result: RangeCompressionResult, min_sample: int) -> None:
    """Render the Range Compression sub-tab."""
    st.markdown(
        "Are an enumerator's numeric answers spread much less widely than the "
        "rest of the team's (compression), or do they sit well above or below "
        "them (shift)? Each selected integer and continuous variable is "
        "scored separately; the enumerator's score is the highest."
    )
    _render_sensitivity(result.threshold)
    if _render_check_conditions(result, "Range Compression", min_sample):
        return

    st.caption("Select an enumerator to see their answers' spread and level.")
    selected = _render_range_table(result.enumerators, RC_TABLE_KEY)
    _render_range_detail(selected, min_sample)


# =============================================================================
# Categorical Response Patterns
# =============================================================================


def _render_categorical_table(
    enumerators: list[CategoricalEnumerator], key: str
) -> CategoricalEnumerator:
    """Render the enumerator table and return the selected enumerator."""
    top = [e.questions[0] if e.questions else None for e in enumerators]
    table = pd.DataFrame(
        {
            "Enumerator": [e.enumerator for e in enumerators],
            "Interviews": [e.interviews for e in enumerators],
            "Top question": [q.variable if q else None for q in top],
            "Most over-chosen option": [q.dominant_option if q else None for q in top],
            "Largest gap (pp)": [q.largest_gap if q else None for q in top],
            "Score": [e.score for e in enumerators],
            "Flag": [e.badge.value for e in enumerators],
        }
    )
    row = _render_enumerator_table(
        table,
        {"Interviews": "{:,}", "Largest gap (pp)": "{:.1f}", "Score": "{:.0f}"},
        {
            "Top question": "The question with the enumerator's highest score",
            "Most over-chosen option": "On the top question, the option the "
            "enumerator chose most often compared with the rest of the team",
            "Largest gap (pp)": "On the top question, the largest difference "
            "in percentage points between the enumerator's and the rest of "
            "the team's share of any option",
            "Score": "0-100, twice the largest gap on any checked question. "
            "50 means a gap of 25 percentage points.",
        },
        key,
    )
    return enumerators[row]


def _option_chart(q: CategoricalQuestion, enumerator: str) -> go.Figure:
    """Return each option's share, enumerator against the team.

    The enumerator's bars are red-orange on options whose gap reaches half
    the flag threshold.
    """
    options = [o.option for o in q.options]
    hover = "%{y}: %{x:.1f}%<extra></extra>"
    fig = go.Figure(
        [
            go.Bar(
                y=options,
                x=[o.enum_pct for o in q.options],
                orientation="h",
                name=enumerator,
                marker_color=[
                    _FLAG_COLOR if o.flagged else _ENUM_COLOR for o in q.options
                ],
                hovertemplate=hover,
            ),
            go.Bar(
                y=options,
                x=[o.team_pct for o in q.options],
                orientation="h",
                name="Rest of team",
                marker_color=_TEAM_COLOR,
                hovertemplate=hover,
            ),
        ]
    )
    fig.update_layout(
        barmode="group",
        xaxis={
            "title": "Share of responses (%)",
            "range": [0, 100],
            "fixedrange": True,
            "ticksuffix": "%",
        },
        # Category axis, so numeric codes aren't plotted as numbers; options
        # read top to bottom in value order
        yaxis={"type": "category", "autorange": "reversed"},
        legend={"orientation": "h", "y": 1.12},
        margin={"t": 30, "b": 40, "l": 40, "r": 10},
        height=120 + 40 * len(options),
    )
    return fig


def _render_question_verdict(q: CategoricalQuestion, enumerator: str) -> None:
    """Show whether one option dominates the enumerator's answers."""
    dominant = next((o for o in q.options if o.option == q.dominant_option), None)
    if q.flagged and dominant:
        st.warning(
            f"{enumerator} chose **{dominant.option}** in "
            f"{dominant.enum_pct:.1f}% of answers, against "
            f"{dominant.team_pct:.1f}% for the rest of the team. One option "
            "dominates; check how they are asking this question.",
            icon=":material/flag:",
        )
    else:
        st.success(
            f"{enumerator}'s answers to **{q.variable}** are consistent with "
            "the rest of the team's.",
            icon=":material/check_circle:",
        )


def _render_question(q: CategoricalQuestion, enumerator: str) -> None:
    """Render one question's title, verdict and option chart."""
    with st.container(border=True):
        anomaly = " :red-badge[ANOMALY]" if q.flagged else ""
        st.markdown(f"**{q.variable}**{anomaly} · score **{q.score:.0f}**")
        st.caption(
            f"{q.n_responses:,} responses · largest gap {q.largest_gap:.1f} "
            "percentage points"
        )
        if q.sample_band == SampleBand.LOW:
            st.warning(LOW_SAMPLE_WARNING, icon=":material/warning:")
        _render_question_verdict(q, enumerator)
        st.plotly_chart(
            _option_chart(q, enumerator),
            width="stretch",
            key=f"{CAT_CHART_KEY}_{q.variable}",
        )


def _render_categorical_detail(e: CategoricalEnumerator, min_sample: int) -> None:
    """Render one enumerator's Categorical Response Patterns detail panel."""
    if e.sample_band == SampleBand.INSUFFICIENT:
        st.info(
            f"Not enough responses to run this check for {e.enumerator}: "
            f"every checked question has fewer than the {min_sample:,} needed.",
            icon=INFO_ICON,
        )
        return
    if e.score is None:
        st.info(
            f"None of the checked questions could be scored for {e.enumerator}.",
            icon=INFO_ICON,
        )
        _render_skipped(e.skipped_variables)
        return

    st.markdown(
        f"##### {e.enumerator}: answer options · score **{e.score:.0f}** "
        f"{_badge(e.badge)}"
    )
    st.caption("Questions are listed highest score first.")
    for q in e.questions:
        _render_question(q, e.enumerator)
    _render_skipped(e.skipped_variables)


def _render_categorical(result: CategoricalResult, min_sample: int) -> None:
    """Render the Categorical Response Patterns sub-tab."""
    st.markdown(
        "Does one answer option dominate an enumerator's answers compared "
        "with the rest of the team's? Each selected categorical variable is "
        "scored separately; the enumerator's score is the highest."
    )
    _render_sensitivity(result.threshold)
    if _render_check_conditions(
        result, "Categorical Response Patterns", min_sample, kind="categorical"
    ):
        return

    st.caption("Select an enumerator to see their answer options.")
    selected = _render_categorical_table(result.enumerators, CAT_TABLE_KEY)
    _render_categorical_detail(selected, min_sample)


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
        "patterns such as rounding, anchoring or one answer option dominating."
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

    digit_tab, range_tab, categorical_tab = st.tabs(
        ["Digit Preference", "Range Compression", "Categorical Response Patterns"]
    )
    with digit_tab:
        _render_digit_preference(results.digit_preference, results.min_sample)
    with range_tab:
        _render_range_compression(results.range_compression, results.min_sample)
    with categorical_tab:
        _render_categorical(results.categorical, results.min_sample)
