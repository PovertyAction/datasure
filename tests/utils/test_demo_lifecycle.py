"""Tests for restarting and exiting the demo (#357)."""

import json
import shutil

import duckdb
import polars as pl
import pytest
import streamlit as st

from datasure.utils.cache_utils import get_cache_path
from datasure.utils.demo_lifecycle import exit_demo, reset_demo_project
from datasure.utils.duckdb_utils import duckdb_save_table, missing_codes_table_name
from datasure.utils.navigations_utils import DEMO_CELEBRATED_KEY
from datasure.utils.onboarding_utils import DEMO_PROJECT_ID, get_onboarding_step
from datasure.utils.settings_utils import page_settings_file


class _SessionState(dict):
    """Session state stand-in with dict and attribute access."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e

    def __setattr__(self, name, value):
        self[name] = value


@pytest.fixture
def session_state(monkeypatch):
    """Replace st.session_state with a plain dict-backed object."""
    state = _SessionState()
    monkeypatch.setattr(st, "session_state", state)
    return state


@pytest.fixture
def demo_cache(tmp_path, monkeypatch):
    """Point the DataSure cache at an empty temporary directory."""
    (tmp_path / "pyproject.toml").write_text("")
    monkeypatch.chdir(tmp_path)
    return tmp_path / "cache" / DEMO_PROJECT_ID


def _snapshot(project_dir):
    """Return the files under the demo project and the tables in each database."""
    files = sorted(
        p.relative_to(project_dir).as_posix()
        for p in project_dir.rglob("*")
        if p.is_file()
    )
    tables = {}
    for db_file in project_dir.rglob("*.duckdb"):
        with duckdb.connect(str(db_file), read_only=True) as conn:
            tables[db_file.name] = sorted(
                r[0] for r in conn.execute("SHOW TABLES").fetchall()
            )
    return files, tables


def _use_demo(page_name="Household HFCs"):
    """Leave behind what a user creates while working through the demo."""
    log = pl.DataFrame({"KEY": ["uuid:1"], "action": ["modify value"]})
    duckdb_save_table(DEMO_PROJECT_ID, log, "corr_log_demo_survey", "logs")
    duckdb_save_table(DEMO_PROJECT_ID, log, "corr_log_demo_backcheck", "logs")
    config = pl.DataFrame({"page_name": [page_name]})
    duckdb_save_table(DEMO_PROJECT_ID, config, "check_config", "logs")
    duckdb_save_table(DEMO_PROJECT_ID, config, "backchecks_household_hfcs", "logs")
    duckdb_save_table(DEMO_PROJECT_ID, config, "outliers_household_hfcs", "logs")
    duckdb_save_table(
        DEMO_PROJECT_ID, config, missing_codes_table_name(DEMO_PROJECT_ID), "logs"
    )
    duckdb_save_table(DEMO_PROJECT_ID, log, "demo_survey", "corrected")
    settings = page_settings_file(DEMO_PROJECT_ID, page_name)
    settings.write_text(json.dumps({"summary": {"target": 10}}))
    (get_cache_path(DEMO_PROJECT_ID, "settings") / "stray.json").write_text("{}")


class TestResetDemoProject:
    """Restart deletes everything under cache/demoproject/ and reloads."""

    def test_restart_leaves_only_freshly_loaded_demo_data(
        self, demo_cache, session_state
    ):
        assert reset_demo_project()
        fresh = _snapshot(demo_cache)

        _use_demo()
        assert _snapshot(demo_cache) != fresh

        assert reset_demo_project()

        assert _snapshot(demo_cache) == fresh
        assert not page_settings_file(DEMO_PROJECT_ID, "Household HFCs").exists()

    def test_fresh_load_has_demo_data_and_no_user_work(self, demo_cache, session_state):
        assert reset_demo_project()

        files, tables = _snapshot(demo_cache)
        assert {"demo_survey", "demo_backcheck"} <= set(tables["raw.duckdb"])
        logs = set(tables["logs.duckdb"])
        assert not {t for t in logs if t.startswith("corr_log_")}
        assert "check_config" not in logs
        assert not [f for f in files if f.endswith(".json")]

    def test_restart_registers_demo_project_and_activates_it(
        self, demo_cache, session_state
    ):
        session_state["st_project_id"] = DEMO_PROJECT_ID
        session_state["onboarding_step"] = 6

        assert reset_demo_project()

        projects = json.loads(get_cache_path("projects.json").read_text())
        assert DEMO_PROJECT_ID in projects
        assert session_state["st_project_id"] == DEMO_PROJECT_ID
        assert get_onboarding_step() == 2

    def test_restart_forgets_demo_session_state(self, demo_cache, session_state):
        session_state["st_project_id"] = DEMO_PROJECT_ID
        session_state["st_prep_dataset_list"] = ["demo_survey"]
        session_state[f"check_nav_household_hfcs__{DEMO_PROJECT_ID}__selected"] = "x"
        session_state[DEMO_CELEBRATED_KEY] = True

        assert reset_demo_project()

        assert "st_prep_dataset_list" not in session_state
        assert DEMO_CELEBRATED_KEY not in session_state
        assert not [k for k in session_state if DEMO_PROJECT_ID in k]

    def test_restart_forgets_demo_keys_that_look_like_another_project(
        self, demo_cache, session_state
    ):
        """A demo page name ending in 8 hex digits is not kept as another project's."""
        page_key = f"check_nav_hfc___20251026__{DEMO_PROJECT_ID}"
        session_state[f"{page_key}__selected"] = "x"
        session_state[page_key] = "y"

        assert reset_demo_project()

        assert not [k for k in session_state if DEMO_PROJECT_ID in k]

    def test_failed_delete_leaves_and_unregisters_demo(
        self, demo_cache, session_state, monkeypatch
    ):
        """A partly deleted demo is not offered for Resume."""
        assert reset_demo_project()
        session_state["st_prep_dataset_list"] = ["demo_survey"]

        def locked(path, *args, **kwargs):
            raise PermissionError("file is in use")

        monkeypatch.setattr(shutil, "rmtree", locked)

        assert not reset_demo_project()

        projects = json.loads(get_cache_path("projects.json").read_text())
        assert DEMO_PROJECT_ID not in projects
        assert session_state["st_project_id"] == ""
        assert "onboarding_step" not in session_state
        assert "st_prep_dataset_list" not in session_state

    def test_failed_load_leaves_and_unregisters_demo(
        self, demo_cache, session_state, monkeypatch
    ):
        monkeypatch.setattr(
            "datasure.utils.demo_lifecycle.load_demo_data", lambda: False
        )

        assert not reset_demo_project()

        projects = json.loads(get_cache_path("projects.json").read_text())
        assert DEMO_PROJECT_ID not in projects
        assert session_state["st_project_id"] == ""


class TestExitDemo:
    """Exit Demo clears every piece of demo session state."""

    def test_exit_clears_demo_session_state(self, session_state):
        start_page = object()
        session_state.update(
            {
                "st_project_id": DEMO_PROJECT_ID,
                "onboarding_step": 4,
                "st_raw_dataset_list": ["demo_survey", "demo_backcheck"],
                "st_prep_dataset_list": ["demo_survey"],
                "st_output_pages": [object()],
                "st_output_page1": object(),
                "st_corr_page": object(),
                "st_replication_page": object(),
                f"corrections_nav__{DEMO_PROJECT_ID}__selected": "household_hfcs",
                DEMO_CELEBRATED_KEY: True,
                "st_start_page": start_page,
            }
        )

        exit_demo()

        assert session_state["st_project_id"] == ""
        for key in (
            "onboarding_step",
            "st_raw_dataset_list",
            "st_prep_dataset_list",
            DEMO_CELEBRATED_KEY,
        ):
            assert key not in session_state
        assert session_state["st_output_pages"] == []
        assert session_state["st_output_page1"] is None
        assert session_state["st_corr_page"] is None
        assert session_state["st_replication_page"] is None
        assert not [k for k in session_state if DEMO_PROJECT_ID in k]
        assert session_state["st_start_page"] is start_page

    def test_exit_keeps_other_projects_state(self, session_state):
        session_state.update(
            {
                "st_project_id": DEMO_PROJECT_ID,
                "prep_nav__a1b2c3d4__selected": "survey",
            }
        )

        exit_demo()

        assert session_state["prep_nav__a1b2c3d4__selected"] == "survey"

    def test_exit_keeps_app_wide_state(self, session_state):
        session_state.update(
            {
                "st_project_id": DEMO_PROJECT_ID,
                "reviewer_name_input": "Ama",
                "st_queued_notices": {"start_demo": []},
            }
        )

        exit_demo()

        assert session_state["reviewer_name_input"] == "Ama"
        assert session_state["st_queued_notices"] == {"start_demo": []}

    def test_project_opened_after_exit_sees_no_demo_state(
        self, demo_cache, session_state
    ):
        """No demo datasets or replication package carry over to the next project."""
        assert reset_demo_project()
        # What working through the demo leaves in session state.
        session_state.update(
            {
                "_replication_build_settings": ("demo_survey",),
                "_replication_zip": b"PK demo package",
                "_replication_filename": "datasure_demo_replication.zip",
                "_replication_exclude_reviewer_names": True,
                "_replication_pii_confirmed": True,
                "refresh_import_log": True,
                "imported_data_select": "demo_survey",
                "iddup_demo_survey_sort": "hhid",
            }
        )

        exit_demo()
        session_state["st_project_id"] = "a1b2c3d4"  # open a real project

        leftover = {
            k: v
            for k, v in session_state.items()
            if "demo" in str(k) or "demo" in repr(v)
        }
        assert leftover == {}
        assert "st_raw_dataset_list" not in session_state
        assert "_replication_zip" not in session_state
