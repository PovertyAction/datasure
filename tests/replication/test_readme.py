"""Tests for replication package README generator."""

from __future__ import annotations

import pytest

from datasure.replication.readme import generate_readme


@pytest.fixture()
def readme():
    return generate_readme(
        project_name="Test Project",
        survey_name="Baseline Survey",
        datasure_version="1.2.3",
        correction_count=5,
        prep_count=3,
        raw_rows=100,
        prepped_rows=98,
        corrected_rows=97,
        n_corrections_by_action={"modify value": 4, "remove row": 1},
        include_scto_form=False,
    )


class TestGenerateReadme:
    def test_returns_string(self, readme):
        assert isinstance(readme, str)

    def test_ends_with_newline(self, readme):
        assert readme.endswith("\n")

    def test_contains_project_name(self, readme):
        assert "Test Project" in readme

    def test_contains_survey_name(self, readme):
        assert "Baseline Survey" in readme

    def test_contains_datasure_version(self, readme):
        assert "DataSure 1.2.3" in readme

    def test_contains_row_counts(self, readme):
        assert "100" in readme
        assert "98" in readme
        assert "97" in readme

    def test_contains_prep_count(self, readme):
        assert "3" in readme

    def test_contains_correction_count(self, readme):
        assert "5" in readme

    def test_contains_action_table_rows(self, readme):
        assert "modify value" in readme
        assert "remove row" in readme

    def test_no_scto_form_line_when_not_included(self, readme):
        assert "questionnaire.xlsx" not in readme

    def test_scto_form_line_when_included(self):
        result = generate_readme(
            project_name="P",
            survey_name="S",
            datasure_version="1.0",
            correction_count=0,
            prep_count=0,
            raw_rows=10,
            prepped_rows=10,
            corrected_rows=10,
            n_corrections_by_action={},
            include_scto_form=True,
        )
        assert "questionnaire.xlsx" in result

    def test_empty_corrections_by_action_shows_dash(self):
        result = generate_readme(
            project_name="P",
            survey_name="S",
            datasure_version="1.0",
            correction_count=0,
            prep_count=0,
            raw_rows=0,
            prepped_rows=0,
            corrected_rows=0,
            n_corrections_by_action={},
        )
        assert "| —" in result
        assert "0 |" in result

    def test_safe_survey_name_used_in_paths(self, readme):
        assert "baseline_survey" in readme

    def test_safe_project_name_used_in_paths(self, readme):
        assert "test_project" in readme

    def test_contains_folder_structure_block(self, readme):
        assert "├── 1_docs/" in readme
        assert "├── 2_scripts/" in readme
        assert "├── 3_data/" in readme
        assert "└── 4_output/" in readme

    def test_contains_how_to_run_section(self, readme):
        assert "How to Run" in readme

    def test_contains_data_pipeline_summary(self, readme):
        assert "Data Pipeline Summary" in readme

    def test_mentions_data_dict_yaml(self, readme):
        assert "data-dict.yaml" in readme

    def test_mentions_parquet(self, readme):
        assert ".parquet" in readme

    def test_mentions_python_scripts(self, readme):
        assert "0_main.py" in readme
        assert "2_import_data.py" in readme
        assert "3_prepare_data.py" in readme
        assert "4_corrections.py" in readme

    def test_contains_python_how_to_run_section(self, readme):
        assert "How to Run (Python" in readme

    def test_is_markdown_with_h1_title(self, readme):
        assert readme.startswith("# ")

    def test_folder_tree_is_fenced(self, readme):
        assert "```text" in readme
        assert readme.count("```") >= 2
