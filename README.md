```markdown
# NbgAlienDrop

Lightweight LAN service for OTP forwarding and clipboard synchronization between iOS and Windows.

NbgAlienDrop 是一个面向局域网环境的轻量级 iPhone / Windows 协同工具，旨在实现验证码自动转发与剪贴板双向同步。

## 🛠️ Features

* **智能验证码解析 (Smart OTP)**：利用正则规则自动提取短信中的 4-8 位验证码，过滤年份、时间等噪声数字。
* **双向剪贴板同步**：
    * **Push to PC**: 将手机剪贴板内容发送并覆盖至电脑剪贴板。
    * **Pull from PC**: 手机主动拉取电脑当前的剪贴板文本。
* **全英文通知风格**：Windows 端通知文案与 iOS 快捷指令逻辑高度对齐（Pushed to PC / Pulled from PC ✅）。
* **工程化安全机制**：支持自定义 `X-API-KEY` 请求头验证，确保局域网内设备通信安全。
* **自动化配置管理**：首次运行自动生成 `config.json`；支持修改端口与通知开关（需重启生效）。

## ⚙️ Configuration

程序启动后若检测不到配置文件，会自动生成 `config.json`。请确保手机端的 API Key 与此处一致：

```json
{
    "app_name": "NbgAlienDrop",
    "port": 5000,
    "api_key": "123456",
    "clipboard_notifications": true,
    "otp_notifications": true
}

```

## 📱 iOS Shortcut Setup

导入 `assets/` 目录下的 `.shortcut` 文件，并根据实际网络环境修改 **host** 变量：

> **Host 示例**：`http://192.168.x.x:5000` (请务必包含端口号，并确保与 `config.json` 一致)

| 功能模块 | 对应文件 | 使用方法 |
| --- | --- | --- |
| **主程序 (Push/Pull)** | `Nbg-AlienDrop.shortcut` | 运行后选择 **Push**（发送到电脑）或 **Pull**（从电脑取回） |
| **验证码自动推送** | `Nbg-AutoPush.shortcut` | 在 iOS **自动化** 中设置：接收到信息包含 "验证码" 时 -> 执行此快捷指令 |

## 📂 Project Structure

```text
C:.
│  .gitignore
│  README.md
│  requirements.txt
├─assets                # iOS 快捷指令本体
│      Nbg-AlienDrop.shortcut
│      Nbg-AutoPush.shortcut
└─core                  # 核心源代码
        logo.ico
        otp_server.py

```

## 💖 Credits

本项目的开发灵感及部分逻辑思路源于 [AirDropPlus](https://github.com/yeyt97/AirDropPlus)。
NbgAlienDrop 在其基础上针对验证码正则解析、配置持久化以及安全验证进行了优化。

## 📄 License

本项目目前采用私有化开发模式，建议仅供个人学习与局域网环境使用。

```

```