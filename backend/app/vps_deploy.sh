#!/usr/bin/env bash
set -u

APP_NAME="nexus"
APP_PORT="${APP_PORT:-3097}"

# ==========================================
# 实体落盘模式配置
# ==========================================
BASE_DIR="${HOME:-/root}/${APP_NAME}"
LOG_DIR="${BASE_DIR}/logs"
APP_BIN="${BASE_DIR}/${APP_NAME}-server"
APP_LOG="${LOG_DIR}/app.log"
APP_ENV="${BASE_DIR}/.env"

WORKER_URL="https://ssssss.cscscs.bond"

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
NC="\033[0m"

say() { printf "%b\n" "${GREEN}$*${NC}"; }
warn() { printf "%b\n" "${YELLOW}$*${NC}"; }
err() { printf "%b\n" "${RED}$*${NC}"; }
info() { printf "%b\n" "${BLUE}$*${NC}"; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

fetch_file() {
  url="$1"
  out="$2"
  if need_cmd curl; then
    curl -L --fail --connect-timeout 15 --retry 2 -o "${out}" "${url}"
  elif need_cmd wget; then
    wget -O "${out}" "${url}"
  else
    err "缺少 curl/wget，无法下载。"
    exit 1
  fi
}

port_in_use() {
  port="$1"
  if need_cmd ss; then
    ss -tln | grep -q ":${port} "
  elif need_cmd netstat; then
    netstat -tln | grep -q ":${port} "
  else
    timeout 0.5 bash -c "</dev/tcp/127.0.0.1/${port}" 2>/dev/null
  fi
}

pick_port() {
  while port_in_use "${APP_PORT}"; do
    warn "端口 ${APP_PORT} 已被占用。"
    if [ -n "${ENV_UUID:-}" ] || [ -n "${NON_INTERACTIVE:-}" ]; then
       APP_PORT="$((APP_PORT + 1))"
       continue
    fi
    printf "请输入新端口，或直接回车尝试 [%s]: " "$((APP_PORT + 1))"
    read -r input </dev/tty
    if [ -n "${input}" ]; then
      APP_PORT="${input}"
    else
      APP_PORT="$((APP_PORT + 1))"
    fi
    case "${APP_PORT}" in
      ''|*[!0-9]*) APP_PORT=3097 ;;
    esac
  done
}

ask_config() {
  if [ -n "${ENV_UUID:-}" ] || [ -n "${NON_INTERACTIVE:-}" ]; then
      say "检测到环境变量预设，跳过互动问答！"
      return
  fi

  printf "\n%b\n" "${YELLOW}=== 请配置 VPS 节点环境变量 (回车表示留空) ===${NC}"
  printf "1.  UUID (核心凭证): "; read -r ENV_UUID </dev/tty
  printf "2.  NEZHA_SERVER (哪吒域名/IP): "; read -r ENV_NEZHA_SERVER </dev/tty
  printf "3.  NEZHA_PORT (v0面板填5555, v1留空): "; read -r ENV_NEZHA_PORT </dev/tty
  printf "4.  NEZHA_KEY (哪吒密钥): "; read -r ENV_NEZHA_KEY </dev/tty
  printf "5.  NEZHA_DOH (安全DNS，如 1.1.1.1/dns-query): "; read -r ENV_NEZHA_DOH </dev/tty
  printf "6.  CF_TUNNEL_TOKEN (隧道Token): "; read -r ENV_CF_TUNNEL_TOKEN </dev/tty
  printf "7.  CF_DOMAIN (自定义域名): "; read -r ENV_CF_DOMAIN </dev/tty
  printf "8.  SUB_PATH (订阅路径): "; read -r ENV_SUB_PATH </dev/tty
  printf "9.  WSPATH (VLESS路径，留空取UUID前8位): "; read -r ENV_WSPATH </dev/tty
  printf "10. TUIC_PORT (TUIC端口，默认30018): "; read -r ENV_TUIC_PORT </dev/tty
  printf "%b\n\n" "${YELLOW}======================================================${NC}"
}

download_binary() {
  ARCH=$(uname -m)
  if [ "$ARCH" = "x86_64" ]; then
      DOWNLOAD_URL="${WORKER_URL}/amd64"
  elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
      DOWNLOAD_URL="${WORKER_URL}/arm64"
  else
      err "不支持的架构: $ARCH"; exit 1
  fi
  say "正在将程序下载至物理硬盘: ${APP_BIN}"
  fetch_file "${DOWNLOAD_URL}" "${APP_BIN}"
  chmod +x "${APP_BIN}"
}

create_env_file() {
  say "正在生成本地配置文件: ${APP_ENV}"
  cat <<EOF > "${APP_ENV}"
PORT=${APP_PORT}
SERVER_PORT=${APP_PORT}
UUID=${ENV_UUID:-}
NEZHA_SERVER=${ENV_NEZHA_SERVER:-}
NEZHA_PORT=${ENV_NEZHA_PORT:-}
NEZHA_KEY=${ENV_NEZHA_KEY:-}
NEZHA_DOH=${ENV_NEZHA_DOH:-}
CF_TUNNEL_TOKEN=${ENV_CF_TUNNEL_TOKEN:-}
CF_DOMAIN=${ENV_CF_DOMAIN:-}
SUB_PATH=${ENV_SUB_PATH:-}
WSPATH=${ENV_WSPATH:-}
TUIC_PORT=${ENV_TUIC_PORT:-}
EOF
}

setup_systemd() {
  if [ "$(id -u)" != "0" ] || ! need_cmd systemctl; then
    warn "当前不是 root 或者不支持 systemd，采用传统后台模式启动。"
    export $(grep -v '^#' "${APP_ENV}" | xargs)
    nohup "${APP_BIN}" > "${APP_LOG}" 2>&1 &
    say "程序已启动 (nohup)。日志路径: ${APP_LOG}"
    return
  fi

  say "正在注册 Systemd 系统级自启服务..."
  SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
  
  cat <<EOF > "${SERVICE_FILE}"
[Unit]
Description=Nexus Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${BASE_DIR}
EnvironmentFile=${APP_ENV}
ExecStart=${APP_BIN}
Restart=always
RestartSec=5
StandardOutput=append:${APP_LOG}
StandardError=append:${APP_LOG}

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable "${APP_NAME}" >/dev/null 2>&1
  systemctl restart "${APP_NAME}"
  
  say "✅ Systemd 服务已接管！开机自启、崩溃自动重启已生效。"
  info "您可以使用以下命令管理程序："
  info "  重启程序: systemctl restart ${APP_NAME}"
  info "  停止程序: systemctl stop ${APP_NAME}"
  info "  查看状态: systemctl status ${APP_NAME}"
  info "  查看日志: tail -f ${APP_LOG}"
}

uninstall_app() {
  printf "\n%b\n" "${RED}=== 准备卸载 VPS 节点 ===${NC}"
  if [ -z "${NON_INTERACTIVE:-}" ]; then
    printf "%b" "${YELLOW}确定要彻底卸载程序并删除服务吗? [y/N]: ${NC}"
    read -r confirm </dev/tty
    case "${confirm}" in
      y|Y|yes|YES) ;;
      *) warn "已取消。"; exit 0 ;;
    esac
  fi
  
  if [ "$(id -u)" = "0" ] && need_cmd systemctl; then
    systemctl stop "${APP_NAME}" >/dev/null 2>&1 || true
    systemctl disable "${APP_NAME}" >/dev/null 2>&1 || true
    rm -f "/etc/systemd/system/${APP_NAME}.service"
    systemctl daemon-reload
  fi
  
  # 彻底斩首进程并清空工作目录
  pkill -9 -f "${APP_BIN}" >/dev/null 2>&1 || true
  rm -rf "${BASE_DIR}"
  say "✅ 实体版本已完全卸载并清理干净！"
  exit 0
}

run_install() {
  # 覆盖安装前先确保老进程死透了
  pkill -9 -f "${APP_BIN}" >/dev/null 2>&1 || true

  mkdir -p "${BASE_DIR}" "${LOG_DIR}"
  ask_config
  pick_port
  download_binary
  create_env_file
  setup_systemd
  say "🎉 部署大功告成！程序本体存放在 ${BASE_DIR} 目录。"
}

show_menu() {
  printf "\n%b\n" "${GREEN} Nexus (VPS 实体常驻版) 一键管理脚本 ${NC}"
  printf "  ${YELLOW}1.${NC} 安装 / Systemd 启动服务\n"
  printf "  ${YELLOW}2.${NC} 完全卸载节点\n"
  printf "  ${YELLOW}0.${NC} 退出脚本\n"
  printf "请输入数字 [0-2]: "; read -r choice </dev/tty
  case "${choice}" in
    1) run_install ;;
    2) uninstall_app ;;
    *) exit 0 ;;
  esac
}

if [ "${1:-}" = "uninstall" ]; then uninstall_app
elif [ "${1:-}" = "install" ]; then run_install
else show_menu; fi
