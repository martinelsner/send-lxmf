#!/usr/bin/env bash
#
# send-lxmf Installer for Debian
#
# Installs into /opt/send-lxmf virtualenv.
# Uses --system-site-packages to access apt-installed Python packages.
#
# Usage:
#   # Download and extract:
#   curl -L https://codeberg.org/melsner/send-lxmf/archive/main.tar.gz | tar -xz -C /tmp
#   cd /tmp/send-lxmf-main
#
#   # Run installer:
#   sudo bash install.sh
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VENV_DIR="/opt/send-lxmf"

# ---------- Preflight ----------

if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root (sudo)."
    exit 1
fi

echo "==> send-lxmf Installer"
echo ""

# ---------- System Packages ----------

echo "--- Installing system dependencies ---"
apt-get update
apt-get install -y python3 python3-pip python3-venv
apt-get install -y python3-cryptography python3-serial python3-bleak
echo "    System packages installed."

# ---------- Virtual Environment ----------

echo ""
echo "--- Setting up virtual environment ---"
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
    echo "    Created virtual environment at ${VENV_DIR}"
else
    echo "    Using existing virtual environment at ${VENV_DIR}"
fi

echo "--- Installing send-lxmf ---"
"$VENV_DIR/bin/pip" install --upgrade "${SCRIPT_DIR}"
echo "    Package installed."

# Symlink commands to system PATH
for cmd in send-lxmf sendmail-lxmf; do
    ln -sf "$VENV_DIR/bin/${cmd}" "/usr/local/bin/${cmd}"
    echo "    Symlinked ${cmd} -> /usr/local/bin/${cmd}"
done

# ---------- Data Directory ----------

echo ""
echo "--- Creating data directory ---"
mkdir -p /var/lib/send-lxmf
chmod ugo+rwX /var/lib/send-lxmf
echo "    Created /var/lib/send-lxmf with world-writable permissions."

# ---------- Summary ----------

echo ""
echo "==========================================="
echo "  Installation complete!"
echo "==========================================="
echo ""
echo "  Commands:"
echo "    send-lxmf     -> /usr/local/bin/send-lxmf"
echo "    sendmail-lxmf -> /usr/local/bin/sendmail-lxmf"
echo ""
echo "  Data directory:"
echo "    /var/lib/send-lxmf (world-writable)"
echo ""
echo "  To get started:"
echo "    send-lxmf --help"
echo ""