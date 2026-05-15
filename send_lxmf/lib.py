"""Shared LXMF sending logic."""

import os
import time
from typing import Any, Optional

import filelock
import LXMF
import RNS

SYSTEM_IDENTITY_PATH = "/var/lib/send-lxmf/identity"
SYSTEM_STORAGE_PATH = "/var/lib/send-lxmf/storage"
SYSTEM_LOCK_PATH = "/var/lib/send-lxmf/sending.lock"
SYSTEM_CONFIG_PATH = "/var/lib/send-lxmf/config"


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


def _create_lock(lock_path: str) -> filelock.FileLock:
    """Create a file lock for synchronizing sends."""
    os.makedirs(os.path.dirname(lock_path), mode=0o755, exist_ok=True)
    return filelock.FileLock(lock_path, timeout=30)


def _create_router(identity: Any, storage_path: str) -> tuple[LXMF.LXMRouter, Any]:
    """Create and register an LXMRouter with an identity."""
    router = LXMF.LXMRouter(identity=identity, storagepath=storage_path)
    source = router.register_delivery_identity(identity)
    return router, source


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
) -> None:
    """Send an LXMF message to one or more destinations.

    Raises LXMFError (or subclasses) on errors.
    """

    destination_hashes = [
        _parse_hex_hash(hex_str, "hex hash") for hex_str in destinations
    ]

    if not destination_hashes:
        raise LXMFError("no destination provided.")

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

    router, source = _create_router(sender_identity, storage_path)

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

    lock = _create_lock(SYSTEM_LOCK_PATH)
    with lock:
        _send_message(router, source, destination_hashes, content, fields, propagation_node)


def _send_message(
    router: LXMF.LXMRouter,
    source: Any,
    destination_hashes: list[bytes],
    content: str,
    fields: dict[str, Any],
    propagation_node: str | None,
) -> None:
    """Send a message to multiple destinations, holding the file lock."""
    for destination_hash in destination_hashes:
        _send_one(router, source, destination_hash, content, fields, propagation_node)


def _send_one(
    router: LXMF.LXMRouter,
    source: Any,
    destination_hash: bytes,
    content: str,
    fields: dict[str, Any],
    propagation_node: str | None,
) -> None:
    RNS.log(f"Target  : {RNS.prettyhexrep(destination_hash)}")

    recipient_identity = RNS.Identity.recall(destination_hash)
    if not recipient_identity:
        raise DeliveryError(f"Recipient identity not found: {RNS.prettyhexrep(destination_hash)}")

    dest = RNS.Destination(
        recipient_identity,
        RNS.Destination.OUT,
        RNS.Destination.SINGLE,
        "lxmf",
        "delivery",
    )

    try:
        _send_direct(router, source, dest, content, fields)
        RNS.log("Message delivered successfully (direct).")
        return
    except DeliveryError:
        pass

    if not propagation_node:
        raise DeliveryError(
            "delivery failed: direct delivery failed and no propagation node available"
        )

    RNS.log(f"Direct delivery failed, attempting propagated delivery via {propagation_node}...")
    propagation_node_bytes = bytes.fromhex(propagation_node)
    router.set_outbound_propagation_node(propagation_node_bytes)

    _send_propagated(router, source, dest, content, fields)
    RNS.log("Message delivered successfully (propagated).")


def _send_direct(
    router: LXMF.LXMRouter,
    source: Any,
    dest: RNS.Destination,
    content: str,
    fields: dict[str, Any],
) -> None:
    _send_with_method(router, source, dest, content, fields, LXMF.LXMessage.DIRECT, "direct")


def _send_propagated(
    router: LXMF.LXMRouter,
    source: Any,
    dest: RNS.Destination,
    content: str,
    fields: dict[str, Any],
) -> None:
    _send_with_method(router, source, dest, content, fields, LXMF.LXMessage.PROPAGATED, "propagated")


def _send_with_method(
    router: LXMF.LXMRouter,
    source: Any,
    dest: RNS.Destination,
    content: str,
    fields: dict[str, Any],
    desired_method: int,
    method_name: str,
) -> None:
    delivered = False
    failed: Optional[LXMF.LXMessage] = None

    def on_delivered(msg: LXMF.LXMessage) -> None:
        nonlocal delivered
        delivered = True

    def on_failed(msg: LXMF.LXMessage) -> None:
        nonlocal failed
        failed = msg

    msg = LXMF.LXMessage(
        dest, source, content,
        title="",
        fields=fields,
        desired_method=desired_method,
    )
    msg.register_delivery_callback(on_delivered)
    msg.register_failed_callback(on_failed)

    router.handle_outbound(msg)
    RNS.log(f"Message queued ({method_name}), waiting for delivery...")

    while not delivered and not failed:
        router.process_outbound()
        time.sleep(0.2)

    if delivered:
        return

    state_map = {
        LXMF.LXMessage.FAILED: "failed",
        LXMF.LXMessage.REJECTED: "rejected",
        LXMF.LXMessage.CANCELLED: "cancelled",
    }
    reason = state_map.get(failed.state if failed else None, f"state={failed.state if failed else None}")
    raise DeliveryError(f"delivery failed: {reason}")


def _parse_hex_hash(hex_str: str, description: str) -> bytes:
    """Convert a hex string to bytes, raising on invalid input."""
    try:
        return bytes.fromhex(hex_str)
    except ValueError:
        raise InvalidHashError(f"'{hex_str}' is not a valid {description}.")


def load_config(path: str | None = None) -> dict[str, str]:
    """Load configuration from a file.

    Returns a dict with keys: display_name, destination, propagation_node.
    Only keys that are present and non-empty in the config are returned.
    """
    config_path = path or SYSTEM_CONFIG_PATH
    if not os.path.isfile(config_path):
        return {}
    result: dict[str, str] = {}
    try:
        with open(config_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key in ("display_name", "destination", "propagation_node"):
                    result[key] = value
    except OSError:
        pass
    return result