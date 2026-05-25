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
  printf "%b" "${YELLOW}Press Enter to continue...${NC}"
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
        err "Port must be a number."
        continue
        ;;
    esac

    if [ "${APP_PORT}" -lt 1 ] || [ "${APP_PORT}" -gt 65535 ]; then
      err "Port must be in range 1-65535."
      continue
    fi

    if port_in_use "${APP_PORT}"; then
      warn "Port ${APP_PORT} is already in use."
      printf "Enter a new port, or press Enter to keep using %s: " "${APP_PORT}"
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
    err "curl/wget is missing, cannot download."
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
    warn "Stopping ${name}: PID ${pid}"
    kill "${pid}" >/dev/null 2>&1 || true
    sleep 2
    if kill -0 "${pid}" >/dev/null 2>&1; then
      warn "${name} is still running, killing it."
      kill -9 "${pid}" >/dev/null 2>&1 || true
    fi
  fi
  rm -f "${pid_file}"
}

configure_project() {
  load_config
  printf "%b\n" "${GREEN}Project config${NC}"

  printf "GitHub ZIP URL [%s]: " "${ZIP_URL}"
  read -r input
  if [ -n "${input}" ]; then
    ZIP_URL="${input}"
  fi

  printf "Entry file [%s]: " "${APP_ENTRY}"
  read -r input
  if [ -n "${input}" ]; then
    APP_ENTRY="${input}"
  fi

  printf "Python command [%s]: " "${PYTHON_BIN}"
  read -r input
  if [ -n "${input}" ]; then
    PYTHON_BIN="${input}"
  fi

  confirm_port
  save_config
  say "Config saved to ${CFG_FILE}"
}

download_project() {
  load_config
  if [ -z "${ZIP_URL}" ]; then
    configure_project
  fi
  if [ -z "${ZIP_URL}" ]; then
    err "ZIP_URL is empty."
    return 1
  fi

  zip_path="${BASE_DIR}/project.zip"
  tmp_dir="${BASE_DIR}/extract.tmp"

  say "Downloading project ZIP..."
  fetch_file "${ZIP_URL}" "${zip_path}" || return 1

  rm -rf "${tmp_dir}"
  mkdir -p "${tmp_dir}"

  say "Extracting project..."
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
  say "Project deployed to ${SRC_DIR}"
}

install_deps() {
  load_config
  if [ ! -d "${SRC_DIR}" ]; then
    err "Source directory does not exist: ${SRC_DIR}"
    return 1
  fi

  cd "${SRC_DIR}" || return 1
  if [ -f "requirements.txt" ]; then
    say "Installing Python dependencies..."
    "${PYTHON_BIN}" -m pip install --user -r requirements.txt
  else
    warn "requirements.txt not found, skipping dependency install."
  fi
}

start_app() {
  load_config
  if is_running "${APP_PID_FILE}"; then
    warn "App is already running: PID $(cat "${APP_PID_FILE}")"
    return 0
  fi
  if [ ! -f "${SRC_DIR}/${APP_ENTRY}" ]; then
    err "Entry file does not exist: ${SRC_DIR}/${APP_ENTRY}"
    return 1
  fi

  cd "${SRC_DIR}" || return 1
  say "Starting app in background..."
  nohup "${PYTHON_BIN}" "${APP_ENTRY}" > "${APP_LOG}" 2>&1 &
  echo $! > "${APP_PID_FILE}"
  sleep 2

  if is_running "${APP_PID_FILE}"; then
    say "App started: PID $(cat "${APP_PID_FILE}")"
    info "Log: ${APP_LOG}"
  else
    err "App failed to start, check log: ${APP_LOG}"
    tail -n 80 "${APP_LOG}" 2>/dev/null || true
    return 1
  fi
}

stop_app() {
  stop_pid "${APP_PID_FILE}" "app"
}

install_cloudflared() {
  if [ -x "${CLOUDFLARED_BIN}" ]; then
    say "cloudflared already exists: ${CLOUDFLARED_BIN}"
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
      err "Unsupported architecture: ${arch}"
      return 1
      ;;
  esac

  say "Downloading cloudflared..."
  fetch_file "${url}" "${CLOUDFLARED_BIN}" || return 1
  chmod +x "${CLOUDFLARED_BIN}"
  say "cloudflared installed."
  "${CLOUDFLARED_BIN}" --version || true
}

start_tunnel() {
  if is_running "${TUNNEL_PID_FILE}"; then
    warn "CF tunnel is already running: PID $(cat "${TUNNEL_PID_FILE}")"
    return 0
  fi

  if [ ! -x "${CLOUDFLARED_BIN}" ]; then
    install_cloudflared || return 1
  fi

  printf "%b" "${YELLOW}Enter Cloudflare Tunnel Token (not saved to disk): ${NC}"
  stty -echo 2>/dev/null || true
  read -r CF_TOKEN
  stty echo 2>/dev/null || true
  printf "\n"

  if [ -z "${CF_TOKEN}" ]; then
    err "Token is empty."
    return 1
  fi

  say "Starting Cloudflare Tunnel in background..."
  TUNNEL_TOKEN="${CF_TOKEN}" nohup "${CLOUDFLARED_BIN}" tunnel --no-autoupdate run > "${TUNNEL_LOG}" 2>&1 &
  echo $! > "${TUNNEL_PID_FILE}"
  unset CF_TOKEN
  sleep 3

  if is_running "${TUNNEL_PID_FILE}"; then
    say "CF tunnel started: PID $(cat "${TUNNEL_PID_FILE}")"
    info "Log: ${TUNNEL_LOG}"
  else
    err "CF tunnel failed to start, check log: ${TUNNEL_LOG}"
    tail -n 80 "${TUNNEL_LOG}" 2>/dev/null || true
    return 1
  fi
}

start_quick_tunnel() {
  load_config
  if is_running "${TUNNEL_PID_FILE}"; then
    warn "CF tunnel is already running: PID $(cat "${TUNNEL_PID_FILE}")"
    return 0
  fi

  if [ ! -x "${CLOUDFLARED_BIN}" ]; then
    install_cloudflared || return 1
  fi

  say "Starting temporary trycloudflare tunnel..."
  nohup "${CLOUDFLARED_BIN}" tunnel --no-autoupdate --url "http://127.0.0.1:${APP_PORT}" > "${TUNNEL_LOG}" 2>&1 &
  echo $! > "${TUNNEL_PID_FILE}"
  sleep 5

  if is_running "${TUNNEL_PID_FILE}"; then
    say "Temporary tunnel started: PID $(cat "${TUNNEL_PID_FILE}")"
    grep -Eo 'https://[-a-zA-Z0-9.]+\.trycloudflare\.com' "${TUNNEL_LOG}" | tail -n 1 || true
    info "Log: ${TUNNEL_LOG}"
  else
    err "Temporary tunnel failed to start, check log: ${TUNNEL_LOG}"
    tail -n 80 "${TUNNEL_LOG}" 2>/dev/null || true
    return 1
  fi
}

stop_tunnel() {
  stop_pid "${TUNNEL_PID_FILE}" "CF tunnel"
}

status_all() {
  load_config
  printf "%b\n" "${GREEN}Status${NC}"
  if is_running "${APP_PID_FILE}"; then
    say "App: RUNNING PID $(cat "${APP_PID_FILE}")"
  else
    warn "App: STOPPED"
  fi

  if is_running "${TUNNEL_PID_FILE}"; then
    say "Tunnel: RUNNING PID $(cat "${TUNNEL_PID_FILE}")"
  else
    warn "Tunnel: STOPPED"
  fi

  printf "Directory: %s\n" "${BASE_DIR}"
  printf "Entry: %s\n" "${SRC_DIR}/${APP_ENTRY}"
  printf "Port: %s\n" "${APP_PORT}"
}

show_logs() {
  printf "%b\n" "${GREEN}Select log${NC}"
  printf "1. App log\n"
  printf "2. Tunnel log\n"
  printf "Select: "
  read -r choice
  case "${choice}" in
    1)
      tail -n 120 "${APP_LOG}" 2>/dev/null || warn "No app log yet."
      ;;
    2)
      tail -n 120 "${TUNNEL_LOG}" 2>/dev/null || warn "No tunnel log yet."
      ;;
    *)
      warn "Cancelled."
      ;;
  esac
}

deploy_all() {
  configure_project || return 1
  download_project || return 1
  install_deps || return 1
  start_app || return 1
  printf "%b" "${YELLOW}Start Cloudflare Tunnel? [y/N]: ${NC}"
  read -r answer
  case "${answer}" in
    y|Y|yes|YES)
      start_tunnel
      ;;
    *)
      warn "Skipped CF tunnel."
      ;;
  esac
}

menu() {
  clear 2>/dev/null || true
  printf "%b\n" "${GREEN}========================================${NC}"
  printf "%b\n" "${GREEN} Python App Green Launcher${NC}"
  printf "%b\n" "${GREEN}========================================${NC}"
  printf "Directory: %s\n" "${BASE_DIR}"
  printf "\n"
  printf "1. Configure project\n"
  printf "2. Download/update project ZIP\n"
  printf "3. Install Python dependencies\n"
  printf "4. Start app in background\n"
  printf "5. Stop app\n"
  printf "6. Install cloudflared\n"
  printf "7. Start CF tunnel (token not saved)\n"
  printf "8. Start temporary trycloudflare tunnel\n"
  printf "9. Stop CF tunnel\n"
  printf "10. Show status\n"
  printf "11. Show logs\n"
  printf "12. One-click deploy and start\n"
  printf "0. Exit\n"
  printf "\nSelect: "
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
    *) warn "Invalid choice."; pause ;;
  esac
done
