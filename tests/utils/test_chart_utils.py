"""Tests for the chart utilities module."""

from unittest.mock import MagicMock, patch

import matplotlib.pyplot as plt

from datasure.utils.chart_utils import donut_chart


class TestDonutChart:
    """Test the donut_chart function."""

    def test_donut_chart_basic(self):
        """Test basic donut chart creation."""
        fig = donut_chart(75, 100)

        # Check that a figure is returned
        assert isinstance(fig, plt.Figure)
        assert fig.get_figwidth() == 10
        assert fig.get_figheight() == 10

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

    def test_donut_chart_no_title(self):
        """Test donut chart without title (None)."""
        fig = donut_chart(60, 100, title=None)

        # Should create chart without title
        assert isinstance(fig, plt.Figure)
        axes = fig.get_axes()
        assert axes[0].get_title() == ""

        plt.close(fig)

    def test_donut_chart_custom_colors(self):
        """Test donut chart with custom colors."""
        custom_colors = ["#FF0000", "#00FF00"]
        fig = donut_chart(60, 100, colors=custom_colors)

        # Check that figure is created without error
        assert isinstance(fig, plt.Figure)

        plt.close(fig)

    def test_donut_chart_default_colors(self):
        """Test donut chart with default colors (None)."""
        fig = donut_chart(75, 100, colors=None)

        # Default value segment is orange and the centre text matches it
        axes = fig.get_axes()
        patches = axes[0].patches
        assert patches[0].get_facecolor()[:3] == plt.matplotlib.colors.to_rgb("#FF8000")
        # The centre text is the last text element (pie wedges add empty labels)
        assert axes[0].texts[-1].get_color() == "#FF8000"

        plt.close(fig)

    def test_donut_chart_percentage_formatting(self):
        """Test that percentage values are formatted to 2 decimal places."""
        fig = donut_chart(75.678, 100, suffix="%")

        axes = fig.get_axes()
        assert axes[0].texts[-1].get_text() == "75.68%"

        plt.close(fig)

    def test_donut_chart_non_percentage_suffix_not_formatted(self):
        """Test that non-percentage values are not decimal-formatted."""
        fig = donut_chart(1500, 2000, prefix="$", suffix="K")

        axes = fig.get_axes()
        assert axes[0].texts[-1].get_text() == "$1500K"

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

    def test_donut_chart_actual_exceeds_target(self):
        """Test donut chart when actual value exceeds target."""
        fig = donut_chart(150, 100)

        # Remainder is clamped to 0; chart still renders as a full ring
        assert isinstance(fig, plt.Figure)
        axes = fig.get_axes()
        assert len(axes) == 1

        plt.close(fig)

    def test_donut_chart_pie_segments(self):
        """Test that pie segments are created correctly."""
        fig = donut_chart(40, 100)

        # Get axes and verify pie chart was created
        axes = fig.get_axes()
        patches = axes[0].patches
        # Should have two pie segments + center circle = 3 patches
        assert len(patches) == 3

        # Background segment is semi-transparent
        assert patches[1].get_alpha() == 0.4

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

    @patch("matplotlib.pyplot.Circle")
    @patch("matplotlib.pyplot.axis")
    def test_donut_chart_circle_creation(self, mock_axis, mock_circle):
        """Test that the center circle is created correctly."""
        mock_circle_instance = MagicMock()
        mock_circle.return_value = mock_circle_instance

        donut_chart(75, 100)

        # Verify Circle was called with correct parameters
        mock_circle.assert_called_once_with((0, 0), 0.7, fc="#FFFFFF")


class TestDonutChartEdgeCases:
    """Edge case and lifecycle tests for donut_chart."""

    def test_edge_case_values(self):
        """Test chart creation across edge case values."""
        edge_cases = [
            (0, 100),  # Zero progress
            (100, 100),  # Complete
            (150, 100),  # Over target
            (1, 1000),  # Very small proportion
        ]

        for actual, target in edge_cases:
            fig = donut_chart(actual, target)
            assert isinstance(fig, plt.Figure)
            plt.close(fig)

    def test_remainder_zero_alpha(self):
        """Test that the zero remainder segment still gets alpha set."""
        fig = donut_chart(100, 100)

        axes = fig.get_axes()
        patches = axes[0].patches
        # Two pie segments (actual and 0 remainder) + center circle
        assert len(patches) == 3
        assert patches[1].get_alpha() == 0.4

        plt.close(fig)

    def test_multiple_chart_creation(self):
        """Test creating multiple charts in sequence."""
        charts = [donut_chart(i * 20, 100, title=f"Chart {i}") for i in range(5)]

        assert len(charts) == 5
        for chart in charts:
            assert isinstance(chart, plt.Figure)
            plt.close(chart)
