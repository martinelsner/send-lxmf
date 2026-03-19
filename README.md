# send-lxmf

Send LXMF messages over the Reticulum network from the command line.

## Installation

```bash
pipx install https://codeberg.org/melsner/send-lxmf/archive/main.tar.gz
```

See [INSTALL.md](INSTALL.md) for other methods (Debian 32-bit, Termux, NixOS) and troubleshooting.

## Usage

### send-lxmf

```bash
echo "Hello there" | send-lxmf --destination <recipient_hex_hash>
```

You can optionally specify a sender identity file:

```bash
send-lxmf --destination <recipient_hex_hash> --identity ~/.reticulum/my_id < message.txt
```

Set a display name so recipients see who sent the message:

```bash
echo "Hi" | send-lxmf --destination <recipient_hex_hash> --display-name "Alice"
```

Add a title to the message (shown by clients that support it, like NomadNet).
The title is prepended to the message body by default, so clients that don't
display the title field (like MeshChat) still show it. Use `--no-prepend-title`
to disable this:

```bash
echo "Meeting at noon" | send-lxmf --destination <recipient_hex_hash> --title "Reminder"
echo "Meeting at noon" | send-lxmf --destination <recipient_hex_hash> --title "Reminder" --no-prepend-title
```

Attach one or more files:

```bash
echo "See attached" | send-lxmf --destination <recipient_hex_hash> --attach report.pdf --attach photo.jpg
```

If no identity is provided, one will be created and stored automatically.

### sendmail-lxmf

A sendmail-compatible interface for LXMF. It reads an RFC 2822 email message
from stdin and delivers it over LXMF. This makes it usable as a drop-in
transport for tools that speak sendmail (e.g. `git send-email`, `msmtp`,
cron `MAILTO`, etc.).

The recipient LXMF address is taken from the `To:` header or from the
command-line arguments (which take precedence). The `Subject:` header becomes
the LXMF message title. MIME attachments are forwarded as LXMF file
attachments. HTML-only emails are automatically converted to Markdown.

Recipient addresses can be specified in several forms:

- bare hex: `b9af7034186731b9f009d06795172a36`
- angle brackets: `<b9af7034186731b9f009d06795172a36>`
- email-style: `b9af7034186731b9f009d06795172a36@lxmf`
- with display name: `Alice <b9af7034186731b9f009d06795172a36@lxmf>`

Basic usage:

```bash
sendmail-lxmf b9af7034186731b9f009d06795172a36 < message.eml
```

Pipe a message directly:

```bash
printf "To: b9af7034186731b9f009d06795172a36@lxmf\nSubject: Hello\n\nHi there\n" | sendmail-lxmf
```

Use with a specific sender identity:

```bash
sendmail-lxmf --identity ~/.reticulum/my_id < message.eml
```

Set a display name (overrides From: header):

```bash
sendmail-lxmf --display-name "Alice" < message.eml
```

Common sendmail flags (`-i`, `-t`, `-f`, `-F`, `-o`) are accepted and
silently ignored for compatibility, so existing sendmail invocations
generally work without modification.

## Development Setup

If you use Nix, drop into a shell with all dependencies:

```bash
nix-shell
```

Then use the Makefile to set up and work with the project:

```bash
make install   # create venv and install in editable mode
make test      # run the test suite
make clean     # remove venv and build artifacts
make help      # list all available targets
```

## References

- [Reticulum](https://reticulum.network/) — the cryptography-based networking stack
- [LXMF](https://github.com/markqvist/LXMF) — Lightweight Extensible Message Format for Reticulum
