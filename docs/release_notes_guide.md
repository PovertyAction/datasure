# Release Notes Guide for Developers

This document provides guidance for maintaining the user-facing release notes (RELEASENOTES.md) for DataSure. Release notes communicate changes and improvements to end users in accessible, non-technical language.

**Note**: This guide is for RELEASENOTES.md, which is separate from CHANGELOG.md. Release notes focus on user benefits and features, while the changelog contains technical implementation details for developers.

---

## Purpose and Audience

### Release Notes (RELEASENOTES.md)

- **Audience**: End users, data managers, survey coordinators, research teams
- **Content**: New features, user-visible improvements, usage instructions, benefits
- **Style**: User-friendly language, focuses on value and impact to data quality workflows

### Technical Changelog (CHANGELOG.md)

- **Audience**: Developers, contributors, maintainers
- **Content**: Technical implementation details, API changes, dependency updates
- **Style**: Detailed technical language with code references

---

## Writing User-Focused Release Notes

### Key Principles

1. **User Benefits First**: Explain how changes improve the user's data quality workflow
2. **Plain Language**: Avoid technical jargon, use terms familiar to survey data managers
3. **Visual Impact**: Describe UI changes and new visualizations clearly
4. **Workflow Context**: Explain how features fit into existing data management processes
5. **Action-Oriented**: Tell users what they can now do that they couldn't before

### Language Guidelines

**Use familiar data management terms:**

- "Survey data quality checks" instead of "data validation algorithms"
- "Export reports" instead of "data serialization"
- "Import from SurveyCTO" instead of "API integration"
- "GPS coordinate validation" instead of "geospatial data processing"

**Focus on outcomes:**

- "Identify duplicate survey responses faster" instead of "improved duplicate detection performance"
- "Visualize outliers with interactive charts" instead of "added Plotly visualization components"
- "Configure check thresholds per project" instead of "implemented configurable parameters"

---

## Release Notes Structure

### Version Header Format

```markdown
## Version X.Y.Z - Release Name
*Released: Month DD, YYYY*

[Brief 1-2 sentence summary of the release's main focus]
```

### Standard Sections

#### New Features

Highlight major new capabilities that improve data quality workflows:

```markdown
### New Features

#### GPS Coordinate Validation
- **Interactive Maps**: View survey locations on interactive maps with outlier highlighting
- **Distance-Based Checks**: Configure maximum distances between consecutive survey points
- **Batch Validation**: Process multiple datasets simultaneously for GPS quality checks

#### Enhanced Duplicate Detection  
- **Smart Matching**: Improved algorithm identifies near-duplicates across different question responses
- **Visual Comparison**: Side-by-side view of potential duplicate entries for easy verification
- **Bulk Actions**: Mark multiple duplicates for removal or correction in one step
```

#### Improvements

Focus on enhanced existing features and workflow optimizations:

```markdown
### Improvements

#### Data Import Experience
- **Faster Processing**: Large CSV files now import 60% faster with progress indicators
- **Better Error Messages**: Clear guidance when import fails with specific troubleshooting steps
- **Auto-Detection**: Automatically detect column types and suggest appropriate data quality checks

#### Report Generation
- **New Export Formats**: Generate reports in PDF, Excel, and PowerPoint formats
- **Custom Branding**: Add your organization logo and styling to exported reports
- **Scheduled Reports**: Set up automatic weekly or monthly report generation
```

#### Bug Fixes

Describe fixes in terms of improved user experience:

```markdown
### Bug Fixes

#### Resolved Issues
- **Fixed**: Survey import now handles special characters in enumerator names correctly
- **Fixed**: Settings are now properly saved between application sessions  
- **Fixed**: Missing data percentage calculations now display accurate results for all check types
- **Fixed**: Application no longer crashes when processing very large datasets (>100MB)
```

---

## DataSure-Specific Content Guidelines

### Feature Categories

**Data Quality Checks:**

- Summary statistics and progress monitoring
- Missing data patterns and completeness analysis
- Duplicate response identification and management
- GPS coordinate validation and mapping
- Statistical outlier detection across variables
- Enumerator performance and productivity analysis
- Survey progress tracking and completion rates
- Descriptive statistics and data distributions
- Back-check workflow management and verification

**Data Management:**

- Multi-source data import (SurveyCTO, CSV, Excel)
- Project-based organization and settings
- Data preparation and cleaning workflows
- Configuration management for different projects
- Cache management and performance optimization

**Reporting and Visualization:**

- Interactive charts and dashboards
- Export capabilities for different audiences
- Custom report generation
- Performance metrics and KPI tracking

### User Workflow Context

Frame features within common data management workflows:

```markdown
### Survey Data Collection Workflow
**New Project Setup**: Create projects with pre-configured quality check thresholds based on survey type (household, individual, GPS-based, etc.)

**Daily Monitoring**: Automated daily reports highlight data quality issues requiring immediate attention from field teams

**Weekly Review**: Generate comprehensive quality reports for research coordinators with trend analysis and recommendations
```

### Installation and Setup Instructions

Provide clear instructions for different user types:

```markdown
### Getting Started

#### For Data Managers (Recommended)
1. Install from PyPI: `pip install DataSure`
2. Launch the application: `datasure`
3. Create your first project and import survey data
4. Configure quality checks based on your survey requirements

#### For Windows Users
1. Download the installer from [GitHub Releases](link)
2. Run the installer and follow setup wizard
3. Launch DataSure from Start Menu or desktop shortcut

#### For Advanced Users
- Install development version: `pip install datasure[dev]`
- Command-line usage: `datasure --help`
```

---

## Version Communication Strategy

### Major Releases (X.0.0)

- **Announcement**: Highlight transformative new capabilities
- **Migration Guide**: Help users transition from previous versions
- **Training Materials**: Link to updated documentation and tutorials

### Minor Releases (0.X.0)

- **Feature Focus**: Emphasize new functionality and workflow improvements
- **Compatibility**: Reassure users about backward compatibility
- **Integration**: Explain how new features work with existing workflows

### Patch Releases (0.0.X)

- **Reliability**: Focus on improved stability and performance
- **Quick Fixes**: Address urgent user-reported issues
- **Maintenance**: Routine updates and dependency improvements

### Pre-releases (Alpha/Beta/RC)

- **Testing Invitation**: Encourage user feedback and testing
- **Feature Preview**: Give users early look at upcoming capabilities
- **Feedback Channels**: Provide clear ways to report issues and suggestions

---

## Examples from DataSure Context

### Good User-Focused Examples

```markdown
### New Features

#### Enhanced Enumerator Performance Analysis
Monitor your data collection team's productivity with new performance dashboards. Identify enumerators who may need additional training or support based on survey completion times, data quality metrics, and response patterns.

**What you can do now:**
- View individual enumerator statistics and trends
- Compare performance across different survey modules
- Generate performance reports for team meetings
- Set alerts for unusual completion patterns

#### Improved SurveyCTO Integration  
Connect directly to your SurveyCTO server with enhanced security and faster data synchronization. New authentication options support both individual and institutional accounts.

**Benefits:**
- 70% faster form metadata loading
- Automatic form updates when surveys are modified
- Secure token-based authentication
- Support for complex form structures and calculations
```

### Avoid Technical Details

```markdown
<!-- Don't write this -->
### Technical Updates
- Migrated from pandas to polars for DataFrame operations
- Implemented OAuth2 authentication flow in scto.py connector
- Refactored session state management in app.py lines 156-234
- Updated pyproject.toml dependencies to latest versions

<!-- Write this instead -->
### Performance Improvements
- **Faster Data Processing**: Large survey datasets now load and process up to 50% faster
- **Enhanced Security**: Improved login system with better protection for your SurveyCTO credentials  
- **Smoother Navigation**: Reduced loading times when switching between different project views
- **Updated Components**: Latest versions of underlying software for better reliability
```

---

## Release Timeline and Coordination

### Pre-Release Process

1. **Feature Freeze**: All new features implemented and tested
2. **User Documentation**: Update help text and tutorials
3. **Release Notes Draft**: Create user-focused content based on technical changelog
4. **Review Process**: Technical review + user experience review
5. **Final Edit**: Polish language and ensure clarity

### Release Day

1. **Version Publication**: Automated release through GitHub Actions
2. **Release Notes Publication**: Update RELEASENOTES.md with final content
3. **Communication**: Notify users through appropriate channels
4. **Support Preparation**: Ensure support team knows about changes

### Post-Release

1. **User Feedback**: Monitor for questions and issues
2. **Documentation Updates**: Address any gaps in user guidance
3. **Next Release Planning**: Begin planning based on user feedback

---

## Quality Checklist

Before publishing release notes, verify:

- [ ] **User Language**: No technical jargon or code references
- [ ] **Clear Benefits**: Each feature explains user value
- [ ] **Workflow Context**: Features described within data management workflows  
- [ ] **Visual Descriptions**: UI changes and new visualizations clearly explained
- [ ] **Installation Instructions**: Up-to-date setup guidance for different user types
- [ ] **Compatibility Notes**: Clear guidance on version compatibility
- [ ] **Contact Information**: Current support channels and documentation links
- [ ] **Cross-Reference**: Consistency with technical changelog content

---

## Support Integration

### Help Documentation Links

Always include links to relevant help sections:

- Getting Started guides for new features
- Updated workflow documentation
- Video tutorials for complex new capabilities
- FAQ updates for common questions

### User Communication Channels

- GitHub Issues for bug reports and feature requests
- Email support for installation and usage questions
- Documentation site for comprehensive guides
- Community forums for user discussions

This guide ensures release notes effectively communicate DataSure improvements to end users while maintaining clear separation from technical changelog content.
