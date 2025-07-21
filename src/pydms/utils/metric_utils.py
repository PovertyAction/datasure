import streamlit as st
from streamlit_extras.stylable_container import stylable_container


def custom_metric():
    """Custom metric to be displayed in the summary report"""
    # New button. Creating a container.
    with stylable_container(
        key="container",
        # 'button' below in css_styles is the element you will be customizing.
        css_styles="""
            button {
                background-color: #3c3635;
                border: none;
                color: white;
            }
            """,
    ):
        st.write("This is a custom metric.")
