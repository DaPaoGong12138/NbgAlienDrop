import re
import subprocess
import time
import pyperclip
import threading
import os
import webbrowser
import sys
import json
import ctypes
from ctypes import wintypes
from datetime import datetime
from flask import Flask, request, abort
from winotify import Notification
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw, ImageGrab

# --- 键盘/鼠标模拟 (ctypes SendInput，无额外依赖) ---

ULONG_PTR = ctypes.c_size_t
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120

# 扩展键（方向键等，发送扫描码时必须带 EXTENDEDKEY 标志，否则会被误判）
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D}

# 虚拟键码
VK = {
    "space": 0x20, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "j": 0x4A, "l": 0x4C, "m": 0x4D, "f": 0x46, "h": 0x48, "d": 0x44, "b": 0x42, "c": 0x43,
    "tab": 0x09, "alt": 0x12,
    "vol_mute": 0xAD, "vol_down": 0xAE, "vol_up": 0xAF,
}

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

_user32 = ctypes.windll.user32

def _key_event(vk_code, keyup=False):
    """构造单个键盘事件（带扫描码，兼容网页 event.code 识别）"""
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.union.ki.wVk = vk_code
    # MAPVK_VK_TO_VSC = 0，补上扫描码，抖音等网页靠 event.code 判断键位
    try:
        inp.union.ki.wScan = _user32.MapVirtualKeyW(vk_code, 0)
    except Exception:
        inp.union.ki.wScan = 0
    flags = KEYEVENTF_EXTENDEDKEY if vk_code in EXTENDED_VKS else 0
    if keyup:
        flags |= KEYEVENTF_KEYUP
    inp.union.ki.dwFlags = flags
    return inp

def send_key(vk_code):
    """模拟按键：按下 + 抬起"""
    inputs = (INPUT * 2)()
    inputs[0] = _key_event(vk_code, False)
    inputs[1] = _key_event(vk_code, True)
    _user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))

def _send(arr):
    _user32.SendInput(len(arr), ctypes.byref(arr), ctypes.sizeof(INPUT))

def send_key_down(vk_code):
    """仅按下按键（不松开）"""
    one = (INPUT * 1)(); one[0] = _key_event(vk_code, False); _send(one)

def send_key_up(vk_code):
    """仅松开按键"""
    one = (INPUT * 1)(); one[0] = _key_event(vk_code, True); _send(one)

# 追踪当前被"保持"按下的键（用于切换开关类功能）
_held_keys = set()

def toggle_hold_key(vk_code):
    """切换按键保持状态：未按住则按下，已按住则松开。返回是否处于按住状态"""
    if vk_code in _held_keys:
        send_key_up(vk_code)
        _held_keys.discard(vk_code)
        return False
    else:
        send_key_down(vk_code)
        _held_keys.add(vk_code)
        return True

def send_alt_tab():
    """模拟 Alt+Tab：按住 Alt → 按住 Tab(约100ms，人类点击时长) → 松开 Tab → 松开 Alt"""
    alt = VK["alt"]
    tab = VK["tab"]
    try:
        # 1. 按住 Alt
        a = (INPUT * 1)(); a[0] = _key_event(alt, False); _send(a)
        time.sleep(0.05)
        # 2. 按住 Tab
        t = (INPUT * 1)(); t[0] = _key_event(tab, False); _send(t)
        time.sleep(0.10)   # Tab 按住时长 ≈ 人手点击
        # 3. 松开 Tab（切换器弹出）
        t = (INPUT * 1)(); t[0] = _key_event(tab, True); _send(t)
        # 4. 短暂保持 Alt，让切换器可见
        time.sleep(0.15)
    finally:
        # 5. 松开 Alt
        a = (INPUT * 1)(); a[0] = _key_event(alt, True); _send(a)

def send_scroll(direction):
    """模拟鼠标滚轮。direction: 'up' 或 'down'"""
    delta = WHEEL_DELTA if direction == "up" else -WHEEL_DELTA
    inputs = (INPUT * 1)()
    inputs[0].type = INPUT_MOUSE
    inputs[0].union.mi.mouseData = delta & 0xFFFFFFFF  # 负数转无符号
    inputs[0].union.mi.dwFlags = MOUSEEVENTF_WHEEL
    _user32.SendInput(1, ctypes.byref(inputs), ctypes.sizeof(INPUT))

# --- 窗口枚举与激活（替代不可靠的 Alt+Tab） ---

_EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

def _find_windows_by_title(keywords):
    """枚举所有可见窗口，返回标题包含任意关键词的窗口句柄列表"""
    found = []

    def callback(hwnd, lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        for kw in keywords:
            if kw.lower() in title.lower():
                found.append(hwnd)
                break
        return True

    _user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return found

def _force_foreground(hwnd):
    """可靠地把窗口带到前台（绕过 Windows 前台锁）"""
    fg = _user32.GetForegroundWindow()
    if fg == hwnd:
        return True

    target_tid = _user32.GetWindowThreadProcessId(hwnd, None)
    fg_tid = _user32.GetWindowThreadProcessId(fg, None) if fg else 0
    current_tid = ctypes.windll.kernel32.GetCurrentThreadId()

    attached = []
    if target_tid and target_tid != current_tid:
        _user32.AttachThreadInput(target_tid, current_tid, True)
        attached.append(target_tid)
    if fg_tid and fg_tid != current_tid and fg_tid != target_tid:
        _user32.AttachThreadInput(fg_tid, current_tid, True)
        attached.append(fg_tid)

    try:
        _user32.ShowWindow(hwnd, 9)  # SW_RESTORE（若最小化则还原）
        _user32.SetForegroundWindow(hwnd)
        _user32.BringWindowToTop(hwnd)
    finally:
        for tid in attached:
            _user32.AttachThreadInput(tid, current_tid, False)

    return _user32.GetForegroundWindow() == hwnd

def focus_window_by_title(keywords):
    """把标题包含指定关键词的窗口带到前台。返回是否成功"""
    hwnds = _find_windows_by_title(keywords)
    if not hwnds:
        return False
    return _force_foreground(hwnds[0])

def focus_douyin():
    """优先找抖音窗口，找不到则退回到任意浏览器窗口"""
    if focus_window_by_title(['抖音', 'douyin']):
        return 'douyin'
    if focus_window_by_title(['chrome', 'edge', 'firefox', 'browser', '浏览器', 'bilibili']):
        return 'browser'
    return None

def list_windows():
    """枚举所有可见窗口，返回 [{id, title}]（按 Z 序，最近激活的在前）"""
    windows = []

    def callback(hwnd, lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if title and title != "Program Manager":
            windows.append({"id": int(hwnd), "title": title})
        return True

    _user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return windows

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
    if request.endpoint in ('health', 'web_panel', None):
        return
    if request.path == '/web':
        return
    # CORS preflight (browsers send OPTIONS without custom headers)
    if request.method == 'OPTIONS':
        return
    if request.headers.get("X-API-KEY") != API_KEY:
        abort(403)

@app.errorhandler(403)
def forbidden(e):
    return {"status": "error", "message": "Invalid API Key"}, 403

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-KEY"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

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

# --- PC 远程控制接口 ---

@app.route('/screenshot', methods=['POST'])
def take_screenshot():
    """截取当前屏幕，返回 base64 编码的图片"""
    import base64, io
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        # 缩放到适合手机查看的尺寸（宽度 800px）
        w, h = img.size
        if w > 800:
            ratio = 800 / w
            img = img.resize((800, int(h * ratio)))
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=75)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return {
            "status": "ok",
            "width": img.size[0],
            "height": img.size[1],
            "image": f"data:image/jpeg;base64,{b64}",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


# --- 图片剪贴板接口 ---

@app.route('/image/set', methods=['POST'])
def set_image():
    """手机发图片(base64) → 写入 Windows 剪贴板"""
    import base64, io, tempfile
    data = request.json or {}
    b64_str = (data.get("image") or "").strip()
    if not b64_str:
        return {"status": "error", "message": "image is required"}, 400
    if "," in b64_str and b64_str.startswith("data:"):
        b64_str = b64_str.split(",", 1)[1]
    try:
        raw = base64.b64decode(b64_str)
        img = Image.open(io.BytesIO(raw))
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(tmp.name, "PNG")
        tmp.close()
        ps_cmd = (
            f'Add-Type -AssemblyName System.Windows.Forms;'
            f'[Windows.Forms.Clipboard]::SetImage([System.Drawing.Image]::FromFile("{tmp.name}"))'
        )
        subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, timeout=10)
        try: os.unlink(tmp.name)
        except: pass
        return {"status": "ok", "width": img.size[0], "height": img.size[1]}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@app.route('/image/get', methods=['POST'])
def get_image():
    """获取 Win 剪贴板图片 → 返回 base64 给手机"""
    import base64, io, tempfile
    try:
        # 方法1: PIL grabclipboard
        img = ImageGrab.grabclipboard()
        if img is not None and isinstance(img, Image.Image):
            pass  # got it
        elif img is not None and isinstance(img, list) and len(img) > 0:
            img = Image.open(img[0])
        else:
            # 方法2: 用 PowerShell 导出剪贴板图片到临时文件
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            ps = (
                f'Add-Type -AssemblyName System.Windows.Forms;'
                f'$img = [Windows.Forms.Clipboard]::GetImage();'
                f'if ($img) {{ $img.Save("{tmp.name}", [System.Drawing.Imaging.ImageFormat]::Png); "ok" }} else {{ "empty" }}'
            )
            r = subprocess.run(["powershell", "-Command", ps], capture_output=True, text=True, timeout=10)
            if "empty" in r.stdout:
                return {"status": "error", "message": "剪贴板中没有图片"}
            img = Image.open(tmp.name)

        w, h = img.size
        if w > 1200:
            img = img.resize((1200, int(h * 1200 / w)))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return {"status": "ok", "width": img.size[0], "height": img.size[1], "image": f"data:image/jpeg;base64,{b64}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@app.route('/command', methods=['POST'])
def run_command():
    """
    执行系统命令或预设操作。
    请求体: {"cmd": "关机"}  或  {"cmd": "shutdown /s /t 60"}
    """
    data = request.json or {}
    cmd = (data.get("cmd") or "").strip()
    if not cmd:
        return {"status": "error", "message": "cmd is required"}, 400

    # 预设中文命令映射
    preset = {
        "关机": "shutdown /s /t 60",
        "取消关机": "shutdown /a",
        "重启": "shutdown /r /t 60",
        "锁屏": "rundll32.exe user32.dll,LockWorkStation",
        "休眠": "shutdown /h",
    }

    # 如果是预设命令则翻译，否则直接作为 shell 命令执行
    actual_cmd = preset.get(cmd, cmd)

    try:
        result = subprocess.run(
            actual_cmd, shell=True,
            capture_output=True, text=True,
            timeout=30, cwd=os.path.expanduser("~"),
        )
        out = result.stdout.strip() + "\n" + result.stderr.strip()
        return {
            "status": "ok",
            "command": cmd,
            "output": out.strip() or "(executed)",
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Command timed out (30s)"}, 500
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@app.route('/remote', methods=['POST'])
def remote_control():
    """
    远程遥控器。action 可选：
      scroll_up / scroll_down      — 鼠标滚轮（切换视频）
      key_j / key_space / key_h / key_m / key_l   — 按键
      arrow_up / arrow_down / arrow_left / arrow_right
      vol_up / vol_down / vol_mute
      alt_tab                      — Alt+Tab 切换窗口
    """
    data = request.json or {}
    action = (data.get('action') or '').strip()
    if not action:
        return {'status': 'error', 'message': 'action required'}, 400

    try:
        if action == 'scroll_up':
            send_scroll('up')
        elif action == 'scroll_down':
            send_scroll('down')
        elif action == 'alt_tab':
            send_alt_tab()
        elif action == 'focus_douyin':
            target = focus_douyin()
            if target is None:
                return {'status': 'error', 'message': '未找到抖音/浏览器窗口'}, 404
            return {'status': 'ok', 'action': action, 'target': target}
        elif action == 'toggle_hold':
            key_name = (data.get('key') or '').strip()
            vk = VK.get(key_name)
            if vk is None:
                return {'status': 'error', 'message': 'unknown key'}, 400
            held = toggle_hold_key(vk)
            return {'status': 'ok', 'action': action, 'key': key_name, 'held': held}
        elif action.startswith('key_'):
            vk = VK.get(action[4:])
            if vk is None:
                return {'status': 'error', 'message': 'unknown key'}, 400
            send_key(vk)
        elif action.startswith('arrow_'):
            vk = VK.get(action[6:])
            if vk is None:
                return {'status': 'error', 'message': 'unknown arrow'}, 400
            send_key(vk)
        elif action in ('vol_up', 'vol_down', 'vol_mute'):
            send_key(VK[action])
        else:
            return {'status': 'error', 'message': 'unknown action'}, 400
        return {'status': 'ok', 'action': action}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500


@app.route('/auth/verify', methods=['POST'])
def auth_verify():
    """Lightweight API key verification for login page"""
    return {'status': 'ok', 'message': 'authenticated'}


@app.route('/windows/list', methods=['POST'])
def windows_list():
    """列出所有可见窗口（用于手机端窗口切换器）"""
    return {'status': 'ok', 'windows': list_windows()}


@app.route('/windows/focus', methods=['POST'])
def windows_focus():
    """聚焦指定窗口（按句柄 id）"""
    data = request.json or {}
    hwnd = data.get('id')
    if not hwnd:
        return {'status': 'error', 'message': 'id required'}, 400
    try:
        ok = _force_foreground(int(hwnd))
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500
    if ok:
        return {'status': 'ok'}
    return {'status': 'error', 'message': '无法聚焦该窗口'}, 500


@app.route('/web')
def web_panel():
    """手机端控制面板 - 对话列表 + 聊天界面"""
    html_path = resource_path("web.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

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
            MenuItem("Web Panel", lambda: webbrowser.open(f"http://127.0.0.1:{PORT}/web")),
            MenuItem("Exit", quit_app)
        )
    )
    icon.run()