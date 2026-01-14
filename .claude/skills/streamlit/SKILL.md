---
name: streamlit
description: This skill should be used when users need to develop Streamlit web applications. Use this skill for building interactive data apps, creating dashboards, handling session state, implementing navigation, configuring layouts, and following Streamlit best practices.
---

# Streamlit Development Skill

This skill provides comprehensive guidance for developing Streamlit applications, with a focus on best practices, session state management, multi-page navigation, and professional UI/UX patterns.

## About Streamlit

Streamlit is a Python framework for building interactive data applications with minimal frontend code. It transforms Python scripts into shareable web apps with automatic reruns on user interaction.

### Key Capabilities

- **Rapid Development**: Write Python scripts that become interactive web apps
- **Built-in Widgets**: Rich collection of input/output components
- **Session State**: Persistent state across reruns and pages
- **Multi-Page Apps**: Native support for complex navigation structures
- **Data Visualization**: Seamless integration with matplotlib, plotly, altair
- **Caching**: Performance optimization with built-in caching decorators
- **Custom Components**: Extensibility through React components

## When to Use This Skill

Use this skill when users need to:

- Build interactive data applications and dashboards
- Create multi-page applications with complex navigation
- Implement session state management patterns
- Design responsive layouts and UI components
- Handle file uploads and data processing
- Integrate data visualizations (charts, maps, tables)
- Configure authentication or access control
- Deploy Streamlit apps to production
- Debug Streamlit-specific issues
- Optimize app performance with caching

## Installation and Setup

### Basic Installation

```bash
# Using pip
pip install streamlit

# Using uv (recommended for modern projects)
uv pip install streamlit

# Verify installation
streamlit hello
```

### Project Setup

```bash
# Create new Streamlit project
mkdir my_streamlit_app
cd my_streamlit_app

# Create main app file
touch app.py

# Create pages directory for multi-page apps
mkdir pages

# Create configuration
mkdir .streamlit
touch .streamlit/config.toml
```

## Core Concepts

### 1. App Execution Model

Streamlit apps run from top to bottom on every user interaction:

```python
import streamlit as st

# This runs every time ANY widget changes
st.title("My App")

# Widget creates state and triggers rerun on change
name = st.text_input("Your name")

# This executes immediately after widget definition
if name:
    st.write(f"Hello, {name}!")
```

**Key principle**: Every interaction reruns the entire script.

### 2. Session State

Session state persists data across reruns and pages:

```python
import streamlit as st

# Initialize session state
if "counter" not in st.session_state:
    st.session_state.counter = 0

# Modify session state
if st.button("Increment"):
    st.session_state.counter += 1

# Access session state
st.write(f"Count: {st.session_state.counter}")
```

**Best practices:**

- Initialize all state variables before first use
- Use descriptive prefixes for namespacing (`user_data`, `app_config`)
- Keep state minimal to reduce memory usage
- Clear state when no longer needed

### 3. Callbacks

Callbacks execute before page reruns:

```python
def handle_submit():
    """Process form before page reruns."""
    st.session_state.submitted = True
    # Process data here

# Button with callback
st.button("Submit", on_click=handle_submit)

# Form with callback
with st.form("my_form"):
    name = st.text_input("Name")
    submitted = st.form_submit_button("Submit", on_submit=handle_submit)
```

**Callback advantages:**

- Guaranteed execution before rerun
- Can modify session state before UI renders
- Useful for validation and data processing

### 4. Caching

Optimize performance with caching decorators:

```python
import streamlit as st
import pandas as pd

@st.cache_data
def load_data(filepath):
    """Cache data loading operations."""
    return pd.read_csv(filepath)

@st.cache_resource
def create_connection():
    """Cache expensive resources (connections, models)."""
    return database_connection()

# Use cached functions
data = load_data("data.csv")
conn = create_connection()
```

**Cache types:**

- `@st.cache_data`: For data transformations (returns new data each time)
- `@st.cache_resource`: For global resources (returns same object)
- Both support TTL, cache size limits, and selective clearing

## Multi-Page Applications

### Directory Structure

```text
app.py                  # Main entry point (optional)
pages/
├── 1_📊_dashboard.py   # First page (numbered for ordering)
├── 2_📈_analysis.py    # Second page
└── 3_⚙️_settings.py    # Third page
```

### Page Configuration

```python
# pages/1_📊_dashboard.py
import streamlit as st

st.set_page_config(
    page_title="Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Dashboard")
# Page content...
```

### Navigation Patterns

**Built-in Navigation (Sidebar)**:

```python
# Streamlit automatically creates sidebar navigation
# from files in pages/ directory
```

**Custom Navigation**:

```python
import streamlit as st

# Custom page selector
page = st.sidebar.selectbox(
    "Navigate to",
    ["Dashboard", "Analysis", "Settings"]
)

if page == "Dashboard":
    show_dashboard()
elif page == "Analysis":
    show_analysis()
else:
    show_settings()
```

**Programmatic Navigation (Streamlit 1.31+)**:

```python
import streamlit as st

if st.button("Go to Dashboard"):
    st.switch_page("pages/1_📊_dashboard.py")
```

### Sharing State Between Pages

```python
# page_1.py
import streamlit as st

st.session_state.shared_data = {"user_id": 123}

# page_2.py
import streamlit as st

data = st.session_state.get("shared_data", {})
st.write(f"User ID: {data.get('user_id')}")
```

## Layout and UI Components

### Page Layout

**Columns**:

```python
col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    st.write("Left sidebar")

with col2:
    st.write("Main content")

with col3:
    st.write("Right sidebar")
```

**Containers**:

```python
# Regular container
with st.container():
    st.write("Grouped content")

# Empty container (fill later)
placeholder = st.empty()
placeholder.write("Updated content")
```

**Expanders**:

```python
with st.expander("Click to expand"):
    st.write("Hidden content")
    st.dataframe(data)
```

**Tabs**:

```python
tab1, tab2, tab3 = st.tabs(["Data", "Visualizations", "Settings"])

with tab1:
    st.dataframe(data)

with tab2:
    st.plotly_chart(fig)

with tab3:
    st.write("Settings here")
```

**Sidebar**:

```python
with st.sidebar:
    st.title("Navigation")
    option = st.selectbox("Choose", ["A", "B", "C"])
```

### Input Widgets

**Text Input**:

```python
name = st.text_input("Name", value="", max_chars=50)
password = st.text_input("Password", type="password")
text = st.text_area("Comments", height=200)
```

**Number Input**:

```python
age = st.number_input("Age", min_value=0, max_value=120, value=25)
slider = st.slider("Select range", 0, 100, (25, 75))
```

**Selection**:

```python
option = st.selectbox("Choose one", ["A", "B", "C"])
options = st.multiselect("Choose multiple", ["A", "B", "C", "D"])
radio = st.radio("Pick one", ["Yes", "No"])
checkbox = st.checkbox("Agree to terms")
```

**File Upload**:

```python
uploaded_file = st.file_uploader(
    "Choose a file",
    type=["csv", "xlsx"],
    accept_multiple_files=False
)

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    st.dataframe(df)
```

**Date/Time**:

```python
date = st.date_input("Select date")
time = st.time_input("Select time")
```

**Buttons**:

```python
if st.button("Submit"):
    st.write("Button clicked!")

if st.download_button("Download", data, "file.csv"):
    st.success("Downloaded!")
```

### Output Components

**Text and Markdown**:

```python
st.title("Title")
st.header("Header")
st.subheader("Subheader")
st.text("Plain text")
st.markdown("**Bold** and *italic*")
st.code("print('Hello')", language="python")
st.latex(r"\sum_{i=1}^n x_i")
```

**Data Display**:

```python
st.dataframe(df)  # Interactive dataframe
st.table(df)      # Static table
st.json({"key": "value"})
st.metric("Revenue", "$1.2M", delta="+15%")
```

**Visualizations**:

```python
# Built-in charts
st.line_chart(data)
st.bar_chart(data)
st.area_chart(data)

# Third-party libraries
st.pyplot(matplotlib_fig)
st.plotly_chart(plotly_fig)
st.altair_chart(altair_chart)
```

**Media**:

```python
st.image("path/to/image.png", caption="Caption", width=300)
st.audio("audio.mp3")
st.video("video.mp4")
```

**Status Elements**:

```python
st.success("Success!")
st.info("Information")
st.warning("Warning!")
st.error("Error!")
st.exception(exception_obj)
```

**Progress Indicators**:

```python
with st.spinner("Loading..."):
    time.sleep(2)

progress_bar = st.progress(0)
for i in range(100):
    progress_bar.progress(i + 1)
```

## Advanced Patterns

### Form Handling

```python
with st.form("my_form"):
    name = st.text_input("Name")
    age = st.number_input("Age")

    # Submit button inside form
    submitted = st.form_submit_button("Submit")

    if submitted:
        st.success(f"Submitted: {name}, {age}")
```

**Form benefits:**

- Batches widget changes
- Single rerun on submit
- Better UX for multi-field inputs

### Dynamic Content

```python
# Dynamic number of widgets
num_inputs = st.number_input("How many inputs?", 1, 10, 3)

for i in range(num_inputs):
    st.text_input(f"Input {i+1}", key=f"input_{i}")
```

### Modal Dialogs (Streamlit 1.31+)

```python
@st.experimental_dialog("Settings")
def show_settings():
    st.write("Settings dialog")
    if st.button("Save"):
        st.rerun()

if st.button("Open Settings"):
    show_settings()
```

### Custom Components

```python
import streamlit.components.v1 as components

# HTML component
components.html("<h1>Custom HTML</h1>")

# IFrame component
components.iframe("https://example.com", height=600)
```

## Session State Patterns

### Pattern 1: Initialize on First Run

```python
# Initialize all state variables at app start
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.user_data = {}
    st.session_state.current_page = "home"
    st.session_state.settings = load_default_settings()
```

### Pattern 2: State Namespacing

```python
# Use prefixes to organize related state
if "data_source" not in st.session_state:
    st.session_state.data_source = None
    st.session_state.data_loaded = False
    st.session_state.data_df = None

if "ui_show_sidebar" not in st.session_state:
    st.session_state.ui_show_sidebar = True
    st.session_state.ui_theme = "light"
```

### Pattern 3: State Reset

```python
def reset_analysis_state():
    """Clear analysis-related state."""
    keys_to_delete = [k for k in st.session_state if k.startswith("analysis_")]
    for key in keys_to_delete:
        del st.session_state[key]

if st.button("Reset Analysis"):
    reset_analysis_state()
    st.rerun()
```

### Pattern 4: Computed State

```python
# Store inputs, compute derived values
if "inputs_height" not in st.session_state:
    st.session_state.inputs_height = 170
if "inputs_weight" not in st.session_state:
    st.session_state.inputs_weight = 70

# Compute BMI on the fly
height_m = st.session_state.inputs_height / 100
bmi = st.session_state.inputs_weight / (height_m ** 2)
st.metric("BMI", f"{bmi:.1f}")
```

## Configuration

### config.toml

Create `.streamlit/config.toml`:

```toml
[server]
port = 8501
headless = true
enableCORS = false

[browser]
gatherUsageStats = false

[theme]
primaryColor = "#F63366"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
font = "sans serif"

[runner]
magicEnabled = true
fastReruns = true
```

### Secrets Management

Create `.streamlit/secrets.toml`:

```toml
[database]
host = "localhost"
port = 5432
username = "admin"
password = "secret"

[api]
key = "your-api-key"
```

Access in code:

```python
import streamlit as st

db_host = st.secrets["database"]["host"]
api_key = st.secrets["api"]["key"]
```

## DataSure-Specific Patterns

### Asset Management

```python
from pathlib import Path

# Package-relative asset paths
assets_dir = Path(__file__).parent.parent / "assets"
logo_path = assets_dir / "logo.png"

if logo_path.exists():
    st.image(str(logo_path), width=200)
```

### Cache Directory Handling

```python
from pathlib import Path
import streamlit as st

def get_cache_dir():
    """Get platform-appropriate cache directory."""
    project_root = Path(__file__).parent.parent

    if (project_root / "pyproject.toml").exists():
        # Development mode
        return project_root / "cache"
    else:
        # Production mode
        import platformdirs
        return Path(platformdirs.user_data_dir("datasure")) / "cache"

# Use in session state
if "cache_dir" not in st.session_state:
    st.session_state.cache_dir = get_cache_dir()
```

### Multi-Dataset Management

```python
# Pattern for managing multiple datasets
MAX_DATASETS = 10

def init_dataset_state():
    """Initialize state for all potential datasets."""
    if "datasets_loaded" not in st.session_state:
        st.session_state.datasets_loaded = []

        for i in range(1, MAX_DATASETS + 1):
            st.session_state[f"scto_{i}"] = None
            st.session_state[f"local_{i}"] = None
            st.session_state[f"script_{i}"] = None

# Usage
init_dataset_state()
```

### Navigation State Persistence

```python
# Store navigation state across pages
if "nav_current_page" not in st.session_state:
    st.session_state.nav_current_page = "start"
    st.session_state.nav_history = ["start"]

def navigate_to(page_name):
    """Navigate to page and track history."""
    st.session_state.nav_current_page = page_name
    st.session_state.nav_history.append(page_name)

if st.button("Go to Analysis"):
    navigate_to("analysis")
    st.rerun()
```

## Performance Optimization

### Caching Best Practices

```python
# DO: Cache data loading
@st.cache_data(ttl=3600)
def load_data(filepath):
    return pd.read_csv(filepath)

# DO: Cache expensive computations
@st.cache_data
def compute_statistics(df):
    return df.describe()

# DON'T: Cache user-specific or frequently changing data
# (without appropriate TTL)

# DO: Cache with parameters for selective invalidation
@st.cache_data
def process_data(df, filter_type):
    return df[df['type'] == filter_type]
```

### Minimize Reruns

```python
# Use forms to batch inputs
with st.form("filters"):
    start_date = st.date_input("Start")
    end_date = st.date_input("End")
    category = st.selectbox("Category", options)

    # Single rerun on submit
    submitted = st.form_submit_button("Apply Filters")

# Use callbacks for state updates
def update_filter():
    st.session_state.active_filter = st.session_state.filter_input

st.text_input("Filter", key="filter_input", on_change=update_filter)
```

### Lazy Loading

```python
# Load data only when needed
if "data" not in st.session_state:
    st.session_state.data = None

if st.button("Load Data"):
    with st.spinner("Loading..."):
        st.session_state.data = load_large_dataset()

if st.session_state.data is not None:
    st.dataframe(st.session_state.data)
```

## Error Handling

### Graceful Error Display

```python
try:
    data = load_data(filepath)
    st.dataframe(data)
except FileNotFoundError:
    st.error("File not found. Please check the path.")
except pd.errors.ParserError:
    st.error("Unable to parse file. Please check the format.")
except Exception as e:
    st.exception(e)
```

### Input Validation

```python
age = st.number_input("Age", value=25)

if age < 0 or age > 120:
    st.error("Please enter a valid age (0-120)")
    st.stop()  # Stop execution

email = st.text_input("Email")
if email and "@" not in email:
    st.warning("Please enter a valid email address")
```

## Testing Streamlit Apps

### Unit Testing

```python
# test_app.py
from streamlit.testing.v1 import AppTest

def test_app_loads():
    """Test that app loads without errors."""
    at = AppTest.from_file("app.py")
    at.run()
    assert not at.exception

def test_button_click():
    """Test button interaction."""
    at = AppTest.from_file("app.py")
    at.run()

    at.button[0].click()
    assert at.success[0].value == "Button clicked!"
```

## Deployment

### Streamlit Cloud

```toml
# .streamlit/config.toml (production)
[server]
headless = true
port = 8501

[browser]
gatherUsageStats = false
```

### Docker Deployment

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0"]
```

### Requirements File

```txt
streamlit>=1.39.0
pandas>=2.0.0
plotly>=5.0.0
# Add other dependencies
```

## Troubleshooting

### Common Issues

#### Issue: State not persisting

- Solution: Initialize state before first use
- Check that widget has unique `key` parameter

#### Issue: Widget not updating

- Solution: Use `st.rerun()` after state changes
- Ensure callbacks are properly defined

#### Issue: Slow performance

- Solution: Add caching to expensive operations
- Use forms to batch inputs
- Profile with `@st.cache_data` and monitor cache size

#### Issue: Import errors in multi-page apps

- Solution: Use absolute imports from package root
- Ensure `__init__.py` files exist in all directories

#### Issue: Asset files not found

- Solution: Use package-relative paths with `Path(__file__)`
- Test both development and installed package scenarios

### Debug Mode

```python
# Enable debug information
import streamlit as st

if st.checkbox("Show Debug Info"):
    st.write("Session State:", st.session_state)
    st.write("Cache Stats:", st.cache_data.stats())
```

## Best Practices

1. **Session State Management**
   - Initialize all state variables at app start
   - Use descriptive prefixes for namespacing
   - Clear unused state to minimize memory

2. **Performance**
   - Cache expensive operations with `@st.cache_data`
   - Use forms to batch user inputs
   - Implement lazy loading for large datasets

3. **User Experience**
   - Provide loading indicators for long operations
   - Display clear error messages
   - Use forms for multi-field inputs

4. **Code Organization**
   - Separate business logic from UI code
   - Use utility modules for shared functions
   - Keep pages focused on single responsibilities

5. **Navigation**
   - Use session state for cross-page data sharing
   - Implement clear navigation patterns
   - Provide breadcrumbs or back buttons

6. **Testing**
   - Test both UI and business logic
   - Use AppTest for integration testing
   - Mock external dependencies

7. **Security**
   - Never commit secrets to version control
   - Use `st.secrets` for sensitive configuration
   - Validate all user inputs

8. **Documentation**
   - Add docstrings to cached functions
   - Document session state variables
   - Provide inline help text for complex UI

## Resources

### Official Documentation

- [Streamlit Documentation](https://docs.streamlit.io/)
- [API Reference](https://docs.streamlit.io/library/api-reference)
- [Multi-Page Apps](https://docs.streamlit.io/library/get-started/multipage-apps)
- [Session State](https://docs.streamlit.io/library/api-reference/session-state)

### Learning Resources

- [Streamlit Gallery](https://streamlit.io/gallery)
- [30 Days of Streamlit](https://30days.streamlit.app/)
- [Streamlit Forums](https://discuss.streamlit.io/)

### DataSure Context

- Reference `src/datasure/app.py` for application patterns
- Check `src/datasure/views/` for page component examples
- Review `src/datasure/utils/` for utility patterns

## Quick Reference

```python
# Essential imports
import streamlit as st
import pandas as pd

# Page config (must be first Streamlit command)
st.set_page_config(
    page_title="My App",
    page_icon="📊",
    layout="wide"
)

# Session state initialization
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.data = None

# Basic UI
st.title("My App")
name = st.text_input("Name")
if st.button("Submit"):
    st.success(f"Hello, {name}!")

# Data display
df = pd.DataFrame({"col1": [1, 2, 3]})
st.dataframe(df)

# Caching
@st.cache_data
def load_data():
    return pd.read_csv("data.csv")

# Layout
col1, col2 = st.columns(2)
with col1:
    st.write("Left")
with col2:
    st.write("Right")
```
