# send-lxmf

Send an LXMF message over the Reticulum network. Message content is read
from standard input.

## Basic usage

```bash
echo "Hello there" | send-lxmf <recipient_hex_hash>
```

## Configuration

All settings can be set in `/var/lib/send-lxmf/config`:

```bash
# Sender display name visible to recipients
display_name = Alice

# Default recipient (used when none given on command line)
destination = b9af7034186731b9f009d06795172a36

# Propagation node for store-and-forward delivery
propagation_node = a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
```

Command-line arguments override the config file. See `send-lxmf.conf` in
the repo for a commented sample.

## Options

### Identity

Specify a sender identity file. If omitted, one is created and stored
automatically.

```bash
send-lxmf <recipient_hex_hash> --identity ~/.reticulum/my_id < message.txt
```

### Display name

Set a display name so recipients see who sent the message:

```bash
echo "Hi" | send-lxmf <recipient_hex_hash> --display-name "Alice"
```

### Title

Add a title to the message (shown by clients that support it, like NomadNet).
The title is prepended to the message body by default, so clients that don't
display the title field (like MeshChat) still show it. Use `--no-prepend-title`
to disable this:

```bash
echo "Meeting at noon" | send-lxmf <recipient_hex_hash> --title "Reminder"
echo "Meeting at noon" | send-lxmf <recipient_hex_hash> --title "Reminder" --no-prepend-title
```

### Attachments

Attach one or more files:

```bash
echo "See attached" | send-lxmf <recipient_hex_hash> --attach report.pdf --attach photo.jpg
```

### Reticulum config

Use an alternative Reticulum config directory:

```bash
echo "Hi" | send-lxmf <recipient_hex_hash> --rnsconfig /path/to/config
```

### Propagation node fallback

If direct delivery fails, fall back to sending via a propagation node
(store-and-forward). This is useful when the recipient may be offline:

```bash
echo "Hi" | send-lxmf <recipient_hex_hash> --propagation-node <node_hex_hash>
```

The message is first attempted via direct (opportunistic) delivery. Only if
that fails is it handed off to the specified propagation node.