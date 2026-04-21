"""
Send an LXMF message over the Reticulum network.

Message content is read from standard input.

Usage:
    echo "Hello there" | send-lxmf b9af7034186731b9f009d06795172a36
    echo "Hello there" | send-lxmf hash1 hash2 hash3
"""

import argparse
import os
import sys

from lxmf_sender import __version__
from lxmf_sender.client import DaemonNotAvailableError, DaemonResponseError
from lxmf_sender.lib import DEFAULT_SOCKET_PATH


def _env_or_default(env_key: str, default: str) -> str:
    """Get value from environment variable LXMFS_<KEY>, with fallback to default."""
    return os.environ.get(f"LXMFS_{env_key}", default)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send an LXMF message (content read from stdin)."
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "destination", nargs="+", help="Recipient LXMF address(es) as hex hash"
    )
    parser.add_argument(
        "--title", default="", help="Message title (not shown by all clients)"
    )
    parser.add_argument(
        "--prepend-title",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Prepend the title to the message body, separated by a blank line (default: true)",
    )
    parser.add_argument(
        "--attach",
        action="append",
        default=[],
        metavar="FILE",
        help="Attach a file (can be used multiple times)",
    )
    parser.add_argument(
        "--socket",
        default=None,
        help=f"Daemon socket path (default: {DEFAULT_SOCKET_PATH})",
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    socket_path = args.socket or _env_or_default("SOCKET", DEFAULT_SOCKET_PATH)
    content = sys.stdin.read()

    try:
        from lxmf_sender.client import DaemonClient

        client = DaemonClient(socket_path=socket_path)
        client.send_message(
            destinations=args.destination,
            content=content,
            title=args.title,
            prepend_title=args.prepend_title,
            attachments=args.attach,
        )
    except DaemonNotAvailableError:
        print("Error: daemon not available", file=sys.stderr)
        sys.exit(1)
    except DaemonResponseError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
