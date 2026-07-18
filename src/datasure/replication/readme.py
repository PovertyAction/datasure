"""Markdown README generation for replication packages."""

from __future__ import annotations

from datetime import date


def generate_readme(
    project_name: str,
    survey_name: str,
    datasure_version: str,
    correction_count: int,
    prep_count: int,
    raw_rows: int,
    prepped_rows: int,
    corrected_rows: int,
    n_corrections_by_action: dict[str, int],
    include_scto_form: bool = False,
    include_pii: bool = True,
    pii_masked_columns: list[str] | None = None,
    pii_hashed_columns: list[str] | None = None,
    pii_coded_columns: list[str] | None = None,
    pii_dropped_columns: list[str] | None = None,
    pii_kept_columns: list[str] | None = None,
) -> str:
    """Generate a Markdown README for the replication package.

    Parameters
    ----------
    project_name : str
        Human-readable project name.
    survey_name : str
        Human-readable survey name.
    datasure_version : str
        Version of DataSure that generated this package.
    correction_count : int
        Total number of correction log entries.
    prep_count : int
        Total number of preparation steps recorded.
    raw_rows : int
        Row count of the raw dataset.
    prepped_rows : int
        Row count of the prepped dataset.
    corrected_rows : int
        Row count of the corrected dataset.
    n_corrections_by_action : dict[str, int]
        Count of corrections keyed by action type.
    include_scto_form : bool
        Whether the SurveyCTO XLS questionnaire was included in the package.
    include_pii : bool
        Whether the package was exported with PII (True) or de-identified
        (False).
    pii_masked_columns : list[str] | None
        Columns masked in a de-identified export (or slated for masking by
        ``5_deidentify_data.py`` in a with-PII export).
    pii_hashed_columns : list[str] | None
        Columns replaced with salted hash pseudonyms (deterministic tokens
        that preserve categorical structure).
    pii_coded_columns : list[str] | None
        Columns recoded with sequential category codes.
    pii_dropped_columns : list[str] | None
        Columns dropped in a de-identified export (or slated for dropping).
    pii_kept_columns : list[str] | None
        Columns flagged in the PII review but kept by reviewer decision.

    Returns
    -------
    str
        Markdown README content as a string.
    """
    today = date.today().isoformat()
    safe_survey = survey_name.lower().replace(" ", "_")
    safe_project = project_name.lower().replace(" ", "_")

    pii_masked_columns = pii_masked_columns or []
    pii_hashed_columns = pii_hashed_columns or []
    pii_coded_columns = pii_coded_columns or []
    pii_dropped_columns = pii_dropped_columns or []
    pii_kept_columns = pii_kept_columns or []

    def _fmt_cols(columns: list[str]) -> str:
        return ", ".join(f"`{c}`" for c in columns) if columns else "none"

    indirect_warning = [
        "> **Warning — indirect identifiers.** De-identification is not",
        "> anonymization: even with direct identifiers masked or dropped,",
        "> subjects may remain identifiable through combinations of the",
        "> remaining variables (e.g. age, location, occupation, household",
        "> composition). Review the data before sharing it further.",
    ]
    if include_pii:
        pii_section = [
            "## PII & De-identification",
            "",
            "**This package was exported WITH personally identifiable",
            "information (PII).** Store it only in encrypted,",
            "access-controlled locations, in line with your organization's",
            "data-security policy.",
            "",
            "The PII decisions recorded in DataSure are encoded in",
            "`2_scripts/5_deidentify_data.py`. Run it to produce",
            "de-identified copies of every bundled dataset",
            "(`*_deidentified.parquet`):",
            "",
            "```",
            "uv run 5_deidentify_data.py",
            "```",
            "",
            f"- Columns to be masked: {_fmt_cols(pii_masked_columns)}",
            f"- Columns to be hashed (salted pseudonyms): {_fmt_cols(pii_hashed_columns)}",
            f"- Columns to be recoded (category codes): {_fmt_cols(pii_coded_columns)}",
            f"- Columns to be dropped: {_fmt_cols(pii_dropped_columns)}",
            f"- Flagged but kept by reviewer decision: {_fmt_cols(pii_kept_columns)}",
            "",
            "The full flag audit trail is in `4_output/3_logs/pii_flags.csv`.",
            "",
            *indirect_warning,
            "",
        ]
    else:
        pii_section = [
            "## PII & De-identification",
            "",
            "**This package was exported de-identified.** Columns flagged in",
            "DataSure's PII review were masked or dropped in every bundled",
            "dataset, the codebook, the data dictionary, and the correction",
            "log before export.",
            "",
            f"- Masked columns: {_fmt_cols(pii_masked_columns)}",
            "- Hashed columns (salted pseudonyms — deterministic, so",
            f"  group-bys/joins/frequencies still work): {_fmt_cols(pii_hashed_columns)}",
            f"- Recoded columns (category codes): {_fmt_cols(pii_coded_columns)}",
            f"- Dropped columns: {_fmt_cols(pii_dropped_columns)}",
            f"- Flagged but kept by reviewer decision: {_fmt_cols(pii_kept_columns)}",
            "",
            *indirect_warning,
            "",
        ]

    if n_corrections_by_action:
        action_rows = "\n".join(
            f"| {action:<28} | {count:>5} |"
            for action, count in sorted(n_corrections_by_action.items())
        )
    else:
        action_rows = "| —                            |     0 |"

    survey_line = (
        f"    ├── 1_surveys/{safe_survey}_questionnaire.xlsx"
        if include_scto_form
        else "    ├── 1_surveys/"
    )

    lines = [
        f"# {project_name} — Replication Package",
        "",
        f"- **Survey:** {survey_name}",
        f"- **Generated by:** DataSure {datasure_version}",
        f"- **Date:** {today}",
        "- **Language:** Stata and Python (uv, no Stata required)",
        "",
        "## Overview",
        "",
        "This replication package contains the raw survey dataset, all data",
        "preparation and correction scripts (Stata do-files and equivalent",
        "Python/Polars scripts), and audit logs. Running the master script —",
        "in either language — reproduces the prepped and corrected datasets",
        "from the raw source. A pre-generated codebook and a data-dict.yaml",
        "data dictionary are also included, along with Parquet copies of the",
        "raw/prepped/corrected datasets so the package is usable without Stata.",
        "",
        *pii_section,
        "## Folder Structure",
        "",
        "```text",
        f"replication_{safe_project}_{safe_survey}/",
        "├── README.md",
        "├── 1_docs/",
        survey_line,
        "    ├── 2_codebooks/        # codebook.csv, data-dict.yaml (pre-generated);",
        "    │                       # codebook.xlsx (generated by the do-files)",
        "    └── 3_notes/",
        "├── 2_scripts/",
        "│   ├── 0_main.do / .py     # Entry point — run this",
        "│   ├── 1_install_packages.do",
        "│   ├── 2_import_data.do      # Stata only — imports raw CSV as DTA",
        "│   ├── 3_prepare_data.do / .py",
        *(
            [
                "│   ├── 4_corrections.do / .py",
                "│   └── 5_deidentify_data.py  # De-identify bundled datasets",
            ]
            if include_pii
            else ["│   └── 4_corrections.do / .py"]
        ),
        "├── 3_data/",
        f"│   ├── 1_raw/              # {safe_survey}_raw.csv/.parquet (pre-generated);",
        "│   │                       # .dta (generated by the do-files)",
        f"│   ├── 2_intermediate/     # {safe_survey}_prepped.parquet (pre-generated);",
        "│   │                       # .dta (generated by the do-files)",
        f"│   └── 3_final/            # {safe_survey}_corrected.parquet (pre-generated);",
        "│                           # .dta (generated by the do-files)",
        "└── 4_output/",
        "    ├── 1_tables/",
        "    ├── 2_figures/",
        "    └── 3_logs/             # <date>/ run logs, correction_log.csv, prep_log.csv",
        "```",
        "",
        "## How to Run (Stata)",
        "",
        "1. Open `2_scripts/0_main.do`.",
        "2. Update the `global root` path near the top of the file:",
        "   ```",
        '   global root "C:/path/to/parent/folder"',
        "   ```",
        "3. Run from the Stata command window:",
        "   ```",
        "   do 0_main.do",
        "   ```",
        "   The master script installs required packages on first run and",
        "   writes a full run log to `4_output/3_logs/<date>/0_main.log`.",
        "4. Datasets will appear in `3_data/2_intermediate/` and `3_data/3_final/`.",
        "5. The codebook (`codebook.xlsx`) will appear in `1_docs/2_codebooks/`.",
        "",
        "## How to Run (Python, no Stata required)",
        "",
        "Requires [uv](https://docs.astral.sh/uv/). No manual path configuration",
        "and no separate package-install step: each script locates the package",
        "root relative to its own file, and `uv run` reads the dependencies",
        "declared at the top of the script and provisions them automatically.",
        "",
        "1. From `2_scripts/`, run:",
        "   ```",
        "   uv run 0_main.py",
        "   ```",
        "   This runs the prepare and corrections steps in order. There is no",
        "   Python import step: the raw dataset is already bundled as a",
        "   Parquet file with the correct types, so `3_prepare_data.py` reads",
        "   it directly.",
        "2. Any step can also be run on its own, e.g.:",
        "   ```",
        "   uv run 4_corrections.py",
        "   ```",
        "3. Datasets will appear in `3_data/2_intermediate/` and `3_data/3_final/`",
        "   as `.parquet` files (Parquet copies of these are also included",
        "   pre-generated — see File Reference below).",
        "",
        "## Data Pipeline Summary",
        "",
        f"| {'Metric':<28} | {'Value':>7} |",
        f"|{'-' * 30}|{'-' * 9}|",
        f"| {'Raw dataset rows':<28} | {raw_rows:>7,} |",
        f"| {'Preparation steps applied':<28} | {prep_count:>7,} |",
        f"| {'Prepped dataset rows':<28} | {prepped_rows:>7,} |",
        f"| {'Corrections applied':<28} | {correction_count:>7,} |",
        f"| {'Corrected dataset rows':<28} | {corrected_rows:>7,} |",
        "",
        "Corrections by action type:",
        "",
        f"| {'Action':<28} | {'Count':>5} |",
        f"|{'-' * 30}|{'-' * 7}|",
        action_rows,
        "",
        "## File Reference",
        "",
        f"| {'File':<45} | {'Description':<40} |",
        f"|{'-' * 47}|{'-' * 42}|",
        f"| {'3_data/1_raw/' + safe_survey + '_raw.csv':<45} | {'Original unmodified dataset':<40} |",
        f"| {'3_data/1_raw/' + safe_survey + '_raw.parquet':<45} | {'Same, as Parquet (no Stata needed)':<40} |",
        f"| {'2_scripts/0_main.do':<45} | {'Stata master script — start here':<40} |",
        f"| {'2_scripts/0_main.py':<45} | {'Python master script — start here':<40} |",
        f"| {'2_scripts/1_install_packages.do':<45} | {'Installs required Stata packages':<40} |",
        f"| {'2_scripts/2_import_data.do':<45} | {'Stata only — imports CSV, saves as DTA':<40} |",
        f"| {'2_scripts/3_prepare_data.do':<45} | {'Data preparation steps (Stata)':<40} |",
        f"| {'2_scripts/3_prepare_data.py':<45} | {'Data preparation steps (Python)':<40} |",
        f"| {'2_scripts/4_corrections.do':<45} | {'All data corrections (Stata)':<40} |",
        f"| {'2_scripts/4_corrections.py':<45} | {'All data corrections (Python)':<40} |",
        *(
            [
                f"| {'2_scripts/5_deidentify_data.py':<45} | {'De-identifies bundled datasets':<40} |",
                f"| {'4_output/3_logs/pii_flags.csv':<45} | {'PII review flag audit trail':<40} |",
            ]
            if include_pii
            else []
        ),
        f"| {'3_data/2_intermediate/' + safe_survey + '_prepped.dta':<45} | {'Dataset after prep steps (generated)':<40} |",
        f"| {'3_data/2_intermediate/' + safe_survey + '_prepped.parquet':<45} | {'Same, pre-generated as Parquet':<40} |",
        f"| {'3_data/3_final/' + safe_survey + '_corrected.dta':<45} | {'Final corrected dataset (generated)':<40} |",
        f"| {'3_data/3_final/' + safe_survey + '_corrected.parquet':<45} | {'Same, pre-generated as Parquet':<40} |",
        f"| {'1_docs/2_codebooks/codebook.csv':<45} | {'Variable codebook (pre-generated)':<40} |",
        f"| {'1_docs/2_codebooks/codebook.xlsx':<45} | {'Variable codebook (generated by do-files)':<40} |",
        f"| {'1_docs/2_codebooks/data-dict.yaml':<45} | {'data-dict.yaml data dictionary':<40} |",
        *(
            [
                f"| {'1_docs/1_surveys/' + safe_survey + '_questionnaire.xlsx':<45}"
                f" | {'SurveyCTO XLS form (questionnaire)':<40} |"
            ]
            if include_scto_form
            else []
        ),
        f"| {'4_output/3_logs/correction_log.csv':<45} | {'Full correction audit trail':<40} |",
        f"| {'4_output/3_logs/prep_log.csv':<45} | {'Full preparation audit trail':<40} |",
        f"| {'4_output/3_logs/<date>/0_main.log':<45} | {'Run log (generated by scripts)':<40} |",
    ]

    return "\n".join(lines) + "\n"
