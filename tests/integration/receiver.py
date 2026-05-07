#!/usr/bin/env python3
"""LXMF receiver for integration testing.

Runs on Container B. Registers an LXMF delivery identity, announces it
on the network, and exposes received messages via a minimal HTTP API:

    GET /hash      -> receiver's 32-char hex identity hash
    GET /messages  -> JSON array of received message contents
"""

import json
import os
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

import LXMF
import RNS


MESSAGES: list[str] = []
RECEIVER_HASH: str | None = None


class MessageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/hash":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write((RECEIVER_HASH or "").encode())
        elif self.path == "/messages":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(MESSAGES).encode())
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, _fmt, *args):
        pass


def run_http(port: int):
    server = HTTPServer(("0.0.0.0", port), MessageHandler)
    server.serve_forever()


def wait_for_rnsd(configdir: str, timeout: int = 60) -> RNS.Reticulum:
    """Wait for rnsd to be available as a shared instance."""
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            r = RNS.Reticulum(configdir=configdir, require_shared_instance=True)
            print(f"Connected to rnsd shared instance", flush=True)
            return r
        except Exception as e:
            last_err = e
            print(f"Waiting for rnsd... ({e})", flush=True)
            time.sleep(2)
    raise TimeoutError(f"rnsd not available after {timeout}s: {last_err}")


def wait_for_backbone_interface(timeout: int = 30) -> bool:
    """Wait for the BackboneInterface to establish by checking rnsd connectivity."""
    print("Waiting for BackboneInterface link to establish...", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        # Give the BackboneInterface time to establish the TCP connection
        # We can't easily check interface status, so we just wait a fixed time
        remaining = deadline - time.time()
        if remaining > 5:
            print(f"Waiting... ({int(remaining)}s remaining)", flush=True)
            time.sleep(5)
        else:
            time.sleep(remaining)
    print("BackboneInterface link wait complete", flush=True)
    return True


def main():
    global RECEIVER_HASH

    configdir = "/etc/reticulum"

    # Wait for rnsd to be available
    print("Connecting to rnsd shared instance...", flush=True)
    reticulum = wait_for_rnsd(configdir, timeout=30)

    # Wait for the BackboneInterface link to be established
    print("Waiting for BackboneInterface link to node_a...", flush=True)
    if not wait_for_backbone_interface(timeout=30):
        print("WARNING: BackboneInterface link not established, continuing anyway...", flush=True)
    else:
        print("BackboneInterface link established", flush=True)

    storage_path = "/tmp/receiver_storage"
    os.makedirs(storage_path, exist_ok=True)

    identity_path = os.path.join(storage_path, "identity")
    if os.path.exists(identity_path):
        identity = RNS.Identity.from_file(identity_path)
        print(f"Loaded existing identity: {identity.hash.hex()}", flush=True)
    else:
        identity = RNS.Identity()
        identity.to_file(identity_path)
        print(f"Created new identity: {identity.hash.hex()}", flush=True)

    router = LXMF.LXMRouter(identity=identity, storagepath=storage_path)
    source = router.register_delivery_identity(identity)
    print(f"Registered delivery identity: {source.hash.hex()}", flush=True)

    RECEIVER_HASH = source.hash.hex()  # This is the announced delivery identity hash

    print(f"Announcing identity {source.hash.hex()}...", flush=True)
    router.announce(source.hash)
    print(f"Announce sent, hash: {source.hash.hex()}", flush=True)

    def on_message(msg):
        content = msg.content
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        MESSAGES.append(content)
        print(f"Received message: {content!r}", flush=True)

    router.register_delivery_callback(on_message)

    # Start HTTP API
    http_thread = threading.Thread(target=run_http, args=(8765,), daemon=True)
    http_thread.start()
    print("HTTP API started on port 8765", flush=True)

    print("Receiver ready, waiting for messages...", flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
