"""Parse the project's missing codes (Missing Values tab), with no Streamlit."""

import polars as pl


def codes_by_label(missing_codes_df: pl.DataFrame) -> dict[str, list[str]]:
    """Get missing code label to codes mapping.

    Parameters
    ----------
    missing_codes_df : pl.DataFrame
        The missing codes configuration.

    Returns
    -------
    dict[str, list[str]]
        Mapping of missing code labels to their codes.
    """
    code_map = {}
    if not missing_codes_df.is_empty():
        for row in missing_codes_df.iter_rows(named=True):
            label = row["label"]
            codes = [code.strip() for code in row["codes"].split(",") if code.strip()]
            code_map[label] = codes
    return code_map


def whole_number_code(code: str) -> str | None:
    """Return `code` as an integer string, or None if it is not a whole number.

    `-999.0` becomes `-999`, so it still matches an integer column. Decimal
    codes such as `.999` are kept for float columns but cannot occur in an
    integer one; truncating them to `0` would flag every real zero as missing.
    """
    try:
        return str(int(code))  # exact for large integers
    except ValueError:
        pass
    try:
        value = float(code)
    except ValueError:
        return None
    return str(int(value)) if value.is_integer() else None
