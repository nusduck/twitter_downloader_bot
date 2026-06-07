# Twitter Downloader Bot (Re-Architected)

[English](#english) | [中文](#chinese)

<a name="english"></a>
## 🇬🇧 English

A high-performance, asynchronous Telegram bot for downloading high-quality media (images & videos) from Twitter (X). Refactored for modularity, stability, and ease of deployment.

### Key Features
- **Asynchronous Core**: Built with `aiogram` and `asyncio` for high concurrency.
- **Large File Support**: Supports uploading files up to **2GB** (via Local Telegram API server).
- **High Quality**: Always attempts to fetch the best available resolution.
- **Modular Architecture**: Clean separation between Bot logic, Core services, and Downloaders.
- **Fallback Mechanism**: Robust error handling to ensure service continuity.
- **Docker Ready**: One-click deployment with Docker Compose.

### Installation

#### Prerequisites
- Docker & Docker Compose
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- (Optional) Twitter Cookies/Auth if required by specific extractors (configured in env)

#### 1. Clone & Configure
```bash
git clone https://github.com/your-username/twitter_downloader_bot.git
cd twitter_downloader_bot

# Copy example environment file
cp .env.example .env
```

#### 2. Environment Variables
Edit `.env` to configure your bot:

```ini
BOT_TOKEN=your_telegram_bot_token
ADMIN_ID=your_admin_user_id
LOG_LEVEL=INFO

# Optional: Local Telegram API URL for large file uploads (>50MB)
# TELEGRAM_API_URL=http://telegram-bot-api:8081

# Downloader Configs
TWITTER_AUTH_TOKEN=...
```

#### 3. Run with Docker
```bash
docker-compose up -d --build
```

### Shortcut Backend Endpoint

Enable the optional HTTP endpoint to let iOS Shortcuts or another backend submit an X/Twitter URL and have the bot send the media to a Telegram chat:

```ini
SHORTCUT_ENABLED=true
SHORTCUT_HOST=0.0.0.0
SHORTCUT_PORT=8080
SHORTCUT_TOKEN=change_me
SHORTCUT_CHAT_ID=your_target_chat_id
```

Call it with JSON:

```bash
curl -X POST http://localhost:8080/shortcut \
  -H "Authorization: Bearer change_me" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://x.com/user/status/1234567890"}'
```

You can also pass `chat_id` in the request body to override `SHORTCUT_CHAT_ID`.

---

<a name="chinese"></a>
## 🇨🇳 中文

这是一个高性能、异步的 Telegram 机器人，用于下载 Twitter (X) 上的高质量媒体资源（图片与视频）。本项目经过重构，旨在提供模块化、高稳定性和易部署的解决方案。

### 核心功能
- **全异步内核**：基于 `aiogram` 和 `asyncio` 构建，支持高并发处理。
- **大文件支持**：支持上传高达 **2GB** 的文件（需配合本地 Telegram API 服务器）。
- **最高画质**：自动解析并下载最高分辨率的媒体文件。
- **模块化架构**：Bot 逻辑、核心服务与下载器分离，易于维护和扩展。
- **Fallback 机制**：健壮的错误处理机制，确保服务可用性。
- **Docker 部署**：支持 Docker Compose 一键启动。

### 安装指南

#### 前置要求
- Docker & Docker Compose
- Telegram Bot Token (获取自 [@BotFather](https://t.me/BotFather))

#### 1. 克隆与配置
```bash
git clone https://github.com/your-username/twitter_downloader_bot.git
cd twitter_downloader_bot

# 复制配置文件
cp .env.example .env
```

#### 2. 环境变量配置
编辑 `.env` 文件：

```ini
BOT_TOKEN=你的BotToken
ADMIN_ID=你的管理员ID
LOG_LEVEL=INFO

# 可选：本地 Telegram API 地址（用于支持 >50MB 的大文件上传）
# TELEGRAM_API_URL=http://telegram-bot-api:8081

# 下载器配置
TWITTER_AUTH_TOKEN=...
```

#### 3. Docker 启动
```bash
docker-compose up -d --build
```

### Shortcut 后端接口

可以开启可选 HTTP 接口，让 iOS 快捷指令或其他后端提交 X/Twitter URL，并由 bot 把媒体发送到 Telegram 聊天：

```ini
SHORTCUT_ENABLED=true
SHORTCUT_HOST=0.0.0.0
SHORTCUT_PORT=8080
SHORTCUT_TOKEN=change_me
SHORTCUT_CHAT_ID=目标聊天ID
```

JSON 调用示例：

```bash
curl -X POST http://localhost:8080/shortcut \
  -H "Authorization: Bearer change_me" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://x.com/user/status/1234567890"}'
```

也可以在请求 body 里传 `chat_id` 覆盖 `SHORTCUT_CHAT_ID`。
