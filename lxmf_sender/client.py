"""Client for connecting to the LXMF daemon via Unix socket."""

import json
import socket
import time
from typing import Any

from lxmf_sender.lib import DEFAULT_SOCKET_PATH

DEFAULT_TIMEOUT = 30


class DaemonNotAvailableError(Exception):
    """Raised when the daemon is not available."""

    pass


class DaemonResponseError(Exception):
    """Raised when the daemon returns an error response."""

    def __init__(self, error: str):
        self.error = error
        super().__init__(f"daemon error: {error}")


class DaemonClient:
    """Client for connecting to the LXMF daemon."""

    def __init__(
        self,
        socket_path: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        retries: int = 3,
        retry_delay: float = 0.5,
    ):
        self.socket_path = socket_path or DEFAULT_SOCKET_PATH
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay

    def _connect(self) -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        return sock

    def _send_request(self, request: dict[str, Any]) -> dict[str, Any]:
        sock = self._connect()
        try:
            data = json.dumps(request).encode()
            sock.sendall(data)

            response_data = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                response_data += chunk
                break

            if not response_data:
                raise DaemonNotAvailableError("empty response from daemon")

            return json.loads(response_data.decode())
        finally:
            sock.close()

    def send_message(
        self,
        destinations: list[str],
        content: str,
        title: str = "",
        prepend_title: bool = True,
        attachments: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send a message via the daemon.

        Returns the daemon response dict.
        Raises DaemonNotAvailableError if the daemon cannot be reached.
        Raises DaemonResponseError if the daemon returns an error.
        """
        request = {
            "action": "send",
            "destinations": destinations,
            "content": content,
            "title": title,
            "prepend_title": prepend_title,
        }

        if attachments:
            request["attachments"] = attachments

        last_error = None
        for attempt in range(self.retries):
            try:
                response = self._send_request(request)

                if response.get("status") == "error":
                    raise DaemonResponseError(response.get("error", "unknown error"))

                return response
            except (socket.error, OSError) as e:
                last_error = e
                if attempt < self.retries - 1:
                    time.sleep(self.retry_delay)
                continue

        raise DaemonNotAvailableError(f"could not connect to daemon: {last_error}")

    def ping(self) -> bool:
        """Check if the daemon is responsive."""
        try:
            response = self._send_request({"action": "ping"})
            return response.get("status") == "ok"
        except Exception:
            return False
