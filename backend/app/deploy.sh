#!/usr/bin/env bash
set -u

APP_NAME="oneimg"
ZIP_URL="https://ssssss.cscscs.bond/py.zip"
APP_ENTRY="main.py"
APP_PORT="${APP_PORT:-3097}"
PYTHON_BIN="${PYTHON_BIN:-python}"

BASE_DIR="${HOME}/apps/${APP_NAME}"
SRC_DIR="${BASE_DIR}/src"
BIN_DIR="${BASE_DIR}/bin"
LOG_DIR="${BASE_DIR}/logs"
RUN_DIR="${BASE_DIR}/run"
APP_LOG="${LOG_DIR}/app.log"
APP_PID_FILE="${RUN_DIR}/app.pid"

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
  "${PYTHON_BIN}" - "${port}" <<'PY' >/dev/null 2>&1
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.5)
try:
    sys.exit(0 if sock.connect_ex(("127.0.0.1", port)) == 0 else 1)
finally:
    sock.close()
PY
}

pick_port() {
  while port_in_use "${APP_PORT}"; do
    warn "端口 ${APP_PORT} 已被占用。"
    printf "请输入新端口，或直接回车自动尝试下一个端口 [%s]: " "$((APP_PORT + 1))"
    # 修复管道输入问题
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
  printf "\n%b\n" "${RED}=== 准备卸载 OneImg ===${NC}"
  printf "%b" "${YELLOW}此操作将杀掉程序进程并完全删除目录 [ ${BASE_DIR} ]，确定继续吗? [y/N]: ${NC}"
  # 修复管道输入问题
  read -r confirm </dev/tty
  case "${confirm}" in
    y|Y|yes|YES)
      say "正在停止运行中的程序..."
      stop_if_running "${APP_PID_FILE}" "应用"
      
      say "正在删除安装目录: ${BASE_DIR}"
      rm -rf "${BASE_DIR}"
      
      say "✅ 卸载完成，清理得干干净净！"
      exit 0
      ;;
    *)
      warn "已取消卸载。"
      exit 0
      ;;
  esac
}

ask_config() {
  printf "\n%b\n" "${YELLOW}=== 请配置探针和隧道环境变量 (直接回车表示留空/跳过) ===${NC}"

  # 全部加上 </dev/tty 强制读取键盘，完美适配 curl | bash
  printf "1. UUID (节点的唯一标识): "
  read -r ENV_UUID </dev/tty

  printf "2. NEZHA_SERVER (哪吒面板的域名/IP，可带端口): "
  read -r ENV_NEZHA_SERVER </dev/tty

  printf "3. NEZHA_PORT (针对老版 v0 面板专用，v1请留空): "
  read -r ENV_NEZHA_PORT </dev/tty

  printf "4. NEZHA_KEY (哪吒面板的 Agent 密钥): "
  read -r ENV_NEZHA_KEY </dev/tty

  printf "5. NEZHA_DOH (自定义安全 DNS 解析，防污染): "
  read -r ENV_NEZHA_DOH </dev/tty

  printf "6. CF_TUNNEL_TOKEN (用于脚本内置启动 Cloudflare 隧道): "
  read -r ENV_CF_TUNNEL_TOKEN </dev/tty

  printf "7. CF_DOMAIN (绑定的自定义域名): "
  read -r ENV_CF_DOMAIN </dev/tty
  
  printf "%b\n\n" "${YELLOW}======================================================${NC}"
}

download_and_extract() {
  zip_path="${BASE_DIR}/project.zip"
  tmp_dir="${BASE_DIR}/extract.tmp"

  say "正在下载项目..."
  fetch_file "${ZIP_URL}" "${zip_path}"

  rm -rf "${tmp_dir}"
  mkdir -p "${tmp_dir}"

  say "正在解压项目..."
  if need_cmd unzip; then
    unzip -q -o "${zip_path}" -d "${tmp_dir}"
  else
    "${PYTHON_BIN}" -m zipfile -e "${zip_path}" "${tmp_dir}"
  fi

  first_dir="$(find "${tmp_dir}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  first_count="$(find "${tmp_dir}" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"

  rm -rf "${SRC_DIR}.old"
  if [ -d "${SRC_DIR}" ]; then
    mv "${SRC_DIR}" "${SRC_DIR}.old"
  fi
  mkdir -p "${SRC_DIR}"

  if [ "${first_count}" = "1" ] && [ -n "${first_dir}" ]; then
    cp -a "${first_dir}/." "${SRC_DIR}/"
  else
    cp -a "${tmp_dir}/." "${SRC_DIR}/"
  fi

  rm -rf "${tmp_dir}"
  say "项目目录: ${SRC_DIR}"
}

install_deps() {
  cd "${SRC_DIR}" || exit 1
  if [ -f "requirements.txt" ]; then
    say "正在安装依赖..."
    "${PYTHON_BIN}" -m pip install --user -r requirements.txt
  else
    warn "没有 requirements.txt，跳过依赖安装。"
  fi
}

start_app() {
  if [ ! -f "${SRC_DIR}/${APP_ENTRY}" ]; then
    err "入口文件不存在: ${SRC_DIR}/${APP_ENTRY}"
    exit 1
  fi

  pick_port
  stop_if_running "${APP_PID_FILE}" "应用"

  cd "${SRC_DIR}" || exit 1
  say "正在后台启动应用，端口: ${APP_PORT}"

  export PORT="${APP_PORT}"
  export SERVER_PORT="${APP_PORT}"
  [ -n "${ENV_UUID}" ] && export UUID="${ENV_UUID}"
  [ -n "${ENV_NEZHA_SERVER}" ] && export NEZHA_SERVER="${ENV_NEZHA_SERVER}"
  [ -n "${ENV_NEZHA_PORT}" ] && export NEZHA_PORT="${ENV_NEZHA_PORT}"
  [ -n "${ENV_NEZHA_KEY}" ] && export NEZHA_KEY="${ENV_NEZHA_KEY}"
  [ -n "${ENV_NEZHA_DOH}" ] && export NEZHA_DOH="${ENV_NEZHA_DOH}"
  [ -n "${ENV_CF_TUNNEL_TOKEN}" ] && export CF_TUNNEL_TOKEN="${ENV_CF_TUNNEL_TOKEN}"
  [ -n "${ENV_CF_DOMAIN}" ] && export CF_DOMAIN="${ENV_CF_DOMAIN}"

  nohup "${PYTHON_BIN}" "${APP_ENTRY}" > "${APP_LOG}" 2>&1 &
  echo $! > "${APP_PID_FILE}"
  sleep 2

  if is_running "${APP_PID_FILE}"; then
    say "应用已启动: PID $(cat "${APP_PID_FILE}")"
    info "应用日志: ${APP_LOG}"
  else
    err "应用启动失败，最后日志如下:"
    tail -n 80 "${APP_LOG}" 2>/dev/null || true
    exit 1
  fi
}

main() {
  if [ "${1:-}" = "uninstall" ]; then
    uninstall_app
  fi

  mkdir -p "${BASE_DIR}" "${SRC_DIR}" "${BIN_DIR}" "${LOG_DIR}" "${RUN_DIR}"

  printf "%b\n" "${GREEN}========================================${NC}"
  printf "%b\n" "${GREEN} OneImg 一键部署启动脚本 (集成交互与卸载)${NC}"
  printf "%b\n" "${GREEN}========================================${NC}"
  printf "项目地址: %s\n" "${ZIP_URL}"
  printf "安装目录: %s\n" "${BASE_DIR}"
  printf "默认端口: %s\n" "${APP_PORT}"
  printf "卸载指令: bash $0 uninstall\n"
  printf "\n"

  ask_config
  download_and_extract
  install_deps
  start_app

  printf "\n"
  say "部署完成！"
  printf "应用日志: %s\n" "${APP_LOG}"
  printf "查看进程: ps -ef | grep -E 'main.py'\n"
}

main "$@"
