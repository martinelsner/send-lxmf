# Setting up sendmail-lxmf on NixOS

This guide shows how to replace the system `sendmail` with `sendmail-lxmf`
on NixOS, so that all local mail (from cron, smartd, etc.) is delivered
over LXMF.

## Overview

The setup involves three pieces:

1. Installing `send-lxmf` and creating a wrapper that exposes
   `sendmail-lxmf` as `/bin/sendmail`.
2. Configuring `/etc/lxmf-sender.conf` so local recipients
   (like `root`) resolve to an LXMF address.
3. Optionally placing the wrapper in `/run/wrappers/bin/sendmail` for
   services that hardcode that path.

## configuration.nix

```nix
let
  unstable = import (fetchTarball
    "https://github.com/NixOS/nixpkgs/archive/nixos-unstable.tar.gz"
  ) {};

  send-lxmf = import (builtins.fetchTarball
    "https://codeberg.org/melsner/send-lxmf/archive/main.tar.gz"
  ) { pkgs = unstable; };

  # Wrapper that symlinks sendmail-lxmf as /bin/sendmail.
  sendmail-lxmf-wrapper = pkgs.runCommand "sendmail-lxmf-wrapper" { } ''
    mkdir -p $out/bin
    ln -s ${send-lxmf}/bin/sendmail-lxmf $out/bin/sendmail
  '';
in
{
  # Install both the send-lxmf package and the sendmail wrapper.
  environment.systemPackages = [
    send-lxmf
    sendmail-lxmf-wrapper
  ];

  # LXMF destination for all local mail.
  # Replace with your own LXMF destination hash.
  environment.etc."lxmf-sender.conf" = {
    text = ''
      [send-lxmf]
      default-destination = a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
    '';
    mode = "0644";
  };

  # (Optional) Place sendmail at /run/wrappers/bin/sendmail so services
  # that hardcode that path (e.g. smartd) can find it.
  security.wrappers.sendmail = {
    setuid = false;
    owner = "root";
    group = "root";
    source = "${sendmail-lxmf-wrapper}/bin/sendmail";
  };
}
```

## Propagation node fallback (optional)

If you have a local or known LXMF propagation node, you can configure it
so that messages are retried via store-and-forward when direct delivery
fails:

```nix
environment.etc."lxmf-sender.conf" = {
  text = ''
    [send-lxmf]
    default-destination = a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
    propagation-node = c4d5e6f7a8b9c4d5e6f7a8b9c4d5e6f7
  '';
  mode = "0644";
};
```

This is especially useful for system mail where the recipient may be
offline. The message is first attempted via direct (opportunistic)
delivery. If that fails, it is handed off to the propagation node.

## How it works

When a service like cron or smartd sends mail to `root@localhost`, it
invokes `/bin/sendmail` (or `/run/wrappers/bin/sendmail`), which is now
`sendmail-lxmf`. Since `root` is not a valid LXMF hex hash, sendmail-lxmf
falls back to the `default-destination` configured in `/etc/lxmf-sender.conf`,
and delivers the message over LXMF.

## Notes

- The `unstable` pinning is optional but recommended — it ensures you get
  the latest Reticulum and LXMF packages from nixpkgs.
- `sendmail-lxmf` reads from stdin and exits, so it works fine as a
  oneshot invocation from any service. No daemon needed for the sendmail
  side (though you'll want `rnsd` running for Reticulum transport).