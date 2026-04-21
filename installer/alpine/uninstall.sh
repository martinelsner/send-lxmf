#!/bin/sh
#
# LXMF Sender Uninstaller for Alpine Linux
#
# Usage: sudo sh uninstall.sh
#

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---------- Preflight ----------

if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root (sudo)."
    exit 1
fi

echo "==> LXMF Sender Uninstaller (Alpine)"
echo ""

# ---------- Stop & Disable ----------

echo "--- Stopping and disabling service ---"
rc-service lxmf-sender stop 2>/dev/null || true
rc-update del lxmf-sender default 2>/dev/null || true
echo "    Service stopped and disabled."

# ---------- Remove OpenRC Init Script ----------

echo ""
echo "--- Removing OpenRC init script ---"
rm -f /etc/init.d/lxmf-sender
echo "    Removed /etc/init.d/lxmf-sender."

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