{
  pkgs ? import (fetchTarball "https://github.com/NixOS/nixpkgs/archive/nixos-25.11.tar.gz") { },
}:

let
  workbenchDir = "/tmp/lxmf-sender-workbench";
in

pkgs.mkShell {
  LC_ALL = "C";

  packages = [
    pkgs.gnumake
    pkgs.python3
    pkgs.uv
    pkgs.zsh
  ];

  LXMFS_DATA_DIR = "${workbenchDir}/data";
  LXMFS_SOCKET = "${workbenchDir}/socket/lxmf-sender.sock";
  # LXMFS_RNSCONFIG = "${workbenchDir}/rnsd";

  shellHook = ''
    mkdir -p ${workbenchDir}/data ${workbenchDir}/socket ${workbenchDir}/rnsd
    chmod 755 ${workbenchDir}/socket
    make venv
    source .venv/bin/activate
    exec zsh
  '';

}