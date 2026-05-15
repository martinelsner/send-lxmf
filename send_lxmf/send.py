"""
Send an LXMF message over the Reticulum network.

Message content is read from standard input.

Usage:
    echo "Hello there" | send-lxmf b9af7034186731b9f009d06795172a36
    echo "Hello there" | send-lxmf hash1 hash2 hash3
    send-lxmf b9af7034186731b9f009d06795172a36 --identity ~/.reticulum/my_id < message.txt
"""

import argparse
import re
import sys

from send_lxmf import __version__
from send_lxmf.lib import LXMFError, send_message

_CONFIG_DIR = "/etc/send-lxmf"
_PROPAGATION_NODE_PATH = _CONFIG_DIR + "/propagation-node"


def _read_propagation_node(path: str = _PROPAGATION_NODE_PATH) -> str | None:
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.search(r"[0-9a-fA-F]{32}", line)
                if m:
                    return m.group(0).lower()
    except FileNotFoundError:
        pass
    return None


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
        "--identity",
        default=None,
        help="Path to a Reticulum identity file to use as sender",
    )
    parser.add_argument(
        "--display-name",
        default=None,
        help="Sender name to announce (visible to recipients)",
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
        "--rnsconfig",
        default=None,
        metavar="RNSCONFIG",
        help="Path to alternative Reticulum config directory",
    )
    parser.add_argument(
        "--propagation-node",
        default=None,
        metavar="HEX_HASH",
        help="Propagation node to fall back to if direct delivery fails",
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    content = sys.stdin.read()

    try:
        send_message(
            destinations=args.destination,
            content=content,
            identity_path=args.identity,
            display_name=args.display_name,
            title=args.title,
            prepend_title=args.prepend_title,
            attachments=args.attach,
            rnsconfig=args.rnsconfig,
            propagation_node=args.propagation_node or _read_propagation_node(),
        )
    except LXMFError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
