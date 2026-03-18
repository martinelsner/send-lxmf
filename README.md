# send-lxmf

Send LXMF messages over the Reticulum network from the command line.

## Installation

Install with [pipx](https://pipx.pypa.io/):

```bash
pipx install https://codeberg.org/melsner/send-lxmf/archive/main.tar.gz
```

If you don't have pipx yet:

```bash
# Debian / Ubuntu
sudo apt install pipx

# Fedora
sudo dnf install pipx

# Arch
sudo pacman -S python-pipx

# macOS
brew install pipx

# Windows
pip install --user pipx
```

Then run `pipx ensurepath` to make sure `~/.local/bin` is on your PATH.

### Debian 32-bit / Termux

On platforms where the Python `cryptography` package has no prebuilt wheels
(e.g. Debian on 32-bit ARM, or Termux on Android), install it from the system
package manager first and tell pipx to reuse system packages:

```bash
# Debian / Ubuntu 32-bit
sudo apt install python3-cryptography
pipx install --system-site-packages https://codeberg.org/melsner/send-lxmf/archive/main.tar.gz

# Termux (pipx is not packaged, install it via pip first)
pkg install python python-cryptography python-pip
pip install pipx
pipx install --system-site-packages https://codeberg.org/melsner/send-lxmf/archive/main.tar.gz
```

### NixOS

Add to your `configuration.nix`:

```nix
let
  send-lxmf = import (builtins.fetchTarball "https://codeberg.org/melsner/send-lxmf/archive/main.tar.gz") {};
in
{
  environment.systemPackages = [ send-lxmf ];
}
```

You can also build and test it without installing:

```bash
nix-build https://codeberg.org/melsner/send-lxmf/archive/main.tar.gz
./result/bin/send-lxmf --help
```

## Usage

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

Add a title to the message (shown by clients that support it, like NomadNet):

```bash
echo "Meeting at noon" | send-lxmf --destination <recipient_hex_hash> --title "Reminder"
```

Use `--prepend-title` to also include the title at the top of the message body,
for clients that don't display the title field (like MeshChat):

```bash
echo "Meeting at noon" | send-lxmf --destination <recipient_hex_hash> --title "Reminder" --prepend-title
```

Attach one or more files:

```bash
echo "See attached" | send-lxmf --destination <recipient_hex_hash> --attach report.pdf --attach photo.jpg
```

If no identity is provided, one will be created and stored automatically.

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
