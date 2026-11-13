"""Time Summary's check health rows, per check, with and without changes.

Used by the `just bench-health` recipe. Builds the demo survey and backcheck
data (``src/datasure/assets/demo_*.csv``) and a generated form of
``--rows`` submissions (50,000 by default) made from the demo rows, sets up
every check on them in a throwaway cache directory, and times each
catalogue check's headline and its change (its delta) over each comparison
period, outside Summary's cache:

- one column per period: the delta from the headline just computed, as
  Summary computes it, reusing the headline's basis
  (``CheckHeadline.basis``).
- ``alone s``: the slowest period's delta from a headline without its basis,
  which computes the check's flags again.

It then times Summary's rows end to end (``health_rows``) on an empty cache,
without deltas and with each period's, and reports the delta overhead: the
time with deltas less the time without. A check whose delta, or a period
whose overhead, is over ``DELTA_BUDGET_SECONDS`` is flagged "over": such a
delta should only be computed on request (issue #399).

Run ``uv run python scripts/benchmark_check_health.py [--rows N] [--repeat N]``.
"""

import argparse
import os
import random
import statistics
import sys
import tempfile
import time
import warnings
from dataclasses import replace
from datetime import date
from pathlib import Path

import polars as pl

ASSETS = Path(__file__).parent.parent / "src" / "datasure" / "assets"
PROJECT_ID = "benchhealth"
PAGE = "bench"
ALIAS = "demo_survey"
# The delta budget of issue #399: a slower delta is computed on request.
DELTA_BUDGET_SECONDS = 1.0

OUTLIER_COLUMNS = ["age", "household_count", "duration", "age_mem1", "age_mem2"]
BACKCHECK_COLUMNS = ["age", "household_count", "eng_farm", "tap", "toilet"]


def _with_dates(data: pl.DataFrame) -> pl.DataFrame:
    """Parse the demo generator's date text, as importing the data does."""
    return data.with_columns(
        pl.col(column).str.to_datetime(strict=False)
        for column in ("starttime", "endtime", "submissiondate")
    )


def _demo_frames() -> tuple[pl.DataFrame, pl.DataFrame]:
    from datasure.utils.onboarding_utils import DemoDataGenerator

    survey = pl.read_csv(
        ASSETS / "demo_survey.csv", truncate_ragged_lines=True, ignore_errors=True
    )
    backcheck = pl.read_csv(
        ASSETS / "demo_backcheck.csv", truncate_ragged_lines=True, ignore_errors=True
    )
    survey = DemoDataGenerator(survey).add_demo_fields()
    backcheck = DemoDataGenerator(backcheck).add_demo_fields(
        "backcheck", survey_df=survey
    )
    return _with_dates(survey), _with_dates(backcheck)


def _generated_frames(
    survey: pl.DataFrame, backcheck: pl.DataFrame, rows: int
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Repeat the demo rows to `rows` submissions with distinct KEYs and IDs.

    Coordinates are jittered and dates spread over the last 60 days by the
    demo generator. The backcheck data repeats the demo backchecks against
    the copies of the surveyed households, about 10% of them.
    """
    from datasure.utils.onboarding_utils import DemoDataGenerator

    copies = -(-rows // survey.height)
    copy = pl.int_range(pl.len()) // survey.height
    big = (
        pl.concat([survey] * copies)
        .head(rows)
        .with_columns(
            pl.format("{}-{}", pl.col("KEY"), copy).alias("KEY"),
            pl.format("{}-{}", pl.col("hhid"), copy).alias("hhid"),
            pl.col("household_latitude")
            + pl.Series([random.gauss(0, 0.01) for _ in range(rows)]),
            pl.col("household_longitude")
            + pl.Series([random.gauss(0, 0.01) for _ in range(rows)]),
        )
    )
    big = DemoDataGenerator(big.drop("starttime", "endtime", "submissiondate"))
    big = _with_dates(big.add_demo_fields())
    bc_copies = max(rows // 10 // backcheck.height, 1)
    bc_copy = pl.int_range(pl.len()) // backcheck.height
    big_backcheck = pl.concat([backcheck] * bc_copies).with_columns(
        pl.format("{}-{}", pl.col("KEY"), bc_copy).alias("KEY"),
        pl.format("{}-{}", pl.col("hhid"), bc_copy).alias("hhid"),
    )
    return big, big_backcheck


def _config(root: Path):
    from datasure.checks.context import PageConfig

    settings = root / "settings.json"
    settings.write_text("{}")
    return PageConfig(
        page_number=1,
        page_name="Bench",
        page_name_id=PAGE,
        survey_data_name=ALIAS,
        survey_key="KEY",
        survey_id="hhid",
        survey_date="submissiondate",
        enumerator="enum_name",
        team="team_id",
        formversion=None,
        duration="duration",
        survey_target=None,
        backcheck_data_name="demo_backcheck",
        backcheck_date="submissiondate",
        backchecker="bcer_name",
        backchecker_team="team_id",
        backcheck_target_percent=10,
        tracking_data_name=None,
        setting_file=settings,
        missing_setting_file=root / "missing.json",
    )


def _set_up_checks(survey: pl.DataFrame) -> list[str]:
    """Save the outlier, GPS and backcheck columns, and correct ten ages.

    Returns the KEYs whose age was corrected to 30.
    """
    from datasure.processing.correction_log import Action
    from datasure.processing.corrections import CorrectionEntry, CorrectionProcessor
    from datasure.utils.duckdb_utils import duckdb_save_table

    count = len(OUTLIER_COLUMNS)
    duckdb_save_table(
        PROJECT_ID,
        pl.DataFrame(
            {
                "search_type": ["exact"] * count,
                "pattern": [None] * count,
                "column_name": [[column] for column in OUTLIER_COLUMNS],
                "grouped_columns": [False] * count,
                "locked": [False] * count,
                "outlier_enabled": [True] * count,
                "outlier_method": ["Interquartile Range (IQR)"] * count,
                "outlier_multiplier": [1.5] * count,
                "outlier_threshold": [3] * count,
                "hard_min": [None] * count,
                "soft_min": [0.0] * count,
                "soft_max": [60.0] * count,
                "hard_max": [None] * count,
            },
            schema_overrides={"pattern": pl.String, "hard_min": pl.Float64},
        ),
        f"outliers_{PAGE}",
        "logs",
    )
    duckdb_save_table(
        PROJECT_ID,
        pl.DataFrame(
            {
                "alias": ["home"],
                "format_type": ["Separate Columns"],
                "delimiter": [None],
                "gps_column": [None],
                "latitude_column": ["household_latitude"],
                "longitude_column": ["household_longitude"],
                "altitude_column": [None],
                "accuracy_column": [None],
            },
            schema_overrides={
                "delimiter": pl.String,
                "gps_column": pl.String,
                "altitude_column": pl.String,
                "accuracy_column": pl.String,
            },
        ),
        f"gps_columns_{PAGE}",
        "logs",
    )
    count = len(BACKCHECK_COLUMNS)
    duckdb_save_table(
        PROJECT_ID,
        pl.DataFrame(
            {
                "search_type": ["exact"] * count,
                "pattern": BACKCHECK_COLUMNS,
                "column_name": [[column] for column in BACKCHECK_COLUMNS],
                "category": [1] * count,
                "ok_range_type": [None] * count,
                "ok_range_values": [None] * count,
                "ttest": [False] * count,
                "prtest": [False] * count,
                "signrank": [False] * count,
                "reliability": [False] * count,
            },
            schema_overrides={
                "ok_range_type": pl.String,
                "ok_range_values": pl.List(pl.Float64),
            },
        ),
        f"backchecks_{PAGE}",
        "logs",
    )
    # The prep data corrections apply to, with ten corrected ages.
    duckdb_save_table(PROJECT_ID, survey, ALIAS, "prep")
    aged = survey.filter(pl.col("age").is_not_null()).head(10)
    CorrectionProcessor(PROJECT_ID).apply_corrections(
        ALIAS,
        "KEY",
        [
            CorrectionEntry(
                key,
                Action.MODIFY_VALUE,
                "benchmark",
                column="age",
                current_value=age,
                new_value=30,
            )
            for key, age in aged.select("KEY", "age").iter_rows()
        ],
    )
    return aged["KEY"].to_list()


def _seconds(compute, repeat: int) -> float:
    times = []
    for _ in range(repeat):
        start = time.perf_counter()
        compute()
        times.append(time.perf_counter() - start)
    return statistics.median(times)


def _time_checks(name: str, survey: pl.DataFrame, backcheck: pl.DataFrame, repeat):
    home = Path.cwd()
    # DuckDB may still hold its files open when the directory is removed.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        # The cache directory is cwd/cache wherever a pyproject.toml is.
        (root / "pyproject.toml").write_text("")
        for folder in ("settings", "data"):
            (root / "cache" / PROJECT_ID / folder).mkdir(parents=True)
        os.chdir(root)
        try:
            _time_in_cache(name, survey, backcheck, repeat, root)
        finally:
            os.chdir(home)


def _time_in_cache(name, survey, backcheck, repeat, root: Path) -> None:
    import streamlit as st

    from datasure.checks.catalogue import CHECK_CATALOGUE, nav_items
    from datasure.checks.context import CheckContext, CheckData
    from datasure.checks.health import clear_headline_cache, health_rows
    from datasure.checks.health_deltas import comparison_window
    from datasure.checks.health_period import ComparisonPeriod
    from datasure.utils.dataframe_utils import get_df_columns
    from datasure.utils.navigation import CheckStatus

    # The correction log and corrected data are cached by project.
    st.cache_data.clear()
    corrected = _set_up_checks(survey)
    # The page data is the corrected data, with its types as loaded.
    data = survey.with_columns(
        pl.when(pl.col("KEY").is_in(corrected))
        .then(pl.lit(30, dtype=survey.schema["age"]))
        .otherwise(pl.col("age"))
        .alias("age")
    )
    ctx = CheckContext(
        PROJECT_ID, _config(root), CheckData(data, backcheck), get_df_columns(data)
    )
    today = date.today()
    windows = {
        period: comparison_window(ctx, period, today) for period in ComparisonPeriod
    }
    print(f"\n{name}: {data.height:,} submissions, {backcheck.height:,} backchecks")
    periods = "".join(f"{period.value + ' s':>10}" for period in windows)
    print(f"{'check':<24}{'headline s':>12}{periods}{'alone s':>10}{'over':>6}")
    for entry in CHECK_CATALOGUE:
        if entry.headline is None:
            continue
        status = entry.status(ctx).status
        if status is not CheckStatus.READY:
            print(f"{entry.label:<24}{status.value:>12}")
            continue
        headline_s = _seconds(lambda e=entry: e.headline(ctx), repeat)
        now = entry.headline(ctx)
        if entry.delta is None or now is None:
            print(f"{entry.label:<24}{headline_s:>12.3f}")
            continue
        delta_s = {
            period: _seconds(lambda e=entry, n=now, w=w: e.delta(ctx, n, w), repeat)
            for period, w in windows.items()
        }
        slowest = max(delta_s, key=delta_s.get)
        bare = replace(now, basis=None)
        alone_s = _seconds(
            lambda e=entry, b=bare, w=windows[slowest]: e.delta(ctx, b, w), repeat
        )
        over = "yes" if max(delta_s.values()) > DELTA_BUDGET_SECONDS else ""
        times = "".join(f"{seconds:>10.3f}" for seconds in delta_s.values())
        print(f"{entry.label:<24}{headline_s:>12.3f}{times}{alone_s:>10.3f}{over:>6}")

    # Summary's rows end to end, on an empty cache, as on a first load.
    items = [item for item in nav_items(ctx) if item.slug != "summary"]
    headlines = {e.slug: e.headline for e in CHECK_CATALOGUE if e.headline}
    views = {e.slug: e.headline_view for e in CHECK_CATALOGUE if e.headline_view}

    def rows(with_window) -> None:
        clear_headline_cache()
        health_rows(
            ctx,
            items,
            headlines,
            deltas={e.slug: e.delta for e in CHECK_CATALOGUE if e.delta},
            window=with_window,
            view_keys=views,
        )

    without = _seconds(lambda: rows(None), repeat)
    print(f"\n{'health_rows':<24}{'total s':>12}{'overhead s':>12}{'over':>6}")
    print(f"{'no deltas':<24}{without:>12.3f}")
    for period, w in windows.items():
        total = _seconds(lambda w=w: rows(w), repeat)
        overhead = total - without
        over = "yes" if overhead > DELTA_BUDGET_SECONDS else ""
        print(f"{period.value + ' deltas':<24}{total:>12.3f}{overhead:>12.3f}{over:>6}")


def main() -> int:
    """Time the health rows on the demo data and on a generated form."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, default=50_000)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    # Streamlit caches warn without a running app.
    warnings.filterwarnings("ignore")
    from streamlit.logger import set_log_level

    set_log_level("error")
    random.seed(399)
    survey, backcheck = _demo_frames()
    _time_checks("Demo data", survey, backcheck, args.repeat)
    big, big_backcheck = _generated_frames(survey, backcheck, args.rows)
    _time_checks("Generated form", big, big_backcheck, args.repeat)
    return 0


if __name__ == "__main__":
    sys.exit(main())
