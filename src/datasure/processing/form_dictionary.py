"""Data dictionary and skip-logic summary stats of a SurveyCTO form.

Built from the form definition the import stores (``form_definitions`` in
``logs.duckdb``) and the alias's raw data, with ``datasure.surveycto``.
No Streamlit: views and checks call these functions.
"""

import io
import logging
from dataclasses import dataclass

import polars as pl
import pyarrow as pa

from datasure.surveycto.codebook import save_codebook
from datasure.surveycto.dictionary import build_dictionary
from datasure.surveycto.pii import PiiConfig, attach, classify
from datasure.surveycto.questions import build_questions
from datasure.surveycto.stats import stats_rows
from datasure.surveycto.xml_contract import parse_contract
from datasure.utils.duckdb_utils import load_form_definition
from datasure.utils.missing_codes import codes_by_label, whole_number_code

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FormDictionary:
    """What a form's dictionary build returns.

    Attributes
    ----------
    questions : list[dict]
        One entry per question, from ``build_questions``.
    dictionary : dict
        ``build_dictionary``'s output with each variable's PII block attached.
    stats : list[dict]
        One row per column from ``stats_rows``: counted only over the rows where
        the question was asked, with the missing codes set apart.
    """

    questions: list[dict]
    dictionary: dict
    stats: list[dict]


def sentinels_from_missing_codes(missing_codes: pl.DataFrame) -> dict[int, str]:
    """Return the project's whole-number missing codes as ``{code: label}``.

    The codes come from the Missing Values tab, never from a default list.
    Codes that are not whole numbers, such as ``.d`` or ``-99.9``, are left out:
    the dictionary counts sentinels in integer and choice columns only. A code
    listed under two labels raises, since its answers can't be attributed.
    """
    sentinels: dict[int, str] = {}
    for label, codes in codes_by_label(missing_codes).items():
        for code in codes:
            whole = whole_number_code(code)
            if whole is None:
                logger.debug("Missing code %r is not a whole number; not counted", code)
                continue
            if int(whole) in sentinels and sentinels[int(whole)] != label:
                raise ValueError(
                    f"Missing code {whole} is listed under both "
                    f"{sentinels[int(whole)]!r} and {label!r} on the Missing Values tab"
                )
            sentinels[int(whole)] = label
    return sentinels


def form_table(data: pl.DataFrame, arrow_schema: bytes) -> pa.Table:
    """Return the raw data as the cast Arrow table, field metadata included.

    The import stores the cast schema because Polars drops Arrow field metadata
    (each column's node path, XML type and choice code), which the dictionary
    reads. The import keeps the schema to raw's columns, so any difference is
    raised, never dropped.
    """
    schema = pa.ipc.read_schema(pa.py_buffer(arrow_schema))
    missing_cols = sorted(set(schema.names) - set(data.columns))
    extra_cols = sorted(set(data.columns) - set(schema.names))
    if missing_cols or extra_cols:
        raise ValueError(
            "raw does not match its stored form schema: "
            f"missing {missing_cols}, not in the schema {extra_cols}; "
            "import the form again"
        )
    return data.to_arrow().select(schema.names).cast(schema)


def build_form_dictionary(
    project_id: str, alias: str, raw: pl.DataFrame, missing_codes: pl.DataFrame
) -> FormDictionary | None:
    """Build the dictionary, PII flags and stats of an alias's raw data.

    ``None`` when the alias has no stored form definition: local files, server
    datasets, and SurveyCTO imports from before definitions were kept.
    PII flags come from the form's rules alone, trusting publishable fields;
    a column the rules leave open is ``may_contain_pii`` and its values stay
    out of the dictionary workbook.
    """
    definition = load_form_definition(project_id, alias)
    if definition is None:
        return None
    xml, arrow_schema = definition
    contract = parse_contract(xml)
    questions = build_questions(contract)
    table = form_table(raw, arrow_schema)
    sentinels = sentinels_from_missing_codes(missing_codes)
    dictionary = build_dictionary(table, questions, contract, sentinels)
    blocks = classify(table, dictionary, questions, PiiConfig(), None)
    attach(dictionary, blocks, questions, [])
    return FormDictionary(
        questions, dictionary, stats_rows(table, questions, dictionary, sentinels)
    )


def dictionary_xlsx(form_dictionary: FormDictionary) -> bytes:
    """Return the data dictionary workbook to share with PIs.

    Sheets: Variables (labels, types, choices, relevance, PII status) and
    Summary stats, counted over the rows where each question was asked.
    Upstream writes it with ``save_codebook``.
    """
    buffer = io.BytesIO()
    save_codebook(buffer, form_dictionary.dictionary, form_dictionary.stats)
    return buffer.getvalue()
