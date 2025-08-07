# DataSure Release Notes

**DataSure** is IPA's Data Management System Dashboard - a comprehensive tool for survey data quality monitoring and high-frequency checks (HFCs) in research projects.

This document tracks user-facing changes and improvements to help data managers, survey coordinators, and research teams understand new features and enhancements in each release.

---

## About This Document

**Purpose**: Communicate new features, improvements, and bug fixes to end users in accessible, non-technical language.

**Audience**: Data managers, survey coordinators, research teams, and field staff using DataSure for survey data quality assurance.

**Related Documentation**:

- **CHANGELOG.md**: Technical implementation details for developers

---

## Current Version

### Version X.Y.Z (Latest)

This version focuses on improving the core application architecture and preparing for enhanced user features in upcoming releases.

#### Improvements

- **Enhanced Stability**: Improved application reliability and error handling
- **Better Performance**: Optimized data processing for faster loading times
- **Updated Dependencies**: Latest versions of underlying components for better security and performance

---

## Getting Started with DataSure

### Installation Options

#### Install with uv

Ensure that you have uv  installed:

#### with winget

```bash
winget install astral-sh.uv
```

#### with homebrew

```bash
brew install uv
```

#### verify uv installation

```bash
uv --version
```

#### Install DataSure

```bash
uv tool install dataSure
```

or

#### Update current version

```bash
uv tool upgrade datasure
```

### Quick Start

1. Launch the application: `datasure`
2. Create your first project
3. Import survey data from SurveyCTO or upload CSV/Excel files
4. Configure data quality checks based on your survey requirements
5. Monitor data quality with interactive dashboards and reports

---

## Core Features

DataSure provides comprehensive survey data quality monitoring through:

### Data Quality Checks

- **Summary Statistics**: Overall project progress and completion tracking
- **Missing Data Analysis**: Identify patterns in incomplete responses
- **Duplicate Detection**: Find and manage duplicate survey entries
- **GPS Validation**: Verify location data accuracy with interactive maps
- **Outlier Detection**: Identify unusual responses requiring review
- **Enumerator Performance**: Monitor data collection team productivity
- **Progress Tracking**: Real-time survey completion monitoring
- **Descriptive Statistics**: Data distribution analysis and summaries
- **Back-check Management**: Verification workflow support

### Data Import and Management

- **SurveyCTO Integration**: Direct connection to your SurveyCTO server
- **Local File Support**: Import CSV and Excel files
- **Multi-Project Organization**: Manage multiple surveys simultaneously
- **Flexible Configuration**: Customize checks per project requirements

### Reporting and Visualization

- **Interactive Dashboards**: Real-time data quality monitoring
- **Export Capabilities**: Generate reports in multiple formats
- **Custom Charts**: Visualize data patterns and quality metrics
- **Automated Alerts**: Notifications for quality issues requiring attention

---

## System Requirements

- **Python**: Version 3.11 or higher
- **Operating System**: Windows, macOS, or Linux
- **Memory**: Minimum 4GB RAM (8GB recommended for large datasets)
- **Storage**: 1GB free space for application and data cache
- **Internet**: Required for SurveyCTO integration and updates

---

## Support and Resources

### Getting Help

- **GitHub Issues**: [Report bugs and request features](https://github.com/PovertyAction/datasure/issues)
- **Email Support**: <researchsupport@poverty-action.org>
- **Documentation**: See project documentation for detailed guides

### Contributing

DataSure is developed by Innovations for Poverty Action (IPA) with contributions from the research community. See CONTRIBUTING.md for development guidelines.

### License

DataSure is released under the MIT License. See LICENSE file for details.

---

## Version History

### Previous Versions

#### Version 0.3.6a1

- Application path resolution improvements
- Enhanced module loading and view handling

---

*This document is maintained alongside the project and updated with each release. For technical details, see CHANGELOG.md.*

**Last Updated**: January 2025  
**Document Version**: 1.0
