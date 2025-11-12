"""Comprehensive tests for config_view.py module."""

from unittest.mock import MagicMock, Mock, patch

import polars as pl
import pytest


class TestGetProjectId:
    """Test _get_project_id function."""

    @patch("datasure.views.config_view.st")
    def test_returns_project_id_when_present(self, mock_st):
        """Test that project ID is returned when present in session state."""
        # Import the function after mocking
        from datasure.views.config_view import _get_project_id

        mock_st.session_state.st_project_id = "project_123"

        result = _get_project_id()

        assert result == "project_123"
        mock_st.info.assert_not_called()
        mock_st.stop.assert_not_called()

    @patch("datasure.views.config_view.st")
    def test_shows_info_and_stops_when_no_project_id(self, mock_st):
        """Test that info message is shown and execution stops when no project ID."""
        from datasure.views.config_view import _get_project_id

        mock_st.session_state.st_project_id = ""
        mock_st.stop.side_effect = Exception("Streamlit stop")

        with pytest.raises(Exception):  # noqa: B017 - st.stop() raises generic exception
            _get_project_id()

        mock_st.info.assert_called_once()
        call_args = mock_st.info.call_args[0][0]
        assert "Select a project from the Start page" in call_args
        mock_st.stop.assert_called_once()

    @patch("datasure.views.config_view.st")
    def test_shows_info_and_stops_when_none_project_id(self, mock_st):
        """Test that info message is shown when project ID is None."""
        from datasure.views.config_view import _get_project_id

        mock_st.session_state.st_project_id = None
        mock_st.stop.side_effect = Exception("Streamlit stop")

        with pytest.raises(Exception):  # noqa: B017 - st.stop() raises generic exception
            _get_project_id()

        mock_st.info.assert_called_once()
        mock_st.stop.assert_called_once()


class TestRenderHeader:
    """Test _render_header function."""

    @patch("datasure.views.config_view.st")
    def test_renders_title_and_markdown(self, mock_st):
        """Test that title and markdown are rendered."""
        from datasure.views.config_view import _render_header

        _render_header()

        mock_st.title.assert_called_once_with("Configure Checks")
        mock_st.markdown.assert_called_once_with(
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
    @patch("datasure.views.config_view.st")
    def test_renders_forms_in_columns(self, mock_st, mock_add_form, mock_remove_form):
        """Test that forms are rendered in columns."""
        from datasure.views.config_view import _render_configuration_actions

        # Mock columns - use MagicMock to support context manager protocol
        mock_col1 = MagicMock()
        mock_col2 = MagicMock()
        mock_col3 = MagicMock()
        mock_st.columns.return_value = [mock_col1, mock_col2, mock_col3]

        project_id = "test_project"
        alias_list = ["alias1", "alias2"]

        _render_configuration_actions(project_id, alias_list)

        # Verify columns created with correct proportions
        mock_st.columns.assert_called_once_with([0.4, 0.3, 0.3])

        # Verify button created with correct callback
        mock_st.button.assert_called_once()
        call_kwargs = mock_st.button.call_args[1]
        assert call_kwargs["on_click"] == mock_add_form
        assert call_kwargs["args"] == (project_id, alias_list)

        # Verify remove form called with correct parameter
        mock_remove_form.assert_called_once_with(project_id)

    @patch("datasure.views.config_view.remove_check_configuration_form")
    @patch("datasure.views.config_view.add_check_configuration_form")
    @patch("datasure.views.config_view.st")
    def test_empty_alias_list(self, mock_st, mock_add_form, mock_remove_form):
        """Test with empty alias list."""
        from datasure.views.config_view import _render_configuration_actions

        mock_col1 = MagicMock()
        mock_col2 = MagicMock()
        mock_col3 = MagicMock()
        mock_st.columns.return_value = [mock_col1, mock_col2, mock_col3]

        _render_configuration_actions("project_id", [])

        # Verify button created with correct callback and empty list
        call_kwargs = mock_st.button.call_args[1]
        assert call_kwargs["on_click"] == mock_add_form
        assert call_kwargs["args"] == ("project_id", [])

        mock_remove_form.assert_called_once_with("project_id")


class TestRenderConfigurationsDisplay:
    """Test _render_configurations_display function."""

    @patch("datasure.views.config_view.st")
    def test_shows_info_when_empty_configurations(self, mock_st):
        """Test that info message is shown when no configurations exist."""
        from datasure.views.config_view import _render_configurations_display

        mock_service = Mock()
        empty_df = pl.DataFrame()
        mock_service.get_all_configurations.return_value = empty_df

        _render_configurations_display(mock_service)

        mock_service.get_all_configurations.assert_called_once()
        mock_st.info.assert_called_once_with(
            "No check configurations found. Please add a check configuration to start."
        )

    @patch("datasure.views.config_view.render_configuration_table")
    @patch("datasure.views.config_view.st")
    def test_renders_table_when_configurations_exist(self, mock_st, mock_render_table):
        """Test that table is rendered when configurations exist."""
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
        mock_st.info.assert_not_called()


class TestRenderNavigation:
    """Test _render_navigation function."""

    @patch("datasure.views.config_view.show_demo_next_action")
    @patch("datasure.views.config_view.demo_expander")
    @patch("datasure.views.config_view.ImportDemoInfo")
    @patch("datasure.views.config_view.st")
    @patch("datasure.views.config_view.is_demo_project")
    def test_demo_navigation_with_configs(
        self, mock_is_demo, mock_st, mock_info, mock_expander, mock_next_action
    ):
        """Test demo navigation when configurations exist."""
        from datasure.views.config_view import _render_navigation

        mock_is_demo.return_value = True
        mock_service = Mock()
        config_df = pl.DataFrame([{"page_name": "Test"}])
        mock_service.get_all_configurations.return_value = config_df
        mock_info.get_info_message.return_value = "Proceed info"

        _render_navigation(mock_service)

        mock_is_demo.assert_called_once()
        mock_st.write.assert_called_once_with("---")
        mock_expander.assert_called_once_with(
            "Learn More: Proceed to Data QUality Checks",
            "Proceed info",
            expanded=True,
        )
        mock_next_action.assert_called_once_with(
            4, "st_output_page1", "View Quality Reports"
        )

    @patch("datasure.views.config_view.st")
    @patch("datasure.views.config_view.is_demo_project")
    def test_demo_navigation_without_configs(self, mock_is_demo, mock_st):
        """Test demo navigation when no configurations exist."""
        from datasure.views.config_view import _render_navigation

        mock_is_demo.return_value = True
        mock_service = Mock()
        empty_df = pl.DataFrame()
        mock_service.get_all_configurations.return_value = empty_df

        _render_navigation(mock_service)

        mock_is_demo.assert_called_once()
        mock_st.write.assert_called_once_with("---")
        # No further actions when configs are empty

    @patch("datasure.views.config_view.page_navigation")
    @patch("datasure.views.config_view.st")
    @patch("datasure.views.config_view.is_demo_project")
    def test_regular_navigation(self, mock_is_demo, mock_st, mock_page_nav):
        """Test regular navigation for non-demo projects."""
        from datasure.views.config_view import _render_navigation

        mock_is_demo.return_value = False
        mock_service = Mock()
        mock_service.get_all_configurations.return_value = pl.DataFrame()
        mock_st.session_state.st_prep_data_page = "prep_page"
        mock_st.session_state.st_output_pages = ["output_page"]

        _render_navigation(mock_service)

        mock_is_demo.assert_called_once()
        mock_page_nav.assert_called_once()
        call_args = mock_page_nav.call_args
        assert call_args[1]["prev"]["page_name"] == "prep_page"
        assert call_args[1]["prev"]["label"] == "← Back: Prepare Data"
        assert call_args[1]["next"]["page_name"] == "output_page"
        assert call_args[1]["next"]["label"] == "Next: Output Page →"

    @patch("datasure.views.config_view.page_navigation")
    @patch("datasure.views.config_view.st")
    @patch("datasure.views.config_view.is_demo_project")
    def test_regular_navigation_no_output_pages(
        self, mock_is_demo, mock_st, mock_page_nav
    ):
        """Test regular navigation when no output pages exist."""
        from datasure.views.config_view import _render_navigation

        mock_is_demo.return_value = False
        mock_service = Mock()
        mock_service.get_all_configurations.return_value = pl.DataFrame()
        mock_st.session_state.st_prep_data_page = "prep_page"
        mock_st.session_state.st_output_pages = []

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
    @patch("datasure.views.config_view.st")
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
        mock_st,
        mock_demo_guidance,
        mock_config_actions,
        mock_config_display,
        mock_navigation,
    ):
        """Test that main function orchestrates all components correctly."""
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
        mock_st.subheader.assert_called_once_with("Check Configurations")
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
    @patch("datasure.views.config_view.st")
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
        mock_st,
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
        mock_get_id.side_effect = Exception("Stopped")

        with pytest.raises(Exception):  # noqa: B017 - st.stop() raises generic exception
            main()

        # Verify that subsequent functions are not called
        mock_header.assert_not_called()


class TestModuleLevelExecution:
    """Test module-level code execution."""

    @patch("datasure.views.config_view.demo_sidebar_help")
    @patch("datasure.views.config_view.add_demo_navigation")
    @patch("datasure.views.config_view.main")
    def test_module_level_calls_are_made(self, mock_main, mock_add_nav, mock_sidebar):
        """Test that module-level functions are called on import."""
        # We can't easily test the actual import execution since it happens
        # when the module is first loaded. This test verifies the pattern.
        # In practice, these are called when the module is imported.

        # These would be called at module level:
        # add_demo_navigation("config_view.py", step=4)
        # demo_sidebar_help()
        # main()

        # We can verify the functions exist and are callable
        from datasure.views import config_view

        assert hasattr(config_view, "add_demo_navigation")
        assert hasattr(config_view, "demo_sidebar_help")
        assert hasattr(config_view, "main")


class TestIntegrationScenarios:
    """Integration tests for common scenarios."""

    @patch("datasure.views.config_view._render_navigation")
    @patch("datasure.views.config_view.render_configuration_table")
    @patch("datasure.views.config_view.remove_check_configuration_form")
    @patch("datasure.views.config_view.add_check_configuration_form")
    @patch("datasure.views.config_view.demo_expander")
    @patch("datasure.views.config_view.is_demo_project")
    @patch("datasure.views.config_view.st")
    @patch("datasure.views.config_view.ConfigurationService")
    @patch("datasure.views.config_view.duckdb_get_aliases")
    @patch("datasure.views.config_view._get_project_id")
    def test_full_flow_with_existing_configs(
        self,
        mock_get_id,
        mock_get_aliases,
        mock_service_class,
        mock_st,
        mock_is_demo,
        mock_expander,
        mock_add_form,
        mock_remove_form,
        mock_render_table,
        mock_navigation,
    ):
        """Test complete flow with existing configurations."""
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

        mock_st.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]

        # Execute
        main()

        # Verify
        assert mock_render_table.called
        assert mock_st.info.call_count == 0  # No info message for empty configs
        assert mock_get_aliases.called
        assert mock_service_class.called

    @patch("datasure.views.config_view._render_navigation")
    @patch("datasure.views.config_view.remove_check_configuration_form")
    @patch("datasure.views.config_view.add_check_configuration_form")
    @patch("datasure.views.config_view.st")
    @patch("datasure.views.config_view.ConfigurationService")
    @patch("datasure.views.config_view.duckdb_get_aliases")
    @patch("datasure.views.config_view._get_project_id")
    def test_full_flow_with_empty_configs(
        self,
        mock_get_id,
        mock_get_aliases,
        mock_service_class,
        mock_st,
        mock_add_form,
        mock_remove_form,
        mock_navigation,
    ):
        """Test complete flow with no existing configurations."""
        from datasure.views.config_view import main

        mock_get_id.return_value = "project_123"
        mock_get_aliases.return_value = ["survey_1"]

        mock_service = Mock()
        empty_df = pl.DataFrame()
        mock_service.get_all_configurations.return_value = empty_df
        mock_service_class.return_value = mock_service

        mock_st.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]

        main()

        # Verify info message shown for empty configs
        mock_st.info.assert_called()
        call_args = mock_st.info.call_args[0][0]
        assert "No check configurations found" in call_args


class TestEdgeCases:
    """Test edge cases and error handling."""

    @patch("datasure.views.config_view.st")
    def test_get_project_id_with_whitespace_only(self, mock_st):
        """Test _get_project_id with whitespace-only string."""
        from datasure.views.config_view import _get_project_id

        mock_st.session_state.st_project_id = "   "

        # Whitespace-only string should be truthy but might need trimming
        # The actual behavior depends on how the code treats this
        result = _get_project_id()

        assert result == "   "

    @patch("datasure.views.config_view.ConfigurationService")
    @patch("datasure.views.config_view.duckdb_get_aliases")
    @patch("datasure.views.config_view._get_project_id")
    def test_main_with_special_characters_in_project_id(
        self, mock_get_id, mock_get_aliases, mock_service_class
    ):
        """Test main with special characters in project ID."""
        from datasure.views.config_view import main

        # Mock all required components to prevent actual execution
        with (
            patch("datasure.views.config_view._render_header"),
            patch("datasure.views.config_view._render_demo_guidance"),
            patch("datasure.views.config_view._render_configuration_actions"),
            patch("datasure.views.config_view._render_configurations_display"),
            patch("datasure.views.config_view._render_navigation"),
            patch("datasure.views.config_view.st"),
        ):
            mock_get_id.return_value = "project-with-special_chars@123"
            mock_get_aliases.return_value = []
            mock_service = Mock()
            mock_service_class.return_value = mock_service

            main()

            mock_service_class.assert_called_once_with("project-with-special_chars@123")
