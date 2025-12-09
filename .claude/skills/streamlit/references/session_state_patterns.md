# Streamlit Session State Patterns

Common patterns for managing session state effectively in Streamlit applications.

## Basic Patterns

### Pattern 1: Initialize on First Run

```python
import streamlit as st

# Check if already initialized
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.user_name = ""
    st.session_state.user_email = ""
    st.session_state.preferences = {}
```

**When to use**: At the start of your app to set up initial state.

### Pattern 2: Conditional Initialization

```python
# Initialize only if needed
if "data" not in st.session_state:
    st.session_state.data = None

if "processed_data" not in st.session_state:
    st.session_state.processed_data = None
```

**When to use**: For state that may not always be needed.

### Pattern 3: Default Values with get()

```python
# Get with default fallback
name = st.session_state.get("user_name", "Guest")
settings = st.session_state.get("settings", {})
```

**When to use**: When you want safe access without initialization checks.

## Namespacing Patterns

### Pattern 4: Prefixed Namespacing

```python
# Group related state with prefixes
if "data_source" not in st.session_state:
    st.session_state.data_source = None
    st.session_state.data_loaded = False
    st.session_state.data_df = None
    st.session_state.data_columns = []

if "ui_sidebar_visible" not in st.session_state:
    st.session_state.ui_sidebar_visible = True
    st.session_state.ui_theme = "light"
    st.session_state.ui_page = "home"
```

**When to use**: For organizing related state variables.

### Pattern 5: Dictionary Namespacing

```python
# Store related state in dictionaries
if "user" not in st.session_state:
    st.session_state.user = {
        "name": "",
        "email": "",
        "role": "viewer",
        "authenticated": False
    }

# Access
st.write(st.session_state.user["name"])

# Modify
st.session_state.user["authenticated"] = True
```

**When to use**: For complex related state that forms a logical group.

## Multi-Dataset Patterns

### Pattern 6: Multiple Dataset Management

```python
# Pattern from DataSure for managing multiple data sources
MAX_DATASETS = 10

def init_dataset_state():
    """Initialize state for all potential datasets."""
    if "datasets_initialized" not in st.session_state:
        st.session_state.datasets_initialized = True
        st.session_state.datasets_loaded = []

        for i in range(1, MAX_DATASETS + 1):
            st.session_state[f"scto_{i}"] = None
            st.session_state[f"local_{i}"] = None
            st.session_state[f"script_{i}"] = None

# Usage
init_dataset_state()

# Store dataset
st.session_state.scto_1 = dataframe
st.session_state.datasets_loaded.append("scto_1")

# Retrieve dataset
df = st.session_state.get("scto_1")
```

**When to use**: For applications managing multiple data sources.

## State Persistence Patterns

### Pattern 7: Cross-Page State

```python
# page_1.py
import streamlit as st

# Store data to share with other pages
st.session_state.project_id = "abc123"
st.session_state.project_data = load_project_data()

# page_2.py
import streamlit as st

# Access shared state
project_id = st.session_state.get("project_id")
if project_id:
    st.write(f"Current project: {project_id}")
```

**When to use**: For sharing data across different pages in multi-page apps.

### Pattern 8: Navigation State

```python
# Track navigation history
if "nav_history" not in st.session_state:
    st.session_state.nav_history = ["home"]
    st.session_state.nav_current = "home"

def navigate_to(page):
    st.session_state.nav_current = page
    st.session_state.nav_history.append(page)

def go_back():
    if len(st.session_state.nav_history) > 1:
        st.session_state.nav_history.pop()
        st.session_state.nav_current = st.session_state.nav_history[-1]

# Usage
if st.button("Go to Analysis"):
    navigate_to("analysis")
    st.rerun()

if st.button("Back"):
    go_back()
    st.rerun()
```

**When to use**: For custom navigation with history tracking.

## State Cleanup Patterns

### Pattern 9: Selective State Reset

```python
def reset_analysis_state():
    """Clear all analysis-related state."""
    keys_to_delete = [k for k in st.session_state if k.startswith("analysis_")]
    for key in keys_to_delete:
        del st.session_state[key]

def reset_form_state():
    """Clear all form inputs."""
    form_keys = ["name", "email", "age", "comments"]
    for key in form_keys:
        if key in st.session_state:
            del st.session_state[key]

# Usage
if st.button("Reset Analysis"):
    reset_analysis_state()
    st.rerun()
```

**When to use**: For clearing state when starting fresh or switching contexts.

### Pattern 10: Complete State Reset

```python
def clear_all_state():
    """Clear all session state (except app config)."""
    protected_keys = ["app_config", "user_auth"]

    for key in list(st.session_state.keys()):
        if key not in protected_keys:
            del st.session_state[key]

# Usage
if st.button("Start Over"):
    clear_all_state()
    st.rerun()
```

**When to use**: For logout or complete app reset scenarios.

## Callback Patterns

### Pattern 11: State Update via Callback

```python
def handle_name_change():
    """Process name change before rerun."""
    name = st.session_state.name_input
    st.session_state.user_name = name.strip().title()
    st.session_state.name_modified = True

# Widget with callback
st.text_input(
    "Your name",
    key="name_input",
    on_change=handle_name_change
)

# Display processed value
if "user_name" in st.session_state:
    st.write(f"Hello, {st.session_state.user_name}!")
```

**When to use**: For processing input before the main script reruns.

### Pattern 12: Form Submit with Callback

```python
def process_form():
    """Handle form submission."""
    st.session_state.form_data = {
        "name": st.session_state.form_name,
        "email": st.session_state.form_email,
        "submitted_at": datetime.now()
    }
    st.session_state.form_submitted = True

with st.form("user_form"):
    st.text_input("Name", key="form_name")
    st.text_input("Email", key="form_email")

    st.form_submit_button("Submit", on_click=process_form)

# Check submission
if st.session_state.get("form_submitted"):
    st.success("Form submitted successfully!")
    st.json(st.session_state.form_data)
```

**When to use**: For processing form data before the page rerenders.

## Computed State Patterns

### Pattern 13: Derived State

```python
# Store inputs, compute derived values
if "inputs_height" not in st.session_state:
    st.session_state.inputs_height = 170  # cm
if "inputs_weight" not in st.session_state:
    st.session_state.inputs_weight = 70   # kg

# Compute BMI on the fly (don't store)
height_m = st.session_state.inputs_height / 100
bmi = st.session_state.inputs_weight / (height_m ** 2)

st.metric("BMI", f"{bmi:.1f}")
```

**When to use**: For values that can be computed from stored state.

### Pattern 14: Cached Computed State

```python
# Store inputs
if "data_filters" not in st.session_state:
    st.session_state.data_filters = {
        "start_date": None,
        "end_date": None,
        "category": "all"
    }

# Cache expensive computation
@st.cache_data
def filter_data(df, filters):
    filtered = df.copy()
    if filters["start_date"]:
        filtered = filtered[filtered["date"] >= filters["start_date"]]
    if filters["end_date"]:
        filtered = filtered[filtered["date"] <= filters["end_date"]]
    if filters["category"] != "all":
        filtered = filtered[filtered["category"] == filters["category"]]
    return filtered

# Use cached function
if "raw_data" in st.session_state:
    filtered_data = filter_data(
        st.session_state.raw_data,
        st.session_state.data_filters
    )
    st.dataframe(filtered_data)
```

**When to use**: For expensive computations that depend on state.

## Workflow State Patterns

### Pattern 15: Multi-Step Workflow

```python
# Workflow state management
if "workflow_step" not in st.session_state:
    st.session_state.workflow_step = 1
    st.session_state.workflow_data = {}

def next_step():
    st.session_state.workflow_step += 1

def previous_step():
    if st.session_state.workflow_step > 1:
        st.session_state.workflow_step -= 1

# Display current step
step = st.session_state.workflow_step

if step == 1:
    st.header("Step 1: Import Data")
    # Step 1 UI
    if st.button("Next"):
        next_step()
        st.rerun()

elif step == 2:
    st.header("Step 2: Configure Settings")
    # Step 2 UI
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Previous"):
            previous_step()
            st.rerun()
    with col2:
        if st.button("Next"):
            next_step()
            st.rerun()

elif step == 3:
    st.header("Step 3: Review and Submit")
    # Step 3 UI
    if st.button("Previous"):
        previous_step()
        st.rerun()
```

**When to use**: For guided multi-step processes.

## Debug Pattern

### Pattern 16: State Inspector

```python
# Debug session state
if st.checkbox("Show Session State (Debug)"):
    st.subheader("Session State")

    # Show all keys
    st.write("Keys:", list(st.session_state.keys()))

    # Show all values
    state_dict = {k: v for k, v in st.session_state.items()}
    st.json(state_dict)

    # Filter by prefix
    prefix = st.text_input("Filter by prefix")
    if prefix:
        filtered = {k: v for k, v in st.session_state.items() if k.startswith(prefix)}
        st.json(filtered)
```

**When to use**: For debugging state issues during development.

## Anti-Patterns to Avoid

### ❌ Don't: Access before initialization

```python
# BAD
counter = st.session_state.counter  # KeyError if not initialized
```

### ✅ Do: Initialize or use get()

```python
# GOOD
if "counter" not in st.session_state:
    st.session_state.counter = 0
counter = st.session_state.counter

# OR
counter = st.session_state.get("counter", 0)
```

### ❌ Don't: Store large data unnecessarily

```python
# BAD
st.session_state.raw_data = load_huge_dataset()  # Stored in session
st.session_state.processed_data = process(st.session_state.raw_data)  # Also stored
```

### ✅ Do: Use caching for large data

```python
# GOOD
@st.cache_data
def load_data():
    return load_huge_dataset()

data = load_data()  # Cached, not in session state
```

### ❌ Don't: Overuse session state

```python
# BAD - storing everything in session state
st.session_state.temp_var = some_calculation()
st.session_state.intermediate = another_calculation()
```

### ✅ Do: Use local variables for transient data

```python
# GOOD - only store what needs to persist
temp_var = some_calculation()
intermediate = another_calculation()

# Only store final result if needed across reruns
st.session_state.final_result = final_calculation(temp_var, intermediate)
```

## Best Practices Summary

1. **Initialize early**: Set up all state at the start of your app
2. **Use namespacing**: Prefix or group related state variables
3. **Clean up**: Remove unused state to save memory
4. **Use get()**: Safe access with default values
5. **Cache data**: Don't store large data that can be cached
6. **Callbacks for processing**: Use callbacks for data processing
7. **Debug visibility**: Add debug mode to inspect state
8. **Document state**: Comment what each state variable represents
