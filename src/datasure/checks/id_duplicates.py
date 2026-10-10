"""ID problems shown as cards on the Duplicates tab.

A card is one row of a "cards" DataFrame. Duplicate ID cards hold every record
that shares an ID; unmatched ID cards hold one backcheck whose ID is not in the
survey data. Every card has the columns:

- ``kind``: `DUPLICATE` or `UNMATCHED`
- ``id``: the ID as text
- ``n_records``: number of records on the card
- ``first_date`` / ``latest_date``: date range of the records, or null when
  no date column is configured
- ``keys``: the records' KEYs as text, for search
- ``rows``: the records' row positions in the dataset the card was built from

The functions here are pure; `id_duplicates_ui` renders the cards.
"""

from enum import StrEnum

import polars as pl

DUPLICATE = "Duplicate ID"
UNMATCHED = "Unmatched ID"
CARDS_PER_PAGE = 10

_ROW = "__row"
_ID = "__id"


class SortBy(StrEnum):
    """Orders for the cards."""

    GROUP_SIZE = "Group size"
    LATEST_DATE = "Latest date"


def _id_text(id_col: str) -> pl.Expr:
    return pl.col(id_col).cast(pl.String)


def _date_expr(data: pl.DataFrame, date_col: str | None) -> pl.Expr:
    """The date column, or a null date when it is not configured or usable."""
    if date_col and date_col in data.columns and data[date_col].dtype.is_temporal():
        return pl.col(date_col)
    return pl.lit(None, dtype=pl.Date)


def _key_expr(data: pl.DataFrame, key_col: str | None) -> pl.Expr:
    if key_col and key_col in data.columns:
        return pl.col(key_col).cast(pl.String)
    return pl.lit(None, dtype=pl.String)


def _cards(
    data: pl.DataFrame,
    id_col: str,
    key_col: str | None,
    date_col: str | None,
    kind: str,
    by_record: bool,
) -> pl.DataFrame:
    """Group `data` into cards, one per ID or, if `by_record`, one per record."""
    indexed = data.with_row_index(_ROW).select(
        pl.col(_ROW),
        _id_text(id_col).alias(_ID),
        _key_expr(data, key_col).alias("keys"),
        _date_expr(data, date_col).alias("date"),
    )
    group_by = [_ID, _ROW] if by_record else [_ID]
    return (
        indexed.group_by(group_by, maintain_order=True)
        .agg(
            pl.len().alias("n_records"),
            pl.col("date").min().alias("first_date"),
            pl.col("date").max().alias("latest_date"),
            pl.col("keys"),
            pl.col(_ROW).alias("rows"),
        )
        .select(
            pl.lit(kind).alias("kind"),
            pl.col(_ID).alias("id"),
            pl.col("n_records").cast(pl.UInt32),
            "first_date",
            "latest_date",
            "keys",
            pl.col("rows").cast(pl.List(pl.UInt32)),
        )
    )


def find_duplicate_groups(
    data: pl.DataFrame, id_col: str, key_col: str | None, date_col: str | None
) -> pl.DataFrame:
    """Return one card per ID shared by two or more records.

    Records with a missing ID are left out; `count_missing_ids` counts them.
    The cards are in the order their IDs first appear in `data`.
    """
    cards = _cards(data, id_col, key_col, date_col, DUPLICATE, by_record=False)
    return cards.filter(pl.col("id").is_not_null() & (pl.col("n_records") > 1))


def find_unmatched_ids(
    backcheck: pl.DataFrame,
    survey: pl.DataFrame,
    id_col: str,
    key_col: str | None,
    date_col: str | None,
) -> pl.DataFrame:
    """Return one card per backcheck whose ID is not in the survey data.

    IDs are compared as text, so a numeric survey ID matches the same ID
    stored as text in the backcheck data. Backchecks with a missing ID are
    left out; `count_missing_ids` counts them.
    """
    survey_ids = (
        survey.select(_id_text(id_col)).to_series().drop_nulls().unique()
        if id_col in survey.columns
        else pl.Series(dtype=pl.String)
    )
    cards = _cards(backcheck, id_col, key_col, date_col, UNMATCHED, by_record=True)
    return cards.filter(
        pl.col("id").is_not_null() & ~pl.col("id").is_in(survey_ids.implode())
    )


def count_missing_ids(data: pl.DataFrame, id_col: str) -> int:
    """Count the records with no ID."""
    return data[id_col].null_count()


def _duplicated_ids(data: pl.DataFrame, id_col: str) -> set[str]:
    if id_col not in data.columns:
        return set()
    return set(find_duplicate_groups(data, id_col, None, None)["id"].to_list())


def count_resolved_ids(
    uncorrected: pl.DataFrame, corrected: pl.DataFrame, id_col: str
) -> int:
    """Count the IDs duplicated before corrections and no longer after.

    Corrections from any page count, so this is how many duplicate IDs the
    correction log has resolved. IDs compare as text.
    """
    return len(
        _duplicated_ids(uncorrected, id_col) - _duplicated_ids(corrected, id_col)
    )


def card_records(data: pl.DataFrame, card: dict) -> pl.DataFrame:
    """Return the records on `card`, a row of a cards DataFrame."""
    return data[list(card["rows"])]


def default_fields(
    columns: list[str],
    *,
    key: str | None,
    date: str | None,
    staff: str | None,
    team: str | None,
    extra: list[str],
) -> list[str]:
    """Return the fields a card compares by default, in display order.

    These are the KEY, date, enumerator (or backchecker) and team columns when
    configured, then the `extra` columns chosen to show in the report. Columns
    not in `columns` are skipped.
    """
    fields: list[str] = []
    for col in [key, date, staff, team, *extra]:
        if col and col in columns and col not in fields:
            fields.append(col)
    return fields


def _cell_text(value) -> str | None:
    return None if value is None else str(value)


def comparison_grid(records: pl.DataFrame, fields: list[str]) -> pl.DataFrame:
    """Lay out `records` with `fields` as rows and records as columns.

    Returns the columns ``Field``, ``Record 1`` ... ``Record n`` (values as
    text, missing values as null) and ``differs``, true when a field's values
    are not the same in every record. A missing value counts as a value of its
    own.
    """
    record_cols = [f"Record {i}" for i in range(1, records.height + 1)]
    rows = []
    for field in fields:
        values = [_cell_text(v) for v in records[field].to_list()]
        rows.append([field, *values, len(set(values)) > 1])
    schema = {
        "Field": pl.String,
        **dict.fromkeys(record_cols, pl.String),
        "differs": pl.Boolean,
    }
    return pl.DataFrame(rows, schema=schema, orient="row")


def search_cards(cards: pl.DataFrame, query: str) -> pl.DataFrame:
    """Keep the cards whose ID or any KEY contains `query`, ignoring case."""
    query = query.strip().lower()
    if not query:
        return cards
    return cards.filter(
        pl.col("id").str.to_lowercase().str.contains(query, literal=True)
        | pl.col("keys")
        .list.eval(pl.element().str.to_lowercase().str.contains(query, literal=True))
        .list.any()
    )


def sort_cards(cards: pl.DataFrame, by: SortBy) -> pl.DataFrame:
    """Sort the cards, largest group or latest date first, then by ID."""
    if by == SortBy.LATEST_DATE:
        return cards.sort(
            ["latest_date", "id"], descending=[True, False], nulls_last=True
        )
    return cards.sort(["n_records", "id"], descending=[True, False])


def paginate_cards(
    cards: pl.DataFrame, page: int, per_page: int = CARDS_PER_PAGE
) -> tuple[pl.DataFrame, int, int]:
    """Return the cards on `page` (from 1), the page count and the page shown.

    `page` is clamped to the pages that exist; an empty list has one page.
    """
    n_pages = max(1, -(-cards.height // per_page))
    page = min(max(page, 1), n_pages)
    return cards.slice((page - 1) * per_page, per_page), n_pages, page


def build_export(
    data: pl.DataFrame, cards: pl.DataFrame, id_col: str, fields: list[str]
) -> pl.DataFrame:
    """Return every record on `cards`, in card order, with `fields`.

    The columns are ``issue`` (the card kind), `id_col` and `fields`.
    """
    columns = [id_col, *(f for f in fields if f != id_col)]
    order = cards.select("kind", "rows").with_row_index("__card").explode("rows")
    return order.join(
        data.with_row_index(_ROW).select(_ROW, *columns),
        left_on="rows",
        right_on=_ROW,
        how="left",
        maintain_order="left",
    ).select(pl.col("kind").alias("issue"), *columns)
