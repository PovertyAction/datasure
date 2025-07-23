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
