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
echo "Hello there" | send-lxmf <recipient_hex_hash>
```

See [doc/send-lxmf.md](doc/send-lxmf.md) for all options.

### sendmail-lxmf

A sendmail-compatible interface that reads an RFC 2822 email from stdin
and delivers it over LXMF:

```bash
sendmail-lxmf b9af7034186731b9f009d06795172a36 < message.eml
```

See [doc/sendmail-lxmf.md](doc/sendmail-lxmf.md) for recipient resolution,
address formats, and all options.

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
