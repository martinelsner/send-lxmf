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

## Address formats

Recipient addresses can be specified in several forms:

- bare hex: `b9af7034186731b9f009d06795172a36`
- angle brackets: `<b9af7034186731b9f009d06795172a36>`
- email-style: `b9af7034186731b9f009d06795172a36@lxmf`
- with display name: `Alice <b9af7034186731b9f009d06795172a36@lxmf>`

## Recipient resolution

When a recipient is not a valid LXMF address (e.g. `root` or
`www-data@localhost`), sendmail-lxmf resolves it using local configuration
files, checked in this order:

1. `/etc/sendmail-lxmf/aliases` — per-user mapping of local names to LXMF destinations
2. `/etc/sendmail-lxmf/default-destination` — catch-all fallback destination

This makes it possible to use sendmail-lxmf as a system-wide sendmail
replacement where services send mail to local users like `root@localhost`.

### Default destination

Set up a default destination so all local mail goes to one LXMF address:

```bash
sudo mkdir -p /etc/sendmail-lxmf
echo "b9af7034186731b9f009d06795172a36" | sudo tee /etc/sendmail-lxmf/default-destination
```

### Aliases

Map specific local users to different LXMF destinations in
`/etc/sendmail-lxmf/aliases` (format: `name: hex_hash`, one per line). Multiple
destinations can be separated by commas:

```text
# /etc/sendmail-lxmf/aliases
root: b9af7034186731b9f009d06795172a36
admin: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4, b9af7034186731b9f009d06795172a36
```

Aliases take precedence over the default destination. Lines starting with
`#` and blank lines are ignored in both files.

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

The propagation node can also be configured system-wide in
`/etc/sendmail-lxmf/propagation-node` (same format as `default-destination` — a
single hex hash, with optional comments). The `--propagation-node` flag
takes precedence over the config file.

```bash
sudo mkdir -p /etc/sendmail-lxmf
echo "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4" | sudo tee /etc/sendmail-lxmf/propagation-node
```

The message is first attempted via direct (opportunistic) delivery. If
that fails, it is handed off to the propagation node.


## NixOS

For a complete NixOS setup that replaces the system `sendmail` with
sendmail-lxmf, see [nixos-sendmail.md](nixos-sendmail.md).
