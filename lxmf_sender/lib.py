"""Shared LXMF utilities for the daemon."""

import time

import RNS

DEFAULT_SOCKET_PATH = "/run/lxmf-sender/lxmf-sender.sock"
DEFAULT_DATA_DIR = "/var/lib/reticulum/lxmf-sender"
DEFAULT_IDENTITY_PATH = "/var/lib/reticulum/lxmf-sender/identity"


class LXMFError(Exception):
    """Base exception for LXMF sending errors."""

    pass


class InvalidHashError(LXMFError):
    """Raised when a hex hash is invalid."""

    pass


class DeliveryError(LXMFError):
    """Raised when message delivery fails."""

    pass


def _parse_hex_hash(hex_str: str, description: str) -> bytes:
    """Convert a hex string to bytes, raising on invalid input."""
    try:
        return bytes.fromhex(hex_str)
    except ValueError:
        raise InvalidHashError(f"'{hex_str}' is not a valid {description}.")
