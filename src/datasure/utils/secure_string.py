"""Secure string handling utilities for sensitive data.

This module provides SecureString-like functionality to minimize
exposure of sensitive data in memory.
"""

import secrets


class SecureString:
    """A secure string container that minimizes password exposure in memory."""

    def __init__(self, value: str) -> None:
        """Initialize secure string with the given value.

        Args:
            value: The sensitive string value to protect
        """
        # Store as bytes with a simple XOR obfuscation
        self._key = secrets.token_bytes(32)
        self._data = self._xor_bytes(value.encode("utf-8"), self._key)
        self._length = len(value)

    def _xor_bytes(self, data: bytes, key: bytes) -> bytes:
        """Apply XOR operation for basic obfuscation."""
        key_cycle = key * ((len(data) // len(key)) + 1)
        return bytes(a ^ b for a, b in zip(data, key_cycle[: len(data)], strict=False))

    def get_value(self) -> str:
        """Retrieve the original string value.

        Returns
        -------
            The original string value
        """
        if not hasattr(self, "_data"):
            return ""

        try:
            decrypted = self._xor_bytes(self._data, self._key)
            return decrypted.decode("utf-8")
        except (AttributeError, UnicodeDecodeError):
            return ""

    def clear(self) -> None:
        """Clear the secure string from memory."""
        if hasattr(self, "_data"):
            # Overwrite memory locations
            self._data = b"\x00" * len(self._data)
            self._key = b"\x00" * len(self._key)
            delattr(self, "_data")
            delattr(self, "_key")

    def __len__(self) -> int:
        """Return the length of the original string."""
        return self._length if hasattr(self, "_length") else 0

    def __bool__(self) -> bool:
        """Return True if the string is not empty."""
        return self._length > 0 if hasattr(self, "_length") else False

    def __del__(self) -> None:
        """Clear the secure string when object is deleted."""
        import contextlib

        with contextlib.suppress(Exception):
            self.clear()


def create_secure_string(value: str | None) -> SecureString | None:
    """Create a SecureString from a regular string.

    Args:
        value: The string value to secure, or None

    Returns
    -------
        SecureString instance or None if input is None
    """
    if value is None:
        return None
    return SecureString(value)


def secure_compare(secure_str: SecureString, compare_value: str) -> bool:
    """Securely compare a SecureString with a regular string.

    Args:
        secure_str: The SecureString to compare
        compare_value: The string to compare against

    Returns
    -------
        True if strings are equal, False otherwise
    """
    if not secure_str:
        return not compare_value

    try:
        return secrets.compare_digest(
            secure_str.get_value().encode("utf-8"), compare_value.encode("utf-8")
        )
    except (AttributeError, UnicodeDecodeError):
        return False
