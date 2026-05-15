# sendmail-lxmf

A sendmail-compatible interface for LXMF. It reads an RFC 2822 email message
from stdin and delivers it over LXMF. This makes it usable as a drop-in
transport for tools that speak sendmail (e.g. `git send-email`, `msmtp`,
cron `MAILTO`, etc.).

The `Subject:` header becomes the LXMF message title. MIME attachments are
forwarded as LXMF file attachments. HTML-only emails are automatically
converted to Markdown. The sender display name is extracted from the `From:`
header (overridable with `--display-name` or `-F`).

## Basic usage

```bash
sendmail-lxmf b9af7034186731b9f009d06795172a36 < message.eml
```

Pipe a message directly:

```bash
printf "To: b9af7034186731b9f009d06795172a36@lxmf\nSubject: Hello\n\nHi there\n" | sendmail-lxmf
```

## Configuration

All settings can be set in `/var/lib/send-lxmf/config`:

```bash
# Sender display name visible to recipients
display_name = Alice

# Propagation node for store-and-forward delivery
propagation_node = a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
```

Command-line arguments override the config file. See `send-lxmf.conf` in
the repo for a commented sample.

## Address formats

Recipient addresses can be specified in several forms:

- bare hex: `b9af7034186731b9f009d06795172a36`
- angle brackets: `<b9af7034186731b9f009d06795172a36>`
- email-style: `b9af7034186731b9f009d06795172a36@lxmf`
- with display name: `Alice <b9af7034186731b9f009d06795172a36@lxmf>`

## Recipient resolution

When a recipient is not a valid LXMF address, sendmail-lxmf cannot resolve
it to an LXMF destination. Provide a valid hex hash on the command line
or in the `To:` header.

## Options

### Identity

```bash
sendmail-lxmf --identity ~/.reticulum/my_id < message.eml
```

### Display name

Overrides the name extracted from the `From:` header:

```bash
sendmail-lxmf --display-name "Alice" < message.eml
```

### Sendmail compatibility

Common sendmail flags (`-i`, `-t`, `-f`, `-F`, `-o`) are accepted and
silently ignored for compatibility, so existing sendmail invocations
generally work without modification.

### Propagation node fallback

If direct delivery fails, fall back to sending via a propagation node
(store-and-forward). This is useful when the recipient may be offline:

```bash
sendmail-lxmf --propagation-node <node_hex_hash> < message.eml
```

The message is first attempted via direct (opportunistic) delivery. If
that fails, it is handed off to the propagation node.


## NixOS

For a complete NixOS setup that replaces the system `sendmail` with
sendmail-lxmf, see [nixos-sendmail.md](nixos-sendmail.md).