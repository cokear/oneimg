# -*- coding: utf-8 -*-
"""
Zampto Auto Renewal — GitHub Actions 版
- 内联 cf_turnstile_helper（与本地版 1:1）
- 加 FlareSolverr cf_clearance 注入（破首页 IUAM）
- 登录两步（强化版）：等邮箱框消失 + 密码框可见可写
- 点击 Sign in 后才检测 CF
登录页: https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl
"""

import time
import os
import sys
import re
import json
import subprocess
import requests
from pathlib import Path
from datetime import datetime
from seleniumbase import SB
from selenium.webdriver.common.by import By


# ============================================================
#  cf_turnstile_helper（内联，1:1 复制本地版 + iframe 兜底）
# ============================================================
_EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
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

# 兜底：找 CF iframe（即使主文档没有 input）
_HAS_CF_IFRAME_JS = """
(function(){
    var ifs = document.querySelectorAll('iframe');
    for (var i=0;i<ifs.length;i++){
        var s = (ifs[i].src||'').toLowerCase();
        if (s.indexOf('challenges.cloudflare.com')>=0 || s.indexOf('turnstile')>=0) {
            return true;
        }
    }
    return false;
})()
"""


def is_turnstile_present(sb) -> bool:
    try:
        if bool(sb.execute_script(_EXISTS_JS)):
            return True
        # 兜底：跨域 iframe 时主文档没 input，看 iframe 是否存在
        return bool(sb.execute_script(_HAS_CF_IFRAME_JS))
    except Exception:
        return False


def is_turnstile_solved(sb) -> bool:
    """严格判定：只看 cf-turnstile-response input 是否有有效 token"""
    try:
        return bool(sb.execute_script(_SOLVED_JS))
    except Exception:
        return False


def get_window_metrics_js() -> str:
    return _WININFO_JS


def detect_cloudflare_challenge(sb) -> bool:
    """检测 CF 挑战页/widget"""
    try:
        page_source = str(sb.get_page_source() or "").lower()
    except Exception:
        page_source = ""
    try:
        title = str(sb.get_title() or "")
    except Exception:
        title = ""

    indicators = (
        "turnstile",
        "challenges.cloudflare",
        "just a moment",
        "verify you are human",
    )
    if any(item in page_source for item in indicators):
        return True
    if "just a moment" in title.lower():
        return True
    # iframe 兜底
    try:
        if bool(sb.execute_script(_HAS_CF_IFRAME_JS)):
            return True
    except Exception:
        pass
    return False


def handle_cloudflare_if_present(sb) -> bool:
    """检测到就处理；返回是否处理过（不一定通过）"""
    if not detect_cloudflare_challenge(sb):
        return False
    if not is_turnstile_present(sb):
        return False
    return handle_turnstile(sb)


def handle_turnstile(sb) -> bool:
    print("检测到 Cloudflare 验证，开始处理...", flush=True)
    time.sleep(2)

    if is_turnstile_solved(sb):
        print("Cloudflare 验证已通过（已有 token）", flush=True)
        return True

    for _ in range(3):
        try:
            sb.execute_script(_EXPAND_JS)
        except Exception:
            pass
        time.sleep(0.5)

    for attempt in range(6):
        if is_turnstile_solved(sb):
            print(f"Cloudflare 验证通过（第 {attempt + 1}/6 轮）", flush=True)
            return True

        try:
            sb.execute_script(_EXPAND_JS)
        except Exception:
            pass
        time.sleep(0.3)

        # 双开火：先 SB 自带 uc_gui_click_captcha（在 xvfb 下精度高），后 xdotool
        try:
            sb.uc_gui_click_captcha()
            print(f"Cloudflare 验证点击（uc_gui，第 {attempt + 1}/6 轮）", flush=True)
        except Exception as e:
            print(f"Cloudflare 验证点击异常（uc_gui，第 {attempt + 1}/6 轮）: {e}", flush=True)
        time.sleep(2)
        if is_turnstile_solved(sb):
            print(f"Cloudflare 验证通过（uc_gui，第 {attempt + 1}/6 轮）", flush=True)
            return True

        _click_turnstile(sb)
        print(f"Cloudflare 验证点击（坐标兜底，第 {attempt + 1}/6 轮）", flush=True)

        for _ in range(8):
            time.sleep(0.5)
            if is_turnstile_solved(sb):
                print(f"Cloudflare 验证通过（坐标兜底，第 {attempt + 1}/6 轮）", flush=True)
                return True

        print(f"Cloudflare 验证第 {attempt + 1}/6 轮未通过，准备重试...", flush=True)

    print("Cloudflare 验证未通过（已尝试 6 轮）", flush=True)
    return False


def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--class", cls],
                capture_output=True, text=True, timeout=3,
            )
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(
                    ["xdotool", "windowactivate", "--sync", wids[0]],
                    timeout=3, stderr=subprocess.DEVNULL,
                )
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(
            ["xdotool", "getactivewindow", "windowactivate"],
            timeout=3, stderr=subprocess.DEVNULL,
        )
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


def click_screen_point(x: int, y: int):
    _xdotool_click(x, y)


def _click_turnstile(sb):
    try:
        coords = sb.execute_script(_COORDS_JS)
    except Exception as e:
        print(f"[cf] failed to get turnstile coords: {e}")
        return
    if not coords:
        print("[cf] unable to locate turnstile coords")
        return
    try:
        wi = sb.execute_script(_WININFO_JS)
    except Exception:
        wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}
    bar = wi["oh"] - wi["ih"]
    ax = coords["cx"] + wi["sx"]
    ay = coords["cy"] + wi["sy"] + bar
    _xdotool_click(ax, ay)


# ============================================================
#  CFBypass (FlareSolverr cookie 注入)
# ============================================================
class CFBypass:
    def __init__(self, proxy_url=None, fs_url=None):
        self.proxy_url = proxy_url or os.environ.get("ZAMPTO_PROXY", "socks5://127.0.0.1:8080")
        self.fs_url = fs_url or os.environ.get("FS_URL", "http://127.0.0.1:8191/v1")
        self._last_ua = None
        self._last_cookies = None

    def solve(self, url, max_timeout=90000):
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": max_timeout,
            "proxy": {"url": self.proxy_url},
        }
        resp = requests.post(self.fs_url, json=payload, timeout=max_timeout // 1000 + 30).json()
        if resp.get("status") != "ok":
            raise RuntimeError(f"FlareSolverr failed: {resp}")
        sol = resp["solution"]
        self._last_ua = sol["userAgent"]
        self._last_cookies = sol.get("cookies", [])
        return True

    def inject_cookies(self, sb, domain=".zampto.net"):
        if not self._last_cookies:
            return
        for c in self._last_cookies:
            try:
                sb.driver.add_cookie({
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", domain),
                    "path": c.get("path", "/"),
                    "secure": c.get("secure", True),
                })
            except Exception:
                pass


# ============================================================
#  RenewalHandler
# ============================================================
class RenewalHandler:
    def __init__(self, output_dir="artifacts"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir = self.output_dir
        self.login_url = "https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl"
        self.cf = CFBypass()

    def log(self, msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

    def run(self, url, username, password, proxy=None):
        print("=" * 40)
        print("  ZAMPTO AUTO RENEWAL")
        print("=" * 40)
        self.log(f"启动任务: {url}")
        self.log(f"登录页: {self.login_url}")
        if proxy:
            self.log(f"使用代理: {proxy}")

        # FlareSolverr 取 cf_clearance（破首页 IUAM）
        self.log("FlareSolverr 取 cf_clearance...")
        try:
            self.cf.solve("https://zampto.net")
            self.log(f"✅ cf_clearance + UA: {self.cf._last_ua[:60]}...")
        except Exception as e:
            self.log(f"⚠️ FlareSolverr 失败 (继续裸连): {e}")

        try:
            sb_args = {}
            if proxy:
                sb_args["proxy"] = proxy

            with SB(uc=True, test=True, locale="en", **sb_args) as sb:
                self.log("浏览器启动成功")

                # IP 检查
                try:
                    sb.open("https://api.ipify.org/?format=json")
                    self.log(f"当前 IP: {sb.get_text('body')}")
                except Exception as e:
                    self.log(f"IP 检查失败: {e}")

                # 注入 cf_clearance
                self.log("加载首页注入 cf_clearance...")
                sb.uc_open_with_reconnect("https://zampto.net", reconnect_time=4)
                time.sleep(2)
                self.cf.inject_cookies(sb)
                sb.uc_open_with_reconnect("https://zampto.net", reconnect_time=4)
                time.sleep(3)

                # 直接进登录页
                self.log(f"访问登录页: {self.login_url}")
                sb.uc_open_with_reconnect(self.login_url, reconnect_time=5)
                time.sleep(3)
                self.log(f"当前 URL: {sb.get_current_url()}")
                self.log(f"页面标题: {sb.get_title()}")

                # 登录
                if not self._login(sb, username, password):
                    self.log("❌ 登录失败")
                    sb.save_screenshot(str(self.screenshot_dir / "final_page.png"))
                    return False
                self.log("✅ 登录成功")

                # 跳转目标页
                if url:
                    self.log(f"🛫 跳转目标页: {url}")
                    sb.uc_open_with_reconnect(url, reconnect_time=5)
                    time.sleep(5)
                    result = self._do_renewal(sb)
                    self.log(f"续期结果: {result}")
                    with open("renewal_result.txt", "w", encoding="utf-8") as f:
                        f.write(result)

                self.log(f"最终 URL: {sb.get_current_url()}")
                self.log(f"最终标题: {sb.get_title()}")
                sb.save_screenshot(str(self.screenshot_dir / "final_page.png"))
                return True

        except Exception as e:
            self.log(f"运行异常: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _handle_cookie_consent(self, sb):
        """处理隐私/Cookie 同意弹窗 (从本地 zampto.py 1:1 复制)"""
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

        # 中文专项兜底
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

    def _click_consent_button_js(self, sb):
        """评分系统：选最像同意按钮的，排除负词"""
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
                    var neg = ['不同意','拒绝','disagree','reject','deny','donotconsent','manage','manageoptions'];
                    var pos = ['同意','接受','accept','agree','allow','允许','acceptall','全部同意','consent'];

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
                        if (t === '同意' || t === 'accept' || t === 'agree' || t === 'acceptall' || t === '全部同意' || t === 'consent') s = 100;
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
        """登录后同意弹窗：当前页 + iframe 兜底"""
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
                    try: sb.driver.switch_to.default_content()
                    except Exception: pass
                    continue
            time.sleep(0.8)
        return False

    def _login(self, sb, username, password):
        """两步登录：邮箱→点击→等切换→密码框可见可写→密码→点击→等 CF→等 URL 跳走"""
        self.log(f"执行登录步骤，账号: {username[:3]}***")
        self._handle_cookie_consent(sb)
        sb.save_screenshot(str(self.screenshot_dir / "debug_before_login.png"))

        # === Step 1: 邮箱 ===
        self.log("第一步：输入邮箱...")
        try:
            sb.wait_for_element_visible("input[name='identifier']", timeout=20)
            sb.clear("input[name='identifier']")
            sb.type("input[name='identifier']", username)
            self.log("✅ 邮箱已输入")
        except Exception as e:
            self.log(f"找不到邮箱输入框: {e}")
            sb.save_screenshot(str(self.screenshot_dir / "login_fail_no_email.png"))
            return False

        try:
            sb.click("button[type='submit']")
            self.log("✅ 第一步按钮已点击")
        except Exception as e:
            self.log(f"第一步按钮点击失败: {e}")
            return False

        # 等邮箱框消失
        self.log("等待页面切换到密码步骤（邮箱框消失）...")
        switched = False
        for i in range(50):
            time.sleep(0.5)
            try:
                still = sb.execute_script(
                    "var e=document.querySelector(\"input[name='identifier']\");"
                    "return !!(e && e.offsetParent !== null && !e.disabled);"
                )
                if not still:
                    switched = True
                    self.log(f"✅ 已切换到密码步骤 ({i*0.5:.1f}s)")
                    break
            except Exception:
                pass
        if not switched:
            sb.save_screenshot(str(self.screenshot_dir / "login_fail_no_switch.png"))
            self.log("❌ 邮箱框始终存在")
            return False

        # === Step 2: 等可见可写密码框 ===
        self.log("等待密码框可见可写 (最多 25s)...")
        pwd_sel = None
        for i in range(50):
            time.sleep(0.5)
            try:
                found = sb.execute_script("""
                    var sels = ["input[name='Password']", "input[name='password']", "input[type='password']"];
                    for (var i=0; i<sels.length; i++) {
                        var el = document.querySelector(sels[i]);
                        if (el && el.offsetParent !== null && !el.disabled && !el.readOnly) {
                            return sels[i];
                        }
                    }
                    return null;
                """)
                if found:
                    pwd_sel = found
                    self.log(f"✅ 密码框就位: {pwd_sel} ({i*0.5:.1f}s)")
                    break
            except Exception:
                pass
        if not pwd_sel:
            sb.save_screenshot(str(self.screenshot_dir / "login_fail_no_pwd.png"))
            self.log("❌ 找不到可写密码框")
            return False

        sb.save_screenshot(str(self.screenshot_dir / "debug_pwd_step.png"))

        try:
            self.log("第二步：输入密码...")
            sb.clear(pwd_sel)
            sb.type(pwd_sel, password)
            self.log("✅ 密码已输入")
            time.sleep(1)
            sb.click("button[type='submit']")
            self.log("✅ 第二步按钮已点击")
        except Exception as e:
            self.log(f"第二步执行失败: {e}")
            sb.save_screenshot(str(self.screenshot_dir / "login_fail_step2.png"))
            return False

        # === 关键：点击后才弹 Turnstile，等出现并解决（最多 30s）===
        self.log("点击后等待 CF Turnstile 出现...")
        cf_seen = False
        for tick in range(60):
            try:
                curr = sb.get_current_url().lower()
                if "sign-in" not in curr and "login" not in curr:
                    self.log(f"  → URL 跳走 ({curr})，静默通过")
                    break
            except Exception:
                pass

            ps_len = 0
            ps_hit = False
            iframe_hit = False
            input_hit = False
            try:
                ps = sb.get_page_source() or ""
                ps_len = len(ps)
                pl = ps.lower()
                ps_hit = any(x in pl for x in ("turnstile", "challenges.cloudflare", "verify you are human"))
            except Exception as e:
                if tick == 0:
                    self.log(f"⚠️ get_page_source 失败: {e}")
            try:
                iframe_hit = bool(sb.execute_script(_HAS_CF_IFRAME_JS))
            except Exception:
                pass
            try:
                input_hit = bool(sb.execute_script(_EXISTS_JS))
            except Exception:
                pass

            # 只有当 iframe 或 input 真的存在才算"出现"
            # ps 文本只是模糊信号，不能单独触发 handle
            if iframe_hit or input_hit:
                cf_seen = True
                self.log(f"🛡️ Turnstile 已加载 (ps={ps_hit}, iframe={iframe_hit}, input={input_hit})")
                break

            if tick % 6 == 0:
                self.log(f"[probe {tick*0.5:.0f}s] ps_len={ps_len} ps={ps_hit} iframe={iframe_hit} input={input_hit}")
            time.sleep(0.5)

        if cf_seen:
            self.log("🛡️ Turnstile 出现，处理中...")
            sb.save_screenshot(str(self.screenshot_dir / "debug_cf_appeared.png"))
            handle_turnstile(sb)
            sb.save_screenshot(str(self.screenshot_dir / "debug_after_cf.png"))
            time.sleep(2)
            try:
                curr = sb.get_current_url().lower()
                if "sign-in" in curr or "login" in curr:
                    self.log("CF 通过但 URL 没跳，再点一次 Sign in...")
                    try: sb.click("button[type='submit']")
                    except Exception: pass
            except Exception:
                pass
        else:
            self.log("ℹ️ 未检测到 CF Turnstile (静默通过或异常)")
            sb.save_screenshot(str(self.screenshot_dir / "debug_no_cf_seen.png"))

        # === 等 URL 离开 sign-in（最多 25s）===
        self.log("等待登录跳转 (最多 25s)...")
        for i in range(50):
            time.sleep(0.5)
            try:
                curr = sb.get_current_url().lower()
                if "sign-in" not in curr and "login" not in curr:
                    self.log(f"✅ 已离开登录页 ({i*0.5:.1f}s) → {curr}")
                    self._handle_social_prompt(sb)
                    return True
            except Exception:
                pass

        sb.save_screenshot(str(self.screenshot_dir / "login_fail_still_sign_in.png"))
        try:
            err = sb.execute_script(
                "return Array.from(document.querySelectorAll('[class*=\"error\"],[class*=\"alert\"],[role=\"alert\"]'))"
                ".map(e=>e.innerText).filter(Boolean).join(' | ').slice(0,300)"
            )
            if err:
                self.log(f"📋 页面错误: {err}")
        except Exception:
            pass
        try:
            self.log(f"⚠️ 仍在登录页: {sb.get_current_url()}")
        except Exception:
            pass
        return False

    def _handle_social_prompt(self, sb):
        try:
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
                self.log(f"🎯 发现 Continue 弹窗 ({coords['x']}, {coords['y']})")
                try:
                    wi = sb.execute_script(_WININFO_JS)
                    bar = wi["oh"] - wi["ih"]
                    click_screen_point(coords["x"]+wi["sx"], coords["y"]+wi["sy"]+bar)
                    time.sleep(0.5)
                except Exception: pass
                try:
                    sb.execute_script("var b = document.querySelector('button.continue-btn'); if(b) b.click();")
                except Exception: pass
                time.sleep(3)
        except Exception:
            pass
        return False

    def _do_renewal(self, sb):
        """续期：点击 → 等待弹窗/CF → 多信号判定（成功/失败/到期变化/弹窗关闭）"""
        self.log("开始续期操作...")
        self._handle_post_login_consent(sb, timeout=10)
        run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        def _read_expiry(phase, attempts=3, interval=1.0, verbose_last=False):
            value = None
            for i in range(max(1, int(attempts))):
                try:
                    value = self._get_expiry_time(
                        sb,
                        verbose=bool(verbose_last and i == max(1, int(attempts)) - 1),
                    )
                except Exception as e:
                    self.log(f"[expiry:{phase}] 读取异常: {e}")
                    value = None
                if value:
                    self.log(f"[expiry:{phase}] 命中: {value} (attempt {i + 1}/{attempts})")
                    return value
                if i < attempts - 1:
                    time.sleep(max(0.2, float(interval)))
            if phase in ("before_renew", "final_after_renew"):
                self.log(f"[expiry:{phase}] 未读到剩余时间 (attempts={attempts})")
            return None

        old_expiry = _read_expiry("before_renew", attempts=4, interval=1.1, verbose_last=True)
        self.log(f"当前剩余时间: {old_expiry or '未知'}")
        old_norm = self._normalize_expiry_text(old_expiry)

        # 1. 点击续期按钮
        self.log("查找续期按钮...")
        click_data = {"clicked": False, "signal": "", "reason": "unknown", "text": ""}
        try:
            raw = sb.execute_script(r"""
                return (function() {
                    function visible(el) {
                        if (!el) return false;
                        var r = el.getBoundingClientRect();
                        var s = window.getComputedStyle(el);
                        return r.width > 16 && r.height > 12 && s.display !== 'none' && s.visibility !== 'hidden';
                    }
                    function norm(t) { return String(t || '').replace(/\s+/g, ' ').trim().toLowerCase(); }
                    function scoreOf(el) {
                        var txt = norm(el.innerText || el.textContent || el.value || '');
                        var attrs = norm(
                            (el.getAttribute('onclick') || '') + ' ' +
                            (el.getAttribute('data-action') || '') + ' ' +
                            (el.getAttribute('aria-label') || '') + ' ' +
                            (el.getAttribute('title') || '') + ' ' +
                            (el.getAttribute('id') || '') + ' ' +
                            (el.getAttribute('class') || '')
                        );
                        var s = 0;
                        if (attrs.indexOf('handleserverrenewal') >= 0) s += 130;
                        if (attrs.indexOf('renew') >= 0) s += 70;
                        if (attrs.indexOf('renewal') >= 0) s += 50;
                        if (txt.indexOf('renew') >= 0) s += 85;
                        if (txt.indexOf('续期') >= 0) s += 95;
                        if (txt.indexOf('extend') >= 0) s += 45;
                        if (txt.indexOf('server') >= 0) s += 20;
                        if (el.tagName === 'A' || el.tagName === 'BUTTON') s += 8;
                        if ((el.getAttribute('disabled') || '') !== '' || el.getAttribute('aria-disabled') === 'true') s -= 200;
                        return { score: s, txt: txt };
                    }
                    function detectSignal() {
                        var modal = document.querySelector('#renew-modal, .modal.show, [role="dialog"]');
                        var modalOpen = false;
                        if (modal) {
                            var rs = modal.getBoundingClientRect();
                            var ms = window.getComputedStyle(modal);
                            modalOpen = rs.width > 20 && rs.height > 20 && ms.display !== 'none' && ms.visibility !== 'hidden';
                        }
                        var cfPresent = !!document.querySelector(
                            "iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile'], input[name='cf-turnstile-response'], .cf-turnstile"
                        );
                        var signal = 'clicked_only';
                        if (modalOpen) signal = 'modal_open';
                        else if (cfPresent) signal = 'cf_present';
                        return { signal: signal, modal_open: modalOpen, cf_present: cfPresent };
                    }

                    var all = Array.from(document.querySelectorAll("a,button,[role='button'],div[role='button'],span[role='button']"));
                    var cands = [];
                    for (var i = 0; i < all.length; i++) {
                        var el = all[i];
                        if (!visible(el)) continue;
                        var info = scoreOf(el);
                        if (info.score > 0) {
                            cands.push({ el: el, score: info.score, txt: info.txt });
                        }
                    }
                    cands.sort(function(a, b) { return b.score - a.score; });
                    if (!cands.length) return { clicked: false, signal: '', reason: 'no_scored_candidate', text: '' };

                    for (var j = 0; j < Math.min(cands.length, 8); j++) {
                        var c = cands[j];
                        try { c.el.scrollIntoView({block: 'center', inline: 'center'}); } catch (e1) {}
                        try {
                            c.el.click();
                            var sig = detectSignal();
                            return {
                                clicked: true,
                                signal: sig.signal,
                                reason: 'clicked',
                                text: (c.txt || '').slice(0, 100),
                                score: c.score
                            };
                        } catch (e2) {}
                    }
                    return { clicked: false, signal: '', reason: 'all_candidates_click_failed', text: '' };
                })();
            """)
            if isinstance(raw, dict):
                click_data = raw
        except Exception as e:
            self.log(f"点击按钮出错: {e}")

        btn_clicked = bool(click_data.get("clicked"))
        click_signal = str(click_data.get("signal") or "").strip()
        click_text = str(click_data.get("text") or "").strip()
        if not btn_clicked:
            fail_reason = str(click_data.get("reason") or "unknown")
            self.log(f"❌ 找不到续期按钮: {fail_reason}")
            sb.save_screenshot(str(self.screenshot_dir / "renew_button_not_found.png"))
            return f"🎮 Zampto 续期\n🕒 {run_time}\n📊 ❌ 失败 (找不到按钮)\n🕒 旧到期: {old_expiry or '未知'}"
        self.log(
            f"✅ 已点击续期按钮: signal={click_signal or 'clicked_only'}"
            + (f", text={click_text}" if click_text else "")
        )

        # 2. 等待弹窗 / CF 真正渲染（防慢网抢跑）
        post_state = self._wait_after_renew_click(sb, timeout=40, stable_hits=2)
        if not click_signal:
            if post_state.get("modal_open"):
                click_signal = "modal_open"
            elif post_state.get("cf_present") or post_state.get("cf_solved"):
                click_signal = "cf_present"
            else:
                click_signal = "clicked_only"

        cf_solved = bool(post_state.get("cf_solved"))
        cf_checked = False
        if not cf_solved:
            if detect_cloudflare_challenge(sb):
                cf_checked = True
                self.log("🛡️ 续期步骤检测到 Cloudflare 验证，开始处理...")
                cf_solved = bool(handle_turnstile(sb))
                if cf_solved:
                    self.log("✅ Cloudflare 验证已通过")
                else:
                    self.log("⚠️ Cloudflare 验证未明确通过，继续观察续期结果")
            else:
                self.log("ℹ️ 未检测到 Cloudflare 验证")
        else:
            cf_checked = True
            self.log("✅ Cloudflare 验证已通过，跳过重复处理")

        # 3. 等结果（轮询 45s，避免固定 sleep 误判）
        self.log("等待续期结果与到期时间更新 (最多 45s)...")
        deadline = time.time() + 45
        new_expiry = None
        expiry_changed = False
        saw_success = False
        saw_failure = False
        last_signal = {}
        while time.time() < deadline:
            last_signal = self._probe_renewal_outcome(sb)
            if last_signal.get("failure"):
                saw_failure = True
                self.log(f"⚠️ 失败信号: {last_signal.get('snippet') or 'unknown'}")
                break
            if last_signal.get("success"):
                saw_success = True

            new_expiry = _read_expiry("after_click", attempts=2, interval=0.8, verbose_last=False)
            new_norm = self._normalize_expiry_text(new_expiry)
            if new_norm and old_norm and new_norm != old_norm:
                # 二次确认稳定
                verify_raw = _read_expiry("after_click_confirm", attempts=2, interval=1.0, verbose_last=False)
                verify = self._normalize_expiry_text(verify_raw)
                if verify and verify != old_norm:
                    self.log(f"✅ 到期时间已变化: {old_expiry} → {verify_raw}")
                    new_expiry = verify_raw
                    expiry_changed = True
                    break
            elif new_norm and not old_norm:
                break

            # 续期阶段 CF 偶尔延迟弹
            if not cf_solved and detect_cloudflare_challenge(sb):
                self.log("🧩 检测到延迟出现的 Cloudflare 验证，补做一次处理...")
                cf_solved = bool(handle_turnstile(sb)) or cf_solved
                cf_checked = True
                if cf_solved:
                    self.log("✅ 延迟 Cloudflare 验证已通过")
            time.sleep(2)

        # 4. 最终读取
        sb.save_screenshot(str(self.screenshot_dir / "renewal_result.png"))
        final_read = _read_expiry("final_after_renew", attempts=3, interval=1.0, verbose_last=True)
        if final_read:
            new_expiry = final_read
        elif (saw_success or (cf_solved and modal_closed if 'modal_closed' in locals() else False)):
            self.log("ℹ️ 已判定续期成功，但暂未读到新到期时间，进行补充读取...")
            extra_deadline = time.time() + 18
            while time.time() < extra_deadline:
                extra = _read_expiry("success_followup", attempts=1, interval=0.5, verbose_last=False)
                if extra:
                    new_expiry = extra
                    self.log(f"✅ 成功后补充读取到新到期时间: {new_expiry}")
                    break
                time.sleep(2)
        self.log(f"续期后剩余时间: {new_expiry or '未知'}")
        new_norm = self._normalize_expiry_text(new_expiry)
        if not expiry_changed and old_norm and new_norm and new_norm != old_norm:
            expiry_changed = True

        final_signal = self._probe_renewal_outcome(sb)
        saw_success = saw_success or bool(final_signal.get("success"))
        saw_failure = saw_failure or bool(final_signal.get("failure"))
        modal_closed = not bool(final_signal.get("modal_open"))

        # 5. 多信号判定
        if saw_failure:
            ok, verdict, reason = False, "❌ 失败", "检测到页面失败提示"
        elif expiry_changed:
            ok, verdict, reason = True, "✅ 成功", "到期信息发生变化"
        elif saw_success:
            ok, verdict, reason = True, "✅ 成功", "检测到成功提示"
        elif cf_solved and modal_closed:
            ok, verdict, reason = True, "✅ 成功(弱确认)", "验证通过且弹窗已关闭"
        elif click_signal in ("modal_open", "cf_present"):
            ok, verdict, reason = False, "⚠️ 待确认", "已进入续期流程，但缺少明确成功信号"
        else:
            ok, verdict, reason = False, "⚠️ 未确认成功", "无明确成功信号"

        self.log(
            f"续期判定: changed={expiry_changed}, success={saw_success}, failure={saw_failure}, "
            f"cf_checked={cf_checked}, cf_passed={cf_solved}, modal_closed={modal_closed}, click_signal={click_signal} | {reason}"
        )

        new_display = new_expiry or ("未读取到（续期已成功）" if ok else "未知")
        msg = (
            "🎮 Zampto 续期通知\n"
            f"🕒 运行时间: {run_time}\n"
            "🖥️ 服务器: 🇮🇹 Zampto (Auto)\n"
            f"📊 续期结果: {verdict}\n"
            f"🕒 旧到期: {old_expiry or '未知'}\n"
            f"🕒 新到期: {new_display}\n"
            f"🧪 判定依据: {reason}"
        )
        return msg

    def _wait_after_renew_click(self, sb, timeout=25, stable_hits=2):
        """点击续期后等弹窗+CF 真正渲染。返回稳定状态。"""
        self.log(f"等待续期弹窗/验证渲染 (≤ {timeout}s, 连续命中 {stable_hits} 次)...")
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
                self.log(f"✅ 续期界面就绪: modal={modal_open}, cf_present={cf_present}, cf_solved={cf_solved}")
                return {"modal_open": modal_open, "cf_present": cf_present, "cf_solved": cf_solved}
            time.sleep(0.8)
        self.log("ℹ️ 弹窗/验证未明确出现，继续后续流程")
        return {"modal_open": False, "cf_present": False, "cf_solved": False}

    def _probe_renewal_outcome(self, sb):
        """从页面提示里探测续期成功/失败/弹窗状态"""
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
                    function isSuccess(t) {
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
                    function isFailure(t) {
                        var s = t.toLowerCase();
                        return (
                            s.indexOf('renew fail') >= 0 ||
                            s.indexOf('failed to renew') >= 0 ||
                            s.indexOf('error') >= 0 ||
                            s.indexOf('续期失败') >= 0 ||
                            s.indexOf('失败') >= 0
                        );
                    }
                    var selectors = ['.alert','.toast','[role="alert"]','.swal2-popup','.notification','.message','#renew-modal'];
                    var nodes = [];
                    selectors.forEach(function(sel) {
                        document.querySelectorAll(sel).forEach(function(el) {
                            if (visible(el)) nodes.push(el);
                        });
                    });
                    if (nodes.length === 0 && document.body) nodes = [document.body];

                    var success = false, failure = false, snippet = '';
                    for (var i = 0; i < nodes.length; i++) {
                        var t = norm(nodes[i].innerText || nodes[i].textContent || '');
                        if (!t) continue;
                        if (!snippet) snippet = t.slice(0, 240);
                        if (isSuccess(t)) success = true;
                        if (isFailure(t)) failure = true;
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
        except Exception:
            pass
        return {"success": False, "failure": False, "modal_open": False, "snippet": ""}

    def _normalize_expiry_text(self, value):
        if value is None:
            return ""
        text = str(value).strip().lower()
        if not text or not self._looks_like_expiry_text(text):
            return ""
        text = re.sub(r"\s+", " ", text)
        text = text.replace("days", "day").replace("hours", "h").replace("hour", "h")
        return text

    def _looks_like_expiry_text(self, value):
        text = str(value or "").strip().lower()
        if not text:
            return False
        bad = [r"document\.getelementbyid\s*\(", r"\bstyle\.display\b", r"\bfunction\s*\(",
               r"\bvar\s+\w+", r"[{};]", r"\b\d+\s*px\b"]
        for p in bad:
            if re.search(p, text, re.IGNORECASE):
                return False
        good = [r"\b\d+\s*day[s]?\s*\d+\s*h\b", r"\b\d+\s*day[s]?\b", r"\b\d+\s*h\b",
                r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"]
        for p in good:
            if re.search(p, text, re.IGNORECASE):
                return True
        return False

    def _get_expiry_time(self, sb, verbose=True):
        """读取 Expiry：DOM 标签-值关系优先，过滤脚本/CSS 噪声"""
        try:
            dom_text = sb.execute_script(
                r"""
                return (function() {
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
                        if (/\b\d+\s*hour[s]?\b/i.test(t)) return true;
                        if (/\b\d+\s*minute[s]?\b/i.test(t)) return true;
                        if (/\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b/.test(t)) return true;
                        if (/\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b/.test(t)) return true;
                        return false;
                    }
                    var strongSelectors = [
                        '#nextRenewalTime',
                        '[data-expiry]',
                        '#expiry',
                        '.expiry',
                        '[id*="expiry"]',
                        '[class*="expiry"]',
                        '[id*="renewal"][id*="time"]',
                        '[class*="renewal"][class*="time"]'
                    ];
                    for (var si = 0; si < strongSelectors.length; si++) {
                        var node = document.querySelector(strongSelectors[si]);
                        if (!node) continue;
                        var sv = clean(txt(node));
                        if (looksExpiry(sv)) return sv;
                    }

                    // 从 Renew Server 按钮所在卡片读取（直接正则提取，不用 looksExpiry 过滤整段 cardText）
                    var renewBtn = Array.from(document.querySelectorAll('a,button,[role="button"]')).find(function(el){
                        var t = clean(txt(el)).toLowerCase();
                        return t.indexOf('renew server') >= 0 || t.indexOf('renew') >= 0 || t.indexOf('续期') >= 0;
                    });
                    if (renewBtn) {
                        var card = renewBtn.closest('section,article,div');
                        for (var deep = 0; deep < 4 && card; deep++) {
                            var cardText = clean(txt(card));
                            var c1 = cardText.match(/\b\d+\s*day[s]?\s*\d+\s*h\b/i);
                            if (c1) return c1[0];
                            var c2 = cardText.match(/\b\d+\s*day[s]?\b/i);
                            if (c2) return c2[0];
                            var c3 = cardText.match(/\b\d+\s*h\b/i);
                            if (c3) return c3[0];
                            var c4 = cardText.match(/\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b/);
                            if (c4) return c4[0];
                            card = card.parentElement;
                        }
                    }

                    var nodes = document.querySelectorAll('div,span,p,td,th,strong,b,dt,label');
                    var labelKeys = ['expiry', 'remaining', 'time left', 'next renewal', '到期', '剩余', '续期'];
                    for (var i = 0; i < nodes.length; i++) {
                        var t = clean(txt(nodes[i])).toLowerCase();
                        var isLabel = false;
                        for (var lk = 0; lk < labelKeys.length; lk++) {
                            if (t.indexOf(labelKeys[lk]) >= 0) { isLabel = true; break; }
                        }
                        if (isLabel) {
                            var cands = [];
                            if (nodes[i].nextElementSibling) cands.push(clean(txt(nodes[i].nextElementSibling)));
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

                    // 最后兜底：从正文文本中抽取时间格式
                    var bodyText = clean((document.body && (document.body.innerText || document.body.textContent)) || '');
                    if (bodyText) {
                        var m1 = bodyText.match(/\b\d+\s*day[s]?\s*\d+\s*h\b/i);
                        if (m1) return m1[0];
                        var m2 = bodyText.match(/\b\d+\s*day[s]?\b/i);
                        if (m2) return m2[0];
                        var m3 = bodyText.match(/\b\d+\s*h\b/i);
                        if (m3) return m3[0];
                        var m4 = bodyText.match(/\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b/);
                        if (m4) return m4[0];
                    }
                    return '';
                })();
                """
            )
            dom_text = str(dom_text or "").strip()
            if dom_text and self._looks_like_expiry_text(dom_text):
                m = re.search(r"(\d+)\s*day[s]?\s*(\d+)\s*h", dom_text, re.IGNORECASE)
                if m: return f"{m.group(1)} day {m.group(2)}h"
                m = re.search(r"(\d+)\s*day[s]?\b", dom_text, re.IGNORECASE)
                if m: return f"{m.group(1)} day"
                m = re.search(r"(\d+)\s*h\b", dom_text, re.IGNORECASE)
                if m: return f"{m.group(1)}h"
                return dom_text
            return None
        except Exception as e:
            if verbose:
                self.log(f"读取时间出错: {e}")
            return None


if __name__ == "__main__":
    target_url = os.environ.get("ZAMPTO_TARGET_URL")
    username = os.environ.get("ZAMPTO_USERNAME")
    password = os.environ.get("ZAMPTO_PASSWORD")
    proxy = os.environ.get("ZAMPTO_PROXY")

    if not username or not password:
        print("错误: 缺少 ZAMPTO_USERNAME 或 ZAMPTO_PASSWORD")
        sys.exit(1)

    handler = RenewalHandler()
    sys.exit(0 if handler.run(target_url, username, password, proxy) else 1)
