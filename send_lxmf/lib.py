"""Shared LXMF sending logic."""

import os

import LXMF
import RNS

TIMEOUT = 10  # seconds to wait for path / identity / delivery

SYSTEM_IDENTITY_PATH = "/var/lib/send-lxmf/identity"
SYSTEM_STORAGE_PATH = "/var/lib/send-lxmf/storage"
SYSTEM_LOCK_PATH = "/var/lib/send-lxmf/sending.lock"


class LXMFError(Exception):
    """Base exception for LXMF sending errors."""

    pass


class InvalidHashError(LXMFError):
    """Raised when a hex hash is invalid."""

    pass


class DeliveryError(LXMFError):
    """Raised when message delivery fails."""

    pass


class IdentityError(LXMFError):
    """Raised when an identity file cannot be loaded."""

    pass


class AttachmentError(LXMFError):
    """Raised when an attachment file cannot be found."""

    pass


def send_message(
    destinations: list[str],
    content: str,
    identity_path: str | None = None,
    display_name: str | None = None,
    title: str = "",
    prepend_title: bool = True,
    attachments: list[str] | None = None,
    rnsconfig: str | None = None,
    propagation_node: str | None = None,
    timeout: int | None = None,
) -> None:
    """Send an LXMF message to one or more destinations.

    Raises LXMFError (or subclasses) on errors.
    """
    effective_timeout = timeout if timeout is not None else TIMEOUT

    destination_hashes = [
        _parse_hex_hash(hex_str, "hex hash") for hex_str in destinations
    ]

    if not content:
        raise LXMFError("no message content provided.")

    reticulum = RNS.Reticulum(configdir=rnsconfig, require_shared_instance=True)
    RNS.log(f"RNS config dir: {rnsconfig or reticulum.configdir}")
    RNS.log(f"send-lxmf data dir: {os.path.dirname(SYSTEM_IDENTITY_PATH)}")

    if identity_path:
        identity_path = os.path.expanduser(identity_path)
        if not os.path.isfile(identity_path):
            raise IdentityError(f"identity file not found: {identity_path}")
        sender_identity = RNS.Identity.from_file(identity_path)
    else:
        id_dir = os.path.dirname(SYSTEM_IDENTITY_PATH)
        os.makedirs(id_dir, exist_ok=True, mode=0o777)
        if not os.path.isfile(SYSTEM_IDENTITY_PATH):
            sender_identity = RNS.Identity()
            sender_identity.to_file(SYSTEM_IDENTITY_PATH)
        else:
            sender_identity = RNS.Identity.from_file(SYSTEM_IDENTITY_PATH)
        identity_path = SYSTEM_IDENTITY_PATH

    storage_path = SYSTEM_STORAGE_PATH
    os.makedirs(storage_path, exist_ok=True, mode=0o777)

    from send_lxmf.pool import get as pool_get
    from send_lxmf.pool import send as pool_send

    router, source = pool_get(sender_identity, storage_path, SYSTEM_LOCK_PATH)

    if display_name:
        RNS.log(f"Sender  : {display_name} <{RNS.prettyhexrep(source.hash)}>")
        router.announce(source.hash)
    else:
        RNS.log(f"Sender  : {RNS.prettyhexrep(source.hash)}")

    if prepend_title and title:
        content = title + "\n\n" + content

    fields = {LXMF.FIELD_RENDERER: LXMF.RENDERER_MARKDOWN}

    if attachments:
        file_list = []
        for path in attachments:
            path = os.path.expanduser(path)
            if not os.path.isfile(path):
                raise AttachmentError(f"attachment not found: {path}")
            with open(path, "rb") as f:
                file_list.append([os.path.basename(path), f.read()])
        fields[LXMF.FIELD_FILE_ATTACHMENTS] = file_list

    for destination_hash in destination_hashes:
        pool_send(
            destination={
                "hash": destination_hash,
                "source": source,
                "title": title,
                "fields": fields,
                "timeout": effective_timeout,
                "propagation_node": propagation_node,
            },
            content=content,
        )


def _parse_hex_hash(hex_str: str, description: str) -> bytes:
    """Convert a hex string to bytes, raising on invalid input."""
    try:
        return bytes.fromhex(hex_str)
    except ValueError:
        raise InvalidHashError(f"'{hex_str}' is not a valid {description}.")