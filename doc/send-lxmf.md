# send-lxmf

Send an LXMF message over the Reticulum network. Message content is read
from standard input.

## Basic usage

```bash
echo "Hello there" | send-lxmf --destination <recipient_hex_hash>
```

## Options

### Identity

Specify a sender identity file. If omitted, one is created and stored
automatically.

```bash
send-lxmf --destination <recipient_hex_hash> --identity ~/.reticulum/my_id < message.txt
```

### Display name

Set a display name so recipients see who sent the message:

```bash
echo "Hi" | send-lxmf --destination <recipient_hex_hash> --display-name "Alice"
```

### Title

Add a title to the message (shown by clients that support it, like NomadNet).
The title is prepended to the message body by default, so clients that don't
display the title field (like MeshChat) still show it. Use `--no-prepend-title`
to disable this:

```bash
echo "Meeting at noon" | send-lxmf --destination <recipient_hex_hash> --title "Reminder"
echo "Meeting at noon" | send-lxmf --destination <recipient_hex_hash> --title "Reminder" --no-prepend-title
```

### Attachments

Attach one or more files:

```bash
echo "See attached" | send-lxmf --destination <recipient_hex_hash> --attach report.pdf --attach photo.jpg
```

### Reticulum config

Use an alternative Reticulum config directory:

```bash
echo "Hi" | send-lxmf --destination <recipient_hex_hash> --rnsconfig /path/to/config
```
