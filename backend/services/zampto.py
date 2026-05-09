# -*- coding: utf-8 -*-
"""
Zampto Auto Renewal — CF-Bypass 合并版
基于 zampto_renewal.py + cf_bypass.py
流程: sing-box 代理 → FlareSolverr 取 cf_clearance → 注入 cookie 登录 → 续期
"""
import time, os, sys, re, subprocess, json, requests
from pathlib import Path
from datetime import datetime
from seleniumbase import SB

# ============================================================
#  Turnstile 辅助脚本 (保留原版的物理点击逻辑)
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
(function(){ return document.querySelector('input[name="cf-turnstile-response"]') !== null; })()
"""

_SOLVED_JS = """
(function(){
    // 1) 主文档 input
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    if (i && i.value && i.value.length > 20) return true;
    // 2) iframe 仍在 → 未通过
    var ifs = document.querySelectorAll('iframe');
    var cf_iframe_count = 0;
    for (var k=0;k<ifs.length;k++){
        var s = (ifs[k].src||'').toLowerCase();
        if (s.indexOf('challenges.cloudflare.com')>=0 || s.indexOf('turnstile')>=0) {
            var r = ifs[k].getBoundingClientRect();
            if (r.width>0 && r.height>0) cf_iframe_count++;
        }
    }
    // 没主文档 input 也没 iframe = 没在挑战
    return cf_iframe_count === 0 && !i;
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
    return { sx: window.screenX || 0, sy: window.screenY || 0, oh: window.outerHeight, ih: window.innerHeight };
})()
"""

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
    ax = coords["cx"] + wi["sx"]
    ay = coords["cy"] + wi["sy"] + bar
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


# ============================================================
#  CF-Bypass 核心 (精简版，无需额外文件)
# ============================================================
class CFBypass:
    def __init__(self, proxy_url: str = None, fs_url: str = None):
        self.proxy_url = proxy_url or os.environ.get("ZAMPTO_PROXY", "socks5://127.0.0.1:1080")
        self.fs_url = fs_url or os.environ.get("FS_URL", "http://127.0.0.1:8191/v1")
        self._last_ua = None
        self._last_cookies = None
        self._last_html = None

    def solve(self, url: str, max_timeout: int = 90000) -> str:
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
        self._last_html = sol["response"]
        return self._last_html

    def inject_cookies(self, sb, domain: str = ".zampto.net"):
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
#  RenewalHandler (合并版)
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
        print("  ZAMPTO AUTO RENEWAL (CF-Bypass Mode)")
        print("=" * 40)
        self.log(f"启动任务: {url}")
        self.log(f"登录页: {self.login_url}")
        if proxy:
            self.log(f"使用代理: {proxy}")

        try:
            sb_args = {}
            if proxy:
                sb_args["proxy"] = proxy

            # === Step 1: FlareSolverr 过 CF 取 cookie ===
            self.log("Step 1: FlareSolverr 取 cf_clearance...")
            try:
                self.cf.solve("https://zampto.net")
                self.log(f"✅ 拿到 cf_clearance + UA: {self.cf._last_ua[:60]}...")
            except Exception as e:
                self.log(f"⚠️ FlareSolverr 失败 (继续裸连): {e}")

            with SB(uc=True, test=True, locale="en", **sb_args) as sb:
                self.log("浏览器启动成功")

                # IP 检查
                try:
                    self.log("检查出口 IP...")
                    sb.open("https://api.ipify.org/?format=json")
                    ip_info = sb.get_text("body")
                    self.log(f"当前 IP: {ip_info}")
                except Exception as e:
                    self.log(f"IP 检查失败: {e}")

                # === Step 2: 加载 zampto.net 注入 cookie ===
                self.log("Step 2: 加载首页并注入 cf_clearance...")
                sb.uc_open_with_reconnect("https://zampto.net", reconnect_time=5)
                time.sleep(2)
                self.cf.inject_cookies(sb)
                sb.uc_open_with_reconnect("https://zampto.net", reconnect_time=4)
                time.sleep(3)
                self.log(f"首页标题: {sb.get_title()}")
                self.log(f"首页 URL: {sb.get_current_url()}")

                # === Step 3: 访问登录页 ===
                self.log(f"Step 3: 访问登录页...")
                sb.uc_open_with_reconnect(self.login_url, reconnect_time=5)
                time.sleep(3)
                self.log(f"当前 URL: {sb.get_current_url()}")
                self.log(f"页面标题: {sb.get_title()}")

                # 登录页内可能有 CF
                self._handle_cloudflare(sb)

                # 判定
                curr_url = sb.get_current_url().lower()
                if "sign-in" in curr_url or "login" in curr_url:
                    self.log("检测到登录页面，开始登录流程...")
                    login_ok = self._login(sb, username, password)
                    if not login_ok:
                        self.log("❌ 登录失败，中止后续流程")
                        sb.save_screenshot(str(self.screenshot_dir / "final_page.png"))
                        return False
                    self.log("✅ 登录动作已执行完毕")

                    # 跳转目标页
                    if url:
                        self.log(f"🛫 登录确认，准备跳转目标页: {url}")
                        sb.uc_open_with_reconnect(url, reconnect_time=5)
                        time.sleep(5)
                        result = self._do_renewal(sb)
                        self.log(f"续期结果: {result}")
                        with open("renewal_result.txt", "w", encoding="utf-8") as f:
                            f.write(result)

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

    def _handle_cloudflare(self, sb):
        """只在确实看到 CF iframe 或主文档 input 时才处理。不靠文本匹配避免误触发。"""
        self._handle_cookie_consent(sb)
        try:
            has_cf_iframe = bool(sb.execute_script("""
                (function(){
                    var ifs = document.querySelectorAll('iframe');
                    for (var i=0;i<ifs.length;i++){
                        var s = (ifs[i].src||'').toLowerCase();
                        if (s.indexOf('challenges.cloudflare.com')>=0 || s.indexOf('turnstile')>=0) {
                            var r = ifs[i].getBoundingClientRect();
                            if (r.width>0 && r.height>0) return true;
                        }
                    }
                    return false;
                })()
            """))
        except Exception:
            has_cf_iframe = False
        in_main = False
        try:
            in_main = bool(sb.execute_script(_EXISTS_JS))
        except Exception:
            pass
        if has_cf_iframe or in_main:
            print(f"  🛡️ 检测到 CF (iframe={has_cf_iframe}, input={in_main})，调 handle_turnstile")
            handle_turnstile(sb)

    def _handle_cookie_consent(self, sb):
        try:
            clicked = bool(sb.execute_script("""
                (function() {
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        var text = (buttons[i].textContent || '').trim().toLowerCase();
                        if (text === 'consent' || text === 'accept') { buttons[i].click(); return true; }
                    }
                    return false;
                })()
            """))
            if clicked:
                self.log("✅ 已点击 Cookie 同意")
                time.sleep(1)
        except Exception:
            pass

    def _login(self, sb, username, password):
        """两步登录（强化版）：CF 只在点击 Sign in 之后才会出现，所以前面不查 CF。"""
        self.log(f"执行登录步骤，账号: {username[:3]}***")
        self._handle_cookie_consent(sb)
        sb.save_screenshot(str(self.screenshot_dir / "debug_before_login.png"))

        # ========== 第一步：输入邮箱 ==========
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

        # 关键修复：等邮箱框真正消失（Clerk 切到密码步），最多 25s
        self.log("等待页面切换到密码步骤（邮箱框消失）...")
        switched = False
        for i in range(50):
            time.sleep(0.5)
            try:
                still_visible = sb.execute_script(
                    "var e=document.querySelector(\"input[name='identifier']\");"
                    "return !!(e && e.offsetParent !== null && !e.disabled);"
                )
                if not still_visible:
                    switched = True
                    self.log(f"✅ 已切换到密码步骤 ({i*0.5:.1f}s)")
                    break
            except Exception:
                pass

        if not switched:
            sb.save_screenshot(str(self.screenshot_dir / "login_fail_no_switch.png"))
            self.log("⚠️ 邮箱框始终存在；可能账号无效 / 触发风控 / 需要 captcha")
            try:
                err = sb.execute_script(
                    "return Array.from(document.querySelectorAll('[class*=\"error\"],[class*=\"alert\"],[role=\"alert\"]'))"
                    ".map(e=>e.innerText).filter(Boolean).join(' | ').slice(0,300)"
                )
                if err:
                    self.log(f"📋 页面错误提示: {err}")
            except Exception:
                pass
            return False

        # 处理切换后可能的 cookie 同意（不查 CF，CF 只会在密码点击后出现）
        self._handle_cookie_consent(sb)

        # ========== 第二步：等到可见可写的密码框 ==========
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
            self.log("❌ 找不到可写的密码框")
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

        # 关键：点 Sign in 后才弹 Turnstile，等它出现并解决（最多 30s）
        self.log("点击后等待 CF Turnstile 出现...")
        cf_iframe_seen = False
        last_dump = None
        for tick in range(60):
            try:
                info = sb.execute_script("""
                    (function(){
                        var ifs = document.querySelectorAll('iframe');
                        var hits = [];
                        var matched = false;
                        for (var i=0;i<ifs.length;i++){
                            var s=(ifs[i].src||'');
                            var sl = s.toLowerCase();
                            var r = ifs[i].getBoundingClientRect();
                            hits.push({src:s.slice(0,80), w:Math.round(r.width), h:Math.round(r.height)});
                            if (sl.indexOf('challenges.cloudflare.com')>=0
                              ||sl.indexOf('turnstile')>=0
                              ||sl.indexOf('cloudflare')>=0) {
                                matched = true;
                            }
                        }
                        // 兜底：检查 cf-turnstile-response input（不要求可见）
                        var inp = document.querySelector('input[name="cf-turnstile-response"]');
                        return {matched: matched, hasInput: !!inp, ifs: hits};
                    })()
                """)
            except Exception as e:
                info = None
            # 已经跳走 = 静默通过
            curr = sb.get_current_url().lower()
            if "sign-in" not in curr and "login" not in curr:
                break
            if info and (info.get("matched") or info.get("hasInput")):
                cf_iframe_seen = True
                self.log(f"🛡️ Turnstile 出现 (matched={info.get('matched')}, input={info.get('hasInput')})")
                break
            # 每 5s dump 一次 iframe 列表方便排查
            if tick % 10 == 0 and info:
                last_dump = info.get("ifs")
                self.log(f"[probe {tick*0.5:.0f}s] iframes={last_dump}")
            time.sleep(0.5)

        if cf_iframe_seen:
            sb.save_screenshot(str(self.screenshot_dir / "debug_cf_appeared.png"))
            handle_turnstile(sb)
            sb.save_screenshot(str(self.screenshot_dir / "debug_after_cf.png"))
            time.sleep(2)
            curr = sb.get_current_url().lower()
            if "sign-in" in curr or "login" in curr:
                self.log("CF 通过但 URL 没跳，再点一次 Sign in...")
                try:
                    sb.click("button[type='submit']")
                except Exception:
                    pass
        else:
            self.log(f"ℹ️ 未检测到 CF Turnstile (最后 iframes={last_dump})")
            sb.save_screenshot(str(self.screenshot_dir / "debug_no_cf_seen.png"))

        # 终极检查
        time.sleep(2)
        if sb.execute_script(_EXISTS_JS):
            handle_turnstile(sb)

        # 等 URL 离开 sign-in（最多 25s）
        self.log("等待登录跳转 (最多 25s)...")
        for i in range(50):
            time.sleep(0.5)
            curr = sb.get_current_url().lower()
            if "sign-in" not in curr and "login" not in curr:
                self.log(f"✅ 已离开登录页 ({i*0.5:.1f}s) → {curr}")
                self._handle_social_prompt(sb)
                return True

        sb.save_screenshot(str(self.screenshot_dir / "login_fail_still_sign_in.png"))
        try:
            err = sb.execute_script(
                "return Array.from(document.querySelectorAll('[class*=\"error\"],[class*=\"alert\"],[role=\"alert\"]'))"
                ".map(e=>e.innerText).filter(Boolean).join(' | ').slice(0,300)"
            )
            if err:
                self.log(f"📋 页面错误提示: {err}")
        except Exception:
            pass
        self.log(f"⚠️ 仍在登录页: {sb.get_current_url()}")
        return False

    def _handle_social_prompt(self, sb):
        self.log("检查是否存在社交引导弹窗...")
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
                self.log(f"🎯 发现弹窗按钮坐标: ({coords['x']}, {coords['y']})")
                sb.save_screenshot(str(self.screenshot_dir / "social_pre_click.png"))
                try:
                    wi = sb.execute_script(_WININFO_JS)
                    bar = wi["oh"] - wi["ih"]
                    ax = coords["x"] + wi["sx"]
                    ay = coords["y"] + wi["sy"] + bar
                    _xdotool_click(ax, ay)
                    time.sleep(0.5)
                except Exception: pass
                try:
                    sb.execute_script("var b = document.querySelector('button.continue-btn'); if(b) b.click();")
                except Exception: pass
                time.sleep(3)
                sb.save_screenshot(str(self.screenshot_dir / "social_post_click.png"))
                self.log("✅ 弹窗处理指令执行完毕")
                return True
        except Exception as e:
            self.log(f"处理社交弹窗时发生非致命异常: {e}")
        return False

    def _do_renewal(self, sb):
        self.log("开始续期操作...")
        run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        old_expiry = self._get_expiry_time(sb)
        self.log(f"当前剩余时间: {old_expiry}")

        self.log("查找续期按钮...")
        btn_found = False
        try:
            btn_found = bool(sb.execute_script("""
                (function() {
                    var links = document.querySelectorAll('a[onclick*="handleServerRenewal"]');
                    for (var i = 0; i < links.length; i++) { links[i].click(); return true; }
                    var btns = document.querySelectorAll('a.action-button, button');
                    for (var j = 0; j < btns.length; j++) {
                        if (btns[j].textContent && btns[j].textContent.toLowerCase().includes('renew')) {
                            btns[j].click(); return true;
                        }
                    }
                    return false;
                })()
            """))
        except Exception as e:
            self.log(f"点击按钮出错: {e}")

        if btn_found:
            self.log("✅ 已点击续期按钮")
        else:
            self.log("❌ 找不到续期按钮")
            sb.save_screenshot(str(self.screenshot_dir / "renew_button_not_found.png"))
            return f"🎮 Zampto 续期通知\n\n🕒 运行时间: {run_time}\n🖥️ 服务器: 🇩🇪 Zampto (Auto)\n📊 续期结果: ❌ 失败 (找不到按钮)\n🕒 旧到期: {old_expiry or '未知'}"

        time.sleep(3)
        self._handle_cloudflare(sb)
        self.log("等待页面响应 (10秒)...")
        time.sleep(10)

        sb.save_screenshot(str(self.screenshot_dir / "renewal_result.png"))
        new_expiry = self._get_expiry_time(sb)
        self.log(f"续期后剩余时间: {new_expiry}")

        status_icon = "✅ 成功" if new_expiry else "⚠️ 异常 (时间未读取)"
        msg = f"🎮 Zampto 续期通知\n\n🕒 运行时间: {run_time}\n🖥️ 服务器: 🇮🇹 Zampto (Auto)\n📊 续期结果: {status_icon}\n🕒 旧到期: {old_expiry or '未知'}\n🕒 新到期: {new_expiry or '未知'}"
        return msg

    def _get_expiry_time(self, sb):
        try:
            page_text = sb.get_page_source()
            match = re.search(r"Expiry.*?([0-9]+\s*[a-zA-Z]+(?:\s*[0-9]+\s*[a-zA-Z]+)?)", page_text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
            match = re.search(r"(\d+)\s*day[s]?\s*(\d+)\s*h", page_text, re.IGNORECASE)
            if match:
                return f"{match.group(1)}d {match.group(2)}h"
            return None
        except Exception as e:
            self.log(f"读取时间出错: {e}")
            return None


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
