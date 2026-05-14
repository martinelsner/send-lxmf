"""Shared router pool for safe concurrent LXMF sending."""

import os
import time

import filelock
import LXMF
import RNS


# Module-level singleton state
_router = None
_identity_registered = False
_source = None
_file_lock = None


def get(identity, storage_path, lock_path):
    """Get or create the singleton router instance."""
    global _router, _identity_registered, _source, _file_lock

    if _router is None:
        _file_lock = filelock.FileLock(lock_path, timeout=30)
        os.makedirs(os.path.dirname(lock_path), mode=0o755, exist_ok=True)

        _router = LXMF.LXMRouter(identity=identity, storagepath=storage_path)
        _source = _router.register_delivery_identity(identity)
        _identity_registered = True

    return _router, _source


def send(destination, content):
    """Send a message to a single destination, holding the file lock."""
    router, source = get(None, None, None)  # uses existing singleton
    with _file_lock:
        _send_one(router, source, destination, content)


def _send_one(router, source, destination, content):
    from send_lxmf.lib import DeliveryError

    destination_hash = destination["hash"]
    title = destination.get("title", "")
    fields = destination.get("fields", {})
    timeout = destination.get("timeout", 10)
    propagation_node = destination.get("propagation_node")

    RNS.log(f"Target  : {RNS.prettyhexrep(destination_hash)}")

    # Create destination for delivery
    recipient_identity = RNS.Identity.recall(destination_hash)
    identity_for_dest = recipient_identity if recipient_identity else destination_hash

    dest = RNS.Destination(
        identity_for_dest,
        RNS.Destination.OUT,
        RNS.Destination.SINGLE,
        "lxmf",
        "delivery",
    )

    # Track delivery state
    delivered = [False]
    failed = [None]

    def on_delivered(msg):
        delivered[0] = True

    def on_failed(msg):
        failed[0] = msg

    # Try direct first
    msg = LXMF.LXMessage(
        dest, source, content,
        title=title, fields=fields,
        desired_method=LXMF.LXMessage.DIRECT,
    )
    msg.register_delivery_callback(on_delivered)
    msg.register_failed_callback(on_failed)

    router.handle_outbound(msg)
    RNS.log("Message queued (direct), waiting for delivery...")

    deadline = time.time() + timeout
    while not delivered[0] and not failed[0]:
        if time.time() > deadline:
            break
        router.process_outbound()
        time.sleep(0.2)

    if delivered[0]:
        RNS.log("Message delivered successfully (direct).")
        return

    # Direct failed/timed out - try propagated if we have a propagation node
    if not propagation_node:
        target_hex = RNS.prettyhexrep(destination_hash)
        if failed[0]:
            reason = _failure_reason(failed[0])
            raise DeliveryError(f"delivery failed: {reason}")
        else:
            raise DeliveryError(
                f"delivery failed: message delivery timed out after {timeout}s "
                f"waiting for direct delivery to {target_hex}"
            )

    # Propagated delivery
    RNS.log("Direct delivery failed, attempting propagated delivery...")

    # LXMRouter.set_outbound_propagation_node() requires:
    # 1. The hash as bytes (not a hex string)
    # 2. The truncated hash (16 bytes / 128 bits), not the full 32-byte hash
    # The CLI receives a 32-character hex string from argparse, so we must convert
    # to bytes first, then truncate to the expected length. Without this conversion,
    # slicing the string would produce 16 characters (not bytes), causing
    # "Invalid destination hash for outbound propagation node" error.
    if isinstance(propagation_node, str):
        propagation_node = bytes.fromhex(propagation_node)
    truncated_propagation_node = propagation_node[: RNS.Identity.TRUNCATED_HASHLENGTH // 8]
    router.set_outbound_propagation_node(truncated_propagation_node)

    msg = LXMF.LXMessage(
        dest, source, content,
        title=title, fields=fields,
        desired_method=LXMF.LXMessage.PROPAGATED,
    )
    msg.register_delivery_callback(on_delivered)
    msg.register_failed_callback(on_failed)

    router.handle_outbound(msg)
    RNS.log("Message queued (propagated), waiting for propagation link...")

    # Propagated delivery requires significantly more time than direct delivery.
    # The LXMRouter uses PATH_REQUEST_WAIT (~7s) for initial path discovery to the
    # propagation node, plus DELIVERY_RETRY_WAIT (10s) between attempts, and time
    # to establish an actual link. Using the same short timeout as direct delivery
    # (10s) will always fail. A minimum of 60s or 3x the direct timeout gives the
    # propagation mechanism time to discover paths and establish the link.
    prop_timeout = max(timeout * 3, 60)
    deadline = time.time() + prop_timeout
    while not delivered[0] and not failed[0]:
        if time.time() > deadline:
            break
        router.process_outbound()
        time.sleep(0.2)

    if delivered[0]:
        RNS.log("Message delivered successfully (propagated).")
    elif failed[0]:
        reason = _failure_reason(failed[0])
        raise DeliveryError(f"delivery failed: {reason}")
    else:
        raise DeliveryError(
            f"delivery failed: message delivery timed out after {timeout}s "
            f"waiting for propagation link"
        )


def _failure_reason(msg) -> str:
    if msg is None:
        return "unknown"
    state_map = {
        LXMF.LXMessage.FAILED: "failed",
        LXMF.LXMessage.REJECTED: "rejected",
        LXMF.LXMessage.CANCELLED: "cancelled",
    }
    return state_map.get(msg.state, f"state={msg.state}")


# Backwards compatibility
class SenderPool:
    """Deprecated: use module-level get() instead.

    This class is a singleton wrapper around module-level state.
    Calling SenderPool() returns the singleton; use SenderPool.get()
    to initialize with specific parameters.
    """
    _instance = None

    def __new__(cls, identity=None, storage_path=None, lock_path=None):
        global _router, _identity_registered, _source, _file_lock

        # If module state already exists, return existing singleton
        if _router is not None:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

        # Otherwise initialize (backwards compat for tests that call SenderPool() directly)
        _file_lock = filelock.FileLock(lock_path, timeout=30)
        os.makedirs(os.path.dirname(lock_path), mode=0o755, exist_ok=True)
        _router = LXMF.LXMRouter(identity=identity, storagepath=storage_path)
        _source = _router.register_delivery_identity(identity)
        _identity_registered = True

        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def get(identity, storage_path, lock_path):
        get(identity, storage_path, lock_path)
        return SenderPool

    def _get_router(self):
        return _router

    def get_source(self):
        return _source

    def send(self, destination, content, **kwargs):
        send(destination, content)


def _reset_for_testing():
    """Reset module state - for testing only."""
    global _router, _identity_registered, _source, _file_lock
    _router = None
    _identity_registered = False
    _source = None
    _file_lock = None
    SenderPool._instance = None