"""Scoring for the enumerator report's Response Patterns section.

Every check compares an enumerator with the rest of the team: all
enumerators except the one being scored. The UI only renders the results
model returned by ``compute_response_patterns``.
"""

import polars as pl

from datasure.checks import missing
from datasure.checks.enumerator.response_patterns.models import (
    MODERATE_MARGIN,
    NUMERIC_TYPES,
    Badge,
    CheckCondition,
    DigitPreferenceEnumerator,
    DigitPreferenceResult,
    PageCondition,
    ResponsePatternResults,
    ResponsePatternSettings,
    SampleBand,
    SkipReason,
    VariableType,
)

_ENUM = "__rp_enumerator"
_VALUE = "__rp_value"
_DIGIT = "__rp_digit"

# Terminal digits a rounding enumerator favors
ROUND_DIGITS: tuple[int, ...] = (0, 5)
MIN_DIGIT_RANGE: int = 10


def infer_variable_types(
    data: pl.DataFrame, exclude: list[str] | None = None
) -> dict[str, VariableType]:
    """Return the inferred type of each column the checks can use.

    Numeric columns are ``integer`` when every non-null value is a whole
    number and ``continuous`` otherwise. Text and categorical columns, which
    the app classifies as categorical, are ``categorical``. Other columns,
    such as dates, are left out.

    Parameters
    ----------
    data : pl.DataFrame
        The survey data.
    exclude : list[str] | None
        Columns to leave out, such as the ID and enumerator columns.

    Returns
    -------
    dict[str, VariableType]
        Column name to inferred type, in the data's column order.
    """
    exclude = set(exclude or [])
    types: dict[str, VariableType] = {}
    for col, dtype in data.schema.items():
        if col in exclude:
            continue
        if dtype.is_integer():
            types[col] = "integer"
        elif dtype.is_float():
            values = data[col].drop_nulls().drop_nans()
            whole = (values == values.floor()).all()
            types[col] = "integer" if whole else "continuous"
        elif dtype in (pl.String, pl.Categorical) or isinstance(dtype, pl.Enum):
            types[col] = "categorical"
    return types


def sample_band(n: int, min_sample: int, warn_sample: int) -> SampleBand:
    """Return the sample-size band of ``n`` responses."""
    if n < min_sample:
        return SampleBand.INSUFFICIENT
    if n < warn_sample:
        return SampleBand.LOW
    return SampleBand.OK


def badge_band(score: float | None, threshold: int) -> Badge:
    """Return the badge for ``score`` against the flag ``threshold``."""
    if score is None:
        return Badge.NA
    if score >= threshold:
        return Badge.HIGH
    if score >= threshold - MODERATE_MARGIN:
        return Badge.MODERATE
    return Badge.LOW


def _sort_key(result: DigitPreferenceEnumerator) -> tuple:
    """Order highest score first, unscored enumerators last, then by name."""
    return (result.score is None, -(result.score or 0), result.enumerator)


def _digit_preference_score(enum_pct: float, team_pct: float) -> float:
    """Return the excess share of 0/5 endings over the team, scaled to 0-100.

    100 means the enumerator's share is at least twice the team's.
    """
    if team_pct == 0:
        return 100.0 if enum_pct > 0 else 0.0
    return min(100.0, max(0.0, (enum_pct - team_pct) / team_pct * 100))


def _pct(counts: list[int]) -> list[float]:
    """Return each count as a percentage of their total."""
    total = sum(counts)
    return [c / total * 100 if total else 0.0 for c in counts]


def _round_pct(counts: list[int]) -> float:
    """Return the percentage of responses ending in 0 or 5."""
    total = sum(counts)
    return sum(counts[d] for d in ROUND_DIGITS) / total * 100 if total else 0.0


def _numeric_skip(values: pl.Series) -> SkipReason | None:
    """Return why a numeric variable cannot be used anywhere, if it can't."""
    values = values.drop_nulls()
    if values.is_empty():
        return SkipReason.NO_RESPONSES
    if values.n_unique() == 1:
        return SkipReason.NO_VARIATION
    return None


def _digit_counts(data: pl.DataFrame, variables: list[str]) -> dict[str, list[int]]:
    """Return each enumerator's count of responses ending in each digit 0-9.

    Terminal digits are pooled across ``variables`` and taken from the
    integer part of each value: ``abs(floor(x)) % 10``.
    """
    long = (
        data.select(_ENUM, *(pl.col(v).cast(pl.Float64) for v in variables))
        .unpivot(index=_ENUM, on=variables, value_name=_VALUE)
        .drop_nulls(_VALUE)
        .filter(pl.col(_VALUE).is_finite())
        .with_columns((pl.col(_VALUE).floor().abs() % 10).cast(pl.Int8).alias(_DIGIT))
        .group_by(_ENUM, _DIGIT)
        .len()
    )
    counts: dict[str, list[int]] = {}
    for enum, digit, n in long.iter_rows():
        counts.setdefault(enum, [0] * 10)[digit] += n
    return counts


def _compute_digit_preference(
    data: pl.DataFrame,
    variables: list[str],
    interviews: dict[str, int],
    settings: ResponsePatternSettings,
) -> DigitPreferenceResult:
    """Score each enumerator's preference for answers ending in 0 or 5."""
    threshold = settings.digit_preference_threshold
    numeric = [v for v in variables if data.schema[v].is_numeric()]
    skipped = {v: SkipReason.NOT_NUMERIC for v in variables if v not in numeric}
    if not variables:
        return DigitPreferenceResult(
            threshold=threshold, condition=CheckCondition.NO_APPLICABLE_VARIABLES
        )

    eligible = []
    for var in numeric:
        values = data[var].cast(pl.Float64).drop_nans()
        reason = _numeric_skip(values)
        if reason is None and values.max() - values.min() < MIN_DIGIT_RANGE:
            reason = SkipReason.RANGE_UNDER_10
        if reason is None:
            eligible.append(var)
        else:
            skipped[var] = reason
    if not eligible:
        return DigitPreferenceResult(
            threshold=threshold,
            condition=CheckCondition.NO_ELIGIBLE_VARIABLES,
            skipped_variables=skipped,
        )

    counts = _digit_counts(data, eligible)
    totals = [sum(c[d] for c in counts.values()) for d in range(10)]
    enumerators = []
    for enum, n_interviews in interviews.items():
        enum_counts = counts.get(enum, [0] * 10)
        team_counts = [t - e for t, e in zip(totals, enum_counts, strict=True)]
        n = sum(enum_counts)
        band = sample_band(n, settings.min_sample, settings.warn_sample)
        enum_pct, team_pct = _round_pct(enum_counts), _round_pct(team_counts)
        score = (
            _digit_preference_score(enum_pct, team_pct)
            if band != SampleBand.INSUFFICIENT and sum(team_counts)
            else None
        )
        enumerators.append(
            DigitPreferenceEnumerator(
                enumerator=enum,
                interviews=n_interviews,
                n_responses=n,
                sample_band=band,
                score=score,
                badge=badge_band(score, threshold),
                enum_pct=enum_pct if n else None,
                team_pct=team_pct if sum(team_counts) else None,
                enum_digit_pct=_pct(enum_counts),
                team_digit_pct=_pct(team_counts),
            )
        )

    all_insufficient = all(
        e.sample_band == SampleBand.INSUFFICIENT for e in enumerators
    )
    return DigitPreferenceResult(
        threshold=threshold,
        condition=CheckCondition.ALL_BELOW_MINIMUM if all_insufficient else None,
        variables=eligible,
        skipped_variables=skipped,
        enumerators=sorted(enumerators, key=_sort_key),
    )


def compute_response_patterns(
    data: pl.DataFrame,
    settings: ResponsePatternSettings,
    enumerator_col: str,
    missing_codes: pl.DataFrame | None,
) -> ResponsePatternResults:
    """Score every enumerator on every response pattern check.

    Parameters
    ----------
    data : pl.DataFrame
        The survey data, one row per interview.
    settings : ResponsePatternSettings
        The selected variables, type overrides and thresholds.
    enumerator_col : str
        The enumerator column.
    missing_codes : pl.DataFrame | None
        The project's missing codes, set to missing before scoring.

    Returns
    -------
    ResponsePatternResults
        Per check and enumerator: score, badge, sample-size band, skipped
        variables and chart series; plus any condition that stops the
        section from running.
    """
    base = ResponsePatternResults(
        min_sample=settings.min_sample, warn_sample=settings.warn_sample
    )
    variables = [
        v
        for v in dict.fromkeys(settings.selected_variables)
        if v in data.columns and v != enumerator_col
    ]
    if not variables:
        base.condition = PageCondition.NO_VARIABLES_SELECTED
        return base

    data = data.select(
        pl.col(enumerator_col).cast(pl.String).alias(_ENUM), *variables
    ).drop_nulls(_ENUM)
    if missing_codes is not None:
        data = missing.mask_missing_codes(data, variables, missing_codes)

    interviews = dict(data.group_by(_ENUM).len().sort(_ENUM).iter_rows())
    if len(interviews) < 2:
        base.condition = PageCondition.SINGLE_ENUMERATOR
        return base

    inferred = infer_variable_types(data, exclude=[_ENUM])
    types = {v: settings.type_overrides.get(v, inferred.get(v)) for v in variables}
    base.digit_preference = _compute_digit_preference(
        data,
        [v for v in variables if types[v] in NUMERIC_TYPES],
        interviews,
        settings,
    )
    return base
