"""Which enumerators need attention, and why. No Streamlit.

The Enumerator page's "Needs attention" list gathers, for each enumerator,
the reasons several checks give to look at their work: this page's own
numbers (activity, interview length, missing answers, consent and
completion, form version), its Response Patterns, and the outstanding issues
other checks on the page count per enumerator (duplicates, outliers,
constraint violations, GPS outliers, backcheck mismatches).

Each reason is Flagged (worth reviewing now) or Watch (worth keeping an eye
on). The rules compare an enumerator with the rest of the team, so a project
where everyone has some outliers does not flag everyone. Rates rest on at
least `MIN_SUBMISSIONS` submissions, so one odd interview does not flag a
new enumerator.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

import polars as pl

from datasure.checks.enumerator.response_patterns.models import (
    Badge,
    ResponsePatternResults,
)

TIMES = "\N{MULTIPLICATION SIGN}"

# The summary table's submissions column, which the rates' sample sizes use.
SUBMISSIONS = "# submissions"

# An enumerator's rates count only with this many submissions.
MIN_SUBMISSIONS = 5

# Days without a submission, counted back from the latest submission in the
# data, before an enumerator is marked Watch as inactive. Counting from the
# data rather than today keeps a finished survey from marking everyone.
INACTIVE_DAYS = 3
# ... and this many times their usual gap between working days.
PACE_MULTIPLE = 3

# Interview length: the enumerator's median over the team's median.
SHORT_FLAG_RATIO = 0.6
SHORT_WATCH_RATIO = 0.75

# Missing answers: points above the team's median share, and how many times
# the team's share, both of which must hold.
MISSING_FLAG = (10.0, 2.0)
MISSING_WATCH = (5.0, 1.5)

# Consent and completion: points below the team's median rate.
RATE_FLAG_POINTS = 15.0
RATE_WATCH_POINTS = 8.0

# Issues another check counts with the relative rule: the enumerator's rate
# over the team's, and the fewest issues that can flag.
RELATIVE_FLAG_RATIO = 2.0
RELATIVE_WATCH_RATIO = 1.5
RELATIVE_MIN_ISSUES = 3


class Severity(StrEnum):
    """How urgent a reason is."""

    FLAG = "Flagged"
    WATCH = "Watch"


@dataclass(frozen=True)
class Reason:
    """One reason to look at an enumerator's work.

    Attributes
    ----------
    check : str
        What found it, such as "Interview length" or "Duplicates".
    finding : str
        What was found, in a few words with the numbers.
    severity : Severity
        Flagged or Watch.
    """

    check: str
    finding: str
    severity: Severity


@dataclass(frozen=True)
class AttentionRow:
    """An enumerator with at least one reason, for the "Needs attention" list."""

    enumerator: str
    team: str | None
    reasons: tuple[Reason, ...]

    @property
    def flags(self) -> int:
        """The Flagged reasons."""
        return sum(reason.severity is Severity.FLAG for reason in self.reasons)

    @property
    def watches(self) -> int:
        """The Watch reasons."""
        return sum(reason.severity is Severity.WATCH for reason in self.reasons)


class CountRule(StrEnum):
    """When another check's per-enumerator issues give a reason."""

    # Every outstanding issue is worth a look: a duplicate ID or a GPS point
    # far from the rest is rare and specific.
    ANY = "any"
    # Only a rate well above the team's: most enumerators have a few
    # outliers, so a count alone says little.
    RELATIVE = "relative"


@dataclass(frozen=True)
class IssueCounts:
    """Another check's outstanding issues, by enumerator.

    Attributes
    ----------
    check : str
        The check's label, such as "Duplicates".
    singular, plural : str
        What one and several issues are called, such as "record with a
        duplicate ID" and "records with a duplicate ID".
    counts : Mapping[str, int]
        Outstanding issues by enumerator; enumerators with none may be left
        out.
    rule : CountRule
        When the issues give a reason.
    denominators : Mapping[str, int] | None
        What each enumerator's rate is out of, such as the backcheck values
        compared; None uses their submissions.
    per : str
        What the rate is per, for the finding: "submission" or "value
        compared".
    """

    check: str
    singular: str
    plural: str
    counts: Mapping[str, int]
    rule: CountRule = CountRule.ANY
    denominators: Mapping[str, int] | None = None
    per: str = "submission"

    def noun(self, count: int) -> str:
        """Return the count with the issue's name, such as "3 outliers"."""
        return f"{count:,} {self.singular if count == 1 else self.plural}"


@dataclass(frozen=True)
class OtherChecks:
    """What the other checks on the page add to the list.

    Attributes
    ----------
    counts : tuple[IssueCounts, ...]
        Per-enumerator issues of each check that is set up.
    errors : tuple[tuple[str, str], ...]
        The check label and the reason, for checks whose numbers could not be
        computed, so the page can say they are left out.
    """

    counts: tuple[IssueCounts, ...] = ()
    errors: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ColumnRoles:
    """The page's columns the rules read; None when not set."""

    enumerator: str
    team: str | None = None
    survey_date: str | None = None
    duration: str | None = None
    duration_unit: str | None = None
    formversion: str | None = None


# --- Formatting -------------------------------------------------------------


def _pct(value: float) -> str:
    """Format a percentage with one decimal under 10 and none above."""
    return f"{value:.1f}%" if abs(value) < 10 else f"{value:.0f}%"


def duration_minutes(value: float, unit: str | None) -> float:
    """Convert a duration in the page's unit to minutes.

    An unknown unit, such as an older saved default, is read as seconds,
    SurveyCTO's unit for the ``duration`` field.
    """
    if unit == "minutes":
        return value
    if unit == "hours":
        return value * 60
    return value / 60


def format_minutes(minutes: float) -> str:
    """Format a duration in minutes: "45 s", "19 min" or "1 h 20 min"."""
    if minutes < 1:
        return f"{minutes * 60:.0f} s"
    if minutes < 60:
        return f"{minutes:.0f} min"
    hours, rest = divmod(round(minutes), 60)
    return f"{hours} h {rest} min" if rest else f"{hours} h"


def _format_date(day: date) -> str:
    return day.strftime("%a %d %b")


# --- Rules on the page's own numbers ----------------------------------------


def _text(series: pl.Series) -> pl.Series:
    return series.cast(pl.String)


def _day(data: pl.DataFrame, column: str) -> pl.Expr | None:
    """Return the column as a date, or None when it holds no dates."""
    dtype = data.schema[column]
    if dtype == pl.Date:
        return pl.col(column)
    if isinstance(dtype, pl.Datetime):
        return pl.col(column).dt.date()
    return None


def activity_reasons(data: pl.DataFrame, roles: ColumnRoles) -> dict[str, list[Reason]]:
    """Mark Watch the enumerators silent for much longer than they usually are.

    The silence runs from their last submission to the latest submission in
    the data, not to today. It must be `INACTIVE_DAYS` or more and
    `PACE_MULTIPLE` times their usual gap between working days (the median;
    1 day with a single working day), so someone who works once a week is
    not marked after three quiet days.
    """
    column = roles.survey_date
    if not column or column not in data.columns or data.is_empty():
        return {}
    day = _day(data, column)
    if day is None:
        return {}
    days = (
        data.select(_text(data[roles.enumerator]).alias("enumerator"), day.alias("day"))
        .drop_nulls()
        .unique()
    )
    if days.is_empty():
        return {}
    latest = days["day"].max()
    pace = (
        days.sort("enumerator", "day")
        .with_columns(
            pl.col("day").diff().dt.total_days().over("enumerator").alias("gap")
        )
        .group_by("enumerator")
        .agg(pl.col("day").max().alias("last"), pl.col("gap").median().alias("usual"))
    )
    reasons: dict[str, list[Reason]] = {}
    for name, last, usual in pace.iter_rows():
        usual = usual or 1
        gap = (latest - last).days
        if gap >= max(INACTIVE_DAYS, PACE_MULTIPLE * usual):
            habit = "daily" if usual <= 1 else f"every {usual:.0f} days"
            reasons[name] = [
                Reason(
                    "Activity",
                    f"No submissions since {_format_date(last)}, {gap} days "
                    f"before the latest submission (usually works {habit})",
                    Severity.WATCH,
                )
            ]
    return reasons


def duration_reasons(data: pl.DataFrame, roles: ColumnRoles) -> dict[str, list[Reason]]:
    """Flag enumerators whose median interview is much shorter than the team's.

    The team's median is over every submission. Long interviews are not
    marked: they are rarely a sign of made-up answers.
    """
    column = roles.duration
    if not column or column not in data.columns:
        return {}
    lengths = data.select(
        _text(data[roles.enumerator]).alias("enumerator"),
        pl.col(column).cast(pl.Float64, strict=False).alias("length"),
    ).drop_nulls()
    team = lengths["length"].median() if not lengths.is_empty() else None
    if not team or team <= 0:
        return {}
    per_enumerator = lengths.group_by("enumerator").agg(
        pl.col("length").median().alias("median"), pl.len().alias("n")
    )
    unit = roles.duration_unit
    team_text = format_minutes(duration_minutes(team, unit))
    reasons: dict[str, list[Reason]] = {}
    for name, median, n in per_enumerator.iter_rows():
        if n < MIN_SUBMISSIONS:
            continue
        ratio = median / team
        if ratio > SHORT_WATCH_RATIO:
            continue
        severity = Severity.FLAG if ratio <= SHORT_FLAG_RATIO else Severity.WATCH
        reasons[name] = [
            Reason(
                "Interview length",
                f"Median {format_minutes(duration_minutes(median, unit))} "
                f"against {team_text} for the team",
                severity,
            )
        ]
    return reasons


def _team_median(summary: pl.DataFrame, column: str) -> float | None:
    eligible = summary.filter(pl.col(SUBMISSIONS) >= MIN_SUBMISSIONS)[column]
    eligible = eligible.drop_nulls()
    return None if eligible.is_empty() else float(eligible.median())


def missing_reasons(summary: pl.DataFrame, enumerator: str) -> dict[str, list[Reason]]:
    """Flag enumerators with a much larger share of missing answers.

    Reads the summary table's "% Total Missing", so the numbers match it.
    """
    column = "% Total Missing"
    if column not in summary.columns or SUBMISSIONS not in summary.columns:
        return {}
    team = _team_median(summary, column)
    if team is None:
        return {}
    reasons: dict[str, list[Reason]] = {}
    for name, share, n in summary.select(
        _text(summary[enumerator]), column, SUBMISSIONS
    ).iter_rows():
        if share is None or n < MIN_SUBMISSIONS:
            continue
        severity = None
        for level, (points, times) in (
            (Severity.FLAG, MISSING_FLAG),
            (Severity.WATCH, MISSING_WATCH),
        ):
            if share >= team + points and share >= team * times:
                severity = level
                break
        if severity is not None:
            reasons.setdefault(name, []).append(
                Reason(
                    "Missing answers",
                    f"{_pct(share)} of answers missing against {_pct(team)} "
                    "for the team",
                    severity,
                )
            )
    return reasons


def rate_reasons(
    summary: pl.DataFrame, enumerator: str, column: str, check: str, what: str
) -> dict[str, list[Reason]]:
    """Flag enumerators whose consent or completion rate is well below the team's.

    ``column`` holds a 0 to 1 rate per enumerator, such as "% consent".
    """
    if column not in summary.columns or SUBMISSIONS not in summary.columns:
        return {}
    team = _team_median(summary, column)
    if team is None:
        return {}
    reasons: dict[str, list[Reason]] = {}
    for name, rate, n in summary.select(
        _text(summary[enumerator]), column, SUBMISSIONS
    ).iter_rows():
        if rate is None or n < MIN_SUBMISSIONS:
            continue
        gap = (team - rate) * 100
        if gap < RATE_WATCH_POINTS:
            continue
        severity = Severity.FLAG if gap >= RATE_FLAG_POINTS else Severity.WATCH
        reasons[name] = [
            Reason(
                check,
                f"{_pct(rate * 100)} {what} against {_pct(team * 100)} for the team",
                severity,
            )
        ]
    return reasons


def form_version_reasons(
    data: pl.DataFrame, roles: ColumnRoles
) -> dict[str, list[Reason]]:
    """Flag enumerators who submitted an older form after the newest came out.

    The newest version is the highest in the data; it came out on the first
    day it was used. Older versions before that day are expected.
    """
    version, day = roles.formversion, roles.survey_date
    if not version or not day or not {version, day} <= set(data.columns):
        return {}
    as_day = _day(data, day)
    if as_day is None:
        return {}
    rows = data.select(
        _text(data[roles.enumerator]).alias("enumerator"),
        pl.col(version).alias("version"),
        as_day.alias("day"),
    ).drop_nulls()
    if rows.is_empty():
        return {}
    newest = rows["version"].max()
    released = rows.filter(pl.col("version") == newest)["day"].min()
    outdated = (
        rows.filter((pl.col("day") >= released) & (pl.col("version") != newest))
        .group_by("enumerator")
        .agg(pl.len().alias("n"), pl.col("version").max().alias("latest_used"))
    )
    reasons: dict[str, list[Reason]] = {}
    for name, n, used in outdated.iter_rows():
        reasons[name] = [
            Reason(
                "Form version",
                f"{n:,} submission{'' if n == 1 else 's'} on version {used} "
                f"after {newest} came out on {_format_date(released)}",
                Severity.FLAG,
            )
        ]
    return reasons


# --- Rules on Response Patterns and other checks ----------------------------

_BADGE_SEVERITY = {Badge.HIGH: Severity.FLAG, Badge.MODERATE: Severity.WATCH}


def _digit_findings(results: ResponsePatternResults) -> Iterable[tuple]:
    digits = results.digit_preference
    for e in digits.enumerators if digits else ():
        if e.ratio is not None and e.enum_pct is not None and e.team_pct is not None:
            yield (
                e.enumerator,
                e.badge,
                "Digit preference",
                f"{_pct(e.enum_pct)} of numeric answers end in 0 or 5 against "
                f"{_pct(e.team_pct)} for the rest of the team",
            )


def _range_findings(results: ResponsePatternResults) -> Iterable[tuple]:
    ranges = results.range_compression
    for e in ranges.enumerators if ranges else ():
        if e.sd_ratio is not None:
            variables = ", ".join(e.flagged_variables[:2]) or "numeric answers"
            yield (
                e.enumerator,
                e.badge,
                "Range compression",
                f"Answers to {variables} spread {e.sd_ratio:.2f}{TIMES} as widely "
                "as the rest of the team's",
            )


def _categorical_findings(results: ResponsePatternResults) -> Iterable[tuple]:
    categorical = results.categorical
    for e in categorical.enumerators if categorical else ():
        if e.questions and e.largest_gap is not None:
            question = e.questions[0]
            yield (
                e.enumerator,
                e.badge,
                "Categorical answers",
                f"Answers to {question.variable} differ from the team's by "
                f"{e.largest_gap:.0f} points (option “{question.scoring_option}”)",
            )


def pattern_reasons(results: ResponsePatternResults | None) -> dict[str, list[Reason]]:
    """Turn Response Patterns' High and Moderate badges into reasons."""
    if results is None or results.condition is not None:
        return {}
    reasons: dict[str, list[Reason]] = {}
    for findings in (_digit_findings, _range_findings, _categorical_findings):
        for name, badge, check, finding in findings(results):
            severity = _BADGE_SEVERITY.get(badge)
            if severity is not None:
                reasons.setdefault(name, []).append(Reason(check, finding, severity))
    return reasons


def count_reasons(
    issues: IssueCounts, submissions: Mapping[str, int]
) -> dict[str, list[Reason]]:
    """Turn another check's per-enumerator issues into reasons.

    Parameters
    ----------
    issues : IssueCounts
        The check's outstanding issues by enumerator.
    submissions : Mapping[str, int]
        Submissions by enumerator, for the enumerators shown; the relative
        rule's rates are out of these unless the issues have their own
        denominators.
    """
    shown = {name: n for name, n in issues.counts.items() if name in submissions}
    if issues.rule is CountRule.ANY:
        return {
            name: [Reason(issues.check, issues.noun(count), Severity.FLAG)]
            for name, count in shown.items()
            if count > 0
        }

    reasons: dict[str, list[Reason]] = {}
    totals = issues.denominators or submissions
    total_issues = sum(shown.values())
    total_out_of = sum(totals.get(name, 0) for name in submissions)
    if total_issues == 0 or total_out_of == 0:
        return reasons
    team_rate = total_issues / total_out_of
    for name, count in shown.items():
        out_of = totals.get(name, 0)
        if count < RELATIVE_MIN_ISSUES or out_of <= 0:
            continue
        ratio = (count / out_of) / team_rate
        if ratio < RELATIVE_WATCH_RATIO:
            continue
        severity = Severity.FLAG if ratio >= RELATIVE_FLAG_RATIO else Severity.WATCH
        reasons[name] = [
            Reason(
                issues.check,
                f"{issues.noun(count)}, {ratio:.1f}{TIMES} the team's rate per "
                f"{issues.per}",
                severity,
            )
        ]
    return reasons


# --- The list ---------------------------------------------------------------


def submissions_by_enumerator(data: pl.DataFrame, enumerator: str) -> dict[str, int]:
    """Count each enumerator's submissions, by their name as text."""
    if enumerator not in data.columns:
        return {}
    counts = (
        data.select(_text(data[enumerator]).alias("enumerator"))
        .drop_nulls()
        .group_by("enumerator")
        .len()
    )
    return dict(counts.iter_rows())


def teams_by_enumerator(data: pl.DataFrame, roles: ColumnRoles) -> dict[str, str]:
    """Return each enumerator's team, the one they submitted most under."""
    team = roles.team
    if not team or team not in data.columns:
        return {}
    pairs = (
        data.select(
            _text(data[roles.enumerator]).alias("enumerator"),
            _text(data[team]).alias("team"),
        )
        .drop_nulls()
        .group_by("enumerator", "team")
        .len()
        .sort("len", descending=True)
        .unique(subset="enumerator", keep="first")
    )
    return {name: team for name, team, _ in pairs.iter_rows()}


def attention_rows(
    data: pl.DataFrame,
    roles: ColumnRoles,
    summary: pl.DataFrame,
    patterns: ResponsePatternResults | None = None,
    other: Iterable[IssueCounts] = (),
) -> list[AttentionRow]:
    """Return the enumerators with a reason to look at, most urgent first.

    Ordered by Flagged reasons, then Watch reasons, then name.

    Parameters
    ----------
    data : pl.DataFrame
        The report's survey data, already narrowed to the team in view.
    roles : ColumnRoles
        The page's columns.
    summary : pl.DataFrame
        ``compute_enumerator_summary`` on ``data``.
    patterns : ResponsePatternResults | None
        Response Patterns' results on ``data``, if it ran.
    other : Iterable[IssueCounts]
        Other checks' outstanding issues by enumerator.
    """
    submissions = submissions_by_enumerator(data, roles.enumerator)
    sources: list[dict[str, list[Reason]]] = [
        activity_reasons(data, roles),
        duration_reasons(data, roles),
        missing_reasons(summary, roles.enumerator),
        rate_reasons(summary, roles.enumerator, "% consent", "Consent", "consent"),
        rate_reasons(
            summary,
            roles.enumerator,
            "% completed survey",
            "Completion",
            "completed",
        ),
        form_version_reasons(data, roles),
        pattern_reasons(patterns),
        *(count_reasons(issues, submissions) for issues in other),
    ]
    merged: dict[str, list[Reason]] = {}
    for source in sources:
        for name, reasons in source.items():
            if name in submissions:
                merged.setdefault(name, []).extend(reasons)
    teams = teams_by_enumerator(data, roles)
    rows = [
        AttentionRow(
            name,
            teams.get(name),
            tuple(sorted(reasons, key=lambda r: r.severity is not Severity.FLAG)),
        )
        for name, reasons in merged.items()
    ]
    return sorted(rows, key=lambda row: (-row.flags, -row.watches, row.enumerator))


def flag_counts(rows: Sequence[AttentionRow]) -> dict[str, str]:
    """Return each listed enumerator's flags as text, such as "3 flags" or "Watch"."""
    labels = {}
    for row in rows:
        if row.flags:
            labels[row.enumerator] = f"{row.flags} flag{'' if row.flags == 1 else 's'}"
        else:
            labels[row.enumerator] = "Watch"
    return labels
