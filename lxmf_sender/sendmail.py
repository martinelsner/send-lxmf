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
import email.utils
import os
import re
import shutil
import sys
import tempfile
from typing import NamedTuple

from markdownify import markdownify as md

from lxmf_sender import __version__
from lxmf_sender.client import DaemonNotAvailableError, DaemonResponseError
from lxmf_sender.lib import DEFAULT_SOCKET_PATH


def _env_or_default(env_key: str, default: str) -> str:
    """Get value from environment variable LXMFS_<KEY>, with fallback to default."""
    return os.environ.get(f"LXMFS_{env_key}", default)


def _extract_lxmf_address(value: str | None) -> str | None:
    """Return the LXMF hex address from a header value or raw argument."""
    if not value:
        return None
    value = value.strip()

    m = re.search(r"<([0-9a-fA-F]{32})(?:@[^>]*)?>", value)
    if m:
        return m.group(1).lower()

    m = re.search(r"([0-9a-fA-F]{32})@\S+", value)
    if m:
        return m.group(1).lower()

    m = re.search(r"[0-9a-fA-F]{32}", value)
    if m:
        return m.group(0).lower()

    return None


class ParsedEmail(NamedTuple):
    """Result of parsing an RFC 2822 email."""

    to: str
    subject: str
    body: str
    attachments: list[str]
    tmp_dir: str | None


def _parse_email(raw: str) -> ParsedEmail:
    """Parse a raw email string."""
    msg = email.message_from_string(raw, policy=email.policy.default)

    raw_to = msg.get("To", "") or ""
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

    return ParsedEmail(raw_to, title, body, attachment_paths, tmp_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sendmail-lxmf",
        description="sendmail-compatible LXMF delivery agent. "
        "Reads an RFC 2822 message from stdin.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "recipients",
        nargs="*",
        help="Recipient LXMF address(es) as hex hash. "
        "Overrides the To: header when given.",
    )
    parser.add_argument(
        "-i", action="store_true", help="(ignored, accepted for sendmail compatibility)"
    )
    parser.add_argument(
        "-t",
        action="store_true",
        help="Read recipients from headers (default behaviour)",
    )
    parser.add_argument(
        "-f",
        "--from",
        dest="sender",
        default=None,
        help="(ignored, accepted for sendmail compatibility)",
    )
    parser.add_argument(
        "-F",
        dest="full_name",
        default=None,
        help="(ignored, accepted for sendmail compatibility)",
    )
    parser.add_argument(
        "-o",
        dest="sendmail_opt",
        action="append",
        help="(ignored, accepted for sendmail compatibility)",
    )
    parser.add_argument(
        "--prepend-title",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Prepend the title to the message body, separated by a blank line (default: true)",
    )
    parser.add_argument(
        "--socket",
        default=None,
        help=f"Daemon socket path (default: {DEFAULT_SOCKET_PATH})",
    )

    args = parser.parse_args()
    socket_path = args.socket or _env_or_default("SOCKET", DEFAULT_SOCKET_PATH)

    raw = sys.stdin.read()
    if not raw.strip():
        print("Error: no message provided on stdin.", file=sys.stderr)
        sys.exit(1)

    parsed = _parse_email(raw)

    destinations = []
    if args.recipients:
        for r in args.recipients:
            addr = _extract_lxmf_address(r)
            if addr:
                destinations.append(addr)
    elif parsed.to:
        addr = _extract_lxmf_address(parsed.to)
        if addr:
            destinations.append(addr)

    if not destinations:
        print(
            "Error: no recipient specified (provide on command line or in To: header).",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        try:
            from lxmf_sender.client import DaemonClient

            client = DaemonClient(socket_path=socket_path)
            client.send_message(
                destinations=destinations,
                content=parsed.body,
                title=parsed.subject,
                prepend_title=args.prepend_title,
                attachments=parsed.attachments or None,
            )
        finally:
            if parsed.tmp_dir:
                shutil.rmtree(parsed.tmp_dir, ignore_errors=True)
    except DaemonNotAvailableError:
        print("Error: daemon not available", file=sys.stderr)
        sys.exit(1)
    except DaemonResponseError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
