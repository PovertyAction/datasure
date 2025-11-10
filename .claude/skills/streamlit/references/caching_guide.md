# Streamlit Caching Guide

Comprehensive guide to caching in Streamlit for optimal performance.

## Cache Decorators

### @st.cache_data

For caching data transformations and computations.

```python
import streamlit as st
import pandas as pd

@st.cache_data
def load_data(filepath):
    """Load data from CSV file."""
    return pd.read_csv(filepath)

@st.cache_data
def process_data(df, column):
    """Process and return new dataframe."""
    return df[df[column] > 0]
```

**When to use:**

- Loading data from files or APIs
- Data transformations (filtering, aggregating)
- Expensive computations that return serializable data
- Any function that returns data (DataFrames, lists, dicts, etc.)

**Key characteristics:**

- Returns a copy of cached data (safe for mutations)
- Data is serialized and stored
- Good for most data operations

### @st.cache_resource

For caching non-serializable global resources.

```python
import streamlit as st
import psycopg2

@st.cache_resource
def get_database_connection():
    """Create and cache database connection."""
    return psycopg2.connect(
        host="localhost",
        database="mydb",
        user="user",
        password="password"
    )

@st.cache_resource
def load_ml_model():
    """Load and cache ML model."""
    import joblib
    return joblib.load("model.pkl")
```

**When to use:**

- Database connections
- ML models
- Complex objects that shouldn't be copied
- Resources that are expensive to create

**Key characteristics:**

- Returns the same object (not a copy)
- Object is not serialized
- Shared across all users and sessions

## Cache Parameters

### TTL (Time To Live)

```python
import streamlit as st
from datetime import timedelta

# Cache for 1 hour
@st.cache_data(ttl=3600)  # seconds
def fetch_api_data():
    return requests.get("https://api.example.com/data").json()

# Cache for 1 day
@st.cache_data(ttl=timedelta(days=1))
def load_daily_report():
    return generate_report()

# Cache until midnight
@st.cache_data(ttl="1d")  # string format
def load_todays_data():
    return fetch_data()
```

**TTL formats:**

- Integer (seconds): `ttl=3600`
- Timedelta: `ttl=timedelta(hours=1)`
- String: `ttl="1h"`, `ttl="30m"`, `ttl="1d"`

### Max Entries

```python
# Limit cache size (LRU eviction)
@st.cache_data(max_entries=100)
def get_user_data(user_id):
    return fetch_user_data(user_id)

# Unlimited cache size (default)
@st.cache_data(max_entries=None)
def load_reference_data():
    return load_data()
```

**When to use:**

- When caching many different inputs
- To prevent unlimited memory growth
- For user-specific or session-specific data

### Show Spinner

```python
# Show loading spinner (default)
@st.cache_data(show_spinner=True)
def slow_function():
    return expensive_computation()

# Custom spinner message
@st.cache_data(show_spinner="Loading data...")
def load_large_file():
    return pd.read_csv("large_file.csv")

# No spinner
@st.cache_data(show_spinner=False)
def fast_function():
    return quick_computation()
```

### Persist to Disk

```python
# Persist cache to disk (survives app restarts)
@st.cache_data(persist="disk")
def expensive_download():
    return download_large_file()

# Keep in memory only (default)
@st.cache_data(persist=None)
def regular_function():
    return compute_something()
```

**persist="disk" considerations:**

- Cache survives app restarts
- Slower than memory cache
- Uses `.streamlit/cache/` directory
- Good for downloads or expensive operations

## Cache Control

### Clear Cache

```python
import streamlit as st

# Clear all caches
if st.button("Clear All Cache"):
    st.cache_data.clear()
    st.cache_resource.clear()

# Clear specific function cache
@st.cache_data
def load_data():
    return pd.read_csv("data.csv")

if st.button("Clear Data Cache"):
    load_data.clear()
```

### Bypass Cache

```python
# Skip cache for one call (experimental)
@st.cache_data
def fetch_data():
    return expensive_operation()

# Normal cached call
data = fetch_data()

# Bypass cache (get fresh data)
fresh_data = fetch_data.bypass()
```

### Check Cache Stats

```python
import streamlit as st

# Show cache statistics
if st.checkbox("Show Cache Stats"):
    st.write("Data cache stats:", st.cache_data.stats())
    st.write("Resource cache stats:", st.cache_resource.stats())
```

## Caching Patterns

### Pattern 1: Basic Data Loading

```python
import streamlit as st
import pandas as pd

@st.cache_data
def load_csv(filepath):
    """Load CSV with caching."""
    return pd.read_csv(filepath)

# Use cached function
df = load_csv("data.csv")
st.dataframe(df)
```

### Pattern 2: Parameterized Caching

```python
@st.cache_data
def filter_data(df, min_value, max_value):
    """Cache based on filter parameters."""
    return df[(df["value"] >= min_value) & (df["value"] <= max_value)]

# Different parameters create different cache entries
filtered_1 = filter_data(df, 0, 10)
filtered_2 = filter_data(df, 10, 20)  # Separate cache entry
```

### Pattern 3: User-Specific Caching

```python
@st.cache_data(max_entries=1000)
def get_user_profile(user_id):
    """Cache user profiles (LRU eviction after 1000 entries)."""
    return fetch_profile_from_db(user_id)

# Each user_id gets its own cache entry
user = get_user_profile(st.session_state.user_id)
```

### Pattern 4: Time-Based Refresh

```python
from datetime import timedelta

@st.cache_data(ttl=timedelta(minutes=5))
def get_live_prices():
    """Refresh price data every 5 minutes."""
    return fetch_prices_from_api()

# Automatically refreshes after 5 minutes
prices = get_live_prices()
```

### Pattern 5: Resource Initialization

```python
@st.cache_resource
def init_resources():
    """Initialize expensive resources once."""
    return {
        "db": create_db_connection(),
        "model": load_ml_model(),
        "config": load_config()
    }

# Resources shared across all users
resources = init_resources()
db = resources["db"]
model = resources["model"]
```

### Pattern 6: Conditional Caching

```python
import streamlit as st

# Cache only in production
def load_data():
    if st.session_state.get("env") == "production":
        return cached_load_data()
    else:
        return uncached_load_data()

@st.cache_data
def cached_load_data():
    return pd.read_csv("data.csv")

def uncached_load_data():
    return pd.read_csv("data.csv")
```

### Pattern 7: Hash Function for Custom Objects

```python
import streamlit as st

class CustomObject:
    def __init__(self, value):
        self.value = value

# Define how to hash custom object
def hash_custom_object(obj):
    return obj.value

@st.cache_data(hash_funcs={CustomObject: hash_custom_object})
def process_custom(obj):
    return f"Processed: {obj.value}"

# Cache based on custom hash
result = process_custom(CustomObject("test"))
```

## DataSure-Specific Patterns

### Pattern 8: Cache Directory-Based Loading

```python
import streamlit as st
from pathlib import Path

@st.cache_data
def load_project_data(project_id, cache_dir):
    """Load project data from cache directory."""
    data_path = Path(cache_dir) / project_id / "data" / "data.parquet"
    return pd.read_parquet(data_path)

# Use with session state
cache_dir = st.session_state.get("cache_dir")
if cache_dir:
    data = load_project_data(st.session_state.project_id, cache_dir)
```

### Pattern 9: Multi-Dataset Caching

```python
@st.cache_data
def load_dataset(source_type, dataset_id, filepath):
    """Cache datasets by source and ID."""
    if source_type == "scto":
        return load_scto_data(filepath)
    elif source_type == "local":
        return pd.read_csv(filepath)
    else:
        return load_other_data(filepath)

# Each dataset cached separately
scto_1 = load_dataset("scto", 1, "path1.csv")
local_1 = load_dataset("local", 1, "path2.csv")
```

### Pattern 10: Check Configuration Caching

```python
@st.cache_data
def load_check_config(project_id, check_name):
    """Cache check configurations."""
    config_path = get_config_path(project_id, check_name)
    return json.load(open(config_path))

# Configuration cached per project and check
missing_config = load_check_config(project_id, "missing")
duplicates_config = load_check_config(project_id, "duplicates")
```

## Common Caching Mistakes

### ❌ Mistake 1: Caching with Mutable Defaults

```python
# BAD - mutable default argument
@st.cache_data
def process_data(df, columns=[]):  # Don't use mutable defaults!
    return df[columns]
```

**Fix:**

```python
# GOOD - immutable default
@st.cache_data
def process_data(df, columns=None):
    if columns is None:
        columns = []
    return df[columns]
```

### ❌ Mistake 2: Caching Non-Deterministic Functions

```python
# BAD - result changes every call
@st.cache_data
def get_random_data():
    return np.random.rand(100)  # Different every time!
```

**Fix:**

```python
# GOOD - include seed in cache key
@st.cache_data
def get_random_data(seed=42):
    np.random.seed(seed)
    return np.random.rand(100)
```

### ❌ Mistake 3: Caching Database Connections with @st.cache_data

```python
# BAD - connection is not serializable data
@st.cache_data
def get_connection():
    return psycopg2.connect(...)
```

**Fix:**

```python
# GOOD - use cache_resource for connections
@st.cache_resource
def get_connection():
    return psycopg2.connect(...)
```

### ❌ Mistake 4: Not Using Cache for Expensive Operations

```python
# BAD - loads every time
def load_large_data():
    return pd.read_csv("large_file.csv")

# Called multiple times = multiple loads
data1 = load_large_data()
data2 = load_large_data()
```

**Fix:**

```python
# GOOD - cache expensive operation
@st.cache_data
def load_large_data():
    return pd.read_csv("large_file.csv")

# Only loads once
data1 = load_large_data()
data2 = load_large_data()  # Uses cached version
```

### ❌ Mistake 5: Over-Caching Everything

```python
# BAD - caching simple operations
@st.cache_data
def add_numbers(a, b):
    return a + b

@st.cache_data
def format_string(text):
    return text.upper()
```

**Fix:**

```python
# GOOD - don't cache trivial operations
def add_numbers(a, b):
    return a + b

def format_string(text):
    return text.upper()
```

## When NOT to Cache

Don't cache when:

1. **Function is already fast** (< 0.1 seconds)
2. **Result changes frequently** (use short TTL if needed)
3. **Function has side effects** (logging, writing files, etc.)
4. **Result depends on external state** (unless you want stale data)
5. **Memory usage would be too high** (very large results)

## Performance Tips

### Tip 1: Use Specific Parameters

```python
# Cache misses more often (new DataFrame hash each time)
@st.cache_data
def process(df):
    return df.mean()

# Better - cache based on filepath
@st.cache_data
def process(filepath):
    df = pd.read_csv(filepath)
    return df.mean()
```

### Tip 2: Chain Cached Functions

```python
@st.cache_data
def load_data(filepath):
    return pd.read_csv(filepath)

@st.cache_data
def clean_data(df):
    return df.dropna()

@st.cache_data
def analyze_data(df):
    return df.describe()

# Each step cached independently
data = load_data("file.csv")
clean = clean_data(data)
analysis = analyze_data(clean)
```

### Tip 3: Use TTL for Time-Sensitive Data

```python
# Refresh every hour
@st.cache_data(ttl=3600)
def get_stock_prices():
    return fetch_prices()

# Daily data - cache until midnight
@st.cache_data(ttl="1d")
def get_daily_report():
    return generate_report()
```

### Tip 4: Limit Cache Size for User Data

```python
# Prevent unlimited growth
@st.cache_data(max_entries=500)
def get_user_data(user_id):
    return fetch_data(user_id)
```

## Debugging Cache Issues

### Check What's Cached

```python
import streamlit as st

st.subheader("Cache Debug Info")

# Show cache stats
st.write("Data cache:", st.cache_data.stats())
st.write("Resource cache:", st.cache_resource.stats())

# Button to clear cache
if st.button("Clear All Caches"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.success("Caches cleared!")
    st.rerun()
```

### Test Cache Behavior

```python
import time

@st.cache_data
def slow_function():
    time.sleep(2)  # Simulate slow operation
    return "Done"

# First call - slow (2 seconds)
start = time.time()
result = slow_function()
elapsed = time.time() - start

st.write(f"Result: {result}")
st.write(f"Time: {elapsed:.2f}s")

# Second call - fast (cached)
start = time.time()
result = slow_function()
elapsed = time.time() - start

st.write(f"Time (cached): {elapsed:.4f}s")
```

## Best Practices Summary

1. **Use @st.cache_data for data** - DataFrames, lists, dicts, etc.
2. **Use @st.cache_resource for connections** - DB connections, models, etc.
3. **Add TTL for time-sensitive data** - Refresh automatically
4. **Limit cache size for user data** - Prevent unlimited growth
5. **Cache at appropriate granularity** - Not too high, not too low
6. **Don't cache trivial operations** - Caching has overhead
7. **Provide clear spinner messages** - Inform users about long operations
8. **Test cache behavior** - Verify caching is working as expected
9. **Clear cache when needed** - Provide manual clear option
10. **Monitor cache size** - Watch memory usage in production

## Cache Decision Tree

```text
Is the function expensive (> 0.1s)?
├─ No  → Don't cache
└─ Yes → Does it return data (DataFrame, dict, list)?
    ├─ Yes → Use @st.cache_data
    │   └─ Is data time-sensitive?
    │       ├─ Yes → Add TTL
    │       └─ No  → No TTL needed
    └─ No → Is it a connection or model?
        ├─ Yes → Use @st.cache_resource
        └─ No  → Use @st.cache_data anyway
```
