#!/usr/bin/env bash
#
# LXMF Sender Installer for Debian
#
# Installs lxmf-sender as a systemd service with a dedicated
# system user and default configuration.
#
# Usage: sudo bash install.sh
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DATA_DIR="/var/lib/reticulum/lxmf-sender"
SOCKET_DIR="/run/lxmf-sender"
VENV_DIR="/opt/reticulum"

# ---------- Preflight ----------

if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root (sudo)."
    exit 1
fi

echo "==> LXMF Sender Installer"
echo ""

# ---------- Dependencies ----------

echo "--- Installing system dependencies ---"
apt-get update
apt-get install -y python3 python3-pip python3-venv
echo "    System packages installed."

# ---------- Virtual Environment ----------

echo "--- Installing Python packages ---"
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
    echo "    Created virtualenv at $VENV_DIR"
else
    echo "    Using existing virtualenv at $VENV_DIR"
fi

"$VENV_DIR/bin/pip" install lxmf-sender
echo "    lxmf-sender installed in virtualenv."

# Symlink binaries to system PATH
for bin in send-lxmf sendmail-lxmf lxmf-sender; do
    ln -sf "$VENV_DIR/bin/${bin}" "/usr/local/bin/${bin}"
    echo "    Symlinked ${bin} -> /usr/local/bin/${bin}"
done

# ---------- User & Group ----------

echo ""
echo "--- Ensuring reticulum user exists ---"

if ! getent group reticulum > /dev/null 2>&1; then
    groupadd --system reticulum
    echo "    Created group: reticulum"
else
    echo "    Group 'reticulum' already exists."
fi

if ! id reticulum > /dev/null 2>&1; then
    useradd \
        --system \
        --gid reticulum \
        --home-dir "$DATA_DIR" \
        --create-home \
        --shell /usr/sbin/nologin \
        reticulum
    echo "    Created user: reticulum"
else
    echo "    User 'reticulum' already exists."
fi

# ---------- Directories ----------

echo ""
echo "--- Creating directories ---"

mkdir -p "$DATA_DIR"
mkdir -p "$SOCKET_DIR"
chown reticulum:reticulum "$DATA_DIR" "$SOCKET_DIR"
chmod 750 "$DATA_DIR"
chmod 755 "$SOCKET_DIR"

echo "    Created $DATA_DIR"
echo "    Created $SOCKET_DIR"

# ---------- Configuration ----------

echo ""
echo "--- Installing configuration file ---"

CONFIG_FILE="/etc/lxmf-sender.conf"

if [[ -f "$CONFIG_FILE" ]]; then
    echo "    SKIP $CONFIG_FILE (already exists)"
else
    cat > "$CONFIG_FILE" << EOF
[lxmf-sender]
# data-dir = /var/lib/reticulum/lxmf-sender
# identity = /var/lib/reticulum/lxmf-sender/identity
# daemon-socket = /run/lxmf-sender/lxmf-sender.sock
# rnsconfig = /var/lib/reticulum/rnsd
# propagation-node =
# display-name =
EOF
    chown root:root "$CONFIG_FILE"
    chmod 644 "$CONFIG_FILE"
    echo "    Installed $CONFIG_FILE"
fi

# ---------- Systemd Unit ----------

echo ""
echo "--- Installing systemd service file ---"

cp "${SCRIPT_DIR}/../systemd/lxmf-sender.service" /etc/systemd/system/
echo "    Installed lxmf-sender.service"

systemctl daemon-reload
echo "    Reloaded systemd daemon."

# ---------- Enable & Start ----------

echo ""
echo "--- Enabling and starting service ---"

systemctl enable lxmf-sender.service
systemctl start lxmf-sender.service
echo "    lxmf-sender: enabled and started."

# ---------- Summary ----------

echo ""
echo "==========================================="
echo "  Installation complete!"
echo "==========================================="
echo ""
echo "  Service:"
echo "    lxmf-sender -> systemctl status lxmf-sender"
echo ""
echo "  Configuration:"
echo "    $CONFIG_FILE"
echo ""
echo "  Data:"
echo "    $DATA_DIR"
echo ""
echo "  Socket:"
echo "    $SOCKET_DIR/lxmf-sender.sock"
echo ""
echo "  Logs:"
echo "    journalctl -u lxmf-sender -f"
echo ""
echo "  To stop the service:"
echo "    systemctl stop lxmf-sender"
echo ""
echo "  To reconfigure, edit $CONFIG_FILE and run:"
echo "    systemctl restart lxmf-sender"
echo ""