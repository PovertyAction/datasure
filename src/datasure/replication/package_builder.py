"""Assemble the Stata replication package as an in-memory zip file."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from collections.abc import Callable

import polars as pl

from datasure.processing.correction_log import (
    CORRECTION_LOG_SCHEMA,
    Action,
    ensure_log_columns,
)
from datasure.processing.pii import (
    apply_pii_decisions,
    build_code_maps,
    empty_flags,
    get_or_create_pii_salt,
    load_code_maps,
    load_pii_flags,
    redact_correction_log,
    save_code_maps,
)
from datasure.replication.codebook import generate_codebook
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
        return ensure_log_columns(
            duckdb_get_table(project_id, f"corr_log_{alias}", "logs")
        )
    except Exception:
        logger.warning(
            "Correction log for %s not found; returning empty DataFrame", alias
        )
        return pl.DataFrame()


def _applied_corrections(correction_log: pl.DataFrame) -> pl.DataFrame:
    """Return the log rows that change data, dropping "accept" review records."""
    if "action" not in correction_log.columns:
        return correction_log
    return correction_log.filter(pl.col("action") != Action.ACCEPT)


def _blank_reviewer_names(correction_log: pl.DataFrame) -> pl.DataFrame:
    """Return a copy of *correction_log* with every ``user`` value set to null.

    The column is kept so the export still matches ``CORRECTION_LOG_SCHEMA``.
    """
    if "user" not in correction_log.columns:
        return correction_log
    return correction_log.with_columns(
        pl.lit(None, dtype=CORRECTION_LOG_SCHEMA["user"]).alias("user")
    )


def _action_summary(correction_log: pl.DataFrame) -> dict[str, int]:
    correction_log = _applied_corrections(correction_log)
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


def _load_pii_flags(project_id: str, alias: str) -> pl.DataFrame:
    try:
        return load_pii_flags(project_id, alias)
    except Exception:
        logger.warning("PII flags for %s not found; returning empty flags", alias)
        return empty_flags()


def _pii_column_lists(
    pii_flags: pl.DataFrame, protect: tuple[str, ...]
) -> dict[str, list[str]]:
    """Split flags into per-decision column lists.

    Returns a dict with keys "masked", "hashed", "coded", "dropped", and
    "kept". "undecided" flags count as masked — the export gate's
    conservative default. Protected columns (e.g. the survey key) are never
    redacted.
    """
    lists: dict[str, list[str]] = {
        "masked": [],
        "hashed": [],
        "coded": [],
        "dropped": [],
        "kept": [],
    }
    bucket = {
        "mask": "masked",
        "undecided": "masked",
        "hash": "hashed",
        "code": "coded",
        "drop": "dropped",
        "keep": "kept",
    }
    for row in pii_flags.iter_rows(named=True):
        if row["column"] in protect:
            lists["kept"].append(row["column"])
            continue
        lists[bucket.get(row["decision"], "kept")].append(row["column"])
    return lists


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
    include_pii: bool = False,
    on_progress: Callable[[str], None] | None = None,
    exclude_reviewer_names: bool = False,
    on_warning: Callable[[str], None] | None = None,
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
        The survey key column name (used in generated scripts). Never
        redacted: the corrections pipeline requires it.
    scto_form_xlsx : bytes | None
        Raw bytes of the SurveyCTO XLS form, if available. When provided the
        file is included in docs/ as ``{survey}_questionnaire.xlsx``.
    form_def : dict | None
        SurveyCTO form definition JSON from ``download_form_definition``.
        When provided, a fully-labelled ``import_data.do`` is generated
        instead of the generic template.
    form_id : str
        SurveyCTO form ID, used in the generated import script header.
    include_pii : bool
        False (default) exports a **de-identified** package: columns flagged
        in the PII review are masked or dropped (undecided flags are masked)
        in every bundled dataset, the codebook, and the correction log
        before anything is written. True exports the data untouched and
        bundles the flags audit log (``pii_flags.csv``).
    on_progress : Callable[[str], None] | None
        Optional callback invoked with a human-readable status message at each
        major step.  Callers can pass ``st.write`` to stream progress into a
        Streamlit status block.
    exclude_reviewer_names : bool
        When ``True``, blank the ``user`` column in the exported
        ``correction_log.csv``. The column is kept, and the project's stored
        correction log is not modified.
    on_warning : Callable[[str], None] | None
        Optional callback invoked with a message for each problem that does
        not stop the build, such as a prep step that could not be translated
        to Stata. Callers can pass ``st.warning``.

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

    # PII gate: in de-identified mode (the default) every flagged column is
    # masked or dropped in the data BEFORE anything downstream is generated,
    # so the CSVs, codebook, correction log, and the value literals
    # embedded in generated correction scripts are all covered. The survey
    # key column is protected (corrections need it).
    pii_flags = _load_pii_flags(project_id, alias)
    protect = (key_col,) if key_col else ()
    pii_cols = _pii_column_lists(pii_flags, protect)

    # The salt and code maps live only in the local cache.
    pii_salt = get_or_create_pii_salt(project_id) if pii_cols["hashed"] else None
    code_maps: dict[str, dict[str, str]] = {}
    if pii_cols["coded"]:
        code_maps = build_code_maps(
            [raw_df, prepped_df, corrected_df],
            pii_flags,
            existing=load_code_maps(project_id, alias),
            mask_undecided=True,
            protect=protect,
        )
        save_code_maps(project_id, alias, code_maps)

    if not include_pii and not pii_flags.is_empty():
        redact_kwargs = {
            "mask_undecided": True,
            "protect": protect,
            "salt": pii_salt,
            "code_maps": code_maps,
        }
        raw_df = apply_pii_decisions(raw_df, pii_flags, **redact_kwargs)
        prepped_df = apply_pii_decisions(prepped_df, pii_flags, **redact_kwargs)
        corrected_df = apply_pii_decisions(corrected_df, pii_flags, **redact_kwargs)
        correction_log = redact_correction_log(
            correction_log,
            pii_flags,
            mask_undecided=True,
            protect=protect,
            salt=pii_salt,
        )
        _step(
            "De-identification applied — "
            f"{len(pii_cols['masked'])} column(s) masked, "
            f"{len(pii_cols['hashed'])} hashed, "
            f"{len(pii_cols['coded'])} recoded, "
            f"{len(pii_cols['dropped'])} dropped"
            + (
                f", {len(pii_cols['kept'])} flagged column(s) kept"
                if pii_cols["kept"]
                else ""
            )
        )
    elif include_pii:
        _step("Export includes PII — data left untouched")

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
        on_warning=on_warning,
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
        correction_count=_applied_corrections(correction_log).height,
        prep_count=prep_log.height,
        raw_rows=raw_df.height,
        prepped_rows=prepped_df.height if not prepped_df.is_empty() else 0,
        corrected_rows=corrected_df.height if not corrected_df.is_empty() else 0,
        n_corrections_by_action=n_by_action,
        include_scto_form=scto_form_xlsx is not None,
        include_pii=include_pii,
        pii_masked_columns=pii_cols["masked"],
        pii_hashed_columns=pii_cols["hashed"],
        pii_coded_columns=pii_cols["coded"],
        pii_dropped_columns=pii_cols["dropped"],
        pii_kept_columns=pii_cols["kept"],
    )
    _step("README generated")

    codebook_csv = generate_codebook(corrected_df)
    _step("Codebook generated")

    # Raw CSV (input for import_data.do)
    raw_csv = raw_df.write_csv() if not raw_df.is_empty() else ""

    # Audit logs as CSV
    exported_log = correction_log
    if exclude_reviewer_names:
        exported_log = _blank_reviewer_names(correction_log)
        _step("Reviewer names removed from `correction_log.csv`")
    correction_log_csv = (
        exported_log.write_csv()
        if not exported_log.is_empty()
        else ",".join(CORRECTION_LOG_SCHEMA) + "\n"
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

        # 3_data/
        zf.writestr(f"{root}/3_data/1_raw/{safe_survey}_raw.csv", raw_csv)
        zf.writestr(f"{root}/3_data/2_intermediate/.gitkeep", "")
        zf.writestr(f"{root}/3_data/3_final/.gitkeep", "")

        # 4_output/
        zf.writestr(f"{root}/4_output/1_tables/.gitkeep", "")
        zf.writestr(f"{root}/4_output/2_figures/.gitkeep", "")
        zf.writestr(f"{root}/4_output/3_logs/correction_log.csv", correction_log_csv)
        zf.writestr(f"{root}/4_output/3_logs/prep_log.csv", prep_log_csv)
        # The flags audit log carries sample matched values (actual data), so
        # it is bundled only when the export already includes PII.
        if include_pii and not pii_flags.is_empty():
            zf.writestr(f"{root}/4_output/3_logs/pii_flags.csv", pii_flags.write_csv())

    logger.info("Zip assembled: %s", root)
    _step("Zip file assembled")

    return buf.getvalue()
