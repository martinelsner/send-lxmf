#!/usr/bin/env bash
#
# send-lxmf Uninstaller for Debian
#
# Removes the installation created by install.sh.
#
# Usage:
#   curl -L https://codeberg.org/melsner/send-lxmf/archive/main.tar.gz | tar -xz -C /tmp
#   sudo bash /tmp/send-lxmf-main/uninstall.sh
#

set -euo pipefail

VENV_DIR="/opt/send-lxmf"
DATA_DIR="/var/lib/send-lxmf"

# ---------- Preflight ----------

if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root (sudo)."
    exit 1
fi

echo "==> send-lxmf Uninstaller"
echo ""

# ---------- Symlinks ----------

echo "--- Removing symlinks ---"
for cmd in send-lxmf sendmail-lxmf sendmail; do
    rm -f "/usr/local/bin/${cmd}"
    echo "    Removed /usr/local/bin/${cmd}"
done

# ---------- Virtual Environment ----------

echo ""
echo "--- Removing virtual environment ---"
if [[ -d "$VENV_DIR" ]]; then
    rm -rf "$VENV_DIR"
    echo "    Removed ${VENV_DIR}"
else
    echo "    ${VENV_DIR} not found, skipping."
fi

# ---------- Config and Data Directory ----------

CONFIG_FILE="/var/lib/send-lxmf/config"
if [[ -f "$CONFIG_FILE" ]]; then
    echo "    ${CONFIG_FILE} exists. To remove it manually:"
    echo "      sudo rm -f ${CONFIG_FILE}"
else
    echo "    ${CONFIG_FILE} not found."
fi

if [[ -d "$DATA_DIR" ]]; then
    echo "    ${DATA_DIR} exists. To remove it manually:"
    echo "      sudo rm -rf ${DATA_DIR}"
else
    echo "    ${DATA_DIR} not found."
fi

# ---------- Summary ----------

echo ""
echo "==========================================="
echo "  Uninstallation complete!"
echo "==========================================="
echo ""
echo "  Note: System packages (python3-cryptography, python3-serial,"
echo "        python3-bleak) were not removed. To remove them:"
echo ""
echo "    sudo apt remove python3-cryptography python3-serial python3-bleak"
echo ""