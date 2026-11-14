"""Plain-text README generation for Stata replication packages."""

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
    """Generate a plain-text README for the Stata replication package.

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
        the reviewer in a with-PII export).
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
        Plain-text README content as a string.
    """
    today = date.today().isoformat()
    safe_survey = survey_name.lower().replace(" ", "_")
    safe_project = project_name.lower().replace(" ", "_")

    sep = "=" * 60

    pii_masked_columns = pii_masked_columns or []
    pii_hashed_columns = pii_hashed_columns or []
    pii_coded_columns = pii_coded_columns or []
    pii_dropped_columns = pii_dropped_columns or []
    pii_kept_columns = pii_kept_columns or []

    def _fmt_cols(columns: list[str]) -> str:
        return ", ".join(columns) if columns else "none"

    indirect_warning = [
        "WARNING (indirect identifiers): de-identification is not",
        "anonymization. Even with direct identifiers masked or dropped,",
        "subjects may remain identifiable through combinations of the",
        "remaining variables (e.g. age, location, occupation, household",
        "composition). Review the data before sharing it further.",
    ]
    if include_pii:
        pii_section = [
            sep,
            "PII & DE-IDENTIFICATION",
            sep,
            "",
            "This package was exported WITH personally identifiable",
            "information (PII). Store it only in encrypted,",
            "access-controlled locations, in line with your organization's",
            "data-security policy.",
            "",
            "PII decisions recorded in DataSure (not applied to this export):",
            f"- Columns to be masked: {_fmt_cols(pii_masked_columns)}",
            f"- Columns to be hashed (salted pseudonyms): {_fmt_cols(pii_hashed_columns)}",
            f"- Columns to be recoded (category codes): {_fmt_cols(pii_coded_columns)}",
            f"- Columns to be dropped: {_fmt_cols(pii_dropped_columns)}",
            f"- Flagged but kept by reviewer decision: {_fmt_cols(pii_kept_columns)}",
            "",
            "The full flag audit trail is in 4_output/3_logs/pii_flags.csv.",
            "",
            *indirect_warning,
            "",
        ]
    else:
        pii_section = [
            sep,
            "PII & DE-IDENTIFICATION",
            sep,
            "",
            "This package was exported de-identified. Columns flagged in",
            "DataSure's PII review were masked or dropped in every bundled",
            "dataset, the codebook, and the correction log before export.",
            "",
            f"- Masked columns: {_fmt_cols(pii_masked_columns)}",
            "- Hashed columns (salted pseudonyms; deterministic, so",
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
        f"{project_name} — Replication Package",
        sep,
        "",
        f"Survey:       {survey_name}",
        f"Generated by: DataSure {datasure_version}",
        f"Date:         {today}",
        "Language:     Stata",
        "",
        sep,
        "OVERVIEW",
        sep,
        "",
        "This replication package contains the raw survey dataset, all data",
        "preparation and correction do-files, and audit logs. Running the",
        "master script will reproduce the prepped and corrected datasets",
        "from the raw source and generate the variable codebook.",
        "",
        *pii_section,
        sep,
        "FOLDER STRUCTURE",
        sep,
        "",
        f"replication_{safe_project}_{safe_survey}/",
        "├── 0_README.txt",
        "├── 1_docs/",
        survey_line,
        "    ├── 2_codebooks/        # Variable codebook (generated by scripts)",
        "    └── 3_notes/",
        "├── 2_scripts/",
        "│   ├── 0_main.do           # Entry point — run this",
        "│   ├── 1_install_packages.do",
        "│   ├── 2_import_data.do",
        "│   ├── 3_prepare_data.do",
        "│   └── 4_corrections.do",
        "├── 3_data/",
        f"│   ├── 1_raw/              # {safe_survey}_raw.csv and .dta",
        f"│   ├── 2_intermediate/     # {safe_survey}_prepped.dta (generated)",
        f"│   └── 3_final/            # {safe_survey}_corrected.dta (generated)",
        "└── 4_output/",
        "    ├── 1_tables/",
        "    ├── 2_figures/",
        "    └── 3_logs/             # <date>/ run logs, correction_log.csv, prep_log.csv",
        "",
        sep,
        "HOW TO RUN",
        sep,
        "",
        "1. Open 2_scripts/0_main.do.",
        "2. Update the `global root` path near the top of the file:",
        '      global root "C:/path/to/parent/folder"',
        "3. Run from the Stata command window:",
        "      do 0_main.do",
        "   The master script installs required packages on first run and",
        "   writes a full run log to 4_output/3_logs/<date>/0_main.log.",
        "4. Datasets will appear in 3_data/2_intermediate/ and 3_data/3_final/.",
        "5. The codebook (codebook.xlsx) will appear in 1_docs/2_codebooks/.",
        "",
        sep,
        "DATA PIPELINE SUMMARY",
        sep,
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
        f"| {'Action':<28} | {'Count':>5} |",
        f"|{'-' * 30}|{'-' * 7}|",
        action_rows,
        "",
        sep,
        "FILE REFERENCE",
        sep,
        "",
        f"| {'File':<45} | {'Description':<40} |",
        f"|{'-' * 47}|{'-' * 42}|",
        f"| {'3_data/1_raw/' + safe_survey + '_raw.csv':<45} | {'Original unmodified dataset':<40} |",
        f"| {'2_scripts/0_main.do':<45} | {'Master script — start here':<40} |",
        f"| {'2_scripts/1_install_packages.do':<45} | {'Installs required Stata packages':<40} |",
        f"| {'2_scripts/2_import_data.do':<45} | {'Imports CSV and saves as DTA':<40} |",
        f"| {'2_scripts/3_prepare_data.do':<45} | {'Data preparation steps':<40} |",
        f"| {'2_scripts/4_corrections.do':<45} | {'All data corrections':<40} |",
        *(
            [
                f"| {'4_output/3_logs/pii_flags.csv':<45} | {'PII review flag audit trail':<40} |"
            ]
            if include_pii
            else []
        ),
        f"| {'3_data/2_intermediate/' + safe_survey + '_prepped.dta':<45} | {'Dataset after prep steps (generated)':<40} |",
        f"| {'3_data/3_final/' + safe_survey + '_corrected.dta':<45} | {'Final corrected dataset (generated)':<40} |",
        f"| {'1_docs/2_codebooks/codebook.xlsx':<45} | {'Variable codebook (generated)':<40} |",
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
