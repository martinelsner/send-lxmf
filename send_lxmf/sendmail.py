"""
sendmail-lxmf — a sendmail-compatible interface for LXMF.

Reads an RFC 2822 email message from stdin and delivers it over LXMF.

The recipient LXMF address is taken from the ``To:`` header (or the
command-line recipients, which take precedence).  The ``Subject:`` header
becomes the LXMF title.  The plain-text body becomes the message content.
MIME attachments are forwarded as LXMF file attachments.

Usage:
    sendmail-lxmf b9af7034186731b9f009d06795172a36 < message.eml
    cat message.eml | sendmail-lxmf -i
"""

import argparse
import email
import email.policy
import os
import re
import shutil
import sys
import tempfile

from markdownify import markdownify as md

from send_lxmf.lib import send_message

# Matches a bare 32-byte hex hash (the LXMF address format).
_HEX_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def _extract_lxmf_address(value: str | None) -> str | None:
    """Return the LXMF hex address from a header value or raw argument.

    Accepts:
      - a bare hex hash: ``b9af7034186731b9f009d06795172a36``
      - an angle-bracket form: ``<b9af7034186731b9f009d06795172a36>``
      - an email-style form: ``Name <b9af7034186731b9f009d06795172a36>``
      - an email-style form: ``b9af7034186731b9f009d06795172a36@lxmf``

    Returns *None* when no valid address is found.
    """
    if not value:
        return None
    value = value.strip()

    # Try angle-bracket form first: "Name <hash>" or "<hash>"
    m = re.search(r"<([0-9a-fA-F]{32})(?:@[^>]*)?>", value)
    if m:
        return m.group(1).lower()

    # Try "hash@domain" form
    m = re.search(r"([0-9a-fA-F]{32})@\S+", value)
    if m:
        return m.group(1).lower()

    # Bare hex hash
    m = re.search(r"[0-9a-fA-F]{32}", value)
    if m:
        return m.group(0).lower()

    return None


def _parse_email(raw: str) -> tuple[str | None, str, str, list[str], str | None]:
    """Parse a raw email string and return (destination, title, body, attachment_paths).

    *attachment_paths* is a list of paths to temporary files that the caller
    should clean up after sending.
    """
    msg = email.message_from_string(raw, policy=email.policy.default)

    destination = _extract_lxmf_address(msg.get("To", ""))
    title = msg.get("Subject", "") or ""

    body = ""
    html_body = ""
    attachment_paths = []
    tmp_dir = None

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))

            if content_type == "text/plain" and "attachment" not in disposition:
                payload = part.get_content()
                if isinstance(payload, str):
                    body += payload
            elif content_type == "text/html" and "attachment" not in disposition:
                payload = part.get_content()
                if isinstance(payload, str):
                    html_body += payload
            elif part.get_filename():
                filename = part.get_filename()
                data = part.get_content()
                if isinstance(data, str):
                    data = data.encode()
                # Create a shared temp dir on first attachment
                if tmp_dir is None:
                    tmp_dir = tempfile.mkdtemp(prefix="sendmail_lxmf_")
                path = os.path.join(tmp_dir, filename)
                with open(path, "wb") as f:
                    f.write(data)
                attachment_paths.append(path)
    else:
        content_type = msg.get_content_type()
        payload = msg.get_content()
        if isinstance(payload, str):
            if content_type == "text/html":
                html_body = payload
            else:
                body = payload

    if not body and html_body:
        body = md(html_body, strip=["img"]).strip()

    return destination, title, body, attachment_paths, tmp_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sendmail-lxmf",
        description="sendmail-compatible LXMF delivery agent. "
                    "Reads an RFC 2822 message from stdin.",
    )
    parser.add_argument(
        "recipients", nargs="*",
        help="Recipient LXMF address(es) as hex hash. "
             "Overrides the To: header when given.",
    )
    parser.add_argument(
        "--identity", default=None,
        help="Path to a Reticulum identity file to use as sender",
    )
    parser.add_argument(
        "--display-name", default=None,
        help="Sender display name (overrides From: header)",
    )
    # Accept (and ignore) common sendmail flags for compatibility.
    parser.add_argument("-i", action="store_true", help="(ignored, accepted for sendmail compatibility)")
    parser.add_argument("-t", action="store_true", help="Read recipients from headers (default behaviour)")
    parser.add_argument("-f", "--from", dest="sender", default=None, help="(ignored, accepted for sendmail compatibility)")
    parser.add_argument("-F", dest="full_name", default=None, help="Sender full name (alias for --display-name)")
    parser.add_argument("-o", dest="sendmail_opt", action="append", help="(ignored, accepted for sendmail compatibility)")
    parser.add_argument("--prepend-title", action=argparse.BooleanOptionalAction, default=True, help="Prepend the title to the message body, separated by a blank line (default: true)")
    parser.add_argument("--rnsconfig", default=None, metavar="RNSCONFIG", help="Path to alternative Reticulum config directory")

    args = parser.parse_args()

    raw = sys.stdin.read()
    if not raw.strip():
        print("Error: no message provided on stdin.", file=sys.stderr)
        sys.exit(1)

    destination_from_header, title, body, attachment_paths, tmp_dir = _parse_email(raw)

    # Determine recipients: CLI args take precedence over To: header.
    destinations = []
    if args.recipients:
        for r in args.recipients:
            addr = _extract_lxmf_address(r)
            if addr is None:
                print(f"Error: '{r}' is not a valid LXMF address.", file=sys.stderr)
                sys.exit(1)
            destinations.append(addr)
    elif destination_from_header:
        destinations.append(destination_from_header)
    else:
        print("Error: no recipient specified (provide on command line or in To: header).", file=sys.stderr)
        sys.exit(1)

    display_name = args.display_name or args.full_name

    try:
        for dest in destinations:
            send_message(
                destination_hex=dest,
                content=body,
                identity_path=args.identity,
                display_name=display_name,
                title=title,
                prepend_title=args.prepend_title,
                attachments=attachment_paths or None,
                rnsconfig=args.rnsconfig,
            )
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
