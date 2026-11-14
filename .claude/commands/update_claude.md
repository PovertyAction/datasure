---
allowed-tools: Bash(git diff:*), Bash(git log:*), Bash(git status:*), Bash(find:*), Bash(grep:*), Bash(wc:*), Bash(ls:*)
description: Route recent code changes into the documentation file that owns each topic
---

# Update project documentation after recent changes

## Current CLAUDE.md

@CLAUDE.md

## Recent changes

### Repository status

!`git status --porcelain`

### Recent commits

!`git log --oneline -10`

### Files changed recently

!`git diff --name-status HEAD~10`

### Source diff

!`git diff HEAD~5 -- "src/**/*.py" "tests/**/*.py" "Justfile" "pyproject.toml" | head -300`

## Your task

**CLAUDE.md is a navigation file, not a knowledge base.** It is deliberately
short: a table pointing at the document that owns each topic, plus a handful of
rules for agents. Your job is to route the changes above into the *owning*
document. In most runs, CLAUDE.md itself should not change at all.

### Step 1: Decide which document owns each change

| If the change affects... | Update this file |
| --- | --- |
| User-facing behavior, installation, cache locations | `README.md` |
| Package layout, data flow, storage, session state, generated views, credentials | `docs/ARCHITECTURE.md` |
| Dev setup, lint/format rules, error handling, view UI rules, testing, releases | `CONTRIBUTING.md` |
| Available commands | `Justfile` (the recipe *is* the documentation) |
| Lint/test/coverage configuration | `pyproject.toml`, `.pre-commit-config.yaml` |
| End-user workflow steps | `docs/USER_GUIDE.md` |
| Notable changes for a release | `CHANGELOG.md` / `RELEASENOTES.md` (follow `docs/changelog_guide.md` and `docs/release_notes_guide.md`) |

### Step 2: Check CLAUDE.md for drift, not for content

Only change CLAUDE.md when one of these is true:

- A pointer is broken — a linked file was renamed, moved, or deleted
- A whole topic gained or lost an owning document, so the table needs a row
  added or removed
- A rule for agents is now wrong (for example, a `just` recipe named in the
  rules was renamed)

### Step 3: Do not add these to CLAUDE.md

Adding any of the following is a regression — put it in the owning document
instead and link to it:

- Command listings or code fences showing `just`, `uv`, `pytest`, or `ruff`
  invocations — `just --list` and the Justfile are the source of truth
- Directory trees or file-by-file inventories of `src/` or `tests/`
- Architecture prose, data flow descriptions, or design rationale
- Setup, installation, or release instructions
- Coverage thresholds, marker lists, fixture lists, or other config values
  copied out of `pyproject.toml`
- A "Recent Updates" / changelog section — that is what `CHANGELOG.md` is for
- Version numbers, dependency versions, or module counts

### Step 4: Report

List, per file, what you changed and why. If CLAUDE.md needed no change, say
so explicitly — that is the expected outcome.
