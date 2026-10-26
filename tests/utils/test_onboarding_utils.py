"""Tests for the onboarding utilities module."""

import importlib
import json
import pkgutil
import re
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.utils.onboarding_utils import (
    DEMO_DUPLICATES,
    DEMO_GUIDANCE_COLUMNS,
    DEMO_LAND_CORRECTION,
    DEMO_OUTPUT_FUNCTIONS,
    DEMO_PROJECT_ID,
    DEMO_PROJECT_NAME,
    DEMO_REPEAT_SUBMISSION,
    DemoColumn,
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


class TestDemoContainer:
    """Test the demo_container function."""

    @patch("datasure.utils.onboarding_utils.st")
    def test_demo_container_creates_container(self, mock_st):
        """Test that demo_container renders an info box with the given text."""
        test_text = "This is a test message"
        demo_container(test_text)

        mock_st.info.assert_called_once_with(test_text)

    @patch("datasure.utils.onboarding_utils.st")
    def test_demo_container_with_empty_text(self, mock_st):
        """Test demo_container with empty text."""
        demo_container("")
        mock_st.info.assert_called_once_with("")


class TestImportDemoInfo:
    """Test the ImportDemoInfo class."""

    def test_get_info_message_valid_ids(self):
        """Test getting valid demo messages."""
        message = ImportDemoInfo.get_info_message("add_to_session_info")
        assert "loaded successfully" in message

        message = ImportDemoInfo.get_info_message("preview_data_info")
        assert "loaded and ready" in message

        message = ImportDemoInfo.get_info_message("proceed_to_config_info")
        assert "experiment with data preparation" in message

        message = ImportDemoInfo.get_info_message("proceed_to_hfcs_info")
        assert "ready for quality analysis" in message

    def test_get_info_message_invalid_id(self):
        """Test getting info message with invalid ID returns default message."""
        message = ImportDemoInfo.get_info_message("invalid_message_id")
        assert message == "Invalid message ID."

    def test_class_variables_exist(self):
        """Test that all class variables are defined."""
        assert hasattr(ImportDemoInfo, "ADD_TO_SESSION_INFO")
        assert hasattr(ImportDemoInfo, "PREVIEW_DATA_INFO")
        assert hasattr(ImportDemoInfo, "PROCEED_TO_CONFIG_INFO")
        assert hasattr(ImportDemoInfo, "PROCEED_TO_HFCS_INFO")

    def test_every_message_is_shown_somewhere(self, datasure_sources):
        """Every ImportDemoInfo message is requested by a page in datasure."""
        requested = {
            message_id
            for _path, text in datasure_sources
            for message_id in re.findall(r"get_info_message\(\s*\"([a-z_]+)\"", text)
        }
        constants = {
            name
            for name, value in vars(ImportDemoInfo).items()
            if name.isupper() and isinstance(value, str)
        }
        assert constants, "no ImportDemoInfo messages found"
        unused = sorted(name for name in constants if name.lower() not in requested)
        assert not unused, f"demo messages never shown: {unused}"


class TestOnboardingSteps:
    """Test the OnboardingSteps class."""

    def test_get_step_info_valid_steps(self):
        """Test getting valid step information."""
        start_step = OnboardingSteps.get_step_info("start")
        assert start_step["step"] == 1
        assert start_step["title"] == "Start Here"
        assert start_step["icon"] == ":material/home:"

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
        assert len(all_steps) == 7
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
            "duplicates", "duplicates_report_settings"
        )
        assert message["title"] == "Duplicates Settings"
        assert "Survey Key" in message["content"]

    def test_get_onboarding_message_missing(self):
        """Test getting onboarding message for missing tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "missing", "missing_summary"
        )
        assert message["title"] == "Missing Values"
        assert "missing data" in message["content"].lower()

    def test_get_onboarding_message_outliers(self):
        """Test getting onboarding message for outliers tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "outliers", "outliers_report_settings"
        )
        assert message["title"] == "Outliers & Constraints Settings"
        assert "Survey Key" in message["content"]

    def test_get_onboarding_message_enumerators(self):
        """Test getting onboarding message for enumerators tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "enumerators", "enumerator_report_settings"
        )
        assert message["title"] == "Enumerator Statistics Settings"
        assert "Duration Column" in message["content"]

    def test_get_onboarding_message_descriptive_stats(self):
        """Test getting onboarding message for descriptive stats tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "descriptive_stats", "descriptive_report"
        )
        assert message["title"] == "Descriptive Statistics"
        assert "distribution" in message["content"].lower()

    def test_get_onboarding_message_backchecks(self):
        """Test getting onboarding message for backchecks tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "backchecks", "backchecks_report_settings"
        )
        assert message["title"] == "Backcheck Analysis Settings"
        assert "Survey Key" in message["content"]

    def test_get_onboarding_message_gpschecks(self):
        """Test getting onboarding message for GPS checks tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "gpschecks", "gpschecks_report_settings"
        )
        assert message["title"] == "GPS Checks Settings"
        assert "Survey Key" in message["content"]

    def test_get_onboarding_message_summary_submissions(self):
        """Test summary_submissions entry."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "summary", "summary_submissions"
        )
        assert message["title"] == "Submission Details"
        assert "Today" in message["content"]

    def test_get_onboarding_message_summary_progress(self):
        """Test summary_progress entry."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "summary", "summary_progress"
        )
        assert message["title"] == "Progress"
        assert "Submission Progress" in message["content"]

    def test_get_onboarding_message_summary_check_health(self):
        """Test summary_check_health entry, which replaced Data Quality."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "summary", "summary_check_health"
        )
        assert message["title"] == "Check health"
        assert "Open →" in message["content"]
        assert (
            OutputOnboardingInfo.get_onboarding_message(
                "summary", "summary_data_quality"
            )
            is None
        )

    def test_get_onboarding_message_progress_display_summary(self):
        """Test display_progress_summary entry."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "progress", "display_progress_summary"
        )
        assert message["title"] == "Progress Summary"
        assert "Submission Progress" in message["content"]

    def test_get_onboarding_message_progress_display_overtime(self):
        """Test display_progress_overtime entry."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "progress", "display_progress_overtime"
        )
        assert message["title"] == "Progress Over Time"
        assert "green" in message["content"].lower()

    def test_get_onboarding_message_progress_attempted_interviews(self):
        """Test display_attempted_interviews entry."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "progress", "display_attempted_interviews"
        )
        assert message["title"] == "Attempted Interviews"
        assert "Unique IDs" in message["content"]

    def test_get_onboarding_message_progress_chart(self):
        """Test display_progress_chart entry."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "progress", "display_progress_chart"
        )
        assert message["title"] == "Consent and Completion Progress"
        assert "Consent Rate" in message["content"]

    def test_get_onboarding_message_missing_columns(self):
        """Test missing_columns entry."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "missing", "missing_columns"
        )
        assert message["title"] == "Missingness by Column"
        assert "Total Missing" in message["content"]

    def test_get_onboarding_message_missing_compare(self):
        """Test missing_compare entry."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "missing", "missing_compare"
        )
        assert message["title"] == "Compare Missing Data Within Groups"
        assert "group" in message["content"].lower()

    def test_get_onboarding_message_missing_over_time(self):
        """Test missing_over_time entry."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "missing", "missing_over_time"
        )
        assert message["title"] == "Missingness Over Time"
        assert "over time" in message["content"].lower()

    def test_get_onboarding_message_missing_correlation(self):
        """Test missing_correlation entry."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "missing", "missing_correlation"
        )
        assert message["title"] == "Nullity Correlation"
        assert "heatmap" in message["content"].lower()

    def test_get_onboarding_message_missing_matrix(self):
        """Test missing_matrix entry."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "missing", "missing_matrix"
        )
        assert message["title"] == "Nullity Matrix"
        assert "missing" in message["content"].lower()

    def test_get_onboarding_message_invalid_tab(self):
        """Test getting onboarding message with invalid tab."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "invalid_tab", "some_message"
        )
        assert message is None

    def test_get_onboarding_message_invalid_message_id(self):
        """Test getting onboarding message with invalid message ID."""
        message = OutputOnboardingInfo.get_onboarding_message(
            "summary", "invalid_message_id"
        )
        assert message is None

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
        def summary_settings():
            return "executed"

        result = summary_settings()
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

    @pytest.mark.parametrize("is_demo", [False, True])
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    @patch("datasure.utils.onboarding_utils.demo_expander")
    def test_unknown_function_still_runs(
        self, mock_demo_expander, mock_is_demo, is_demo
    ):
        """A function with no message entry runs, with no guidance, in any project."""
        mock_is_demo.return_value = is_demo

        @demo_output_onboarding("summary")
        def renamed_report():
            return "executed"

        assert renamed_report() == "executed"
        mock_demo_expander.assert_not_called()

    @patch("datasure.utils.onboarding_utils.is_demo_project", return_value=True)
    @patch("datasure.utils.onboarding_utils.demo_expander")
    def test_unknown_function_warns_once_in_demo(
        self, mock_demo_expander, mock_is_demo, caplog
    ):
        """In the demo, a missing message logs one warning across reruns."""

        @demo_output_onboarding("summary")
        def warned_report():
            return None

        with caplog.at_level("WARNING", logger="datasure.utils.onboarding_utils"):
            warned_report()
            warned_report()

        warnings = [
            r
            for r in caplog.records
            if "No demo guidance for warned_report" in r.message
        ]
        assert len(warnings) == 1

    def test_decorator_preserves_function_name(self):
        """The wrapper keeps the decorated function's name."""

        @demo_output_onboarding("summary")
        def summary_report():
            return None

        assert summary_report.__name__ == "summary_report"

    def test_every_decorated_function_has_message(self):
        """Every @demo_output_onboarding function in datasure has a message."""
        import datasure.checks

        for module in pkgutil.walk_packages(
            datasure.checks.__path__, prefix="datasure.checks."
        ):
            importlib.import_module(module.name)

        checked = {
            (tab, name)
            for module, tab, name in DEMO_OUTPUT_FUNCTIONS
            if module.startswith("datasure.")
        }
        assert checked, "no decorated check functions were registered"
        missing = sorted(
            (tab, name)
            for tab, name in checked
            if OutputOnboardingInfo.get_onboarding_message(tab, name) is None
        )
        assert not missing, f"decorated functions without a message: {missing}"

    def test_every_message_has_decorated_function(self):
        """Every OutputOnboardingInfo message is shown by a decorated function."""
        import datasure.checks

        for module in pkgutil.walk_packages(
            datasure.checks.__path__, prefix="datasure.checks."
        ):
            importlib.import_module(module.name)

        shown = [
            OutputOnboardingInfo.get_onboarding_message(tab, name)
            for module, tab, name in DEMO_OUTPUT_FUNCTIONS
            if module.startswith("datasure.")
        ]
        unused = sorted(
            f"{group}[{message_id!r}]"
            for group, messages in vars(OutputOnboardingInfo).items()
            if group.isupper() and isinstance(messages, dict)
            for message_id, message in messages.items()
            if message not in shown
        )
        assert not unused, f"demo messages never shown: {unused}"


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
        mock_get_step.return_value = 7
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
        mock_st.columns.return_value = [MagicMock() for _ in range(7)]

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
        for _ in range(7):
            mock_col = MagicMock()
            mock_col.__enter__ = MagicMock(return_value=mock_col)
            mock_col.__exit__ = MagicMock(return_value=False)
            mock_cols.append(mock_col)

        mock_st.columns.return_value = mock_cols

        show_progress_indicator()

        # Verify that markdown was called (header + current step + future steps)
        assert mock_st.markdown.call_count >= 5

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.demo_container")
    def test_show_demo_intro(self, mock_demo_container, mock_st):
        """Test demo intro displays correctly."""
        show_demo_intro()
        mock_demo_container.assert_called_once()
        args = mock_demo_container.call_args[0][0]
        assert "New to DataSure?" in args
        assert "Import" in args

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
        """After the last step nothing is shown; the completion message follows."""
        mock_is_demo.return_value = True

        show_next_steps(7)

        mock_st.success.assert_not_called()
        mock_st.info.assert_not_called()
        mock_st.button.assert_not_called()

    @patch("datasure.utils.onboarding_utils.st")
    @patch("datasure.utils.onboarding_utils.is_demo_project")
    def test_show_next_steps_non_demo(self, mock_is_demo, mock_st):
        """Test next steps doesn't display when not in demo mode."""
        mock_is_demo.return_value = False

        show_next_steps(2)

        mock_st.markdown.assert_not_called()

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

    def test_dates_are_ordered_strings_ending_today(self):
        """Each interview starts, ends, then is submitted; the latest is today."""
        df = pl.DataFrame({"id": list(range(50))})
        result_df = DemoDataGenerator(df, today=date(2026, 3, 10)).add_demo_fields()

        for col in DemoDataGenerator.DATE_COLUMNS:
            assert result_df[col].dtype == pl.Utf8
        start, end, submitted = (
            result_df[col].str.to_datetime(DemoDataGenerator.DATE_FORMAT)
            for col in DemoDataGenerator.DATE_COLUMNS
        )
        assert (start < end).all()
        assert (end < submitted).all()
        assert submitted.dt.date().max() == date(2026, 3, 10)
        assert start.min() >= datetime(2026, 1, 9)

    def test_same_seed_gives_same_fields(self):
        """The generator is seeded, so two runs agree."""
        df = pl.DataFrame({"id": list(range(20))})

        first = DemoDataGenerator(df, today=date(2026, 3, 10)).add_demo_fields()
        second = DemoDataGenerator(df, today=date(2026, 3, 10)).add_demo_fields()

        assert first.equals(second)

    def test_consent_and_completion_values(self):
        """Consent is mostly yes and completion mostly complete."""
        df = pl.DataFrame({"id": list(range(1000))})
        result_df = DemoDataGenerator(df).add_demo_fields()

        consent = result_df["consent"].to_list()
        status = result_df["completion_status"].to_list()
        assert set(consent) <= {"yes", "no"}
        assert consent.count("yes") >= 900
        assert set(status) <= {"complete", "incomplete"}
        assert status.count("complete") >= 900

    def test_backcheck_is_dated_after_its_survey(self):
        """A backcheck starts after the survey of the same household."""
        survey = DemoDataGenerator(
            pl.DataFrame({"hhid": ["A", "B", "C"]}), today=date(2026, 3, 10)
        ).add_demo_fields()
        backcheck = DemoDataGenerator(
            pl.DataFrame({"hhid": ["C", "A"]}), today=date(2026, 3, 10)
        ).add_demo_fields("backcheck", survey_df=survey)

        joined = backcheck.join(survey, on="hhid", suffix="_survey")
        assert (
            joined["starttime"].str.to_datetime()
            > joined["submissiondate_survey"].str.to_datetime()
        ).all()
        assert joined["submissiondate"].str.to_datetime().dt.date().max() <= date(
            2026, 3, 10
        )

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


@pytest.fixture
def load_real_demo(tmp_path, monkeypatch):
    """Load the shipped demo CSVs into a fresh cache and return the raw tables.

    Each call builds its own empty cache directory, so every load is a fresh
    first-time load of ``assets/demo_survey.csv`` and ``demo_backcheck.csv``.
    """
    from datasure.utils.duckdb_utils import duckdb_get_table

    def _load(today=None):
        cache_root = tmp_path / f"run{len(list(tmp_path.iterdir()))}"
        cache_root.mkdir()
        (cache_root / "pyproject.toml").write_text("")
        monkeypatch.chdir(cache_root)
        create_demo_project()
        with patch("datasure.utils.onboarding_utils.st"):
            assert load_demo_data(today=today) is True
        return (
            duckdb_get_table(DEMO_PROJECT_ID, "demo_survey", "raw"),
            duckdb_get_table(DEMO_PROJECT_ID, "demo_backcheck", "raw"),
        )

    return _load


class TestRealDemoData:
    """Load the real demo assets through load_demo_data (#360, #364)."""

    def test_two_fresh_loads_on_the_same_day_are_identical(self, load_real_demo):
        """Restarting the demo on the same day gives the same data."""
        survey_a, backcheck_a = load_real_demo(today=date(2026, 3, 10))
        survey_b, backcheck_b = load_real_demo(today=date(2026, 3, 10))

        assert survey_a.equals(survey_b)
        assert backcheck_a.equals(backcheck_b)

    def test_loads_on_different_days_differ_only_by_the_date_offset(
        self, load_real_demo
    ):
        """A later load moves every date by whole days and changes nothing else."""
        date_cols = list(DemoDataGenerator.DATE_COLUMNS)
        date_format = DemoDataGenerator.DATE_FORMAT
        earlier = load_real_demo(today=date(2026, 3, 10))
        later = load_real_demo(today=date(2026, 3, 17))

        for before, after in zip(earlier, later, strict=True):
            assert before.drop(date_cols).equals(after.drop(date_cols))
            for col in date_cols:
                shifted = before[col].str.to_datetime(date_format) + timedelta(days=7)
                assert after[col].str.to_datetime(date_format).equals(shifted)

    def test_latest_submissions_fall_on_yesterday_and_today(self, load_real_demo):
        """Check health deltas need submissions on the last two days."""
        today = date(2026, 3, 10)
        survey, _ = load_real_demo(today=today)

        days = set(survey["submissiondate"].str.to_datetime().dt.date())

        assert max(days) == today
        assert today - timedelta(days=1) in days

    def test_default_load_puts_the_latest_submission_today(self, load_real_demo):
        """Without an explicit date the demo is anchored on the current day."""
        survey, _ = load_real_demo()

        latest = survey["submissiondate"].str.to_datetime().dt.date().max()

        assert latest == date.today()

    def test_every_backcheck_follows_its_survey(self, load_real_demo):
        """A backcheck never starts before its household's survey was submitted."""
        survey, backcheck = load_real_demo(today=date(2026, 3, 10))

        latest_survey = survey.group_by("hhid").agg(
            pl.col("submissiondate").str.to_datetime().max().alias("surveyed")
        )
        joined = backcheck.join(latest_survey, on="hhid", how="left")

        assert joined["surveyed"].null_count() == 0
        assert (joined["starttime"].str.to_datetime() > joined["surveyed"]).all()
        assert joined["submissiondate"].str.to_datetime().dt.date().max() <= date(
            2026, 3, 10
        )

    def test_state_values_are_states(self, load_real_demo):
        """``state`` holds Indian states, not districts such as Anantapur."""
        states = {"Andhra Pradesh", "Gujarat", "Uttar Pradesh"}
        for data in load_real_demo(today=date(2026, 3, 10)):
            assert set(data["state"].unique()) == states

    def test_survey_has_refused_values(self, load_real_demo):
        """-88 ("Refused") shows up in the Missing check."""
        survey, _ = load_real_demo(today=date(2026, 3, 10))

        refused = sum(
            (survey[col] == -88).sum()
            for col in survey.columns
            if survey[col].dtype.is_numeric()
        )

        assert refused >= 10

    def test_land_acre_is_a_populated_numeric_outlier_example(self, load_real_demo):
        """The Outliers guidance needs a numeric column with values to flag."""
        survey, _ = load_real_demo(today=date(2026, 3, 10))
        land = survey["land_acre"]

        assert land.dtype.is_numeric()
        assert land.null_count() <= survey.height // 10
        valid = land.filter(land >= 0)
        q1, q3 = valid.quantile(0.25), valid.quantile(0.75)
        assert (valid > q3 + 3 * (q3 - q1)).sum() >= 2

    def test_recommended_backcheck_columns_have_mismatches(self, load_real_demo):
        """Each column the Backchecks guidance adds shows non-zero error rates."""
        from datasure.checks.backchecks.compute import compute_backcheck_analysis
        from datasure.checks.backchecks.models import BackcheckSettings

        survey, backcheck = load_real_demo(today=date(2026, 3, 10))
        # The columns, categories and OK ranges from the demo guidance
        guidance = {
            "age": (1, [-1, 1]),
            "household_count": (2, None),
            "minc_pri": (1, None),
            "npinc_out": (1, None),
            "no_save": (1, None),
            "pri_govt_sch": (1, None),
        }
        column_settings = pl.DataFrame(
            {
                "search_type": ["exact"] * len(guidance),
                "pattern": list(guidance),
                "column_name": [[col] for col in guidance],
                "category": [category for category, _ in guidance.values()],
                "ok_range_type": [
                    "number" if ok else None for _, ok in guidance.values()
                ],
                "ok_range_values": [ok for _, ok in guidance.values()],
                "ttest": [False] * len(guidance),
                "prtest": [False] * len(guidance),
                "signrank": [False] * len(guidance),
                "reliability": [False] * len(guidance),
            }
        )
        settings = BackcheckSettings(
            survey_key="KEY",
            survey_id="hhid",
            enumerator="enum_id",
            backchecker="bcer_id",
        )

        analysis = compute_backcheck_analysis(
            survey, backcheck, settings, column_settings
        )
        mismatches = dict(
            analysis.filter(pl.col("match_status") == "mismatch")
            .group_by("column_name")
            .len()
            .iter_rows()
        )

        for col in guidance:
            assert mismatches.get(col, 0) >= 2, col

    def test_every_column_named_in_guidance_exists(self, load_real_demo):
        """Demo guidance only names columns the demo data has (#356)."""
        survey, backcheck = load_real_demo(today=date(2026, 3, 10))
        data = {"demo_survey": survey, "demo_backcheck": backcheck}

        assert set(DEMO_GUIDANCE_COLUMNS) == set(data)
        missing = sorted(
            (alias, str(col))
            for alias, columns in DEMO_GUIDANCE_COLUMNS.items()
            for col in columns
            if col not in data[alias].columns
        )
        assert not missing, f"guidance names columns not in the demo data: {missing}"

    def test_duplicates_named_in_guidance_match_the_demo_data(self, load_real_demo):
        """The duplicate IDs, KEYs and new IDs the guidance names are real."""
        survey, _ = load_real_demo(today=date(2026, 3, 10))
        hhids = set(survey[DemoColumn.HHID])

        for duplicate in DEMO_DUPLICATES:
            records = survey.filter(pl.col(DemoColumn.HHID) == duplicate.hhid)
            assert records.height == 2, duplicate.hhid
            assert duplicate.key in records[DemoColumn.KEY].to_list(), duplicate
            if duplicate.new_hhid is not None:
                assert duplicate.new_hhid not in hhids, duplicate

    def test_repeat_submission_to_drop_is_the_emptier_record(self, load_real_demo):
        """The record the guidance drops leaves more answers blank than the other."""
        survey, _ = load_real_demo(today=date(2026, 3, 10))
        records = survey.filter(
            pl.col(DemoColumn.HHID) == DEMO_REPEAT_SUBMISSION.hhid
        ).with_columns(blanks=pl.sum_horizontal(pl.all().is_null()))
        blanks = dict(records.select(DemoColumn.KEY, "blanks").iter_rows())

        dropped = blanks.pop(DEMO_REPEAT_SUBMISSION.key)
        (kept,) = blanks.values()
        assert dropped > kept

    def test_correction_named_in_guidance_fixes_an_outlier(self, load_real_demo):
        """The value Correct Data fixes is an IQR outlier; the new value is not."""
        from datasure.checks.outliers.compute import compute_outlier_stats_polars

        survey, _ = load_real_demo(today=date(2026, 3, 10))
        fix = DEMO_LAND_CORRECTION
        row = survey.filter(pl.col(DemoColumn.KEY) == fix.key)
        assert row[fix.column].to_list() == [fix.old_value]

        def bounds(data):
            # Negative values are missing codes such as -99, not answers
            values = data[fix.column].filter(data[fix.column] >= 0)
            stats = compute_outlier_stats_polars(values, None, None)
            return stats.lower_bound, stats.upper_bound

        low, high = bounds(survey)
        assert not low <= fix.old_value <= high
        corrected = survey.with_columns(
            pl.when(pl.col(DemoColumn.KEY) == fix.key)
            .then(fix.new_value)
            .otherwise(pl.col(fix.column))
            .alias(fix.column)
        )
        low, high = bounds(corrected)
        assert low <= fix.new_value <= high
