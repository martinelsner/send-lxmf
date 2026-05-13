"""Shared LXMF sending logic."""

import os
import time

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

    Parameters
    ----------
    destinations : list[str]
        Recipient LXMF address(es) as hex strings.
    content : str
        Message body text.
    identity_path : str | None
        Path to a Reticulum identity file. When *None* a default
        identity is created/loaded from the platform data directory.
    display_name : str | None
        Sender display name to announce.
    title : str
        Message title (not shown by all clients).
    prepend_title : bool
        If *True*, prepend *title* to *content* separated by a blank line.
    attachments : list[str] | None
        Paths to files to attach.
    rnsconfig : str | None
        Path to alternative Reticulum config directory.
    propagation_node : str | None
        Hex hash of an LXMF propagation node used for propagated delivery.
    timeout : int | None
        Seconds to wait for delivery per method. Defaults to *TIMEOUT*.
    """
    from send_lxmf.pool import SenderPool

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

    pool = SenderPool.get(sender_identity, storage_path, SYSTEM_LOCK_PATH)
    router = pool._get_router()
    source = pool.get_source()
    router.announce(source.hash)
    RNS.Transport.request_path(source.hash)
    RNS.log("Waiting for announce to propagate...")
    time.sleep(2)

    if display_name:
        RNS.log(f"Sender  : {display_name} <{RNS.prettyhexrep(source.hash)}>")
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

    pn_hash = None
    if propagation_node:
        pn_hash = _parse_hex_hash(propagation_node, "propagation node hash")

    for destination_hash in destination_hashes:
        RNS.log(f"Requesting path to {RNS.prettyhexrep(destination_hash)}...")
        RNS.Transport.request_path(destination_hash)

        deadline = time.time() + effective_timeout
        while not RNS.Transport.has_path(destination_hash):
            if time.time() > deadline:
                RNS.log("Destination not reachable, continuing anyway...")
                break
            time.sleep(0.5)

        recipient_identity = RNS.Identity.recall(destination_hash)
        if recipient_identity is None:
            RNS.log("Destination identity not known locally, attempting announce download...")
            RNS.Transport.request_path(destination_hash)
            deadline = time.time() + effective_timeout
            while recipient_identity is None:
                if time.time() > deadline:
                    raise IdentityError("timed out waiting for recipient identity")
                time.sleep(0.5)
                recipient_identity = RNS.Identity.recall(destination_hash)

        pool.send(
            destination={
                "hash": destination_hash,
                "source": source,
                "title": title,
                "fields": fields,
                "timeout": effective_timeout,
                "propagation_node": propagation_node,
                "pn_hash": pn_hash,
            },
            content=content,
        )


def _parse_hex_hash(hex_str: str, description: str) -> bytes:
    """Convert a hex string to bytes, raising on invalid input."""
    try:
        return bytes.fromhex(hex_str)
    except ValueError:
        raise InvalidHashError(f"'{hex_str}' is not a valid {description}.")


def _setup_propagation_link(router, pn_hash: bytes, timeout: int) -> None:
    """Pre-establish link to propagation node for faster delivery."""
    router.set_outbound_propagation_node(pn_hash)

    if not RNS.Transport.has_path(pn_hash):
        RNS.Transport.request_path(pn_hash)
        deadline = time.time() + timeout
        while not RNS.Transport.has_path(pn_hash):
            if time.time() > deadline:
                RNS.log(
                    "Could not find path to propagation node, "
                    "will continue without pre-established link."
                )
                return
            time.sleep(0.2)

    if RNS.Transport.has_path(pn_hash):
        pn_identity = RNS.Identity.recall(pn_hash)
        if pn_identity:
            pn_dest = RNS.Destination(
                pn_identity,
                RNS.Destination.OUT,
                RNS.Destination.SINGLE,
                "lxmf",
                "propagation",
            )
            router.outbound_propagation_link = RNS.Link(
                pn_dest,
                established_callback=router.process_outbound,
            )
            router.outbound_propagation_link.set_packet_callback(
                router.propagation_transfer_signalling_packet,
            )
            RNS.log("Pre-establishing link to propagation node...")

            deadline = time.time() + timeout
            while router.outbound_propagation_link.status not in (
                RNS.Link.ACTIVE,
                RNS.Link.CLOSED,
            ):
                if time.time() > deadline:
                    break
                time.sleep(0.2)

            if router.outbound_propagation_link.status == RNS.Link.ACTIVE:
                RNS.log("Propagation link established.")
            else:
                RNS.log(
                    "Propagation link could not be established, "
                    "router will retry internally."
                )


def _wait_for_propagation_storage(
    router, pn_hash: bytes, delivery_timeout: int
) -> bool:
    """Wait for message propagation to complete.

    After a PROPAGATED delivery is reported, we keep the link active
    and process outbound messages. If the link stays ACTIVE for the
    duration, we consider the propagation successful.

    For persistent connections the link may stay open indefinitely,
    so we return True as long as we haven't failed.
    """
    deadline = time.time() + delivery_timeout
    while router.outbound_propagation_link.status == RNS.Link.ACTIVE:
        if time.time() > deadline:
            return True
        router.process_outbound()
        time.sleep(0.5)
    return True


def _failure_reason(msg) -> str:
    """Extract a human-readable failure reason from a failed LXMessage."""
    if msg is None:
        return "unknown"

    state_map = {
        LXMF.LXMessage.FAILED: "failed",
        LXMF.LXMessage.REJECTED: "rejected",
        LXMF.LXMessage.CANCELLED: "cancelled",
    }
    return state_map.get(msg.state, f"state={msg.state}")