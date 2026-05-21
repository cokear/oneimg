#!/usr/bin/env bash
set -euo pipefail

BIN_URL="https://bbbb.emem.qzz.io"
BIN_PATH_ROOT="/usr/local/bin/sb"
SERVICE_PATH_ROOT="/etc/systemd/system/sb.service"
OPENRC_PATH_ROOT="/etc/init.d/sb"
LOG_PATH_ROOT="/tmp/sb.log"
BIN_PATH_USER="$HOME/.local/bin/sb"
SERVICE_PATH_USER="$HOME/.config/systemd/user/sb.service"
LOG_PATH_USER="$HOME/.local/state/sb/sb.log"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
RESET="\033[0m"

ensure_root_paths() {
  mkdir -p "$(dirname "$BIN_PATH_ROOT")"
}

ensure_user_paths() {
  mkdir -p "$HOME/.local/bin"
  mkdir -p "$HOME/.config/systemd/user"
  mkdir -p "$(dirname "$LOG_PATH_USER")"
}

root_systemd_available() {
  command -v systemctl >/dev/null 2>&1 && systemctl list-units >/dev/null 2>&1
}

user_systemd_available() {
  command -v systemctl >/dev/null 2>&1 && systemctl --user list-units >/dev/null 2>&1
}

openrc_available() {
  command -v rc-service >/dev/null 2>&1 && [[ -d /etc/init.d ]]
}

validate_port() {
  local port="$1"
  [[ "$port" =~ ^[0-9]+$ ]] && (( port >= 1 && port <= 65535 ))
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

download_root_binary() {
  ensure_root_paths
  curl -fsSL "$BIN_URL" -o "$BIN_PATH_ROOT"
  chmod +x "$BIN_PATH_ROOT"
}

install_sb_root_systemd() {
  local port="$1"
  echo -e "${YELLOW}开始安装 (root/systemd)...${RESET}"
  download_root_binary
  mkdir -p "$(dirname "$SERVICE_PATH_ROOT")"

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

install_sb_root_openrc() {
  local port="$1"
  echo -e "${YELLOW}开始安装 (root/OpenRC)...${RESET}"
  download_root_binary

  cat > "$OPENRC_PATH_ROOT" <<EOF
#!/sbin/openrc-run
name="sb"
description="sb service"
command="$BIN_PATH_ROOT"
command_args="--public-port $port"
command_background="yes"
pidfile="/run/sb.pid"
output_log="$LOG_PATH_ROOT"
error_log="$LOG_PATH_ROOT"
directory="/"
export PORT=""
export SERVER_PORT=""
export PRIMARY_PORT=""

depend() {
  need net
  after firewall
}
EOF

  chmod +x "$OPENRC_PATH_ROOT"
  rc-update add sb default
  rc-service sb restart
  rc-service sb status || true
  echo -e "${GREEN}安装完成。${RESET}"
}

install_sb_root_nohup() {
  local port="$1"
  echo -e "${YELLOW}开始安装 (root/nohup)...${RESET}"
  download_root_binary
  pkill -f "$BIN_PATH_ROOT" 2>/dev/null || true
  nohup "$BIN_PATH_ROOT" --public-port "$port" >"$LOG_PATH_ROOT" 2>&1 &
  echo -e "${GREEN}已后台启动。日志: $LOG_PATH_ROOT${RESET}"
}

install_sb_root() {
  local port="$1"
  if root_systemd_available; then
    install_sb_root_systemd "$port"
  elif openrc_available; then
    install_sb_root_openrc "$port"
  else
    install_sb_root_nohup "$port"
  fi
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
  pkill -f "$BIN_PATH_USER" 2>/dev/null || true
  nohup "$BIN_PATH_USER" --public-port "$port" >"$LOG_PATH_USER" 2>&1 &
  echo -e "${GREEN}已后台启动。日志: $LOG_PATH_USER${RESET}"
}

uninstall_sb_root() {
  echo -e "${YELLOW}开始卸载 (root)...${RESET}"
  systemctl stop sb 2>/dev/null || true
  systemctl disable sb 2>/dev/null || true
  rc-service sb stop 2>/dev/null || true
  rc-update del sb default 2>/dev/null || true
  pkill -f "$BIN_PATH_ROOT" 2>/dev/null || true
  rm -f "$SERVICE_PATH_ROOT"
  rm -f "$OPENRC_PATH_ROOT"
  rm -f "$BIN_PATH_ROOT"
  systemctl daemon-reload 2>/dev/null || true
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
  while true; do
    port="$(prompt "请输入容器监听端口" "33636")"
    if validate_port "$port"; then
      break
    fi
    echo -e "${RED}端口必须是 1-65535 的数字。${RESET}"
  done

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

  if user_systemd_available; then
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
