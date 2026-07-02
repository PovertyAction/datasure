# Streamlit Widget Reference

Quick reference for Streamlit widgets with common use cases and parameters.

## Input Widgets

### Text Input

```python
# Basic text input
name = st.text_input("Label", value="default", max_chars=100)

# Password input
password = st.text_input("Password", type="password")

# Text area (multi-line)
text = st.text_area("Comments", height=200, max_chars=1000)

# With callback
def on_change():
    st.session_state.processed = st.session_state.user_input.upper()

st.text_input("Input", key="user_input", on_change=on_change)
```

### Number Input

```python
# Number input
age = st.number_input("Age", min_value=0, max_value=120, value=25, step=1)

# Float input
price = st.number_input("Price", min_value=0.0, value=10.0, step=0.5, format="%.2f")

# Slider (single value)
volume = st.slider("Volume", min_value=0, max_value=100, value=50, step=5)

# Range slider (two values)
range_vals = st.slider("Range", 0, 100, (25, 75))
```

### Selection Widgets

```python
# Selectbox (dropdown)
option = st.selectbox(
    "Choose one",
    options=["Option A", "Option B", "Option C"],
    index=0  # Default selection
)

# Multiselect
selections = st.multiselect(
    "Choose multiple",
    options=["A", "B", "C", "D"],
    default=["A"]
)

# Radio buttons
choice = st.radio(
    "Pick one",
    options=["Yes", "No", "Maybe"],
    index=0,
    horizontal=True  # Display horizontally
)

# Checkbox
agreed = st.checkbox("I agree to terms", value=False)

# Toggle (Streamlit 1.31+)
enabled = st.toggle("Enable feature", value=True)
```

### Date and Time

```python
import datetime

# Date input
date = st.date_input(
    "Select date",
    value=datetime.date.today(),
    min_value=datetime.date(2020, 1, 1),
    max_value=datetime.date(2030, 12, 31)
)

# Time input
time = st.time_input("Select time", value=datetime.time(9, 0))

# Date range
date_range = st.date_input(
    "Select date range",
    value=(datetime.date.today(), datetime.date.today() + datetime.timedelta(days=7))
)
```

### File Upload

```python
# Single file
uploaded_file = st.file_uploader(
    "Choose a file",
    type=["csv", "xlsx", "txt"],
    accept_multiple_files=False
)

if uploaded_file:
    # Read file
    import pandas as pd
    df = pd.read_csv(uploaded_file)
    st.dataframe(df)

# Multiple files
uploaded_files = st.file_uploader(
    "Choose files",
    type=["csv"],
    accept_multiple_files=True
)

for file in uploaded_files:
    df = pd.read_csv(file)
    st.write(f"File: {file.name}")
    st.dataframe(df)
```

### Color Picker

```python
# Color picker
color = st.color_picker("Pick a color", value="#00f900")
st.write(f"Selected color: {color}")
```

### Camera Input

```python
# Take photo from camera
picture = st.camera_input("Take a picture")

if picture:
    st.image(picture)
```

## Button Widgets

### Regular Buttons

```python
# Basic button
if st.button("Click me"):
    st.write("Button clicked!")

# Button with custom styling
if st.button("Primary", type="primary"):
    st.write("Primary button clicked!")

# Disabled button
if st.button("Disabled", disabled=True):
    pass  # Won't execute
```

### Download Button

```python
import pandas as pd

# Download CSV
df = pd.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6]})
csv = df.to_csv(index=False)

st.download_button(
    label="Download CSV",
    data=csv,
    file_name="data.csv",
    mime="text/csv"
)

# Download text file
text_data = "Hello, world!"
st.download_button(
    label="Download TXT",
    data=text_data,
    file_name="message.txt",
    mime="text/plain"
)

# Download JSON
import json
json_data = json.dumps({"key": "value"}, indent=2)
st.download_button(
    label="Download JSON",
    data=json_data,
    file_name="data.json",
    mime="application/json"
)
```

### Link Button

```python
# Link button (opens URL)
st.link_button("Go to Google", "https://google.com")
```

## Forms

### Basic Form

```python
with st.form("my_form"):
    # All inputs inside form
    name = st.text_input("Name")
    age = st.number_input("Age", min_value=0)
    email = st.text_input("Email")

    # Submit button (required)
    submitted = st.form_submit_button("Submit")

    if submitted:
        st.success(f"Form submitted: {name}, {age}, {email}")
```

### Form with Callback

```python
def handle_submit():
    st.session_state.form_data = {
        "name": st.session_state.form_name,
        "age": st.session_state.form_age
    }

with st.form("callback_form"):
    st.text_input("Name", key="form_name")
    st.number_input("Age", key="form_age")

    st.form_submit_button("Submit", on_click=handle_submit)

if "form_data" in st.session_state:
    st.json(st.session_state.form_data)
```

### Form with Clear Button

```python
with st.form("form_with_clear"):
    name = st.text_input("Name")
    email = st.text_input("Email")

    col1, col2 = st.columns(2)

    with col1:
        submitted = st.form_submit_button("Submit")
    with col2:
        cleared = st.form_submit_button("Clear")

    if submitted:
        st.success("Submitted!")
    if cleared:
        st.rerun()  # Rerun to clear form
```

## Output Widgets

### Text Display

```python
# Title
st.title("App Title")

# Header
st.header("Section Header")

# Subheader
st.subheader("Subsection")

# Text
st.text("Plain text")

# Markdown
st.markdown("**Bold** and *italic* text")

# Caption (small text)
st.caption("Small caption text")

# Code
st.code("print('Hello')", language="python")

# LaTeX
st.latex(r"\sum_{i=1}^n x_i^2")

# Divider
st.divider()
```

### Data Display

```python
import pandas as pd

df = pd.DataFrame({
    "col1": [1, 2, 3],
    "col2": [4, 5, 6]
})

# Interactive dataframe
st.dataframe(
    df,
    width="stretch",
    hide_index=False,
    column_config={
        "col1": st.column_config.NumberColumn(
            "Column 1",
            help="First column",
            format="%d"
        )
    }
)

# Data editor (editable dataframe)
edited_df = st.data_editor(
    df,
    num_rows="dynamic",  # Allow adding/deleting rows
    width="stretch"
)

# Static table
st.table(df)

# JSON
st.json({"key": "value", "number": 42})

# Metric
st.metric(
    label="Revenue",
    value="$1.2M",
    delta="+15%",
    delta_color="normal"  # "normal", "inverse", or "off"
)

# Dict display
st.write({"key": "value"})
```

### Charts

```python
import pandas as pd
import numpy as np

# Sample data
df = pd.DataFrame({
    "x": range(10),
    "y": np.random.randn(10)
})

# Line chart
st.line_chart(df, x="x", y="y")

# Area chart
st.area_chart(df)

# Bar chart
st.bar_chart(df)

# Scatter chart
st.scatter_chart(df)

# Map (requires lat/lon columns)
map_df = pd.DataFrame({
    "lat": [37.76, 37.77, 37.78],
    "lon": [-122.4, -122.41, -122.42]
})
st.map(map_df)
```

### Widget options and styling

```python
# Example of widget with with options
st.selectbox(
    "Choose an option",
    options=["Option 1", "Option 2", "Option 3"],
    index=1,  # Default to "Option 2"
    help="Select one of the options",
    width='stretch'  # Make widget stretch to container width
)

```

### Deprecated Parameters

**`use_container_width` is deprecated** — use the `width` parameter instead:

| Old (deprecated) | New | Meaning |
| --- | --- | --- |
| `use_container_width=True` | `width="stretch"` | Fill full container width |
| `use_container_width=False` | `width="content"` | Fit to content width |

The `width` parameter accepts `"content"`, `"stretch"`, or an integer pixel value.

```python
# WRONG — deprecated
if st.button("Submit", use_container_width=True): ...
st.dataframe(df, use_container_width=True)
st.plotly_chart(fig, use_container_width=True)
with st.popover("Options", use_container_width=True): ...

# CORRECT
if st.button("Submit", width="content"): ...
st.dataframe(df, width="stretch")
st.plotly_chart(fig, use_container_width=True)  # plotly_chart uses use_container_width still
with st.popover("Options", width="content"): ...
```

**`use_column_width` on `st.image` is also deprecated** — pass an integer `width` instead or omit for natural size:

```python
# WRONG — deprecated
st.image("logo.png", use_column_width=True)

# CORRECT
st.image("logo.png", width=300)
```

### Third-Party Visualizations

```python
import matplotlib.pyplot as plt
import plotly.express as px
import altair as alt

# Matplotlib
fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 9])
st.pyplot(fig)

# Plotly
fig = px.line(x=[1, 2, 3], y=[1, 4, 9])
st.plotly_chart(fig, width="stretch")

# Altair
chart = alt.Chart(df).mark_line().encode(x="x", y="y")
st.altair_chart(chart, width="stretch")
```

### Media

```python
# Image
st.image(
    "path/to/image.png",
    caption="Image caption",
    width=300,
    use_column_width=True
)

# Audio
st.audio("path/to/audio.mp3")

# Video
st.video("path/to/video.mp4")
```

## Status and Progress

### Status Messages

```python
# Success
st.success("Success message!")

# Info
st.info("Information message")

# Warning
st.warning("Warning message!")

# Error
st.error("Error message!")

# Exception
try:
    1 / 0
except Exception as e:
    st.exception(e)
```

### Progress Indicators

```python
import time

# Spinner
with st.spinner("Loading..."):
    time.sleep(2)
st.success("Done!")

# Progress bar
progress_bar = st.progress(0)
for i in range(100):
    time.sleep(0.01)
    progress_bar.progress(i + 1)

# Status container
with st.status("Processing...", expanded=True) as status:
    st.write("Step 1: Loading data...")
    time.sleep(1)
    st.write("Step 2: Processing...")
    time.sleep(1)
    status.update(label="Complete!", state="complete", expanded=False)
```

## Layout Components

### Columns

```python
# Equal columns
col1, col2, col3 = st.columns(3)

with col1:
    st.write("Column 1")

with col2:
    st.write("Column 2")

with col3:
    st.write("Column 3")

# Unequal columns
col1, col2 = st.columns([1, 3])  # 1:3 ratio
```

### Tabs

```python
tab1, tab2, tab3 = st.tabs(["Data", "Charts", "Settings"])

with tab1:
    st.dataframe(df)

with tab2:
    st.line_chart(df)

with tab3:
    st.write("Settings here")
```

### Expander

```python
with st.expander("Click to expand"):
    st.write("Hidden content")
    st.dataframe(df)
```

### Container

```python
# Regular container
with st.container():
    st.write("Content in container")

# Container with border
with st.container(border=True):
    st.write("Bordered container")

# Empty container (fill later)
placeholder = st.empty()

# Update placeholder
placeholder.write("Updated content")

# Clear placeholder
placeholder.empty()
```

### Sidebar

```python
# Add to sidebar
with st.sidebar:
    st.title("Sidebar")
    option = st.selectbox("Choose", ["A", "B", "C"])

# Alternative syntax
st.sidebar.title("Sidebar")
option = st.sidebar.selectbox("Choose", ["A", "B", "C"])
```

## Advanced Widgets

### Popover (Streamlit 1.33+)

```python
with st.popover("Open popover"):
    st.write("Content inside popover")
    name = st.text_input("Name")
```

### Modal Dialog

```python
@st.experimental_dialog("Settings")
def show_settings():
    st.write("Settings dialog")
    theme = st.selectbox("Theme", ["Light", "Dark"])

    if st.button("Save"):
        st.session_state.theme = theme
        st.rerun()

if st.button("Open Settings"):
    show_settings()
```

## Widget Keys and Callbacks

### Using Keys

```python
# Key for state access
st.text_input("Name", key="user_name")

# Access value
name = st.session_state.user_name
```

### Callbacks

```python
def on_change():
    st.session_state.processed = st.session_state.raw_input.upper()

def on_click():
    st.session_state.clicked = True

# Text input with callback
st.text_input("Input", key="raw_input", on_change=on_change)

# Button with callback
st.button("Click", on_click=on_click)
```

## Common Patterns

### Conditional Display

```python
show_advanced = st.checkbox("Show advanced options")

if show_advanced:
    st.number_input("Advanced setting 1")
    st.number_input("Advanced setting 2")
```

### Dynamic Widget Count

```python
num_inputs = st.number_input("How many inputs?", 1, 10, 3)

for i in range(num_inputs):
    st.text_input(f"Input {i+1}", key=f"input_{i}")
```

### Disabled Widgets

```python
# Disable based on condition
input_disabled = not st.checkbox("Enable input")

st.text_input("Name", disabled=input_disabled)
st.button("Submit", disabled=input_disabled)
```

### Help Text

```python
# Add help text to widgets
st.text_input(
    "Email",
    help="Enter your email address"
)

st.selectbox(
    "Country",
    options=["USA", "UK", "Canada"],
    help="Select your country of residence"
)
```

## Column Configuration (Data Editor)

```python
import pandas as pd

df = pd.DataFrame({
    "name": ["Alice", "Bob"],
    "age": [25, 30],
    "active": [True, False],
    "avatar": ["https://...", "https://..."]
})

edited = st.data_editor(
    df,
    column_config={
        "name": st.column_config.TextColumn(
            "Name",
            help="Full name",
            max_chars=50,
            required=True
        ),
        "age": st.column_config.NumberColumn(
            "Age",
            min_value=0,
            max_value=120,
            format="%d"
        ),
        "active": st.column_config.CheckboxColumn(
            "Active",
            help="Is user active?"
        ),
        "avatar": st.column_config.ImageColumn(
            "Avatar",
            help="Profile picture"
        )
    }
)
```

## Best Practices

1. **Use keys for state management**: Assign keys to widgets when you need to access their values in session state
2. **Use callbacks for processing**: Process input in callbacks before the main script reruns
3. **Use forms to batch inputs**: Reduce reruns by grouping related inputs in forms
4. **Provide help text**: Add help text to complex widgets for better UX
5. **Disable when appropriate**: Disable widgets when actions are not valid
6. **Use appropriate widget types**: Choose widgets that match the expected input type
7. **Add validation**: Validate user inputs and display clear error messages
8. **Use placeholders**: Provide placeholder text for text inputs

## Widget Comparison

| Use Case | Widget | Notes |
|----------|--------|-------|
| Single line text | `text_input` | Limited length |
| Multi-line text | `text_area` | For longer text |
| Integer | `number_input` | Set step=1 |
| Float | `number_input` | Set step and format |
| Range selection | `slider` | Visual selection |
| Single choice | `selectbox` or `radio` | Dropdown vs inline |
| Multiple choices | `multiselect` | Allow multiple selections |
| Boolean | `checkbox` or `toggle` | Simple yes/no |
| Date | `date_input` | Calendar picker |
| File | `file_uploader` | Handle file uploads |
| Color | `color_picker` | Visual color selection |
