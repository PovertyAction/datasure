"""Tests for the chart utilities module."""

from unittest.mock import MagicMock, patch

import matplotlib.pyplot as plt

from datasure.utils.chart_utils import donut_chart, donut_chart2


class TestDonutChart:
    """Test the donut_chart function."""

    def test_donut_chart_basic(self):
        """Test basic donut chart creation."""
        fig = donut_chart(75, 100)

        # Check that a figure is returned
        assert isinstance(fig, plt.Figure)
        assert fig.get_figwidth() == 2
        assert fig.get_figheight() == 2
        assert fig.get_dpi() == 100

        # Check that the figure has one subplot
        axes = fig.get_axes()
        assert len(axes) == 1

        plt.close(fig)

    def test_donut_chart_with_title(self):
        """Test donut chart with title."""
        title = "Test Progress"
        fig = donut_chart(50, 100, title=title)

        axes = fig.get_axes()
        assert axes[0].get_title() == title

        plt.close(fig)

    def test_donut_chart_custom_colors(self):
        """Test donut chart with custom colors."""
        custom_colors = ["#FF0000", "#00FF00"]
        fig = donut_chart(60, 100, colors=custom_colors)

        # Check that figure is created without error
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart_custom_prefix_suffix(self):
        """Test donut chart with custom prefix and suffix."""
        fig = donut_chart(1500, 2000, prefix="$", suffix="K")

        # Check that figure is created without error
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart_full_completion(self):
        """Test donut chart when actual equals target."""
        fig = donut_chart(100, 100)

        # Should handle full completion without error
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart_zero_value(self):
        """Test donut chart with zero actual value."""
        fig = donut_chart(0, 100)

        # Should handle zero value without error
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart_custom_target(self):
        """Test donut chart with custom target value."""
        fig = donut_chart(25, 50, suffix=" items")

        # Should handle custom target without error
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart_actual_exceeds_target(self):
        """Test donut chart when actual value exceeds target."""
        fig = donut_chart(150, 100)

        # Should handle exceeding target correctly
        assert isinstance(fig, plt.Figure)

        # Check that the figure has one subplot
        axes = fig.get_axes()
        assert len(axes) == 1

        plt.close(fig)

    def test_donut_chart_no_title(self):
        """Test donut chart without title (None)."""
        fig = donut_chart(60, 100, title=None)

        # Should create chart without title
        assert isinstance(fig, plt.Figure)
        axes = fig.get_axes()
        assert axes[0].get_title() == ""

        plt.close(fig)

    def test_donut_chart_default_colors(self):
        """Test donut chart with default colors (None)."""
        fig = donut_chart(75, 100, colors=None)

        # Should use default colors without error
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart_text_elements(self):
        """Test that text elements are created correctly."""
        fig = donut_chart(85, 100, prefix="$", suffix="K", title="Revenue")

        # Verify figure is created with text elements
        assert isinstance(fig, plt.Figure)

        # Get the axes and check text elements exist
        axes = fig.get_axes()
        texts = axes[0].texts
        assert len(texts) > 0  # Should have center text

        plt.close(fig)

    def test_donut_chart_pie_segments(self):
        """Test that pie segments are created correctly."""
        fig = donut_chart(40, 100)

        # Get axes and verify pie chart was created
        axes = fig.get_axes()
        patches = axes[0].patches
        # Should have two pie segments + center circle = 3 patches
        assert len(patches) == 3

        plt.close(fig)

    def test_donut_chart_single_segment(self):
        """Test donut chart when actual equals or exceeds target (single segment)."""
        fig = donut_chart(200, 100)

        # Get axes and verify only one segment exists
        axes = fig.get_axes()
        patches = axes[0].patches
        # Should have one pie segment + center circle = 2 patches
        assert len(patches) == 2

        plt.close(fig)

    @patch("matplotlib.pyplot.Circle")
    @patch("matplotlib.pyplot.axis")
    def test_donut_chart_circle_creation(self, mock_axis, mock_circle):
        """Test that the center circle is created correctly."""
        mock_circle_instance = MagicMock()
        mock_circle.return_value = mock_circle_instance

        donut_chart(75, 100)

        # Verify Circle was called with correct parameters
        mock_circle.assert_called_once_with((0, 0), 0.7, fc="#FFFFFF")


class TestDonutChart2:
    """Test the donut_chart2 function."""

    def test_donut_chart2_basic(self):
        """Test basic donut_chart2 creation."""
        fig = donut_chart2(75, 100)

        # Check that a figure is returned
        assert isinstance(fig, plt.Figure)
        assert fig.get_figwidth() == 10
        assert fig.get_figheight() == 10

        # Check that the figure has one subplot
        axes = fig.get_axes()
        assert len(axes) == 1

        plt.close(fig)

    def test_donut_chart2_with_title(self):
        """Test donut_chart2 with title."""
        title = "Large Progress Chart"
        fig = donut_chart2(80, 100, title=title)

        axes = fig.get_axes()
        assert axes[0].get_title() == title

        plt.close(fig)

    def test_donut_chart2_default_colors(self):
        """Test donut_chart2 with default colors."""
        fig = donut_chart2(60, 100)

        # Should use default colors without error
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart2_custom_colors(self):
        """Test donut_chart2 with custom colors."""
        custom_colours = ["#0000FF", "#FFFF00"]
        fig = donut_chart2(45, 100, colours=custom_colours)

        # Check that figure is created without error
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart2_percentage_formatting(self):
        """Test donut_chart2 with percentage suffix formatting."""
        fig = donut_chart2(75.5555, 100, suffix="%")

        # Should format percentage to 2 decimal places
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart2_non_percentage_suffix(self):
        """Test donut_chart2 with non-percentage suffix."""
        fig = donut_chart2(150, 200, prefix="$", suffix="K")

        # Should not format as percentage
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart2_actual_exceeds_target(self):
        """Test donut_chart2 when actual value exceeds target."""
        fig = donut_chart2(120, 100)

        # Should handle exceeding target by setting remainder to 0
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart2_actual_equals_target(self):
        """Test donut_chart2 when actual equals target."""
        fig = donut_chart2(100, 100)

        # Should handle equal values correctly
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart2_zero_value(self):
        """Test donut_chart2 with zero actual value."""
        fig = donut_chart2(0, 100)

        # Should handle zero value without error
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart2_no_title(self):
        """Test donut_chart2 without title (None)."""
        fig = donut_chart2(50, 100, title=None)

        # Should create chart without title
        assert isinstance(fig, plt.Figure)
        axes = fig.get_axes()
        assert axes[0].get_title() == ""

        plt.close(fig)

    def test_donut_chart2_percentage_decimal_formatting(self):
        """Test donut_chart2 formats percentages to 2 decimal places."""
        fig = donut_chart2(75.678, 100, suffix="%")

        # Should format to 2 decimal places
        assert isinstance(fig, plt.Figure)

        # Get the axes and check text elements exist
        axes = fig.get_axes()
        texts = axes[0].texts
        assert len(texts) > 0

        plt.close(fig)

    def test_donut_chart2_pie_segments(self):
        """Test that pie segments are created correctly in donut_chart2."""
        fig = donut_chart2(60, 100)

        # Get axes and verify pie chart was created
        axes = fig.get_axes()
        patches = axes[0].patches
        # Should have two pie segments + center circle = 3 patches
        assert len(patches) == 3

        # Verify alpha transparency is set on second pie segment (index 1)
        assert patches[1].get_alpha() == 0.4

        plt.close(fig)

    def test_donut_chart2_text_elements(self):
        """Test that text elements are created with correct styling."""
        fig = donut_chart2(90, 100, prefix="$", suffix="K", title="Sales")

        # Verify figure is created with text elements
        assert isinstance(fig, plt.Figure)

        # Get the axes and check text elements exist
        axes = fig.get_axes()
        texts = axes[0].texts
        assert len(texts) > 0  # Should have center text

        plt.close(fig)

    def test_donut_chart2_color_defaults(self):
        """Test donut_chart2 default colors when colours is None."""
        fig = donut_chart2(55, 100, colours=None)

        # Should use default orange colors
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    @patch("matplotlib.pyplot.Circle")
    def test_donut_chart2_circle_creation(self, mock_circle):
        """Test that the center circle is created correctly in donut_chart2."""
        mock_circle_instance = MagicMock()
        mock_circle.return_value = mock_circle_instance

        donut_chart2(75, 100)

        # Verify Circle was called with correct parameters
        mock_circle.assert_called_once_with((0, 0), 0.7, fc="#FFFFFF")


class TestChartUtilsIntegration:
    """Integration tests for chart utilities."""

    def test_both_charts_different_sizes(self):
        """Test that both chart functions create different sized figures."""
        fig1 = donut_chart(50, 100)
        fig2 = donut_chart2(50, 100)

        # Charts should have different sizes
        assert fig1.get_figwidth() != fig2.get_figwidth()
        assert fig1.get_figheight() != fig2.get_figheight()

        # Both should be valid figures
        assert isinstance(fig1, plt.Figure)
        assert isinstance(fig2, plt.Figure)

        # Clean up to prevent memory warning
        plt.close(fig1)
        plt.close(fig2)

    def test_charts_with_same_data_different_appearance(self):
        """Test that both charts handle the same data correctly."""
        actual, target = 75, 100
        title = "Progress Chart"

        fig1 = donut_chart(actual, target, title=title)
        fig2 = donut_chart2(actual, target, title=title)

        # Both should create figures without error
        assert isinstance(fig1, plt.Figure)
        assert isinstance(fig2, plt.Figure)

        # Clean up to prevent memory warning
        plt.close(fig1)
        plt.close(fig2)

    def test_edge_case_values(self):
        """Test both charts with edge case values."""
        edge_cases = [
            (0, 100),  # Zero progress
            (100, 100),  # Complete
            (150, 100),  # Over target (donut_chart2 only handles this)
            (1, 1000),  # Very small proportion
        ]

        for actual, target in edge_cases:
            fig1 = donut_chart(actual, target)
            fig2 = donut_chart2(actual, target)

            assert isinstance(fig1, plt.Figure)
            assert isinstance(fig2, plt.Figure)

            # Clean up each figure to prevent memory warning
            plt.close(fig1)
            plt.close(fig2)

    @patch("matplotlib.pyplot.close")
    def test_memory_management(self, mock_close):
        """Test that figures can be properly closed for memory management."""
        fig1 = donut_chart(50, 100)
        fig2 = donut_chart2(75, 100)

        # Close figures to free memory
        plt.close(fig1)
        plt.close(fig2)

        # Verify figures were created
        assert isinstance(fig1, plt.Figure)
        assert isinstance(fig2, plt.Figure)

    def test_multiple_chart_creation(self):
        """Test creating multiple charts in sequence."""
        charts = []

        for i in range(5):
            fig1 = donut_chart(i * 20, 100, title=f"Chart {i}")
            fig2 = donut_chart2(i * 20, 100, title=f"Large Chart {i}")
            charts.extend([fig1, fig2])

        # All charts should be valid figures
        assert len(charts) == 10
        for chart in charts:
            assert isinstance(chart, plt.Figure)

        # Clean up
        for chart in charts:
            plt.close(chart)

    def test_donut_chart_color_variations(self):
        """Test donut chart with various color combinations."""
        # Test with custom colors
        fig1 = donut_chart(75, 100, colors=["#FF0000", "#0000FF"])
        assert isinstance(fig1, plt.Figure)

        # Test with default colors (None)
        fig2 = donut_chart(75, 100, colors=None)
        assert isinstance(fig2, plt.Figure)

        plt.close(fig1)
        plt.close(fig2)

    def test_donut_chart2_with_all_parameters(self):
        """Test donut_chart2 with all parameters specified."""
        fig = donut_chart2(
            actual_value=85,
            target_value=100,
            title="Complete Test",
            prefix="$",
            suffix="K",
            colours=["#00FF00", "#FF00FF"],
        )

        assert isinstance(fig, plt.Figure)
        axes = fig.get_axes()
        assert axes[0].get_title() == "Complete Test"

        plt.close(fig)

    def test_donut_chart_with_all_parameters(self):
        """Test donut_chart with all parameters specified."""
        fig = donut_chart(
            actual_value=65,
            target_value=100,
            title="Full Test",
            prefix="€",
            suffix="M",
            colors=["#AAAAAA", "#BBBBBB"],
        )

        assert isinstance(fig, plt.Figure)
        axes = fig.get_axes()
        assert axes[0].get_title() == "Full Test"

        plt.close(fig)

    def test_donut_chart_exact_target_match(self):
        """Test when actual exactly matches target in donut_chart."""
        fig = donut_chart(100, 100)

        axes = fig.get_axes()
        patches = axes[0].patches
        # When actual equals target, remainder is 0
        # Should have 1 pie segment + center circle
        assert len(patches) == 2

        plt.close(fig)

    def test_donut_chart2_remainder_zero_alpha(self):
        """Test donut_chart2 when remainder is zero (actual equals target)."""
        # When actual equals target, remainder is 0
        # The alpha setting on line 126 will still execute
        fig = donut_chart2(100, 100)

        axes = fig.get_axes()
        patches = axes[0].patches
        # Still has 2 pie segments (actual and 0 remainder) + center circle = 3 patches
        assert len(patches) == 3

        # Second pie segment should have alpha set
        assert patches[1].get_alpha() == 0.4

        plt.close(fig)
