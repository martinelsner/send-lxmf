# Installation

## pipx

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

## Debian 32-bit / Termux

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

## NixOS

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

For setting up `sendmail-lxmf` as the system sendmail on NixOS, see
[doc/nixos-sendmail.md](doc/nixos-sendmail.md).
