"""Tests for the onboarding utilities module."""

import json
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.utils.onboarding_utils import (
    DEMO_PROJECT_ID,
    DEMO_PROJECT_NAME,
    CheckPage,
    DemoDataGenerator,
    ImportDemoInfo,
    OnboardingSteps,
    OutputOnboardingInfo,
    create_demo_project,
    demo_container,
    demo_expander,
    demo_output_onboarding,
    get_onboarding_step,
    is_demo_complete,
    is_demo_project,
    load_csv_flexibly,
    load_demo_data,
    set_onboarding_step,
    show_demo_banner,
    show_demo_completion_message,
    show_demo_intro,
    show_next_steps,
    show_progress_indicator,
)


class TestConstants:
    """Test module constants."""

    def test_demo_project_constants(self):
        """Test that demo project constants are defined correctly."""
        assert DEMO_PROJECT_ID == "demoproject"
        assert DEMO_PROJECT_NAME == "DataSure Demo"
        assert isinstance(DEMO_PROJECT_ID, str)
        assert isinstance(DEMO_PROJECT_NAME, str)


class TestCheckPage:
    """Test the CheckPage enum."""

    def test_check_page_values(self):
        """Test that CheckPage enum has correct values."""
        assert CheckPage.SUMMARY.value == "Summary"
        assert CheckPage.SURVEY_PROGRESS.value == "Survey Progress"
        assert CheckPage.DUPLICATES.value == "Duplicates"
        assert CheckPage.MISSING_DATA.value == "Missing Data"
        assert CheckPage.OUTLIERS.value == "Outliers"
        assert CheckPage.ENUMERATOR_STATS.value == "Enumerator Stats"
        assert CheckPage.DESCRIPTIVE_STATS.value == "Descriptive Stats"
        assert CheckPage.BACK_CHECKS.value == "Back Checks"
        assert CheckPage.GPS_CHECKS.value == "GPS Checks"

    def test_check_page_member_count(self):
        """Test that CheckPage enum has correct number of members."""
        assert len(CheckPage) == 9


class TestDemoContainer:
    """Test the demo_container function."""

    @patch("datasure.utils.onboarding_utils.st")
    def test_demo_container_creates_container(self, mock_st):
        """Test that demo_container creates a streamlit container with styled text."""
        test_text = "This is a test message"
        demo_container(test_text)

        # Verify container was created
        mock_st.container.assert_called_once()

        # Verify markdown was called with unsafe_allow_html=True
        assert mock_st.markdown.call_count == 2  # Once for styled div, once for spacing

    @patch("datasure.utils.onboarding_utils.st")
    def test_demo_container_with_empty_text(self, mock_st):
        """Test demo_container with empty text."""
        demo_container("")
        mock_st.container.assert_called_once()


class TestImportDemoInfo:
    """Test the ImportDemoInfo class."""

    def test_get_info_message_valid_ids(self):
        """Test getting valid demo messages."""
        message = ImportDemoInfo.get_info_message("add_to_session_info")
        assert "successfully loaded your demo survey data" in message

        message = ImportDemoInfo.get_info_message("prepare_data_info")
        assert "Data preparation is a crucial step" in message

        message = ImportDemoInfo.get_info_message("preview_data_info")
        assert "Data import complete" in message

        message = ImportDemoInfo.get_info_message("proceed_to_config_info")
        assert "experiment with data preparation" in message

        message = ImportDemoInfo.get_info_message("demo_data_info")
        assert "Data Import Complete" in message

        message = ImportDemoInfo.get_info_message("proceed_to_hfcs_info")
        assert "ready to view your HFC reports" in message

        message = ImportDemoInfo.get_info_message("add_check_config_info")
        assert "Follow these steps to set up data quality checks" in message

        message = ImportDemoInfo.get_info_message("add_prep_steps_info")
        assert "convert the submissiondate" in message

        message = ImportDemoInfo.get_info_message("add_correction_step_info")
        assert "make corrections to the demo_survey dataset" in message

    def test_get_info_message_invalid_id(self):
        """Test getting info message with invalid ID returns default message."""
        message = ImportDemoInfo.get_info_message("invalid_message_id")
        assert message == "Invalid message ID."

    def test_class_variables_exist(self):
        """Test that all class variables are defined."""
        assert hasattr(ImportDemoInfo, "ADD_TO_SESSION_INFO")
        assert hasattr(ImportDemoInfo, "PREVIEW_DATA_INFO")
        assert hasattr(ImportDemoInfo, "PREPARE_DATA_INFO")
        assert hasattr(ImportDemoInfo, "PROCEED_TO_CONFIG_INFO")
        assert hasattr(ImportDemoInfo, "DEMO_DATA_INFO")
        assert hasattr(ImportDemoInfo, "PROCEED_TO_HFCS_INFO")
        assert hasattr(ImportDemoInfo, "ADD_CHECK_CONFIG_INFO")
        assert hasattr(ImportDemoInfo, "ADD_PREP_STEPS_INFO")
        assert hasattr(ImportDemoInfo, "ADD_CORRECTION_STEP_INFO")


class TestOnboardingSteps:
    """Test the OnboardingSteps class."""

    def test_get_step_info_valid_steps(self):
        """Test getting valid step information."""
        start_step = OnboardingSteps.get_step_info("start")
        assert start_step["step"] == 1
        assert start_step["title"] == "Start Here"
        assert start_step["icon"] == "🏠"

        import_step = OnboardingSteps.get_step_info("import")
        assert import_step["step"] == 2
        assert import_step["title"] == "Import Data"

        prepare_step = OnboardingSteps.get_step_info("prepare")
        assert prepare_step["step"] == 3

        configure_step = OnboardingSteps.get_step_info("configure")
        assert configure_step["step"] == 4

        reports_step = OnboardingSteps.get_step_info("reports")
        assert reports_step["step"] == 5

        correct_step = OnboardingSteps.get_step_info("correct")
        assert correct_step["step"] == 6

    def test_get_step_info_invalid_step(self):
        """Test getting step info with invalid step name."""
        result = OnboardingSteps.get_step_info("invalid_step")
        assert result == {}

    def test_get_all_steps(self):
        """Test getting all onboarding steps."""
        all_steps = OnboardingSteps.get_all_steps()
        assert len(all_steps) == 6
        assert all_steps[0]["step"] == 1
        assert all_steps[5]["step"] == 6

    def test_get_all_steps_order(self):
        """Test that all steps are in correct order."""
        all_steps = OnboardingSteps.get_all_steps()
        for i, step in enumerate(all_steps, start=1):
            assert step["step"] == i

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.demo_container")
    def test_get_guidance_valid_step(self, mock_demo_container, mock_st):
        """Test getting guidance for valid step."""
        OnboardingSteps.get_guidance(1)
        mock_st.expander.assert_called_once()
        mock_demo_container.assert_called_once()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.demo_container")
    def test_get_guidance_all_steps(self, mock_demo_container, mock_st):
        """Test getting guidance for all valid steps."""
        for step_num in range(1, 7):
            OnboardingSteps.get_guidance(step_num)
        assert mock_st.expander.call_count == 6

    @patch("datasure.utils.onboarding_utils.st")
    def test_get_guidance_invalid_step(self, mock_st):
        """Test that getting guidance for invalid step raises ValueError."""
        with pytest.raises(ValueError, match="Invalid step: 99"):
            OnboardingSteps.get_guidance(99)

    def test_class_variables_exist(self):
        """Test that all class variables are defined."""
        assert hasattr(OnboardingSteps, "START")
        assert hasattr(OnboardingSteps, "IMPORT")
        assert hasattr(OnboardingSteps, "PREPARE")
        assert hasattr(OnboardingSteps, "CONFIGURE")
        assert hasattr(OnboardingSteps, "OUTPUTS")
        assert hasattr(OnboardingSteps, "CORRECT")


class TestOutputOnboardingInfo:
    """Test the OutputOnboardingInfo class."""

    def test_get_onboarding_message_summary(self):
        """Test getting onboarding message for summary tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "summary", "summary_report"
        )
        assert message["title"] == "Data Quality Summary"
        assert "overview of the data quality checks" in message["content"]

        # Test other summary messages
        message = OutputOnboardingInfo.get_onboarding_message(
            "summary", "summary_settings"
        )
        assert message["title"] == "Summary Settings"

        message = OutputOnboardingInfo.get_onboarding_message(
            "summary", "summary_data_summary"
        )
        assert message["title"] == "Data Summary"

    def test_get_onboarding_message_progress(self):
        """Test getting onboarding message for progress tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "progress", "progress_report"
        )
        assert message["title"] == "Progress Report"

        message = OutputOnboardingInfo.get_onboarding_message(
            "progress", "progress_report_settings"
        )
        assert message["title"] == "Progress Settings"

    def test_get_onboarding_message_duplicates(self):
        """Test getting onboarding message for duplicates tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "duplicates", "duplicate_report"
        )
        assert message["title"] == "Duplicate Records Report"

    def test_get_onboarding_message_missing(self):
        """Test getting onboarding message for missing tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "missing", "missing_report"
        )
        assert message["title"] == "Missing Data Report"

    def test_get_onboarding_message_outliers(self):
        """Test getting onboarding message for outliers tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "outliers", "outlier_report"
        )
        assert message["title"] == "Outliers Report"

    def test_get_onboarding_message_enumerators(self):
        """Test getting onboarding message for enumerators tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "enumerators", "enumerator_report"
        )
        assert message["title"] == "Enumerator Stats Report"

    def test_get_onboarding_message_descriptive_stats(self):
        """Test getting onboarding message for descriptive stats tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "descriptive_stats", "descriptive_report"
        )
        assert message["title"] == "Descriptive Statistics Report"

    def test_get_onboarding_message_backchecks(self):
        """Test getting onboarding message for backchecks tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "backchecks", "backchecks_report"
        )
        assert message["title"] == "Back Checks Report"

    def test_get_onboarding_message_gpschecks(self):
        """Test getting onboarding message for GPS checks tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "gpschecks", "gpschecks_report"
        )
        assert message["title"] == "GPS Checks Report"

    def test_get_onboarding_message_invalid_tab(self):
        """Test getting onboarding message with invalid tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "invalid_tab", "some_message"
        )
        assert message == "Invalid Message"

    def test_get_onboarding_message_invalid_message_id(self):
        """Test getting onboarding message with invalid message ID."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "summary", "invalid_message_id"
        )
        assert message == "Invalid Message"

    def test_class_variables_exist(self):
        """Test that all class variables are defined."""
        assert hasattr(OutputOnboardingInfo, "SUMMARY")
        assert hasattr(OutputOnboardingInfo, "PROGRESS")
        assert hasattr(OutputOnboardingInfo, "DUPLICATES")
        assert hasattr(OutputOnboardingInfo, "MISSING")
        assert hasattr(OutputOnboardingInfo, "OUTLIERS")
        assert hasattr(OutputOnboardingInfo, "ENUMERATORS")
        assert hasattr(OutputOnboardingInfo, "DESCRIPTIVE_STATS")
        assert hasattr(OutputOnboardingInfo, "BACKCHECKS")
        assert hasattr(OutputOnboardingInfo, "GPSCHECKS")


class TestDemoOutputOnboarding:
    """Test the demo_output_onboarding decorator."""

    @patch("datasure.utils.onboarding_utils.is_demo_project")
    @patch("datasure.utils.onboarding_utils.demo_expander")
    def test_decorator_with_demo_project(self, mock_demo_expander, mock_is_demo):
        """Test decorator when in demo mode."""
        mock_is_demo.return_value = True

        @demo_output_onboarding("summary")
        def summary_report():
            return "executed"

        result = summary_report()
        assert result == "executed"
        mock_demo_expander.assert_called_once()

    @patch("datasure.utils.onboarding_utils.is_demo_project")
    @patch("datasure.utils.onboarding_utils.demo_expander")
    def test_decorator_without_demo_project(self, mock_demo_expander, mock_is_demo):
        """Test decorator when not in demo mode."""
        mock_is_demo.return_value = False

        @demo_output_onboarding("summary")
        def summary_report():
            return "executed"

        result = summary_report()
        assert result == "executed"
        mock_demo_expander.assert_not_called()

    @patch("datasure.utils.onboarding_utils.is_demo_project")
    @patch("datasure.utils.onboarding_utils.demo_expander")
    def test_decorator_with_args_and_kwargs(self, mock_demo_expander, mock_is_demo):
        """Test decorator with function that has arguments."""
        mock_is_demo.return_value = True

        @demo_output_onboarding("summary")
        def summary_report(arg1, arg2, kwarg1=None):
            return f"{arg1}-{arg2}-{kwarg1}"

        result = summary_report("a", "b", kwarg1="c")
        assert result == "a-b-c"


class TestDemoProjectFunctions:
    """Test demo project state functions."""

    @patch("datasure.utils.onboarding_utils.st")
    def test_is_demo_project_true(self, mock_st):
        """Test is_demo_project returns True when project ID matches."""
        mock_st.session_state.get.return_value = DEMO_PROJECT_ID
        assert is_demo_project() is True

    @patch("datasure.utils.onboarding_utils.st")
    def test_is_demo_project_false(self, mock_st):
        """Test is_demo_project returns False when project ID doesn't match."""
        mock_st.session_state.get.return_value = "other_project"
        assert is_demo_project() is False

    @patch("datasure.utils.onboarding_utils.st")
    def test_set_onboarding_step(self, mock_st):
        """Test setting onboarding step."""
        mock_st.session_state = {}
        set_onboarding_step(3)
        assert mock_st.session_state["onboarding_step"] == 3

    @patch("datasure.utils.onboarding_utils.st")
    def test_get_onboarding_step_exists(self, mock_st):
        """Test getting onboarding step when it exists."""
        mock_st.session_state = {"onboarding_step": 4}
        assert get_onboarding_step() == 4

    @patch("datasure.utils.onboarding_utils.st")
    def test_get_onboarding_step_default(self, mock_st):
        """Test getting onboarding step returns default when not set."""
        # Mock session_state to return None for the onboarding_step key
        mock_session = MagicMock()
        mock_session.__getitem__.return_value = None
        mock_st.session_state = mock_session

        result = get_onboarding_step()
        # When session_state["onboarding_step"] returns None, "None or 1" evaluates to 1
        assert result == 1

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.get_onboarding_step")
    def test_is_demo_complete_true(self, mock_get_step, mock_st):
        """Test is_demo_complete returns True when all steps completed."""
        mock_get_step.return_value = 6
        assert is_demo_complete() is True

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.get_onboarding_step")
    def test_is_demo_complete_false(self, mock_get_step, mock_st):
        """Test is_demo_complete returns False when steps incomplete."""
        mock_get_step.return_value = 3
        assert is_demo_complete() is False

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.get_onboarding_step")
    def test_is_demo_complete_exceeds_steps(self, mock_get_step, mock_st):
        """Test is_demo_complete when step exceeds total steps."""
        mock_get_step.return_value = 10
        assert is_demo_complete() is True


class TestDemoUIFunctions:
    """Test demo UI display functions."""

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    @patch("datasure.utils.onboarding_utils.get_onboarding_step")
    def test_show_progress_indicator_demo_mode(
        self, mock_get_step, mock_is_demo, mock_st
    ):
        """Test progress indicator displays in demo mode."""
        mock_is_demo.return_value = True
        mock_get_step.return_value = 2
        mock_st.columns.return_value = [MagicMock() for _ in range(6)]

        show_progress_indicator()

        mock_st.markdown.assert_called()
        mock_st.columns.assert_called()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    def test_show_progress_indicator_non_demo(self, mock_is_demo, mock_st):
        """Test progress indicator doesn't display when not in demo mode."""
        mock_is_demo.return_value = False

        show_progress_indicator()

        mock_st.markdown.assert_not_called()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    @patch("datasure.utils.onboarding_utils.get_onboarding_step")
    def test_show_progress_indicator_step_states(
        self, mock_get_step, mock_is_demo, mock_st
    ):
        """Test progress indicator shows different states for current, completed,
        and future steps.
        """
        mock_is_demo.return_value = True
        mock_get_step.return_value = 3

        # Create mock columns with context manager support
        mock_cols = []
        for _ in range(6):
            mock_col = MagicMock()
            mock_col.__enter__ = MagicMock(return_value=mock_col)
            mock_col.__exit__ = MagicMock(return_value=False)
            mock_cols.append(mock_col)

        mock_st.columns.return_value = mock_cols

        show_progress_indicator()

        # Verify that markdown was called for each step
        assert mock_st.markdown.call_count >= 6

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.demo_container")
    def test_show_demo_intro(self, mock_demo_container, mock_st):
        """Test demo intro displays correctly."""
        show_demo_intro()
        mock_demo_container.assert_called_once()
        args = mock_demo_container.call_args[0][0]
        assert "Start here" in args
        assert "Importing survey data" in args

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    def test_show_demo_banner_demo_mode(self, mock_is_demo, mock_st):
        """Test demo banner displays in demo mode."""
        mock_is_demo.return_value = True

        show_demo_banner()

        mock_st.info.assert_called_once()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    def test_show_demo_banner_non_demo(self, mock_is_demo, mock_st):
        """Test demo banner doesn't display when not in demo mode."""
        mock_is_demo.return_value = False

        show_demo_banner()

        mock_st.info.assert_not_called()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    def test_show_next_steps_middle_step(self, mock_is_demo, mock_st):
        """Test showing next steps for middle onboarding step."""
        mock_is_demo.return_value = True

        show_next_steps(2)

        mock_st.markdown.assert_called()
        mock_st.info.assert_called()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    def test_show_next_steps_first_step(self, mock_is_demo, mock_st):
        """Test showing next steps for first step."""
        mock_is_demo.return_value = True

        show_next_steps(1)

        # Should show special message for step 1
        assert mock_st.markdown.call_count >= 2

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    def test_show_next_steps_completed(self, mock_is_demo, mock_st):
        """Test showing next steps when all steps completed."""
        mock_is_demo.return_value = True
        mock_st.button.return_value = False

        show_next_steps(6)

        mock_st.success.assert_called_once()
        mock_st.button.assert_called()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    def test_show_next_steps_non_demo(self, mock_is_demo, mock_st):
        """Test next steps doesn't display when not in demo mode."""
        mock_is_demo.return_value = False

        show_next_steps(2)

        mock_st.markdown.assert_not_called()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    @patch("datasure.utils.onboarding_utils.is_demo_complete")
    def test_show_demo_completion_message_complete(
        self, mock_is_complete, mock_is_demo, mock_st
    ):
        """Test completion message displays when demo is complete."""
        mock_is_demo.return_value = True
        mock_is_complete.return_value = True
        mock_st.button.return_value = False
        mock_st.columns.return_value = [MagicMock(), MagicMock()]

        show_demo_completion_message()

        mock_st.balloons.assert_called_once()
        mock_st.success.assert_called_once()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    @patch("datasure.utils.onboarding_utils.is_demo_complete")
    def test_show_demo_completion_message_restart_button(
        self, mock_is_complete, mock_is_demo, mock_st
    ):
        """Test completion message restart button click."""
        mock_is_demo.return_value = True
        mock_is_complete.return_value = True
        mock_st.button.side_effect = [True, False]  # First button clicked
        mock_st.columns.return_value = [MagicMock(), MagicMock()]

        with patch("datasure.utils.onboarding_utils.set_onboarding_step") as mock_set:
            show_demo_completion_message()
            mock_set.assert_called_with(1)
            mock_st.rerun.assert_called_once()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    @patch("datasure.utils.onboarding_utils.is_demo_complete")
    def test_show_demo_completion_message_create_project_button(
        self, mock_is_complete, mock_is_demo, mock_st
    ):
        """Test completion message create new project button click."""
        mock_is_demo.return_value = True
        mock_is_complete.return_value = True
        mock_st.button.side_effect = [False, True]  # Second button clicked
        mock_st.columns.return_value = [MagicMock(), MagicMock()]

        # Use MagicMock for session_state to support attribute assignment
        mock_session_state = MagicMock()
        mock_session_state.onboarding_step = 6
        mock_st.session_state = mock_session_state

        show_demo_completion_message()

        assert mock_st.session_state.st_project_id == ""
        mock_st.switch_page.assert_called_with("pages/start_view.py")

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    @patch("datasure.utils.onboarding_utils.is_demo_complete")
    def test_show_demo_completion_message_non_demo(
        self, mock_is_complete, mock_is_demo, mock_st
    ):
        """Test completion message doesn't display when not in demo mode."""
        mock_is_demo.return_value = False
        mock_is_complete.return_value = True

        show_demo_completion_message()

        mock_st.balloons.assert_not_called()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    @patch("datasure.utils.onboarding_utils.is_demo_complete")
    def test_show_demo_completion_message_incomplete(
        self, mock_is_complete, mock_is_demo, mock_st
    ):
        """Test completion message doesn't display when demo incomplete."""
        mock_is_demo.return_value = True
        mock_is_complete.return_value = False

        show_demo_completion_message()

        mock_st.balloons.assert_not_called()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    @patch("datasure.utils.onboarding_utils.demo_container")
    def test_demo_expander_demo_mode(self, mock_demo_container, mock_is_demo, mock_st):
        """Test demo expander displays in demo mode."""
        mock_is_demo.return_value = True

        demo_expander("Test Title", "Test Content")

        mock_st.expander.assert_called_once()
        mock_demo_container.assert_called_once_with("Test Content")

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    @patch("datasure.utils.onboarding_utils.demo_container")
    def test_demo_expander_collapsed(self, mock_demo_container, mock_is_demo, mock_st):
        """Test demo expander with expanded=False."""
        mock_is_demo.return_value = True

        demo_expander("Test Title", "Test Content", expanded=False)

        # Verify expander was called with expanded=False
        call_args = mock_st.expander.call_args
        assert call_args[1]["expanded"] is False

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    def test_demo_expander_non_demo(self, mock_is_demo, mock_st):
        """Test demo expander doesn't display when not in demo mode."""
        mock_is_demo.return_value = False

        demo_expander("Test Title", "Test Content")

        mock_st.expander.assert_not_called()


class TestCreateDemoProject:
    """Test the create_demo_project function."""

    @patch("datasure.utils.onboarding_utils.get_cache_path")
    def test_create_demo_project_new(self, mock_get_cache_path, tmp_path):
        """Test creating a new demo project."""
        project_path = tmp_path / "demo_project"
        projects_file = tmp_path / "projects.json"

        def get_cache_path_side_effect(path):
            if path == DEMO_PROJECT_ID:
                return project_path
            elif path == "projects.json":
                return projects_file
            return tmp_path / path

        mock_get_cache_path.side_effect = get_cache_path_side_effect

        result = create_demo_project()

        assert result == DEMO_PROJECT_ID
        assert project_path.exists()
        assert (project_path / "data").exists()
        assert (project_path / "settings").exists()
        assert projects_file.exists()

        # Verify projects.json content
        with open(projects_file) as f:
            projects = json.load(f)
        assert DEMO_PROJECT_ID in projects
        assert projects[DEMO_PROJECT_ID]["name"] == DEMO_PROJECT_NAME
        assert projects[DEMO_PROJECT_ID]["is_demo"] is True

    @patch("datasure.utils.onboarding_utils.get_cache_path")
    def test_create_demo_project_existing(self, mock_get_cache_path, tmp_path):
        """Test creating demo project when it already exists."""
        project_path = tmp_path / "demo_project"
        projects_file = tmp_path / "projects.json"

        # Create existing project structure
        project_path.mkdir(parents=True)
        (project_path / "data").mkdir()
        (project_path / "settings").mkdir()

        # Create existing projects.json
        existing_projects = {"other_project": {"name": "Other Project"}}
        with open(projects_file, "w") as f:
            json.dump(existing_projects, f)

        def get_cache_path_side_effect(path):
            if path == DEMO_PROJECT_ID:
                return project_path
            elif path == "projects.json":
                return projects_file
            return tmp_path / path

        mock_get_cache_path.side_effect = get_cache_path_side_effect

        result = create_demo_project()

        assert result == DEMO_PROJECT_ID

        # Verify projects.json was updated
        with open(projects_file) as f:
            projects = json.load(f)
        assert DEMO_PROJECT_ID in projects
        assert "other_project" in projects  # Existing project preserved


class TestDemoDataGenerator:
    """Test the DemoDataGenerator class."""

    def test_demo_data_generator_initialization(self):
        """Test DemoDataGenerator initialization."""
        df = pl.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
        generator = DemoDataGenerator(df)
        assert generator.df.height == 3

    def test_gen_starttime(self):
        """Test generating starttime column."""
        df = pl.DataFrame({"id": [1, 2, 3]})
        generator = DemoDataGenerator(df)
        result_df = generator._gen_starttime()

        assert "starttime" in result_df.columns
        assert result_df.height == 3

    def test_gen_endtime(self):
        """Test generating endtime column."""
        df = pl.DataFrame({"id": [1, 2, 3]})
        generator = DemoDataGenerator(df)
        generator._gen_starttime()
        result_df = generator._gen_endtime()

        assert "endtime" in result_df.columns
        assert result_df.height == 3

    def test_gen_submissiondate(self):
        """Test generating submissiondate column."""
        df = pl.DataFrame({"id": [1, 2, 3]})
        generator = DemoDataGenerator(df)
        generator._gen_starttime()
        generator._gen_endtime()
        result_df = generator._gen_submissiondate()

        assert "submissiondate" in result_df.columns
        assert result_df.height == 3

    def test_gen_dates(self):
        """Test generating all date columns."""
        df = pl.DataFrame({"id": [1, 2, 3]})
        generator = DemoDataGenerator(df)
        result_df = generator._gen_dates()

        assert "starttime" in result_df.columns
        assert "endtime" in result_df.columns
        assert "submissiondate" in result_df.columns
        # Verify dates are strings
        assert result_df["starttime"].dtype == pl.Utf8

    def test_gen_consent_status(self):
        """Test generating consent status column."""
        df = pl.DataFrame({"id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
        generator = DemoDataGenerator(df)
        result_df = generator._gen_consent_status()

        assert "consent" in result_df.columns
        assert result_df.height == 10
        # Check that values are either 'yes' or 'no'
        consent_values = result_df["consent"].to_list()
        assert all(val in ["yes", "no"] for val in consent_values)
        # Most should be 'yes' given 98% weight
        assert consent_values.count("yes") >= 8

    def test_gen_completion_status(self):
        """Test generating completion status column."""
        df = pl.DataFrame({"id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
        generator = DemoDataGenerator(df)
        result_df = generator._gen_completion_status()

        assert "completion_status" in result_df.columns
        assert result_df.height == 10
        # Check that values are either 'complete' or 'incomplete'
        status_values = result_df["completion_status"].to_list()
        assert all(val in ["complete", "incomplete"] for val in status_values)

    def test_add_demo_fields_survey(self):
        """Test adding all demo fields for survey data."""
        df = pl.DataFrame({"id": [1, 2, 3]})
        generator = DemoDataGenerator(df)
        result_df = generator.add_demo_fields("survey")

        assert "starttime" in result_df.columns
        assert "endtime" in result_df.columns
        assert "submissiondate" in result_df.columns
        assert "consent" in result_df.columns
        assert "completion_status" in result_df.columns

    def test_add_demo_fields_backcheck(self):
        """Test adding demo fields for backcheck data."""
        df = pl.DataFrame({"id": [1, 2, 3]})
        generator = DemoDataGenerator(df)
        result_df = generator.add_demo_fields("backcheck")

        assert "starttime" in result_df.columns
        assert "endtime" in result_df.columns
        assert "submissiondate" in result_df.columns
        assert "consent" not in result_df.columns
        assert "completion_status" not in result_df.columns

    def test_add_demo_fields_default(self):
        """Test add_demo_fields with default datatype."""
        df = pl.DataFrame({"id": [1, 2]})
        generator = DemoDataGenerator(df)
        result_df = generator.add_demo_fields()  # Default is "survey"

        assert "consent" in result_df.columns
        assert "completion_status" in result_df.columns


class TestLoadCsvFlexibly:
    """Test the load_csv_flexibly function."""

    @patch("datasure.utils.onboarding_utils.pl.read_csv")
    @patch("datasure.utils.onboarding_utils.st")
    def test_load_csv_flexibly_success(self, mock_st, mock_read_csv, tmp_path):
        """Test successful CSV loading with polars."""
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("col1,col2\n1,a\n2,b\n")

        mock_df = pl.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        mock_read_csv.return_value = mock_df

        result = load_csv_flexibly(csv_path)

        assert result.height == 2
        mock_read_csv.assert_called_once()

    @patch("datasure.utils.onboarding_utils.pl.read_csv")
    @patch("datasure.utils.onboarding_utils.pd.read_csv")
    @patch("datasure.utils.onboarding_utils.pl.from_pandas")
    @patch("datasure.utils.onboarding_utils.st")
    def test_load_csv_flexibly_fallback_to_pandas(
        self, mock_st, mock_from_pandas, mock_pd_read, mock_pl_read, tmp_path
    ):
        """Test fallback to pandas when polars fails."""
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("col1,col2\n1,a\n2,b\n")

        # Make polars fail
        mock_pl_read.side_effect = Exception("Polars error")

        # Make pandas succeed
        import pandas as pd

        pandas_df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        mock_pd_read.return_value = pandas_df

        polars_df = pl.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        mock_from_pandas.return_value = polars_df

        result = load_csv_flexibly(csv_path)

        assert result.height == 2
        mock_st.error.assert_called()
        mock_pd_read.assert_called_once()

    @patch("datasure.utils.onboarding_utils.pl.read_csv")
    @patch("datasure.utils.onboarding_utils.pd.read_csv")
    @patch("datasure.utils.onboarding_utils.st")
    def test_load_csv_flexibly_both_fail(
        self, mock_st, mock_pd_read, mock_pl_read, tmp_path
    ):
        """Test when both polars and pandas fail."""
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("invalid,csv\ndata")

        # Make both fail
        polars_error = Exception("Polars error")
        mock_pl_read.side_effect = polars_error
        mock_pd_read.side_effect = Exception("Pandas error")

        with pytest.raises(Exception):  # noqa: B017
            load_csv_flexibly(csv_path)

        assert mock_st.error.call_count == 2


class TestLoadDemoData:
    """Test the load_demo_data function."""

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.load_csv_flexibly")
    @patch("datasure.utils.onboarding_utils.DemoDataGenerator")
    @patch("datasure.utils.onboarding_utils.duckdb_save_table")
    @patch("datasure.utils.onboarding_utils.duckdb_remove_table")
    @patch("datasure.utils.onboarding_utils.pl.read_csv")
    @patch("datasure.utils.onboarding_utils.Path")
    def test_load_demo_data_success(
        self,
        mock_path,
        mock_pl_read,
        mock_remove,
        mock_save,
        mock_generator_class,
        mock_load_csv,
        mock_st,
    ):
        """Test successful demo data loading."""
        # Setup mocks
        mock_file = MagicMock()
        mock_assets_dir = MagicMock()
        mock_survey_path = MagicMock()
        mock_backcheck_path = MagicMock()

        mock_survey_path.exists.return_value = True
        mock_backcheck_path.exists.return_value = True

        mock_file.parent.parent = mock_assets_dir
        mock_assets_dir.__truediv__.side_effect = [
            mock_survey_path,
            mock_backcheck_path,
        ]
        mock_path.return_value = mock_file

        # Mock DataFrames
        survey_df = pl.DataFrame({"id": [1, 2], "name": ["a", "b"]})
        backcheck_df = pl.DataFrame({"id": [1], "name": ["x"]})

        mock_load_csv.side_effect = [survey_df, backcheck_df]
        mock_pl_read.return_value = backcheck_df

        # Mock generator
        mock_generator = MagicMock()
        mock_generator.add_demo_fields.return_value = survey_df
        mock_generator_class.return_value = mock_generator

        # Mock session state - use MagicMock to support attribute assignment
        mock_st.session_state = MagicMock()

        result = load_demo_data()

        assert result is True
        assert mock_st.session_state.st_raw_dataset_list == [
            "demo_survey",
            "demo_backcheck",
        ]

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.Path")
    def test_load_demo_data_files_not_found(self, mock_path, mock_st):
        """Test load_demo_data when files don't exist."""
        # Setup mocks for files not existing
        mock_file = MagicMock()
        mock_assets_dir = MagicMock()
        mock_survey_path = MagicMock()
        mock_backcheck_path = MagicMock()

        mock_survey_path.exists.return_value = False
        mock_backcheck_path.exists.return_value = False

        mock_file.parent.parent = mock_assets_dir
        mock_assets_dir.__truediv__.side_effect = [
            mock_survey_path,
            mock_backcheck_path,
        ]
        mock_path.return_value = mock_file

        result = load_demo_data()

        assert result is False
        mock_st.error.assert_called()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.load_csv_flexibly")
    @patch("datasure.utils.onboarding_utils.Path")
    def test_load_demo_data_survey_load_fails(self, mock_path, mock_load_csv, mock_st):
        """Test load_demo_data when survey loading fails."""
        # Setup paths
        mock_file = MagicMock()
        mock_assets_dir = MagicMock()
        mock_survey_path = MagicMock()
        mock_backcheck_path = MagicMock()

        mock_survey_path.exists.return_value = True
        mock_backcheck_path.exists.return_value = True

        mock_file.parent.parent = mock_assets_dir
        mock_assets_dir.__truediv__.side_effect = [
            mock_survey_path,
            mock_backcheck_path,
        ]
        mock_path.return_value = mock_file

        # Make survey loading fail
        mock_load_csv.side_effect = Exception("Load error")

        result = load_demo_data()

        assert result is False

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.load_csv_flexibly")
    @patch("datasure.utils.onboarding_utils.Path")
    def test_load_demo_data_backcheck_load_fails(
        self, mock_path, mock_load_csv, mock_st
    ):
        """Test load_demo_data when backcheck loading fails."""
        # Setup paths
        mock_file = MagicMock()
        mock_assets_dir = MagicMock()
        mock_survey_path = MagicMock()
        mock_backcheck_path = MagicMock()

        mock_survey_path.exists.return_value = True
        mock_backcheck_path.exists.return_value = True

        mock_file.parent.parent = mock_assets_dir
        mock_assets_dir.__truediv__.side_effect = [
            mock_survey_path,
            mock_backcheck_path,
        ]
        mock_path.return_value = mock_file

        # First call succeeds (survey), second fails (backcheck)
        survey_df = pl.DataFrame({"id": [1, 2]})
        mock_load_csv.side_effect = [survey_df, Exception("Backcheck error")]

        result = load_demo_data()

        assert result is False
