from datetime import datetime
from typing import Any

import polars as pl
import streamlit as st

from datasure.utils import duckdb_get_table, duckdb_save_table


class CorrectionProcessor:
    """Handles all data correction operations and persistence."""

    def __init__(self, project_id: str) -> None:
        """Initialize the correction processor.

        Parameters
        ----------
        project_id : str
            The project identifier
        """
        self.project_id = project_id

    @st.cache_data(ttl=60, show_spinner=False)
    def get_corrected_data(_self, alias: str) -> pl.DataFrame:
        """Get corrected data for a given alias.

        If no corrected data exists, initializes from prepped data.

        Parameters
        ----------
        alias : str
            The data alias/table name

        Returns
        -------
        pl.DataFrame
            The corrected data
        """
        corrected_data = duckdb_get_table(
            project_id=_self.project_id,
            alias=alias,
            db_name="corrected",
        )

        if corrected_data.is_empty():
            # Initialize from prepped data
            prepped_data = duckdb_get_table(
                project_id=_self.project_id,
                alias=alias,
                db_name="prep",
            )
            if not prepped_data.is_empty():
                _self.save_corrected_data(alias, prepped_data)
                return prepped_data

        return corrected_data

    def save_corrected_data(self, alias: str, data: pl.DataFrame) -> None:
        """Save corrected data to storage.

        Parameters
        ----------
        alias : str
            The data alias/table name
        data : pl.DataFrame
            The data to save
        """
        duckdb_save_table(
            project_id=self.project_id,
            table_data=data,
            alias=alias,
            db_name="corrected",
        )
        # Clear cache after saving to ensure fresh data
        self.get_corrected_data.clear()
        self.get_data_summary.clear()

    @st.cache_data(ttl=30, show_spinner=False)
    def get_correction_log(_self, alias: str) -> pl.DataFrame:
        """Get correction log for a given alias.

        Parameters
        ----------
        alias : str
            The data alias/table name

        Returns
        -------
        pl.DataFrame
            The correction log
        """
        return duckdb_get_table(
            project_id=_self.project_id,
            alias=f"corr_log_{alias}",
            db_name="logs",
        )

    def add_correction_entry(
        self,
        alias: str,
        key_value: str,
        current_id: str | None,
        action: str,
        column: str | None,
        current_value: Any | None,
        new_value: Any | None,
        reason: str,
    ) -> None:
        """Add a new correction entry to the log.

        Parameters
        ----------
        alias : str
            The data alias/table name
        key_value : str
            The key value being corrected
        current_id : str | None
            The current ID value
        action : str
            The correction action
        column : str | None
            The column being modified
        current_value : Any | None
            The current value
        new_value : Any | None
            The new value
        reason : str
            The reason for correction
        """
        current_log = self.get_correction_log(alias)

        # Create new entry DataFrame with proper schema
        new_entry_data = {
            "date": [datetime.now()],
            "KEY": [str(key_value)],
            "ID": [str(current_id) if current_id is not None else None],
            "action": [str(action)],
            "column": [str(column) if column is not None else None],
            "current_value": [
                str(current_value) if current_value is not None else None
            ],
            "new_value": [str(new_value) if new_value is not None else None],
            "reason": [str(reason)],
        }
        new_entry_df = pl.DataFrame(new_entry_data)

        if current_log.is_empty():
            # If no existing log, use the new entry schema
            updated_log = new_entry_df
        else:
            # Ensure schema compatibility before concatenating
            # Cast columns to match the new entry schema
            aligned_current_log = current_log.with_columns(
                [
                    pl.col("date").cast(pl.Datetime("us")),
                    pl.col("KEY").cast(pl.String),
                    pl.col("ID").cast(pl.String),
                    pl.col("action").cast(pl.String),
                    pl.col("column").cast(pl.String),
                    pl.col("current_value").cast(pl.String),
                    pl.col("new_value").cast(pl.String),
                    pl.col("reason").cast(pl.String),
                ]
            )
            updated_log = pl.concat([aligned_current_log, new_entry_df])

        duckdb_save_table(
            project_id=self.project_id,
            table_data=updated_log,
            alias=f"corr_log_{alias}",
            db_name="logs",
        )

    def apply_correction(
        self,
        alias: str,
        key_col: str,
        key_value: str,
        action: str,
        column: str | None = None,
        current_value: Any | None = None,
        new_value: Any | None = None,
        reason: str | None = None,
    ) -> pl.DataFrame:
        """Apply a single correction to the data.

        Parameters
        ----------
        alias : str
            The data alias/table name
        key_col : str
            The key column name
        key_value : str
            The key value to correct
        action : str
            The correction action ('modify value', 'remove value', 'remove row')
        column : str | None
            The column to modify
        current_value : Any | None
            The current value
        new_value : Any | None
            The new value
        reason : str | None
            The reason for correction

        Returns
        -------
        pl.DataFrame
            The corrected data
        """
        corrected_data = self.get_corrected_data(alias)

        if action == "modify value" and column and new_value is not None:
            corrected_data = self._apply_modify_value(
                corrected_data, key_col, key_value, column, new_value
            )
        elif action == "remove value" and column:
            corrected_data = self._apply_remove_value(
                corrected_data, key_col, key_value, column
            )
        elif action == "remove row":
            corrected_data = self._apply_remove_row(corrected_data, key_col, key_value)

        self.save_corrected_data(alias, corrected_data)

        # Add to correction log if reason is provided
        if reason:
            self.add_correction_entry(
                alias=alias,
                key_value=key_value,
                current_id=None,  # Legacy field, not used in new implementation
                action=action,
                column=column,
                current_value=current_value,
                new_value=new_value,
                reason=reason,
            )

        return corrected_data

    def _apply_modify_value(
        self,
        data: pl.DataFrame,
        key_col: str,
        key_value: str,
        column: str,
        new_value: Any,
    ) -> pl.DataFrame:
        """Apply modify value correction.

        Parameters
        ----------
        data : pl.DataFrame
            The data to modify
        key_col : str
            The key column name
        key_value : str
            The key value to match
        column : str
            The column to modify
        new_value : Any
            The new value

        Returns
        -------
        pl.DataFrame
            The modified data
        """
        if data[column].dtype == pl.String:
            return data.with_columns(
                pl.when(pl.col(key_col) == key_value)
                .then(pl.lit(str(new_value)))
                .otherwise(pl.col(column))
                .alias(column)
            )
        else:
            # Handle type conversion for non-string columns
            try:
                if isinstance(new_value, str):
                    typed_value = pl.lit(new_value).cast(data[column].dtype)
                else:
                    typed_value = pl.lit(new_value)

                return data.with_columns(
                    pl.when(pl.col(key_col) == key_value)
                    .then(typed_value)
                    .otherwise(pl.col(column))
                    .alias(column)
                )
            except Exception:
                # Fallback to string conversion if type casting fails
                return data.with_columns(
                    pl.when(pl.col(key_col) == key_value)
                    .then(pl.lit(str(new_value)))
                    .otherwise(pl.col(column))
                    .alias(column)
                )

    def _apply_remove_value(
        self,
        data: pl.DataFrame,
        key_col: str,
        key_value: str,
        column: str,
    ) -> pl.DataFrame:
        """Apply remove value correction.

        Parameters
        ----------
        data : pl.DataFrame
            The data to modify
        key_col : str
            The key column name
        key_value : str
            The key value to match
        column : str
            The column to modify

        Returns
        -------
        pl.DataFrame
            The modified data
        """
        return data.with_columns(
            pl.when(pl.col(key_col) == key_value)
            .then(None)
            .otherwise(pl.col(column))
            .alias(column)
        )

    def _apply_remove_row(
        self,
        data: pl.DataFrame,
        key_col: str,
        key_value: str,
    ) -> pl.DataFrame:
        """Apply remove row correction.

        Parameters
        ----------
        data : pl.DataFrame
            The data to modify
        key_col : str
            The key column name
        key_value : str
            The key value to match

        Returns
        -------
        pl.DataFrame
            The modified data
        """
        return data.filter(pl.col(key_col) != key_value)

    @st.cache_data(ttl=60, show_spinner=False)
    def get_data_summary(_self, data: pl.DataFrame) -> dict[str, Any]:
        """Get summary statistics for the data.

        Parameters
        ----------
        data : pl.DataFrame
            The data to summarize

        Returns
        -------
        dict[str, Any]
            Summary statistics including row count, column count, and missing percentage
        """
        if data.is_empty():
            return {"rows": 0, "columns": 0, "missing_percentage": 0.0}

        rows, columns = data.shape

        # Calculate missing values percentage
        missing_count = data.select(pl.all().is_null().sum())
        total_missing = missing_count.select(
            pl.sum_horizontal(pl.all()).alias("total")
        )[0, "total"]

        missing_percentage = (
            round((total_missing / (rows * columns)) * 100, 2)
            if rows > 0 and columns > 0
            else 0.0
        )

        return {
            "rows": rows,
            "columns": columns,
            "missing_percentage": missing_percentage,
        }

    def validate_correction_input(
        self,
        data: pl.DataFrame,
        key_col: str,
        key_value: str,
        action: str,
        column: str | None = None,
        new_value: Any | None = None,
    ) -> tuple[bool, str]:
        """Validate correction input parameters.

        Parameters
        ----------
        data : pl.DataFrame
            The data to validate against
        key_col : str
            The key column name
        key_value : str
            The key value
        action : str
            The correction action
        column : str | None
            The column to modify
        new_value : Any | None
            The new value

        Returns
        -------
        tuple[bool, str]
            (is_valid, error_message)
        """
        if key_col not in data.columns:
            return False, f"Key column '{key_col}' not found in data"

        if key_value not in data[key_col].to_list():
            return False, f"Key value '{key_value}' not found in data"

        if action in ["modify value", "remove value"]:
            if not column:
                return False, "Column must be specified for modify/remove value actions"
            if column not in data.columns:
                return False, f"Column '{column}' not found in data"

        if action == "modify value" and new_value is None:
            return False, "New value must be provided for modify value action"

        return True, ""

    def remove_correction_entry(
        self,
        alias: str,
        correction_index: int,
    ) -> None:
        """Remove a correction entry from the log and reapply corrections.

        Parameters
        ----------
        alias : str
            The data alias/table name
        correction_index : int
            The index of the correction entry to remove
        """
        correction_log = self.get_correction_log(alias)

        if correction_log.is_empty():
            raise ValueError("No corrections to remove")

        if correction_index < 0 or correction_index >= correction_log.height:
            raise ValueError(f"Invalid correction index: {correction_index}")

        # Remove the correction entry at the specified index
        if correction_index == 0 and correction_log.height == 1:
            # If removing the only entry, create an empty DataFrame with proper schema
            updated_log = pl.DataFrame(
                {
                    "date": pl.Series([], dtype=pl.Datetime("us")),
                    "KEY": pl.Series([], dtype=pl.String),
                    "ID": pl.Series([], dtype=pl.String),
                    "action": pl.Series([], dtype=pl.String),
                    "column": pl.Series([], dtype=pl.String),
                    "current_value": pl.Series([], dtype=pl.String),
                    "new_value": pl.Series([], dtype=pl.String),
                    "reason": pl.Series([], dtype=pl.String),
                }
            )
        else:
            # Build list of parts to concatenate
            parts = []
            if correction_index > 0:
                parts.append(correction_log[:correction_index])
            if correction_index < len(correction_log) - 1:
                parts.append(correction_log[correction_index + 1 :])

            if parts:
                updated_log = pl.concat(parts)
            else:
                # Should not happen given the conditions above, but handle it
                updated_log = pl.DataFrame(
                    {
                        "date": pl.Series([], dtype=pl.Datetime("us")),
                        "KEY": pl.Series([], dtype=pl.String),
                        "ID": pl.Series([], dtype=pl.String),
                        "action": pl.Series([], dtype=pl.String),
                        "column": pl.Series([], dtype=pl.String),
                        "current_value": pl.Series([], dtype=pl.String),
                        "new_value": pl.Series([], dtype=pl.String),
                        "reason": pl.Series([], dtype=pl.String),
                    }
                )

        # Save the updated log
        duckdb_save_table(
            project_id=self.project_id,
            table_data=updated_log,
            alias=f"corr_log_{alias}",
            db_name="logs",
        )
        # Clear correction log cache
        self.get_correction_log.clear()
        self.get_correction_summary.clear()

        # Reapply all remaining corrections
        self._reapply_all_corrections(alias)

    def _reapply_all_corrections(self, alias: str) -> None:
        """Reapply all corrections from the log to fresh data.

        Parameters
        ----------
        alias : str
            The data alias/table name
        """
        # Get fresh data from prep database
        fresh_data = duckdb_get_table(
            project_id=self.project_id,
            alias=alias,
            db_name="prep",
        )

        if fresh_data.is_empty():
            # If no prep data, nothing to correct
            return

        # Get updated correction log
        correction_log = self.get_correction_log(alias)

        if correction_log.is_empty():
            # No corrections to apply, save fresh data as corrected
            self.save_corrected_data(alias, fresh_data)
            return

        # Apply all corrections in sequence
        corrected_data = fresh_data

        for row in correction_log.iter_rows(named=True):
            action = row["action"]
            key_col = None  # We need to get this from the first non-null column
            key_value = row["KEY"]
            column = row["column"]
            new_value = row["new_value"]

            # Find key column by looking for a column that contains the key value
            for col in corrected_data.columns:
                if key_value in corrected_data[col].to_list():
                    key_col = col
                    break

            if not key_col:
                continue  # Skip if key column not found

            try:
                if action == "modify value" and column and new_value is not None:
                    corrected_data = self._apply_modify_value(
                        corrected_data, key_col, key_value, column, new_value
                    )
                elif action == "remove value" and column:
                    corrected_data = self._apply_remove_value(
                        corrected_data, key_col, key_value, column
                    )
                elif action == "remove row":
                    corrected_data = self._apply_remove_row(
                        corrected_data, key_col, key_value
                    )
            except Exception:
                # Skip corrections that fail (data may have changed)
                continue

        # Save the reapplied corrections
        self.save_corrected_data(alias, corrected_data)

    @st.cache_data(ttl=30, show_spinner=False)
    def get_correction_summary(_self, alias: str) -> list[dict[str, Any]]:
        """Get a summary of all correction entries for display.

        Parameters
        ----------
        alias : str
            The data alias/table name

        Returns
        -------
        list[dict[str, Any]]
            List of correction summaries with index, description, and details
        """
        correction_log = _self.get_correction_log(alias)

        if correction_log.is_empty():
            return []

        summaries = []
        for index, row in enumerate(correction_log.iter_rows(named=True)):
            action = row["action"]
            key_value = row["KEY"]
            column = row["column"]
            new_value = row["new_value"]
            reason = row["reason"]
            date = row["date"]

            # Create description based on action type
            if action == "modify value":
                description = f"Modify {column} for key {key_value} to '{new_value}'"
            elif action == "remove value":
                description = f"Remove {column} value for key {key_value}"
            elif action == "remove row":
                description = f"Remove entire row for key {key_value}"
            else:
                description = f"{action} for key {key_value}"

            summaries.append(
                {
                    "index": index,
                    "action_index": f"{index} - {action} - {description}",
                    "action": action,
                    "description": description,
                    "key_value": key_value,
                    "column": column,
                    "new_value": new_value,
                    "reason": reason,
                    "date": date,
                }
            )

        return summaries
