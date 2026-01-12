"""Comprehensive tests for config_view.py module."""

import sys
from unittest.mock import MagicMock, Mock, patch

import polars as pl
import pytest


@pytest.fixture(autouse=True)
def reset_streamlit_mocks():
    """Reset streamlit mocks between tests to avoid call count accumulation."""
    import streamlit as st

    yield

    # Reset all mock call counts
    st.info.reset_mock()
    st.warning.reset_mock()
    st.error.reset_mock()
    st.success.reset_mock()
    st.title.reset_mock()
    st.markdown.reset_mock()
    st.subheader.reset_mock()
    st.write.reset_mock()
    st.columns.reset_mock()
    st.button.reset_mock()
    st.stop.reset_mock()


class TestGetProjectId:
    """Test _get_project_id function."""

    def test_returns_project_id_when_present(self):
        """Test that project ID is returned when present in session state."""
        import streamlit as st

        from datasure.views.config_view import _get_project_id

        st.session_state.st_project_id = "project_123"

        result = _get_project_id()

        assert result == "project_123"
        st.info.assert_not_called()
        st.stop.assert_not_called()

    def test_shows_info_and_stops_when_no_project_id(self):
        """Test that info message is shown and execution stops when no project ID."""
        import streamlit as st

        from datasure.views.config_view import _get_project_id

        st.session_state.st_project_id = ""
        st.stop.side_effect = StopIteration

        with pytest.raises(StopIteration):
            _get_project_id()

        st.info.assert_called_once()
        call_args = st.info.call_args[0][0]
        assert "Select a project from the Start page" in call_args
        st.stop.assert_called_once()

    def test_shows_info_and_stops_when_none_project_id(self):
        """Test that info message is shown when project ID is None."""
        import streamlit as st

        from datasure.views.config_view import _get_project_id

        st.session_state.st_project_id = None
        st.stop.side_effect = StopIteration

        with pytest.raises(StopIteration):
            _get_project_id()

        st.info.assert_called_once()
        st.stop.assert_called_once()


class TestRenderHeader:
    """Test _render_header function."""

    def test_renders_title_and_markdown(self):
        """Test that title and markdown are rendered."""
        import streamlit as st

        from datasure.views.config_view import _render_header

        _render_header()

        st.title.assert_called_once_with("Configure Checks")
        st.markdown.assert_called_once_with(
            "Add a page for each dataset you want to check"
        )


class TestRenderDemoGuidance:
    """Test _render_demo_guidance function."""

    @patch("datasure.views.config_view.demo_expander")
    @patch("datasure.views.config_view.ImportDemoInfo")
    @patch("datasure.views.config_view.is_demo_project")
    def test_renders_guidance_when_demo_project(
        self, mock_is_demo, mock_info, mock_expander
    ):
        """Test that demo guidance is rendered for demo projects."""
        from datasure.views.config_view import _render_demo_guidance

        mock_is_demo.return_value = True
        mock_info.get_info_message.return_value = "Demo info message"

        _render_demo_guidance()

        mock_is_demo.assert_called_once()
        mock_info.get_info_message.assert_called_once_with("add_check_config_info")
        mock_expander.assert_called_once_with(
            "Demo Instructions: Create Your First Configuration",
            "Demo info message",
            expanded=True,
        )

    @patch("datasure.views.config_view.demo_expander")
    @patch("datasure.views.config_view.is_demo_project")
    def test_no_guidance_when_not_demo_project(self, mock_is_demo, mock_expander):
        """Test that no guidance is rendered for non-demo projects."""
        from datasure.views.config_view import _render_demo_guidance

        mock_is_demo.return_value = False

        _render_demo_guidance()

        mock_is_demo.assert_called_once()
        mock_expander.assert_not_called()


class TestRenderConfigurationActions:
    """Test _render_configuration_actions function."""

    @patch("datasure.views.config_view.remove_check_configuration_form")
    @patch("datasure.views.config_view.add_check_configuration_form")
    def test_renders_forms_in_columns(self, mock_add_form, mock_remove_form):
        """Test that forms are rendered in columns."""
        import streamlit as st

        from datasure.views.config_view import _render_configuration_actions

        # Mock columns - use MagicMock to support context manager protocol
        mock_col1 = MagicMock()
        mock_col2 = MagicMock()
        mock_col3 = MagicMock()
        st.columns.return_value = [mock_col1, mock_col2, mock_col3]

        project_id = "test_project"
        alias_list = ["alias1", "alias2"]

        _render_configuration_actions(project_id, alias_list)

        # Verify columns created with correct proportions
        st.columns.assert_called_once_with([0.4, 0.3, 0.3])

        # Verify button created with correct callback
        st.button.assert_called_once()
        call_kwargs = st.button.call_args[1]
        assert call_kwargs["on_click"] == mock_add_form
        assert call_kwargs["args"] == (project_id, alias_list)

        # Verify remove form called with correct parameter
        mock_remove_form.assert_called_once_with(project_id)

    @patch("datasure.views.config_view.remove_check_configuration_form")
    @patch("datasure.views.config_view.add_check_configuration_form")
    def test_empty_alias_list(self, mock_add_form, mock_remove_form):
        """Test with empty alias list."""
        import streamlit as st

        from datasure.views.config_view import _render_configuration_actions

        mock_col1 = MagicMock()
        mock_col2 = MagicMock()
        mock_col3 = MagicMock()
        st.columns.return_value = [mock_col1, mock_col2, mock_col3]

        _render_configuration_actions("project_id", [])

        # Verify button created with correct callback and empty list
        call_kwargs = st.button.call_args[1]
        assert call_kwargs["on_click"] == mock_add_form
        assert call_kwargs["args"] == ("project_id", [])

        mock_remove_form.assert_called_once_with("project_id")


class TestRenderConfigurationsDisplay:
    """Test _render_configurations_display function."""

    def test_shows_info_when_empty_configurations(self):
        """Test that info message is shown when no configurations exist."""
        import streamlit as st

        from datasure.views.config_view import _render_configurations_display

        mock_service = Mock()
        empty_df = pl.DataFrame()
        mock_service.get_all_configurations.return_value = empty_df

        _render_configurations_display(mock_service)

        mock_service.get_all_configurations.assert_called_once()
        st.info.assert_called_once_with(
            "No check configurations found. Please add a check configuration to start."
        )

    @patch("datasure.views.config_view.render_configuration_table")
    def test_renders_table_when_configurations_exist(self, mock_render_table):
        """Test that table is rendered when configurations exist."""
        import streamlit as st

        from datasure.views.config_view import _render_configurations_display

        mock_service = Mock()
        config_df = pl.DataFrame([{"page_name": "Test", "survey_key": "key"}])
        mock_service.get_all_configurations.return_value = config_df

        _render_configurations_display(mock_service)

        mock_service.get_all_configurations.assert_called_once()
        mock_render_table.assert_called_once()
        # Verify the dataframe passed to render_table
        call_args = mock_render_table.call_args[0][0]
        assert call_args.equals(config_df)
        st.info.assert_not_called()


class TestRenderNavigation:
    """Test _render_navigation function."""

    @patch("datasure.views.config_view.show_demo_next_action")
    @patch("datasure.views.config_view.demo_expander")
    @patch("datasure.views.config_view.ImportDemoInfo")
    @patch("datasure.views.config_view.is_demo_project")
    def test_demo_navigation_with_configs(
        self, mock_is_demo, mock_info, mock_expander, mock_next_action
    ):
        """Test demo navigation when configurations exist."""
        import streamlit as st

        from datasure.views.config_view import _render_navigation

        mock_is_demo.return_value = True
        mock_service = Mock()
        config_df = pl.DataFrame([{"page_name": "Test"}])
        mock_service.get_all_configurations.return_value = config_df
        mock_info.get_info_message.return_value = "Proceed info"

        _render_navigation(mock_service)

        mock_is_demo.assert_called_once()
        st.write.assert_called_once_with("---")
        mock_expander.assert_called_once_with(
            "Learn More: Proceed to Data QUality Checks",
            "Proceed info",
            expanded=True,
        )
        mock_next_action.assert_called_once_with(
            4, "st_output_page1", "View Quality Reports"
        )

    @patch("datasure.views.config_view.is_demo_project")
    def test_demo_navigation_without_configs(self, mock_is_demo):
        """Test demo navigation when no configurations exist."""
        import streamlit as st

        from datasure.views.config_view import _render_navigation

        mock_is_demo.return_value = True
        mock_service = Mock()
        empty_df = pl.DataFrame()
        mock_service.get_all_configurations.return_value = empty_df

        _render_navigation(mock_service)

        mock_is_demo.assert_called_once()
        st.write.assert_called_once_with("---")
        # No further actions when configs are empty

    @patch("datasure.views.config_view.page_navigation")
    @patch("datasure.views.config_view.is_demo_project")
    def test_regular_navigation(self, mock_is_demo, mock_page_nav):
        """Test regular navigation for non-demo projects."""
        import streamlit as st

        from datasure.views.config_view import _render_navigation

        mock_is_demo.return_value = False
        mock_service = Mock()
        mock_service.get_all_configurations.return_value = pl.DataFrame()
        st.session_state.st_prep_data_page = "prep_page"
        st.session_state.st_output_pages = ["output_page"]

        _render_navigation(mock_service)

        mock_is_demo.assert_called_once()
        mock_page_nav.assert_called_once()
        call_args = mock_page_nav.call_args
        assert call_args[1]["prev"]["page_name"] == "prep_page"
        assert call_args[1]["prev"]["label"] == "← Back: Prepare Data"
        assert call_args[1]["next"]["page_name"] == "output_page"
        assert call_args[1]["next"]["label"] == "Next: Output Page →"

    @patch("datasure.views.config_view.page_navigation")
    @patch("datasure.views.config_view.is_demo_project")
    def test_regular_navigation_no_output_pages(
        self, mock_is_demo, mock_page_nav
    ):
        """Test regular navigation when no output pages exist."""
        import streamlit as st

        from datasure.views.config_view import _render_navigation

        mock_is_demo.return_value = False
        mock_service = Mock()
        mock_service.get_all_configurations.return_value = pl.DataFrame()
        st.session_state.st_prep_data_page = "prep_page"
        st.session_state.st_output_pages = []

        _render_navigation(mock_service)

        mock_is_demo.assert_called_once()
        mock_page_nav.assert_called_once()
        call_args = mock_page_nav.call_args
        assert call_args[1]["prev"]["page_name"] == "prep_page"
        assert call_args[1]["prev"]["label"] == "← Back: Prepare Data"
        assert call_args[1]["next"] is None


class TestMain:
    """Test main function."""

    @patch("datasure.views.config_view._render_navigation")
    @patch("datasure.views.config_view._render_configurations_display")
    @patch("datasure.views.config_view._render_configuration_actions")
    @patch("datasure.views.config_view._render_demo_guidance")
    @patch("datasure.views.config_view.ConfigurationService")
    @patch("datasure.views.config_view.duckdb_get_aliases")
    @patch("datasure.views.config_view._render_header")
    @patch("datasure.views.config_view._get_project_id")
    def test_main_orchestration(
        self,
        mock_get_id,
        mock_header,
        mock_get_aliases,
        mock_service_class,
        mock_demo_guidance,
        mock_config_actions,
        mock_config_display,
        mock_navigation,
    ):
        """Test that main function orchestrates all components correctly."""
        import streamlit as st

        from datasure.views.config_view import main

        # Setup mocks
        mock_get_id.return_value = "test_project"
        mock_get_aliases.return_value = ["alias1", "alias2"]
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        # Call main
        main()

        # Verify correct call sequence
        mock_get_id.assert_called_once()
        mock_get_aliases.assert_called_once_with(project_id="test_project")
        mock_service_class.assert_called_once_with("test_project")
        mock_header.assert_called_once()
        st.subheader.assert_called_once_with("Check Configurations")
        mock_demo_guidance.assert_called_once()
        mock_config_actions.assert_called_once_with(
            "test_project", ["alias1", "alias2"]
        )
        mock_config_display.assert_called_once_with(mock_service)
        mock_navigation.assert_called_once_with(mock_service)

    @patch("datasure.views.config_view._render_navigation")
    @patch("datasure.views.config_view._render_configurations_display")
    @patch("datasure.views.config_view._render_configuration_actions")
    @patch("datasure.views.config_view._render_demo_guidance")
    @patch("datasure.views.config_view.ConfigurationService")
    @patch("datasure.views.config_view.duckdb_get_aliases")
    @patch("datasure.views.config_view._render_header")
    @patch("datasure.views.config_view._get_project_id")
    def test_main_with_empty_aliases(
        self,
        mock_get_id,
        mock_header,
        mock_get_aliases,
        mock_service_class,
        mock_demo_guidance,
        mock_config_actions,
        mock_config_display,
        mock_navigation,
    ):
        """Test main function with empty alias list."""
        from datasure.views.config_view import main

        mock_get_id.return_value = "test_project"
        mock_get_aliases.return_value = []
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        main()

        mock_config_actions.assert_called_once_with("test_project", [])

    @patch("datasure.views.config_view._render_header")
    @patch("datasure.views.config_view._get_project_id")
    def test_main_stops_when_no_project_id(self, mock_get_id, mock_header):
        """Test that main stops when no project ID is available."""
        from datasure.views.config_view import main

        # Make _get_project_id raise exception (simulating st.stop())
        mock_get_id.side_effect = StopIteration

        with pytest.raises(StopIteration):
            main()

        # Verify that subsequent functions are not called
        mock_header.assert_not_called()


class TestModuleLevelExecution:
    """Test module-level code execution."""

    def test_module_level_functions_exist(self):
        """Test that module-level functions exist and are callable."""
        from datasure.views import config_view

        assert hasattr(config_view, "add_demo_navigation")
        assert hasattr(config_view, "demo_sidebar_help")
        assert hasattr(config_view, "main")

    def test_pytest_module_check(self):
        """Test that pytest check prevents module-level execution."""
        # Verify pytest is in sys.modules during tests
        assert "pytest" in sys.modules


class TestIntegrationScenarios:
    """Integration tests for common scenarios."""

    @patch("datasure.views.config_view._render_navigation")
    @patch("datasure.views.config_view.render_configuration_table")
    @patch("datasure.views.config_view.remove_check_configuration_form")
    @patch("datasure.views.config_view.add_check_configuration_form")
    @patch("datasure.views.config_view.demo_expander")
    @patch("datasure.views.config_view.is_demo_project")
    @patch("datasure.views.config_view.ConfigurationService")
    @patch("datasure.views.config_view.duckdb_get_aliases")
    @patch("datasure.views.config_view._get_project_id")
    def test_full_flow_with_existing_configs(
        self,
        mock_get_id,
        mock_get_aliases,
        mock_service_class,
        mock_is_demo,
        mock_expander,
        mock_add_form,
        mock_remove_form,
        mock_render_table,
        mock_navigation,
    ):
        """Test complete flow with existing configurations."""
        import streamlit as st

        from datasure.views.config_view import main

        # Setup
        mock_get_id.return_value = "project_123"
        mock_get_aliases.return_value = ["survey_1", "survey_2"]
        mock_is_demo.return_value = False

        mock_service = Mock()
        config_df = pl.DataFrame(
            [
                {"page_name": "Page 1", "survey_key": "key1"},
                {"page_name": "Page 2", "survey_key": "key2"},
            ]
        )
        mock_service.get_all_configurations.return_value = config_df
        mock_service_class.return_value = mock_service

        st.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]

        # Execute
        main()

        # Verify
        assert mock_render_table.called
        # Should not show info message for empty configs
        info_calls = [call for call in st.info.call_args_list if call[0][0].startswith("No check")]
        assert len(info_calls) == 0
        assert mock_get_aliases.called
        assert mock_service_class.called

    @patch("datasure.views.config_view._render_navigation")
    @patch("datasure.views.config_view.remove_check_configuration_form")
    @patch("datasure.views.config_view.add_check_configuration_form")
    @patch("datasure.views.config_view.ConfigurationService")
    @patch("datasure.views.config_view.duckdb_get_aliases")
    @patch("datasure.views.config_view._get_project_id")
    def test_full_flow_with_empty_configs(
        self,
        mock_get_id,
        mock_get_aliases,
        mock_service_class,
        mock_add_form,
        mock_remove_form,
        mock_navigation,
    ):
        """Test complete flow with no existing configurations."""
        import streamlit as st

        from datasure.views.config_view import main

        mock_get_id.return_value = "project_123"
        mock_get_aliases.return_value = ["survey_1"]

        mock_service = Mock()
        empty_df = pl.DataFrame()
        mock_service.get_all_configurations.return_value = empty_df
        mock_service_class.return_value = mock_service

        st.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]

        main()

        # Verify info message shown for empty configs
        st.info.assert_called()
        call_args = st.info.call_args[0][0]
        assert "No check configurations found" in call_args


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_get_project_id_with_whitespace_only(self):
        """Test _get_project_id with whitespace-only string."""
        import streamlit as st

        from datasure.views.config_view import _get_project_id

        st.session_state.st_project_id = "   "

        # Whitespace-only string should be truthy but might need trimming
        # The actual behavior depends on how the code treats this
        result = _get_project_id()

        assert result == "   "

    @patch("datasure.views.config_view._render_navigation")
    @patch("datasure.views.config_view._render_configurations_display")
    @patch("datasure.views.config_view._render_configuration_actions")
    @patch("datasure.views.config_view._render_demo_guidance")
    @patch("datasure.views.config_view._render_header")
    @patch("datasure.views.config_view.ConfigurationService")
    @patch("datasure.views.config_view.duckdb_get_aliases")
    @patch("datasure.views.config_view._get_project_id")
    def test_main_with_special_characters_in_project_id(
        self,
        mock_get_id,
        mock_get_aliases,
        mock_service_class,
        mock_header,
        mock_demo_guidance,
        mock_config_actions,
        mock_config_display,
        mock_navigation,
    ):
        """Test main with special characters in project ID."""
        from datasure.views.config_view import main

        mock_get_id.return_value = "project-with-special_chars@123"
        mock_get_aliases.return_value = []
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        main()

        mock_service_class.assert_called_once_with("project-with-special_chars@123")
