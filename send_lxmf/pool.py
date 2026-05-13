"""Shared router pool for safe concurrent LXMF sending."""

import os
import time

import filelock
import LXMF
import RNS


class SenderPool:
    """A singleton router pool that serializes sends via a file lock.

    A single LXMRouter instance is reused across all sends within a process,
    and a file lock ensures cross-process serialization to prevent msgpack
    storage corruption.
    """

    _instance = None

    def __init__(self, identity, storage_path, lock_path):
        self.identity = identity
        self.storage_path = storage_path
        self._router = None
        self._identity_registered = False
        self._file_lock = filelock.FileLock(lock_path, timeout=30)
        os.makedirs(os.path.dirname(lock_path), mode=0o755, exist_ok=True)

    @classmethod
    def get(cls, identity, storage_path, lock_path):
        """Get or create the singleton SenderPool instance."""
        if cls._instance is None:
            cls._instance = cls(identity, storage_path, lock_path)
        return cls._instance

    def send(self, destination, content, **kwargs):
        """Send a message to a single destination, holding the file lock."""
        with self._file_lock:
            router = self._get_router()
            self._send_one(router, destination, content, **kwargs)

    def _get_router(self):
        """Lazily create and register the shared LXMRouter instance."""
        if self._router is None:
            self._router = LXMF.LXMRouter(
                identity=self.identity, storagepath=self.storage_path
            )
        if not self._identity_registered:
            self._source = self._router.register_delivery_identity(self.identity)
            self._identity_registered = True
        return self._router

    def get_source(self):
        """Return the registered delivery identity source."""
        self._get_router()
        return self._source

    def _send_one(self, router, destination, content, **kwargs):
        from send_lxmf.lib import DeliveryError

        destination_hash = destination["hash"]
        source = destination["source"]
        title = destination.get("title", "")
        fields = destination.get("fields", {})
        effective_timeout = destination.get("timeout", 10)
        propagation_node = destination.get("propagation_node")

        RNS.log(f"Target  : {RNS.prettyhexrep(destination_hash)}")

        if not RNS.Transport.has_path(destination_hash):
            RNS.log(f"Requesting path to {RNS.prettyhexrep(destination_hash)}...")
            RNS.Transport.request_path(destination_hash)

        recipient_identity = RNS.Identity.recall(destination_hash)
        if recipient_identity is None:
            RNS.log(f"Destination identity not known, requesting announce from {RNS.prettyhexrep(destination_hash)}...")
            RNS.Transport.request_path(destination_hash)
            deadline = time.time() + effective_timeout
            while recipient_identity is None:
                if time.time() > deadline:
                    RNS.log("Destination identity not found, message may fail")
                    break
                time.sleep(0.2)
                recipient_identity = RNS.Identity.recall(destination_hash)
            if recipient_identity is None:
                RNS.log("Destination identity still not available, proceeding with delivery attempt...")

        dest = RNS.Destination(
            recipient_identity if recipient_identity else destination_hash,
            RNS.Destination.OUT,
            RNS.Destination.SINGLE,
            "lxmf",
            "delivery",
        )

        msg = LXMF.LXMessage(
            dest,
            source,
            content,
            title=title,
            fields=fields,
            desired_method=LXMF.LXMessage.DIRECT,
        )

        delivered = False
        failed = False
        failed_msg = None
        timed_out = False

        def on_delivered(msg):
            nonlocal delivered
            delivered = True

        def on_failed(msg):
            nonlocal failed, failed_msg
            failed = True
            failed_msg = msg

        msg.register_delivery_callback(on_delivered)
        msg.register_failed_callback(on_failed)

        router.handle_outbound(msg)
        RNS.log("Message queued (direct), waiting for delivery...")

        deadline = time.time() + effective_timeout
        while not delivered and not failed:
            if time.time() > deadline:
                timed_out = True
                failed = True
                break
            router.process_outbound()
            time.sleep(0.2)

        if delivered:
            RNS.log("Message delivered successfully (direct).")
        elif propagation_node:
            pn_hash = destination["pn_hash"]
            RNS.log(f"Direct delivery failed, trying propagated via {RNS.prettyhexrep(pn_hash)}...")

            delivered = False
            failed = False
            failed_msg = None
            timed_out = False

            msg = LXMF.LXMessage(
                dest,
                source,
                content,
                title=title,
                fields=fields,
                desired_method=LXMF.LXMessage.PROPAGATED,
            )

            msg.register_delivery_callback(on_delivered)
            msg.register_failed_callback(on_failed)

            self._setup_propagation_link(router, pn_hash, effective_timeout)
            router.handle_outbound(msg)
            RNS.log("Message queued (propagated), waiting for delivery...")

            deadline = time.time() + effective_timeout
            while not delivered and not failed:
                if time.time() > deadline:
                    timed_out = True
                    failed = True
                    break
                router.process_outbound()
                time.sleep(0.2)

            if delivered:
                RNS.log(
                    "Propagation link active, verifying message storage..."
                )
                self._wait_for_propagation_storage(router, pn_hash, effective_timeout)
                RNS.log("Message delivered and stored by propagation node.")
            else:
                target_hex = RNS.prettyhexrep(destination["hash"])
                if timed_out:
                    raise DeliveryError(
                        f"message delivery timed out after {effective_timeout}s "
                        f"waiting for propagation node {RNS.prettyhexrep(pn_hash)} "
                        f"to accept message for {target_hex}. "
                        f"The propagation node may be offline or unreachable."
                    )
                else:
                    reason = self._failure_reason(failed_msg)
                    raise DeliveryError(f"message delivery failed ({reason}).")
        else:
            target_hex = RNS.prettyhexrep(destination["hash"])
            if timed_out:
                raise DeliveryError(
                    f"message delivery timed out after {effective_timeout}s "
                    f"waiting for direct delivery to {target_hex}. "
                    f"The recipient may be offline or unreachable."
                )
            else:
                reason = self._failure_reason(failed_msg)
                raise DeliveryError(f"message delivery failed ({reason}).")

    def _setup_propagation_link(self, router, pn_hash, timeout):
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

    def _wait_for_propagation_storage(self, router, pn_hash, delivery_timeout):
        deadline = time.time() + delivery_timeout
        while router.outbound_propagation_link.status == RNS.Link.ACTIVE:
            if time.time() > deadline:
                return True
            router.process_outbound()
            time.sleep(0.5)
        return True

    @staticmethod
    def _failure_reason(msg) -> str:
        if msg is None:
            return "unknown"

        state_map = {
            LXMF.LXMessage.FAILED: "failed",
            LXMF.LXMessage.REJECTED: "rejected",
            LXMF.LXMessage.CANCELLED: "cancelled",
        }
        return state_map.get(msg.state, f"state={msg.state}")