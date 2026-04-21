#!/usr/bin/env bash
#
# LXMF Sender Uninstaller for Debian
#
# Usage: sudo bash uninstall.sh
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------- Preflight ----------

if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root (sudo)."
    exit 1
fi

echo "==> LXMF Sender Uninstaller"
echo ""

# ---------- Stop & Disable ----------

echo "--- Stopping and disabling service ---"
systemctl stop lxmf-sender.service 2>/dev/null || true
systemctl disable lxmf-sender.service 2>/dev/null || true
echo "    Service stopped and disabled."

# ---------- Remove Systemd Unit ----------

echo ""
echo "--- Removing systemd service file ---"
rm -f /etc/systemd/system/lxmf-sender.service
systemctl daemon-reload
echo "    Removed systemd service."

# ---------- Remove Symlinks & Package ----------

echo ""
echo "--- Removing symlinks ---"
for bin in send-lxmf sendmail-lxmf lxmf-sender; do
    rm -f "/usr/local/bin/${bin}"
done
echo "    Removed symlinks."

echo ""
echo "--- Removing lxmf-sender from virtualenv ---"
/opt/reticulum/bin/pip uninstall -y lxmf-sender 2>/dev/null || true
echo "    lxmf-sender uninstalled (venv kept for rnsd/lxmd)."

# ---------- Summary ----------

echo ""
echo "==========================================="
echo "  Uninstallation complete!"
echo "==========================================="
echo ""
echo "  Data and configuration files were NOT removed."
echo "  To remove them manually:"
echo "    rm -rf /var/lib/reticulum/lxmf-sender"
echo "    rm -f /etc/lxmf-sender.conf"
echo "    rm -rf /run/lxmf-sender"
echo ""