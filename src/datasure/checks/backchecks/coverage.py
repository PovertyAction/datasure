"""Backcheck coverage against the backcheck target.

The target % resolves from the settings panel, then the page config, then
`DEFAULT_TARGET_PERCENT`. Coverage counts unique survey IDs, leaving out
duplicated IDs and applying the optional eligibility filter, that have a
matching backcheck.
"""

import math
from dataclasses import dataclass

import polars as pl

from datasure.checks.backchecks.compute import exclude_duplicate_ids
from datasure.checks.backchecks.models import BackcheckSettings

DEFAULT_TARGET_PERCENT: float = 10.0

# Column `backchecked_surveys` adds to flag surveys with a matching backcheck.
BACKCHECKED: str = "_backchecked"


def settings_from_page_config(config: dict) -> BackcheckSettings:
    """Build backcheck settings from the page configuration.

    The page configuration stores 0 for a target left blank, so 0 means
    "not set" for both the backcheck target % and the survey target.
    """
    return BackcheckSettings(
        **{
            **config,
            "backcheck_target_percent": config.get("backcheck_target_percent") or None,
            "survey_target": config.get("survey_target") or None,
        }
    )


def effective_target_percent(settings: BackcheckSettings) -> float:
    """Return the backcheck target %, or the default when none is set."""
    if settings.backcheck_target_percent is None:
        return DEFAULT_TARGET_PERCENT
    return settings.backcheck_target_percent


@dataclass(frozen=True)
class BackcheckCoverage:
    """Backcheck progress against the target %.

    `on_track_percent` and `points_vs_target` are None when there are no
    eligible surveys. The expected-total fields are None when the survey
    target is not set.
    """

    eligible: int
    backchecked: int
    target_percent: float
    on_track_percent: float | None
    points_vs_target: float | None
    expected_backchecks: int | None
    expected_progress_percent: float | None


def backchecked_surveys(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    settings: BackcheckSettings,
) -> pl.DataFrame | None:
    """Return one row per eligible survey ID, flagged if it was backchecked.

    Records with a duplicated survey ID are left out of both datasets first,
    as in the backcheck comparison. Matching is by survey ID only.

    Returns
    -------
    pl.DataFrame | None
        The eligible survey rows with a unique ID plus a boolean `BACKCHECKED`
        column, or None if either dataset lacks the survey ID column.
    """
    survey_id = settings.survey_id
    if (
        not survey_id
        or survey_id not in survey_data.columns
        or survey_id not in backcheck_data.columns
    ):
        return None

    surveys = exclude_duplicate_ids(survey_data, survey_id)
    backchecked_ids = exclude_duplicate_ids(backcheck_data, survey_id)[
        survey_id
    ].drop_nulls()

    surveys = surveys.filter(pl.col(survey_id).is_not_null())
    eligibility_column = settings.eligibility_column
    if (
        eligibility_column
        and eligibility_column in surveys.columns
        and settings.eligibility_values
    ):
        surveys = surveys.filter(
            pl.col(eligibility_column).cast(pl.Utf8).is_in(settings.eligibility_values)
        )

    return surveys.with_columns(
        pl.col(survey_id).is_in(backchecked_ids.implode()).alias(BACKCHECKED)
    )


def compute_backcheck_coverage(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    settings: BackcheckSettings,
) -> BackcheckCoverage | None:
    """Compute overall backcheck coverage against the target.

    Returns None if either dataset lacks the survey ID column.
    """
    surveys = backchecked_surveys(survey_data, backcheck_data, settings)
    if surveys is None:
        return None

    eligible = surveys.height
    backchecked = int(surveys[BACKCHECKED].sum())
    target_percent = effective_target_percent(settings)
    on_track_percent = backchecked / eligible * 100 if eligible else None

    expected = None
    if settings.survey_target:
        # Round away float noise first so an exact product doesn't round up.
        expected = math.ceil(round(settings.survey_target * target_percent / 100, 9))

    return BackcheckCoverage(
        eligible=eligible,
        backchecked=backchecked,
        target_percent=target_percent,
        on_track_percent=on_track_percent,
        points_vs_target=(
            on_track_percent - target_percent if on_track_percent is not None else None
        ),
        expected_backchecks=expected,
        expected_progress_percent=backchecked / expected * 100 if expected else None,
    )


def compute_staff_coverage(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    settings: BackcheckSettings,
    staff_type: str = "enumerator",
) -> pl.DataFrame:
    """Compute backcheck coverage per enumerator, or backchecks per backchecker.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    settings : BackcheckSettings
        Backcheck settings.
    staff_type : str
        Either "enumerator" or "backchecker".

    Returns
    -------
    pl.DataFrame
        For enumerators: the enumerator column, "Surveys" (eligible unique
        submissions), "Backchecks" (how many of those were backchecked),
        "Coverage %" and "vs target" (points). Enumerators with no backchecks
        appear at 0%. For backcheckers: the backchecker column and
        "Backchecks" (unique backchecked survey IDs). Empty if the survey ID
        or staff column is missing.
    """
    surveys = backchecked_surveys(survey_data, backcheck_data, settings)
    if surveys is None:
        return pl.DataFrame()

    if staff_type == "enumerator":
        staff_col = settings.enumerator
        if not staff_col or staff_col not in surveys.columns:
            return pl.DataFrame()
        target_percent = effective_target_percent(settings)
        return (
            surveys.filter(pl.col(staff_col).is_not_null())
            .group_by(staff_col, maintain_order=True)
            .agg(
                pl.len().alias("Surveys"),
                pl.col(BACKCHECKED).sum().cast(pl.Int64).alias("Backchecks"),
            )
            .with_columns(
                (pl.col("Backchecks") / pl.col("Surveys") * 100).alias("Coverage %")
            )
            .with_columns((pl.col("Coverage %") - target_percent).alias("vs target"))
            .with_columns(pl.col("Surveys").cast(pl.Int64))
        )

    staff_col = settings.backchecker
    if not staff_col or staff_col not in backcheck_data.columns:
        return pl.DataFrame()
    survey_id = settings.survey_id
    backchecked_ids = surveys.filter(pl.col(BACKCHECKED))[survey_id]
    return (
        exclude_duplicate_ids(backcheck_data, survey_id)
        .filter(
            pl.col(survey_id).is_in(backchecked_ids.implode())
            & pl.col(staff_col).is_not_null()
        )
        .group_by(staff_col, maintain_order=True)
        .agg(pl.col(survey_id).n_unique().cast(pl.Int64).alias("Backchecks"))
    )
