"""
Multi-Page Streamlit App Template

Template for creating a multi-page Streamlit app with navigation and shared state.

Directory structure:
    app.py                  # This file (optional main page)
    pages/
    ├── 1_📊_data.py       # Data page
    ├── 2_📈_analysis.py   # Analysis page
    └── 3_⚙️_settings.py    # Settings page
"""

import pandas as pd
import streamlit as st

# Page configuration
st.set_page_config(
    page_title="Multi-Page App",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Initialize session state
def init_session_state():
    """Initialize shared session state for all pages."""
    if "app_initialized" not in st.session_state:
        st.session_state.app_initialized = True

        # Navigation state
        st.session_state.current_page = "home"
        st.session_state.nav_history = []

        # Data state
        st.session_state.data_loaded = False
        st.session_state.data_df = None
        st.session_state.data_source = None

        # Settings state
        st.session_state.settings = {
            "theme": "light",
            "show_advanced": False,
        }


# Shared utility functions
@st.cache_data
def load_data_from_file(filepath):
    """Load data with caching."""
    return pd.read_csv(filepath)


def display_navigation_state():
    """Debug: Display current navigation state."""
    if st.checkbox("Show Navigation Debug"):
        st.write("Current page:", st.session_state.current_page)
        st.write("History:", st.session_state.nav_history)
        st.write("Settings:", st.session_state.settings)


# Main page content
def main():
    """Home page content."""
    init_session_state()

    st.title("🏠 Multi-Page Application")

    st.markdown("""
    Welcome to this multi-page Streamlit application!

    ### Pages

    Use the sidebar to navigate between pages:

    - **📊 Data**: Upload and view your data
    - **📈 Analysis**: Analyze and visualize your data
    - **⚙️ Settings**: Configure application settings

    ### Getting Started

    1. Navigate to the **Data** page
    2. Upload a CSV file
    3. Go to **Analysis** to explore your data
    """)

    # Quick stats if data is loaded
    if st.session_state.data_loaded and st.session_state.data_df is not None:
        st.success("✓ Data is loaded and ready!")

        df = st.session_state.data_df

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Rows", len(df))

        with col2:
            st.metric("Columns", len(df.columns))

        with col3:
            st.metric("Source", st.session_state.data_source or "Unknown")

    else:
        st.info("No data loaded yet. Go to the Data page to upload a file.")

    # Navigation helpers
    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("→ Go to Data Page", use_container_width=True):
            st.switch_page("pages/1_📊_data.py")

    with col2:
        if st.button("→ Go to Analysis Page", use_container_width=True):
            if st.session_state.data_loaded:
                st.switch_page("pages/2_📈_analysis.py")
            else:
                st.warning("Please load data first!")

    # Debug section
    with st.expander("Debug Info"):
        display_navigation_state()


if __name__ == "__main__":
    main()
