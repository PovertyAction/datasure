"""Check configuration view for DataSure application."""

import sys

import streamlit as st

from datasure.utils.config_utils import (
    ConfigurationService,
    add_check_configuration_form,
    remove_check_configuration_form,
    render_configuration_table,
)
from datasure.utils.duckdb_utils import duckdb_get_aliases
from datasure.utils.navigations_utils import (
    add_demo_navigation,
    demo_sidebar_help,
    page_navigation,
    show_demo_next_action,
)
from datasure.utils.onboarding_utils import (
    ImportDemoInfo,
    demo_expander,
    is_demo_project,
)

# Add demo navigation and guidance (skip during tests)
if "pytest" not in sys.modules:
    add_demo_navigation("config_view.py", step=4)
    demo_sidebar_help()


def _get_project_id() -> str:
    """
    Get project ID from session state.

    Returns
    -------
        Project ID string

    Raises
    ------
        Stops execution if no project ID found
    """
    project_id: str = st.session_state.st_project_id

    if not project_id:
        st.info(
            "Select a project from the Start page and import data. "
            "You can also create a new project from the Start page."
        )
        st.stop()

    return project_id


def _render_header() -> None:
    """Render page header and description."""
    st.title("Configure Checks")
    st.markdown("Add a page for each dataset you want to check")


def _render_demo_guidance() -> None:
    """Render demo project guidance if applicable."""
    if is_demo_project():
        demo_expander(
            "Demo Instructions: Create Your First Configuration",
            ImportDemoInfo.get_info_message("add_check_config_info"),
            expanded=True,
        )


def _render_configuration_actions(project_id: str, alias_list: list[str]) -> None:
    """
    Render add and remove configuration actions.

    Args:
        project_id: Current project ID
        alias_list: List of available dataset aliases
    """
    col1, col2, _ = st.columns([0.4, 0.3, 0.3])

    with col1:
        st.button(
            ":material/add: Add New Check Configuration",
            on_click=add_check_configuration_form,
            args=(project_id, alias_list),
            width="stretch",
        )

    with col2:
        remove_check_configuration_form(project_id)


def _render_configurations_display(config_service: ConfigurationService) -> None:
    """
    Display existing check configurations.

    Args:
        config_service: Service instance for configuration operations
    """
    check_config_log = config_service.get_all_configurations()

    if check_config_log.is_empty():
        st.info(
            "No check configurations found. Please add a check configuration to start."
        )
    else:
        render_configuration_table(check_config_log)


def _render_navigation(config_service: ConfigurationService) -> None:
    """
    Render page navigation or demo next action.

    Args:
        config_service: Service instance for configuration operations
    """
    check_config_log = config_service.get_all_configurations()

    if is_demo_project():
        st.write("---")

        if not check_config_log.is_empty():
            demo_expander(
                "Learn More: Proceed to Data QUality Checks",
                ImportDemoInfo.get_info_message("proceed_to_hfcs_info"),
                expanded=True,
            )
            show_demo_next_action(4, "st_output_page1", "View Quality Reports")
    else:
        if len(st.session_state.st_output_pages) > 0:
            next_page = {
                "page_name": st.session_state.st_output_pages[0],
                "label": "Next: Output Page →",
            }
        else:
            next_page = None
        page_navigation(
            prev={
                "page_name": st.session_state.st_prep_data_page,
                "label": "← Back: Prepare Data",
            },
            next=next_page,
        )


def main() -> None:
    """Main entry point for the configuration view."""
    # Get project context
    project_id = _get_project_id()
    alias_list = duckdb_get_aliases(project_id=project_id)

    # Initialize services
    config_service = ConfigurationService(project_id)

    # Render page sections
    _render_header()

    st.subheader("Check Configurations")
    _render_demo_guidance()

    _render_configuration_actions(project_id, alias_list)
    _render_configurations_display(config_service)
    _render_navigation(config_service)


# Execute main function (skip during tests)
if "pytest" not in sys.modules:
    main()
