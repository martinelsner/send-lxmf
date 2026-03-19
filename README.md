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

To pull the latest dependencies from nixpkgs-unstable, pass your own `pkgs`:

```nix
let
  unstable = import (fetchTarball "https://github.com/NixOS/nixpkgs/archive/nixos-unstable.tar.gz") {};
  send-lxmf = import (builtins.fetchTarball "https://codeberg.org/melsner/send-lxmf/archive/main.tar.gz") { pkgs = unstable; };
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

### send-lxmf

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

### sendmail-lxmf

A sendmail-compatible interface for LXMF. It reads an RFC 2822 email message
from stdin and delivers it over LXMF. This makes it usable as a drop-in
transport for tools that speak sendmail (e.g. `git send-email`, `msmtp`,
cron `MAILTO`, etc.).

The recipient LXMF address is taken from the `To:` header or from the
command-line arguments (which take precedence). The `Subject:` header becomes
the LXMF message title. MIME attachments are forwarded as LXMF file
attachments.

Recipient addresses can be specified in several forms:

- bare hex: `b9af7034186731b9f009d06795172a36`
- angle brackets: `<b9af7034186731b9f009d06795172a36>`
- email-style: `b9af7034186731b9f009d06795172a36@lxmf`
- with display name: `Alice <b9af7034186731b9f009d06795172a36@lxmf>`

Basic usage:

```bash
sendmail-lxmf b9af7034186731b9f009d06795172a36 < message.eml
```

Pipe a message directly:

```bash
printf "To: b9af7034186731b9f009d06795172a36@lxmf\nSubject: Hello\n\nHi there\n" | sendmail-lxmf
```

Use with a specific sender identity:

```bash
sendmail-lxmf --identity ~/.reticulum/my_id < message.eml
```

Set a display name (overrides From: header):

```bash
sendmail-lxmf --display-name "Alice" < message.eml
```

Common sendmail flags (`-i`, `-t`, `-f`, `-F`, `-o`) are accepted and
silently ignored for compatibility, so existing sendmail invocations
generally work without modification.

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
