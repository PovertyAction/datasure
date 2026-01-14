"""
Basic Streamlit App Template

A minimal template for creating a Streamlit application with best practices.
"""

import pandas as pd
import streamlit as st

# Page configuration - MUST be first Streamlit command
st.set_page_config(
    page_title="My Streamlit App",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Initialize session state
def init_session_state():
    """Initialize all session state variables."""
    if "initialized" not in st.session_state:
        st.session_state.initialized = True
        st.session_state.data = None
        st.session_state.settings = {}


# Cached data loading function
@st.cache_data
def load_data(filepath):
    """Load data from CSV file with caching."""
    return pd.read_csv(filepath)


# Main app logic
def main():
    """Main application entry point."""
    # Initialize state
    init_session_state()

    # Title and description
    st.title("📊 My Streamlit App")
    st.markdown("Welcome to this Streamlit application!")

    # Sidebar
    with st.sidebar:
        st.header("Settings")

        # File uploader
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

        if uploaded_file:
            st.session_state.data = pd.read_csv(uploaded_file)
            st.success("File uploaded successfully!")

        # Settings
        show_raw_data = st.checkbox("Show raw data", value=True)

    # Main content
    if st.session_state.data is not None:
        df = st.session_state.data

        # Display data
        if show_raw_data:
            st.subheader("Raw Data")
            st.dataframe(df, width="stretch")

        # Basic statistics
        st.subheader("Statistics")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Total Rows", len(df))

        with col2:
            st.metric("Total Columns", len(df.columns))

        with col3:
            st.metric(
                "Memory Usage", f"{df.memory_usage(deep=True).sum() / 1024:.1f} KB"
            )

        # Simple visualization
        if len(df.select_dtypes(include=["number"]).columns) > 0:
            st.subheader("Data Visualization")
            numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

            selected_col = st.selectbox("Select column to visualize", numeric_cols)

            if selected_col:
                st.line_chart(df[selected_col])

    else:
        # Empty state
        st.info("👈 Upload a CSV file to get started!")

        # Example
        with st.expander("See example"):
            example_df = pd.DataFrame(
                {
                    "Column A": [1, 2, 3, 4, 5],
                    "Column B": [10, 20, 30, 40, 50],
                }
            )
            st.dataframe(example_df)


if __name__ == "__main__":
    main()
