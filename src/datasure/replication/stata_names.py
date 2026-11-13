"""Stata names for the columns a replication package uses.

The rules live in ``processing/column_names.stata_name_map``. This module
lists the names a package uses and keeps the names people chose instead of
the proposals, per dataset, in the ``stata_names_{alias}`` table of
``logs.duckdb``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping

import duckdb
import polars as pl

from datasure.processing.column_names import stata_name_map
from datasure.replication.prep_script_generator import prep_log_column_names
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table

logger = logging.getLogger(__name__)

_EDITS_SCHEMA = {"datasure_name": pl.String, "stata_name": pl.String}

# Variables the package's import scripts create, so no column may take them.
PACKAGE_VARIABLES = ("_ds_row", "new_data_row", "num_for_key")


def stata_names_table(alias: str) -> str:
    """The ``logs`` table holding a dataset's edited Stata names."""
    return f"stata_names_{alias}"


def package_column_names(
    raw_columns: Iterable[str], prep_log: pl.DataFrame
) -> list[str]:
    """Every column name the package uses, in the order they claim Stata names.

    The imported columns come first, then the names the prep steps use and
    create.
    """
    return list(dict.fromkeys([*raw_columns, *prep_log_column_names(prep_log)]))


def package_name_map(
    raw_columns: Iterable[str],
    prep_log: pl.DataFrame,
    edits: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Stata names for the names the package uses that Stata can't use."""
    return stata_name_map(
        package_column_names(raw_columns, prep_log), edits, PACKAGE_VARIABLES
    )


def updated_stata_name_edits(
    typed: Mapping[str, str],
    shown: Mapping[str, str],
    proposals: Mapping[str, str],
    saved: Mapping[str, str],
) -> dict[str, str]:
    """The edits to keep after people change the Stata names shown.

    ``typed`` is what the table holds now, ``shown`` the map it was filled
    from (with ``saved`` edits applied), and ``proposals`` the map without
    edits. A name counts as edited when it differs from what was shown or
    was already saved, and isn't simply the proposal, so typing the proposal
    back undoes an edit. A proposal that moved because an edit took its
    name isn't an edit.
    """
    edits: dict[str, str] = {}
    for name, stata_name in shown.items():
        value = str(typed.get(name) or "").strip()
        if (value != stata_name or name in saved) and value != proposals.get(name):
            edits[name] = value
    return edits


def load_stata_name_edits(project_id: str, alias: str) -> dict[str, str]:
    """The Stata names people chose for a dataset, keyed by DataSure name."""
    try:
        table = duckdb_get_table(project_id, stata_names_table(alias), "logs")
    except (duckdb.Error, OSError):
        logger.exception("Could not read the Stata name edits for %s", alias)
        return {}
    if table.is_empty() or not set(_EDITS_SCHEMA) <= set(table.columns):
        return {}
    return dict(zip(table["datasure_name"], table["stata_name"], strict=True))


def save_stata_name_edits(
    project_id: str, alias: str, edits: Mapping[str, str]
) -> None:
    """Replace a dataset's saved Stata name edits with ``edits``."""
    table = pl.DataFrame(
        {"datasure_name": list(edits), "stata_name": list(edits.values())},
        schema=_EDITS_SCHEMA,
    )
    duckdb_save_table(project_id, table, stata_names_table(alias), "logs")
