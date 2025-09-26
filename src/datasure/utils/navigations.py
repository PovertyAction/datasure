"""Navigation utilities for Streamlit pages."""

import streamlit as st

from datasure.utils.onboarding_utils import (
    ONBOARDING_STEPS,
    get_onboarding_step,
    is_demo_project,
    set_onboarding_step,
    show_demo_banner,
    show_next_steps,
    show_progress_indicator,
    show_step_guidance,
)


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


def add_demo_navigation(page_name: str, step: int | None = None):
    """Add navigation elements to pages with demo support."""
    # Set the current page in session state
    st.session_state["current_page"] = page_name

    # If this is a demo project, show onboarding elements
    if is_demo_project():
        # Update onboarding step if provided
        if step is not None:
            set_onboarding_step(step)

        # Show demo-specific UI elements
        show_demo_banner()
        show_progress_indicator()
        show_step_guidance(step or get_onboarding_step())


def show_demo_next_action(
    current_step: int,
    next_page_session_key: str | None = None,
    custom_message: str | None = None,
):
    """Show next action button for demo users."""
    if not is_demo_project():
        return

    if current_step < len(ONBOARDING_STEPS):
        next_step = ONBOARDING_STEPS[current_step]  # 0-indexed

        message = custom_message or f"Continue to {next_step['title']}"

        if st.button(f"{message}", type="primary", use_container_width=True):
            if next_page_session_key and next_page_session_key in st.session_state:
                set_onboarding_step(current_step + 1)
                st.switch_page(st.session_state[next_page_session_key])
            else:
                set_onboarding_step(current_step + 1)
                st.rerun()
    else:
        show_next_steps(current_step)


def demo_callout(message: str, type: str = "info"):
    """Show a demo-specific callout message."""
    if not is_demo_project():
        return

    if type == "info":
        st.info(f"**Demo Tip:** {message}")
    elif type == "success":
        st.success(f"**Demo Success:** {message}")
    elif type == "warning":
        st.warning(f"**Demo Note:** {message}")
    elif type == "error":
        st.error(f"**Demo Issue:** {message}")


def demo_expander(title: str, content: str, expanded: bool = False):
    """Create a demo-specific expander with helpful information."""
    if not is_demo_project():
        return

    with st.expander(f"**Learn More: {title}**", expanded=expanded):
        st.markdown(content)


def demo_sidebar_help():
    """Add demo-specific help to the sidebar."""
    if not is_demo_project():
        return

    with st.sidebar:
        st.markdown("### Demo Help")

        current_step = get_onboarding_step()

        st.markdown(f"**Current Step:** {current_step} of {len(ONBOARDING_STEPS)}")

        step_info = next(
            (s for s in ONBOARDING_STEPS if s["step"] == current_step), None
        )
        if step_info:
            st.markdown(f"**{step_info['title']}**")
            st.markdown(step_info["description"])

        st.markdown("---")

        if st.button("Return to Start", use_container_width=True):
            st.switch_page("pages/start_view.py")

        if st.button("Exit Demo", use_container_width=True):
            st.session_state.st_project_id = ""
            st.session_state.pop("onboarding_step", None)
            st.switch_page("pages/start_view.py")
