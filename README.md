# NbgAlienDrop

## Description

**中文：** NbgAlienDrop 是一个基于 Flask 与 iOS Shortcuts 的 Windows + iOS 局域网协作工具，实现 iPhone 与 Windows 之间的剪贴板双向同步以及 OTP 验证码自动识别与推送。

**English:** NbgAlienDrop is a LAN bridge between iPhone and Windows built with Flask and iOS Shortcuts. It provides two-way clipboard sync and automatic OTP code extraction & forwarding between your phone and PC.

---

## Features

- iPhone ↔ Windows LAN communication over HTTP
- Automatic OTP code recognition (extracts 4–8 digit codes)
- Two-way clipboard sync between phone and PC
- Runs in the background via Windows system tray
- Simple API key based access control (`X-API-KEY` header)
- Native Windows toast notifications via `winotify`

---

## API Endpoints

All requests must include the `X-API-KEY` header matching `api_key` in `config.json`.

| Method | Endpoint         | Purpose                                  |
|--------|------------------|------------------------------------------|
| POST   | `/clipboard/set` | Push clipboard content from iPhone to PC |
| GET    | `/clipboard/get` | Pull clipboard content from PC to iPhone |
| POST   | `/otp`           | Submit text for OTP extraction & forward |

Example:

```bash
curl -X POST http://<ip>:5000/clipboard/set \
  -H "X-API-KEY: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"text": "hello from iPhone"}'

curl http://<ip>:5000/clipboard/get \
  -H "X-API-KEY: your-secret-key"
```

---

## Configuration

Configuration is stored in `core/config.json` and is generated/loaded at runtime.

```json
{
  "app_name": "NbgAlienDrop",
  "port": 5000,
  "api_key": "your-secret-key",
  "clipboard_notifications": true,
  "otp_notifications": true
}
```

| Field | Description |
|-------|-------------|
| `app_name` | Application display name (used in tray and notifications) |
| `port` | Port the Flask server listens on |
| `api_key` | Shared secret required in the `X-API-KEY` request header |
| `clipboard_notifications` | Toggle Windows toasts on clipboard sync |
| `otp_notifications` | Toggle Windows toasts on OTP detection |

The API key is a lightweight LAN-level access control mechanism and is not intended for production-grade security.

---

## iOS Shortcut Setup

Two shortcuts are provided in `assets/`:

| Shortcut | Purpose | Endpoint | Method |
|----------|---------|----------|--------|
| `Nbg-AlienDrop.shortcut` | Push / Pull clipboard synchronization | `/clipboard/set` & `/clipboard/get` | POST / GET |
| `Nbg-AutoPush.shortcut`  | Auto-detect OTP from SMS and forward to PC | `/otp` | POST |

Host example: `http://192.168.1.10:5000`

Setup steps:

1. Open each `.shortcut` file on your iPhone to import it.
2. Edit the **Host** field, e.g. `http://192.168.1.10:5000`.
3. Edit the **API Key** field to match `api_key` in `config.json`.
4. (Optional) For `Nbg-AutoPush`, enable the *Automation* trigger on new SMS.

---

## Project Structure

```
PhoneBridge/
│  README.md
│  requirements.txt
│  .gitignore
├─assets/
│   Nbg-AlienDrop.shortcut
│   Nbg-AutoPush.shortcut
└─core/
    otp_server.py
    config.json
    logo.ico
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the server

```bash
python core/otp_server.py
```

When launched, the application runs in background mode with a system tray icon.
The Flask server listens on the port defined in `config.json`.

### 3. (Optional) Build a Windows executable

`config.json` is generated/loaded at runtime and should NOT be bundled.

```bash
pyinstaller --noconfirm --onefile --windowed ^
  --icon core/logo.ico ^
  --add-data "core/logo.ico;." ^
  core/otp_server.py
```

The resulting binary will be available in `dist/`.

---

## Notes

- iPhone and Windows must be on the **same LAN**.
- Allow `python.exe` (or the built `.exe`) through the Windows Firewall on the configured port.
- OTP extraction uses a simple regex matching 4–8 consecutive digits; non-numeric codes are ignored.
- This project is intended for trusted local networks only; it does not implement TLS.

---

## Credits

- [Flask](https://flask.palletsprojects.com/)
- [pyperclip](https://github.com/asweigart/pyperclip)
- [winotify](https://github.com/versa-syahptr/winotify)
- [pystray](https://github.com/moses-palmer/pystray)
- [Pillow (PIL)](https://python-pillow.org/)
- Apple Shortcuts

---

## License

Released under the [MIT License](LICENSE).
