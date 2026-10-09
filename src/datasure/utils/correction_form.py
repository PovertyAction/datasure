"""Shared correction form: the action, new-value and reason inputs.

The Corrections page and the check pages all correct or accept values with
the same inputs. `render_correction_form` renders them for one KEY (and
optionally a prefilled column and current value) with an Apply button;
`render_correction_inputs` renders them without a button so a caller can
collect several entries and save them together with
`apply_correction_entries`, which applies them all or none.

Every widget key is suffixed with `key_namespace`, so the form can appear on
several pages and tabs at once.

Streamlit is imported inside each function rather than at module level, as
in `ui_utils`: view tests swap ``sys.modules["streamlit"]`` for a mock, and
resolving it per call honors that swap whatever the import order.
"""

import logging
from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any

import polars as pl
from pydantic import BaseModel, Field

from datasure.processing.correction_log import (
    CORRECTION_ACTIONS,
    Action,
)
from datasure.processing.corrections import CorrectionEntry, CorrectionProcessor

logger = logging.getLogger(__name__)


class CorrectionFormState(BaseModel):
    """State management for correction form inputs."""

    key_value: str = Field(..., description="The selected key value for correction")
    action: Action = Field(..., description="The correction action type")
    column: str | None = Field(None, description="The column to modify (if applicable)")
    current_value: Any | None = Field(
        None, description="The current value (if applicable)"
    )
    new_value: Any | None = Field(None, description="The new value (if applicable)")
    validation_error: str | None = Field(
        None, description="Validation error message (if any)"
    )
    reason: str = Field("", description="The reason entered for the entry")
    check_type: str | None = Field(
        None, description="For 'accept', the check whose flag is accepted"
    )
    survey_id_value: Any | None = Field(
        None, description="The Survey ID value for the KEY, if configured"
    )

    def to_entry(self) -> CorrectionEntry:
        """Return the entry to pass to `CorrectionProcessor.apply_corrections`."""
        return CorrectionEntry(
            key_value=self.key_value,
            action=self.action,
            reason=self.reason,
            column=self.column,
            current_value=self.current_value,
            new_value=self.new_value,
            survey_id_value=self.survey_id_value,
            check_type=self.check_type,
        )


def get_current_value(
    data: pl.DataFrame, key_col: str, key_value: str, column: str
) -> Any:
    """
    Retrieve the current value for a specific key and column.

    Parameters
    ----------
    data : pl.DataFrame
        The dataset to query.
    key_col : str
        The name of the key column.
    key_value : str
        The key value to filter by.
    column : str
        The column to retrieve the value from.

    Returns
    -------
    Any
        The current value, or None if not found.
    """
    try:
        return data.filter(pl.col(key_col) == key_value).select(column)[0, 0]
    except (pl.exceptions.PolarsError, IndexError):
        logger.debug(
            "No value for %s=%r in column %r", key_col, key_value, column, exc_info=True
        )
        return None


def parse_date_value(value: Any) -> date | None:
    """
    Parse a datetime value to a date object.

    Parameters
    ----------
    value : Any
        The value to parse (can be string or datetime).

    Returns
    -------
    date | None
        Parsed date or None if parsing fails.
    """
    if not value:
        return None

    try:
        if isinstance(value, str):
            return datetime.fromisoformat(value).date()
        return value.date()
    except (ValueError, TypeError, AttributeError):
        logger.debug("Could not parse %r as a date", value, exc_info=True)
        return None


def validate_numeric_input(value: str, dtype: pl.DataType) -> tuple[bool, str | None]:
    """
    Validate numeric input based on column data type.

    Parameters
    ----------
    value : str
        The input value to validate.
    dtype : pl.DataType
        The expected data type.

    Returns
    -------
    tuple[bool, str | None]
        A tuple of (is_valid, error_message).
    """
    if dtype in [pl.Int64, pl.Int32, pl.Float64, pl.Float32]:
        try:
            float(value)
            return True, None  # noqa: TRY300
        except ValueError:
            return False, "New value must be a number."
    return True, None


def should_enable_apply_button(
    action: Action, reason: str, new_value: Any = None
) -> bool:
    """
    Determine if the apply button should be enabled.

    Parameters
    ----------
    action : Action
        The correction action type.
    reason : str
        The reason for correction.
    new_value : Any, optional
        The new value (required for modify action). Falsy values such as
        "0" or 0 are valid. An empty string is treated as missing: to blank
        a cell, use the "remove value" action.

    Returns
    -------
    bool
        True if apply button should be enabled.
    """
    if not reason:
        return False

    if action == Action.MODIFY_VALUE:
        return new_value is not None and new_value != ""
    return action in [Action.REMOVE_VALUE, Action.REMOVE_ROW, Action.ACCEPT]


def render_value_input_widget(
    column: str,
    col_dtype: pl.DataType,
    current_value: Any,
    key_namespace: str | int,
) -> tuple[Any, str | None]:
    """
    Render appropriate input widget based on column data type.

    Parameters
    ----------
    column : str
        The column name being modified.
    col_dtype : pl.DataType
        The column data type.
    current_value : Any
        The current value in the column.
    key_namespace : str | int
        Suffix for unique widget keys.

    Returns
    -------
    tuple[Any, str | None]
        A tuple of (new_value, error_message).
    """
    import streamlit as st

    if col_dtype == pl.Datetime:
        current_date = parse_date_value(current_value)
        new_value = st.date_input(
            label="New Value",
            key=f"correction_new_value_{key_namespace}",
            value=current_date,
            help="Select a date for the new value.",
        )
        return new_value, None

    # Text input for other types
    new_value = st.text_input(
        label="New Value",
        key=f"correction_new_value_{key_namespace}",
        placeholder="Enter new value",
    )

    if new_value:
        is_valid, error_msg = validate_numeric_input(new_value, col_dtype)
        if not is_valid:
            return None, error_msg

    return new_value, None


def _render_column_selector(
    data: pl.DataFrame,
    key_col: str,
    key_value: str,
    key_namespace: str | int,
    column: str | None = None,
    current_value: Any = None,
) -> tuple[str | None, Any]:
    """Render the column selector (unless prefilled) and the current value.

    Returns the column and its current value. A prefilled `current_value` is
    shown as is; otherwise it is looked up in `data`.
    """
    import streamlit as st

    if column is None:
        column = st.selectbox(
            label="Select Column to Modify",
            options=data.columns,
            key=f"correction_col_to_modify_{key_namespace}",
        )
        if not column:
            return None, None
    else:
        st.write(f"**Column:** {column}")

    if current_value is None:
        current_value = get_current_value(data, key_col, key_value, column)

    st.write(f"**Current Value:** {current_value}")

    return column, current_value


def _render_modify_value_action(
    data: pl.DataFrame,
    key_col: str,
    key_value: str,
    key_namespace: str | int,
    column: str | None = None,
    current_value: Any = None,
) -> CorrectionFormState:
    """Render the 'modify value' inputs and return the collected state."""
    import streamlit as st

    column, current_value = _render_column_selector(
        data, key_col, key_value, key_namespace, column, current_value
    )

    if not column:
        return CorrectionFormState(
            key_value=key_value, action=Action.MODIFY_VALUE, column=None
        )

    col_dtype = data.schema[column]
    new_value, validation_error = render_value_input_widget(
        column, col_dtype, current_value, key_namespace
    )

    if validation_error:
        st.error(validation_error)

    return CorrectionFormState(
        key_value=key_value,
        action=Action.MODIFY_VALUE,
        column=column,
        current_value=current_value,
        new_value=new_value,
        validation_error=validation_error,
    )


def _render_remove_value_action(
    data: pl.DataFrame,
    key_col: str,
    key_value: str,
    key_namespace: str | int,
    column: str | None = None,
    current_value: Any = None,
) -> CorrectionFormState:
    """Render the 'remove value' inputs and return the collected state."""
    column, current_value = _render_column_selector(
        data, key_col, key_value, key_namespace, column, current_value
    )

    return CorrectionFormState(
        key_value=key_value,
        action=Action.REMOVE_VALUE,
        column=column,
        current_value=current_value,
    )


def _render_remove_row_action(key_value: str) -> CorrectionFormState:
    """Render the 'remove row' warning and return the collected state."""
    import streamlit as st

    st.warning("This will remove the row with the selected key value from the dataset.")

    return CorrectionFormState(key_value=key_value, action=Action.REMOVE_ROW)


def _render_accept_action(
    data: pl.DataFrame,
    key_col: str,
    key_value: str,
    key_namespace: str | int,
    column: str | None = None,
    current_value: Any = None,
    check_type: str | None = None,
) -> CorrectionFormState:
    """Render the 'accept' inputs and return the collected state.

    A GPS acceptance has no column: its prefilled current value maps the
    latitude and longitude columns to their values.
    """
    import streamlit as st

    if column is None and isinstance(current_value, dict):
        st.write(f"**Current Value:** {current_value}")
    else:
        column, current_value = _render_column_selector(
            data, key_col, key_value, key_namespace, column, current_value
        )

    return CorrectionFormState(
        key_value=key_value,
        action=Action.ACCEPT,
        column=column,
        current_value=current_value,
        check_type=check_type,
    )


def _render_action_ui(
    action: Action,
    data: pl.DataFrame,
    key_col: str,
    key_value: str,
    key_namespace: str | int,
    column: str | None = None,
    current_value: Any = None,
    check_type: str | None = None,
) -> CorrectionFormState:
    """Render the inputs for `action` and return the collected state."""
    if action == Action.MODIFY_VALUE:
        return _render_modify_value_action(
            data, key_col, key_value, key_namespace, column, current_value
        )

    if action == Action.REMOVE_VALUE:
        return _render_remove_value_action(
            data, key_col, key_value, key_namespace, column, current_value
        )

    if action == Action.ACCEPT:
        return _render_accept_action(
            data, key_col, key_value, key_namespace, column, current_value, check_type
        )

    if action == Action.REMOVE_ROW:
        return _render_remove_row_action(key_value)

    # Never fall back to a destructive action for an unrecognized value.
    raise ValueError(f"Unsupported correction action: {action!r}")


def render_correction_inputs(
    data: pl.DataFrame,
    key_col: str,
    key_value: str,
    *,
    key_namespace: str | int,
    actions: Sequence[Action] = CORRECTION_ACTIONS,
    column: str | None = None,
    current_value: Any = None,
    check_type: str | None = None,
    survey_id_value: Any = None,
) -> CorrectionFormState:
    """
    Render the action, new-value and reason inputs for one KEY.

    Parameters
    ----------
    data : pl.DataFrame
        The corrected dataset, used for column options, types and lookups.
    key_col : str
        The Survey KEY column name.
    key_value : str
        The KEY the entry applies to.
    key_namespace : str | int
        Suffix for unique widget keys, so several forms can render at once.
    actions : Sequence[Action]
        The actions to offer. May include "accept".
    column : str | None
        A prefilled column. If None, the user picks one when the action
        needs it (except a GPS acceptance, which has no column).
    current_value : Any
        A prefilled current value. If None, it is looked up in `data`. For a
        GPS acceptance, a mapping of the latitude and longitude columns to
        their values.
    check_type : str | None
        The check an "accept" entry accepts. Required if `actions` includes
        "accept".
    survey_id_value : Any
        The Survey ID value for the KEY, recorded with the entry.

    Returns
    -------
    CorrectionFormState
        The collected inputs; `to_entry()` turns them into a CorrectionEntry.
    """
    import streamlit as st

    action = st.selectbox(
        label="Select Action",
        options=actions,
        key=f"correction_action_{key_namespace}",
    )

    state = _render_action_ui(
        action,
        data,
        key_col,
        key_value,
        key_namespace,
        column,
        current_value,
        check_type,
    )

    reason = st.text_input(
        label="Reason for Correction",
        key=f"correction_reason_{key_namespace}",
        placeholder="Enter reason for correction",
    )

    return state.model_copy(
        update={"reason": reason, "survey_id_value": survey_id_value}
    )


def apply_correction_entries(
    correction_processor: CorrectionProcessor,
    alias: str,
    key_col: str,
    entries: Sequence[CorrectionEntry],
    source: str,
) -> bool:
    """
    Apply several entries all-or-nothing and report the outcome.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    alias : str
        The data alias/table name.
    key_col : str
        The Survey KEY column name.
    entries : Sequence[CorrectionEntry]
        The corrections and acceptances to apply, in order.
    source : str
        The page making the entries, recorded in the log.

    Returns
    -------
    bool
        True if every entry was applied; False if none were.
    """
    import streamlit as st

    try:
        correction_processor.apply_corrections(
            alias=alias, key_col=key_col, entries=list(entries), source=source
        )
    except Exception as e:
        # UI boundary: report any failure to the user instead of crashing the page.
        logger.exception(
            "Failed to apply %d correction entries to %s", len(entries), alias
        )
        st.error(f"Error applying correction: {e!s}")
        return False

    st.success(
        "Correction applied successfully!"
        if len(entries) == 1
        else f"{len(entries)} corrections applied successfully!"
    )
    return True


def render_correction_form(
    correction_processor: CorrectionProcessor,
    alias: str,
    key_col: str,
    data: pl.DataFrame,
    key_value: str,
    *,
    key_namespace: str | int,
    source: str,
    actions: Sequence[Action] = CORRECTION_ACTIONS,
    column: str | None = None,
    current_value: Any = None,
    check_type: str | None = None,
    survey_id_value: Any = None,
    on_apply: Callable[[CorrectionFormState], None] | None = None,
) -> None:
    """
    Render the correction inputs for one KEY with an Apply button.

    Parameters are as for `render_correction_inputs`, plus:

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    alias : str
        The data alias/table name.
    source : str
        The page making the entry, recorded in the log.
    on_apply : Callable[[CorrectionFormState], None] | None
        Called with the collected state when Apply is clicked, in place of
        the default save through `apply_correction_entries`.
    """
    import streamlit as st

    state = render_correction_inputs(
        data,
        key_col,
        key_value,
        key_namespace=key_namespace,
        actions=actions,
        column=column,
        current_value=current_value,
        check_type=check_type,
        survey_id_value=survey_id_value,
    )

    apply_enabled = should_enable_apply_button(
        state.action, state.reason, state.new_value
    )

    if not st.button(
        label="Apply",
        key=f"correction_apply_{key_namespace}",
        width="stretch",
        disabled=not apply_enabled or bool(state.validation_error),
        type="primary",
    ):
        return

    if on_apply is not None:
        on_apply(state)
    elif apply_correction_entries(
        correction_processor, alias, key_col, [state.to_entry()], source
    ):
        st.rerun()
