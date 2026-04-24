"""Assemble the Stata replication package as an in-memory zip file."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from collections.abc import Callable

import polars as pl

from datasure.replication.prep_script_generator import (
    generate_prepare_data_script,
)
from datasure.replication.readme import generate_readme
from datasure.replication.script_generators import (
    SCRIPT_EXT,
    generate_corrections_script,
    generate_import_script,
    generate_install_packages_script,
    generate_master_script,
)
from datasure.replication.scto_import_generator import (
    generate_scto_import_script,
)
from datasure.utils.duckdb_utils import duckdb_get_table

logger = logging.getLogger(__name__)


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
    key_col: str,
    scto_form_xlsx: bytes | None = None,
    form_def: dict | None = None,
    form_id: str = "",
    on_progress: Callable[[str], None] | None = None,
) -> bytes:
    """Build the Stata replication package and return it as zip bytes.

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
    key_col : str
        The survey key column name (used in generated scripts).
    scto_form_xlsx : bytes | None
        Raw bytes of the SurveyCTO XLS form, if available. When provided the
        file is included in docs/ as ``{survey}_questionnaire.xlsx``.
    form_def : dict | None
        SurveyCTO form definition JSON from ``download_form_definition``.
        When provided, a fully-labelled ``import_data.do`` is generated
        instead of the generic template.
    form_id : str
        SurveyCTO form ID, used in the generated import script header.
    on_progress : Callable[[str], None] | None
        Optional callback invoked with a human-readable status message at each
        major step.  Callers can pass ``st.write`` to stream progress into a
        Streamlit status block.

    Returns
    -------
    bytes
        Zip file contents ready for download.
    """

    def _step(msg: str) -> None:
        logger.info(msg)
        if on_progress is not None:
            on_progress(msg)

    datasure_version = _get_version()
    safe_project = project_name.lower().replace(" ", "_")
    safe_survey = survey_name.lower().replace(" ", "_")
    root = f"replication_{safe_project}_{safe_survey}"

    logger.info(
        "Building replication package: project=%s survey=%s", project_name, survey_name
    )

    # Load data
    raw_df = _load_dataset(project_id, alias, "raw")
    _step(f"Raw data loaded — {raw_df.height:,} rows")

    prep_log = _load_prep_log(project_id, alias)
    _step(f"Preparation log loaded — {prep_log.height:,} steps")

    prepped_df = _load_dataset(project_id, alias, "prep")
    _step(f"Prepped dataset loaded — {prepped_df.height:,} rows")

    corrected_df = _load_corrected(project_id, alias)
    _step(f"Corrected dataset loaded — {corrected_df.height:,} rows")

    correction_log = _load_correction_log(project_id, alias)
    _step(f"Correction log loaded — {correction_log.height:,} entries")

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

    # Generate scripts
    if form_def is not None:
        import_script = generate_scto_import_script(
            form_def=form_def,
            form_id=form_id,
            form_title=survey_name,
            survey_name=survey_name,
            datasure_version=datasure_version,
        )
        _step("`import_data.do` generated (SurveyCTO — with labels & value labels)")
    else:
        import_script = generate_import_script(
            project_name=project_name,
            survey_name=survey_name,
            datasure_version=datasure_version,
        )
        _step("`import_data.do` generated")

    prepare_data_script = generate_prepare_data_script(
        prep_log=prep_log,
        project_name=project_name,
        survey_name=survey_name,
        datasure_version=datasure_version,
    )
    _step("`prepare_data.do` generated")

    install_packages_script = generate_install_packages_script(
        project_name=project_name,
        survey_name=survey_name,
        datasure_version=datasure_version,
    )
    _step("`install_packages.do` generated")

    corrections_script = generate_corrections_script(
        correction_log=correction_log,
        key_col=key_col,
        project_name=project_name,
        survey_name=survey_name,
        datasure_version=datasure_version,
    )
    _step("`corrections.do` generated")

    master_script = generate_master_script(
        project_name=project_name,
        survey_name=survey_name,
        datasure_version=datasure_version,
    )
    _step("`0_main.do` generated")

    readme = generate_readme(
        project_name=project_name,
        survey_name=survey_name,
        datasure_version=datasure_version,
        correction_count=correction_log.height,
        prep_count=prep_log.height,
        raw_rows=raw_df.height,
        prepped_rows=prepped_df.height if not prepped_df.is_empty() else 0,
        corrected_rows=corrected_df.height if not corrected_df.is_empty() else 0,
        n_corrections_by_action=n_by_action,
        include_scto_form=scto_form_xlsx is not None,
    )
    _step("README generated")

    # Raw CSV (input for import_data.do)
    raw_csv = raw_df.write_csv() if not raw_df.is_empty() else ""

    # Audit logs as CSV
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

    # Assemble zip in memory. DTA files are generated when the scripts are run.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # README
        zf.writestr(f"{root}/0_README.txt", readme)

        # 1_docs/
        if scto_form_xlsx is not None:
            zf.writestr(
                f"{root}/1_docs/surveys/{safe_survey}_questionnaire.xlsx",
                scto_form_xlsx,
            )
        else:
            zf.writestr(f"{root}/1_docs/surveys/.gitkeep", "")
        zf.writestr(f"{root}/1_docs/codebooks/.gitkeep", "")
        zf.writestr(f"{root}/1_docs/notes/.gitkeep", "")

        # 2_scripts/
        zf.writestr(f"{root}/2_scripts/0_main.{SCRIPT_EXT}", master_script)
        zf.writestr(
            f"{root}/2_scripts/1_install_packages.{SCRIPT_EXT}", install_packages_script
        )
        zf.writestr(f"{root}/2_scripts/2_import_data.{SCRIPT_EXT}", import_script)
        zf.writestr(
            f"{root}/2_scripts/3_prepare_data.{SCRIPT_EXT}", prepare_data_script
        )
        zf.writestr(f"{root}/2_scripts/4_corrections.{SCRIPT_EXT}", corrections_script)

        # data/
        zf.writestr(f"{root}/data/raw/{safe_survey}_raw.csv", raw_csv)
        zf.writestr(f"{root}/data/intermediate/.gitkeep", "")
        zf.writestr(f"{root}/data/final/.gitkeep", "")

        # output/
        zf.writestr(f"{root}/output/tables/.gitkeep", "")
        zf.writestr(f"{root}/output/figures/.gitkeep", "")
        zf.writestr(f"{root}/output/logs/correction_log.csv", correction_log_csv)
        zf.writestr(f"{root}/output/logs/prep_log.csv", prep_log_csv)

    logger.info("Zip assembled: %s", root)
    _step("Zip file assembled")

    return buf.getvalue()
