"""Navigation utilities for Streamlit pages."""

import streamlit as st

from datasure.utils.demo_lifecycle import (
    DEMO_RESET_FAILED_MESSAGE,
    RESTART_DEMO_MESSAGE,
    exit_demo,
    reset_demo_project,
)
from datasure.utils.onboarding_utils import (
    OnboardingSteps,
    get_onboarding_step,
    is_demo_project,
    set_onboarding_step,
    show_demo_banner,
    show_next_steps,
    show_progress_indicator,
)
from datasure.utils.ui_utils import confirm_dialog, queue_notice, show_queued_notices

ONBOARDING_STEPS = OnboardingSteps.get_all_steps()  # List of onboarding steps

# `queue_notice` scope of the demo sidebar's messages.
_DEMO_SIDEBAR_NOTICE_SCOPE = "demo_sidebar"


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
                width="stretch",
            ):
                st.switch_page(prev["page_name"])
    if next:
        with next_col:
            if st.button(
                next["label"],
                key=f"next_button_{next['label']}",
                width="stretch",
                type="primary",
            ):
                st.switch_page(next["page_name"])


def add_demo_navigation(page_name: str, step: int | None = None):
    """Add navigation elements to pages with demo support."""
    st.session_state["current_page"] = page_name

    if is_demo_project():
        if step is not None and step > get_onboarding_step():
            set_onboarding_step(step)

        show_demo_banner()
        show_progress_indicator()
        OnboardingSteps.get_guidance(step or get_onboarding_step())


def show_demo_next_action(
    current_step: int,
    next_page_session_key: str | None = None,
    custom_message: str | None = None,
    disabled: bool = False,
):
    """Show next action button for demo users."""
    if not is_demo_project():
        return

    if current_step < len(ONBOARDING_STEPS):
        next_step = ONBOARDING_STEPS[current_step]  # 0-indexed

        message = custom_message or f"Continue to {next_step['title']}"

        if st.button(f"{message}", type="primary", width="stretch", disabled=disabled):
            if next_page_session_key and next_page_session_key in st.session_state:
                set_onboarding_step(current_step + 1)
                st.switch_page(st.session_state[next_page_session_key])
            else:
                set_onboarding_step(current_step + 1)
                st.rerun()
    else:
        show_next_steps(current_step)


def demo_callout(message: str, type: str = "info"):
    """Render a demo-specific callout message."""
    if not is_demo_project():
        return

    render = {
        "info": st.info,
        "success": st.success,
        "warning": st.warning,
        "error": st.error,
    }
    render.get(type, st.info)(message)


def _restart_demo_from_sidebar() -> None:
    """Reset the demo and open the import page, or queue the failure."""
    if reset_demo_project():
        st.switch_page(st.session_state.st_import_data_page)
        return
    # confirm_dialog reruns after this, which would clear a direct st.error.
    queue_notice(_DEMO_SIDEBAR_NOTICE_SCOPE, "error", DEMO_RESET_FAILED_MESSAGE)


def demo_sidebar_help():
    """Add demo-specific help to the sidebar."""
    if not is_demo_project():
        return

    with st.sidebar:
        st.markdown("### Demo Help")
        show_queued_notices(_DEMO_SIDEBAR_NOTICE_SCOPE)

        current_step = get_onboarding_step()

        st.markdown(f"**Current Step:** {current_step} of {len(ONBOARDING_STEPS)}")

        step_info = next(
            (s for s in ONBOARDING_STEPS if s["step"] == current_step), None
        )
        if step_info:
            st.markdown(f"**{step_info['title']}**")
            st.markdown(step_info["description"])

        st.markdown("---")

        if st.button("Restart Demo", width="stretch"):
            confirm_dialog(
                "Restart demo",
                RESTART_DEMO_MESSAGE,
                confirm_label="Restart demo",
                on_confirm=_restart_demo_from_sidebar,
            )

        if st.button("Exit Demo", width="stretch"):
            exit_demo()
            st.switch_page(st.session_state.st_start_page)
