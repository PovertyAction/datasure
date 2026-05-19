# DataSure Roadmap

This document outlines the current development status and planned features for DataSure. It reflects our commitment to continuously improving data quality monitoring for survey research.

For feature requests and bug reports, see our [GitHub Issues](https://github.com/PovertyAction/datasure/issues).

## Status Legend

| Status | Description |
| ------ | ----------- |
| **Launched** | Available in the current release |
| **In Development** | Actively being built |
| **Planned** | Committed to a future release |
| **Exploring** | Under consideration; scope not yet defined |

---

## Current Release

### Data Quality Check Modules

| Feature | Description | Status |
| ------- | ----------- | ------ |
| **Summary** | Overall project progress and completion tracking | Launched |
| **Missing Data** | Identify and analyze patterns in incomplete responses | Launched |
| **Duplicates** | Detect and manage duplicate survey entries | Launched |
| **GPS Validation** | Verify location data accuracy with interactive maps | Launched |
| **Outliers** | Statistical identification of unusual responses | Launched |
| **Enumerator Performance** | Monitor data collection team productivity and quality metrics | Launched |
| **Progress Tracking** | Real-time survey completion monitoring | Launched |
| **Descriptive Statistics** | Per-column summaries, histograms, and value counts | Launched |
| **Back-checks** | Verification workflow support for back-check surveys | Launched |

### Core Platform

| Feature | Description | Status |
| ------- | ----------- | ------ |
| **SurveyCTO Integration** | Direct API connection with authentication and form metadata | Launched |
| **Local File Support** | CSV, Excel, Stata (.dta), and JSON upload | Launched |
| **Multi-Project Management** | Manage multiple surveys with isolated settings and data | Launched |
| **Data Preparation Workflows** | Built-in cleaning and transformation tools | Launched |
| **Data Correction Interface** | Review and apply corrections to flagged records in-app | Launched |
| **DuckDB Backend** | High-performance analytical query engine | Launched |
| **Cross-Platform Support** | Windows, macOS, and Linux compatibility | Launched |
| **Package Distribution** | Available via PyPI (`uv tool install datasure`) | Launched |
| **Replication Package Export** | Bundle and export full analysis packages | Launched |

---

## Near-Term (Q2-Q3 2026)

Features currently in development or planned for the next release cycle.

### Other Specify Check ([#155](https://github.com/PovertyAction/datasure/issues/155))

**Status:** In Development

A dedicated tab for reviewing and recoding open-ended "other specify" responses.

- Fuzzy matching to identify responses that should be recoded to existing categories
- Side-by-side pair configuration for original and recoded values
- Frequency analysis of open-ended responses
- Bulk recode workflow with review and approval step

### Enumerator Response Pattern Checks ([#158](https://github.com/PovertyAction/datasure/issues/158))

**Status:** Planned

Three additional sub-checks within the Enumerator Performance module to detect systematic response biases.

| Sub-Check | Description |
| --------- | ----------- |
| **Digit Preference** | Detect over-representation of specific digits (e.g., rounding to 0 or 5) in numeric responses |
| **Range Compression** | Identify enumerators who consistently avoid extreme scale values |
| **Categorical Response Patterns** | Flag enumerators with statistically unusual distributions across categorical choices |

### Balance Test ([#156](https://github.com/PovertyAction/datasure/issues/156))

**Status:** Planned

A dedicated tab for verifying randomization integrity in experimental studies.

- Treatment arm configuration with flexible grouping
- Statistical tests: t-test, ANOVA, chi-square, and regression-based balance checks
- Balance table with standardized mean differences
- P-value distribution chart across all tested variables
- Export-ready summary for pre-analysis plans

---

## Future Considerations

Features under exploration for future releases. These are not yet committed to the roadmap.

| Feature | Description | Status |
| ------- | ----------- | ------ |
| **Consent and Refusal Rates** | Track and flag unusual refusal or incomplete interview rates by enumerator | Exploring |
| **Time-to-Complete Analysis** | Identify implausibly short or long interview durations | Exploring |
| **Longitudinal Tracking** | Compare data quality metrics across survey rounds | Exploring |
| **Automated Correction Suggestions** | ML-assisted flagging and correction recommendations | Exploring |
| **Report Export** | Generate printable PDF or Word summary reports for project managers | Exploring |
| **Audit Trail** | Log all corrections with timestamps and reviewer attribution | Exploring |
| **API Mode** | Programmatic access to check results for integration with other tools | Exploring |

---

## How to Influence the Roadmap

- **Request a feature**: [Open an issue](https://github.com/PovertyAction/datasure/issues/new) on GitHub with the `enhancement` label
- **Vote on priorities**: Upvote existing issues to signal demand
- **Contribute**: See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute code or documentation
- **Contact the team**: Reach out at <researchsupport@poverty-action.org>

---

**DataSure** - Ensuring data quality for better research outcomes.
