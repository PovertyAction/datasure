"""Assemble the Stata replication package as an in-memory zip file."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from collections.abc import Callable

import polars as pl

from datasure.replication.codebook import generate_codebook
from datasure.replication.data_dict import generate_data_dict
from datasure.replication.prep_script_generator import (
    generate_prepare_data_script,
)
from datasure.replication.py_prep_script_generator import (
    generate_prepare_data_script_py,
)
from datasure.replication.py_script_generators import (
    SCRIPT_EXT_PY,
    generate_corrections_script_py,
    generate_import_script_py,
    generate_master_script_py,
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
    try:
        return duckdb_get_table(project_id, alias, db_name)
    except Exception:
        logger.warning(
            "Table %s/%s not found; returning empty DataFrame", db_name, alias
        )
        return pl.DataFrame()


def _load_corrected(project_id: str, alias: str) -> tuple[pl.DataFrame, bool]:
    """Load corrected data, falling back to prep if no corrections exist.

    Returns
    -------
    tuple[pl.DataFrame, bool]
        The dataset and a flag indicating whether corrections were applied.
    """
    corrected = _load_dataset(project_id, alias, "corrected")
    if not corrected.is_empty():
        return corrected, True
    return _load_dataset(project_id, alias, "prep"), False


def _load_prep_log(project_id: str, alias: str) -> pl.DataFrame:
    try:
        return duckdb_get_table(project_id, f"prep_log_{alias}", "logs")
    except Exception:
        logger.warning("Prep log for %s not found; returning empty DataFrame", alias)
        return pl.DataFrame()


def _load_correction_log(project_id: str, alias: str) -> pl.DataFrame:
    try:
        return duckdb_get_table(project_id, f"corr_log_{alias}", "logs")
    except Exception:
        logger.warning(
            "Correction log for %s not found; returning empty DataFrame", alias
        )
        return pl.DataFrame()


def _action_summary(correction_log: pl.DataFrame) -> dict[str, int]:
    if correction_log.is_empty():
        return {}
    counts = (
        correction_log.group_by("action").agg(pl.len().alias("count")).sort("action")
    )
    return dict(
        zip(counts["action"].to_list(), counts["count"].to_list(), strict=False)
    )


def _select_import_script(
    form_def: dict | None,
    form_id: str,
    project_name: str,
    survey_name: str,
    datasure_version: str,
) -> str:
    if form_def is not None:
        return generate_scto_import_script(
            form_def=form_def,
            form_id=form_id,
            form_title=form_def.get("title", survey_name),
            survey_name=survey_name,
            datasure_version=datasure_version,
        )
    return generate_import_script(
        project_name=project_name,
        survey_name=survey_name,
        datasure_version=datasure_version,
    )


def _to_parquet_bytes(df: pl.DataFrame) -> bytes:
    if df.is_empty():
        return b""
    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


def _serialize_prep_args(x: object) -> str | None:
    if x is None:
        return None
    try:
        return json.dumps(x)
    except (TypeError, ValueError):
        return str(x)


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

    corrected_df, has_corrections = _load_corrected(project_id, alias)
    _step(
        f"Corrected dataset loaded — {corrected_df.height:,} rows"
        if has_corrections
        else f"No corrections applied — using prepped dataset ({corrected_df.height:,} rows)"
    )

    correction_log = _load_correction_log(project_id, alias)
    _step(f"Correction log loaded — {correction_log.height:,} entries")

    n_by_action = _action_summary(correction_log)

    # Generate scripts
    import_script = _select_import_script(
        form_def, form_id, project_name, survey_name, datasure_version
    )
    _step(
        "`import_data.do` generated (SurveyCTO — with labels & value labels)"
        if form_def is not None
        else "`import_data.do` generated"
    )

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

    import_script_py = generate_import_script_py(
        project_name=project_name,
        survey_name=survey_name,
        datasure_version=datasure_version,
    )
    prepare_data_script_py = generate_prepare_data_script_py(
        prep_log=prep_log,
        project_name=project_name,
        survey_name=survey_name,
        datasure_version=datasure_version,
    )
    corrections_script_py = generate_corrections_script_py(
        correction_log=correction_log,
        key_col=key_col,
        project_name=project_name,
        survey_name=survey_name,
        datasure_version=datasure_version,
    )
    master_script_py = generate_master_script_py(
        project_name=project_name,
        survey_name=survey_name,
        datasure_version=datasure_version,
    )
    _step("Python replication scripts generated (`uv run`-ready)")

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

    codebook_csv = generate_codebook(corrected_df)
    _step("Codebook generated")

    corrected_parquet_path = f"../../3_data/3_final/{safe_survey}_corrected.parquet"
    data_dict_yaml = generate_data_dict(
        corrected_df,
        table_name=safe_survey,
        label=survey_name,
        description=(
            f"Corrected dataset for {survey_name}, generated by DataSure "
            f"{datasure_version}."
        ),
        key_col=key_col,
        parquet_path=corrected_parquet_path,
        datasure_version=datasure_version,
    )
    _step("data-dict.yaml generated")

    # Raw CSV (input for import_data.do)
    raw_csv = raw_df.write_csv() if not raw_df.is_empty() else ""

    # Parquet exports (usable without Stata)
    raw_parquet = _to_parquet_bytes(raw_df)
    prepped_parquet = _to_parquet_bytes(prepped_df)
    corrected_parquet = _to_parquet_bytes(corrected_df)
    _step("Parquet exports generated")

    # Audit logs as CSV
    correction_log_csv = (
        correction_log.write_csv()
        if not correction_log.is_empty()
        else "date,KEY,ID,action,column,current_value,new_value,reason\n"
    )
    prep_log_csv = (
        prep_log.with_columns(
            pl.col("prep_args").map_elements(
                _serialize_prep_args,
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
                f"{root}/1_docs/1_surveys/{safe_survey}_questionnaire.xlsx",
                scto_form_xlsx,
            )
        else:
            zf.writestr(f"{root}/1_docs/1_surveys/.gitkeep", "")
        zf.writestr(f"{root}/1_docs/2_codebooks/codebook.csv", codebook_csv)
        zf.writestr(f"{root}/1_docs/2_codebooks/data-dict.yaml", data_dict_yaml)
        zf.writestr(f"{root}/1_docs/3_notes/.gitkeep", "")

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
        zf.writestr(f"{root}/2_scripts/0_main.{SCRIPT_EXT_PY}", master_script_py)
        zf.writestr(f"{root}/2_scripts/2_import_data.{SCRIPT_EXT_PY}", import_script_py)
        zf.writestr(
            f"{root}/2_scripts/3_prepare_data.{SCRIPT_EXT_PY}", prepare_data_script_py
        )
        zf.writestr(
            f"{root}/2_scripts/4_corrections.{SCRIPT_EXT_PY}", corrections_script_py
        )

        # 3_data/
        zf.writestr(f"{root}/3_data/1_raw/{safe_survey}_raw.csv", raw_csv)
        zf.writestr(f"{root}/3_data/1_raw/{safe_survey}_raw.parquet", raw_parquet)
        if prepped_parquet:
            zf.writestr(
                f"{root}/3_data/2_intermediate/{safe_survey}_prepped.parquet",
                prepped_parquet,
            )
        else:
            zf.writestr(f"{root}/3_data/2_intermediate/.gitkeep", "")
        if corrected_parquet:
            zf.writestr(
                f"{root}/3_data/3_final/{safe_survey}_corrected.parquet",
                corrected_parquet,
            )
        else:
            zf.writestr(f"{root}/3_data/3_final/.gitkeep", "")

        # 4_output/
        zf.writestr(f"{root}/4_output/1_tables/.gitkeep", "")
        zf.writestr(f"{root}/4_output/2_figures/.gitkeep", "")
        zf.writestr(f"{root}/4_output/3_logs/correction_log.csv", correction_log_csv)
        zf.writestr(f"{root}/4_output/3_logs/prep_log.csv", prep_log_csv)

    logger.info("Zip assembled: %s", root)
    _step("Zip file assembled")

    return buf.getvalue()
