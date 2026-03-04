#!/usr/bin/env bash
set -euo pipefail

BIN_URL="https://github.com/cokear/oneimg/raw/refs/heads/main/data/sb"
BIN_PATH="/usr/local/bin/sb"
SERVICE_PATH="/etc/systemd/system/sb.service"

need_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "Please run as root (sudo)." >&2
    exit 1
  fi
}

prompt() {
  local label="$1"
  local default="$2"
  local val
  if [[ -n "$default" ]]; then
    read -r -p "$label [$default]: " val
    echo "${val:-$default}"
  else
    read -r -p "$label: " val
    echo "$val"
  fi
}

install_sb() {
  local port="$1"
  echo "Installing sb..."
  curl -fsSL "$BIN_URL" -o "$BIN_PATH"
  chmod +x "$BIN_PATH"

  cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=sb service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$BIN_PATH --public-port $port
Restart=always
RestartSec=2
WorkingDirectory=/
Environment=PORT=
Environment=SERVER_PORT=
Environment=PRIMARY_PORT=

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable sb
  systemctl restart sb
  systemctl status sb --no-pager || true
  echo "Install done."
}

uninstall_sb() {
  echo "Uninstalling sb..."
  systemctl stop sb 2>/dev/null || true
  systemctl disable sb 2>/dev/null || true
  rm -f "$SERVICE_PATH"
  rm -f "$BIN_PATH"
  systemctl daemon-reload
  echo "Uninstall done."
}

config_and_install() {
  local port
  port="$(prompt "Enter container listen port" "33636")"

  echo ""
  echo "Config summary:"
  echo "  Binary URL: $BIN_URL"
  echo "  Listen port: $port"
  echo ""
  local confirm
  confirm="$(prompt "Proceed with install? (y/n)" "y")"
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Cancelled."
    exit 0
  fi

  install_sb "$port"
}

usage() {
  cat <<EOF
Usage:
  $0 install         Interactive config then install
  $0 uninstall       Remove service and binary
EOF
}

main() {
  need_root
  echo "Select action:"
  echo "  1) Install"
  echo "  2) Uninstall"
  echo "  3) Exit"
  local choice
  choice="$(prompt "Enter choice" "1")"

  case "$choice" in
    1) config_and_install ;;
    2) uninstall_sb ;;
    3) echo "Exit." ;;
    *) echo "Invalid choice." ;;
  esac
}

main "$@"
