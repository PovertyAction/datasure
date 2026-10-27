"""The page configuration each check starts from, as the dict it takes.

Shared by the check catalogue (rendering, settings, headlines) and the check
health deltas (`health_deltas`), so both pass every check the same values.
"""

from datasure.checks.context import CheckContext


def outliers_config(ctx: CheckContext) -> dict:
    """The configuration of Outliers & Constraints."""
    config = ctx.config
    return {
        "survey_key": config.survey_key,
        "survey_id": config.survey_id,
        "enumerator": config.enumerator,
        "team": config.team,
        "survey_date": config.survey_date,
    }


def backcheck_config(ctx: CheckContext) -> dict:
    """The configuration of Backchecks."""
    config = ctx.config
    return {
        "survey_key": config.survey_key,
        "survey_id": config.survey_id,
        "survey_date": config.survey_date,
        "backcheck_date": config.backcheck_date,
        "enumerator": config.enumerator,
        "backchecker": config.backchecker,
        "backchecker_team": config.backchecker_team,
        "backcheck_target_percent": config.backcheck_target_percent,
        "survey_target": config.survey_target,
    }


def progress_config(ctx: CheckContext) -> dict:
    """The configuration of Progress."""
    config = ctx.config
    return {
        "survey_key": config.survey_key,
        "survey_id": config.survey_id,
        "enumerator": config.enumerator,
        "survey_date": config.survey_date,
        "survey_target": config.survey_target,
    }


def duplicates_config(ctx: CheckContext) -> dict:
    """The configuration of Duplicates."""
    config = ctx.config
    return {
        "survey_key": config.survey_key,
        "survey_id": config.survey_id,
        "enumerator": config.enumerator,
        "team": config.team,
        "survey_date": config.survey_date,
        "backcheck_data_name": config.backcheck_data_name,
        "backcheck_date": config.backcheck_date,
        "backchecker": config.backchecker,
        "backchecker_team": config.backchecker_team,
    }


def enumerator_config(ctx: CheckContext) -> dict:
    """The configuration of Enumerator Stats."""
    config = ctx.config
    return {
        "survey_key": config.survey_key,
        "survey_id": config.survey_id,
        "survey_date": config.survey_date,
        "enumerator": config.enumerator,
        "formversion": config.formversion,
        "duration": config.duration,
        "team": config.team,
    }


def gps_config(ctx: CheckContext) -> dict:
    """The configuration of GPS Checks."""
    config = ctx.config
    return {
        "survey_key": config.survey_key,
        "survey_id": config.survey_id,
        "survey_date": config.survey_date,
        "enumerator": config.enumerator,
        "team": config.team,
    }
