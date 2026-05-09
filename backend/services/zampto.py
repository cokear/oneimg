# -*- coding: utf-8 -*-
"""
Zampto Auto Renewal - 基于 SeleniumBase UC 模式
支持 Cookie 持久化：优先使用 cookie 登录，失败再用账号密码
登录页: https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl
"""

import time
import os
import sys
import re
import json
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

from datetime import datetime
from seleniumbase import SB
from selenium.webdriver.common.by import By
from cf_turnstile_helper import (
    click_screen_point,
    get_window_metrics_js,
    handle_cloudflare_if_present,
    is_turnstile_present,
    is_turnstile_solved,
)


TG_CHAT_ID = (os.environ.get("TG_CHAT_ID") or os.environ.get("CHAT_ID") or "").strip()
TG_TOKEN = (
    os.environ.get("TG_BOT_TOKEN")
    or os.environ.get("TG_TOKEN")
    or os.environ.get("BOT_TOKEN")
    or ""
).strip()
TASK_RESULT_PATH = os.environ.get("TASK_RESULT_PATH", "").strip()
TASK_SCREENSHOT_PATH = os.environ.get("TASK_SCREENSHOT_PATH", "").strip()
ENTRY_CF_AUTO_HANDLE = str(os.environ.get("ZAMPTO_ENTRY_CF_AUTO_HANDLE", "0")).strip().lower() in ("1", "true", "yes", "on")
POST_CLICK_WAIT_SEC = max(10, int(float(os.environ.get("ZAMPTO_POST_CLICK_WAIT_SEC", "40"))))
POST_CLICK_READY_HITS = max(1, int(os.environ.get("ZAMPTO_POST_CLICK_READY_HITS", "2")))

USER_ENV_FILE = str(Path.home() / ".config" / "browser-automation-panel" / "scripts.env")


def _load_env_file(env_file_path: str):
    """最小化 .env 解析（KEY=VALUE，支持 export/引号），不会覆盖已有环境变量。"""
    path = Path(env_file_path)
    try:
        if not path.exists():
            print(f"ℹ️ 未找到配置文件: {env_file_path}")
            return False
        loaded_any = False
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
                if "=" not in line:
                    continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if len(value) >= 2 and ((value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")):
                value = value[1:-1]
            os.environ.setdefault(key, value)
            loaded_any = True
        if loaded_any:
            print(f"ℹ️ 已读取配置文件: {env_file_path}")
        else:
            print(f"⚠️ 配置文件可读但未解析到变量: {env_file_path}")
        return loaded_any
    except PermissionError:
        print(f"⚠️ 无权限读取 env 文件，已跳过: {env_file_path}")
        return False
    except Exception as exc:
        print(f"⚠️ 读取 env 文件失败: {env_file_path} -> {exc}")
        return False


def _resolve_accounts_from_json():
    """
    多账号解析：
    - 优先读取 ZAMPTO_ACCOUNTS_JSON
    - 其次读取 ZAMPTO_ACCOUNTS_FILE 指向的 JSON 文件
    - 通过 BROWSER_USER_DATA_DIR 匹配当前账号
    返回 (target_url, username, password)；匹配不到则返回 (None, None, None)
    """
    user_data_dir = (os.environ.get("BROWSER_USER_DATA_DIR") or "").strip()
    profile_name = (os.environ.get("BROWSER_PROFILE_NAME") or "").strip()
    raw_json = (os.environ.get("ZAMPTO_ACCOUNTS_JSON") or "").strip()
    accounts_file = (os.environ.get("ZAMPTO_ACCOUNTS_FILE") or "").strip()
    payload = None

    if raw_json:
        try:
            payload = json.loads(raw_json)
        except Exception as exc:
            print(f"⚠️ ZAMPTO_ACCOUNTS_JSON 解析失败: {exc}")
            payload = None
    elif accounts_file:
        try:
            payload = json.loads(Path(accounts_file).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"⚠️ ZAMPTO_ACCOUNTS_FILE 读取失败: {accounts_file} -> {exc}")
            payload = None

    if not payload:
        return None, None, None

    def _norm_path(v: str) -> str:
        s = str(v or "").strip().replace("\\", "/")
        while "//" in s:
            s = s.replace("//", "/")
        if len(s) > 1 and s.endswith("/"):
            s = s[:-1]
        return s

    user_data_dir_norm = _norm_path(user_data_dir)

    picked = None
    picked_source = ""
    if isinstance(payload, dict):
        # 1) 先用原始路径精确匹配
        if user_data_dir and user_data_dir in payload:
            picked = payload.get(user_data_dir)
            picked_source = f"dict.exact:{user_data_dir}"
        # 2) 再做路径归一化匹配（防止多余斜杠/尾斜杠）
        if picked is None and user_data_dir_norm:
            for k, v in payload.items():
                if _norm_path(k) == user_data_dir_norm:
                    picked = v
                    picked_source = f"dict.norm:{k}"
                    break
        # 3) 支持 profile_name 兜底
        if picked is None and profile_name and profile_name in payload:
            picked = payload.get(profile_name)
            picked_source = f"dict.profile:{profile_name}"
        elif "__default__" in payload:
            picked = payload.get("__default__")
            picked_source = "dict.__default__"
    elif isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            item_dir = str(item.get("user_data_dir") or "").strip()
            if user_data_dir and item_dir and item_dir == user_data_dir:
                picked = item
                picked_source = f"list.exact:{item_dir}"
                break
            if user_data_dir_norm and item_dir and _norm_path(item_dir) == user_data_dir_norm:
                picked = item
                picked_source = f"list.norm:{item_dir}"
                break
            item_profile = str(item.get("profile_name") or item.get("profile") or "").strip()
            if profile_name and item_profile and item_profile == profile_name:
                picked = item
                picked_source = f"list.profile:{item_profile}"
                break
        if picked is None:
            for item in payload:
                if isinstance(item, dict) and item.get("default"):
                    picked = item
                    picked_source = "list.default:true"
                    break

    if not isinstance(picked, dict):
        print(
            "⚠️ 多账号配置存在，但未匹配账号。"
            f" user_data_dir={user_data_dir or '(空)'}"
            f" profile_name={profile_name or '(空)'}"
        )
        return None, None, None

    username = str(picked.get("username") or picked.get("user") or "").strip()
    password = str(picked.get("password") or picked.get("pass") or "").strip()
    target_url = str(picked.get("target_url") or picked.get("url") or "").strip()
    masked_user = f"{username[:2]}***" if username else "(empty)"
    print(
        "ℹ️ 多账号匹配成功:"
        f" source={picked_source or '(unknown)'}"
        f" user={masked_user}"
        f" target={target_url or '(empty)'}"
    )
    if not username or not password:
        print("⚠️ 已匹配账号项，但缺少 username/password，回退单账号环境变量")
        return None, None, None
    return target_url or None, username, password


def login_form_visible(sb) -> bool:
    selectors = [
        "input[name='identifier']",
        "input[name='Password']",
        "input[type='password']",
        "input[name='password']",
    ]
    for sel in selectors:
        try:
            if sb.is_element_visible(sel):
                return True
        except Exception:
            continue
    return False


def send_tg_photo(photo_path, caption=""):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️ TG 未配置，跳过图片推送")
        return
    if not os.path.exists(photo_path):
        print(f"⚠️ TG 图片不存在，跳过推送: {photo_path}")
        return

    boundary = "----ZamptoDebugBoundary"
    try:
        with open(photo_path, "rb") as f:
            file_bytes = f.read()

        body = []
        for name, value in (("chat_id", TG_CHAT_ID), ("caption", caption)):
            body.append(f"--{boundary}\r\n".encode())
            body.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"))
        body.append(f"--{boundary}\r\n".encode())
        body.append(f'Content-Disposition: form-data; name="photo"; filename="{os.path.basename(photo_path)}"\r\n'.encode("utf-8"))
        body.append(b"Content-Type: image/png\r\n\r\n")
        body.append(file_bytes)
        body.append(f"\r\n--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
            data=b"".join(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30):
            print(f"📷 TG 图片推送成功: {os.path.basename(photo_path)}")
    except Exception as e:
        print(f"⚠️ TG 图片推送失败：{e}")


def send_tg_message(text: str):
    """纯文本 Telegram 推送（兼容 GitHub 常见 sendMessage 用法）"""
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️ TG 未配置，跳过文本推送")
        return
    message = (text or "").strip()
    if not message:
        return
    try:
        payload = urllib.parse.urlencode(
            {
                "chat_id": TG_CHAT_ID,
                "text": message,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30):
            print("📨 TG 文本推送成功")
    except Exception as e:
        print(f"⚠️ TG 文本推送失败：{e}")


def write_task_result(ok: bool, error: str = "", screenshot_path: str = ""):
    if not TASK_RESULT_PATH:
        return
    payload = {"ok": bool(ok)}
    if screenshot_path:
        payload["screenshotPath"] = screenshot_path
    if error:
        payload["error"] = error
    try:
        result_file = Path(TASK_RESULT_PATH)
        result_file.parent.mkdir(parents=True, exist_ok=True)
        result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"⚠️ 写 TASK_RESULT_PATH 失败: {exc}", flush=True)


def export_task_screenshot(source_path: str):
    if not TASK_SCREENSHOT_PATH:
        return
    try:
        source = Path(source_path)
        if not source.exists():
            return
        target = Path(TASK_SCREENSHOT_PATH)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(source), str(target))
    except Exception as exc:
        print(f"⚠️ 写 TASK_SCREENSHOT_PATH 失败: {exc}", flush=True)


def read_renewal_result_text(file_path="renewal_result.txt") -> str:
    try:
        p = Path(file_path)
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


class RenewalHandler:
    def __init__(self, output_dir="artifacts"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir = self.output_dir
        self.login_url = "https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl"

    def log(self, msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

    def _debug_screenshot(self, sb, filename, caption):
        path = str(self.screenshot_dir / filename)
        try:
            sb.save_screenshot(path)
            self.log(f"📸 调试截图已保存: {path}")
        except Exception as e:
            self.log(f"⚠️ 调试截图保存失败: {e}")
        send_tg_photo(path, caption=caption)

    def _wait_for_login_form(self, sb, rounds=5, round_wait=60):
        self.log(f"登录表单不可见，进入整页挑战静默等待：每轮 {round_wait}s，最多 {rounds} 轮...")

        for round_index in range(rounds):
            self.log(f"第 {round_index + 1}/{rounds} 轮：等待登录表单出现...")

            for second in range(round_wait):
                self._handle_cookie_consent(sb)
                if login_form_visible(sb):
                    self.log(f"✅ 登录表单已出现 (第 {round_index + 1} 轮，第 {second}s)")
                    return True
                time.sleep(1)

            self._debug_screenshot(
                sb,
                f"login_page_before_refresh_{round_index + 1}.png",
                f"Zampto 登录页等待第 {round_index + 1}/{rounds} 轮结束，准备刷新 | URL: {sb.get_current_url()} | Title: {sb.get_title()}",
            )

            if round_index < rounds - 1:
                self.log(f"⚠️ 本轮等待 {round_wait}s 仍未进入登录页，刷新网页重试 ({round_index + 1}/{rounds})")
                try:
                    sb.refresh()
                except Exception as e:
                    self.log(f"刷新登录页失败: {e}")
                    return False
                time.sleep(3)

        self.log("❌ 等待结束后仍未看到登录表单")
        self._debug_screenshot(
            sb,
            "login_page_not_ready.png",
            f"Zampto 登录页最终仍未就绪 | URL: {sb.get_current_url()} | Title: {sb.get_title()}",
        )
        return False

    def _is_challenge_title(self, title_text: str) -> bool:
        t = (title_text or "").strip().lower()
        if not t:
            return False
        keys = [
            "just a moment",
            "please wait",
            "checking your browser",
            "verify you are human",
            "请稍候",
            "稍候",
        ]
        return any(k in t for k in keys)

    def _is_dashboard_ready(self, sb) -> bool:
        """判断是否已进入可操作的服务详情页（而不是挑战/登录中间态）"""
        try:
            return bool(
                sb.execute_script(
                    """
                    (function() {
                        var renewBtn = document.querySelector("a[onclick*='handleServerRenewal'],a.action-button,button");
                        var hasExpiry = false;
                        var nodes = document.querySelectorAll("div,span,p,td,th");
                        for (var i = 0; i < nodes.length; i++) {
                            var txt = (nodes[i].innerText || nodes[i].textContent || '').trim().toLowerCase();
                            if (txt === 'expiry' || txt.indexOf('expiry') >= 0) {
                                hasExpiry = true;
                                break;
                            }
                        }
                        return !!renewBtn && hasExpiry;
                    })()
                    """
                )
            )
        except Exception:
            return False

    def _wait_target_page_ready(self, sb, timeout=45):
        """
        等待目标页就绪：
        - login: 回到登录页
        - ready: 服务详情页可操作
        - unknown: 超时仍未可用
        """
        waited = 0
        while waited < timeout:
            try:
                curr_title = sb.get_title() or ""
                if login_form_visible(sb):
                    return "login"
                if self._is_challenge_title(curr_title):
                    self.log(f"⏳ 页面仍在挑战态: {curr_title}")
                    if ENTRY_CF_AUTO_HANDLE:
                        self._handle_cloudflare_with_retry(sb, wait_appear_sec=10, rounds=1)
                elif self._is_dashboard_ready(sb):
                    return "ready"
            except Exception:
                pass
            time.sleep(1)
            waited += 1
        return "unknown"

    def run(self, url, username, password, proxy=None):
        print("=" * 40)
        print("  ZAMPTO AUTO RENEWAL (Strongest Mode)")
        print("=" * 40)

        self.log(f"启动任务: {url}")
        self.log(f"登录页: {self.login_url}")
        if proxy:
            self.log(f"使用代理: {proxy}")

        try:
            chrome_path = (os.environ.get("BROWSER_CHROME_PATH") or "").strip()
            user_data_dir = (os.environ.get("BROWSER_USER_DATA_DIR") or "").strip()
            browser_locale = (os.environ.get("BROWSER_LOCALE") or "").strip()

            # SeleniumBase 对 proxy 参数通常使用 host:port 形式。
            # 同时额外加 --proxy-server 作为兜底，避免 UC 模式下配置被覆盖。
            sb_proxy = (proxy or "").strip()
            for prefix in ("socks5h://", "socks5://", "https://", "http://"):
                if sb_proxy.lower().startswith(prefix):
                    sb_proxy = sb_proxy[len(prefix):]
                    break

            sb_args = {
                "uc": True,
                "test": True,
                "headed": True,
                "locale": "en",
            }
            if sb_proxy:
                sb_args["proxy"] = sb_proxy
            if chrome_path:
                sb_args["binary_location"] = chrome_path
            if user_data_dir:
                sb_args["user_data_dir"] = user_data_dir
            if browser_locale:
                sb_args["locale_code"] = browser_locale

            chromium_args = []
            if proxy:
                chromium_args.append(f"--proxy-server={proxy}")
            if browser_locale:
                chromium_args.append(f"--lang={browser_locale}")
            if chromium_args:
                sb_args["chromium_arg"] = ",".join(chromium_args)

            self.log(f"SB_PROXY(规范化): {sb_proxy or '(空)'}")
            self.log(f"BROWSER_USER_DATA_DIR: {user_data_dir or '(空)'}")
            self.log(f"BROWSER_CHROME_PATH: {chrome_path or '(空)'}")
            self.log(f"BROWSER_LOCALE: {browser_locale or '(空)'}")

            with SB(**sb_args) as sb:
                self.log("浏览器启动成功")

                # IP 检查 (确认代理是否工作)
                try:
                    self.log("检查出口 IP...")
                    sb.open("https://api.ipify.org/?format=json")
                    ip_info = sb.get_text("body")
                    self.log(f"当前 IP: {ip_info}")
                except Exception as e:
                    self.log(f"IP 检查失败: {e}")

                # 优先直接进目标页，已登录则跳过登录流程
                if url:
                    self.log(f"优先尝试复用登录态，直接访问目标页: {url}")
                    sb.uc_open_with_reconnect(url, reconnect_time=5)
                    time.sleep(5)
                    self._handle_cookie_consent(sb)
                    time.sleep(1)
                else:
                    self.log("未提供目标页，先访问 auth 根域暖场")
                    sb.uc_open_with_reconnect("https://auth.zampto.net/", reconnect_time=5)
                    self.log("等待 auth 根域初始化 (10秒)...")
                    time.sleep(10)

                curr_url = (sb.get_current_url() or "").lower()
                self.log(f"当前页面: {sb.get_current_url()}")
                self.log(f"页面标题: {sb.get_title()}")

                if self._is_challenge_title(sb.get_title() or ""):
                    if ENTRY_CF_AUTO_HANDLE:
                        self.log("检测到挑战页标题，自动处理验证并等待页面就绪...")
                        self._handle_cloudflare_with_retry(sb, wait_appear_sec=45, rounds=2)
                    else:
                        self.log("检测到挑战页标题，已禁用自动处理，请手动完成验证...")

                page_state = self._wait_target_page_ready(sb, timeout=45)
                self.log(f"目标页就绪状态: {page_state}")
                if page_state == "unknown":
                    self.log("❌ 目标页长时间未就绪，终止本次任务")
                    self._debug_screenshot(
                        sb,
                        "target_not_ready.png",
                        f"Zampto 目标页未就绪 | URL: {sb.get_current_url()} | Title: {sb.get_title()}",
                    )
                    return False

                need_login = ("sign-in" in curr_url) or ("login" in curr_url) or login_form_visible(sb)
                if need_login:
                    self.log("检测到登录页或登录表单，进入登录流程...")
                    # 访问标准登录入口，避免非标准中间页导致元素不齐
                    if "sign-in" not in curr_url and "login" not in curr_url:
                        self.log(f"跳转到标准登录页: {self.login_url}")
                        sb.uc_open_with_reconnect(self.login_url, reconnect_time=5)
                        time.sleep(3)
                        self._handle_cookie_consent(sb)
                        time.sleep(1)

                    if not login_form_visible(sb):
                        if not self._wait_for_login_form(sb):
                            return False

                    if not self._login(sb, username, password):
                        self.log("❌ 登录失败，中止流程")
                        return False
                    self.log("✅ 登录成功，继续续期流程")

                    if url:
                        self.log(f"🛫 登录后跳转目标页: {url}")
                        sb.uc_open_with_reconnect(url, reconnect_time=5)
                        self.log("🛬 页面跳转指令已发出，等待渲染...")
                        time.sleep(5)
                else:
                    self.log("✅ 检测到已登录会话，跳过登录步骤")

                # 登录后常见“同意”弹窗，先处理掉避免挡住续期按钮
                self._handle_post_login_consent(sb, timeout=12)

                # 执行续期操作
                renewal_ok, result = self._do_renewal(sb)
                self.log(f"续期结果: {result}")
                with open("renewal_result.txt", "w", encoding="utf-8") as f:
                    f.write(result)
                if not renewal_ok:
                    self.log("❌ 续期未确认成功，本次任务判定为失败")
                    sb.save_screenshot(str(self.screenshot_dir / "renewal_not_confirmed.png"))
                    return False

                # 最终结果

                self.log(f"最终 URL: {sb.get_current_url()}")
                self.log(f"最终标题: {sb.get_title()}")
                sb.save_screenshot(str(self.screenshot_dir / "final_page.png"))

                self.log("任务执行完毕")
                return True

        except Exception as e:
            self.log(f"运行异常: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _detect_turnstile_type(self, sb):
        """[母版逻辑] 检测 Turnstile 类型"""
        try:
            return sb.execute_script("""
                (function() {
                    var iframes = document.querySelectorAll('iframe');
                    for (var i = 0; i < iframes.length; i++) {
                        var src = iframes[i].src || "";
                        if (src.includes("challenges.cloudflare.com") || src.includes("turnstile")) {
                            var rect = iframes[i].getBoundingClientRect();
                            if (rect.width > 50 && rect.height > 30) return "visible";
                        }
                    }
                    return "invisible";
                })()
            """)
        except Exception: return "visible"

    def _wait_turnstile_complete(self, sb, timeout=45):
        """[母版逻辑] 等待验证完成"""
        self.log(f"等待验证完成 (最多 {timeout}s)...")
        for i in range(timeout):
            if is_turnstile_solved(sb):
                self.log(f"✅ Token 已获取 ({i}s)")
                return "token"
            time.sleep(1)
        return "timeout"

    def _handle_cloudflare_mother(self, sb):
        """[母版逻辑] 专门用于续期的盾处理逻辑 (uc_gui_click_captcha)"""
        self._handle_cookie_consent(sb)
        page_source = sb.get_page_source().lower()
        if not (any(x in page_source for x in ["turnstile", "challenges.cloudflare", "verify you are human"]) or "Just a moment" in sb.get_title()):
            return

        time.sleep(3)
        ttype = self._detect_turnstile_type(sb)
        self.log(f"[母版] Turnstile 类型: {ttype}")

        if ttype == "visible":
            self.log("尝试母版 uc_gui_click_captcha...")
            try:
                sb.uc_gui_click_captcha()
                self.log("✅ 已点击验证")
            except Exception: pass
        
        self._wait_turnstile_complete(sb, 45)

    def _handle_cloudflare(self, sb):
        """直接调用 handle_turnstile (1:1 照抄 JustRunMy，登录步使用)"""
        self._handle_cookie_consent(sb)
        handle_cloudflare_if_present(sb)

    def _click_consent_button_js(self, sb):
        """在当前文档上下文里点击“同意/接受”按钮，返回按钮文本"""
        try:
            label = sb.execute_script(
                r"""
                (function() {
                    function visible(el) {
                        if (!el) return false;
                        var r = el.getBoundingClientRect();
                        var s = window.getComputedStyle(el);
                        return r.width > 20 && r.height > 16 && s.display !== 'none' && s.visibility !== 'hidden';
                    }
                    function norm(t) { return String(t || '').trim().toLowerCase().replace(/\s+/g, ''); }
                    var neg = ['不同意','拒绝','disagree','reject','deny'];
                    var pos = ['同意','接受','accept','agree','allow','允许','acceptall','全部同意'];

                    var cands = Array.from(document.querySelectorAll("button,[role='button'],a,input[type='button'],input[type='submit']"));
                    var best = null;
                    var score = -1;
                    for (var i = 0; i < cands.length; i++) {
                        var el = cands[i];
                        if (!visible(el)) continue;
                        var raw = (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
                        var t = norm(raw);
                        if (!t) continue;
                        if (neg.some(function(k){ return t.indexOf(k) >= 0; })) continue;
                        var s = 0;
                        if (t === '同意' || t === 'accept' || t === 'agree' || t === 'acceptall' || t === '全部同意') s = 100;
                        else if (pos.some(function(k){ return t.indexOf(k) >= 0; })) s = 70;
                        if (s > score) { score = s; best = el; }
                    }
                    if (best && score > 0) {
                        best.click();
                        return (best.innerText || best.textContent || best.value || best.getAttribute('aria-label') || '').trim() || 'clicked';
                    }
                    return '';
                })()
                """
            )
            return str(label or "").strip()
        except Exception:
            return ""

    def _handle_post_login_consent(self, sb, timeout=12):
        """
        登录后“同意”弹窗处理：
        - 先尝试当前页面
        - 再尝试 iframe（同源可切入）
        """
        end_at = time.time() + timeout
        while time.time() < end_at:
            hit = self._click_consent_button_js(sb)
            if hit:
                self.log(f"✅ 已处理同意弹窗: {hit}")
                time.sleep(1.0)
                return True

            try:
                frames = sb.driver.find_elements(By.TAG_NAME, "iframe")
            except Exception:
                frames = []

            for idx, frame in enumerate(frames[:10]):
                try:
                    sb.driver.switch_to.frame(frame)
                    hit = self._click_consent_button_js(sb)
                    sb.driver.switch_to.default_content()
                    if hit:
                        self.log(f"✅ 已在 iframe[{idx}] 处理同意弹窗: {hit}")
                        time.sleep(1.0)
                        return True
                except Exception:
                    try:
                        sb.driver.switch_to.default_content()
                    except Exception:
                        pass
                    continue

            time.sleep(0.8)
        return False

    def _wait_cf_appearance(self, sb, timeout=25, poll=1.0):
        """等待 Turnstile/挑战出现，兼容慢网络下延迟渲染"""
        waited = 0.0
        while waited < timeout:
            try:
                if is_turnstile_solved(sb):
                    self.log("✅ [cf] Token 已存在，跳过验证点击")
                    return "solved"
                if is_turnstile_present(sb):
                    self.log(f"🧩 [cf] 检测到 Turnstile 组件 (wait={waited:.1f}s)")
                    return "present"
                title = (sb.get_title() or "").lower()
                if "just a moment" in title or "verify" in title:
                    self.log(f"🧩 [cf] 检测到挑战页面标题 (wait={waited:.1f}s)")
                    return "present"
            except Exception:
                pass
            time.sleep(poll)
            waited += poll
        self.log(f"ℹ️ [cf] {timeout}s 内未检测到验证组件，继续后续流程")
        return "none"

    def _handle_cloudflare_with_retry(self, sb, wait_appear_sec=25, rounds=2):
        """
        续期阶段 Cloudflare 处理:
        - 先等待验证组件出现（慢网场景）
        - 再做有限轮次求解，避免无意义长卡
        """
        state = self._wait_cf_appearance(sb, timeout=wait_appear_sec, poll=1.0)
        if state == "solved":
            return True
        if state == "none":
            return False

        solved = False
        for i in range(rounds):
            self.log(f"[cf] 处理验证 round={i + 1}/{rounds}")
            try:
                solved = bool(handle_cloudflare_if_present(sb))
            except Exception as e:
                self.log(f"[cf] 验证处理异常: {e}")
                solved = False
            if solved or is_turnstile_solved(sb):
                self.log("✅ [cf] 验证已通过")
                return True
            if i < rounds - 1:
                time.sleep(2)
        self.log("⚠️ [cf] 验证未通过或未触发，继续观察结果")
        return False

    def _handle_cookie_consent(self, sb):
        """处理隐私/Cookie 同意弹窗 (母版逻辑)"""
        # 一些常见 CMP 的直接选择器优先点击
        direct_selectors = [
            "#onetrust-accept-btn-handler",
            "button#didomi-notice-agree-button",
            "button[aria-label*='Accept']",
            "button[aria-label*='同意']",
        ]
        for sel in direct_selectors:
            try:
                if sb.is_element_visible(sel):
                    sb.click(sel)
                    self.log(f"✅ 已点击 Cookie 同意选择器: {sel}")
                    time.sleep(1)
                    return
            except Exception:
                pass

        try:
            clicked = bool(
                sb.execute_script(r"""
                (function() {
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        var text = (buttons[i].textContent || '').trim().toLowerCase().replace(/\s+/g, '');
                        if (
                          text === 'consent' ||
                          text === 'accept' ||
                          text === 'agree' ||
                          text === 'acceptall' ||
                          text === '同意' ||
                          text === '我同意'
                        ) {
                            buttons[i].click();
                            return true;
                        }
                    }
                    // 兜底：按 aria/标题关键词匹配同意按钮
                    var all = document.querySelectorAll('button,[role="button"],a');
                    for (var j = 0; j < all.length; j++) {
                        var item = all[j];
                        var title = (item.getAttribute('aria-label') || item.getAttribute('title') || '').toLowerCase();
                        var txt = (item.textContent || '').toLowerCase().replace(/\s+/g, '');
                        if (
                          title.includes('accept') || title.includes('agree') ||
                          txt.includes('accept') || txt.includes('agree') ||
                          txt.includes('同意') || txt.includes('全部同意')
                        ) {
                            item.click();
                            return true;
                        }
                    }
                    return false;
                })()
                """)
            )
            if clicked:
                self.log("✅ 已点击 Cookie 同意")
                time.sleep(1)
        except Exception:
            pass

        # 二次兜底：专门针对图中这种 “同意/不同意/管理选项” 中文弹窗
        try:
            zh_clicked = bool(
                sb.execute_script(r"""
                (function() {
                    var cands = Array.from(document.querySelectorAll('button,[role="button"],a'));
                    function visible(el) {
                        if (!el) return false;
                        var r = el.getBoundingClientRect();
                        var s = window.getComputedStyle(el);
                        return r.width > 30 && r.height > 18 && s.visibility !== 'hidden' && s.display !== 'none';
                    }
                    for (var i = 0; i < cands.length; i++) {
                        var t = (cands[i].textContent || '').trim();
                        if (!visible(cands[i])) continue;
                        if (t === '同意' || t.indexOf('同意') >= 0 || t.indexOf('接受') >= 0) {
                            cands[i].click();
                            return true;
                        }
                    }
                    return false;
                })()
                """)
            )
            if zh_clicked:
                self.log("✅ 已点击中文同意按钮")
                time.sleep(1)
        except Exception:
            pass

    def _do_renewal(self, sb):
        """执行续期操作：点击 Renew Server -> 处理人机验证 -> 读取剩余时间"""
        self.log("开始续期操作...")
        # 二次兜底：续期前再清一次同意弹窗
        self._handle_post_login_consent(sb, timeout=6)

        # 记录运行时间
        run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 先读取当前剩余时间
        old_expiry = self._get_expiry_time(sb)
        self.log(f"当前剩余时间: {old_expiry or '未知'}")
        old_norm = self._normalize_expiry_text(old_expiry)

        # 1. 找到并点击续期按钮
        self.log("查找续期按钮...")
        btn_found = False
        try:
            btn_found = bool(
                sb.execute_script("""
                (function() {
                    var links = document.querySelectorAll('a[onclick*="handleServerRenewal"]');
                    for (var i = 0; i < links.length; i++) {
                        links[i].click();
                        return true;
                    }
                    var btns = document.querySelectorAll('a.action-button, button');
                    for (var j = 0; j < btns.length; j++) {
                        if (btns[j].textContent && btns[j].textContent.toLowerCase().includes('renew')) {
                            btns[j].click();
                            return true;
                        }
                    }
                    return false;
                })()
            """)
            )
        except Exception as e:
            self.log(f"点击按钮出错: {e}")

        if btn_found:
            self.log("✅ 已点击续期按钮")
        else:
            self.log("❌ 找不到续期按钮")
            sb.save_screenshot(str(self.screenshot_dir / "renew_button_not_found.png"))
            return False, f"🎮 Zampto 续期通知\n\n🕒 运行时间: {run_time}\n🖥️ 服务器: 🇩🇪 Zampto (Auto)\n📊 续期结果: ❌ 失败 (找不到按钮)\n🕒 旧到期: {old_expiry or '未知'}"

        # 2. 点击后先等待弹窗/验证真正渲染，避免慢网时抢跑
        post_click_state = self._wait_after_renew_click(
            sb,
            timeout=POST_CLICK_WAIT_SEC,
            stable_hits=POST_CLICK_READY_HITS,
        )
        cf_solved = bool(post_click_state.get("cf_solved"))
        if not cf_solved:
            cf_solved = bool(self._handle_cloudflare_with_retry(sb, wait_appear_sec=40, rounds=2))
        else:
            self.log("✅ [cf] 点击后检测到 Token 已存在，跳过首次验证处理")

        # 3. 等待页面刷新/结果（轮询，避免固定 sleep 误判）
        self.log("等待页面响应与到期时间更新 (最多 45 秒)...")
        deadline = time.time() + 45
        new_expiry = None
        expiry_changed = False
        saw_success_signal = False
        saw_failure_signal = False
        last_signal = {}
        while time.time() < deadline:
            last_signal = self._probe_renewal_outcome(sb)
            if last_signal.get("failure"):
                saw_failure_signal = True
                self.log(f"⚠️ 检测到失败信号: {last_signal.get('snippet') or 'unknown'}")
                break
            if last_signal.get("success"):
                saw_success_signal = True

            new_expiry = self._get_expiry_time(sb, verbose=False)
            new_norm = self._normalize_expiry_text(new_expiry)
            if new_norm:
                if old_norm and new_norm != old_norm:
                    # 再读一次做稳定确认，避免瞬时/抓错字段误判
                    time.sleep(1.2)
                    verify_expiry = self._get_expiry_time(sb, verbose=False)
                    verify_norm = self._normalize_expiry_text(verify_expiry)
                    if verify_norm and verify_norm != old_norm:
                        self.log(f"✅ 检测到到期时间稳定变化: {old_expiry} -> {verify_expiry}")
                        expiry_changed = True
                        break
                    self.log("ℹ️ 侦测到瞬时变化但未稳定，继续等待...")
                if not old_norm:
                    break
            # 挑战有时会慢出现；但若首次已 solved，不再重复解，避免误触发二次卡顿
            try:
                if (not cf_solved) and is_turnstile_present(sb) and not is_turnstile_solved(sb):
                    self.log("🧩 检测到延迟出现 Turnstile，补一次验证处理...")
                    cf_solved = bool(self._handle_cloudflare_with_retry(sb, wait_appear_sec=8, rounds=1)) or cf_solved
            except Exception:
                pass
            time.sleep(2)

        # 4. 读取新的剩余时间（最终读取，带日志）
        sb.save_screenshot(str(self.screenshot_dir / "renewal_result.png"))
        new_expiry = self._get_expiry_time(sb)
        self.log(f"续期后剩余时间: {new_expiry or '未知'}")
        new_norm = self._normalize_expiry_text(new_expiry)
        if not expiry_changed and old_norm and new_norm and new_norm != old_norm:
            expiry_changed = True

        final_signal = self._probe_renewal_outcome(sb)
        saw_success_signal = saw_success_signal or bool(final_signal.get("success"))
        saw_failure_signal = saw_failure_signal or bool(final_signal.get("failure"))
        modal_closed = not bool(final_signal.get("modal_open"))

        # 6. 多信号判定，避免仅凭 old/new 文本误判
        # 优先级：失败信号 > 到期变化 > 成功信号 > 验证通过且弹窗关闭
        if saw_failure_signal:
            renewal_ok = False
            verdict = "❌ 失败"
            reason = "检测到页面失败提示"
        elif expiry_changed:
            renewal_ok = True
            verdict = "✅ 成功"
            reason = "到期信息发生变化"
        elif saw_success_signal:
            renewal_ok = True
            verdict = "✅ 成功"
            reason = "检测到成功提示"
        elif cf_solved and modal_closed:
            renewal_ok = True
            verdict = "✅ 成功(弱确认)"
            reason = "验证已通过且续期弹窗已关闭"
        else:
            renewal_ok = False
            verdict = "⚠️ 未确认成功"
            reason = "无明确成功信号"

        self.log(
            f"续期判定细节: expiry_changed={expiry_changed}, "
            f"saw_success={saw_success_signal}, saw_failure={saw_failure_signal}, "
            f"cf_solved={cf_solved}, modal_closed={modal_closed}, reason={reason}"
        )

        # 5. 构建 XServer 风格通知
        status_icon = verdict

        msg = f"🎮 Zampto 续期通知\n\n"
        msg += f"🕒 运行时间: {run_time}\n"
        msg += f"🖥️ 服务器: 🇮🇹 Zampto (Auto)\n"
        msg += f"📊 续期结果: {status_icon}\n"
        msg += f"🕒 旧到期: {old_expiry or '未知'}\n"
        msg += f"🕒 新到期: {new_expiry or '未知'}\n"
        msg += f"🧪 判定依据: {reason}"

        return bool(renewal_ok), msg

    def _wait_after_renew_click(self, sb, timeout=25, stable_hits=2):
        """点击续期后等待弹窗/验证出现，防止慢网条件下抢跑。"""
        self.log(
            f"等待续期弹窗与验证组件加载 (最多 {timeout} 秒, 连续命中 {stable_hits} 次)..."
        )
        deadline = time.time() + timeout
        hit_count = 0
        while time.time() < deadline:
            probe = self._probe_renewal_outcome(sb)
            try:
                cf_present = bool(is_turnstile_present(sb))
                cf_solved = bool(is_turnstile_solved(sb))
            except Exception:
                cf_present = False
                cf_solved = False

            modal_open = bool(probe.get("modal_open"))
            ready_now = bool(modal_open or cf_present or cf_solved)
            if ready_now:
                hit_count += 1
            else:
                hit_count = 0

            if hit_count >= stable_hits:
                self.log(
                    f"续期界面已就绪: modal_open={modal_open}, "
                    f"cf_present={cf_present}, cf_solved={cf_solved}, stable_hits={hit_count}"
                )
                return {
                    "modal_open": modal_open,
                    "cf_present": cf_present,
                    "cf_solved": cf_solved,
                }

            time.sleep(0.8)

        self.log("ℹ️ 续期弹窗/验证组件未明确出现，继续后续流程")
        return {"modal_open": False, "cf_present": False, "cf_solved": False}

    def _probe_renewal_outcome(self, sb):
        """从页面可见提示里探测续期结果信号。"""
        try:
            data = sb.execute_script(
                r"""
                (function() {
                    function visible(el) {
                        if (!el) return false;
                        var r = el.getBoundingClientRect();
                        var s = window.getComputedStyle(el);
                        return r.width > 10 && r.height > 8 && s.display !== 'none' && s.visibility !== 'hidden';
                    }
                    function norm(t) { return String(t || '').replace(/\s+/g, ' ').trim(); }
                    function isSuccessText(t) {
                        var s = t.toLowerCase();
                        return (
                            s.indexOf('renew success') >= 0 ||
                            s.indexOf('renewed') >= 0 ||
                            s.indexOf('successfully') >= 0 ||
                            s.indexOf('续期成功') >= 0 ||
                            s.indexOf('已续期') >= 0 ||
                            s.indexOf('成功') >= 0
                        );
                    }
                    function isFailureText(t) {
                        var s = t.toLowerCase();
                        return (
                            s.indexOf('renew fail') >= 0 ||
                            s.indexOf('failed to renew') >= 0 ||
                            s.indexOf('error') >= 0 ||
                            s.indexOf('续期失败') >= 0 ||
                            s.indexOf('失败') >= 0
                        );
                    }

                    var selectors = [
                        '.alert',
                        '.toast',
                        '[role="alert"]',
                        '.swal2-popup',
                        '.notification',
                        '.message',
                        '#renew-modal'
                    ];
                    var nodes = [];
                    selectors.forEach(function(sel) {
                        document.querySelectorAll(sel).forEach(function(el) {
                            if (visible(el)) nodes.push(el);
                        });
                    });
                    if (nodes.length === 0 && document.body) nodes = [document.body];

                    var success = false;
                    var failure = false;
                    var snippet = '';
                    for (var i = 0; i < nodes.length; i++) {
                        var t = norm(nodes[i].innerText || nodes[i].textContent || '');
                        if (!t) continue;
                        if (!snippet) snippet = t.slice(0, 240);
                        if (isSuccessText(t)) success = true;
                        if (isFailureText(t)) failure = true;
                    }

                    var modal = document.querySelector('#renew-modal, .modal.show, [role="dialog"]');
                    var modalOpen = false;
                    if (modal) {
                        var rs = modal.getBoundingClientRect();
                        var ms = window.getComputedStyle(modal);
                        modalOpen = rs.width > 20 && rs.height > 20 && ms.display !== 'none' && ms.visibility !== 'hidden';
                    }
                    return { success: success, failure: failure, modal_open: modalOpen, snippet: snippet };
                })()
                """
            )
            if isinstance(data, dict):
                return data
            return {"success": False, "failure": False, "modal_open": False, "snippet": ""}
        except Exception:
            return {"success": False, "failure": False, "modal_open": False, "snippet": ""}

    def _normalize_expiry_text(self, value):
        """归一化到期文案，减少格式差异导致的误判"""
        if value is None:
            return ""
        text = str(value).strip().lower()
        if not text:
            return ""
        if not self._looks_like_expiry_text(text):
            return ""
        text = re.sub(r"\s+", " ", text)
        text = text.replace("days", "day").replace("hours", "h").replace("hour", "h")
        return text

    def _looks_like_expiry_text(self, value):
        """校验是否像合法到期时间文本，过滤脚本/样式噪声。"""
        text = str(value or "").strip().lower()
        if not text:
            return False

        # 明确排除脚本/CSS 片段
        bad_patterns = [
            r"document\.getelementbyid\s*\(",
            r"\bstyle\.display\b",
            r"\bfunction\s*\(",
            r"\bvar\s+\w+",
            r"\bconst\s+\w+",
            r"\blet\s+\w+",
            r"[{};]",
            r"\b\d+\s*px\b",
        ]
        for p in bad_patterns:
            if re.search(p, text, re.IGNORECASE):
                return False

        # 常见可接受格式
        good_patterns = [
            r"\b\d+\s*day[s]?\s*\d+\s*h\b",
            r"\b\d+\s*day[s]?\b",
            r"\b\d+\s*h\b",
            r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        ]
        for p in good_patterns:
            if re.search(p, text, re.IGNORECASE):
                return True

        return False

    def _get_expiry_time(self, sb, verbose=True):
        """读取 Expiry 时间，包含容错和调试信息"""
        try:
            # 优先走 DOM 标签-值关系定位，避免误抓脚本/样式文本
            dom_text = sb.execute_script(
                r"""
                (function() {
                    function txt(el){ return (el && (el.innerText || el.textContent) || '').trim(); }
                    function clean(s){ return String(s || '').replace(/\s+/g, ' ').trim(); }
                    function looksExpiry(v) {
                        var t = clean(v).toLowerCase();
                        if (!t) return false;
                        if (t.indexOf('document.getelementbyid(') >= 0) return false;
                        if (t.indexOf('style.display') >= 0) return false;
                        if (/[{};]/.test(t)) return false;
                        if (/\b\d+\s*px\b/i.test(t)) return false;
                        if (/\b\d+\s*day[s]?\b/i.test(t)) return true;
                        if (/\b\d+\s*h\b/i.test(t)) return true;
                        if (/\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b/.test(t)) return true;
                        if (/\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b/.test(t)) return true;
                        return false;
                    }

                    // 强优先：直接读取服务器页明确字段
                    var strong = document.querySelector('#nextRenewalTime');
                    if (strong) {
                        var sv = clean(txt(strong));
                        if (looksExpiry(sv)) return sv;
                    }

                    var nodes = document.querySelectorAll('div,span,p,td,th,strong,b,dt,label');
                    for (var i = 0; i < nodes.length; i++) {
                        var t = clean(txt(nodes[i])).toLowerCase();
                        if (t === 'expiry' || t.indexOf('expiry') >= 0) {
                            var cands = [];
                            if (nodes[i].nextElementSibling) {
                                cands.push(clean(txt(nodes[i].nextElementSibling)));
                            }
                            if (nodes[i].parentElement) {
                                var ch = nodes[i].parentElement.children;
                                for (var j = 0; j < ch.length; j++) {
                                    if (ch[j] === nodes[i]) continue;
                                    var tag = (ch[j].tagName || '').toUpperCase();
                                    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'TEMPLATE') continue;
                                    cands.push(clean(txt(ch[j])));
                                }
                                if (nodes[i].parentElement.nextElementSibling) {
                                    var nx = nodes[i].parentElement.nextElementSibling;
                                    var ntag = (nx.tagName || '').toUpperCase();
                                    if (!(ntag === 'SCRIPT' || ntag === 'STYLE' || ntag === 'NOSCRIPT' || ntag === 'TEMPLATE')) {
                                        cands.push(clean(txt(nx)));
                                    }
                                }
                            }
                            for (var k = 0; k < cands.length; k++) {
                                if (looksExpiry(cands[k])) return cands[k];
                            }
                        }
                    }
                    // 兜底：尝试常见 expiry 命名
                    var fallbacks = document.querySelectorAll(
                        '[data-expiry], #expiry, .expiry, [id*="expiry"], [class*="expiry"]'
                    );
                    for (var m = 0; m < fallbacks.length; m++) {
                        var fv = clean(txt(fallbacks[m]));
                        if (looksExpiry(fv) && fv.toLowerCase().indexOf('expiry') < 0) return fv;
                    }
                    return '';
                })()
                """
            )
            dom_text = str(dom_text or "").strip()
            if dom_text and self._looks_like_expiry_text(dom_text):
                m_day_h = re.search(r"(\d+)\s*day[s]?\s*(\d+)\s*h", dom_text, re.IGNORECASE)
                if m_day_h:
                    return f"{m_day_h.group(1)} day {m_day_h.group(2)}h"
                m_day = re.search(r"(\d+)\s*day[s]?\b", dom_text, re.IGNORECASE)
                if m_day:
                    return f"{m_day.group(1)} day"
                m_hour = re.search(r"(\d+)\s*h\b", dom_text, re.IGNORECASE)
                if m_hour:
                    return f"{m_hour.group(1)}h"
                return dom_text
            if dom_text and verbose:
                self.log(f"⚠️ 读取到疑似脏到期值，已忽略: {dom_text[:120]}")

            if verbose:
                self.log("⚠️ 无法读取剩余时间，打印源码片段调试:")
                page_text = sb.get_page_source()
                idx = page_text.find("Expiry")
                if idx != -1:
                    start = max(0, idx - 200)
                    end = min(len(page_text), idx + 500)
                    self.log(
                        f"--- Source Snippet ---\n{page_text[start:end]}\n----------------------"
                    )
                else:
                    self.log(
                        f"--- Full Source (First 500 chars) ---\n{page_text[:500]}\n----------------------"
                    )

            return None
        except Exception as e:
            self.log(f"读取时间出错: {e}")
            return None

    def _login(self, sb, username, password):
        """Zampto 两步登录：先输入邮箱 -> 点击登录 -> 再输入密码 -> 点击登录 (保持登录成功版点位)"""
        self.log(f"执行登录步骤，账号: {username[:3]}***")
        self._handle_cookie_consent(sb)

        # 登录页内可能有 Cloudflare 验证 (继续使用物理盾，因为它之前点开了)
        self._handle_cloudflare(sb)

        # 调试截图
        sb.save_screenshot(str(self.screenshot_dir / "debug_before_login.png"))
        self.log("已保存调试截图: debug_before_login.png")

        # ========== 第一步：输入邮箱 ==========
        self.log("第一步：输入邮箱...")
        try:
            sb.wait_for_element_visible("input[name='identifier']", timeout=20)
            sb.type("input[name='identifier']", username)
            self.log("✅ 邮箱已输入")
        except Exception as e:
            self.log(f"找不到邮箱输入框: {e}")
            sb.save_screenshot(str(self.screenshot_dir / "login_fail_no_email.png"))
            return False

        # 点击第一步的登录按钮
        self.log("点击登录按钮 (第一步)...")
        try:
            sb.click("button[type='submit']")
            self.log("✅ 第一步按钮已点击")
        except Exception as e:
            self.log(f"第一步按钮点击失败: {e}")
            return False

        # 等待密码框出现 (转场动画加固)
        self.log("等待密码框出现 (最多 15s)...")
        try:
            pwd_sel = "input[name='Password'], input[type='password'], input[name='password']"
            sb.wait_for_element_visible(pwd_sel, timeout=15)
            self.log("✅ 密码框已就位")
            
            # 处理转场中可能浮现的 Cloudflare
            self._handle_cloudflare(sb)

            # ========== 第二步：输入密码 ==========
            self.log("第二步：输入密码...")
            sb.type(pwd_sel, password)
            self.log("✅ 密码已输入")
            
            sb.click("button[type='submit']")
            self.log("✅ 第二步按钮已点击")
        except Exception as e:
            self.log(f"第二步执行失败: {e}")
            sb.save_screenshot(str(self.screenshot_dir / "login_fail_step2.png"))
            return False

        # === 终极检查：通过后再检测一次盾 ===
        time.sleep(2)
        handle_cloudflare_if_present(sb)

        # 等待登录完成
        self.log("等待登录完成 (10秒)...")
        time.sleep(10)

        # 判定最终 URL
        curr_url = sb.get_current_url().lower()
        if "sign-in" not in curr_url and "login" not in curr_url:
            self.log("✅ 登录成功！")
            
            # --- 新增：处理可能出现的社交弹窗 (Social Prompt) ---
            self._handle_social_prompt(sb)
            
            return True
        else:
            self.log("⚠️ 可能登录失败，仍在登录页")
            return False

    def _handle_social_prompt(self, sb):
        """处理登录后的引导弹窗 (Social Prompt) - 物理级混合打击版"""
        self.log("检查是否存在社交引导弹窗 (Social Prompt)...")
        try:
            # 1. 精准获取按钮物理坐标
            coords = sb.execute_script("""
                (function() {
                    var b = document.querySelector('button.continue-btn') || 
                            Array.from(document.querySelectorAll('button')).find(el => el.textContent.includes('Continue'));
                    if (!b) return null;
                    var r = b.getBoundingClientRect();
                    return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                })()
            """)
            
            if coords:
                self.log(f"🎯 发现弹窗按钮坐标: ({coords['x']}, {coords['y']})，准备强力清除...")
                
                # 盲拍点击前的证据
                sb.save_screenshot(str(self.screenshot_dir / "social_pre_click.png"))
                
                # 战术 A：物理坐标打击 (xdotool) - 越过浏览器引擎直接点击
                try:
                    wi = sb.execute_script(get_window_metrics_js())
                    bar = wi["oh"] - wi["ih"]
                    ax = coords["x"] + wi["sx"]
                    ay = coords["y"] + wi["sy"] + bar
                    self.log(f"   -- 物理开火: xdotool click at ({ax}, {ay})")
                    click_screen_point(ax, ay)
                    time.sleep(0.5)
                except Exception: pass
                
                # 战术 B：极简 JS 注入点击 (非阻塞)
                try:
                    self.log("   -- 混合开火: 强制注入原生 JS 点击")
                    sb.execute_script("var b = document.querySelector('button.continue-btn'); if(b) b.click();")
                except Exception: pass
                
                time.sleep(3)
                
                # 盲拍点击后的结果
                sb.save_screenshot(str(self.screenshot_dir / "social_post_click.png"))
                self.log("✅ 弹窗处理指令执行完毕")
                return True
                
        except Exception as e:
            self.log(f"处理社交弹窗时发生非致命异常 (可能已自动消失): {e}")
        return False

if __name__ == "__main__":
    # 只读取当前运行用户目录，默认不再尝试 /root 路径
    user_loaded = _load_env_file(USER_ENV_FILE)
    env_file_from_var = (os.environ.get("ZAMPTO_ENV_FILE") or "").strip()
    if env_file_from_var and env_file_from_var != USER_ENV_FILE:
        _load_env_file(env_file_from_var)
    elif not user_loaded:
        print("⚠️ 未加载到外部配置文件，将仅使用当前进程环境变量")

    # TG_* lives in scripts.env for panel-launched runs, so refresh after env files load.
    TG_CHAT_ID = (os.environ.get("TG_CHAT_ID") or os.environ.get("CHAT_ID") or "").strip()
    TG_TOKEN = (
        os.environ.get("TG_BOT_TOKEN")
        or os.environ.get("TG_TOKEN")
        or os.environ.get("BOT_TOKEN")
        or ""
    ).strip()

    # 先尝试多账号映射，再回退单账号变量
    target_url, username, password = _resolve_accounts_from_json()
    if not username or not password:
        target_url = target_url or os.environ.get("ZAMPTO_TARGET_URL")
        username = os.environ.get("ZAMPTO_USERNAME")
        password = os.environ.get("ZAMPTO_PASSWORD")
    proxy = (os.environ.get("BROWSER_PROXY") or os.environ.get("ZAMPTO_PROXY") or "").strip()

    if not username or not password:
        print("错误: 缺少 ZAMPTO_USERNAME 或 ZAMPTO_PASSWORD 环境变量")
        write_task_result(False, "缺少 ZAMPTO_USERNAME 或 ZAMPTO_PASSWORD 环境变量")
        sys.exit(1)

    handler = RenewalHandler()
    try:
        ok = handler.run(target_url, username, password, proxy)
        final_shot = str(handler.screenshot_dir / "final_page.png")
        export_task_screenshot(final_shot)
        result_message = read_renewal_result_text("renewal_result.txt")
        if not result_message:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if ok:
                result_message = (
                    "🎮 Zampto 续期通知\n\n"
                    f"🕒 运行时间: {now_str}\n"
                    "🖥️ 服务器: 🇮🇹 Zampto (Auto)\n"
                    "📊 续期结果: ✅ 成功\n"
                    "🕒 详情: 未生成 renewal_result.txt"
                )
            else:
                result_message = (
                    "🎮 Zampto 续期通知\n\n"
                    f"🕒 运行时间: {now_str}\n"
                    "🖥️ 服务器: 🇮🇹 Zampto (Auto)\n"
                    "📊 续期结果: ❌ 失败\n"
                    "🕒 原因: run() returned False"
                )
        send_tg_message(result_message)
        if ok:
            write_task_result(True, screenshot_path=TASK_SCREENSHOT_PATH or final_shot)
            sys.exit(0)
        write_task_result(False, "run() returned False", screenshot_path=TASK_SCREENSHOT_PATH or final_shot)
        sys.exit(1)
    except Exception as exc:
        final_shot = str(handler.screenshot_dir / "final_page.png")
        export_task_screenshot(final_shot)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fail_msg = (
            "🎮 Zampto 续期通知\n\n"
            f"🕒 运行时间: {now_str}\n"
            "🖥️ 服务器: 🇮🇹 Zampto (Auto)\n"
            "📊 续期结果: ❌ 失败\n"
            f"🕒 异常: {str(exc)[:240]}"
        )
        send_tg_message(fail_msg)
        write_task_result(False, f"未捕获异常: {exc}", screenshot_path=TASK_SCREENSHOT_PATH or final_shot)
        raise





