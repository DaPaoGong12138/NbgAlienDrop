import re
import pyperclip
import threading
import os
import webbrowser
import sys
import json
from datetime import datetime
from flask import Flask, request, abort
from winotify import Notification
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw

# --- 环境适配逻辑 ---

def resource_path(relative_path):
    """ 获取内置资源路径（专用于打包入 exe 的 logo.ico） """
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

def get_config_full_path():
    """ 获取配置文件物理路径（确保在 .exe 同级目录生成，对用户可见） """
    if getattr(sys, 'frozen', False):
        # 打包后，返回 .exe 所在的真实物理目录
        return os.path.join(os.path.dirname(sys.executable), "config.json")
    # 开发环境下，返回脚本所在目录
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    target_path = get_config_full_path()
    
    # 默认配置字典
    default_config = {
        "app_name": "NbgAlienDrop",
        "port": 5000,
        "api_key": "123456",
        "clipboard_notifications": True,
        "otp_notifications": True
    }

    # 如果不存在配置文件则自动生成
    if not os.path.exists(target_path):
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to create config: {e}")
        return default_config

    # 读取并更新配置，确保新增字段能获取默认值
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
            default_config.update(user_config)
            return default_config
    except Exception:
        return default_config

# --- 全局配置初始化 ---
CONFIG = load_config()
PORT = CONFIG.get("port", 5000)
API_KEY = CONFIG.get("api_key") or "123456"
APP_NAME = CONFIG.get("app_name", "NbgAlienDrop")

app = Flask(__name__)

# --- 安全验证逻辑 ---

@app.before_request
def verify_api_key():
    if request.endpoint == 'health':
        return
    if request.headers.get("X-API-KEY") != API_KEY:
        abort(403)

@app.errorhandler(403)
def forbidden(e):
    return {"status": "error", "message": "Invalid API Key"}, 403

# --- 通知逻辑 ---

def send_dual_notifications(raw_msg, code, now_time):
    """ 验证码双重通知：解析窗 + 原始备份窗 """
    if not CONFIG.get("otp_notifications", True):
        return

    parsed_msg = f"Code: {code}\nTime: {now_time}\n[✅ Auto-copied to clipboard]" if code else f"Code: Not Found\nTime: {now_time}\n[❌ Extraction Failed]"
    
    Notification(
        app_id=f"{APP_NAME}_OTP",
        title="OTP Recognized",
        msg=parsed_msg
    ).show()

    Notification(
        app_id=f"{APP_NAME}_Raw",
        title="Original Message Backup",
        msg=raw_msg
    ).show()

def send_clipboard_notification(content, direction="received"):
    """ 剪贴板同步通知：Pushed / Pulled 风格 """
    if not CONFIG.get("clipboard_notifications", True):
        return

    preview = content[:30] + ("..." if len(content) > 30 else "")
    
    if direction == "received":
        display_title = "Pushed to PC ✅"
        status_text = f"Content: {preview}\n[Already copied to clipboard]"
    else:
        display_title = "Pulled from PC ✅"
        status_text = f"Content: {preview}\n[Synced to mobile device]"
    
    Notification(
        app_id=APP_NAME,
        title=display_title,
        msg=status_text
    ).show()

# --- Flask 路由 ---

@app.route('/')
def health():
    return {"status": f"{APP_NAME} Service is running", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

@app.route('/clipboard/set', methods=['POST'])
def set_clipboard():
    data = request.json or {}
    if "content" not in data:
        return {"status": "error"}, 400
    content = data["content"]
    try:
        pyperclip.copy(content)
    except Exception:
        pass
    send_clipboard_notification(content, direction="received")
    return {"status": "ok"}

@app.route('/clipboard/get', methods=['GET'])
def get_clipboard():
    content = pyperclip.paste()
    if content:
        send_clipboard_notification(content, direction="sent")
    else:
        if CONFIG.get("clipboard_notifications", True):
            Notification(
                app_id=APP_NAME, 
                title="Pulled from PC ⚠", 
                msg="[PC clipboard is empty]"
            ).show()
    return {"status": "ok", "content": content}

@app.route('/otp', methods=['POST'])
def otp():
    data = request.json or {}
    msg = data.get("msg", "")
    code = None
    # 正则提取逻辑：匹配4-8位数字，排除常见年份干扰
    kw_pattern = r'(?:验证码|校验码|验证密码|动态码|码是|Code)[:：\s-]{0,3}(\d{4,8})'
    match = re.search(kw_pattern, msg, re.IGNORECASE)
    if match:
        code = match.group(1)
    else:
        back_matches = re.findall(r'\b(\d{4,8})\b(?![分位秒])', msg)
        if back_matches:
            filtered = [m for m in back_matches if not m.startswith('202')]
            code = filtered[0] if filtered else None

    now_time = datetime.now().strftime("%H:%M:%S")
    if code:
        pyperclip.copy(code)
    send_dual_notifications(msg, code, now_time)
    return {"status": "ok", "code": code}

# --- 托盘与运行逻辑 ---

def create_image():
    """ 兜底图标绘制 """
    image = Image.new('RGB', (64, 64), (30, 144, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill=(255, 255, 255))
    draw.text((22, 18), "PB", fill=(30, 144, 255))
    return image

def quit_app(icon, item):
    icon.stop()
    sys.exit(0)

def run_server():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
    
def get_icon():
    icon_path = resource_path("logo.ico")
    if os.path.exists(icon_path):
        return Image.open(icon_path)
    return create_image()
    
if __name__ == '__main__':
    # 启动后端 Flask 线程
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # 启动系统托盘图标
    icon = Icon(
        APP_NAME,
        get_icon(),
        f"{APP_NAME} Backend Service",
        menu=Menu(
            MenuItem("Status Page", lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")),
            MenuItem("Exit", quit_app)
        )
    )
    icon.run()