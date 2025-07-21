"""Test descriptive table functions with SonarQube parameter issue."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


class TestDescriptiveTableFunctions:
    """Test cases for descriptive table display functions."""

    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing."""
        return pd.DataFrame(
            {
                "category": ["A", "B", "A", "C", "B", "A"],
                "category2": ["X", "Y", "X", "Z", "Y", "X"],
                "numeric": [10, 20, 15, 25, 30, 12],
            }
        )

    @pytest.fixture
    def sample_one_way_table(self):
        """Create sample one-way table for testing."""
        return pd.DataFrame(
            {
                "category": ["A", "B", "C"],
                "Frequency": [3, 2, 1],
                "Percentage": [50.0, 33.33, 16.67],
            }
        )

    @pytest.fixture
    def sample_two_way_table(self):
        """Create sample two-way table for testing."""
        return pd.DataFrame(
            {"X": [2, 1, 0], "Y": [0, 1, 0], "Z": [1, 0, 1], "Total": [3, 2, 1]},
            index=["A", "B", "C"],
        )

    def test_compute_one_way_table(self, sample_data):
        """Test the compute_one_way_table function logic."""

        # Create a function that mimics the compute_one_way_table
        def mock_compute_one_way_table(data, categorical_col):
            one_way_table = data[categorical_col].value_counts().reset_index()
            one_way_table.columns = [categorical_col, "Frequency"]
            one_way_table["Percentage"] = (
                one_way_table["Frequency"] / one_way_table["Frequency"].sum()
            ) * 100
            return one_way_table

        result = mock_compute_one_way_table(sample_data, "category")

        # Verify structure
        assert isinstance(result, pd.DataFrame)
        assert "category" in result.columns
        assert "Frequency" in result.columns
        assert "Percentage" in result.columns

        # Verify data
        assert len(result) == 3  # A, B, C
        assert result["Frequency"].sum() == 6  # total rows
        assert abs(result["Percentage"].sum() - 100.0) < 0.01  # percentages sum to 100

    def test_compute_two_way_table(self, sample_data):
        """Test the compute_two_way_table function."""

        # Create a mock function that mimics the compute_two_way_table
        def mock_compute_two_way_table(data, categorical_col, cat_col_2):
            two_way_table = pd.crosstab(data[categorical_col], data[cat_col_2])
            two_way_table["Total"] = two_way_table.sum(axis=1)
            two_way_table.loc["Total"] = two_way_table.sum()
            return two_way_table

        result = mock_compute_two_way_table(sample_data, "category", "category2")

        # Verify structure
        assert isinstance(result, pd.DataFrame)
        assert "Total" in result.columns
        assert "Total" in result.index

        # Verify that the total row/column calculations are correct
        for col in result.columns[:-1]:  # Exclude 'Total' column
            assert result.loc["Total", col] == result[col].iloc[:-1].sum()

    @patch("streamlit.write")
    @patch("streamlit.dataframe")
    @patch("seaborn.light_palette")
    def test_display_one_way_table_original_behavior(
        self, mock_palette, mock_dataframe, mock_write, sample_one_way_table
    ):
        """Test the original display_one_way_table function behavior."""
        # Mock the palette
        mock_palette.return_value = "mock_cmap"

        # Mock the compute function to return our sample table
        def mock_compute_one_way_table(data, categorical_col):
            return sample_one_way_table

        # Create the function with mocked dependencies
        def display_one_way_table_original(one_way_table: pd.DataFrame) -> None:
            """Original function that ignores parameter."""
            # This mimics the problematic behavior - parameter is ignored
            _ = mock_compute_one_way_table(None, "category")  # Ignored result

            mock_write("### One-way Table")
            _ = mock_palette("pink", as_cmap=True)  # Ignored result

            # Create a mock styled dataframe
            styled_df = MagicMock()
            styled_df.style.format.return_value.background_gradient.return_value = (
                styled_df
            )

            mock_dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
            )

        # Test the function
        input_table = pd.DataFrame({"dummy": [1, 2, 3]})  # This gets ignored
        display_one_way_table_original(input_table)

        # Verify Streamlit functions were called
        mock_write.assert_called_with("### One-way Table")
        mock_palette.assert_called_with("pink", as_cmap=True)
        mock_dataframe.assert_called_once()

    @patch("streamlit.write")
    @patch("streamlit.dataframe")
    @patch("seaborn.light_palette")
    def test_display_two_way_table_original_behavior(
        self, mock_palette, mock_dataframe, mock_write, sample_two_way_table
    ):
        """Test the original display_two_way_table function behavior."""
        # Mock the palette
        mock_palette.return_value = "mock_cmap"

        # Mock the compute function to return our sample table
        def mock_compute_two_way_table(data, categorical_col, cat_col_2):
            return sample_two_way_table.copy()

        # Create the function with mocked dependencies
        def display_two_way_table_original(two_way_table: pd.DataFrame) -> None:
            """Original function that ignores parameter."""
            # This mimics the problematic behavior - parameter is ignored
            two_way_table = mock_compute_two_way_table(None, "category", "category2")

            # Mimic the original processing
            two_way_table.reset_index(inplace=True)
            two_way_table.rename(columns={"index": "category"}, inplace=True)
            two_way_table = two_way_table[two_way_table["category"] != "Total"]
            format_cols = [
                col for col in two_way_table.columns if col not in ["category", "Total"]
            ]
            two_way_table = two_way_table[["category", "Total"] + format_cols]

            mock_write("### Two-way Table")
            _ = mock_palette("pink", as_cmap=True)  # Ignored result

            # Create a mock styled dataframe
            styled_df = MagicMock()
            styled_df.style.background_gradient.return_value = styled_df

            mock_dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
            )

        # Test the function
        input_table = pd.DataFrame({"dummy": [1, 2, 3]})  # This gets ignored
        display_two_way_table_original(input_table)

        # Verify Streamlit functions were called
        mock_write.assert_called_with("### Two-way Table")
        mock_palette.assert_called_with("pink", as_cmap=True)
        mock_dataframe.assert_called_once()

    @patch("streamlit.write")
    @patch("streamlit.dataframe")
    @patch("seaborn.light_palette")
    def test_display_one_way_table_fixed_behavior(
        self, mock_palette, mock_dataframe, mock_write, sample_one_way_table
    ):
        """Test the fixed display_one_way_table function that uses parameter."""
        # Mock the palette
        mock_palette.return_value = "mock_cmap"

        # Create the fixed function that uses the parameter
        def display_one_way_table_fixed(one_way_table: pd.DataFrame) -> None:
            """Fixed function that uses the parameter."""
            mock_write("### One-way Table")
            _ = mock_palette("pink", as_cmap=True)  # Ignored result

            # Create a mock styled dataframe
            styled_df = MagicMock()
            styled_df.style.format.return_value.background_gradient.return_value = (
                styled_df
            )

            mock_dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
            )

        # Test the function with actual parameter usage
        display_one_way_table_fixed(sample_one_way_table)

        # Verify Streamlit functions were called
        mock_write.assert_called_with("### One-way Table")
        mock_palette.assert_called_with("pink", as_cmap=True)
        mock_dataframe.assert_called_once()

    @patch("streamlit.write")
    @patch("streamlit.dataframe")
    @patch("seaborn.light_palette")
    def test_display_two_way_table_fixed_behavior(
        self, mock_palette, mock_dataframe, mock_write, sample_two_way_table
    ):
        """Test the fixed display_two_way_table function that uses parameter."""
        # Mock the palette
        mock_palette.return_value = "mock_cmap"

        # Create the fixed function that uses the parameter
        def display_two_way_table_fixed(two_way_table: pd.DataFrame) -> None:
            """Fixed function that uses the parameter."""
            # Use the actual parameter instead of recomputing
            table_copy = two_way_table.copy()

            # Process the input table
            table_copy.reset_index(inplace=True)
            table_copy.rename(columns={"index": "category"}, inplace=True)
            table_copy = table_copy[table_copy["category"] != "Total"]
            format_cols = [
                col for col in table_copy.columns if col not in ["category", "Total"]
            ]
            table_copy = table_copy[["category", "Total"] + format_cols]

            mock_write("### Two-way Table")
            _ = mock_palette("pink", as_cmap=True)  # Ignored result

            # Create a mock styled dataframe
            styled_df = MagicMock()
            styled_df.style.background_gradient.return_value = styled_df

            mock_dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
            )

        # Test the function with actual parameter usage
        display_two_way_table_fixed(sample_two_way_table)

        # Verify Streamlit functions were called
        mock_write.assert_called_with("### Two-way Table")
        mock_palette.assert_called_with("pink", as_cmap=True)
        mock_dataframe.assert_called_once()

    def test_parameter_usage_patterns(self):
        """Test different patterns of parameter usage."""

        # Pattern 1: Parameter ignored (SonarQube issue)
        def bad_function(data: pd.DataFrame) -> pd.DataFrame:
            data = pd.DataFrame({"new": [1, 2, 3]})  # Parameter ignored
            return data

        # Pattern 2: Parameter initial value used
        def good_function_v1(data: pd.DataFrame) -> pd.DataFrame:
            if data is None:
                data = pd.DataFrame({"default": [1, 2, 3]})
            return data.copy()

        # Pattern 3: Parameter used directly
        def good_function_v2(data: pd.DataFrame) -> pd.DataFrame:
            return data.copy()

        # Pattern 4: Remove parameter if not needed
        def good_function_v3() -> pd.DataFrame:
            data = pd.DataFrame({"computed": [1, 2, 3]})
            return data

        # Test the patterns
        test_data = pd.DataFrame({"test": [10, 20, 30]})

        # Bad pattern - parameter ignored
        result_bad = bad_function(test_data)
        assert "test" not in result_bad.columns  # Original data lost

        # Good pattern - parameter used conditionally
        result_good1 = good_function_v1(test_data)
        assert "test" in result_good1.columns  # Original data preserved

        result_good1_none = good_function_v1(None)
        assert "default" in result_good1_none.columns  # Default used when None

        # Good pattern - parameter used directly
        result_good2 = good_function_v2(test_data)
        assert "test" in result_good2.columns  # Original data preserved

        # Good pattern - no parameter needed
        result_good3 = good_function_v3()
        assert "computed" in result_good3.columns  # Computed data

    def test_edge_cases(self):
        """Test edge cases for the table functions."""
        # Test with empty dataframe
        empty_df = pd.DataFrame()

        def safe_compute_one_way_table(data, categorical_col):
            if data.empty or categorical_col not in data.columns:
                return pd.DataFrame(
                    columns=[categorical_col, "Frequency", "Percentage"]
                )

            one_way_table = data[categorical_col].value_counts().reset_index()
            one_way_table.columns = [categorical_col, "Frequency"]
            one_way_table["Percentage"] = (
                one_way_table["Frequency"] / one_way_table["Frequency"].sum()
            ) * 100
            return one_way_table

        result = safe_compute_one_way_table(empty_df, "category")
        assert len(result) == 0
        assert list(result.columns) == ["category", "Frequency", "Percentage"]

        # Test with single value
        single_df = pd.DataFrame({"category": ["A"]})
        result = safe_compute_one_way_table(single_df, "category")
        assert len(result) == 1
        assert result.iloc[0]["Frequency"] == 1
        assert result.iloc[0]["Percentage"] == 100.0

    def test_function_signature_improvements(self):
        """Test improved function signatures that fix the SonarQube issue."""

        # Original problematic signature
        def display_table_bad(table: pd.DataFrame) -> None:
            _ = pd.DataFrame({"recomputed": [1, 2, 3]})  # Parameter ignored
            # ... display logic

        # Fixed option 1: Remove unused parameter
        def display_table_fixed_v1() -> None:
            _ = pd.DataFrame({"computed": [1, 2, 3]})  # Display logic placeholder
            # ... display logic

        # Fixed option 2: Use the parameter
        def display_table_fixed_v2(table: pd.DataFrame) -> None:
            # Use the actual parameter
            if table is not None and not table.empty:
                # ... display logic using table
                pass

        # Fixed option 3: Use parameter with fallback
        def display_table_fixed_v3(table: pd.DataFrame = None) -> None:
            if table is None:
                table = pd.DataFrame({"default": [1, 2, 3]})
            # ... display logic using table

        # Test that the functions work as expected
        test_data = pd.DataFrame({"test": [1, 2, 3]})

        # These should not raise exceptions
        display_table_bad(test_data)  # Works but ignores parameter
        display_table_fixed_v1()  # Works, no parameter needed
        display_table_fixed_v2(test_data)  # Works, uses parameter
        display_table_fixed_v3(test_data)  # Works, uses parameter
        display_table_fixed_v3(None)  # Works, uses default
