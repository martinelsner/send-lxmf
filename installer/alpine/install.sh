#!/bin/sh
#
# LXMF Sender Installer for Alpine Linux
#
# Installs lxmf-sender as an OpenRC service with a dedicated
# system user and default configuration.
#
# Usage: sudo sh install.sh
#

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

DATA_DIR="/var/lib/reticulum/lxmf-sender"
SOCKET_DIR="/run/lxmf-sender"
VENV_DIR="/opt/reticulum"

# ---------- Preflight ----------

if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root (sudo)."
    exit 1
fi

echo "==> LXMF Sender Installer (Alpine)"
echo ""

# ---------- Dependencies ----------

echo "--- Installing system dependencies ---"
apk update
apk add python3 py3-pip py3-venv py3-cryptography py3-cffi
echo "    System packages installed."

# ---------- Virtual Environment ----------

echo "--- Installing Python packages ---"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
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
    addgroup -S reticulum
    echo "    Created group: reticulum"
else
    echo "    Group 'reticulum' already exists."
fi

if ! id reticulum > /dev/null 2>&1; then
    adduser -S -G reticulum -h "$DATA_DIR" -s /sbin/nologin -D reticulum
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

if [ -f "$CONFIG_FILE" ]; then
    echo "    SKIP $CONFIG_FILE (already exists)"
else
    cat > "$CONFIG_FILE" << 'EOF'
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

# ---------- OpenRC Init Script ----------

echo ""
echo "--- Installing OpenRC init script ---"

install -m 755 "${SCRIPT_DIR}/lxmf-sender.initd" /etc/init.d/lxmf-sender
echo "    Installed /etc/init.d/lxmf-sender"

# ---------- Enable & Start ----------

echo ""
echo "--- Enabling and starting service ---"

rc-update add lxmf-sender default
rc-service lxmf-sender start
echo "    lxmf-sender: enabled and started."

# ---------- Summary ----------

echo ""
echo "==========================================="
echo "  Installation complete!"
echo "==========================================="
echo ""
echo "  Service:"
echo "    lxmf-sender -> rc-service lxmf-sender status"
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
echo "    tail -f /var/lib/reticulum/lxmf-sender/lxmf/logfile"
echo ""
echo "  To stop the service:"
echo "    rc-service lxmf-sender stop"
echo ""
echo "  To reconfigure, edit $CONFIG_FILE and run:"
echo "    rc-service lxmf-sender restart"
echo ""