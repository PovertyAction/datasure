# DataSure

**DataSure** is IPA's Data Management System Dashboard - a comprehensive tool for survey data quality monitoring and high-frequency checks (HFCs) in research projects.

Built for data managers, survey coordinators, and research teams, DataSure provides real-time monitoring of survey data quality with interactive dashboards, automated checks, and flexible reporting capabilities.

## Key Features

- **Data Quality Monitoring**: Real-time dashboards for comprehensive survey data analysis
- **Automated Checks**: 9 specialized quality check modules including duplicates, outliers, GPS validation, and missing data analysis
- **Interactive Visualizations**: Charts and maps for data exploration and quality assessment
- **Multi-Source Integration**: Direct SurveyCTO API connection plus local file support (CSV, Excel, Stata, JSON)
- **Flexible Configuration**: Project-based settings with customizable check parameters
- **Data Correction Workflows**: Built-in interface for reviewing and correcting flagged records
- **Enumerator Performance**: Monitor data collection team productivity and quality metrics

## Installation

### Step 1: Install uv from terminal

```bash
# WINDOWS
winget install astral-sh.uv

# MACOS/LINUX
brew install uv
```

### Step 2: Install datasure with uv

```bash
# install
uv tool install datasure

# ON WINDOWS: update windows path after installation
uv tool update-shell
```

### Step 3: Verify installation

```bash
datasure --version
```

## Getting the Latest Release

```bash
# if datasure is already installed, get latest version with
uv tool upgrade datasure
```

## Quick Start

1. **Launch the application**:

   ```bash
   datasure
   ```

2. **Create or open a project** from the Start Here page

3. **Import survey data**:
   - Connect directly to your SurveyCTO server
   - Upload CSV, Excel, Stata (.dta), or JSON files from local storage

4. **Prepare your data** with the built-in cleaning and transformation tools

5. **Configure data quality checks** by selecting your dataset and setting check parameters

6. **Monitor data quality** with interactive DQA Report dashboards organized into specialized check modules

7. **Correct flagged records** using the Correct Data workflow

## System Requirements

- **Python**: Version 3.11 or higher
- **Operating System**: Windows, macOS, or Linux
- **Memory**: Minimum 4GB RAM (8GB recommended for large datasets)
- **Storage**: 1GB free space for application and data cache
- **Internet**: Required for SurveyCTO integration and updates

## Data Quality Check Modules

DataSure includes 9 specialized modules for comprehensive survey data quality monitoring:

| Module | Purpose |
|--------|---------|
| **Summary** | Overall project progress and completion tracking |
| **Missing Data** | Identify patterns in incomplete responses |
| **Duplicates** | Find and manage duplicate survey entries |
| **GPS Validation** | Verify location data accuracy with interactive maps |
| **Outliers** | Identify unusual responses requiring review |
| **Enumerator Performance** | Monitor data collection team productivity |
| **Progress Tracking** | Real-time survey completion monitoring |
| **Descriptive Statistics** | Per-column summary statistics, histograms, and value counts |
| **Back-checks** | Verification workflow support |

## Core Capabilities

### Data Import and Management

- **SurveyCTO Integration**: Direct API connection with form metadata and authentication
- **Local File Support**: CSV, Excel, Stata (.dta), and JSON upload with automatic type detection
- **Multi-Project Organization**: Manage multiple surveys simultaneously
- **Data Preparation**: Cleaning and transformation workflows

### Interactive Dashboards

- **Real-time Monitoring**: Dashboards refresh as new data is imported
- **Customizable Views**: Configure which checks to run and set thresholds per project
- **Column Selector**: Choose specific columns for analysis within each check
- **Data Correction**: Review and apply corrections to flagged records directly in the app

### Performance and Scalability

- **High-Performance Processing**: DuckDB backend for fast analytical queries
- **Large Dataset Support**: Optimized with Polars for datasets with hundreds of thousands of records
- **Intelligent Caching**: Reduces processing time and API calls
- **Cross-Platform Compatibility**: Works on Windows, macOS, and Linux

## Getting Started - Application Workflow

Once DataSure is installed, you can begin monitoring your survey data quality:

### 1. Launch the Application

```bash
datasure
```

The web interface will open in your default browser (typically at `http://localhost:8501`).

### 2. Create or Open a Project

- **Start Here Page**: Create a new project or open an existing one
- Projects are identified by a unique ID and store all settings and cached data

### 3. Import Data

- **Import Data Page**: Connect your data sources
- **SurveyCTO Integration**: Connect to your SurveyCTO server with authentication
- **Local Files**: Upload CSV, Excel (.xlsx/.xls), Stata (.dta), or JSON files
- **Multiple Datasets**: Import and manage up to 10 datasets per project

### 4. Prepare Data

- **Prepare Data Page**: Preview imported datasets in separate tabs
- Review data types, column names, and apply transformations before running checks

### 5. Configure Checks

- **Configure Checks Page**: Set up High-Frequency Checks (HFCs)
  - Enter a page name for your quality monitoring dashboard
  - Select the dataset to analyze
  - Configure check parameters and thresholds
  - Save settings to create your DQA Report page

### 6. Monitor Data Quality

- **DQA Reports**: Access your configured check pages in the sidebar
- **Check Tabs**: Each report includes tabs for Summary, Missing Data, Duplicates, GPS, Outliers, Enumerator Performance, Progress, Descriptive Statistics, and Back-checks
- **Column Selector**: Use the inline selector to choose which columns to include in each analysis

### 7. Correct Data

- **Correct Data Page**: Review flagged issues and apply corrections within the app

### Command Line Options

```bash
# Show version information
datasure --version

# Launch with custom host/port
datasure --host 0.0.0.0 --port 8080

# View all available options
datasure --help
```

## Data Storage and Cache

DataSure automatically manages data storage and caching for optimal performance:

### Cache Directory Locations

- **Development Mode**: `./cache/` (in project root)
- **Production Mode**:
  - **Windows**: `%APPDATA%/datasure/cache/`
  - **Linux/macOS**: `~/.local/share/datasure/cache/`

### What's Stored

- **Project configurations**: HFC page settings and form configurations
- **Database files**: DuckDB databases for processed survey data
- **SurveyCTO cache**: Cached form metadata and server connections
- **User settings**: Check configurations and preferences

Cache directories are created automatically — no manual setup required.

## Support and Resources

### Getting Help

- **GitHub Issues**: [Report bugs and request features](https://github.com/PovertyAction/datasure/issues)
- **Email Support**: <researchsupport@poverty-action.org>
- **Release Notes**: See [RELEASENOTES.md](RELEASENOTES.md) for latest updates

### Version Information

- **Current Version**: See [RELEASENOTES.md](RELEASENOTES.md) for the latest release information
- **Version History**: Track all changes and improvements in [CHANGELOG.md](CHANGELOG.md)
- **Upgrade Instructions**: Follow installation commands above to get the latest version

## Contributing

We welcome contributions from the research community! DataSure is developed by Innovations for Poverty Action (IPA) with input from data managers and survey coordinators worldwide.

### Ways to Contribute

- **Report Issues**: Found a bug or have a feature request? [Open an issue](https://github.com/PovertyAction/datasure/issues)
- **Suggest Features**: Share ideas for new data quality checks or workflow improvements
- **Share Use Cases**: Help us understand how DataSure fits into different research workflows
- **Code Contributions**: Developers can contribute code improvements and new features

### For Developers

If you're interested in contributing code or setting up a development environment, see our comprehensive [CONTRIBUTING.md](CONTRIBUTING.md) guide which includes:

- Development environment setup
- Code quality standards and testing requirements
- Package building and distribution workflows
- Release process and documentation guidelines
- Technical architecture and development patterns

### Community Standards

- Use clear, descriptive language when reporting issues
- Follow our code of conduct and treat all contributors with respect
- Help create a welcoming environment for researchers and developers from all backgrounds

## Authors and Acknowledgments

DataSure is developed and maintained by the [**Global Research & Data Science (GRDS)**](https://poverty-action.org/research-support) team at [**Innovations for Poverty Action (IPA)**](https://poverty-action.org/). Contact GRDS at <researchsupport@poverty-action.org>.

### Core Development Team

- [Ishmail Azindoo Baako](https://poverty-action.org/people/ishmail-azindoo-baako)
- [Wesley Kirui](https://poverty-action.org/people/wesley-kirui)
- [Niall Keleher](https://poverty-action.org/people/niall-keleher)
- [Dania Ochoa](https://poverty-action.org/people/dania-ochoa)
- [Laura Lahoz](https://poverty-action.org/people/laura-lahoz)

## License and Contact

- **License**: MIT License - see [LICENSE](LICENSE) file for details
- **Repository**: [https://github.com/PovertyAction/datasure](https://github.com/PovertyAction/datasure)
- **Organization**: Innovations for Poverty Action (IPA)
- **Contact**: <researchsupport@poverty-action.org>

---

**DataSure** - Ensuring data quality for better research outcomes.
