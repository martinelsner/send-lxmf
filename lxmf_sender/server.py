"""LXMF message daemon.

Owns the router, identity, and storage. Provides a Unix socket interface
for CLI tools to submit messages without each process needing its own router.
"""

import asyncio
import configparser
import json
import os
import signal
import socket
import threading
import time
from typing import Any

import LXMF
import RNS

from lxmf_sender.lib import (
    DEFAULT_DATA_DIR,
    DEFAULT_IDENTITY_PATH,
    DEFAULT_SOCKET_PATH,
    DeliveryError,
    _parse_hex_hash,
)
from lxmf_sender.queue import MessageQueue

APP_NAME = "send-lxmf"

OPPURTUNISTIC_TIMEOUT = 60.0


class DaemonError(Exception):
    """Base exception for daemon errors."""


class LXMDaemon:
    """LXMF message daemon.

    Manages a persistent LXMRouter instance and accepts message requests
    via a Unix socket. Messages are enqueued and processed asynchronously.
    """

    def __init__(
        self,
        data_dir: str | None = None,
        identity_path: str | None = None,
        socket_path: str | None = None,
        rnsconfig: str | None = None,
        propagation_node: str | None = None,
        display_name: str | None = None,
        pid_file: str | None = None,
    ):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.identity_path = identity_path
        self.socket_path = socket_path or DEFAULT_SOCKET_PATH
        self.rnsconfig = rnsconfig
        self.propagation_node = propagation_node
        self.display_name = display_name
        self.pid_file = pid_file

        self._router: LXMF.LXMRouter | None = None
        self._source: RNS.Destination | None = None
        self._server_socket: socket.socket | None = None
        self._shutdown_event = threading.Event()
        self._loop_thread: threading.Thread | None = None
        self._queue: MessageQueue | None = None
        self._queue_processor_thread: threading.Thread | None = None

    def _ensure_directories(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        run_dir = os.path.dirname(self.socket_path)
        os.makedirs(run_dir, exist_ok=True)

    def _load_or_create_identity(self) -> RNS.Identity:
        if self.identity_path:
            identity_path = os.path.expanduser(self.identity_path)
            if not os.path.isfile(identity_path):
                raise DaemonError(f"identity file not found: {identity_path}")
            return RNS.Identity.from_file(identity_path)

        identity_path = os.path.join(self.data_dir, "identity")
        if os.path.isfile(identity_path):
            return RNS.Identity.from_file(identity_path)

        identity = RNS.Identity()
        identity.to_file(identity_path)
        RNS.log(f"Created new sender identity, saved to {identity_path}")
        return identity

    def start(self) -> None:
        self._ensure_directories()

        RNS.log(f"Data dir: {self.data_dir}")
        RNS.log(f"Socket   : {self.socket_path}")
        RNS.log(f"RNS config: {self.rnsconfig or 'default'}")

        reticulum = RNS.Reticulum(configdir=self.rnsconfig)

        sender_identity = self._load_or_create_identity()

        storage_path = os.path.join(self.data_dir, "lxmf")
        self._router = LXMF.LXMRouter(
            identity=sender_identity, storagepath=storage_path
        )
        self._source = self._router.register_delivery_identity(
            sender_identity, display_name=self.display_name
        )

        if self.display_name:
            self._router.announce(self._source.hash)

        RNS.log(f"Sender  : {RNS.prettyhexrep(self._source.hash)}")

        queue_db_path = os.path.join(self.data_dir, "queue.db")
        self._queue = MessageQueue(queue_db_path)

        if self.pid_file:
            with open(self.pid_file, "w") as f:
                f.write(str(os.getpid()))

        self._queue_processor_thread = threading.Thread(
            target=self._run_queue_processor, daemon=True
        )
        self._queue_processor_thread.start()

        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()

    def _run_queue_processor(self) -> None:
        while not self._shutdown_event.is_set():
            self._process_queue()
            time.sleep(1.0)

    def _process_queue(self) -> None:
        if self._router is None or self._source is None:
            return

        messages = self._queue.get_pending(limit=10)
        for msg in messages:
            self._try_deliver_message(msg)

    def _try_deliver_message(self, msg) -> None:
        self._queue.mark_attempt(msg.id)

        for destination_hash in msg.destinations:
            RNS.log(f"Target  : {RNS.prettyhexrep(destination_hash)}")

            if not RNS.Transport.has_path(destination_hash):
                RNS.log("No path, requesting...")
                RNS.Transport.request_path(destination_hash)

            recipient_identity = RNS.Identity.recall(destination_hash)
            if recipient_identity is None:
                deadline = time.time() + OPPURTUNISTIC_TIMEOUT
                while recipient_identity is None:
                    if time.time() > deadline:
                        RNS.log("timed out waiting for recipient identity.")
                        break
                    time.sleep(0.2)
                    recipient_identity = RNS.Identity.recall(destination_hash)

            if recipient_identity is None:
                RNS.log("Could not resolve recipient identity.")
                continue

            destination = RNS.Destination(
                recipient_identity,
                RNS.Destination.OUT,
                RNS.Destination.SINGLE,
                "lxmf",
                "delivery",
            )

            if msg.propagation_node:
                methods = [
                    LXMF.LXMessage.OPPORTUNISTIC,
                    LXMF.LXMessage.PROPAGATED,
                ]
            else:
                methods = [LXMF.LXMessage.OPPORTUNISTIC]

            delivered = False
            failed = False

            def on_delivered(lxmsg):
                nonlocal delivered
                delivered = True

            def on_failed(lxmsg):
                nonlocal failed
                failed = True

            message = LXMF.LXMessage(
                destination,
                self._source,
                msg.content,
                title=msg.title,
                fields=msg.fields,
                desired_method=methods[0],
            )
            message.register_delivery_callback(on_delivered)
            message.register_failed_callback(on_failed)

            self._router.handle_outbound(message)
            RNS.log("Message queued, waiting for opportunistic delivery...")

            deadline = time.time() + OPPURTUNISTIC_TIMEOUT
            while not delivered and not failed:
                if time.time() > deadline:
                    RNS.log("Opportunistic delivery timed out.")
                    break
                self._router.process_outbound()
                time.sleep(0.2)

            if delivered:
                RNS.log("Message delivered successfully.")
                self._queue.mark_done(msg.id)
                return
            elif msg.propagation_node and methods[0] == LXMF.LXMessage.OPPORTUNISTIC:
                RNS.log("Trying propagated delivery...")
                message2 = LXMF.LXMessage(
                    destination,
                    self._source,
                    msg.content,
                    title=msg.title,
                    fields=msg.fields,
                    desired_method=LXMF.LXMessage.PROPAGATED,
                )
                message2.register_delivery_callback(on_delivered)
                message2.register_failed_callback(on_failed)
                self._router.handle_outbound(message2)

                deadline = time.time() + OPPURTUNISTIC_TIMEOUT
                while not delivered and not failed:
                    self._router.process_outbound()
                    time.sleep(0.2)

                if delivered:
                    RNS.log("Message delivered via propagation node.")
                    self._queue.mark_done(msg.id)
                    return

            failed = True

        if failed:
            RNS.log("Message delivery failed.")
            self._queue.mark_failed(msg.id)

    def _run_loop(self) -> None:
        asyncio.run(self._async_loop())

    async def _async_loop(self) -> None:
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_socket.setblocking(False)
        server_socket.bind(self.socket_path)
        server_socket.listen(5)

        loop = asyncio.get_event_loop()

        async def handle_client(client_sock: socket.socket) -> None:
            try:
                data = await loop.sock_recv(client_sock, 65536)
                if not data:
                    client_sock.close()
                    return

                try:
                    request = json.loads(data.decode())
                except json.JSONDecodeError:
                    response = {"status": "error", "error": "invalid JSON"}
                    client_sock.sendall(json.dumps(response).encode())
                    client_sock.close()
                    return

                response = await self._handle_request(request)
                client_sock.sendall(json.dumps(response).encode())
                client_sock.close()
            except Exception as e:
                try:
                    response = {"status": "error", "error": str(e)}
                    client_sock.sendall(json.dumps(response).encode())
                except Exception:
                    pass
                try:
                    client_sock.close()
                except Exception:
                    pass

        clients: list[asyncio.Task] = []

        while not self._shutdown_event.is_set():
            try:
                client_sock, _ = await asyncio.wait_for(
                    loop.sock_accept(server_socket), timeout=1.0
                )
                task = asyncio.create_task(handle_client(client_sock))
                clients.append(task)
                clients = [t for t in clients if not t.done()]
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

        server_socket.close()
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

        for task in clients:
            await task

    async def _handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")

        if action == "send":
            return await self._handle_send(request)
        elif action == "ping":
            return {"status": "ok", "version": "1.0"}
        else:
            return {"status": "error", "error": f"unknown action: {action}"}

    async def _handle_send(self, request: dict[str, Any]) -> dict[str, Any]:
        destinations = request.get("destinations", [])
        content = request.get("content", "")
        title = request.get("title", "")
        prepend_title = request.get("prepend_title", True)
        attachments = request.get("attachments", [])
        propagation_node = request.get("propagation_node")
        pn_hash = None
        if propagation_node:
            try:
                pn_hash = _parse_hex_hash(propagation_node, "propagation node hash")
            except Exception as e:
                return {
                    "status": "error",
                    "error": f"invalid propagation node: {e}",
                }

        if not destinations:
            return {"status": "error", "error": "no destinations provided"}
        if not content:
            return {"status": "error", "error": "no content provided"}

        try:
            destination_hashes = [_parse_hex_hash(h, "hex hash") for h in destinations]
        except Exception as e:
            return {"status": "error", "error": f"invalid destination: {e}"}

        if prepend_title and title:
            content = title + "\n\n" + content

        fields = {LXMF.FIELD_RENDERER: LXMF.RENDERER_MARKDOWN}

        if attachments:
            file_list = []
            for path in attachments:
                path = os.path.expanduser(path)
                if not os.path.isfile(path):
                    return {
                        "status": "error",
                        "error": f"attachment not found: {path}",
                    }
                with open(path, "rb") as f:
                    file_list.append([os.path.basename(path), f.read()])
            fields[LXMF.FIELD_FILE_ATTACHMENTS] = file_list

        queue_id = self._queue.enqueue(
            destinations=destination_hashes,
            content=content,
            title=title,
            fields=fields,
            propagation_node=pn_hash,
        )

        RNS.log(f"Message enqueued (id={queue_id})")
        return {"status": "queued", "queue_id": queue_id}

    def stop(self) -> None:
        self._shutdown_event.set()
        if self._queue_processor_thread:
            self._queue_processor_thread.join(timeout=5)
        if self._loop_thread:
            self._loop_thread.join(timeout=5)
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except Exception:
                pass
        if self.pid_file and os.path.exists(self.pid_file):
            try:
                os.unlink(self.pid_file)
            except Exception:
                pass

    def wait(self) -> None:
        self._shutdown_event.wait()


def _env_or_default(env_key: str, default: str | None) -> str | None:
    return os.environ.get(f"LXMFS_{env_key}", default)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="LXMF message server")
    parser.add_argument(
        "--config",
        default=None,
        help="Configuration file path",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Data directory (overrides config)",
    )
    parser.add_argument(
        "--identity",
        default=None,
        help="Identity file path (overrides config)",
    )
    parser.add_argument(
        "--socket",
        default=None,
        help="Socket path (overrides config)",
    )
    parser.add_argument(
        "--pid-file",
        default=None,
        help="PID file path",
    )
    parser.add_argument(
        "--rnsconfig",
        default=None,
        help="Reticulum config directory",
    )
    parser.add_argument(
        "--propagation-node",
        default=None,
        help="Default propagation node",
    )
    parser.add_argument(
        "--display-name",
        default=None,
        help="Sender display name",
    )

    args = parser.parse_args()

    config_file = (
        args.config
        or _env_or_default("CONFIG", "/etc/lxmf-sender.conf")
        or "/etc/lxmf-sender.conf"
    )

    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        config.read(config_file)

    data_dir = (
        args.data_dir
        or os.environ.get("LXMFS_DATA_DIR")
        or config.get("lxmf-sender", "data-dir", fallback=None)
    )
    identity_path = (
        args.identity
        or os.environ.get("LXMFS_IDENTITY")
        or config.get("lxmf-sender", "identity", fallback=None)
    )
    socket_path = (
        args.socket
        or os.environ.get("LXMFS_SOCKET")
        or config.get("lxmf-sender", "daemon-socket", fallback=None)
    )
    rnsconfig = (
        args.rnsconfig
        or os.environ.get("LXMFS_RNSCONFIG")
        or config.get("lxmf-sender", "rnsconfig", fallback=None)
    )
    propagation_node = (
        args.propagation_node
        or os.environ.get("LXMFS_PROPAGATION_NODE")
        or config.get("lxmf-sender", "propagation-node", fallback=None)
    )
    display_name = (
        args.display_name
        or os.environ.get("LXMFS_DISPLAY_NAME")
        or config.get("lxmf-sender", "display-name", fallback=None)
    )

    daemon = LXMDaemon(
        data_dir=data_dir,
        identity_path=identity_path,
        socket_path=socket_path,
        rnsconfig=rnsconfig,
        propagation_node=propagation_node,
        display_name=display_name,
        pid_file=args.pid_file,
    )

    def shutdown_handler(sig, frame):
        daemon.stop()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGHUP, shutdown_handler)

    daemon.start()
    daemon.wait()
    daemon.stop()


if __name__ == "__main__":
    main()
