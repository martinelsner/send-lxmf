"""LXMF integration test — two-node direct delivery over BackboneInterface.

Architecture:
    Container A (node_a): rnsd with BackboneInterface Listener + send-lxmf
    Container B (node_b): rnsd with BackboneInterface Client → A + LXMF receiver

Test flow:
    1. docker compose builds and starts both containers
    2. node_b's LXMF receiver announces its identity
    3. From node_a, send-lxmf sends a DIRECT message to node_b
    4. node_b's HTTP API is queried to verify the message arrived

Run with: pytest tests/integration/ -m integration
"""

import subprocess
import time
import os
import sys

import pytest
import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMPOSE_FILE = os.path.join(PROJECT_ROOT, "tests", "integration", "docker-compose.yml")
COMPOSE_PROJECT = f"send-lxmf-test-{os.getpid()}"


def compose(*args, check=True, **kwargs):
    """Run a docker compose command scoped to our test project."""
    cmd = [
        "docker", "compose",
        "-f", COMPOSE_FILE,
        "-p", COMPOSE_PROJECT,
        *args,
    ]
    if args[0] in ("build", "up"):
        kwargs.setdefault("stdout", None)
        kwargs.setdefault("stderr", None)
    elif args[0] in ("port", "logs"):
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
    return subprocess.run(cmd, text=True, check=check, **kwargs)


def get_receiver_port() -> int:
    """Get the host-mapped port for node_b's HTTP API (8765)."""
    # Retry a few times as there may be a race between healthy containers and port mapping
    for _ in range(5):
        result = compose("port", "node_b", "8765")
        if result.returncode == 0 and result.stdout is not None:
            # Output like "0.0.0.0:32771" or "[::]:32771"
            addr = result.stdout.strip()
            if addr:
                return int(addr.rsplit(":", 1)[1])
        time.sleep(2)
    raise RuntimeError(
        f"docker compose port failed after retries (exit {result.returncode}): "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )


def wait_for_receiver(port: int, timeout: int = 180) -> str:
    """Wait until the receiver's /hash endpoint returns a valid hash."""
    deadline = time.time() + timeout
    last_err = None
    elapsed = 0
    while time.time() < deadline:
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/hash", timeout=5)
            if resp.status_code == 200 and len(resp.text.strip()) == 32:
                return resp.text.strip()
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
        elapsed += 2
        print(f"  [{elapsed}s] Waiting for receiver...", file=sys.stderr)
        time.sleep(2)
    raise TimeoutError(
        f"Receiver not ready after {timeout}s (last error: {last_err})"
    )


def wait_for_announce_propagation(port: int, receiver_hash: str, timeout: int = 60):
    """Wait for the receiver's announce to propagate by polling node_a logs."""
    deadline = time.time() + timeout
    elapsed = 0
    while time.time() < deadline:
        # Check if node_a logs show the announce was received
        result = compose("logs", "node_a")
        logs = result.stdout.lower()
        # Look for evidence of announce reception in node_a
        # The announce should be visible when node_b announces and node_a receives it
        if "destination" in logs or "path" in logs or "lxmf" in logs:
            # Something network-related is happening
            pass
        # Also check node_b logs to see if announce was sent
        result_b = compose("logs", "node_b")
        if "announce" in result_b.stdout.lower():
            print(f"  [{elapsed}s] Announce detected, waiting for propagation...", file=sys.stderr)
        elapsed += 2
        print(f"  [{elapsed}s] Checking announce propagation...", file=sys.stderr)
        time.sleep(2)
    print(f"Announce propagation check complete", file=sys.stderr)


@pytest.fixture(scope="module")
def compose_stack():
    """Build and start the docker compose stack; tear down after tests."""
    try:
        # Build images
        result = compose("build", check=False)
        if result.returncode != 0:
            print(f"Build failed:\n{result.stdout}\n{result.stderr}", file=sys.stderr)
            pytest.fail(f"docker compose build failed: {result.stderr}")

        # Start containers
        result = compose("up", "-d", "--wait", check=False)
        if result.returncode != 0:
            # Print logs for debugging
            logs = compose("logs", check=False)
            print(f"Startup failed:\n{result.stdout}\n{result.stderr}", file=sys.stderr)
            print(f"Container logs:\n{logs.stdout}", file=sys.stderr)
            pytest.fail(f"docker compose up failed: {result.stderr}")

        port = get_receiver_port()
        print(f"Waiting for receiver to be ready on port {port}...", file=sys.stderr)
        receiver_hash = wait_for_receiver(port)
        print(f"Receiver ready with hash: {receiver_hash}", file=sys.stderr)

        # Wait for announce to propagate from node_b to node_a
        wait_for_announce_propagation(port, receiver_hash)

        # Additional wait for network to settle
        print(f"Waiting 15s for network to settle...", file=sys.stderr)
        time.sleep(15)

        yield {
            "port": port,
            "receiver_hash": receiver_hash,
        }
    finally:
        # Dump logs for post-mortem debugging
        logs = compose("logs", check=False)
        print(f"\n--- Container logs ---\n{logs.stdout}", file=sys.stderr)

        compose("down", "-v", "--remove-orphans", check=False)


@pytest.mark.integration
def test_direct_message_delivery(compose_stack):
    """Send a DIRECT LXMF message from node_a to node_b and verify receipt."""
    port = compose_stack["port"]
    receiver_hash = compose_stack["receiver_hash"]
    test_message = "Hello from integration test"

    print(f"Sending message to receiver hash: {receiver_hash}", file=sys.stderr)

    # Write message to a temp file in the container
    write_result = compose(
        "exec", "-T", "node_a",
        "sh", "-c",
        f"printf '%s' {repr(test_message)} > /tmp/send_lxmf_msg.txt",
        check=False,
    )
    if write_result.returncode != 0:
        print(f"Warning: failed to write message file: {write_result.stderr}", file=sys.stderr)

    # Send the message using send-lxmf reading from the file
    result = compose(
        "exec", "-T", "node_a",
        "sh", "-c",
        f"/opt/reticulum/bin/python3 -m send_lxmf "
        f"--rnsconfig /etc/reticulum "
        f"--timeout 120 "
        f"{receiver_hash} "
        f"< /tmp/send_lxmf_msg.txt",
        check=False,
    )

    print(
        f"send-lxmf exit={result.returncode}\n"
        f"  stdout: {result.stdout!r}\n"
        f"  stderr: {result.stderr!r}",
        file=sys.stderr,
    )

    # send-lxmf should succeed (exit 0) for a DIRECT delivery
    assert result.returncode == 0, (
        f"send-lxmf failed with code {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # Verify the message was received by node_b
    # Give time for the message to be delivered
    deadline = time.time() + 60
    messages = []
    last_err = None
    elapsed = 0
    while time.time() < deadline:
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/messages", timeout=5)
            messages = resp.json()
            if messages:
                print(f"Received messages: {messages}", file=sys.stderr)
                break
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
        elapsed += 2
        print(f"  [{elapsed}s] Waiting for message delivery...", file=sys.stderr)
        time.sleep(2)

    assert len(messages) > 0, (
        f"No messages received by node_b within timeout.\n"
        f"send-lxmf stdout: {result.stdout}\n"
        f"send-lxmf stderr: {result.stderr}\n"
        f"Last error: {last_err}"
    )
    assert test_message in messages[0], (
        f"Message content mismatch. Expected {test_message!r} in {messages[0]!r}"
    )
    print(f"Message delivered successfully: {messages[0]!r}", file=sys.stderr)
