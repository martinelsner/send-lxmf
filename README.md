# send-lxmf

Send LXMF messages over the Reticulum network from the command line.

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

## Usage

```bash
echo "Hello there" | send-lxmf --destination <recipient_hex_hash>
```

You can optionally specify a sender identity file:

```bash
send-lxmf --destination <recipient_hex_hash> --identity ~/.reticulum/my_id < message.txt
```

If no identity is provided, one will be created and stored automatically.

## References

- [Reticulum](https://reticulum.network/) — the cryptography-based networking stack
- [LXMF](https://github.com/markqvist/LXMF) — Lightweight Extensible Message Format for Reticulum
