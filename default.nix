{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python3;
  versionFile = builtins.readFile ./send_lxmf/__init__.py;
  version = builtins.head (builtins.match ''.*__version__ = "([^"]+)".*'' versionFile);
in
python.pkgs.buildPythonApplication {
  pname = "send-lxmf";
  inherit version;
  src = pkgs.lib.cleanSource ./.;
  format = "pyproject";

  build-system = [ python.pkgs.setuptools ];

  dependencies = [
    python.pkgs.lxmf
    python.pkgs.markdownify
    python.pkgs.platformdirs
  ];

  meta = {
    description = "Send LXMF messages from the command line";
    license = pkgs.lib.licenses.mit;
  };
}
