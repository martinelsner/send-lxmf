"""Shared LXMF sending logic."""

import os
import sys
import time

import LXMF
import RNS
from platformdirs import user_data_dir

APP_NAME = "send_lxmf"
TIMEOUT = 30  # seconds to wait for path / identity / delivery


def send_message(destination_hex: str, content: str, identity_path: str | None = None,
                 display_name: str | None = None, title: str = "",
                 prepend_title: bool = True, attachments: list[str] | None = None,
                 rnsconfig: str | None = None) -> None:
    """Send an LXMF message. Raises SystemExit on errors.

    Parameters
    ----------
    destination_hex : str
        Recipient LXMF address as a hex string.
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
    """
    try:
        destination_hash = bytes.fromhex(destination_hex)
    except ValueError:
        print(f"Error: '{destination_hex}' is not a valid hex hash.", file=sys.stderr)
        sys.exit(1)

    if not content:
        print("Error: no message content provided.", file=sys.stderr)
        sys.exit(1)

    reticulum = RNS.Reticulum(configdir=rnsconfig)

    # Load sender identity
    if identity_path:
        identity_path = os.path.expanduser(identity_path)
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
    source = router.register_delivery_identity(sender_identity, display_name=display_name)

    if display_name:
        router.announce(source.hash)

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

    if prepend_title and title:
        content = title + "\n\n" + content

    fields = {LXMF.FIELD_RENDERER: LXMF.RENDERER_MARKDOWN}

    if attachments:
        file_list = []
        for path in attachments:
            path = os.path.expanduser(path)
            if not os.path.isfile(path):
                print(f"Error: attachment not found: {path}", file=sys.stderr)
                sys.exit(1)
            with open(path, "rb") as f:
                file_list.append([os.path.basename(path), f.read()])
        fields[LXMF.FIELD_FILE_ATTACHMENTS] = file_list

    message = LXMF.LXMessage(
        destination,
        source,
        content,
        title=title,
        fields=fields,
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
