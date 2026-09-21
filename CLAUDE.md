# CLAUDE.md

Navigation for agents working in this repository. **DataSure** is IPA's
Streamlit application for data quality monitoring and high-frequency checks on
survey data. Everything below is a pointer: read the linked file rather than
relying on a summary here, and update the linked file (not this one) when
behavior changes.

## Where things are documented

| Topic | Source of truth |
| --- | --- |
| What the app does, installation, cache locations | [README.md](README.md) |
| Package layout, data flow, storage, session state, generated views | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Dev setup, code quality, error handling, view UI rules, testing, releases | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Every available command | `just --list` and the [Justfile](Justfile) |
| Test/coverage/lint configuration | [pyproject.toml](pyproject.toml), [.pre-commit-config.yaml](.pre-commit-config.yaml) |
| End-user workflow | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| Changelog and release-notes style | [docs/changelog_guide.md](docs/changelog_guide.md), [docs/release_notes_guide.md](docs/release_notes_guide.md) |
| Planned work | [ROADMAP.md](ROADMAP.md) |

## Rules for agents

**Use the documented `just` recipes.** Do not invent ad-hoc `ruff`, `pytest`,
`uv build`, or version-bump invocations when a recipe exists. Run `just --list`
to see them all. In particular:

- Lint with `just lint-py`, format with `just fmt-python`, and run both plus
  everything else CI runs with `just pre-commit-run`. `just lint-py` alone is
  not enough — CI enforces formatting too.
- Test with `just test` (or `just test-cov` / `just test-cov-xml`). Use
  `uv run python -m pytest <path>` only for narrowing to a single file or
  pattern.
- Format Markdown with `just fmt-markdown`.
- Never bump the version by editing `pyproject.toml`; use `just bump-patch` /
  `bump-minor` / `bump-major`.

**Always open pull requests with the repository template.** Use
[`.github/pull_request_template.md`](.github/pull_request_template.md), fill in
every section, and complete the checklist. Write "N/A" for sections that do not
apply rather than deleting them. With the `gh` CLI, pass the template
explicitly (for example `gh pr create --body-file <filled-in template>`); do not
write a freeform PR body.

**Do not commit generated files.** `src/datasure/views/output_view_?.py` is
generated at runtime and gitignored — edit `views/output_view_template.py`
instead. The `cache/` and `archived/` directories are also gitignored.

**Never write credentials to disk, logs, or session state.** SurveyCTO
passwords live in the OS keyring via `utils/secure_credentials.py`.

**Keep the docs single-sourced.** When a change makes a document stale, fix the
document that owns the topic per the table above instead of duplicating the new
detail here.
