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

from send_lxmf import __version__
from send_lxmf.lib import LXMFError, load_config, send_message


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


def _resolve_recipient(recipient: str) -> list[str]:
    """Resolve a recipient string to one or more LXMF destination hashes.

    If the recipient is already a valid LXMF address, it is returned directly.
    Otherwise returns an empty list.
    """
    addr = _extract_lxmf_address(recipient)
    if addr:
        return [addr]
    return []


class ParsedEmail(NamedTuple):
    """Result of parsing an RFC 2822 email."""

    to: str
    from_name: str | None
    subject: str
    body: str
    attachments: list[str]
    tmp_dir: str | None


def _parse_email(raw: str) -> ParsedEmail:
    """Parse a raw email string.

    *destination* is the LXMF hex address extracted from the To: header, or
    *None* if the header doesn't contain a valid LXMF address.  *raw_to* is
    the raw To: header value for further resolution by the caller.
    *display_name* is the sender name extracted from the From: header.

    *attachment_paths* is a list of paths to temporary files that the caller
    should clean up after sending.
    """
    msg = email.message_from_string(raw, policy=email.policy.default)

    raw_to = msg.get("To", "") or ""
    title = msg.get("Subject", "") or ""

    raw_from = msg.get("From", "") or ""
    display_name = None
    if raw_from:
        realname, _ = email.utils.parseaddr(raw_from)
        if realname:
            display_name = realname

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
        payload = part.get_content()
        if isinstance(payload, str):
            if content_type == "text/html":
                html_body = payload
            else:
                body = payload

    if not body and html_body:
        body = md(html_body, strip=["img"]).strip()

    return ParsedEmail(raw_to, display_name, title, body, attachment_paths, tmp_dir)


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
        "--identity",
        default=None,
        help="Path to a Reticulum identity file to use as sender",
    )
    parser.add_argument(
        "--display-name",
        default=None,
        help="Sender display name (overrides From: header)",
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
        help="Sender full name (alias for --display-name)",
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

    args = parser.parse_args()

    raw = sys.stdin.read()
    if not raw.strip():
        print("Error: no message provided on stdin.", file=sys.stderr)
        sys.exit(1)

    parsed = _parse_email(raw)

    destinations = []
    if args.recipients:
        for r in args.recipients:
            addrs = _resolve_recipient(r)
            if not addrs:
                print(
                    f"Error: could not resolve '{r}' to an LXMF address.",
                    file=sys.stderr,
                )
                sys.exit(1)
            destinations.extend(addrs)
    elif parsed.to:
        addrs = _resolve_recipient(parsed.to)
        if addrs:
            destinations.extend(addrs)

    if not destinations:
        print(
            "Error: no recipient specified (provide on command line or in To: header).",
            file=sys.stderr,
        )
        sys.exit(1)

    display_name = args.display_name or args.full_name or parsed.from_name
    config = load_config()
    propagation_node = args.propagation_node or config.get("propagation_node")

    try:
        try:
            send_message(
                destinations=destinations,
                content=parsed.body,
                identity_path=args.identity,
                display_name=display_name,
                title=parsed.subject,
                prepend_title=args.prepend_title,
                attachments=parsed.attachments or None,
                rnsconfig=args.rnsconfig,
                propagation_node=propagation_node,
            )
        finally:
            if parsed.tmp_dir:
                shutil.rmtree(parsed.tmp_dir, ignore_errors=True)
    except LXMFError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()