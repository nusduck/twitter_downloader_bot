# Development Documentation

This document outlines the architectural decisions and design patterns used in the refactored Twitter Downloader Bot.

## Architecture Overview

The project follows a **Modular Layered Architecture** to ensure separation of concerns and scalability.

```
/app
├── bot/           # Telegram Bot Interface Layer
│   ├── handlers/  # Command and Message handlers
│   ├── middlewares/
│   └── keyboards/ # Inline and Reply keyboards
├── core/          # Core Business Logic
│   ├── config.py  # Configuration management
│   └── utils/     # Shared utilities
└── downloader/    # Media Extraction Layer
    ├── base.py    # Abstract base class for downloaders
    ├── twitter.py # Specific Twitter implementation
    └── manager.py # Manager to handle extraction strategies
```

### 1. Modular Design

- **Interface Layer (`app/bot`)**: Purely handles Telegram interactions (parsing updates, sending messages). It knows *nothing* about how to download a tweet, only that it needs to call a service to do so.
- **Extraction Layer (`app/downloader`)**: Dedicated to parsing URLs and fetching media bytes. It returns standardized data objects (media URL, type, thumbnail), decoupling the bot from specific site logic.
- **Core Layer (`app/core`)**: Holds shared state, configuration loading, and logging setup.

### 2. Asynchronous & Performance

- **AsyncIO**: The entire pipeline is non-blocking. Network I/O (Twitter API calls, Telegram uploads) uses `aiohttp` and `aiogram`.
- **Local Bot API Support**: Designed to work with a local Telegram Bot API server. This bypasses the standard 50MB upload limit, enabling file uploads up to **2GB**.

### 3. Fallback Mechanism

Robustness is a key goal. The extraction logic includes a fallback strategy:

1. **Primary Extractor**: Attempts to use the primary method (e.g., API or direct scraping).
2. **Error Handling**: Network timeouts or parsing errors are caught gracefully.
3. **Fallback**: If the primary fails, the system can switch to alternative methods (if implemented) or return a user-friendly error without crashing the bot.

## Deployment Strategy

- **Docker-First**: The application is containerized.
- **Environment Isolation**: All secrets are loaded from `.env`, ensuring code portability and security.
