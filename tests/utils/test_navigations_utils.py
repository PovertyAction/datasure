"""Tests for the navigation utilities module."""

from unittest.mock import MagicMock, patch

import pytest

from datasure.utils.navigations_utils import (
    add_demo_navigation,
    demo_callout,
    demo_sidebar_help,
    page_navigation,
    show_demo_next_action,
)


class TestPageNavigation:
    """Test the page_navigation function."""

    @patch("datasure.utils.navigations_utils.st")
    def test_navigation_with_both_buttons(self, mock_st):
        """Test page navigation with both previous and next buttons."""
        # Setup mock streamlit components
        mock_back_col = MagicMock()
        mock_next_col = MagicMock()
        mock_st.columns.return_value = [mock_back_col, MagicMock(), mock_next_col]
        mock_st.button.side_effect = [False, False]  # Neither button clicked

        prev_config = {"page_name": "Import Data", "label": "← Back: Import"}
        next_config = {"page_name": "Configuration", "label": "Next: Config →"}

        page_navigation(prev=prev_config, next=next_config)

        # Verify divider is called
        mock_st.divider.assert_called_once()

        # Verify columns are created with correct ratios
        mock_st.columns.assert_called_once_with([1, 4, 1])

        assert mock_st.button.call_count == 2

        # Check first button call (previous)
        prev_call = mock_st.button.call_args_list[0]
        assert prev_call[0][0] == prev_config["label"]
        assert prev_call[1]["key"] == f"prev_button_{prev_config['label']}"
        assert prev_call[1]["width"] == "stretch"
        assert "type" not in prev_call[1]  # Previous button should not be primary

        # Check second button call (next)
        next_call = mock_st.button.call_args_list[1]
        assert next_call[0][0] == next_config["label"]
        assert next_call[1]["key"] == f"next_button_{next_config['label']}"
        assert next_call[1]["width"] == "stretch"
        assert next_call[1]["type"] == "primary"  # Next button should be primary

    @patch("datasure.utils.navigations_utils.st")
    def test_navigation_with_prev_button_only(self, mock_st):
        """Test page navigation with only previous button."""
        # Setup mock streamlit components
        mock_back_col = MagicMock()
        mock_next_col = MagicMock()
        mock_st.columns.return_value = [mock_back_col, MagicMock(), mock_next_col]
        mock_st.button.return_value = False

        prev_config = {"page_name": "Start", "label": "← Back to Start"}

        page_navigation(prev=prev_config, next=None)

        # Verify divider is called
        mock_st.divider.assert_called_once()

        # Verify only one button is created (previous)
        mock_st.button.assert_called_once_with(
            prev_config["label"],
            key=f"prev_button_{prev_config['label']}",
            width="stretch",
        )

    @patch("datasure.utils.navigations_utils.st")
    def test_navigation_with_next_button_only(self, mock_st):
        """Test page navigation with only next button."""
        # Setup mock streamlit components
        mock_back_col = MagicMock()
        mock_next_col = MagicMock()
        mock_st.columns.return_value = [mock_back_col, MagicMock(), mock_next_col]
        mock_st.button.return_value = False

        next_config = {"page_name": "Results", "label": "View Results →"}

        page_navigation(prev=None, next=next_config)

        # Verify divider is called
        mock_st.divider.assert_called_once()

        # Verify only one button is created (next)
        mock_st.button.assert_called_once_with(
            next_config["label"],
            key=f"next_button_{next_config['label']}",
            width="stretch",
            type="primary",
        )

    @patch("datasure.utils.navigations_utils.st")
    def test_navigation_with_no_buttons(self, mock_st):
        """Test page navigation with no buttons."""
        # Setup mock streamlit components
        mock_st.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]

        page_navigation(prev=None, next=None)

        # Verify divider is called
        mock_st.divider.assert_called_once()

        # Verify columns are still created
        mock_st.columns.assert_called_once_with([1, 4, 1])

        # Verify no buttons are created
        mock_st.button.assert_not_called()

    @patch("datasure.utils.navigations_utils.st")
    def test_prev_button_click_triggers_page_switch(self, mock_st):
        """Test that clicking previous button triggers page switch."""
        # Setup mock streamlit components
        mock_back_col = MagicMock()
        mock_next_col = MagicMock()
        mock_st.columns.return_value = [mock_back_col, MagicMock(), mock_next_col]
        mock_st.button.side_effect = [True, False]  # Previous button clicked

        prev_config = {"page_name": "Import Data", "label": "← Back: Import"}
        next_config = {"page_name": "Configuration", "label": "Next: Config →"}

        page_navigation(prev=prev_config, next=next_config)

        # Verify switch_page is called with correct page name
        mock_st.switch_page.assert_called_once_with(prev_config["page_name"])

    @patch("datasure.utils.navigations_utils.st")
    def test_next_button_click_triggers_page_switch(self, mock_st):
        """Test that clicking next button triggers page switch."""
        # Setup mock streamlit components
        mock_back_col = MagicMock()
        mock_next_col = MagicMock()
        mock_st.columns.return_value = [mock_back_col, MagicMock(), mock_next_col]
        mock_st.button.side_effect = [False, True]  # Next button clicked

        prev_config = {"page_name": "Import Data", "label": "← Back: Import"}
        next_config = {"page_name": "Configuration", "label": "Next: Config →"}

        page_navigation(prev=prev_config, next=next_config)

        # Verify switch_page is called with correct page name
        mock_st.switch_page.assert_called_once_with(next_config["page_name"])

    @patch("datasure.utils.navigations_utils.st")
    def test_unique_button_keys_generation(self, mock_st):
        """Test that unique keys are generated for buttons."""
        # Setup mock streamlit components
        mock_back_col = MagicMock()
        mock_next_col = MagicMock()
        mock_st.columns.return_value = [mock_back_col, MagicMock(), mock_next_col]
        mock_st.button.return_value = False

        prev_config = {
            "page_name": "Import Data",
            "label": "← Special Characters & Symbols",
        }
        next_config = {"page_name": "Configuration", "label": "Next: Config → Test"}

        page_navigation(prev=prev_config, next=next_config)

        # Verify unique keys are generated based on labels
        expected_prev_key = f"prev_button_{prev_config['label']}"
        expected_next_key = f"next_button_{next_config['label']}"

        prev_call = mock_st.button.call_args_list[0]
        next_call = mock_st.button.call_args_list[1]

        assert prev_call[1]["key"] == expected_prev_key
        assert next_call[1]["key"] == expected_next_key
        assert expected_prev_key != expected_next_key

    @patch("datasure.utils.navigations_utils.st")
    def test_column_context_managers(self, mock_st):
        """Test that columns are used as context managers correctly."""
        # Setup mock streamlit components
        mock_back_col = MagicMock()
        mock_next_col = MagicMock()
        mock_st.columns.return_value = [mock_back_col, MagicMock(), mock_next_col]
        mock_st.button.return_value = False

        prev_config = {"page_name": "Import Data", "label": "← Back"}
        next_config = {"page_name": "Configuration", "label": "Next →"}

        page_navigation(prev=prev_config, next=next_config)

        # Verify that columns are used as context managers
        mock_back_col.__enter__.assert_called_once()
        mock_back_col.__exit__.assert_called_once()
        mock_next_col.__enter__.assert_called_once()
        mock_next_col.__exit__.assert_called_once()

    @patch("datasure.utils.navigations_utils.st")
    def test_empty_string_labels(self, mock_st):
        """Test navigation with empty string labels."""
        # Setup mock streamlit components
        mock_back_col = MagicMock()
        mock_next_col = MagicMock()
        mock_st.columns.return_value = [mock_back_col, MagicMock(), mock_next_col]
        mock_st.button.return_value = False

        prev_config = {"page_name": "Import Data", "label": ""}
        next_config = {"page_name": "Configuration", "label": ""}

        page_navigation(prev=prev_config, next=next_config)

        # Verify buttons are still created with empty labels
        assert mock_st.button.call_count == 2

        prev_call = mock_st.button.call_args_list[0]
        next_call = mock_st.button.call_args_list[1]

        assert prev_call[0][0] == ""
        assert next_call[0][0] == ""

    @patch("datasure.utils.navigations_utils.st")
    def test_missing_required_keys_in_config(self, mock_st):
        """Test behavior with missing required keys in button config."""
        # Setup mock streamlit components
        mock_st.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]

        # Test with missing 'page_name' key
        prev_config = {"label": "← Back"}
        next_config = {"page_name": "Configuration", "label": "Next →"}

        with pytest.raises(KeyError):
            page_navigation(prev=prev_config, next=next_config)

        # Test with missing 'label' key
        prev_config = {"page_name": "Import Data"}
        next_config = {"page_name": "Configuration", "label": "Next →"}

        with pytest.raises(KeyError):
            page_navigation(prev=prev_config, next=next_config)

    @patch("datasure.utils.navigations_utils.st")
    def test_special_characters_in_page_names(self, mock_st):
        """Test navigation with special characters in page names."""
        # Setup mock streamlit components
        mock_back_col = MagicMock()
        mock_next_col = MagicMock()
        mock_st.columns.return_value = [mock_back_col, MagicMock(), mock_next_col]
        mock_st.button.side_effect = [True, False]  # Previous button clicked

        prev_config = {
            "page_name": "Import Data & Configuration",
            "label": "← Back: Import & Config",
        }
        next_config = {
            "page_name": "Results/Analysis",
            "label": "Next: Results/Analysis →",
        }

        page_navigation(prev=prev_config, next=next_config)

        # Verify switch_page is called with the exact page name including
        # special characters
        mock_st.switch_page.assert_called_once_with("Import Data & Configuration")


# =============================================================================
# Shared onboarding steps fixture
# =============================================================================

FAKE_STEPS = [
    {"step": 1, "title": "Import Data", "description": "Load your dataset."},
    {"step": 2, "title": "Configure Checks", "description": "Set up checks."},
    {"step": 3, "title": "View Results", "description": "Review the report."},
]


# =============================================================================
# TestAddDemoNavigation
# =============================================================================


class TestAddDemoNavigation:
    """Test add_demo_navigation function."""

    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=False)
    @patch("datasure.utils.navigations_utils.st")
    def test_non_demo_project_sets_session_state_only(self, mock_st, _is_demo):
        """When not a demo project, only session_state is updated."""
        add_demo_navigation("My Page")

        mock_st.session_state.__setitem__.assert_called_with("current_page", "My Page")

    @patch("datasure.utils.navigations_utils.show_progress_indicator")
    @patch("datasure.utils.navigations_utils.show_demo_banner")
    @patch("datasure.utils.navigations_utils.OnboardingSteps")
    @patch("datasure.utils.navigations_utils.get_onboarding_step", return_value=1)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_demo_project_no_step_shows_onboarding(
        self,
        mock_st,
        _is_demo,
        _get_step,
        mock_onboarding,
        mock_banner,
        mock_progress,
    ):
        """Demo project without step shows banner, progress, and current guidance."""
        add_demo_navigation("My Page")

        mock_banner.assert_called_once()
        mock_progress.assert_called_once()
        mock_onboarding.get_guidance.assert_called_once_with(1)

    @patch("datasure.utils.navigations_utils.show_progress_indicator")
    @patch("datasure.utils.navigations_utils.show_demo_banner")
    @patch("datasure.utils.navigations_utils.set_onboarding_step")
    @patch("datasure.utils.navigations_utils.OnboardingSteps")
    @patch("datasure.utils.navigations_utils.get_onboarding_step", return_value=1)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_demo_project_with_step_calls_set_onboarding(
        self,
        mock_st,
        _is_demo,
        _get_step,
        mock_onboarding,
        mock_set_step,
        mock_banner,
        mock_progress,
    ):
        """Demo project with explicit step calls set_onboarding_step."""
        add_demo_navigation("My Page", step=2)

        mock_set_step.assert_called_once_with(2)
        mock_banner.assert_called_once()
        mock_progress.assert_called_once()
        mock_onboarding.get_guidance.assert_called_once_with(2)


# =============================================================================
# TestShowDemoNextAction
# =============================================================================


class TestShowDemoNextAction:
    """Test show_demo_next_action function."""

    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=False)
    @patch("datasure.utils.navigations_utils.st")
    def test_non_demo_project_returns_early(self, mock_st, _is_demo):
        """Non-demo project should return without rendering anything."""
        show_demo_next_action(0)

        mock_st.button.assert_not_called()

    @patch("datasure.utils.navigations_utils.show_next_steps")
    @patch("datasure.utils.navigations_utils.ONBOARDING_STEPS", FAKE_STEPS)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_step_at_end_calls_show_next_steps(self, mock_st, _is_demo, mock_next):
        """When current_step >= len(ONBOARDING_STEPS), show_next_steps is called."""
        show_demo_next_action(len(FAKE_STEPS))

        mock_next.assert_called_once_with(len(FAKE_STEPS))
        mock_st.button.assert_not_called()

    @patch("datasure.utils.navigations_utils.ONBOARDING_STEPS", FAKE_STEPS)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_button_not_clicked_does_not_advance(self, mock_st, _is_demo):
        """When button is not clicked, onboarding step is not advanced."""
        mock_st.button.return_value = False
        show_demo_next_action(0)

        mock_st.button.assert_called_once()
        mock_st.rerun.assert_not_called()

    @patch("datasure.utils.navigations_utils.set_onboarding_step")
    @patch("datasure.utils.navigations_utils.ONBOARDING_STEPS", FAKE_STEPS)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_button_clicked_no_session_key_reruns(self, mock_st, _is_demo, mock_set):
        """Clicking button without session key advances step and reruns."""
        mock_st.button.return_value = True
        show_demo_next_action(0)

        mock_set.assert_called_once_with(1)
        mock_st.rerun.assert_called_once()

    @patch("datasure.utils.navigations_utils.set_onboarding_step")
    @patch("datasure.utils.navigations_utils.ONBOARDING_STEPS", FAKE_STEPS)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_button_clicked_with_valid_session_key_switches_page(
        self, mock_st, _is_demo, mock_set
    ):
        """Clicking button with valid session key calls switch_page."""
        mock_st.button.return_value = True
        mock_st.session_state.__contains__ = MagicMock(return_value=True)
        mock_st.session_state.__getitem__ = MagicMock(return_value="views/page2.py")

        show_demo_next_action(0, next_page_session_key="st_next_page")

        mock_set.assert_called_once_with(1)
        mock_st.switch_page.assert_called_once_with("views/page2.py")
        mock_st.rerun.assert_not_called()

    @patch("datasure.utils.navigations_utils.set_onboarding_step")
    @patch("datasure.utils.navigations_utils.ONBOARDING_STEPS", FAKE_STEPS)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_button_clicked_with_missing_session_key_reruns(
        self, mock_st, _is_demo, mock_set
    ):
        """Clicking button with session key absent from state reruns."""
        mock_st.button.return_value = True
        mock_st.session_state.__contains__ = MagicMock(return_value=False)

        show_demo_next_action(0, next_page_session_key="missing_key")

        mock_set.assert_called_once_with(1)
        mock_st.rerun.assert_called_once()

    @patch("datasure.utils.navigations_utils.ONBOARDING_STEPS", FAKE_STEPS)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_custom_message_overrides_default(self, mock_st, _is_demo):
        """Custom message is used instead of the default 'Continue to …'."""
        mock_st.button.return_value = False
        show_demo_next_action(0, custom_message="Go!")

        call_label = mock_st.button.call_args[0][0]
        assert call_label == "Go!"

    @patch("datasure.utils.navigations_utils.ONBOARDING_STEPS", FAKE_STEPS)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_default_message_uses_next_step_title(self, mock_st, _is_demo):
        """Default message references the next step title."""
        mock_st.button.return_value = False
        show_demo_next_action(0)

        call_label = mock_st.button.call_args[0][0]
        assert "Import Data" in call_label

    @patch("datasure.utils.navigations_utils.ONBOARDING_STEPS", FAKE_STEPS)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_disabled_flag_passed_to_button(self, mock_st, _is_demo):
        """Disabled flag is forwarded to the st.button call."""
        mock_st.button.return_value = False
        show_demo_next_action(0, disabled=True)

        assert mock_st.button.call_args[1]["disabled"] is True


# =============================================================================
# TestDemoCallout
# =============================================================================


class TestDemoCallout:
    """Test demo_callout function."""

    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=False)
    @patch("datasure.utils.navigations_utils.st")
    def test_non_demo_renders_nothing(self, mock_st, _is_demo):
        """Non-demo project returns early without rendering anything."""
        demo_callout("Hello")
        mock_st.info.assert_not_called()
        mock_st.success.assert_not_called()
        mock_st.warning.assert_not_called()
        mock_st.error.assert_not_called()

    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_info_type(self, mock_st, _is_demo):
        """Info type renders via st.info."""
        demo_callout("Check this", type="info")
        mock_st.info.assert_called_once_with("Check this")

    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_success_type(self, mock_st, _is_demo):
        """Success type renders via st.success."""
        demo_callout("Done", type="success")
        mock_st.success.assert_called_once_with("Done")

    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_warning_type(self, mock_st, _is_demo):
        """Warning type renders via st.warning."""
        demo_callout("Be careful", type="warning")
        mock_st.warning.assert_called_once_with("Be careful")

    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_error_type(self, mock_st, _is_demo):
        """Error type renders via st.error."""
        demo_callout("Problem", type="error")
        mock_st.error.assert_called_once_with("Problem")

    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_unknown_type_falls_back_to_info(self, mock_st, _is_demo):
        """Unknown type falls back to st.info."""
        demo_callout("Something", type="unknown")
        mock_st.info.assert_called_once_with("Something")

    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_default_type_is_info(self, mock_st, _is_demo):
        """Omitting type defaults to st.info."""
        demo_callout("Hi")
        mock_st.info.assert_called_once_with("Hi")


# =============================================================================
# TestDemoSidebarHelp
# =============================================================================


class TestDemoSidebarHelp:
    """Test demo_sidebar_help function."""

    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=False)
    @patch("datasure.utils.navigations_utils.st")
    def test_non_demo_returns_early(self, mock_st, _is_demo):
        """Non-demo project skips all sidebar rendering."""
        demo_sidebar_help()

        mock_st.sidebar.__enter__.assert_not_called()

    @patch("datasure.utils.navigations_utils.load_demo_data")
    @patch("datasure.utils.navigations_utils.get_onboarding_step", return_value=99)
    @patch("datasure.utils.navigations_utils.ONBOARDING_STEPS", FAKE_STEPS)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_step_info_not_found_skips_step_details(
        self, mock_st, _is_demo, _get_step, _load_demo
    ):
        """When current_step doesn't match any step, step details are skipped."""
        mock_st.button.return_value = False
        demo_sidebar_help()

        calls = [str(c) for c in mock_st.markdown.call_args_list]
        assert not any("title" in c.lower() for c in calls)

    @patch("datasure.utils.navigations_utils.load_demo_data")
    @patch("datasure.utils.navigations_utils.get_onboarding_step", return_value=1)
    @patch("datasure.utils.navigations_utils.ONBOARDING_STEPS", FAKE_STEPS)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_step_info_found_renders_title_and_description(
        self, mock_st, _is_demo, _get_step, _load_demo
    ):
        """When current_step matches a step, title and description are shown."""
        mock_st.button.return_value = False
        demo_sidebar_help()

        all_markdown = " ".join(str(c.args[0]) for c in mock_st.markdown.call_args_list)
        assert "Import Data" in all_markdown
        assert "Load your dataset." in all_markdown

    @patch("datasure.utils.navigations_utils.load_demo_data")
    @patch("datasure.utils.navigations_utils.get_onboarding_step", return_value=1)
    @patch("datasure.utils.navigations_utils.ONBOARDING_STEPS", FAKE_STEPS)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_restart_demo_button_switches_page_and_loads_demo(
        self, mock_st, _is_demo, _get_step, mock_load
    ):
        """Confirming restart loads demo data and switches to import page."""
        # Simulate confirmation state already set (user previously clicked
        # "Restart Demo")
        mock_st.session_state.get.return_value = True
        # Buttons rendered: Restart Demo, Confirm restart, Cancel, Exit Demo
        mock_st.button.side_effect = [False, True, False, False]
        mock_st.session_state.st_import_data_page = "views/import.py"

        demo_sidebar_help()

        mock_st.switch_page.assert_called_once_with("views/import.py")
        mock_load.assert_called_once()

    @patch("datasure.utils.navigations_utils.load_demo_data")
    @patch("datasure.utils.navigations_utils.get_onboarding_step", return_value=1)
    @patch("datasure.utils.navigations_utils.ONBOARDING_STEPS", FAKE_STEPS)
    @patch("datasure.utils.navigations_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.navigations_utils.st")
    def test_exit_demo_button_clears_project_and_switches_page(
        self, mock_st, _is_demo, _get_step, _load_demo
    ):
        """Clicking 'Exit Demo' clears project id and switches to start page."""
        # No confirmation dialog active
        mock_st.session_state.get.return_value = False
        # Buttons rendered: Restart Demo, Exit Demo
        mock_st.button.side_effect = [False, True]
        mock_st.session_state.st_start_page = "views/start.py"

        demo_sidebar_help()

        mock_st.switch_page.assert_called_once_with("views/start.py")
