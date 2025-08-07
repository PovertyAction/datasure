# DataSure

**DataSure** is IPA's Data Management System Dashboard - a comprehensive tool for survey data quality monitoring and high-frequency checks (HFCs) in research projects.

Built for data managers, survey coordinators, and research teams, DataSure provides real-time monitoring of survey data quality with interactive dashboards, automated checks, and flexible reporting capabilities.

## Key Features

- **📊 Data Quality Monitoring**: Real-time dashboards for comprehensive survey data analysis
- **🔍 Automated Checks**: 10 specialized quality check modules including duplicates, outliers, GPS validation, and missing data analysis
- **📈 Interactive Visualizations**: Charts and maps for data exploration and quality assessment
- **🔗 Multi-Source Integration**: Direct SurveyCTO API connection plus CSV/Excel file support
- **⚙️ Flexible Configuration**: Project-based settings with customizable check parameters
- **📋 Comprehensive Reporting**: Export capabilities for different audiences and formats
- **🎯 Enumerator Performance**: Monitor data collection team productivity and quality metrics

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

### Step 3: verify installation

```bash
datasure --version
```

## Getting the latest release

```bash
# if datasure is already install, get latest version with
uv tool upgrade datasure
```

## Quick Start

1. **Launch the application**:

   ```bash
   datasure
   ```

2. **Create your first project** and configure data quality checks

3. **Import survey data**:
   - Connect directly to your SurveyCTO server
   - Upload CSV or Excel files from local storage

4. **Monitor data quality** with interactive dashboards organized into specialized check modules

5. **Generate reports** and export results for your research team

## System Requirements

- **Python**: Version 3.11 or higher
- **Operating System**: Windows, macOS, or Linux
- **Memory**: Minimum 4GB RAM (8GB recommended for large datasets)
- **Storage**: 1GB free space for application and data cache
- **Internet**: Required for SurveyCTO integration and updates

## Data Quality Check Modules

DataSure includes 10 specialized modules for comprehensive survey data quality monitoring:

| Module | Purpose |
|--------|---------|
| **Summary** | Overall project progress and completion tracking |
| **Missing Data** | Identify patterns in incomplete responses |
| **Duplicates** | Find and manage duplicate survey entries |
| **GPS Validation** | Verify location data accuracy with interactive maps |
| **Outliers** | Identify unusual responses requiring review |
| **Enumerator Performance** | Monitor data collection team productivity |
| **Progress Tracking** | Real-time survey completion monitoring |
| **Descriptive Statistics** | Data distribution analysis and summaries |
| **Back-checks** | Verification workflow support |
| **Custom Checks** | Configure additional quality checks per project |

## Core Capabilities

### Data Import and Management

- **SurveyCTO Integration**: Direct API connection with form metadata and authentication
- **Local File Support**: CSV and Excel upload with automatic type detection  
- **Multi-Project Organization**: Manage multiple surveys simultaneously
- **Data Preparation**: Cleaning and transformation workflows

### Interactive Dashboards

- **Real-time Monitoring**: Live updates as new data arrives
- **Customizable Views**: Configure dashboards per project requirements
- **Export Options**: Generate reports in PDF, Excel, and other formats
- **Automated Alerts**: Notifications for quality issues requiring attention

### Performance and Scalability

- **High-Performance Processing**: DuckDB backend for fast analytical queries
- **Large Dataset Support**: Optimized for datasets with hundreds of thousands of records
- **Intelligent Caching**: Reduces processing time and API calls
- **Cross-Platform Compatibility**: Works on Windows, macOS, and Linux

## Getting Started - Application Usage

### Using DataSure

Once DataSure is installed, you can begin monitoring your survey data quality:

#### 1. Launch the Application

```bash
datasure
```

The web interface will open in your default browser (typically at `http://localhost:8501`).

#### 2. Import Data

- **Import Data Page**: Start here to connect your data sources
- **SurveyCTO Integration**: Connect directly to your SurveyCTO server with authentication
- **Local Files**: Upload CSV or Excel files from your computer
- **Multiple Datasets**: Import and manage up to 10 datasets per project

#### 3. Prepare and Configure

- **Prepare Data Page**: Preview your imported datasets in separate tabs
- **Configure Checks Page**: Set up High-Frequency Checks (HFCs)
  - Enter a page name for your quality monitoring dashboard
  - Select the dataset to analyze
  - Configure check parameters and thresholds
  - Save settings to create your HFC page

#### 4. Monitor Data Quality

- **HFC Dashboard**: Access your configured quality check page
- **Interactive Tabs**: Each check type has its own tab (Summary, Missing Data, Duplicates, etc.)
- **Settings Expanders**: Configure specific parameters for each check
- **Real-time Updates**: Dashboard refreshes as new data becomes available

#### 5. Export and Share

- Generate reports for different audiences
- Export findings in various formats
- Monitor trends over time

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

Cache directories are created automatically - no manual setup required.

## Support and Resources

### Getting Help

- **GitHub Issues**: [Report bugs and request features](https://github.com/PovertyAction/datasure/issues)
- **Email Support**: <researchsupport@poverty-action.org>
- **Documentation**: See [RELEASENOTES.md](RELEASENOTES.md) for latest updates

### Version Information

- **Current Version**: See [RELEASENOTES.md](RELEASENOTES.md) for the latest release information
- **Version History**: Track all changes and improvements
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
