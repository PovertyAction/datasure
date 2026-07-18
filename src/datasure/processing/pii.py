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
per-column decisions to DataFrames and to the correction log before export:

- **mask** — every value replaced with a constant label (``[PERSON]``)
- **hash** — HMAC-SHA256 pseudonyms (``PERSON_3fa1b9c2``) keyed with a
  per-project secret salt kept in the local cache and never exported;
  deterministic, so categorical analysis (group-bys, joins, frequencies)
  still works, and dictionary attacks fail without the salt
- **code** — sequential category codes (``VILLAGE_NAME_001``) assigned in
  random order and persisted per project, the most readable option for
  categorical analysis with no cryptanalytic surface
- **drop** — column removed
- **keep** — untouched

Note: any deterministic pseudonym (hash or code) preserves the frequency
distribution, so rare categories remain identifiable by their rarity —
part of why de-identified output always carries the indirect-identifier
warning.

Presidio and spaCy are imported lazily inside functions: they are heavy and
only needed when a scan or model operation actually runs.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import random
import re
import secrets
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
FLAG_DECISIONS = ("undecided", "mask", "hash", "code", "drop", "keep")

# Hex digits kept from the HMAC digest in hash pseudonyms
HASH_TOKEN_LENGTH = 8

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


# --- Pseudonymization: salted hash tokens ----------------------------------------


def get_or_create_pii_salt(project_id: str) -> str:
    """Return the project's secret PII salt, generating it on first use.

    The salt lives in the local cache (logs db) like other project settings
    and is never included in de-identified exports, so recipients cannot
    dictionary-attack hash pseudonyms. It is stable for the project's
    lifetime, keeping hash tokens consistent across repeated exports.
    """
    try:
        stored = duckdb_utils.duckdb_get_table(project_id, "pii_salt", "logs")
        if not stored.is_empty():
            return stored["salt"][0]
    except Exception:
        logger.warning("PII salt for project %s not found; generating one", project_id)

    salt = secrets.token_hex(16)
    duckdb_utils.duckdb_save_table(
        project_id, pl.DataFrame({"salt": [salt]}), alias="pii_salt", db_name="logs"
    )
    return salt


def token_prefix(column: str, entity_type: str | None) -> str:
    """Return the pseudonym-token prefix for a column (e.g. ``PERSON``)."""
    raw = entity_type or column
    return "".join(ch if ch.isalnum() else "_" for ch in raw).upper()


def hash_token(value: object, salt: str, prefix: str) -> str:
    """Return a deterministic salted pseudonym like ``PERSON_3fa1b9c2``."""
    digest = hmac.new(salt.encode(), str(value).encode(), hashlib.sha256).hexdigest()
    return f"{prefix}_{digest[:HASH_TOKEN_LENGTH]}"


def hash_column_expr(column: str, salt: str, prefix: str) -> pl.Expr:
    """Polars expression hashing a column's values into salted pseudonyms.

    Idempotent: values that already look like this column's tokens are
    passed through unchanged, so hashing applied as a prep step is not
    hashed a second time by the export gate (HMAC is not idempotent by
    itself). Nulls stay null.
    """
    token_pattern = re.compile(
        rf"^{re.escape(prefix)}_[0-9a-f]{{{HASH_TOKEN_LENGTH}}}$"
    )

    def _tokenize(value: str) -> str:
        if token_pattern.match(value):
            return value
        return hash_token(value, salt, prefix)

    return (
        pl.col(column)
        .cast(pl.String)
        .map_elements(_tokenize, return_dtype=pl.String)
        .alias(column)
    )


def code_column_expr(column: str, mapping: dict[str, str]) -> pl.Expr:
    """Polars expression recoding a column's values via a code map.

    Idempotent: values that already are codes of this mapping pass through
    unchanged (so the export gate does not re-map an already-coded prep
    dataset). Values missing from the map are masked — never leaked.
    """
    code_values = list(set(mapping.values()))
    as_string = pl.col(column).cast(pl.String)
    return (
        pl.when(pl.col(column).is_null())
        .then(pl.lit(None, dtype=pl.String))
        .when(as_string.is_in(code_values))
        .then(as_string)
        .otherwise(as_string.replace_strict(mapping, default=DEFAULT_MASK))
        .alias(column)
    )


# --- Pseudonymization: category codes ---------------------------------------------


def load_code_maps(project_id: str, alias: str) -> dict[str, dict[str, str]]:
    """Load persisted value→code maps for *alias*: {column: {value: code}}."""
    try:
        stored = duckdb_utils.duckdb_get_table(
            project_id, f"pii_code_map_{alias}", "logs"
        )
    except Exception:
        logger.warning("PII code maps for %s not found; returning empty", alias)
        return {}
    if stored.is_empty():
        return {}
    maps: dict[str, dict[str, str]] = {}
    for row in stored.iter_rows(named=True):
        maps.setdefault(row["column"], {})[row["value"]] = row["code"]
    return maps


def save_code_maps(
    project_id: str, alias: str, maps: dict[str, dict[str, str]]
) -> None:
    """Persist value→code maps for *alias* to the logs db."""
    rows = [
        {"column": column, "value": value, "code": code}
        for column, mapping in maps.items()
        for value, code in mapping.items()
    ]
    if not rows:
        return
    duckdb_utils.duckdb_save_table(
        project_id,
        pl.DataFrame(rows),
        alias=f"pii_code_map_{alias}",
        db_name="logs",
    )


def build_code_maps(
    dfs: list[pl.DataFrame],
    flags: pl.DataFrame,
    existing: dict[str, dict[str, str]] | None = None,
    mask_undecided: bool = False,
    protect: tuple[str, ...] = (),
) -> dict[str, dict[str, str]]:
    """Assign sequential codes to every distinct value of code-decision columns.

    Distinct values are collected across all provided DataFrames (so the raw,
    prepped, and corrected datasets get consistent codes), new values are
    assigned in random order (no alphabetical-rank leak), and previously
    assigned codes from *existing* are preserved so re-exports stay stable.
    """
    maps: dict[str, dict[str, str]] = {
        column: dict(mapping) for column, mapping in (existing or {}).items()
    }
    for row in flags.iter_rows(named=True):
        column = row["column"]
        if column in protect:
            continue
        if _effective_decision(row["decision"], mask_undecided) != "code":
            continue

        values: set[str] = set()
        for df in dfs:
            if column in df.columns:
                values.update(
                    df[column].drop_nulls().cast(pl.String).unique().to_list()
                )

        maps[column] = extend_code_map(
            maps.get(column, {}), sorted(values), token_prefix(column, None)
        )
    return maps


def extend_code_map(
    mapping: dict[str, str], values: list[str], prefix: str
) -> dict[str, str]:
    """Return *mapping* extended with codes for any new *values*.

    Existing assignments are preserved; values that already are codes of
    this mapping are skipped. New values are assigned in random order.
    """
    extended = dict(mapping)
    new_values = sorted(set(values) - set(extended) - set(extended.values()))
    random.shuffle(new_values)
    next_index = len(extended) + 1
    for offset, value in enumerate(new_values):
        extended[value] = f"{prefix}_{next_index + offset:03d}"
    return extended


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
    salt: str | None = None,
    code_maps: dict[str, dict[str, str]] | None = None,
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
    salt : str | None
        Project secret for "hash" decisions. When missing, hash columns
        fall back to masking (the privacy-safe failure mode).
    code_maps : dict[str, dict[str, str]] | None
        Value→code maps for "code" decisions (see ``build_code_maps``).
        Columns without a map fall back to masking.

    Returns
    -------
    pl.DataFrame
        Copy of *df* with masked/hashed/coded columns replaced (cast to
        String) and dropped columns removed.
    """
    if df.is_empty() or flags.is_empty():
        return df

    result = df
    for row in flags.iter_rows(named=True):
        column = row["column"]
        if column not in result.columns or column in protect:
            continue
        decision = _effective_decision(row["decision"], mask_undecided)

        if decision == "hash" and salt is None:
            logger.warning("No salt provided; masking %s instead of hashing", column)
            decision = "mask"
        if decision == "code" and not (code_maps or {}).get(column):
            logger.warning("No code map for %s; masking instead of coding", column)
            decision = "mask"

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
        elif decision == "hash":
            prefix = token_prefix(column, row["entity_type"])
            result = result.with_columns(hash_column_expr(column, salt, prefix))
        elif decision == "code":
            result = result.with_columns(code_column_expr(column, code_maps[column]))
    return result


def redact_correction_log(
    corr_log: pl.DataFrame,
    flags: pl.DataFrame,
    mask_undecided: bool = False,
    protect: tuple[str, ...] = (),
    salt: str | None = None,
) -> pl.DataFrame:
    """Redact correction-log values for corrections that touch redacted columns.

    The correction log's ``current_value``/``new_value`` columns carry actual
    data values; when the corrected column is redacted, those values must not
    leave the app (they are also embedded as literals in generated correction
    scripts). Hash-decision columns get hash pseudonyms (keeping the log
    analyzable); mask/drop/code columns get the mask label — code maps are
    built from dataset values, so a correction's old/new values may not be
    in them, and masking is the safe default.
    """
    if corr_log.is_empty() or flags.is_empty() or "column" not in corr_log.columns:
        return corr_log

    masked_columns: list[str] = []
    hash_prefixes: dict[str, str] = {}
    for row in flags.iter_rows(named=True):
        column = row["column"]
        if column in protect:
            continue
        decision = _effective_decision(row["decision"], mask_undecided)
        if decision == "hash" and salt is not None:
            hash_prefixes[column] = token_prefix(column, row["entity_type"])
        elif decision in ("mask", "drop", "code", "hash"):
            masked_columns.append(column)

    if not masked_columns and not hash_prefixes:
        return corr_log

    def _redact_field(row: dict, field: str) -> str | None:
        value = row.get(field)
        if value is None:
            return None
        column = row.get("column")
        if column in hash_prefixes:
            return hash_token(value, salt, hash_prefixes[column])
        if column in masked_columns:
            return DEFAULT_MASK
        return value

    fields = [f for f in ("current_value", "new_value") if f in corr_log.columns]
    if not fields:
        return corr_log

    rows = [
        {**row, **{field: _redact_field(row, field) for field in fields}}
        for row in corr_log.iter_rows(named=True)
    ]
    return pl.DataFrame(rows, schema=corr_log.schema)
