# Setting up sendmail-lxmf on NixOS

This guide shows how to replace the system `sendmail` with `sendmail-lxmf`
on NixOS, so that all local mail (from cron, smartd, etc.) is delivered
over LXMF.

## Overview

The setup involves three pieces:

1. Installing `send-lxmf` and creating a wrapper that exposes
   `sendmail-lxmf` as `/bin/sendmail`.
2. Creating `/var/lib/send-lxmf` at boot with world-readable permissions
   (so all users can store identity/state there).

## configuration.nix

```nix
let
  unstable = import (fetchTarball
    "https://github.com/NixOS/nixpkgs/archive/nixos-unstable.tar.gz"
  ) { allowUnfree = true; };

  send-lxmf = import (builtins.fetchTarball
    "https://codeberg.org/melsner/send-lxmf/archive/main.tar.gz"
  ) { pkgs = unstable; };

  sendmail-lxmf-wrapper = pkgs.runCommand "sendmail-lxmf-wrapper" { } ''
    mkdir -p $out/bin
    ln -s ${send-lxmf}/bin/sendmail-lxmf $out/bin/sendmail
  '';
in
{
  environment.systemPackages = [
    send-lxmf
    sendmail-lxmf-wrapper
  ];

  systemd.tmpfiles.rules = [
    "d /var/lib/send-lxmf 0775 root users"
  ];
}
```

## Notes

- The `unstable` pinning is optional but recommended — it ensures you get
  the latest Reticulum and LXMF packages from nixpkgs.
- `sendmail-lxmf` reads from stdin and exits, so it works fine as a
  oneshot invocation from any service. No daemon needed for the sendmail
  side (though you'll want `rnsd` running for Reticulum transport).