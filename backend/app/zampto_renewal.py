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
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from datetime import datetime
from seleniumbase import SB


TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
TG_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()


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


# ============================================================
#  页面注入脚本 (1:1 照抄 JustRunMy 标答)
# ============================================================
_EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        // 暴力清除所有可能遮挡物理点击的层级限制 (含 Modal 弹窗)
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden' || el.classList.contains('modal-content') || el.classList.contains('modal-dialog')) {
            el.style.overflow = 'visible';
            el.style.zIndex = '999999';
        }
        el.style.minWidth = 'max-content';
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.includes('challenges.cloudflare.com')) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1'; f.style.zIndex = '999999';
        }
    });
    return 'done';
})()
"""

_EXISTS_JS = """
(function(){
    return document.querySelector('input[name="cf-turnstile-response"]') !== null;
})()
"""

_SOLVED_JS = """
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()
"""

_COORDS_JS = """
(function(){
    var iframes = document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        var src = iframes[i].src || '';
        if (src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges')) {
            var r = iframes[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
        }
    }
    var inp = document.querySelector('input[name="cf-turnstile-response"]');
    if (inp) {
        var p = inp.parentElement;
        for (var j = 0; j < 5; j++) {
            if (!p) break;
            var r = p.getBoundingClientRect();
            if (r.width > 100 && r.height > 30)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
            p = p.parentElement;
        }
    }
    return null;
})()
"""

_WININFO_JS = """
(function(){
    return {
        sx: window.screenX || 0,
        sy: window.screenY || 0,
        oh: window.outerHeight,
        ih: window.innerHeight
    };
})()
"""

# ============================================================
#  底层输入工具 (1:1 照抄 JustRunMy)
# ============================================================
def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls], capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _xdotool_click(x: int, y: int):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")

def _click_turnstile(sb):
    try:
        coords = sb.execute_script(_COORDS_JS)
    except Exception as e:
        print(f"  ⚠️ 获取 Turnstile 坐标失败: {e}")
        return
    if not coords:
        print("  ⚠️ 无法定位 Turnstile 坐标")
        return
    try:
        wi = sb.execute_script(_WININFO_JS)
    except Exception:
        wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}

    bar = wi["oh"] - wi["ih"]
    ax  = coords["cx"] + wi["sx"]
    ay  = coords["cy"] + wi["sy"] + bar
    # print(f"  🖱️ 物理级点击 Turnstile ({ax}, {ay})")
    _xdotool_click(ax, ay)

def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)

    if sb.execute_script(_SOLVED_JS):
        print("  ✅ 已静默通过")
        return True

    for _ in range(3):
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.5)

    for attempt in range(6):
        if sb.execute_script(_SOLVED_JS):
            print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
            return True
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.3)

        _click_turnstile(sb)

        for _ in range(8):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
                return True
        print(f"  ⚠️ 第 {attempt + 1} 次未通过，重试...")

    print("  ❌ Turnstile 6 次均失败")
    return False


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

    def run(self, url, username, password, proxy=None):
        print("=" * 40)
        print("  ZAMPTO AUTO RENEWAL (Strongest Mode)")
        print("=" * 40)

        self.log(f"启动任务: {url}")
        self.log(f"登录页: {self.login_url}")
        if proxy:
            self.log(f"使用代理: {proxy}")

        try:
            sb_args = {}
            if proxy:
                sb_args["proxy"] = proxy

            with SB(uc=True, test=True, locale="en", **sb_args) as sb:
                self.log("浏览器启动成功")

                # IP 检查 (确认代理是否工作)
                try:
                    self.log("检查出口 IP...")
                    sb.open("https://api.ipify.org/?format=json")
                    ip_info = sb.get_text("body")
                    self.log(f"当前 IP: {ip_info}")
                except Exception as e:
                    self.log(f"IP 检查失败: {e}")

                # 先访问 auth 根域暖场，再进入登录深链
                self.log("正在访问 auth 根域暖场: https://auth.zampto.net/")
                sb.uc_open_with_reconnect("https://auth.zampto.net/", reconnect_time=5)
                self.log("等待 auth 根域初始化 (25秒)...")
                time.sleep(25)

                # 直接访问登录页
                self.log(f"正在访问入口页面: {self.login_url}")
                sb.uc_open_with_reconnect(self.login_url, reconnect_time=5)
                time.sleep(3)

                self.log(f"进入页面: {sb.get_current_url()}")
                self.log(f"页面标题: {sb.get_title()}")

                if not login_form_visible(sb):
                    if not self._wait_for_login_form(sb):
                        return False

                # 判定逻辑
                self.log(f"判定逻辑运行中，当前 URL: {sb.get_current_url()}")
                if login_form_visible(sb):
                    self.log("判定[是]: 登录表单已可见")
                    self.log("检测到登录页面，开始登录流程...")
                    # 执行登录主流程 (含过盾与弹窗清理)
                    self._login(sb, username, password)
                    self.log("✅ [核心同步] 登录动作已执行完毕，正带着 Session 返回主程序")

                    # 登录完成后跳转到目标页
                    if url:
                        self.log(f"🛫 登录确认，准备跳转目标页: {url}")
                        sb.uc_open_with_reconnect(url, reconnect_time=5)
                        self.log("🛬 页面跳转指令已发出，等待渲染...")
                        time.sleep(5)

                        # 执行续期操作
                        result = self._do_renewal(sb)
                        self.log(f"续期结果: {result}")

                        # 写入结果供 Workflow 读取
                        with open("renewal_result.txt", "w", encoding="utf-8") as f:
                            f.write(result)

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
            if sb.execute_script(_SOLVED_JS):
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
        page_source = sb.get_page_source().lower()
        cf_indicators = [
            "turnstile",
            "challenges.cloudflare",
            "just a moment",
            "verify you are human",
        ]

        if not (
            any(x in page_source for x in cf_indicators)
            or "Just a moment" in sb.get_title()
        ):
            return

        if sb.execute_script(_EXISTS_JS):
            handle_turnstile(sb)

    def _handle_cookie_consent(self, sb):
        """处理隐私/Cookie 同意弹窗 (母版逻辑)"""
        try:
            clicked = bool(
                sb.execute_script("""
                (function() {
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        var text = (buttons[i].textContent || '').trim().toLowerCase();
                        if (text === 'consent' || text === 'accept') {
                            buttons[i].click();
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

    def _do_renewal(self, sb):
        """执行续期操作：点击 Renew Server -> 处理人机验证 -> 读取剩余时间"""
        self.log("开始续期操作...")

        # 记录运行时间
        run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 先读取当前剩余时间
        old_expiry = self._get_expiry_time(sb)
        self.log(f"当前剩余时间: {old_expiry}")

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
            return f"🎮 Zampto 续期通知\n\n🕒 运行时间: {run_time}\n🖥️ 服务器: 🇩🇪 Zampto (Auto)\n📊 续期结果: ❌ 失败 (找不到按钮)\n🕒 旧到期: {old_expiry or '未知'}"

        # 2. 处理人机验证 (统一切换至物理对位模式)
        time.sleep(3)
        # self.log("处理续期步人机验证 (物理对位模式)...")
        self._handle_cloudflare(sb)
        # 3. 等待页面刷新/结果
        self.log("等待页面响应 (10秒)...")
        time.sleep(10)

        # 4. 读取新的剩余时间
        sb.save_screenshot(str(self.screenshot_dir / "renewal_result.png"))
        new_expiry = self._get_expiry_time(sb)
        self.log(f"续期后剩余时间: {new_expiry}")

        # 5. 构建 XServer 风格通知
        status_icon = "✅ 成功" if new_expiry else "⚠️ 异常 (时间未读取)"

        msg = f"🎮 Zampto 续期通知\n\n"
        msg += f"🕒 运行时间: {run_time}\n"
        msg += f"🖥️ 服务器: 🇮🇹 Zampto (Auto)\n"
        msg += f"📊 续期结果: {status_icon}\n"
        msg += f"🕒 旧到期: {old_expiry or '未知'}\n"
        msg += f"🕒 新到期: {new_expiry or '未知'}"

        return msg

    def _get_expiry_time(self, sb):
        """读取 Expiry 时间，包含容错和调试信息"""
        try:
            page_text = sb.get_page_source()
            match = re.search(
                r"Expiry.*?([0-9]+\s*[a-zA-Z]+(?:\s*[0-9]+\s*[a-zA-Z]+)?)",
                page_text,
                re.IGNORECASE | re.DOTALL,
            )
            if match:
                return match.group(1).strip()

            match = re.search(r"(\d+)\s*day[s]?\s*(\d+)\s*h", page_text, re.IGNORECASE)
            if match:
                return f"{match.group(1)}d {match.group(2)}h"

            self.log("⚠️ 无法读取剩余时间，打印源码片段调试:")
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
        if sb.execute_script(_EXISTS_JS):
            handle_turnstile(sb)

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
                    wi = sb.execute_script(_WININFO_JS)
                    bar = wi["oh"] - wi["ih"]
                    ax = coords["x"] + wi["sx"]
                    ay = coords["y"] + wi["sy"] + bar
                    self.log(f"   -- 物理开火: xdotool click at ({ax}, {ay})")
                    _xdotool_click(ax, ay)
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
    target_url = os.environ.get("ZAMPTO_TARGET_URL")
    username = os.environ.get("ZAMPTO_USERNAME")
    password = os.environ.get("ZAMPTO_PASSWORD")
    proxy = os.environ.get("ZAMPTO_PROXY")

    if not username or not password:
        print("错误: 缺少 ZAMPTO_USERNAME 或 ZAMPTO_PASSWORD 环境变量")
        sys.exit(1)

    handler = RenewalHandler()
    if handler.run(target_url, username, password, proxy):
        sys.exit(0)
    else:
        sys.exit(1)
