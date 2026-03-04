#!/usr/bin/env bash
set -euo pipefail

BIN_URL="https://sss.bbe.pp.ua"
BIN_PATH="/usr/local/bin/sb"
SERVICE_PATH="/etc/systemd/system/sb.service"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
RESET="\033[0m"

need_root() {
  if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}请使用 root 或 sudo 运行。${RESET}" >&2
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
  echo -e "${YELLOW}开始安装...${RESET}"
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
  echo -e "${GREEN}安装完成。${RESET}"
}

uninstall_sb() {
  echo -e "${YELLOW}开始卸载...${RESET}"
  systemctl stop sb 2>/dev/null || true
  systemctl disable sb 2>/dev/null || true
  rm -f "$SERVICE_PATH"
  rm -f "$BIN_PATH"
  systemctl daemon-reload
  echo -e "${GREEN}卸载完成。${RESET}"
}

config_and_install() {
  local port
  port="$(prompt "请输入容器监听端口" "33636")"

  echo ""
  echo -e "${GREEN}配置确认:${RESET}"
  echo "  二进制地址: $BIN_URL"
  echo "  监听端口: $port"
  echo ""
  local confirm
  confirm="$(prompt "确认安装? (y/n)" "y")"
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo -e "${RED}已取消。${RESET}"
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
  echo -e "${GREEN}请选择操作:${RESET}"
  echo -e "${GREEN}  1) 安装${RESET}"
  echo -e "${GREEN}  2) 卸载${RESET}"
  echo -e "${GREEN}  3) 退出${RESET}"
  local choice
  choice="$(prompt "请输入选择" "1")"

  case "$choice" in
    1) config_and_install ;;
    2) uninstall_sb ;;
    3) echo -e "${YELLOW}已退出。${RESET}" ;;
    *) echo -e "${RED}无效选择。${RESET}" ;;
  esac
}

main "$@"
