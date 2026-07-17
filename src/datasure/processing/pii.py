"""PII detection, review flags, and redaction for DataSure.

Two detection passes:

1. **Column-name heuristics** (always available, no model): strict and
   substring matching against multilingual restricted-word lists (ported in
   spirit from PovertyAction/PII_detection, MIT), plus a sparsity heuristic
   for free-text columns.
2. **Value scan** (requires a spaCy model): Microsoft Presidio's
   ``BatchAnalyzerEngine`` over a sample of values from string columns —
   NER-backed entities (PERSON, LOCATION) plus pattern recognizers
   (PHONE_NUMBER, EMAIL_ADDRESS, ...).

Flags persist per dataset in ``pii_flags_{alias}`` (logs db), following the
``prep_log_{alias}`` convention. Redaction helpers apply the reviewer's
per-column decisions (mask / drop / keep) to DataFrames and to the
correction log before export.

Presidio and spaCy are imported lazily inside functions: they are heavy and
only needed when a scan or model operation actually runs.
"""

from __future__ import annotations

import logging
from datetime import datetime

import polars as pl

# Module-attribute access (not `from ... import`) so tests patching
# datasure.utils.duckdb_utils at source affect this module too.
from datasure.utils import duckdb_utils

logger = logging.getLogger(__name__)

# --- Languages and models -------------------------------------------------

PII_LANGUAGES: dict[str, str] = {"en": "English", "es": "Spanish", "fr": "French"}
PII_MODEL_OPTIONS: dict[str, str] = {
    "en": "en_core_web_sm",
    "es": "es_core_news_sm",
    "fr": "fr_core_news_sm",
}

# --- Detection tuning -----------------------------------------------------

# Presidio entities considered PII for column flagging. DATE_TIME, URL and
# NRP are excluded as too noisy for survey data.
VALUE_SCAN_ENTITIES: frozenset[str] = frozenset(
    {
        "PERSON",
        "PHONE_NUMBER",
        "EMAIL_ADDRESS",
        "LOCATION",
        "IP_ADDRESS",
        "CREDIT_CARD",
        "IBAN_CODE",
        "MEDICAL_LICENSE",
    }
)
VALUE_SCORE_THRESHOLD = 0.4  # per-detection minimum confidence
VALUE_HIT_THRESHOLD = 0.3  # share of sampled values with a hit → flag column
VALUE_SAMPLE_SIZE = 100  # values sampled per string column

SPARSITY_THRESHOLD = 0.9  # unique/non-null ratio → likely free text
SPARSITY_MIN_ROWS = 20  # skip the heuristic on tiny columns

DEFAULT_MASK = "*****"
FLAG_DECISIONS = ("undecided", "mask", "drop", "keep")

# --- Restricted-word lists --------------------------------------------------
# Ported in spirit from PovertyAction/PII_detection (MIT), restricted_words.py,
# curated for false positives and extended with French. Strict = exact
# column-name match; fuzzy = substring match. The survey KEY / caseid system
# identifiers are deliberately NOT listed: the corrections pipeline needs the
# key column, and the export gate protects it explicitly.

_STRICT_WORDS: frozenset[str] = frozenset(
    {
        # SurveyCTO device/metadata identifiers
        "deviceid",
        "subscriberid",
        "simid",
        "devicephonenum",
        # Direct identifiers and common survey shorthands
        "name",
        "gps",
        "lat",
        "lon",
        "coord",
        "age",
        "dob",
        "phone",
        "fax",
        "email",
        "url",
        "ip",
        "enumerator",
        "enum",
        "address",
        "birth",
        # Spanish
        "nombre",
        "edad",
        "direccion",
        "telefono",
        "encuestador",
        # French
        "nom",
        "prenom",
        "adresse",
        "telephone",
        "naissance",
        # Swahili (retained from the source lists)
        "jina",
        "simu",
        "umri",
    }
)

_FUZZY_WORDS: frozenset[str] = frozenset(
    {
        # Names
        "first_name",
        "last_name",
        "firstname",
        "lastname",
        "fname",
        "lname",
        "nickname",
        "resp_name",
        "head_name",
        "enum_name",
        "_name",
        # Contact
        "phone",
        "email",
        "address",
        "website",
        # Location
        "latitude",
        "longitude",
        "coordinates",
        "village",
        "district",
        "subcounty",
        "sublocation",
        "parish",
        "community",
        "neighborhood",
        "neighbourhood",
        "municipio",
        "panchayat",
        "upazila",
        "barangay",
        # Demographics
        "birthday",
        "birth_date",
        "birthyear",
        "birthyy",
        # Spanish
        "apellido",
        "direccion",
        "latitud",
        "longitud",
        "coordenadas",
        "comunidad",
        "beneficiario",
        "fecha_nacimiento",
        "ubicacion",
        # French
        "prenom",
        "adresse",
        "quartier",
        "commune",
        "coordonnees",
        "telephone",
        "courriel",
        # Swahili
        "kijiji",
        "wilaya",
        "mkoa",
    }
)

# Mask labels per detected entity type; DEFAULT_MASK otherwise.
_ENTITY_MASKS: dict[str, str] = {
    "PERSON": "[PERSON]",
    "PHONE_NUMBER": "[PHONE]",
    "EMAIL_ADDRESS": "[EMAIL]",
    "LOCATION": "[LOCATION]",
    "IP_ADDRESS": "[IP_ADDRESS]",
    "CREDIT_CARD": "[CREDIT_CARD]",
    "IBAN_CODE": "[IBAN]",
    "MEDICAL_LICENSE": "[MEDICAL_LICENSE]",
}

_FLAGS_SCHEMA: dict[str, pl.DataType] = {
    "column": pl.String,
    "source": pl.String,
    "entity_type": pl.String,
    "hit_rate": pl.Float64,
    "sample_matches": pl.String,
    "decision": pl.String,
    "mask_label": pl.String,
    "scanned_at": pl.String,
}


def empty_flags() -> pl.DataFrame:
    """Return an empty PII-flags DataFrame with the canonical schema."""
    return pl.DataFrame(schema=_FLAGS_SCHEMA)


def mask_label_for(entity_type: str | None) -> str:
    """Return the mask label for an entity type, DEFAULT_MASK if unknown."""
    if not entity_type:
        return DEFAULT_MASK
    return _ENTITY_MASKS.get(entity_type, DEFAULT_MASK)


# --- Pass 1: column-name heuristics -----------------------------------------


def _name_match_source(column: str) -> str | None:
    """Return the heuristic source that flags *column*, or None."""
    name = column.lower().strip()
    if name in _STRICT_WORDS:
        return "name_match"
    if any(word in name for word in _FUZZY_WORDS):
        return "fuzzy"
    return None


def scan_column_names(df: pl.DataFrame) -> pl.DataFrame:
    """Flag columns by restricted-word matching and sparsity (no model needed).

    Parameters
    ----------
    df : pl.DataFrame
        The dataset to scan (typically the prepped data).

    Returns
    -------
    pl.DataFrame
        Flags rows with source "name_match", "fuzzy", or "sparsity".
    """
    now = datetime.now().isoformat(timespec="seconds")
    rows: list[dict] = []

    for column in df.columns:
        source = _name_match_source(column)
        if source is not None:
            rows.append(
                {
                    "column": column,
                    "source": source,
                    "entity_type": None,
                    "hit_rate": 1.0,
                    "sample_matches": "",
                    "decision": "undecided",
                    "mask_label": DEFAULT_MASK,
                    "scanned_at": now,
                }
            )
            continue

        # Sparsity: high-cardinality string columns are likely free text or
        # open-ended responses that can carry identifying detail.
        series = df[column]
        if series.dtype == pl.String:
            non_null = series.drop_nulls()
            if non_null.len() >= SPARSITY_MIN_ROWS:
                ratio = non_null.n_unique() / non_null.len()
                if ratio >= SPARSITY_THRESHOLD:
                    rows.append(
                        {
                            "column": column,
                            "source": "sparsity",
                            "entity_type": None,
                            "hit_rate": round(ratio, 3),
                            "sample_matches": "",
                            "decision": "undecided",
                            "mask_label": DEFAULT_MASK,
                            "scanned_at": now,
                        }
                    )

    if not rows:
        return empty_flags()
    return pl.DataFrame(rows, schema=_FLAGS_SCHEMA)


# --- Pass 2: Presidio value scan ---------------------------------------------


def installed_models() -> dict[str, bool]:
    """Return {language code: whether its spaCy model is installed}."""
    import spacy.util

    return {
        lang: spacy.util.is_package(model) for lang, model in PII_MODEL_OPTIONS.items()
    }


def download_model(language: str) -> tuple[bool, str]:
    """Download the spaCy model for *language*.

    Returns
    -------
    tuple[bool, str]
        (success, message). Fails gracefully on network errors.
    """
    model = PII_MODEL_OPTIONS.get(language)
    if model is None:
        return False, f"Unsupported language: {language}"
    try:
        import spacy.cli

        spacy.cli.download(model)
    except SystemExit as e:  # spacy.cli.download exits on failure
        logger.warning("spaCy model download failed for %s: %s", model, e)
        return False, f"Download failed for {model}. Check your network connection."
    except Exception as e:
        logger.warning("spaCy model download failed for %s: %s", model, e)
        return False, f"Download failed for {model}: {e}"
    return True, f"Model {model} installed."


# Analyzer engines are expensive to build (spaCy model load); memoize per
# language for the process lifetime. A plain dict is used instead of
# st.cache_resource so this module stays streamlit-free.
_ANALYZER_CACHE: dict[str, object] = {}


def _get_batch_analyzer(language: str):
    """Build (and cache) a Presidio BatchAnalyzerEngine for *language*."""
    if language in _ANALYZER_CACHE:
        return _ANALYZER_CACHE[language]

    from presidio_analyzer import AnalyzerEngine, BatchAnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": language, "model_name": PII_MODEL_OPTIONS[language]}],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=configuration).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=[language])
    batch = BatchAnalyzerEngine(analyzer_engine=analyzer)
    _ANALYZER_CACHE[language] = batch
    return batch


def scan_values(
    df: pl.DataFrame,
    language: str = "en",
    sample_size: int = VALUE_SAMPLE_SIZE,
) -> pl.DataFrame:
    """Scan sampled values of string columns with Presidio (needs a model).

    Parameters
    ----------
    df : pl.DataFrame
        The dataset to scan.
    language : str
        Language code; its spaCy model must already be installed.
    sample_size : int
        Maximum number of non-null values sampled per column.

    Returns
    -------
    pl.DataFrame
        Flags rows with source "value_scan" for columns whose sampled values
        hit PII entities at or above ``VALUE_HIT_THRESHOLD``.
    """
    now = datetime.now().isoformat(timespec="seconds")

    samples: dict[str, list[str]] = {}
    for column in df.columns:
        if df[column].dtype != pl.String:
            continue
        non_null = df[column].drop_nulls()
        if non_null.is_empty():
            continue
        samples[column] = non_null.head(sample_size).to_list()

    if not samples:
        return empty_flags()

    batch_analyzer = _get_batch_analyzer(language)
    results = batch_analyzer.analyze_dict(samples, language=language)

    rows: list[dict] = []
    for result in results:
        values = list(result.value)
        hit_values: list[str] = []
        entity_counts: dict[str, int] = {}
        for value, detections in zip(values, result.recognizer_results, strict=False):
            hits = [
                d
                for d in detections
                if d.entity_type in VALUE_SCAN_ENTITIES
                and d.score >= VALUE_SCORE_THRESHOLD
            ]
            if hits:
                hit_values.append(str(value))
                for d in hits:
                    entity_counts[d.entity_type] = (
                        entity_counts.get(d.entity_type, 0) + 1
                    )

        if not values:
            continue
        hit_rate = len(hit_values) / len(values)
        if hit_rate < VALUE_HIT_THRESHOLD:
            continue

        dominant = max(entity_counts, key=entity_counts.get)
        sample_matches = " | ".join(v[:60] for v in hit_values[:3])
        rows.append(
            {
                "column": result.key,
                "source": "value_scan",
                "entity_type": dominant,
                "hit_rate": round(hit_rate, 3),
                "sample_matches": sample_matches,
                "decision": "undecided",
                "mask_label": mask_label_for(dominant),
                "scanned_at": now,
            }
        )

    if not rows:
        return empty_flags()
    return pl.DataFrame(rows, schema=_FLAGS_SCHEMA)


# --- Scan orchestration -------------------------------------------------------


def run_pii_scan(
    df: pl.DataFrame,
    language: str = "en",
    use_value_scan: bool = True,
) -> pl.DataFrame:
    """Run both detection passes and combine to one flag row per column.

    When a column is flagged by both passes, the value-scan row wins for
    entity/hit-rate/mask fields and the sources are joined with "+".
    """
    name_flags = scan_column_names(df)
    value_flags = (
        scan_values(df, language=language) if use_value_scan else empty_flags()
    )

    by_column: dict[str, dict] = {
        row["column"]: row for row in name_flags.iter_rows(named=True)
    }
    for row in value_flags.iter_rows(named=True):
        existing = by_column.get(row["column"])
        if existing is not None:
            row = {**row, "source": f"{existing['source']}+{row['source']}"}
        by_column[row["column"]] = row

    if not by_column:
        return empty_flags()
    return pl.DataFrame(list(by_column.values()), schema=_FLAGS_SCHEMA)


def merge_with_existing(
    new_flags: pl.DataFrame, old_flags: pl.DataFrame
) -> pl.DataFrame:
    """Merge a fresh scan with stored flags, preserving user decisions.

    Detection fields come from the new scan; ``decision`` (and its
    ``mask_label`` when the user chose to mask) is carried over from the old
    flags. Columns no longer detected but carrying a non-default decision
    are retained so reviewer choices never silently disappear.
    """
    if old_flags.is_empty():
        return new_flags
    if new_flags.is_empty():
        return old_flags.filter(pl.col("decision") != "undecided")

    old_by_column = {row["column"]: row for row in old_flags.iter_rows(named=True)}
    rows: list[dict] = []
    for row in new_flags.iter_rows(named=True):
        old = old_by_column.pop(row["column"], None)
        if old is not None and old["decision"] != "undecided":
            row = {**row, "decision": old["decision"], "mask_label": old["mask_label"]}
        rows.append(row)

    rows.extend(old for old in old_by_column.values() if old["decision"] != "undecided")
    return pl.DataFrame(rows, schema=_FLAGS_SCHEMA)


# --- Persistence ---------------------------------------------------------------


def load_pii_flags(project_id: str, alias: str) -> pl.DataFrame:
    """Load stored PII flags for *alias*, empty flags if none exist."""
    try:
        flags = duckdb_utils.duckdb_get_table(project_id, f"pii_flags_{alias}", "logs")
    except Exception:
        logger.warning("PII flags for %s not found; returning empty flags", alias)
        return empty_flags()
    if flags.is_empty():
        return empty_flags()
    return flags


def save_pii_flags(project_id: str, alias: str, flags: pl.DataFrame) -> None:
    """Persist PII flags for *alias* to the logs db."""
    duckdb_utils.duckdb_save_table(
        project_id, flags, alias=f"pii_flags_{alias}", db_name="logs"
    )


# --- Redaction -------------------------------------------------------------------


def _effective_decision(decision: str, mask_undecided: bool) -> str:
    if decision == "undecided" and mask_undecided:
        return "mask"
    return decision


def apply_pii_decisions(
    df: pl.DataFrame,
    flags: pl.DataFrame,
    mask_undecided: bool = False,
    protect: tuple[str, ...] = (),
) -> pl.DataFrame:
    """Apply per-column PII decisions to a DataFrame.

    Parameters
    ----------
    df : pl.DataFrame
        The dataset to redact.
    flags : pl.DataFrame
        PII flags (canonical schema).
    mask_undecided : bool
        Treat "undecided" flags as "mask" (the export gate's conservative
        default).
    protect : tuple[str, ...]
        Columns never redacted regardless of flags (e.g. the survey key
        column, which the corrections pipeline requires).

    Returns
    -------
    pl.DataFrame
        Copy of *df* with masked columns replaced by their mask label
        (cast to String) and dropped columns removed.
    """
    if df.is_empty() or flags.is_empty():
        return df

    result = df
    for row in flags.iter_rows(named=True):
        column = row["column"]
        if column not in result.columns or column in protect:
            continue
        decision = _effective_decision(row["decision"], mask_undecided)
        if decision == "drop":
            result = result.drop(column)
        elif decision == "mask":
            label = row["mask_label"] or DEFAULT_MASK
            result = result.with_columns(
                pl.when(pl.col(column).is_not_null())
                .then(pl.lit(label))
                .otherwise(pl.lit(None, dtype=pl.String))
                .alias(column)
            )
    return result


def redact_correction_log(
    corr_log: pl.DataFrame,
    flags: pl.DataFrame,
    mask_undecided: bool = False,
    protect: tuple[str, ...] = (),
) -> pl.DataFrame:
    """Mask correction-log values for corrections that touch redacted columns.

    The correction log's ``current_value``/``new_value`` columns carry actual
    data values; when the corrected column is masked or dropped, those values
    must not leave the app (they are also embedded as literals in generated
    correction scripts).
    """
    if corr_log.is_empty() or flags.is_empty() or "column" not in corr_log.columns:
        return corr_log

    redacted_columns = [
        row["column"]
        for row in flags.iter_rows(named=True)
        if row["column"] not in protect
        and _effective_decision(row["decision"], mask_undecided) in ("mask", "drop")
    ]
    if not redacted_columns:
        return corr_log

    updates = [
        pl.when(pl.col("column").is_in(redacted_columns) & pl.col(field).is_not_null())
        .then(pl.lit(DEFAULT_MASK))
        .otherwise(pl.col(field))
        .alias(field)
        for field in ("current_value", "new_value")
        if field in corr_log.columns
    ]
    if not updates:
        return corr_log
    return corr_log.with_columns(updates)
