"""Tests for the navigation utilities module."""

from unittest.mock import MagicMock, patch

import pytest

from datasure.utils.navigations import page_navigation


class TestPageNavigation:
    """Test the page_navigation function."""

    @patch("datasure.utils.navigations.st")
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
        assert prev_call[1]["use_container_width"] is True
        assert "type" not in prev_call[1]  # Previous button should not be primary

        # Check second button call (next)
        next_call = mock_st.button.call_args_list[1]
        assert next_call[0][0] == next_config["label"]
        assert next_call[1]["key"] == f"next_button_{next_config['label']}"
        assert next_call[1]["use_container_width"] is True
        assert next_call[1]["type"] == "primary"  # Next button should be primary

    @patch("datasure.utils.navigations.st")
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
            use_container_width=True,
        )

    @patch("datasure.utils.navigations.st")
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
            use_container_width=True,
            type="primary",
        )

    @patch("datasure.utils.navigations.st")
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

    @patch("datasure.utils.navigations.st")
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

    @patch("datasure.utils.navigations.st")
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

    @patch("datasure.utils.navigations.st")
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

    @patch("datasure.utils.navigations.st")
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

    @patch("datasure.utils.navigations.st")
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

    @patch("datasure.utils.navigations.st")
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

    @patch("datasure.utils.navigations.st")
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
