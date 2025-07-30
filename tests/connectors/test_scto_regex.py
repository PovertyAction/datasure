"""Test regex vulnerability in SurveyCTO connector."""

import re
import time


class TestServerNameRegex:
    """Test cases for server name validation regex vulnerability."""

    def test_vulnerable_regex_pattern(self):
        """Test the original vulnerable regex pattern."""
        # This is the vulnerable pattern from the code
        vulnerable_pattern = r"\b[a-z]+[a-z0-9]+\b"

        # These should match
        assert re.fullmatch(vulnerable_pattern, "server1")
        assert re.fullmatch(vulnerable_pattern, "myserver2")
        assert re.fullmatch(vulnerable_pattern, "test123")
        assert re.fullmatch(
            vulnerable_pattern, "server"
        )  # matches because [a-z0-9]+ includes letters
        assert re.fullmatch(vulnerable_pattern, "abc")  # matches for same reason

        # These should not match
        assert not re.fullmatch(vulnerable_pattern, "")
        assert not re.fullmatch(vulnerable_pattern, "Server1")  # uppercase
        assert not re.fullmatch(vulnerable_pattern, "123")  # starts with number
        assert not re.fullmatch(vulnerable_pattern, "server-1")  # contains hyphen

    def test_vulnerable_regex_backtracking(self):
        """Test that the vulnerable regex exhibits catastrophic backtracking."""
        vulnerable_pattern = r"\b[a-z]+[a-z0-9]+\b"

        # This string should cause catastrophic backtracking:
        # It starts with lowercase letters, then has many lowercase letters
        # but ends with an uppercase letter that breaks the pattern
        # causing the regex engine to backtrack extensively
        problematic_string = "a" * 20 + "A"

        start_time = time.time()
        result = re.fullmatch(vulnerable_pattern, problematic_string)
        end_time = time.time()

        # Should not match due to uppercase letter at the end
        assert not result

        # Document the timing (for demonstration - not a hard assertion)
        execution_time = end_time - start_time
        print(
            f"Vulnerable regex took {execution_time:.4f} seconds for input: {problematic_string}"
        )

    def test_safe_regex_pattern(self):
        """Test a safe regex pattern that avoids backtracking."""
        # This is the safe pattern we'll implement - matches same logic as vulnerable
        # but without backtracking. Must start with lowercase letter, then have
        # 1-63 lowercase letters or numbers (reasonable server name length)
        safe_pattern = r"^[a-z][a-z0-9]{1,63}$"

        # These should match (same as vulnerable pattern)
        assert re.fullmatch(safe_pattern, "server1")
        assert re.fullmatch(safe_pattern, "myserver2")
        assert re.fullmatch(safe_pattern, "test123")
        assert re.fullmatch(
            safe_pattern, "server"
        )  # matches because [a-z0-9]+ includes letters
        assert re.fullmatch(safe_pattern, "abc")  # matches for same reason

        # These should not match (same as vulnerable pattern)
        assert not re.fullmatch(safe_pattern, "")
        assert not re.fullmatch(safe_pattern, "Server1")  # uppercase
        assert not re.fullmatch(safe_pattern, "123")  # starts with number
        assert not re.fullmatch(safe_pattern, "server-1")  # contains hyphen
        assert not re.fullmatch(safe_pattern, "1server")  # starts with number

    def test_safe_regex_no_backtracking(self):
        """Test that the safe regex does not exhibit catastrophic backtracking."""
        safe_pattern = r"^[a-z][a-z0-9]{1,63}$"

        # Same problematic string as before
        problematic_string = "a" * 20 + "A"

        start_time = time.time()
        result = re.fullmatch(safe_pattern, problematic_string)
        end_time = time.time()

        # Should not match due to uppercase letter at the end
        assert not result

        # Should be much faster
        execution_time = end_time - start_time
        print(
            f"Safe regex took {execution_time:.4f} seconds for input: {problematic_string}"
        )

        # Should complete in reasonable time (less than 0.01 seconds)
        assert execution_time < 0.01

    def test_edge_cases(self):
        """Test edge cases for server name validation."""
        safe_pattern = r"^[a-z][a-z0-9]{1,63}$"

        # Edge cases that should match
        assert re.fullmatch(safe_pattern, "a1")
        assert re.fullmatch(safe_pattern, "server123")
        assert re.fullmatch(safe_pattern, "longservername999")
        assert re.fullmatch(safe_pattern, "ab")  # letters only (allowed)
        assert re.fullmatch(safe_pattern, "server")  # letters only (allowed)

        # Edge cases that should not match
        assert not re.fullmatch(safe_pattern, "a")  # too short (need at least 2 chars)
        assert not re.fullmatch(safe_pattern, "1")  # just a number
        assert not re.fullmatch(safe_pattern, "serverA")  # uppercase letter
        assert not re.fullmatch(safe_pattern, "server_1")  # underscore
        assert not re.fullmatch(safe_pattern, "server.1")  # dot
        assert not re.fullmatch(safe_pattern, " server1")  # leading space
        assert not re.fullmatch(safe_pattern, "server1 ")  # trailing space

        # Test length limits (should not match if too long)
        long_name = "a" + "b" * 64  # 65 chars total, should fail
        assert not re.fullmatch(safe_pattern, long_name)

        # Test maximum allowed length (should match)
        max_length_name = "a" + "b" * 63  # 64 chars total, should pass
        assert re.fullmatch(safe_pattern, max_length_name)

    def test_performance_comparison(self):
        """Compare performance between vulnerable and safe regex patterns."""
        vulnerable_pattern = r"\b[a-z]+[a-z0-9]+\b"
        safe_pattern = r"^[a-z][a-z0-9]{1,63}$"

        # Test string that could cause backtracking
        test_strings = [
            "server1",
            "myserver123",
            "a" * 10 + "1",
            "a" * 15 + "B",  # This one causes backtracking in vulnerable regex
        ]

        for test_string in test_strings:
            # Test vulnerable regex
            start_time = time.time()
            vulnerable_result = re.fullmatch(vulnerable_pattern, test_string)
            vulnerable_time = time.time() - start_time

            # Test safe regex
            start_time = time.time()
            safe_result = re.fullmatch(safe_pattern, test_string)
            safe_time = time.time() - start_time

            print(f"Input: {test_string}")
            print(f"  Vulnerable: {vulnerable_result} ({vulnerable_time:.6f}s)")
            print(f"  Safe:       {safe_result} ({safe_time:.6f}s)")

            # The safe regex should always be faster or similar
            # (allowing some tolerance for measurement variations)
            assert safe_time <= vulnerable_time + 0.001

    def test_bounded_quantifier_benefits(self):
        """Test that bounded quantifiers provide additional safety."""
        bounded_pattern = r"^[a-z][a-z0-9]{1,63}$"

        # Test with extremely long input that could cause issues with unbounded
        # quantifiers
        very_long_input = "a" * 1000

        start_time = time.time()
        result = re.fullmatch(bounded_pattern, very_long_input)
        end_time = time.time()

        # Should fail quickly due to length limit
        assert not result
        execution_time = end_time - start_time

        # Should be very fast (much less than 0.01 seconds)
        assert execution_time < 0.01
        print(
            f"Bounded regex rejected {len(very_long_input)}-char input in {execution_time:.6f}s"
        )

        # Test realistic server names still work
        realistic_names = [
            "server1",
            "myproject2023",
            "dev",
            "prod123",
            "staging",
        ]

        for name in realistic_names:
            assert re.fullmatch(bounded_pattern, name), (
                f"Should match realistic name: {name}"
            )


class TestEmailRegexSecurity:
    """Test email regex security improvements."""

    def test_vulnerable_email_regex(self):
        """Test the original vulnerable email regex pattern."""
        vulnerable_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"

        # These should match
        assert re.fullmatch(vulnerable_pattern, "user@example.com")
        assert re.fullmatch(vulnerable_pattern, "test.user@domain.org")
        assert re.fullmatch(vulnerable_pattern, "admin+tag@site.net")

        # These should not match
        assert not re.fullmatch(vulnerable_pattern, "invalid.email")
        assert not re.fullmatch(vulnerable_pattern, "@domain.com")
        assert not re.fullmatch(vulnerable_pattern, "user@")

    def test_safe_email_regex(self):
        """Test the safe email regex pattern with bounded quantifiers."""
        safe_pattern = r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,63}\.[A-Za-z]{2,7}$"

        # These should match (same as vulnerable pattern)
        assert re.fullmatch(safe_pattern, "user@example.com")
        assert re.fullmatch(safe_pattern, "test.user@domain.org")
        assert re.fullmatch(safe_pattern, "admin+tag@site.net")

        # These should not match (same as vulnerable pattern)
        assert not re.fullmatch(safe_pattern, "invalid.email")
        assert not re.fullmatch(safe_pattern, "@domain.com")
        assert not re.fullmatch(safe_pattern, "user@")

        # Test length limits
        long_local = "a" * 65 + "@example.com"  # local part too long
        assert not re.fullmatch(safe_pattern, long_local)

        long_domain = (
            "user@" + "a" * 65 + ".com"
        )  # domain part too long (exceeds 63 limit)
        assert not re.fullmatch(safe_pattern, long_domain)

        # Test maximum allowed lengths
        max_local = "a" * 64 + "@example.com"  # exactly 64 chars in local part
        assert re.fullmatch(safe_pattern, max_local)

    def test_email_regex_no_backtracking(self):
        """Test that the safe email regex does not exhibit catastrophic backtracking."""
        safe_pattern = r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,63}\.[A-Za-z]{2,7}$"

        # Problematic input that could cause backtracking
        problematic_email = "a" * 100 + "@" + "b" * 100 + ".INVALID"

        start_time = time.time()
        result = re.fullmatch(safe_pattern, problematic_email)
        end_time = time.time()

        # Should not match due to length limits
        assert not result

        # Should be very fast
        execution_time = end_time - start_time
        assert execution_time < 0.01
        print(f"Safe email regex rejected long input in {execution_time:.6f}s")


def validate_email_vulnerable(email):
    """Original vulnerable email validation function."""
    return re.fullmatch(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", email)


def validate_email_safe(email):
    """Safe email validation function with bounded quantifiers."""
    return re.fullmatch(
        r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,63}\.[A-Za-z]{2,7}$", email
    )


def validate_server_name_vulnerable(servername):
    """Original vulnerable server name validation function."""
    return re.fullmatch(r"\b[a-z]+[a-z0-9]+\b", servername)


def validate_server_name_safe(servername):
    """Safe server name validation function with bounded quantifiers."""
    return re.fullmatch(r"^[a-z][a-z0-9]{1,63}$", servername)


class TestServerNameValidation:
    """Test the server name validation functions."""

    def test_both_functions_same_results_valid_inputs(self):
        """Test that both functions return the same results for valid inputs."""
        valid_inputs = [
            "server1",
            "myserver2",
            "test123",
            "abc123",
            "s1",
        ]

        for input_str in valid_inputs:
            vulnerable_result = validate_server_name_vulnerable(input_str)
            safe_result = validate_server_name_safe(input_str)

            # Both should return truthy values for valid inputs
            assert bool(vulnerable_result) == bool(safe_result)

    def test_both_functions_same_results_invalid_inputs(self):
        """Test that both functions return the same results for invalid inputs."""
        invalid_inputs = [
            "",
            "Server1",
            "123",
            "server-1",
            "1server",
            "MYSERVER1",
            "my_server1",
            "server.1",
        ]

        for input_str in invalid_inputs:
            vulnerable_result = validate_server_name_vulnerable(input_str)
            safe_result = validate_server_name_safe(input_str)

            # Both should return falsy values for invalid inputs
            assert bool(vulnerable_result) == bool(safe_result)

    def test_both_functions_same_results_valid_inputs_extended(self):
        """Test that both functions return the same results for all valid inputs."""
        valid_inputs = [
            "server",  # both patterns allow this
            "server1",
            "myserver2",
            "test123",
            "abc",
            "ab",
            "a1",
        ]

        for input_str in valid_inputs:
            vulnerable_result = validate_server_name_vulnerable(input_str)
            safe_result = validate_server_name_safe(input_str)

            # Both should return truthy values for valid inputs
            assert bool(vulnerable_result) == bool(safe_result), (
                f"Mismatch for '{input_str}'"
            )
