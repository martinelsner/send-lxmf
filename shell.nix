{
  pkgs ? import (fetchTarball "https://github.com/NixOS/nixpkgs/archive/nixos-25.11.tar.gz") {}
}:

pkgs.mkShell {
  LC_ALL = "C";

  packages = [
    pkgs.gnumake
    pkgs.python3
    pkgs.uv
  ];
}
