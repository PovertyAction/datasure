"""Comprehensive tests for metric utilities module."""

from unittest.mock import MagicMock, Mock, patch

from datasure.utils.metric_utils import custom_metric


class TestCustomMetric:
    """Test custom_metric function."""

    @patch("datasure.utils.metric_utils.stylable_container")
    @patch("datasure.utils.metric_utils.st")
    def test_custom_metric_basic_execution(self, mock_st, mock_stylable_container):
        """Test that custom_metric executes without errors."""
        # Setup mock context manager
        mock_context = MagicMock()
        mock_stylable_container.return_value.__enter__ = Mock(return_value=mock_context)
        mock_stylable_container.return_value.__exit__ = Mock(return_value=None)

        # Call the function
        custom_metric()

        # Verify stylable_container was called
        assert mock_stylable_container.called

    @patch("datasure.utils.metric_utils.stylable_container")
    @patch("datasure.utils.metric_utils.st")
    def test_custom_metric_container_key(self, mock_st, mock_stylable_container):
        """Test that stylable_container is called with correct key."""
        # Setup mock context manager
        mock_context = MagicMock()
        mock_stylable_container.return_value.__enter__ = Mock(return_value=mock_context)
        mock_stylable_container.return_value.__exit__ = Mock(return_value=None)

        # Call the function
        custom_metric()

        # Verify stylable_container was called with correct key
        mock_stylable_container.assert_called_once()
        call_kwargs = mock_stylable_container.call_args[1]
        assert call_kwargs["key"] == "container"

    @patch("datasure.utils.metric_utils.stylable_container")
    @patch("datasure.utils.metric_utils.st")
    def test_custom_metric_css_styles(self, mock_st, mock_stylable_container):
        """Test that stylable_container is called with correct CSS styles."""
        # Setup mock context manager
        mock_context = MagicMock()
        mock_stylable_container.return_value.__enter__ = Mock(return_value=mock_context)
        mock_stylable_container.return_value.__exit__ = Mock(return_value=None)

        # Call the function
        custom_metric()

        # Verify stylable_container was called with CSS styles
        call_kwargs = mock_stylable_container.call_args[1]
        css_styles = call_kwargs["css_styles"]

        # Check that CSS contains expected styling
        assert "button" in css_styles
        assert "background-color" in css_styles
        assert "#3c3635" in css_styles
        assert "border: none" in css_styles
        assert "color: white" in css_styles

    @patch("datasure.utils.metric_utils.stylable_container")
    @patch("datasure.utils.metric_utils.st")
    def test_custom_metric_writes_content(self, mock_st, mock_stylable_container):
        """Test that custom_metric writes expected content."""
        # Setup mock context manager
        mock_context = MagicMock()
        mock_stylable_container.return_value.__enter__ = Mock(return_value=mock_context)
        mock_stylable_container.return_value.__exit__ = Mock(return_value=None)

        # Call the function
        custom_metric()

        # Verify st.write was called with the expected message
        mock_st.write.assert_called_once_with("This is a custom metric.")

    @patch("datasure.utils.metric_utils.stylable_container")
    @patch("datasure.utils.metric_utils.st")
    def test_custom_metric_context_manager_behavior(
        self, mock_st, mock_stylable_container
    ):
        """Test that stylable_container is used as a context manager."""
        # Setup mock context manager
        mock_context = MagicMock()
        mock_enter = Mock(return_value=mock_context)
        mock_exit = Mock(return_value=None)

        mock_stylable_container.return_value.__enter__ = mock_enter
        mock_stylable_container.return_value.__exit__ = mock_exit

        # Call the function
        custom_metric()

        # Verify context manager methods were called
        mock_enter.assert_called_once()
        mock_exit.assert_called_once()

    @patch("datasure.utils.metric_utils.stylable_container")
    @patch("datasure.utils.metric_utils.st")
    def test_custom_metric_css_formatting(self, mock_st, mock_stylable_container):
        """Test that CSS is properly formatted with correct structure."""
        # Setup mock context manager
        mock_context = MagicMock()
        mock_stylable_container.return_value.__enter__ = Mock(return_value=mock_context)
        mock_stylable_container.return_value.__exit__ = Mock(return_value=None)

        # Call the function
        custom_metric()

        # Get the CSS styles
        call_kwargs = mock_stylable_container.call_args[1]
        css_styles = call_kwargs["css_styles"]

        # Verify CSS is a string
        assert isinstance(css_styles, str)

        # Verify CSS contains proper structure
        assert "{" in css_styles
        assert "}" in css_styles

    @patch("datasure.utils.metric_utils.stylable_container")
    @patch("datasure.utils.metric_utils.st")
    def test_custom_metric_no_return_value(self, mock_st, mock_stylable_container):
        """Test that custom_metric returns None."""
        # Setup mock context manager
        mock_context = MagicMock()
        mock_stylable_container.return_value.__enter__ = Mock(return_value=mock_context)
        mock_stylable_container.return_value.__exit__ = Mock(return_value=None)

        # Call the function
        result = custom_metric()

        # Verify function returns None
        assert result is None

    @patch("datasure.utils.metric_utils.stylable_container")
    @patch("datasure.utils.metric_utils.st")
    def test_custom_metric_multiple_calls(self, mock_st, mock_stylable_container):
        """Test that custom_metric can be called multiple times."""
        # Setup mock context manager
        mock_context = MagicMock()
        mock_stylable_container.return_value.__enter__ = Mock(return_value=mock_context)
        mock_stylable_container.return_value.__exit__ = Mock(return_value=None)

        # Call the function multiple times
        custom_metric()
        custom_metric()
        custom_metric()

        # Verify stylable_container was called 3 times
        assert mock_stylable_container.call_count == 3

        # Verify st.write was called 3 times
        assert mock_st.write.call_count == 3

    @patch("datasure.utils.metric_utils.stylable_container")
    @patch("datasure.utils.metric_utils.st")
    def test_custom_metric_call_order(self, mock_st, mock_stylable_container):
        """Test that stylable_container is called before st.write."""
        # Setup mock context manager
        mock_context = MagicMock()
        mock_stylable_container.return_value.__enter__ = Mock(return_value=mock_context)
        mock_stylable_container.return_value.__exit__ = Mock(return_value=None)

        # Track call order
        call_order = []

        def record_stylable_call(*args, **kwargs):
            call_order.append("stylable_container")
            mock_cm = MagicMock()
            mock_cm.__enter__ = Mock(return_value=mock_context)
            mock_cm.__exit__ = Mock(return_value=None)
            return mock_cm

        def record_write_call(*args, **kwargs):
            call_order.append("st.write")

        mock_stylable_container.side_effect = record_stylable_call
        mock_st.write.side_effect = record_write_call

        # Call the function
        custom_metric()

        # Verify call order
        assert call_order == ["stylable_container", "st.write"]

    @patch("datasure.utils.metric_utils.stylable_container")
    @patch("datasure.utils.metric_utils.st")
    def test_custom_metric_css_contains_all_properties(
        self, mock_st, mock_stylable_container
    ):
        """Test that CSS contains all expected properties."""
        # Setup mock context manager
        mock_context = MagicMock()
        mock_stylable_container.return_value.__enter__ = Mock(return_value=mock_context)
        mock_stylable_container.return_value.__exit__ = Mock(return_value=None)

        # Call the function
        custom_metric()

        # Get the CSS styles
        call_kwargs = mock_stylable_container.call_args[1]
        css_styles = call_kwargs["css_styles"]

        # Verify all CSS properties are present
        expected_properties = [
            "background-color",
            "border",
            "color",
        ]

        for prop in expected_properties:
            assert prop in css_styles, f"CSS property '{prop}' not found"

    @patch("datasure.utils.metric_utils.stylable_container")
    @patch("datasure.utils.metric_utils.st")
    def test_custom_metric_container_key_is_string(
        self, mock_st, mock_stylable_container
    ):
        """Test that container key is a string."""
        # Setup mock context manager
        mock_context = MagicMock()
        mock_stylable_container.return_value.__enter__ = Mock(return_value=mock_context)
        mock_stylable_container.return_value.__exit__ = Mock(return_value=None)

        # Call the function
        custom_metric()

        # Verify key is a string
        call_kwargs = mock_stylable_container.call_args[1]
        assert isinstance(call_kwargs["key"], str)

    @patch("datasure.utils.metric_utils.stylable_container")
    @patch("datasure.utils.metric_utils.st")
    def test_custom_metric_write_message_is_string(
        self, mock_st, mock_stylable_container
    ):
        """Test that write message is a string."""
        # Setup mock context manager
        mock_context = MagicMock()
        mock_stylable_container.return_value.__enter__ = Mock(return_value=mock_context)
        mock_stylable_container.return_value.__exit__ = Mock(return_value=None)

        # Call the function
        custom_metric()

        # Verify write was called with a string
        write_args = mock_st.write.call_args[0]
        assert len(write_args) > 0
        assert isinstance(write_args[0], str)


class TestMetricUtilsModule:
    """Test module-level attributes and imports."""

    def test_module_has_custom_metric_function(self):
        """Test that module exports custom_metric function."""
        from datasure.utils import metric_utils

        assert hasattr(metric_utils, "custom_metric")
        assert callable(metric_utils.custom_metric)

    def test_custom_metric_is_importable(self):
        """Test that custom_metric can be imported directly."""
        from datasure.utils.metric_utils import custom_metric

        assert callable(custom_metric)

    def test_custom_metric_has_docstring(self):
        """Test that custom_metric has a docstring."""
        assert custom_metric.__doc__ is not None
        assert len(custom_metric.__doc__) > 0
        assert "Custom metric" in custom_metric.__doc__
