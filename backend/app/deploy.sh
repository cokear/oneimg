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
TUNNEL_LOG="${LOG_DIR}/tunnel.log"
APP_PID_FILE="${RUN_DIR}/app.pid"
TUNNEL_PID_FILE="${RUN_DIR}/tunnel.pid"
CLOUDFLARED_BIN="${BIN_DIR}/cloudflared"

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
    read -r input
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
  APP_PORT="${APP_PORT}" PORT="${APP_PORT}" nohup "${PYTHON_BIN}" "${APP_ENTRY}" > "${APP_LOG}" 2>&1 &
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

install_cloudflared() {
  if [ -x "${CLOUDFLARED_BIN}" ]; then
    return 0
  fi

  arch="$(uname -m)"
  case "${arch}" in
    x86_64|amd64)
      url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
      ;;
    aarch64|arm64)
      url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
      ;;
    *)
      err "不支持的架构: ${arch}"
      exit 1
      ;;
  esac

  say "正在下载 cloudflared..."
  fetch_file "${url}" "${CLOUDFLARED_BIN}"
  chmod +x "${CLOUDFLARED_BIN}"
}

start_tunnel_with_token() {
  printf "%b" "${YELLOW}是否启动 Cloudflare Tunnel? [y/N]: ${NC}"
  read -r answer
  case "${answer}" in
    y|Y|yes|YES)
      ;;
    *)
      warn "已跳过 CF 隧道。"
      return 0
      ;;
  esac

  install_cloudflared

  printf "%b" "${YELLOW}请输入 Cloudflare Tunnel Token（不会保存到磁盘）: ${NC}"
  stty -echo 2>/dev/null || true
  read -r CF_TOKEN
  stty echo 2>/dev/null || true
  printf "\n"

  if [ -z "${CF_TOKEN}" ]; then
    warn "Token 为空，改用临时 trycloudflare 隧道。"
    stop_if_running "${TUNNEL_PID_FILE}" "CF 隧道"
    say "正在后台启动临时隧道..."
    nohup "${CLOUDFLARED_BIN}" tunnel --no-autoupdate --url "http://127.0.0.1:${APP_PORT}" > "${TUNNEL_LOG}" 2>&1 &
    echo $! > "${TUNNEL_PID_FILE}"
    sleep 5
    if is_running "${TUNNEL_PID_FILE}"; then
      say "临时隧道已启动: PID $(cat "${TUNNEL_PID_FILE}")"
      grep -Eo 'https://[-a-zA-Z0-9.]+\.trycloudflare\.com' "${TUNNEL_LOG}" | tail -n 1 || true
      info "隧道日志: ${TUNNEL_LOG}"
    else
      err "临时隧道启动失败，最后日志如下:"
      tail -n 80 "${TUNNEL_LOG}" 2>/dev/null || true
    fi
    return 0
  fi

  stop_if_running "${TUNNEL_PID_FILE}" "CF 隧道"

  say "正在后台启动 CF 隧道..."
  TUNNEL_TOKEN="${CF_TOKEN}" nohup "${CLOUDFLARED_BIN}" tunnel --no-autoupdate run > "${TUNNEL_LOG}" 2>&1 &
  echo $! > "${TUNNEL_PID_FILE}"
  unset CF_TOKEN
  sleep 3

  if is_running "${TUNNEL_PID_FILE}"; then
    say "CF 隧道已启动: PID $(cat "${TUNNEL_PID_FILE}")"
    info "隧道日志: ${TUNNEL_LOG}"
  else
    err "CF 隧道启动失败，最后日志如下:"
    tail -n 80 "${TUNNEL_LOG}" 2>/dev/null || true
  fi
}

main() {
  mkdir -p "${BASE_DIR}" "${SRC_DIR}" "${BIN_DIR}" "${LOG_DIR}" "${RUN_DIR}"

  printf "%b\n" "${GREEN}========================================${NC}"
  printf "%b\n" "${GREEN} OneImg 一键部署启动脚本${NC}"
  printf "%b\n" "${GREEN}========================================${NC}"
  printf "项目地址: %s\n" "${ZIP_URL}"
  printf "安装目录: %s\n" "${BASE_DIR}"
  printf "默认端口: %s\n" "${APP_PORT}"
  printf "\n"

  download_and_extract
  install_deps
  start_app
  start_tunnel_with_token

  printf "\n"
  say "完成。"
  printf "应用日志: %s\n" "${APP_LOG}"
  printf "隧道日志: %s\n" "${TUNNEL_LOG}"
  printf "查看进程: ps -ef | grep -E 'main.py|cloudflared'\n"
}

main "$@"
