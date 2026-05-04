# lxmf-sender

Send LXMF messages over the Reticulum network from the command line.

## Installation

### With systemd (Debian, Ubuntu, Alpine)

Use the installer scripts to set up as a systemd/OpenRC service:

```bash
# Debian/Ubuntu
sudo bash installer/debian/install.sh

# Alpine Linux
sudo sh installer/alpine/install.sh
```

This requires [reticulum-installer](https://codeberg.org/melsner/reticulum-installer) to be installed first (provides the shared virtualenv at `/opt/reticulum` and the `reticulum` system user).

See [INSTALL.md](INSTALL.md) for manual installation methods.

## Usage

### send-lxmf

```bash
echo "Hello there" | send-lxmf <recipient_hex_hash>
```

See [doc/send-lxmf.md](doc/send-lxmf.md) for all options.

### sendmail-lxmf

A sendmail-compatible interface that reads an RFC 2822 email from stdin
and delivers it over LXMF:

```bash
sendmail-lxmf b9af7034186731b9f009d06795172a36 < message.eml
```

See [doc/sendmail-lxmf.md](doc/sendmail-lxmf.md) for all options.

### Background Sending

Messages are enqueued and sent in the background, releasing the caller immediately. The daemon manages delivery attempts, retries, and propagation — you don't need to wait for the message to reach the recipient.

## Configuration

Configuration file: `/etc/lxmf-sender.conf`

```ini
[lxmf-sender]
# data-dir = /var/lib/reticulum/lxmf-sender
# identity = /var/lib/reticulum/lxmf-sender/identity
# daemon-socket = /run/lxmf-sender/lxmf-sender.sock
# rnsconfig = /var/lib/reticulum/rnsd
# propagation-node =
# display-name =
```

## Environment Variables

All options can be set via environment variables with the prefix `LXMFS_`:

| Variable | Description |
|----------|-------------|
| `LXMFS_SOCKET` | Daemon socket path |
| `LXMFS_CONFIG` | Config file path (server only) |
| `LXMFS_DATA_DIR` | Data directory (server only) |
| `LXMFS_IDENTITY` | Identity file path (server only) |
| `LXMFS_RNSCONFIG` | Reticulum config directory (server only) |
| `LXMFS_PROPAGATION_NODE` | Default propagation node (server only) |
| `LXMFS_DISPLAY_NAME` | Sender display name (server only) |
| `LXMFS_PID_FILE` | PID file path (server only) |

Priority: command-line option > environment variable > config file

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
- [reticulum-installer](https://codeberg.org/melsner/reticulum-installer) — Installs rnsd and lxmd