"""
Send an LXMF message over the Reticulum network.

Message content is read from standard input.

Usage:
    echo "Hello there" | send-lxmf --destination b9af7034186731b9f009d06795172a36
    send-lxmf --destination b9af7034186731b9f009d06795172a36 --identity ~/.reticulum/my_id < message.txt
"""

import argparse
import os
import sys
import time

import LXMF
import RNS
from platformdirs import user_data_dir

APP_NAME = "send_lxmf"
TIMEOUT = 30  # seconds to wait for path / identity / delivery


def main():
    parser = argparse.ArgumentParser(description="Send an LXMF message (content read from stdin).")
    parser.add_argument("--destination", required=True, help="Recipient LXMF address as hex hash")
    parser.add_argument("--identity", default=None, help="Path to a Reticulum identity file to use as sender")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    try:
        destination_hash = bytes.fromhex(args.destination)
    except ValueError:
        print(f"Error: '{args.destination}' is not a valid hex hash.", file=sys.stderr)
        sys.exit(1)

    content = sys.stdin.read()
    if not content:
        print("Error: no message content provided on stdin.", file=sys.stderr)
        sys.exit(1)

    reticulum = RNS.Reticulum()

    # Load sender identity from explicit path or fall back to app data dir
    if args.identity:
        identity_path = os.path.expanduser(args.identity)
        if not os.path.isfile(identity_path):
            print(f"Error: identity file not found: {identity_path}", file=sys.stderr)
            sys.exit(1)
        sender_identity = RNS.Identity.from_file(identity_path)
    else:
        data_dir = user_data_dir(APP_NAME, ensure_exists=True)
        identity_path = os.path.join(data_dir, "identity")
        if os.path.isfile(identity_path):
            sender_identity = RNS.Identity.from_file(identity_path)
        else:
            sender_identity = RNS.Identity()
            sender_identity.to_file(identity_path)
            RNS.log("Created new sender identity, saved to " + identity_path)

    data_dir = user_data_dir(APP_NAME, ensure_exists=True)
    storage_path = os.path.join(data_dir, "storage")
    router = LXMF.LXMRouter(identity=sender_identity, storagepath=storage_path)
    source = router.register_delivery_identity(sender_identity, display_name="LXMF Sender")

    RNS.log(f"Sender  : {RNS.prettyhexrep(source.hash)}")
    RNS.log(f"Target  : {RNS.prettyhexrep(destination_hash)}")

    # Resolve path to destination
    if not RNS.Transport.has_path(destination_hash):
        RNS.log("Requesting path to destination...")
        RNS.Transport.request_path(destination_hash)

    deadline = time.time() + TIMEOUT
    while not RNS.Transport.has_path(destination_hash):
        if time.time() > deadline:
            print("Error: timed out waiting for path to destination.", file=sys.stderr)
            sys.exit(1)
        time.sleep(0.2)

    # Resolve recipient identity
    recipient_identity = RNS.Identity.recall(destination_hash)
    if recipient_identity is None:
        deadline = time.time() + TIMEOUT
        while recipient_identity is None:
            if time.time() > deadline:
                print("Error: timed out waiting for recipient identity.", file=sys.stderr)
                sys.exit(1)
            time.sleep(0.2)
            recipient_identity = RNS.Identity.recall(destination_hash)

    destination = RNS.Destination(
        recipient_identity,
        RNS.Destination.OUT,
        RNS.Destination.SINGLE,
        "lxmf",
        "delivery",
    )

    message = LXMF.LXMessage(
        destination,
        source,
        content,
        title="",
        desired_method=LXMF.LXMessage.DIRECT,
    )

    delivered = False
    failed = False

    def on_delivered(msg):
        nonlocal delivered
        delivered = True

    def on_failed(msg):
        nonlocal failed
        failed = True

    message.register_delivery_callback(on_delivered)
    message.register_failed_callback(on_failed)

    router.handle_outbound(message)
    RNS.log("Message queued, waiting for delivery...")

    deadline = time.time() + TIMEOUT
    while not delivered and not failed:
        if time.time() > deadline:
            print("Error: timed out waiting for delivery confirmation.", file=sys.stderr)
            sys.exit(1)
        time.sleep(0.2)

    if delivered:
        RNS.log("Message delivered successfully.")
    else:
        print("Error: message delivery failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
