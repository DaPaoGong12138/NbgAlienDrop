# NbgAlienDrop

Lightweight LAN utility for iPhone OTP forwarding and clipboard synchronization between iOS and Windows.

NbgAlienDrop 是一个面向局域网环境的轻量级 iPhone / Windows 协同工具，用于验证码自动转发与剪贴板双向同步。

---

## 🛠️ Features

- **智能验证码解析 (Smart OTP)**
  自动提取短信中的 4–8 位验证码，并过滤年份、时间等干扰数字。

- **双向剪贴板同步**
  - **Pushed to PC**：手机剪贴板 → 电脑剪贴板
  - **Pulled from PC**：电脑剪贴板 → 手机

- **系统托盘常驻运行**
  Windows 后台运行，不占用前台窗口

- **原生通知系统**
  基于 `winotify` 的 Windows Toast 通知

- **工程化配置系统**
  自动生成 `config.json`，支持端口与功能开关配置

- **API Key 访问控制**
  支持 `X-API-KEY` 请求头验证（局域网安全控制）

---

## ⚙️ Configuration

首次运行会自动生成 `config.json`：

```json
{
    "app_name": "NbgAlienDrop",
    "port": 5000,
    "api_key": "123456",
    "clipboard_notifications": true,
    "otp_notifications": true
}
```

> 修改配置后需要重启程序生效。

---

## 📱 iOS Shortcut Setup

导入 `assets/` 目录下的快捷指令文件：

| 功能       | 文件                       | 说明             |
| -------- | ------------------------ | -------------- |
| 剪贴板同步    | `Nbg-AlienDrop.shortcut` | Push / Pull 模式 |
| OTP 自动推送 | `Nbg-AutoPush.shortcut`  | 自动发送验证码        |

---

### 🌐 Host 配置

在快捷指令中修改服务器地址：

```
http://<your-ip>:5000
```

示例：

```
http://192.168.1.10:5000
```

---

## 📂 Project Structure

```
PhoneBridge/
│  README.md
│  requirements.txt
│  .gitignore
│
├─assets/
│      Nbg-AlienDrop.shortcut
│      Nbg-AutoPush.shortcut
│
└─core/
       otp_server.py
       config.json
       logo.ico
```

---

## 🚀 Quick Start

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行服务

```bash
python core/otp_server.py
```

### 3. 打包（可选）

```bash
pyinstaller --noconsole --onefile ^
--name "NbgAlienDrop" ^
--icon="core/logo.ico" ^
--add-data "core/logo.ico;." ^
core/otp_server.py
```

---

## 💡 Notes

* 默认监听端口：`5000`
* 必须保证手机与电脑在同一局域网
* API Key 可自行修改（建议避免公网暴露）

---

## 💖 Credits

Inspired by AirDrop-style LAN tools.

This project extends:

* OTP extraction automation
* iOS shortcut integration
* lightweight LAN API design

---

## 📄 License

MIT License (recommended for open source usage)
