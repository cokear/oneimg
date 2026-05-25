#!/usr/bin/env bash
set -u

APP_NAME="pyapp"
BASE_DIR="${HOME}/apps/${APP_NAME}"
SRC_DIR="${BASE_DIR}/src"
BIN_DIR="${BASE_DIR}/bin"
LOG_DIR="${BASE_DIR}/logs"
RUN_DIR="${BASE_DIR}/run"
CFG_FILE="${BASE_DIR}/config.env"
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

ZIP_URL="https://github.com/cokear/oneimg/raw/refs/heads/main/backend/app/py.zip"
APP_ENTRY="main.py"
APP_PORT="3097"
PYTHON_BIN="${PYTHON_BIN:-python}"

mkdir -p "${BASE_DIR}" "${SRC_DIR}" "${BIN_DIR}" "${LOG_DIR}" "${RUN_DIR}"

say() {
  printf "%b\n" "${GREEN}$*${NC}"
}

warn() {
  printf "%b\n" "${YELLOW}$*${NC}"
}

err() {
  printf "%b\n" "${RED}$*${NC}"
}

info() {
  printf "%b\n" "${BLUE}$*${NC}"
}

pause() {
  printf "%b" "${YELLOW}按回车继续...${NC}"
  read -r _
}

load_config() {
  if [ -f "${CFG_FILE}" ]; then
    # shellcheck disable=SC1090
    . "${CFG_FILE}"
  fi
}

save_config() {
  {
    printf 'ZIP_URL=%q\n' "${ZIP_URL}"
    printf 'APP_ENTRY=%q\n' "${APP_ENTRY}"
    printf 'APP_PORT=%q\n' "${APP_PORT}"
    printf 'PYTHON_BIN=%q\n' "${PYTHON_BIN}"
  } > "${CFG_FILE}"
  chmod 600 "${CFG_FILE}" 2>/dev/null || true
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
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

confirm_port() {
  while true; do
    printf "App port [%s]: " "${APP_PORT}"
    read -r input
    if [ -n "${input}" ]; then
      APP_PORT="${input}"
    fi

    case "${APP_PORT}" in
      ''|*[!0-9]*)
        err "端口必须是数字。"
        continue
        ;;
    esac

    if [ "${APP_PORT}" -lt 1 ] || [ "${APP_PORT}" -gt 65535 ]; then
      err "端口范围必须是 1-65535。"
      continue
    fi

    if port_in_use "${APP_PORT}"; then
      warn "端口 ${APP_PORT} 已被占用。"
      printf "输入新端口，或直接回车继续使用 %s: " "${APP_PORT}"
      read -r input
      if [ -n "${input}" ]; then
        APP_PORT="${input}"
        continue
      fi
    fi

    return 0
  done
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
    return 1
  fi
}

is_running() {
  pid_file="$1"
  [ -f "${pid_file}" ] || return 1
  pid="$(cat "${pid_file}" 2>/dev/null || true)"
  [ -n "${pid}" ] || return 1
  kill -0 "${pid}" >/dev/null 2>&1
}

stop_pid() {
  pid_file="$1"
  name="$2"
  if is_running "${pid_file}"; then
    pid="$(cat "${pid_file}")"
    warn "正在停止 ${name}: PID ${pid}"
    kill "${pid}" >/dev/null 2>&1 || true
    sleep 2
    if kill -0 "${pid}" >/dev/null 2>&1; then
      warn "${name} 仍在运行，正在强制结束。"
      kill -9 "${pid}" >/dev/null 2>&1 || true
    fi
  fi
  rm -f "${pid_file}"
}

configure_project() {
  load_config
  printf "%b\n" "${GREEN}项目配置${NC}"

  printf "GitHub ZIP 下载地址 [%s]: " "${ZIP_URL}"
  read -r input
  if [ -n "${input}" ]; then
    ZIP_URL="${input}"
  fi

  printf "入口文件 [%s]: " "${APP_ENTRY}"
  read -r input
  if [ -n "${input}" ]; then
    APP_ENTRY="${input}"
  fi

  printf "Python 命令 [%s]: " "${PYTHON_BIN}"
  read -r input
  if [ -n "${input}" ]; then
    PYTHON_BIN="${input}"
  fi

  confirm_port
  save_config
  say "配置已保存到 ${CFG_FILE}"
}

download_project() {
  load_config
  if [ -z "${ZIP_URL}" ]; then
    configure_project
  fi
  if [ -z "${ZIP_URL}" ]; then
    err "ZIP_URL 为空。"
    return 1
  fi

  zip_path="${BASE_DIR}/project.zip"
  tmp_dir="${BASE_DIR}/extract.tmp"

  say "正在下载项目 ZIP..."
  fetch_file "${ZIP_URL}" "${zip_path}" || return 1

  rm -rf "${tmp_dir}"
  mkdir -p "${tmp_dir}"

  say "正在解压项目..."
  if need_cmd unzip; then
    unzip -q -o "${zip_path}" -d "${tmp_dir}" || return 1
  else
    "${PYTHON_BIN}" -m zipfile -e "${zip_path}" "${tmp_dir}" || return 1
  fi

  first_dir="$(find "${tmp_dir}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  first_file_count="$(find "${tmp_dir}" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"

  rm -rf "${SRC_DIR}.old"
  if [ -d "${SRC_DIR}" ]; then
    mv "${SRC_DIR}" "${SRC_DIR}.old"
  fi
  mkdir -p "${SRC_DIR}"

  if [ "${first_file_count}" = "1" ] && [ -n "${first_dir}" ]; then
    cp -a "${first_dir}/." "${SRC_DIR}/"
  else
    cp -a "${tmp_dir}/." "${SRC_DIR}/"
  fi

  rm -rf "${tmp_dir}"
  say "项目已部署到 ${SRC_DIR}"
}

install_deps() {
  load_config
  if [ ! -d "${SRC_DIR}" ]; then
    err "源码目录不存在: ${SRC_DIR}"
    return 1
  fi

  cd "${SRC_DIR}" || return 1
  if [ -f "requirements.txt" ]; then
    say "正在安装 Python 依赖..."
    "${PYTHON_BIN}" -m pip install --user -r requirements.txt
  else
    warn "没有找到 requirements.txt，跳过依赖安装。"
  fi
}

start_app() {
  load_config
  if is_running "${APP_PID_FILE}"; then
    warn "应用已在运行: PID $(cat "${APP_PID_FILE}")"
    return 0
  fi
  if [ ! -f "${SRC_DIR}/${APP_ENTRY}" ]; then
    err "入口文件不存在: ${SRC_DIR}/${APP_ENTRY}"
    return 1
  fi

  cd "${SRC_DIR}" || return 1
  say "正在后台启动应用..."
  nohup "${PYTHON_BIN}" "${APP_ENTRY}" > "${APP_LOG}" 2>&1 &
  echo $! > "${APP_PID_FILE}"
  sleep 2

  if is_running "${APP_PID_FILE}"; then
    say "应用已启动: PID $(cat "${APP_PID_FILE}")"
    info "日志: ${APP_LOG}"
  else
    err "应用启动失败，请查看日志: ${APP_LOG}"
    tail -n 80 "${APP_LOG}" 2>/dev/null || true
    return 1
  fi
}

stop_app() {
  stop_pid "${APP_PID_FILE}" "应用"
}

install_cloudflared() {
  if [ -x "${CLOUDFLARED_BIN}" ]; then
    say "cloudflared 已存在: ${CLOUDFLARED_BIN}"
    "${CLOUDFLARED_BIN}" --version || true
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
      return 1
      ;;
  esac

  say "正在下载 cloudflared..."
  fetch_file "${url}" "${CLOUDFLARED_BIN}" || return 1
  chmod +x "${CLOUDFLARED_BIN}"
  say "cloudflared 安装完成。"
  "${CLOUDFLARED_BIN}" --version || true
}

start_tunnel() {
  if is_running "${TUNNEL_PID_FILE}"; then
    warn "CF 隧道已在运行: PID $(cat "${TUNNEL_PID_FILE}")"
    return 0
  fi

  if [ ! -x "${CLOUDFLARED_BIN}" ]; then
    install_cloudflared || return 1
  fi

  printf "%b" "${YELLOW}请输入 Cloudflare Tunnel Token（不会保存到磁盘）: ${NC}"
  stty -echo 2>/dev/null || true
  read -r CF_TOKEN
  stty echo 2>/dev/null || true
  printf "\n"

  if [ -z "${CF_TOKEN}" ]; then
    err "Token 为空。"
    return 1
  fi

  say "正在后台启动 Cloudflare Tunnel..."
  TUNNEL_TOKEN="${CF_TOKEN}" nohup "${CLOUDFLARED_BIN}" tunnel --no-autoupdate run > "${TUNNEL_LOG}" 2>&1 &
  echo $! > "${TUNNEL_PID_FILE}"
  unset CF_TOKEN
  sleep 3

  if is_running "${TUNNEL_PID_FILE}"; then
    say "CF 隧道已启动: PID $(cat "${TUNNEL_PID_FILE}")"
    info "日志: ${TUNNEL_LOG}"
  else
    err "CF 隧道启动失败，请查看日志: ${TUNNEL_LOG}"
    tail -n 80 "${TUNNEL_LOG}" 2>/dev/null || true
    return 1
  fi
}

start_quick_tunnel() {
  load_config
  if is_running "${TUNNEL_PID_FILE}"; then
    warn "CF 隧道已在运行: PID $(cat "${TUNNEL_PID_FILE}")"
    return 0
  fi

  if [ ! -x "${CLOUDFLARED_BIN}" ]; then
    install_cloudflared || return 1
  fi

  say "正在启动临时 trycloudflare 隧道..."
  nohup "${CLOUDFLARED_BIN}" tunnel --no-autoupdate --url "http://127.0.0.1:${APP_PORT}" > "${TUNNEL_LOG}" 2>&1 &
  echo $! > "${TUNNEL_PID_FILE}"
  sleep 5

  if is_running "${TUNNEL_PID_FILE}"; then
    say "临时隧道已启动: PID $(cat "${TUNNEL_PID_FILE}")"
    grep -Eo 'https://[-a-zA-Z0-9.]+\.trycloudflare\.com' "${TUNNEL_LOG}" | tail -n 1 || true
    info "日志: ${TUNNEL_LOG}"
  else
    err "临时隧道启动失败，请查看日志: ${TUNNEL_LOG}"
    tail -n 80 "${TUNNEL_LOG}" 2>/dev/null || true
    return 1
  fi
}

stop_tunnel() {
  stop_pid "${TUNNEL_PID_FILE}" "CF 隧道"
}

status_all() {
  load_config
  printf "%b\n" "${GREEN}运行状态${NC}"
  if is_running "${APP_PID_FILE}"; then
    say "应用: 运行中 PID $(cat "${APP_PID_FILE}")"
  else
    warn "应用: 已停止"
  fi

  if is_running "${TUNNEL_PID_FILE}"; then
    say "隧道: 运行中 PID $(cat "${TUNNEL_PID_FILE}")"
  else
    warn "隧道: 已停止"
  fi

  printf "目录: %s\n" "${BASE_DIR}"
  printf "入口: %s\n" "${SRC_DIR}/${APP_ENTRY}"
  printf "端口: %s\n" "${APP_PORT}"
}

show_logs() {
  printf "%b\n" "${GREEN}选择日志${NC}"
  printf "1. 应用日志\n"
  printf "2. 隧道日志\n"
  printf "请选择: "
  read -r choice
  case "${choice}" in
    1)
      tail -n 120 "${APP_LOG}" 2>/dev/null || warn "暂无应用日志。"
      ;;
    2)
      tail -n 120 "${TUNNEL_LOG}" 2>/dev/null || warn "暂无隧道日志。"
      ;;
    *)
      warn "已取消。"
      ;;
  esac
}

deploy_all() {
  configure_project || return 1
  download_project || return 1
  install_deps || return 1
  start_app || return 1
  printf "%b" "${YELLOW}是否启动 Cloudflare Tunnel? [y/N]: ${NC}"
  read -r answer
  case "${answer}" in
    y|Y|yes|YES)
      start_tunnel
      ;;
    *)
      warn "已跳过 CF 隧道。"
      ;;
  esac
}

menu() {
  clear 2>/dev/null || true
  printf "%b\n" "${GREEN}========================================${NC}"
  printf "%b\n" "${GREEN} Python 应用绿色启动器${NC}"
  printf "%b\n" "${GREEN}========================================${NC}"
  printf "目录: %s\n" "${BASE_DIR}"
  printf "\n"
  printf "1. 配置项目\n"
  printf "2. 下载/更新项目 ZIP\n"
  printf "3. 安装 Python 依赖\n"
  printf "4. 后台启动应用\n"
  printf "5. 停止应用\n"
  printf "6. 安装 cloudflared\n"
  printf "7. 启动 CF 隧道（Token 不落盘）\n"
  printf "8. 启动临时 trycloudflare 隧道\n"
  printf "9. 停止 CF 隧道\n"
  printf "10. 查看状态\n"
  printf "11. 查看日志\n"
  printf "12. 一键部署并启动\n"
  printf "0. 退出\n"
  printf "\n请选择: "
}

load_config

while true; do
  menu
  read -r choice
  case "${choice}" in
    1) configure_project; pause ;;
    2) download_project; pause ;;
    3) install_deps; pause ;;
    4) start_app; pause ;;
    5) stop_app; pause ;;
    6) install_cloudflared; pause ;;
    7) start_tunnel; pause ;;
    8) start_quick_tunnel; pause ;;
    9) stop_tunnel; pause ;;
    10) status_all; pause ;;
    11) show_logs; pause ;;
    12) deploy_all; pause ;;
    0) exit 0 ;;
    *) warn "无效选择。"; pause ;;
  esac
done
