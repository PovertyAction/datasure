"""Navigation utilities for Streamlit pages."""

import streamlit as st


def page_navigation(prev=None, next=None):
    """
    Create navigation buttons at the bottom of a page.

    Args:
        prev (dict, optional): Left button config with 'page_name' and 'label' keys
        next (dict, optional): Right button config with 'page_name' and 'label' keys

    Example:
        page_navigation(
            prev={'page_name': 'Import Data', 'label': '← Back: Import'},
            next={'page_name': 'Configuration', 'label': 'Next: Config →'}
        )
    """
    st.divider()

    back_col, _, next_col = st.columns([1, 4, 1])
    if prev:
        with back_col:
            if st.button(
                prev["label"],
                key=f"prev_button_{prev['label']}",
                use_container_width=True,
            ):
                st.switch_page(prev["page_name"])
    if next:
        with next_col:
            if st.button(
                next["label"],
                key=f"next_button_{next['label']}",
                use_container_width=True,
                type="primary",
            ):
                st.switch_page(next["page_name"])
