"""Scoring for the enumerator report's Response Patterns section.

Every check compares an enumerator with the rest of the team: all
enumerators except the one being scored. The UI only renders the results
model returned by ``compute_response_patterns``.
"""

import re

import polars as pl

from datasure.checks import missing
from datasure.checks.enumerator.response_patterns.models import (
    MODERATE_MARGIN,
    NUMERIC_TYPES,
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
    RangeSignal,
    RangeVariable,
    ResponsePatternResults,
    ResponsePatternSettings,
    SampleBand,
    SkipReason,
    VariableType,
)

_GPS_NAME_PARTS: tuple[str, ...] = (
    "latitude",
    "longitude",
    "altitude",
    "gps",
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

# Range Compression: each team SD between the means adds 33 points, so a
# shift of about 1.5 SD scores 50 and about 3 SD scores 100
SHIFT_POINTS_PER_SD: int = 33
# Each side's values are capped at its own 5th and 95th percentiles before
# scoring, so one extreme answer can't inflate everyone else's baseline SD
TRIM_QUANTILES: tuple[float, float] = (0.05, 0.95)
_SCORE_DECIMALS: int = 6
HISTOGRAM_BUCKETS: int = 10
# The histogram spans the rest of the team's 1st to 99th percentile
HISTOGRAM_QUANTILES: tuple[float, float] = (0.01, 0.99)

# Categorical Response Patterns: each percentage point between the
# enumerator's and the team's share of one option adds 2 points, so a gap of
# 25 points scores 50 and 50 points scores 100
CATEGORICAL_POINTS_PER_PP: int = 2


def is_gps_column(name: str) -> bool:
    """Return whether a column name looks like part of a GPS reading.

    Matches names containing latitude, longitude, altitude, gps or geopoint,
    names with a word lat, lon or lng, and SurveyCTO's ``field-Accuracy``
    geopoint part. Coordinates vary with where an enumerator works, not
    how they ask questions, so they don't suit these checks.
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


def badge_band(score: float | None, threshold: int) -> Badge:
    """Return the badge for ``score`` against the flag ``threshold``."""
    if score is None:
        return Badge.NA
    if score >= threshold:
        return Badge.HIGH
    if score >= threshold - MODERATE_MARGIN:
        return Badge.MODERATE
    return Badge.LOW


def _sort_key(
    result: DigitPreferenceEnumerator
    | RangeCompressionEnumerator
    | CategoricalEnumerator,
) -> tuple:
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


def _variation_skip(values: pl.Series) -> SkipReason | None:
    """Return why a variable cannot be used in any check, if it can't."""
    values = values.drop_nulls()
    if values.is_empty():
        return SkipReason.NO_RESPONSES
    if values.n_unique() == 1:
        return SkipReason.NO_VARIATION
    return None


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
        reason = _variation_skip(values)
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


def _compression_score(sd_ratio: float) -> float:
    """Return how far the enumerator's spread falls below the team's, 0-100.

    50 means an SD ratio of 0.5; a spread at least as wide as the team's
    scores 0.
    """
    return max(0.0, (1 - sd_ratio) * 100)


def _shift_score(enum_mean: float, team_mean: float, team_sd: float) -> float:
    """Return how far the enumerator's mean sits from the team's, 0-100."""
    return min(100.0, abs(enum_mean - team_mean) / team_sd * SHIFT_POINTS_PER_SD)


def _bucket_shares(values: pl.Series, low: float, width: float) -> list[float]:
    """Return the percentage of ``values`` in each histogram bucket.

    Values beyond either end count in the end bucket, so shares sum to 100.
    """
    buckets = ((values - low) / width).floor().clip(0, HISTOGRAM_BUCKETS - 1)
    counts = [0] * HISTOGRAM_BUCKETS
    for bucket in buckets.cast(pl.Int64):
        counts[bucket] += 1
    return _pct(counts)


def _histogram(
    enum_values: pl.Series, team_values: pl.Series
) -> tuple[list[float], list[float], list[float]]:
    """Return shared bucket edges and each series' share per bucket.

    The equal-width buckets span the rest of the team's 1st to 99th
    percentile, or its full range when those are equal.
    """
    low, high = (team_values.quantile(q, "linear") for q in HISTOGRAM_QUANTILES)
    if high <= low:
        low, high = team_values.min(), team_values.max()
    width = (high - low) / HISTOGRAM_BUCKETS
    edges = [low + i * width for i in range(HISTOGRAM_BUCKETS + 1)]
    return (
        edges,
        _bucket_shares(enum_values, low, width),
        _bucket_shares(team_values, low, width),
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
    """Score one enumerator on one variable, or return why it can't be."""
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
    sd_ratio = enum_sd / team_sd
    # Rounded so float noise can't drop a score at a threshold just below it
    compression = round(_compression_score(sd_ratio), _SCORE_DECIMALS)
    shift = round(_shift_score(enum_mean, team_mean, team_sd), _SCORE_DECIMALS)
    edges, enum_pct, team_pct = _histogram(enum_values, team_values)
    return RangeVariable(
        variable=variable,
        n_responses=n,
        sample_band=band,
        score=max(compression, shift),
        # Compression wins a tie, as its verdict comes first
        signal=RangeSignal.COMPRESSION if compression >= shift else RangeSignal.SHIFT,
        compression_score=compression,
        shift_score=shift,
        enum_mean=enum_mean,
        team_mean=team_mean,
        enum_sd=enum_sd,
        team_sd=team_sd,
        sd_ratio=sd_ratio,
        bucket_edges=edges,
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
    """Score one enumerator on every eligible variable.

    The enumerator's score is their highest variable score, so one problem
    question is never averaged away.
    """
    threshold = settings.range_compression_threshold
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

    scored.sort(key=lambda v: -v.score)
    top = scored[0] if scored else None
    score = top.score if top else None
    return RangeCompressionEnumerator(
        enumerator=enum,
        interviews=n_interviews,
        sample_band=top.sample_band if top else _best_band(bands),
        score=score,
        badge=badge_band(score, threshold),
        signal=top.signal if top else None,
        variables=scored,
        compression_variables=[
            v.variable for v in scored if v.compression_score >= threshold
        ],
        shift_variables=[v.variable for v in scored if v.shift_score >= threshold],
        skipped_variables=skipped,
    )


def _compute_range_compression(
    data: pl.DataFrame,
    variables: list[str],
    interviews: dict[str, int],
    settings: ResponsePatternSettings,
) -> RangeCompressionResult:
    """Score each enumerator's spread and level against the rest of the team."""
    threshold = settings.range_compression_threshold
    if not variables:
        return RangeCompressionResult(
            threshold=threshold, condition=CheckCondition.NO_APPLICABLE_VARIABLES
        )

    skipped: dict[str, SkipReason] = {}
    values: dict[str, pl.DataFrame] = {}
    for var in variables:
        if not data.schema[var].is_numeric():
            skipped[var] = SkipReason.NOT_NUMERIC
            continue
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
            threshold=threshold,
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
        threshold=threshold,
        condition=CheckCondition.ALL_BELOW_MINIMUM if all_insufficient else None,
        variables=list(values),
        skipped_variables=skipped,
        enumerators=sorted(enumerators, key=_sort_key),
    )


def _option_counts(
    frame: pl.DataFrame,
) -> tuple[list[str], dict[str, list[int]]]:
    """Return the options and each enumerator's count of each.

    Options are every value anyone on the team chose, as text, in the order
    of their values, so numeric codes sort 1, 2, 10 rather than 1, 10, 2.
    """
    options = (
        frame.select(_VALUE, pl.col(_VALUE).cast(pl.String).alias(_OPTION))
        .unique()
        .sort(_VALUE)[_OPTION]
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
    """Score one enumerator on one question, or return why it can't be.

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
    # Rounded so float noise can't drop a score at a threshold just below it
    gaps = [
        round(e - t, _SCORE_DECIMALS) for e, t in zip(enum_pct, team_pct, strict=True)
    ]
    largest_gap = max(abs(g) for g in gaps)
    score = min(100.0, largest_gap * CATEGORICAL_POINTS_PER_PP)
    highlight = settings.categorical_threshold / CATEGORICAL_POINTS_PER_PP
    top = max(range(len(options)), key=lambda i: gaps[i])
    # An over-chosen option wins a tie, as it names what the enumerator chose
    scoring = max(range(len(options)), key=lambda i: (abs(gaps[i]), gaps[i]))
    return CategoricalQuestion(
        variable=variable,
        n_responses=n,
        sample_band=band,
        score=score,
        largest_gap=largest_gap,
        scoring_option=options[scoring],
        flagged=score >= settings.categorical_threshold,
        dominant_option=options[top] if gaps[top] > 0 else None,
        options=[
            CategoricalOption(
                option=option,
                enum_pct=e,
                team_pct=t,
                gap=g,
                flagged=abs(g) >= highlight,
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
    """Score one enumerator on every eligible question.

    The enumerator's score is their highest question score, so one badly
    asked question is enough to flag them.
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

    scored.sort(key=lambda q: -q.score)
    top = scored[0] if scored else None
    score = top.score if top else None
    return CategoricalEnumerator(
        enumerator=enum,
        interviews=n_interviews,
        sample_band=top.sample_band if top else _best_band(bands),
        score=score,
        badge=badge_band(score, settings.categorical_threshold),
        questions=scored,
        skipped_variables=skipped,
    )


def _compute_categorical(
    data: pl.DataFrame,
    variables: list[str],
    interviews: dict[str, int],
    settings: ResponsePatternSettings,
) -> CategoricalResult:
    """Score how far each enumerator's answer options differ from the team's."""
    threshold = settings.categorical_threshold
    if not variables:
        return CategoricalResult(
            threshold=threshold, condition=CheckCondition.NO_APPLICABLE_VARIABLES
        )

    skipped: dict[str, SkipReason] = {}
    counts: dict[str, tuple[list[str], dict[str, list[int]]]] = {}
    for var in variables:
        frame = data.select(_ENUM, pl.col(var).alias(_VALUE)).drop_nulls(_VALUE)
        reason = _variation_skip(frame[_VALUE])
        if reason is None:
            counts[var] = _option_counts(frame)
        else:
            skipped[var] = reason
    if not counts:
        return CategoricalResult(
            threshold=threshold,
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
        threshold=threshold,
        condition=CheckCondition.ALL_BELOW_MINIMUM if all_insufficient else None,
        variables=list(counts),
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
        The project's missing codes, set to missing before scoring in both
        numeric and text columns.

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
