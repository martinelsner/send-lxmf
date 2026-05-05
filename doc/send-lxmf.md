# send-lxmf

Send an LXMF message over the Reticulum network. Message content is read
from standard input.

## Basic usage

```bash
echo "Hello there" | send-lxmf <recipient_hex_hash>
```

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

The propagation node can also be configured system-wide in
`/etc/send-lxmf/propagation-node` (a single hex hash, with optional comments).
The `--propagation-node` flag takes precedence over the config file.

```bash
sudo mkdir -p /etc/send-lxmf
echo "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4" | sudo tee /etc/send-lxmf/propagation-node
```
