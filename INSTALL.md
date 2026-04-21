# Installation

## With systemd / OpenRC (Recommended)

Use the installer scripts:

```bash
# Debian / Ubuntu (systemd)
sudo bash installer/debian/install.sh

# Alpine Linux (OpenRC)
sudo sh installer/alpine/install.sh
```

**Prerequisite:** Install [reticulum-installer](https://codeberg.org/melsner/reticulum-installer) first. This provides:

- Virtual environment at `/opt/reticulum`
- `reticulum` system user
- Reticulum transport service (`rnsd`)
- LXMF propagation router (`lxmd`)

The installer adds `lxmf-sender` to the existing virtualenv and creates a systemd/OpenRC service.

### Uninstall

```bash
# Debian / Ubuntu
sudo bash installer/debian/uninstall.sh

# Alpine Linux
sudo sh installer/alpine/uninstall.sh
```

## pipx

Install as a user-level command:

```bash
pipx install https://codeberg.org/melsner/lxmf-sender/archive/main.tar.gz
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

## Debian 32-bit / Termux

On platforms where the Python `cryptography` package has no prebuilt wheels
(e.g. Debian on 32-bit ARM, or Termux on Android), install it from the system
package manager first and tell pipx to reuse system packages:

```bash
# Debian / Ubuntu 32-bit
sudo apt install python3-cryptography
pipx install --system-site-packages https://codeberg.org/melsner/lxmf-sender/archive/main.tar.gz

# Termux (pipx is not packaged, install it via pip first)
pkg install python python-cryptography python-pip
pip install pipx
pipx install --system-site-packages https://codeberg.org/melsner/lxmf-sender/archive/main.tar.gz
```

## Configuration

Edit `/etc/lxmf-sender.conf`:

```ini
[lxmf-sender]
# data-dir = /var/lib/reticulum/lxmf-sender
# identity = /var/lib/reticulum/lxmf-sender/identity
# daemon-socket = /run/lxmf-sender/lxmf-sender.sock
# rnsconfig = /var/lib/reticulum/rnsd
# propagation-node =
# display-name =
```

For details on all configuration options, see [doc/sendmail-lxmf.md](doc/sendmail-lxmf.md).

## NixOS

Add to your `configuration.nix`:

```nix
let
  lxmf-sender = import (builtins.fetchTarball "https://codeberg.org/melsner/lxmf-sender/archive/main.tar.gz") {};
in
{
  environment.systemPackages = [ lxmf-sender ];
}
```

To pull the latest dependencies from nixpkgs-unstable, pass your own `pkgs`:

```nix
let
  unstable = import (fetchTarball "https://github.com/NixOS/nixpkgs/archive/nixos-unstable.tar.gz") {};
  lxmf-sender = import (builtins.fetchTarball "https://codeberg.org/melsner/lxmf-sender/archive/main.tar.gz") { pkgs = unstable; };
in
{
  environment.systemPackages = [ lxmf-sender ];
}
```

You can also build and test it without installing:

```bash
nix-build https://codeberg.org/melsner/lxmf-sender/archive/main.tar.gz
./result/bin/send-lxmf --help
```

For setting up `sendmail-lxmf` as the system sendmail on NixOS, see
[doc/nixos-sendmail.md](doc/nixos-sendmail.md).