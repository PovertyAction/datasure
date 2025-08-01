# CHANGELOG.md Guide for Developers

This document provides guidance for maintaining the technical changelog (CHANGELOG.md) for DataSure. The changelog contains detailed technical notes for developers and maintainers.

**Note**: This changelog is separate from RELEASENOTES.md, which contains user-facing release information. The changelog focuses on technical implementation details, while release notes focus on user benefits and features.

---

## Purpose and Audience

### Technical Changelog (CHANGELOG.md)
- **Audience**: Developers, contributors, maintainers
- **Content**: Technical implementation details, API changes, dependency updates, architectural changes
- **Style**: References to specific modules and functions

### Release Notes (RELEASENOTES.md)
- **Audience**: End users, data managers, survey coordinators
- **Content**: New features, user-visible improvements, usage instructions
- **Style**: User-friendly language, focuses on benefits and impact

---

## Changelog Format

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### Standard Template

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- **Module/Component**: Technical description with implementation details
- **API**: New function/class with signature and usage example
- **Dependencies**: New package additions with version constraints

### Changed
- **Breaking**: API changes that require code updates
- **Internal**: Refactoring, performance improvements, architectural changes
- **Dependencies**: Version updates with impact notes

### Deprecated
- **API**: Functions/classes marked for removal with migration path
- **Configuration**: Settings that will be removed with timeline

### Removed
- **API**: Removed functions/classes with migration instructions
- **Dependencies**: Removed packages with alternatives

### Fixed  
- **Bug**: Specific issue with root cause and technical solution
- **Performance**: Optimization details with before/after metrics
- **Security**: Vulnerability fixes with CVE references if applicable

### Security
- **Vulnerability**: Security fixes with severity and impact assessment
- **Dependencies**: Security updates in third-party packages
```

---

## Technical Writing Guidelines

### Implementation Details

Include specific technical information:

```markdown
### Added
- **src/datasure/checks/gpschecks.py**: Added `validate_gps_coordinates()` function with configurable distance thresholds
- **src/datasure/utils/duckdb_utils.py**: Implemented connection pooling with automatic cleanup using contextlib

### Changed
- **Breaking**: Modified `DataFrameProcessor.clean_data()` signature - removed deprecated `inplace` parameter
  - Migration: Use `cleaned_df = processor.clean_data(df)` instead of `processor.clean_data(df, inplace=True)`
- **src/datasure/connectors/scto.py**: Refactored authentication to use OAuth2 flow instead of basic auth
  - Performance improvement: 40% faster form metadata retrieval
  - Backward compatibility maintained through adapter pattern
```

### Dependency and Environment Changes

```markdown
### Changed
- **Dependencies**: Updated streamlit from 1.35.0 to 1.41.1
  - New session state persistence API utilized in `src/datasure/app.py:45-67`
  - Resolves memory leak in multi-page applications (#234)
- **Build**: Migrated from setuptools to uv_build backend
  - 60% faster package builds in CI/CD pipeline
  - Improved handling of data files and assets

### Added
- **Requirements**: Added polars>=0.20.0 for high-performance DataFrame operations
  - Used in `src/datasure/processing/prep.py` for large dataset handling (>100MB)
  - Fallback to pandas maintained for compatibility
```

### Bug Fixes with Technical Context

```markdown
### Fixed
- **src/datasure/checks/duplicates.py:123**: Fixed memory leak in `find_duplicates()` when processing datasets >500MB
  - Root cause: DataFrame copies were not being garbage collected
  - Solution: Implemented chunked processing with explicit `del` statements
  - Performance: Reduced memory usage by 70% for large datasets
- **src/datasure/views/import_view.py:89**: Resolved Unicode handling in CSV import for special characters
  - Issue: UnicodeDecodeError when importing files with non-ASCII enumerator names
  - Fix: Added encoding detection using chardet library with fallback to utf-8-sig
```

---

## DataSure-Specific Examples

### Module-Specific Changes

```markdown
### Added
- **Check Modules**: New `src/datasure/checks/enumerator.py` with performance analysis
  - Functions: `calculate_survey_speed()`, `identify_outlier_enumerators()`, `generate_performance_report()`
  - Integrates with existing session state pattern in `st.session_state.st_enumerator_analysis`
- **Connector Enhancement**: SurveyCTO form caching in `src/datasure/connectors/scto.py`
  - Reduces API calls by 85% through intelligent form metadata caching
  - Cache invalidation based on form modification timestamps

### Changed
- **Views Refactoring**: Consolidated navigation logic from individual view files to `src/datasure/app.py:156-234`
  - Eliminates duplicate session state initialization across 6 view modules
  - Maintains backward compatibility with existing view interfaces
- **Utility Functions**: Modified `src/datasure/utils/chart_utils.py` to use Plotly 6.2.0 new features
  - Updated `create_outlier_boxplot()` to use native outlier detection instead of custom implementation
  - 25% performance improvement in chart generation
```

### Configuration and Settings

```markdown
### Added
- **Cache Management**: New cache directory structure in `src/datasure/utils/cache_utils.py`
  - Development mode: `./cache/` (when pyproject.toml present)
  - Production mode: Platform-specific user data directories
  - Automatic migration from legacy cache locations

### Changed
- **Settings Schema**: Updated JSON configuration schema in `src/datasure/utils/settings_utils.py`
  - Breaking: Renamed `gps_check_threshold` to `gps_outlier_distance_km` for consistency
  - Migration script provided in `scripts/migrate_settings_v2.py`
```

---

## Version Management

### Pre-release Versioning

```markdown
### Alpha Releases (X.Y.Za1)
- **Purpose**: Early development testing, API may change
- **Audience**: Core developers and early adopters
- **Documentation**: Include experimental feature warnings

### Beta Releases (X.Y.Zb1)  
- **Purpose**: Feature-complete testing, stable API
- **Audience**: Extended testing team, integration partners
- **Documentation**: Complete API documentation required

### Release Candidates (X.Y.Zrc1)
- **Purpose**: Final testing before production release
- **Audience**: All stakeholders, production-like testing
- **Documentation**: Final review of all documentation
```

### Breaking Changes

Always include migration instructions:

```markdown
### Changed
- **Breaking**: Removed deprecated `DataConnector.legacy_import()` method (deprecated since v0.2.0)
  - Migration: Use `DataConnector.import_data()` with new parameter structure
  - Support for legacy configurations ends in v0.5.0
```

---

## Integration with Release Process

### During Development
1. Add entries to `## [Unreleased]` section as features are implemented
2. Use technical language and include code references
3. Link to relevant GitHub issues/PRs with technical context

### Before Release
1. Move unreleased changes to new version section
2. Ensure all breaking changes have migration instructions
3. Cross-reference with RELEASENOTES.md for consistency
---

## Quality Standards

### Required Information
- **Module/file references**: Specific paths for all changes
- **Function signatures**: For new/modified APIs
- **Performance metrics**: Before/after measurements where applicable
- **Migration paths**: For all breaking changes
- **Security context**: CVE references, impact assessment

### Code Examples
Include minimal, runnable examples:

```python
# Good: Shows actual usage
from datasure.checks import OutlierDetection
detector = OutlierDetection(method='iqr', threshold=1.5)
outliers = detector.find_outliers(df['survey_duration'])

# Avoid: Too abstract
# Use the new outlier detection API
```

### Cross-References
- Link to relevant RELEASENOTES.md sections
- Reference GitHub issues/PRs with context
- Include links to updated documentation sections

This guide ensures the technical changelog serves as a comprehensive resource for developers while maintaining clear separation from user-facing release notes.