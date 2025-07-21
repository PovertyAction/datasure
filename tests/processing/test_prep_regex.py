"""Test regex vulnerability in prep.py processing module."""

import re
import time


class TestNumericRegexSecurity:
    """Test cases for numeric extraction regex vulnerability."""

    def test_vulnerable_regex_pattern(self):
        """Test the original vulnerable regex pattern."""
        # This is the vulnerable pattern from the code
        vulnerable_pattern = r"\d+\.?\d*$"

        # These should match
        assert re.search(vulnerable_pattern, "add 5")
        assert re.search(vulnerable_pattern, "multiply 10.5")
        assert re.search(vulnerable_pattern, "subtract 42")
        assert re.search(vulnerable_pattern, "divide 3.14159")
        assert re.search(vulnerable_pattern, "add 100")

        # These should not match (no numbers at end)
        assert not re.search(vulnerable_pattern, "add")
        assert not re.search(vulnerable_pattern, "multiply abc")
        assert not re.search(vulnerable_pattern, "123 add")

    def test_vulnerable_regex_backtracking(self):
        """Test that the vulnerable regex exhibits catastrophic backtracking."""
        vulnerable_pattern = r"\d+\.?\d*$"

        # This string could cause catastrophic backtracking:
        # Many digits followed by dots but no final digits
        # causing the regex engine to backtrack extensively
        problematic_string = "add " + "1" * 20 + "." * 10

        start_time = time.time()
        result = re.search(vulnerable_pattern, problematic_string)
        end_time = time.time()

        # Should not match due to dots at the end without digits
        assert not result

        # Document the timing (for demonstration)
        execution_time = end_time - start_time
        print(
            f"Vulnerable regex took {execution_time:.4f} seconds for input: "
            f"{problematic_string[:50]}..."
        )

    def test_safe_regex_pattern(self):
        """Test a safe regex pattern that avoids backtracking."""
        # This is the safe pattern we'll implement with bounded quantifiers
        # Matches: space followed by 1-10 digits, optional dot with 1-10 digits, end
        safe_pattern = r"\s\d{1,10}(?:\.\d{1,10})?$"

        # These should match (same as vulnerable pattern)
        assert re.search(safe_pattern, "add 5")
        assert re.search(safe_pattern, "multiply 10.5")
        assert re.search(safe_pattern, "subtract 42")
        assert re.search(safe_pattern, "divide 3.14159")
        assert re.search(safe_pattern, "add 100")

        # These should not match (same as vulnerable pattern)
        assert not re.search(safe_pattern, "add")
        assert not re.search(safe_pattern, "multiply abc")
        assert not re.search(safe_pattern, "123 add")

        # Additional edge cases
        assert re.search(safe_pattern, "value 0")
        assert re.search(safe_pattern, "number 0.0")
        assert re.search(safe_pattern, "test 999.999")

    def test_safe_regex_no_backtracking(self):
        """Test that the safe regex does not exhibit catastrophic backtracking."""
        safe_pattern = r"\s\d{1,10}(?:\.\d{1,10})?$"

        # Same problematic string as before
        problematic_string = "add " + "1" * 20 + "." * 10

        start_time = time.time()
        result = re.search(safe_pattern, problematic_string)
        end_time = time.time()

        # Should not match due to excessive length and dots at end
        assert not result

        # Should be much faster
        execution_time = end_time - start_time
        print(
            f"Safe regex took {execution_time:.4f} seconds for input: "
            f"{problematic_string[:50]}..."
        )

        # Should complete in reasonable time (less than 0.01 seconds)
        assert execution_time < 0.01

    def test_edge_cases(self):
        """Test edge cases for numeric extraction."""
        safe_pattern = r"\s\d{1,10}(?:\.\d{1,10})?$"

        # Edge cases that should match
        assert re.search(safe_pattern, "add 1")
        assert re.search(safe_pattern, "multiply 1.0")
        assert re.search(safe_pattern, "value 9999999999")  # 10 digits
        assert re.search(safe_pattern, "number 123.4567890")  # 10 decimal places

        # Edge cases that should not match
        assert not re.search(safe_pattern, "value 12345678901")  # 11 digits
        assert not re.search(safe_pattern, "number 1.12345678901")  # 11 decimal places
        assert not re.search(safe_pattern, "test .")  # just a dot
        assert not re.search(safe_pattern, "operation 1.")  # trailing dot
        assert not re.search(safe_pattern, "calc .5")  # leading dot
        assert not re.search(safe_pattern, "empty ")  # no number

    def test_performance_comparison(self):
        """Compare performance between vulnerable and safe regex patterns."""
        vulnerable_pattern = r"\d+\.?\d*$"
        safe_pattern = r"\s\d{1,10}(?:\.\d{1,10})?$"

        # Test strings that could cause backtracking
        test_strings = [
            "add 123",
            "multiply 45.67",
            "subtract " + "8" * 15,  # long number
            "divide " + "9" * 10 + "." + "1" * 5,  # potential backtracking case
        ]

        for test_string in test_strings:
            # Test vulnerable regex
            start_time = time.time()
            vulnerable_result = re.search(vulnerable_pattern, test_string)
            vulnerable_time = time.time() - start_time

            # Test safe regex
            start_time = time.time()
            safe_result = re.search(safe_pattern, test_string)
            safe_time = time.time() - start_time

            print(f"Input: {test_string}")
            print(f"  Vulnerable: {bool(vulnerable_result)} ({vulnerable_time:.6f}s)")
            print(f"  Safe:       {bool(safe_result)} ({safe_time:.6f}s)")

            # For valid inputs within bounds, both should give same result
            if vulnerable_result:
                num_str = vulnerable_result.group(0)
                # Check if it fits our safe pattern constraints
                if "." in num_str:
                    before_dot, after_dot = num_str.split(".", 1)
                    within_bounds = len(before_dot) <= 10 and len(after_dot) <= 10
                else:
                    within_bounds = len(num_str) <= 10

                if within_bounds:
                    assert safe_result is not None
                    assert vulnerable_result.group(0) == safe_result.group(0).strip()
                else:
                    # Long numbers should be rejected by safe pattern
                    print(f"  Expected safe to reject: {num_str} (length constraints)")
                    # Note: safe pattern might still match end of long numbers

    def test_bounded_quantifier_benefits(self):
        """Test that bounded quantifiers provide additional safety."""
        bounded_pattern = r"\s\d{1,10}(?:\.\d{1,10})?$"

        # Test with extremely long input that could cause issues
        very_long_input = "calculate " + "9" * 50 + "." + "8" * 50

        start_time = time.time()
        result = re.search(bounded_pattern, very_long_input)
        end_time = time.time()

        # Should fail quickly due to length limits
        assert not result
        execution_time = end_time - start_time

        # Should be very fast (much less than 0.01 seconds)
        assert execution_time < 0.01
        print(
            f"Bounded regex rejected {len(very_long_input)}-char input in "
            f"{execution_time:.6f}s"
        )

        # Test realistic numeric values still work
        realistic_values = [
            "add 1",
            "multiply 3.14",
            "subtract 1000",
            "divide 2.5",
            "value 999.99",
        ]

        for value in realistic_values:
            assert re.search(bounded_pattern, value), f"Should match: {value}"


def extract_numeric_value_vulnerable(description):
    """Original vulnerable numeric extraction function."""
    match = re.search(r"\d+\.?\d*$", description)
    return float(match.group(0)) if match else None


def extract_numeric_value_safe(description):
    """Safe numeric extraction function with bounded quantifiers."""
    match = re.search(r"\s\d{1,10}(?:\.\d{1,10})?$", description)
    return float(match.group(0).strip()) if match else None


class TestNumericExtraction:
    """Test the numeric extraction functions."""

    def test_both_functions_same_results_valid_inputs(self):
        """Test that both functions return the same results for valid inputs."""
        valid_inputs = [
            "add 5",
            "multiply 10.5",
            "subtract 42",
            "divide 3.14159",
            "value 100",
            "number 0",
            "test 0.0",
            "calc 999.999",
        ]

        for input_str in valid_inputs:
            vulnerable_result = extract_numeric_value_vulnerable(input_str)
            safe_result = extract_numeric_value_safe(input_str)

            # Both should return the same numeric values
            if vulnerable_result is not None and safe_result is not None:
                assert abs(vulnerable_result - safe_result) < 1e-10
            else:
                assert vulnerable_result == safe_result

    def test_both_functions_same_results_invalid_inputs(self):
        """Test that both functions return the same results for invalid inputs."""
        invalid_inputs = [
            "add",
            "multiply abc",
            "123 add",
            "no numbers here",
            "empty string",
            "dots only ...",
        ]

        for input_str in invalid_inputs:
            vulnerable_result = extract_numeric_value_vulnerable(input_str)
            safe_result = extract_numeric_value_safe(input_str)

            # Both should return None for invalid inputs
            assert vulnerable_result is None and safe_result is None

    def test_safe_function_handles_long_inputs(self):
        """Test that safe function handles excessively long inputs gracefully."""
        # Input that exceeds reasonable numeric bounds
        long_input = "calculate " + "9" * 50

        result = extract_numeric_value_safe(long_input)

        # Should return None due to length limits
        assert result is None

    def test_realistic_use_cases(self):
        """Test realistic use cases from the application context."""
        realistic_cases = [
            ("Transform columns 'age' to add 1", 1.0),
            ("Apply operation multiply 2.5", 2.5),
            ("Update values subtract 100", 100.0),
            ("Process data divide 3.14159", 3.14159),
            ("Modify column add 0", 0.0),
            ("Calculate value multiply 1000", 1000.0),
        ]

        for description, expected_value in realistic_cases:
            vulnerable_result = extract_numeric_value_vulnerable(description)
            safe_result = extract_numeric_value_safe(description)

            # Both should extract the same value for reasonable inputs
            assert vulnerable_result == expected_value
            assert safe_result == expected_value

    def test_malformed_numbers(self):
        """Test handling of malformed number strings."""
        malformed_cases = [
            "add 1.2.3",  # multiple dots
            "multiply 5.",  # trailing dot
            "subtract .7",  # leading dot
            "divide 1..2",  # double dots
            "value 1.2.3.4",  # multiple dots
        ]

        for case in malformed_cases:
            vulnerable_result = extract_numeric_value_vulnerable(case)
            safe_result = extract_numeric_value_safe(case)

            # Results might differ for malformed input, but safe should be robust
            print(f"Malformed input: {case}")
            print(f"  Vulnerable: {vulnerable_result}")
            print(f"  Safe: {safe_result}")

            # Safe function should not crash
            assert safe_result is None or isinstance(safe_result, float)
