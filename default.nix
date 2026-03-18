{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python3;
in
python.pkgs.buildPythonApplication {
  pname = "send-lxmf";
  version = "0.4.0";
  src = pkgs.lib.cleanSource ./.;
  format = "pyproject";

  build-system = [ python.pkgs.setuptools ];

  dependencies = [
    python.pkgs.lxmf
    python.pkgs.platformdirs
  ];

  meta = {
    description = "Send LXMF messages from the command line";
    license = pkgs.lib.licenses.mit;
  };
}
