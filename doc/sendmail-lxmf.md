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
`www-data@localhost`), sendmail-lxmf falls back to the default destination
configured in `/etc/lxmf-sender.conf`.

This makes it possible to use sendmail-lxmf as a system-wide sendmail
replacement where services send mail to local users like `root@localhost`.

### Configuration file

Create `/etc/lxmf-sender.conf` with an INI-style format:

```ini
[send-lxmf]
default-destination = b9af7034186731b9f009d06795172a36
propagation-node = a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
rnsconfig = /var/lib/reticulum/rnsd
data-dir = /var/lib/lxmf-sender
```

A template configuration file with all options and explanations is provided
in the package. Copy it to `/etc/lxmf-sender.conf` and uncomment the options you need:

```bash
cp $(python -c "import lxmf_sender; import os; print(os.path.dirname(lxmf_sender.__file__))")/send-lxmf.conf /etc/lxmf-sender.conf
nano /etc/lxmf-sender.conf  # uncomment and set your options
```

#### Options

All options are under the `[send-lxmf]` section. Option names match the
corresponding command-line arguments.

| Option | Description |
|--------|-------------|
| `default-destination` | Default LXMF destination address for non-address recipients (sendmail-lxmf only) |
| `propagation-node` | LXMF propagation node hash for store-and-forward delivery |
| `rnsconfig` | Reticulum config directory |
| `data-dir` | Directory for identity and LXMF router storage (default: per-user) |
| `display-name` | Sender display name |
| `prepend-title` | Prepend title to message body (default: true) |
| `timeout` | Timeout in seconds for delivery attempts |

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

The propagation node can also be configured in `/etc/lxmf-sender.conf`
as `propagation-node`. The `--propagation-node` flag takes precedence over
the config file.

## NixOS

For a complete NixOS setup that replaces the system `sendmail` with
sendmail-lxmf, see [nixos-sendmail.md](nixos-sendmail.md).