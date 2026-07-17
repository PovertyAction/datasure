"""Validate generated data-dict.yaml files with the external `data-dict` CLI.

This is an optional integration test: the CLI (https://github.com/tidyverse/
data-dict) is a Rust tool, not part of DataSure's Python/uv toolchain, and is
not installed in CI. The whole module is skipped when the `data-dict` binary
isn't on PATH. See CONTRIBUTING.md for install instructions (rustup + cargo
install).
"""

from __future__ import annotations

import datetime
import shutil
import subprocess

import polars as pl
import pytest

from datasure.replication.data_dict import generate_data_dict

pytestmark = pytest.mark.skipif(
    shutil.which("data-dict") is None,
    reason="data-dict CLI not installed (see CONTRIBUTING.md)",
)


@pytest.fixture()
def package_dir(tmp_path):
    """Build a miniature package layout: a data-dict.yaml next to the Parquet
    file it describes, at the same relative offset package_builder.py uses
    (1_docs/2_codebooks/data-dict.yaml -> ../../3_data/3_final/*.parquet).
    """
    docs_dir = tmp_path / "1_docs" / "2_codebooks"
    docs_dir.mkdir(parents=True)
    data_dir = tmp_path / "3_data" / "3_final"
    data_dir.mkdir(parents=True)

    df = pl.DataFrame(
        {
            "key": ["k1", "k2", "k3", "k4"],
            "age": [25, 30, 40, 65],
            "category": ["a", "b", "a", "b"],
            "joined": [
                datetime.date(2020, 1, 15),
                datetime.date(2019, 3, 22),
                datetime.date(2021, 7, 1),
                datetime.date(2018, 11, 30),
            ],
            "active": [True, False, True, True],
        }
    )
    df.write_parquet(data_dir / "baseline_corrected.parquet")

    yaml_text = generate_data_dict(
        df,
        table_name="baseline",
        label="Baseline Survey",
        description="Test dataset for data-dict CLI validation.",
        key_col="key",
        parquet_path="../../3_data/3_final/baseline_corrected.parquet",
        datasure_version="1.0.0",
    )
    yaml_path = docs_dir / "data-dict.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")
    return yaml_path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["data-dict", *args], capture_output=True, text=True, check=False
    )


class TestValidateSpec:
    def test_passes(self, package_dir):
        result = _run("validate-spec", str(package_dir))
        assert result.returncode == 0, result.stdout + result.stderr


class TestValidateMeta:
    def test_passes(self, package_dir):
        result = _run("validate-meta", str(package_dir))
        assert result.returncode == 0, result.stdout + result.stderr


class TestValidateData:
    def test_passes(self, package_dir):
        result = _run("validate-data", str(package_dir))
        assert result.returncode == 0, result.stdout + result.stderr
