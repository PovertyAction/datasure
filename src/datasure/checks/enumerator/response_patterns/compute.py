"""Scoring for the enumerator report's Response Patterns section.

Every check compares an enumerator with the rest of the team: all
enumerators except the one being checked. The UI only renders the results
model returned by ``compute_response_patterns``.
"""

import math
import re

import numpy as np
import polars as pl

from datasure.checks import missing
from datasure.checks.enumerator.response_patterns.models import (
    CATEGORICAL_LEVELS,
    DIGIT_PREFERENCE_LEVELS,
    NUMERIC_TYPES,
    RANGE_COMPRESSION_LEVELS,
    Badge,
    CategoricalEnumerator,
    CategoricalOption,
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
    ResponsePatternSettings,
    SampleBand,
    Sensitivity,
    SkipReason,
    VariableType,
)

# Only names of coordinate parts: a plain "gps" also names GPS-measured
# survey answers, such as plot_area_gps, which these checks should keep
_GPS_NAME_PARTS: tuple[str, ...] = (
    "latitude",
    "longitude",
    "altitude",
    "geopoint",
)
_GPS_NAME_WORDS: frozenset[str] = frozenset({"lat", "lon", "lng"})

_ENUM = "__rp_enumerator"
_VALUE = "__rp_value"
_DIGIT = "__rp_digit"
_OPTION = "__rp_option"

# Terminal digits a rounding enumerator favors
ROUND_DIGITS: tuple[int, ...] = (0, 5)
MIN_DIGIT_RANGE: int = 10

# Range Compression: each side's values are capped at its own 5th and 95th
# percentiles before taking SDs, so one extreme answer can't inflate everyone
# else's baseline SD
TRIM_QUANTILES: tuple[float, float] = (0.05, 0.95)
HISTOGRAM_BUCKETS: int = 10
# The histogram spans the rest of the team's 1st to 99th percentile
HISTOGRAM_QUANTILES: tuple[float, float] = (0.01, 0.99)

# Decimals Categorical gaps are rounded to before comparing them with a level:
# the precision the report shows them at
_GAP_DECIMALS: int = 1


def is_gps_column(name: str) -> bool:
    """Return whether a column name looks like part of a GPS reading.

    Matches names containing latitude, longitude, altitude or geopoint,
    names with a word lat, lon or lng, and SurveyCTO's ``field-Accuracy``
    geopoint part. A name that only contains "gps", such as
    ``plot_area_gps``, is a GPS-measured answer and is not matched.
    Coordinates vary with where an enumerator works, not how they ask
    questions, so they don't suit these checks.
    """
    lower = name.lower()
    if any(part in lower for part in _GPS_NAME_PARTS) or lower.endswith("-accuracy"):
        return True
    return not _GPS_NAME_WORDS.isdisjoint(re.split(r"[^a-z0-9]+", lower))


def infer_variable_types(
    data: pl.DataFrame, exclude: list[str] | None = None
) -> dict[str, VariableType]:
    """Return the inferred type of each column the checks can use.

    Numeric columns are ``integer`` when every non-null value is a whole
    number and ``continuous`` otherwise. Text and categorical columns, which
    the app classifies as categorical, are ``categorical``. Other columns,
    such as dates, and GPS-looking columns are left out.

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
        if col in exclude or is_gps_column(col):
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


def badge_band(
    ratio: float | None, sensitivity: Sensitivity, n_responses: int
) -> Badge:
    """Return the badge for ``ratio`` at ``sensitivity``.

    High when the ratio reaches the level's. Moderate when the next more
    sensitive level would flag the enumerator: the ratio reaches that level's
    and ``n_responses`` meets its minimum. The most sensitive level has no
    Moderate band.
    """
    if ratio is None:
        return Badge.NA
    levels = list(DIGIT_PREFERENCE_LEVELS)
    if ratio >= DIGIT_PREFERENCE_LEVELS[sensitivity].ratio:
        return Badge.HIGH
    position = levels.index(sensitivity)
    if position > 0:
        stricter = DIGIT_PREFERENCE_LEVELS[levels[position - 1]]
        if ratio >= stricter.ratio and n_responses >= stricter.min_responses:
            return Badge.MODERATE
    return Badge.LOW


def _sort_key(result: DigitPreferenceEnumerator) -> tuple:
    """Order highest ratio first, enumerators without one last, then by name."""
    return (result.ratio is None, -(result.ratio or 0), result.enumerator)


def categorical_badge_band(gap: float | None, sensitivity: Sensitivity) -> Badge:
    """Return the badge for a largest option gap at ``sensitivity``.

    High when the gap reaches the level's. Moderate when the next more
    sensitive level would flag the enumerator. The most sensitive level has
    no Moderate band.
    """
    if gap is None:
        return Badge.NA
    if gap >= CATEGORICAL_LEVELS[sensitivity].min_gap:
        return Badge.HIGH
    levels = list(CATEGORICAL_LEVELS)
    position = levels.index(sensitivity)
    if position > 0 and gap >= CATEGORICAL_LEVELS[levels[position - 1]].min_gap:
        return Badge.MODERATE
    return Badge.LOW


def _categorical_sort_key(result: CategoricalEnumerator) -> tuple:
    """Order largest gap first, enumerators without one last, then by name."""
    return (result.largest_gap is None, -(result.largest_gap or 0), result.enumerator)


def range_badge_band(sd_ratio: float | None, sensitivity: Sensitivity) -> Badge:
    """Return the badge for an SD ratio at ``sensitivity``.

    High when the ratio is at or below the level's. Moderate when the next
    more sensitive level would flag the enumerator. The most sensitive level
    has no Moderate band.
    """
    if sd_ratio is None:
        return Badge.NA
    if sd_ratio <= RANGE_COMPRESSION_LEVELS[sensitivity].max_sd_ratio:
        return Badge.HIGH
    levels = list(RANGE_COMPRESSION_LEVELS)
    position = levels.index(sensitivity)
    if position > 0:
        stricter = RANGE_COMPRESSION_LEVELS[levels[position - 1]]
        if sd_ratio <= stricter.max_sd_ratio:
            return Badge.MODERATE
    return Badge.LOW


def _range_sort_key(result: RangeCompressionEnumerator) -> tuple:
    """Order lowest SD ratio first, enumerators without one last, then by name."""
    return (result.sd_ratio is None, result.sd_ratio or 0, result.enumerator)


def _pct(counts: list[int]) -> list[float]:
    """Return each count as a percentage of their total."""
    total = sum(counts)
    return [c / total * 100 if total else 0.0 for c in counts]


def _round_pct(counts: list[int]) -> float:
    """Return the percentage of responses ending in 0 or 5."""
    total = sum(counts)
    return sum(counts[d] for d in ROUND_DIGITS) / total * 100 if total else 0.0


def _variation_skip(values: pl.Series) -> SkipReason | None:
    """Return why a variable cannot be used in any check, if it can't."""
    values = values.drop_nulls()
    if values.is_empty():
        return SkipReason.NO_RESPONSES
    if values.n_unique() == 1:
        return SkipReason.NO_VARIATION
    return None


def _digit_skip(values: pl.Series) -> SkipReason | None:
    """Return why a numeric variable cannot be checked for digit preference."""
    values = values.cast(pl.Float64).drop_nans()
    reason = _variation_skip(values)
    if reason is None and values.max() - values.min() < MIN_DIGIT_RANGE:
        return SkipReason.RANGE_UNDER_10
    return reason


def _as_numbers(
    data: pl.DataFrame, variables: list[str]
) -> tuple[pl.DataFrame, dict[str, SkipReason]]:
    """Convert text columns the user typed as numeric to numbers.

    Values that are not numbers become missing. A column with answers but no
    number among them is returned as skipped.
    """
    text = [v for v in variables if not data.schema[v].is_numeric()]
    converted = data.with_columns(
        pl.col(v).cast(pl.String).str.strip_chars().cast(pl.Float64, strict=False)
        for v in text
    )
    skipped = {
        v: SkipReason.NOT_NUMERIC
        for v in text
        if data[v].drop_nulls().len() and converted[v].drop_nulls().is_empty()
    }
    return converted, skipped


def _digit_counts(data: pl.DataFrame, variables: list[str]) -> dict[str, list[int]]:
    """Return each enumerator's count of responses ending in each digit 0-9.

    Terminal digits are pooled across ``variables`` and taken from the
    integer part of each value: ``floor(abs(x)) % 10``.
    """
    long = (
        data.select(_ENUM, *(pl.col(v).cast(pl.Float64) for v in variables))
        .unpivot(index=_ENUM, on=variables, value_name=_VALUE)
        .drop_nulls(_VALUE)
        .filter(pl.col(_VALUE).is_finite())
        .with_columns((pl.col(_VALUE).abs().floor() % 10).cast(pl.Int8).alias(_DIGIT))
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
    """Rate each enumerator's preference for answers ending in 0 or 5."""
    sensitivity = settings.digit_preference_sensitivity
    min_responses = max(
        settings.min_sample, DIGIT_PREFERENCE_LEVELS[sensitivity].min_responses
    )
    base = {"sensitivity": sensitivity, "min_responses": min_responses}
    data, skipped = _as_numbers(data, variables)
    numeric = [v for v in variables if v not in skipped]
    if not variables:
        return DigitPreferenceResult(
            **base, condition=CheckCondition.NO_APPLICABLE_VARIABLES
        )

    reasons = {var: _digit_skip(data[var]) for var in numeric}
    eligible = [var for var, reason in reasons.items() if reason is None]
    skipped |= {var: reason for var, reason in reasons.items() if reason is not None}
    if not eligible:
        return DigitPreferenceResult(
            **base,
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
        band = sample_band(n, min_responses, settings.warn_sample)
        enum_pct, team_pct = _round_pct(enum_counts), _round_pct(team_counts)
        # Rounded as shown, so a ratio shown as 1.5x is flagged at 1.5x
        ratio = (
            round(enum_pct / team_pct, 2)
            if band != SampleBand.INSUFFICIENT and team_pct > 0
            else None
        )
        enumerators.append(
            DigitPreferenceEnumerator(
                enumerator=enum,
                interviews=n_interviews,
                n_responses=n,
                sample_band=band,
                ratio=ratio,
                badge=badge_band(ratio, sensitivity, n),
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
        **base,
        condition=CheckCondition.ALL_BELOW_MINIMUM if all_insufficient else None,
        variables=eligible,
        skipped_variables=skipped,
        enumerators=sorted(enumerators, key=_sort_key),
    )


def _bucket_shares(
    values: pl.Series, low: float, width: float, n_buckets: int
) -> list[float]:
    """Return the percentage of ``values`` in each histogram bucket.

    Buckets include their lower edge and exclude their upper one. Values
    beyond either end count in the end bucket, so shares sum to 100.
    """
    buckets = ((values - low) / width).floor().clip(0, n_buckets - 1)
    counts = np.bincount(buckets.cast(pl.Int64).to_numpy(), minlength=n_buckets)
    return _pct(counts.tolist())


def _is_whole(values: pl.Series) -> bool:
    """Return whether every value is a whole number."""
    return bool((values == values.floor()).all())


def _histogram(
    enum_values: pl.Series, team_values: pl.Series
) -> tuple[list[float], list[float], list[float], bool]:
    """Return shared bucket edges, each series' share per bucket, and wholeness.

    The buckets span the rest of the team's 1st to 99th percentile, or its
    full range when those are equal. When every value is a whole number,
    the edges are whole numbers too, so each bucket holds a whole run of
    values ("10 to 19"); a narrow range then gets fewer than
    ``HISTOGRAM_BUCKETS`` buckets, one value each. Otherwise there are
    ``HISTOGRAM_BUCKETS`` equal-width buckets.
    """
    low, high = (team_values.quantile(q, "linear") for q in HISTOGRAM_QUANTILES)
    if high <= low:
        low, high = team_values.min(), team_values.max()
    whole = _is_whole(enum_values) and _is_whole(team_values)
    if whole:
        low, high = math.floor(low), math.ceil(high)
        n_values = high - low + 1
        width = math.ceil(n_values / HISTOGRAM_BUCKETS)
        n_buckets = math.ceil(n_values / width)
    else:
        width = (high - low) / HISTOGRAM_BUCKETS
        n_buckets = HISTOGRAM_BUCKETS
    edges = [low + i * width for i in range(n_buckets + 1)]
    return (
        edges,
        _bucket_shares(enum_values, low, width, n_buckets),
        _bucket_shares(team_values, low, width, n_buckets),
        whole,
    )


def _trimmed(values: pl.Series) -> pl.Series:
    """Return ``values`` capped at their own 5th and 95th percentiles.

    Capping each side at its own percentiles, rather than the team's, keeps
    the spread of an enumerator whose answers all sit beyond the team's.
    """
    low, high = (values.quantile(q, "linear") for q in TRIM_QUANTILES)
    return values.clip(low, high)


def _range_variable(
    variable: str,
    enum_values: pl.Series,
    team_values: pl.Series,
    settings: ResponsePatternSettings,
) -> RangeVariable | SkipReason:
    """Compare one enumerator's spread on one variable, or return why not."""
    n = enum_values.len()
    band = sample_band(n, settings.min_sample, settings.warn_sample)
    # An SD needs at least two responses, whatever the minimum
    if band == SampleBand.INSUFFICIENT or n < 2:
        return SkipReason.BELOW_MINIMUM
    team_trimmed = _trimmed(team_values) if team_values.len() > 1 else None
    team_sd = team_trimmed.std() if team_trimmed is not None else None
    if not team_sd:
        return SkipReason.TEAM_NO_VARIATION

    enum_trimmed = _trimmed(enum_values)
    enum_mean, team_mean = enum_trimmed.mean(), team_trimmed.mean()
    enum_sd = enum_trimmed.std()
    edges, enum_pct, team_pct, whole = _histogram(enum_values, team_values)
    return RangeVariable(
        variable=variable,
        n_responses=n,
        sample_band=band,
        enum_mean=enum_mean,
        team_mean=team_mean,
        enum_sd=enum_sd,
        team_sd=team_sd,
        # Rounded as shown, so a ratio shown as 0.50 is flagged at 0.5
        sd_ratio=round(enum_sd / team_sd, 2),
        bucket_edges=edges,
        whole_numbers=whole,
        enum_bucket_pct=enum_pct,
        team_bucket_pct=team_pct,
    )


def _best_band(bands: list[SampleBand]) -> SampleBand:
    """Return the band of the largest sample among ``bands``."""
    for band in (SampleBand.OK, SampleBand.LOW):
        if band in bands:
            return band
    return SampleBand.INSUFFICIENT


def _range_enumerator(
    enum: str,
    n_interviews: int,
    values: dict[str, pl.DataFrame],
    settings: ResponsePatternSettings,
) -> RangeCompressionEnumerator:
    """Compare one enumerator's spread on every eligible variable.

    The enumerator's SD ratio is their lowest across variables, so one
    problem question is never averaged away.
    """
    sensitivity = settings.range_compression_sensitivity
    max_sd_ratio = RANGE_COMPRESSION_LEVELS[sensitivity].max_sd_ratio
    scored: list[RangeVariable] = []
    skipped: dict[str, SkipReason] = {}
    bands: list[SampleBand] = []
    for var, frame in values.items():
        is_enum = pl.col(_ENUM) == enum
        enum_values = frame.filter(is_enum)[_VALUE]
        bands.append(
            sample_band(enum_values.len(), settings.min_sample, settings.warn_sample)
        )
        result = _range_variable(
            var, enum_values, frame.filter(~is_enum)[_VALUE], settings
        )
        if isinstance(result, SkipReason):
            skipped[var] = result
        else:
            scored.append(result)

    scored.sort(key=lambda v: v.sd_ratio)
    top = scored[0] if scored else None
    sd_ratio = top.sd_ratio if top else None
    return RangeCompressionEnumerator(
        enumerator=enum,
        interviews=n_interviews,
        sample_band=top.sample_band if top else _best_band(bands),
        sd_ratio=sd_ratio,
        badge=range_badge_band(sd_ratio, sensitivity),
        variables=scored,
        flagged_variables=[v.variable for v in scored if v.sd_ratio <= max_sd_ratio],
        skipped_variables=skipped,
    )


def _compute_range_compression(
    data: pl.DataFrame,
    variables: list[str],
    interviews: dict[str, int],
    settings: ResponsePatternSettings,
) -> RangeCompressionResult:
    """Compare each enumerator's spread with the rest of the team's."""
    sensitivity = settings.range_compression_sensitivity
    if not variables:
        return RangeCompressionResult(
            sensitivity=sensitivity, condition=CheckCondition.NO_APPLICABLE_VARIABLES
        )

    # Text columns typed as numeric are parsed as Digit Preference does,
    # so both checks score the same variables
    data, skipped = _as_numbers(data, variables)
    values: dict[str, pl.DataFrame] = {}
    for var in (v for v in variables if v not in skipped):
        frame = (
            data.select(_ENUM, pl.col(var).cast(pl.Float64).alias(_VALUE))
            .drop_nulls(_VALUE)
            .filter(pl.col(_VALUE).is_finite())
        )
        reason = _variation_skip(frame[_VALUE])
        if reason is None:
            values[var] = frame
        else:
            skipped[var] = reason
    if not values:
        return RangeCompressionResult(
            sensitivity=sensitivity,
            condition=CheckCondition.NO_ELIGIBLE_VARIABLES,
            skipped_variables=skipped,
        )

    enumerators = [
        _range_enumerator(enum, n_interviews, values, settings)
        for enum, n_interviews in interviews.items()
    ]
    all_insufficient = all(
        e.sample_band == SampleBand.INSUFFICIENT for e in enumerators
    )
    return RangeCompressionResult(
        sensitivity=sensitivity,
        condition=CheckCondition.ALL_BELOW_MINIMUM if all_insufficient else None,
        variables=list(values),
        skipped_variables=skipped,
        enumerators=sorted(enumerators, key=_range_sort_key),
    )


def _option_counts(
    frame: pl.DataFrame,
) -> tuple[list[str], dict[str, list[int]]]:
    """Return the options and each enumerator's count of each.

    Options are every value anyone on the team chose, as text. Numeric
    options come first in the order of their values, so codes sort 1, 2, 10
    rather than 1, 10, 2 even when they are stored as text. Other options
    follow in text order.
    """
    option = pl.col(_VALUE).cast(pl.String)
    options = (
        frame.select(option.alias(_OPTION))
        .unique()
        .sort(
            pl.col(_OPTION).cast(pl.Float64, strict=False),
            pl.col(_OPTION),
            nulls_last=True,
        )[_OPTION]
        .to_list()
    )
    index = {option: i for i, option in enumerate(options)}
    long = (
        frame.select(_ENUM, pl.col(_VALUE).cast(pl.String).alias(_OPTION))
        .group_by(_ENUM, _OPTION)
        .len()
    )
    counts: dict[str, list[int]] = {}
    for enum, option, n in long.iter_rows():
        counts.setdefault(enum, [0] * len(options))[index[option]] += n
    return options, counts


def _categorical_question(
    variable: str,
    options: list[str],
    enum_counts: list[int],
    team_counts: list[int],
    settings: ResponsePatternSettings,
) -> CategoricalQuestion | SkipReason:
    """Compare one enumerator with the team on one question, or say why not.

    The options are those either side chose, so an option only one side
    chose counts as 0% on the other.
    """
    n = sum(enum_counts)
    band = sample_band(n, settings.min_sample, settings.warn_sample)
    if band == SampleBand.INSUFFICIENT:
        return SkipReason.BELOW_MINIMUM
    if not sum(team_counts):
        return SkipReason.TEAM_NO_RESPONSES

    enum_pct, team_pct = _pct(enum_counts), _pct(team_counts)
    # Rounded as shown, so a gap shown as 25.0 is flagged at 25
    gaps = [
        round(e - t, _GAP_DECIMALS) for e, t in zip(enum_pct, team_pct, strict=True)
    ]
    largest_gap = max(abs(g) for g in gaps)
    min_gap = CATEGORICAL_LEVELS[settings.categorical_sensitivity].min_gap
    top = max(range(len(options)), key=lambda i: gaps[i])
    # An over-chosen option wins a tie, as it names what the enumerator chose
    scoring = max(range(len(options)), key=lambda i: (abs(gaps[i]), gaps[i]))
    return CategoricalQuestion(
        variable=variable,
        n_responses=n,
        sample_band=band,
        largest_gap=largest_gap,
        scoring_option=options[scoring],
        flagged=largest_gap >= min_gap,
        dominant_option=options[top] if gaps[top] > 0 else None,
        options=[
            CategoricalOption(
                option=option,
                enum_pct=e,
                team_pct=t,
                gap=g,
                flagged=abs(g) >= min_gap,
            )
            for option, e, t, g in zip(options, enum_pct, team_pct, gaps, strict=True)
        ],
    )


def _categorical_enumerator(
    enum: str,
    n_interviews: int,
    counts: dict[str, tuple[list[str], dict[str, list[int]]]],
    settings: ResponsePatternSettings,
) -> CategoricalEnumerator:
    """Compare one enumerator with the team on every eligible question.

    The enumerator's largest gap is the largest on any question, so one
    badly asked question is enough to flag them.
    """
    scored: list[CategoricalQuestion] = []
    skipped: dict[str, SkipReason] = {}
    bands: list[SampleBand] = []
    for var, (options, by_enum) in counts.items():
        enum_counts = by_enum.get(enum, [0] * len(options))
        totals = [sum(c[i] for c in by_enum.values()) for i in range(len(options))]
        team_counts = [t - e for t, e in zip(totals, enum_counts, strict=True)]
        bands.append(
            sample_band(sum(enum_counts), settings.min_sample, settings.warn_sample)
        )
        result = _categorical_question(var, options, enum_counts, team_counts, settings)
        if isinstance(result, SkipReason):
            skipped[var] = result
        else:
            scored.append(result)

    scored.sort(key=lambda q: -q.largest_gap)
    top = scored[0] if scored else None
    gap = top.largest_gap if top else None
    return CategoricalEnumerator(
        enumerator=enum,
        interviews=n_interviews,
        sample_band=top.sample_band if top else _best_band(bands),
        largest_gap=gap,
        badge=categorical_badge_band(gap, settings.categorical_sensitivity),
        questions=scored,
        skipped_variables=skipped,
    )


def _compute_categorical(
    data: pl.DataFrame,
    variables: list[str],
    interviews: dict[str, int],
    settings: ResponsePatternSettings,
) -> CategoricalResult:
    """Measure how far each enumerator's answer options differ from the team's."""
    sensitivity = settings.categorical_sensitivity
    if not variables:
        return CategoricalResult(
            sensitivity=sensitivity, condition=CheckCondition.NO_APPLICABLE_VARIABLES
        )

    skipped: dict[str, SkipReason] = {}
    counts: dict[str, tuple[list[str], dict[str, list[int]]]] = {}
    for var in variables:
        frame = data.select(_ENUM, pl.col(var).alias(_VALUE)).drop_nulls(_VALUE)
        if frame.schema[_VALUE].is_float():
            # NaN marks a blank answer, not an option
            frame = frame.filter(pl.col(_VALUE).is_finite())
        reason = _variation_skip(frame[_VALUE])
        if reason is None:
            counts[var] = _option_counts(frame)
        else:
            skipped[var] = reason
    if not counts:
        return CategoricalResult(
            sensitivity=sensitivity,
            condition=CheckCondition.NO_ELIGIBLE_VARIABLES,
            skipped_variables=skipped,
        )

    enumerators = [
        _categorical_enumerator(enum, n_interviews, counts, settings)
        for enum, n_interviews in interviews.items()
    ]
    all_insufficient = all(
        e.sample_band == SampleBand.INSUFFICIENT for e in enumerators
    )
    return CategoricalResult(
        sensitivity=sensitivity,
        condition=CheckCondition.ALL_BELOW_MINIMUM if all_insufficient else None,
        variables=list(counts),
        skipped_variables=skipped,
        enumerators=sorted(enumerators, key=_categorical_sort_key),
    )


def compute_response_patterns(
    data: pl.DataFrame,
    settings: ResponsePatternSettings,
    enumerator_col: str,
    missing_codes: pl.DataFrame | None,
) -> ResponsePatternResults:
    """Run every response pattern check on every enumerator.

    Parameters
    ----------
    data : pl.DataFrame
        The survey data, one row per interview.
    settings : ResponsePatternSettings
        The selected variables, type overrides, minimums and sensitivities.
    enumerator_col : str
        The enumerator column.
    missing_codes : pl.DataFrame | None
        The project's missing codes, set to missing before scoring in both
        numeric and text columns.

    Returns
    -------
    ResponsePatternResults
        Per check and enumerator: ratio, badge, sample-size band,
        skipped variables and chart series; plus any condition that stops
        the section from running.
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
        data = missing.mask_text_missing_codes(data, variables, missing_codes)

    interviews = dict(data.group_by(_ENUM).len().sort(_ENUM).iter_rows())
    if len(interviews) < 2:
        base.condition = PageCondition.SINGLE_ENUMERATOR
        return base

    inferred = infer_variable_types(data, exclude=[_ENUM])
    types = {v: settings.type_overrides.get(v, inferred.get(v)) for v in variables}
    numeric = [v for v in variables if types[v] in NUMERIC_TYPES]
    base.digit_preference = _compute_digit_preference(
        data, numeric, interviews, settings
    )
    base.range_compression = _compute_range_compression(
        data, numeric, interviews, settings
    )
    categorical = [v for v in variables if types[v] == "categorical"]
    base.categorical = _compute_categorical(data, categorical, interviews, settings)
    return base
