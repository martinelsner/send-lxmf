{
  pkgs ? import (fetchTarball "https://github.com/NixOS/nixpkgs/archive/nixos-25.11.tar.gz") { },
}:

pkgs.mkShell {
  LC_ALL = "C";

  packages = [
    pkgs.gnumake
    pkgs.python3
    pkgs.uv
    pkgs.zsh
  ];

  shellHook = ''
    make venv
    source .venv/bin/activate
    exec zsh
  '';

}
