"""Assemble the replication package as an in-memory zip file."""

from __future__ import annotations

import io
import json
import zipfile

import polars as pl

from datasure.processing.replication.codebook import generate_codebook
from datasure.processing.replication.prep_script_generator import (
    generate_prepare_data_script,
)
from datasure.processing.replication.readme import generate_readme
from datasure.processing.replication.script_generators import (
    LANGUAGE_EXT,
    generate_corrections_script,
    generate_master_script,
)
from datasure.utils.duckdb_utils import duckdb_get_table


def _get_version() -> str:
    try:
        from importlib.metadata import version

        return version("DataSure")
    except Exception:
        return "unknown"


def _load_dataset(project_id: str, alias: str, db_name: str) -> pl.DataFrame:
    return duckdb_get_table(project_id, alias, db_name)


def _load_corrected(project_id: str, alias: str) -> pl.DataFrame:
    """Load corrected data, falling back to prep if no corrections exist."""
    corrected = _load_dataset(project_id, alias, "corrected")
    if corrected.is_empty():
        return _load_dataset(project_id, alias, "prep")
    return corrected


def _load_prep_log(project_id: str, alias: str) -> pl.DataFrame:
    return duckdb_get_table(project_id, f"prep_log_{alias}", "logs")


def _load_correction_log(project_id: str, alias: str) -> pl.DataFrame:
    return duckdb_get_table(project_id, f"corr_log_{alias}", "logs")


def build_replication_package(
    project_id: str,
    project_name: str,
    survey_name: str,
    alias: str,
    lang: str,
    key_col: str,
) -> bytes:
    """Build the replication package and return it as zip bytes.

    Parameters
    ----------
    project_id : str
        The project identifier.
    project_name : str
        Human-readable project name (used for folder and file naming).
    survey_name : str
        Human-readable survey name (used for file naming).
    alias : str
        The dataset alias stored in DuckDB.
    lang : str
        Export language: 'stata', 'r', or 'python'.
    key_col : str
        The survey key column name (used in generated scripts).

    Returns
    -------
    bytes
        Zip file contents ready for download.
    """
    datasure_version = _get_version()
    ext = LANGUAGE_EXT[lang]
    safe_project = project_name.lower().replace(" ", "_")
    safe_survey = survey_name.lower().replace(" ", "_")
    root = f"{safe_project}_replication"

    # Load data
    raw_df = _load_dataset(project_id, alias, "raw")
    prep_log = _load_prep_log(project_id, alias)
    prepped_df = _load_dataset(project_id, alias, "prep")
    corrected_df = _load_corrected(project_id, alias)
    correction_log = _load_correction_log(project_id, alias)

    # Build correction action summary
    n_by_action: dict[str, int] = {}
    if not correction_log.is_empty():
        counts = (
            correction_log.group_by("action")
            .agg(pl.len().alias("count"))
            .sort("action")
        )
        n_by_action = dict(
            zip(counts["action"].to_list(), counts["count"].to_list(), strict=False)
        )

    # Generate file contents
    prepare_data_script = generate_prepare_data_script(
        lang=lang,
        prep_log=prep_log,
        project_name=project_name,
        survey_name=survey_name,
        datasure_version=datasure_version,
    )
    corrections_script = generate_corrections_script(
        lang=lang,
        correction_log=correction_log,
        key_col=key_col,
        project_name=project_name,
        survey_name=survey_name,
        datasure_version=datasure_version,
    )
    master_script = generate_master_script(
        lang=lang,
        project_name=project_name,
        survey_name=survey_name,
        datasure_version=datasure_version,
    )
    readme = generate_readme(
        project_name=project_name,
        survey_name=survey_name,
        lang=lang,
        datasure_version=datasure_version,
        correction_count=correction_log.height,
        prep_count=prep_log.height,
        raw_rows=raw_df.height,
        prepped_rows=prepped_df.height if not prepped_df.is_empty() else 0,
        corrected_rows=corrected_df.height if not corrected_df.is_empty() else 0,
        n_corrections_by_action=n_by_action,
    )
    codebook_csv = generate_codebook(
        corrected_df if not corrected_df.is_empty() else raw_df
    )

    # Datasets as CSV strings
    raw_csv = raw_df.write_csv() if not raw_df.is_empty() else ""
    prepped_csv = prepped_df.write_csv() if not prepped_df.is_empty() else raw_csv
    corrected_csv = (
        corrected_df.write_csv() if not corrected_df.is_empty() else prepped_csv
    )
    correction_log_csv = (
        correction_log.write_csv()
        if not correction_log.is_empty()
        else "date,KEY,ID,action,column,current_value,new_value,reason\n"
    )
    prep_log_csv = (
        prep_log.with_columns(
            pl.col("prep_args").map_elements(
                lambda x: json.dumps(x) if x is not None else None,
                return_dtype=pl.String,
            )
        ).write_csv()
        if not prep_log.is_empty()
        else "action,description,prep_args,action_index\n"
    )

    # Assemble zip in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{root}/raw/{safe_survey}_raw.csv", raw_csv)
        zf.writestr(f"{root}/scripts/master.{ext}", master_script)
        zf.writestr(f"{root}/scripts/prepare_data.{ext}", prepare_data_script)
        zf.writestr(f"{root}/scripts/corrections.{ext}", corrections_script)
        zf.writestr(f"{root}/output/{safe_survey}_prepped.csv", prepped_csv)
        zf.writestr(f"{root}/output/{safe_survey}_corrected.csv", corrected_csv)
        zf.writestr(f"{root}/docs/README.md", readme)
        zf.writestr(f"{root}/docs/codebook.csv", codebook_csv)
        zf.writestr(f"{root}/docs/correction_log.csv", correction_log_csv)
        zf.writestr(f"{root}/docs/prep_log.csv", prep_log_csv)

    return buf.getvalue()
