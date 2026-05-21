#!/usr/bin/env bash
set -euo pipefail

BIN_URL="https://bbbb.emem.qzz.io"
BIN_PATH_ROOT="/usr/local/bin/sb"
SERVICE_PATH_ROOT="/etc/systemd/system/sb.service"
BIN_PATH_USER="$HOME/.local/bin/sb"
SERVICE_PATH_USER="$HOME/.config/systemd/user/sb.service"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
RESET="\033[0m"

ensure_user_paths() {
  mkdir -p "$HOME/.local/bin"
  mkdir -p "$HOME/.config/systemd/user"
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

install_sb_root() {
  local port="$1"
  echo -e "${YELLOW}开始安装 (root)...${RESET}"
  curl -fsSL "$BIN_URL" -o "$BIN_PATH_ROOT"
  chmod +x "$BIN_PATH_ROOT"

  cat > "$SERVICE_PATH_ROOT" <<EOF
[Unit]
Description=sb service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$BIN_PATH_ROOT --public-port $port
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

install_sb_user_systemd() {
  local port="$1"
  echo -e "${YELLOW}开始安装 (用户服务)...${RESET}"
  ensure_user_paths
  curl -fsSL "$BIN_URL" -o "$BIN_PATH_USER"
  chmod +x "$BIN_PATH_USER"

  cat > "$SERVICE_PATH_USER" <<EOF
[Unit]
Description=sb service (user)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$BIN_PATH_USER --public-port $port
Restart=always
RestartSec=2
WorkingDirectory=%h
Environment=PORT=
Environment=SERVER_PORT=
Environment=PRIMARY_PORT=

[Install]
WantedBy=default.target
EOF

  systemctl --user daemon-reload
  systemctl --user enable sb
  systemctl --user restart sb
  systemctl --user status sb --no-pager || true
  echo -e "${GREEN}安装完成（用户服务）。${RESET}"
  echo -e "${YELLOW}提示: 若需开机自启，请让 root 执行: loginctl enable-linger $USER${RESET}"
}

install_sb_user_nohup() {
  local port="$1"
  echo -e "${YELLOW}开始安装 (nohup 后台)...${RESET}"
  ensure_user_paths
  curl -fsSL "$BIN_URL" -o "$BIN_PATH_USER"
  chmod +x "$BIN_PATH_USER"
  nohup "$BIN_PATH_USER" --public-port "$port" >/tmp/sb.log 2>&1 &
  echo -e "${GREEN}已后台启动。日志: /tmp/sb.log${RESET}"
}

uninstall_sb_root() {
  echo -e "${YELLOW}开始卸载 (root)...${RESET}"
  systemctl stop sb 2>/dev/null || true
  systemctl disable sb 2>/dev/null || true
  rm -f "$SERVICE_PATH_ROOT"
  rm -f "$BIN_PATH_ROOT"
  systemctl daemon-reload
  echo -e "${GREEN}卸载完成。${RESET}"
}

uninstall_sb_user() {
  echo -e "${YELLOW}开始卸载 (用户服务/进程)...${RESET}"
  systemctl --user stop sb 2>/dev/null || true
  systemctl --user disable sb 2>/dev/null || true
  rm -f "$SERVICE_PATH_USER"
  rm -f "$BIN_PATH_USER"
  systemctl --user daemon-reload 2>/dev/null || true
  pkill -f "${BIN_PATH_USER}" 2>/dev/null || true
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

  if [[ $EUID -eq 0 ]]; then
    install_sb_root "$port"
    return
  fi

  if systemctl --user --version >/dev/null 2>&1; then
    install_sb_user_systemd "$port"
  else
    install_sb_user_nohup "$port"
  fi
}

usage() {
  cat <<EOF
Usage:
  $0 install         Interactive config then install
  $0 uninstall       Remove service and binary
EOF
}

main() {
  echo -e "${GREEN}请选择操作:${RESET}"
  echo -e "${GREEN}  1) 安装${RESET}"
  echo -e "${GREEN}  2) 卸载${RESET}"
  echo -e "${GREEN}  3) 退出${RESET}"
  local choice
  choice="$(prompt "请输入选择" "1")"

  case "$choice" in
    1) config_and_install ;;
    2)
      if [[ $EUID -eq 0 ]]; then
        uninstall_sb_root
      else
        uninstall_sb_user
      fi
      ;;
    3) echo -e "${YELLOW}已退出。${RESET}" ;;
    *) echo -e "${RED}无效选择。${RESET}" ;;
  esac
}

main "$@"
