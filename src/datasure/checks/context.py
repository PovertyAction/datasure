"""Page configuration and data shared by every check on a check page."""

from dataclasses import dataclass
from pathlib import Path

import polars as pl

from datasure.models.schemas import ColumnByType
from datasure.utils.dataframe_utils import TableState, get_table_state


@dataclass
class PageConfig:
    """Configuration data for an output page."""

    page_number: int
    page_name: str
    page_name_id: str
    survey_data_name: str
    survey_key: str
    survey_id: str | None
    survey_date: str | None
    enumerator: str | None
    team: str | None
    formversion: str | None
    duration: str | None
    survey_target: int | None
    backcheck_data_name: str | None
    backcheck_date: str | None
    backchecker: str | None
    backchecker_team: str | None
    backcheck_target_percent: int | None
    tracking_data_name: str | None
    setting_file: Path
    missing_setting_file: Path


@dataclass
class CheckData:
    """Data required for running checks."""

    page_data: pl.DataFrame
    # None when the page has no backcheck dataset. Otherwise kept as loaded,
    # even with no rows, so the Backchecks check can say why it is empty.
    backcheck_data: pl.DataFrame | None = None

    @property
    def backcheck_state(self) -> TableState:
        """The state of the backcheck table; MISSING when none is configured."""
        if self.backcheck_data is None:
            return TableState.MISSING
        return get_table_state(self.backcheck_data)

    @property
    def backcheck_data_with_rows(self) -> pl.DataFrame | None:
        """The backcheck data for check modules, or None when it has no rows."""
        if self.backcheck_state is TableState.HAS_ROWS:
            return self.backcheck_data
        return None


@dataclass(frozen=True)
class CheckContext:
    """Everything a check needs to report its status or render.

    Attributes
    ----------
    project_id : str
        The project identifier.
    config : PageConfig
        The check page's configuration.
    data : CheckData
        The survey data and backcheck data loaded for the page.
    survey_columns : ColumnByType
        The survey data's columns by type.
    """

    project_id: str
    config: PageConfig
    data: CheckData
    survey_columns: ColumnByType
