<div align="center">

# Telegram Media Resource Management Bot

**A feature-rich Telegram bot focusing on media resource management, Emby integration, automatic downloads, and Quark Drive resource management**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://hub.docker.com/r/beocean/tgbot)

[Features](#-features) • [Quick Start](#-quick-start) • [Configuration](#-configuration) • [User Guide](#-user-guide) • [Development Guide](#-development-guide)

</div>

---

## 📑 Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
  - [Prerequisites](#prerequisites)
  - [Docker Deployment](#docker-deployment)
  - [Local Development](#local-development)
- [Configuration](#-configuration)
  - [Environment Variables](#environment-variables-configuration)
  - [Personal Service Configuration](#personal-service-configuration)
- [User Guide](#-user-guide)
  - [Basic Commands](#basic-commands)
  - [Resource Search](#resource-search)
  - [QAS Download Management](#qas-download-management)
  - [Emby Integration](#emby-integration)
- [Development Guide](#-development-guide)
- [Project Structure](#-project-structure)
- [FAQ](#-faq)
- [Acknowledgements](#-acknowledgements)
- [License](#-license)

---

## ✨ Features

### 📺 Media Resource Search
- **Multi-platform search**: Supports multiple resource search platforms such as CloudSaver and PanSou.
- **TMDB Integration**: Integrates The Movie Database API to retrieve detailed movie/TV show information.
- **Link Validation**: Automatically checks the validity of Quark Drive links.
- **Smart Classification**: Supports classification for TV shows, movies, and multi-season mode recognition.

### 🔄 QAS Project Integration
- **Quark Auto Save Integration**: Integrates the [QAS project](https://github.com/Cp0204/quark-auto-save) to implement automatic downloads from Quark Drive.
- **AI Enhancement**: Uses AI to generate download parameters and regular expressions, intelligently identifying season numbers.
- **Task Management**: Create, update, delete, and run download tasks, with automatic classification for multi-season TV series.
- **Regex Matching**: Intelligent file filtering and renaming rules, supporting custom patterns and replacements.

### 🎬 Emby Integration
- **Library Management**: Search and manage resources within the Emby media library.
- **Library Refresh**: Remotely refresh the Emby media library.
- **Notification Config**: Manage notifications for new media added to Emby.
- **Metadata Retrieval**: Retrieve detailed media information and posters.

### 🤖 AI Capabilities
- **Smart Parameter Generation**: AI automatically generates pattern and replace rules for download tasks.
- **Season Classification**: AI automatically identifies and classifies TV series seasons.
- **Multi-AI Providers**: Supports multiple AI services including OpenAI, DeepSeek, and Kimi.
- **Dynamic Configuration**: Configurable via the `/upsert_configuration` command, allowing independent AI settings for each user.

### 👥 User Management
- **Role-based Permissions**: Supports three-level permission management: Owner, Admin, and User.
- **Command Access**: Role-based access control for bot commands.
- **User Registration**: Simple user registration and permission assignment.

### 📊 Task Scheduling
- **Scheduled Tasks**: Supports scheduled reminders and task scheduling.
- **Job Management**: Create, view, and delete scheduled jobs.

---

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose (Recommended)
- Or Python 3.8+ environment (for local development)
- Telegram Bot Token (obtained from [@BotFather](https://t.me/botfather))

### Docker Deployment (Recommended)

1. **Create deployment directory**
   ```bash
   mkdir tgbot && cd tgbot
   ```

2. **Create `docker-compose.yml` file**
   ```yaml
   version: '3.8'

   services:
     tgbot:
       image: beocean/tgbot:latest
       container_name: tgbot
       restart: unless-stopped
       environment:
         # Required configuration
         - TG_BOT_TOKEN=your_telegram_bot_token
         - CRYPTO_PASSWORD=your_strong_password_16chars
         - CRYPTO_SALT=your_random_salt_16chars

         # Optional configuration
         - TMDB_API_KEY=your_tmdb_api_key
         - TMDB_POSTER_BASE_URL=https://image.tmdb.org/t/p/original
         - PANSOU_HOST=https://your-pansou-host.com
         - CLOUD_SAVER_HOST=https://your-cloud-saver-host.com
         - CLOUD_SAVER_USERNAME=your_username
         - CLOUD_SAVER_PASSWORD=your_password
       volumes:
         - ./data:/app/db/data
   ```

3. **Start service**
   ```bash
   docker compose up -d
   ```

4. **Check logs**
   ```bash
   docker compose logs -f
   ```

5. **Use in Telegram**
   - Find your bot.
   - Send `/register` to register.
   - Send `/help` to view available commands.

### Local Development

1. **Clone repository**
   ```bash
   git clone <repository-url>
   cd tgbot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   ```bash
   export TG_BOT_TOKEN=your_telegram_bot_token
   export CRYPTO_PASSWORD=your_strong_password_16chars
   export CRYPTO_SALT=your_random_salt_16chars
   ```

4. **Initialize database**
   ```bash
   alembic upgrade head
   ```

5. **Run the bot**
   ```bash
   python main.py
   ```

---

## ⚙️ Configuration

### Environment Variables Configuration

> ⚠️ **Configuration Method**: Set via system environment variables (`export KEY=value`, Docker `environment` field, `systemd`/`Supervisor` config, etc.)

#### Required Environment Variables

| Variable | Description | Required |
|----------|-------------|:--------:|
| `TG_BOT_TOKEN` | Telegram Bot Token (from [@BotFather](https://t.me/botfather)) | ✅ |
| `CRYPTO_PASSWORD` | Encryption password (min 16 chars, used for encrypting sensitive data) | ✅ |
| `CRYPTO_SALT` | Encryption salt (min 16 chars, used for encrypting sensitive data) | ✅ |

> 🔒 **Security Tip**: Once `CRYPTO_PASSWORD` and `CRYPTO_SALT` are set, changing them will make previously encrypted data undecryptable. Please keep them safe.

#### Optional Environment Variables

<details>
<summary><b>TMDB Configuration</b> (Click to expand)</summary>

| Variable | Description | Default Value |
|----------|-------------|---------------|
| `TMDB_API_KEY` | The Movie Database API Key | - |
| `TMDB_POSTER_BASE_URL` | TMDB Poster Base URL | `https://image.tmdb.org/t/p/original` |

</details>

<details>
<summary><b>PanSou Configuration</b> (Click to expand)</summary>

| Variable | Description |
|----------|-------------|
| `PANSOU_HOST` | PanSou search service host address |

</details>

<details>
<summary><b>CloudSaver Configuration</b> (Click to expand)</summary>

| Variable | Description |
|----------|-------------|
| `CLOUD_SAVER_HOST` | CloudSaver service host address |
| `CLOUD_SAVER_USERNAME` | CloudSaver username |
| `CLOUD_SAVER_PASSWORD` | CloudSaver password |

</details>

<details>
<summary><b>Other Configuration</b> (Click to expand)</summary>

| Variable | Description | Default Value |
|----------|-------------|---------------|
| `DATA_PATH` | Database storage path | `db/data/` |

</details>

### Personal Service Configuration

Using the `/upsert_configuration` command, each user can configure their own personal service connections.

#### Supported Services

<table>
<tr>
<td width="33%">

**🤖 AI Services**
- OpenAI
- DeepSeek
- Kimi

Config items: API Key, Host, Model

</td>
<td width="33%">

**📥 QAS Service**
- Quark Auto Download

Config items: Host, API Token, Save Path, Matching Rules

</td>
<td width="33%">

**🎬 Emby Service**
- Library Management

Config items: Host, API Token, Username, Password

</td>
</tr>
</table>

#### Configuration Features

| Feature | Description |
|---------|-------------|
| 🔐 **User Isolation** | Each user's configuration is independent and isolated. |
| 💬 **Interactive Setup** | Configuration is completed through Telegram dialogue guidance. |
| ⚡ **Instant Effect** | Settings take effect immediately upon completion. |
| 🔒 **Secure Storage** | Sensitive information is encrypted and stored in the database. |

#### Configuration Method Comparison

| Config Type | Method | Scope | Applicable Scenario |
|-------------|--------|-------|---------------------|
| **Env Vars** | System Environment | Global | Bot Token, Encryption Keys, and system-level configs |
| **User Config** | `/upsert_configuration` | User-level | QAS, Emby, AI and personal service connections |

---

## 📖 User Guide

### Basic Commands

```bash
/register          # Register new user (required for first-time use)
/help              # Show list of available commands
/refresh_menu      # Refresh menu
/my_info           # View personal information
/upsert_configuration  # Configure personal services (QAS, Emby, AI)
```

### Resource Search

```bash
/search_tv {title}              # Search for TV show resources
/search_movie {title}           # Search for movie resources
/search_media_resource {name}   # Search for general media resources
```

**Example:**
```
/search_tv Game of Thrones
/search_movie The Shawshank Redemption
```

### QAS Download Management

QAS (Quark Auto Save) integration for automatic Quark Drive downloads.

```bash
/qas_add_task {share_link} {task_name}  # Add download task
/qas_list_task {task_name}            # List tasks
/qas_delete_task {task_id}            # Delete task
/qas_run_script {task_id}            # Run task
/qas_view_task_regex {task_id}        # Preview task regex matching effect
```

**Workflow:**
1. Use `/upsert_configuration` to configure QAS service.
2. Use `/qas_add_task` to add a Quark Drive sharing link.
3. AI automatically generates download parameters and regular expressions.
4. Use `/qas_run_script` to execute the download task.

### Emby Integration

```bash
/emby_list_resource {name}       # List Emby media resources
/emby_list_notification          # List Emby notification configs
```

**Features:**
- Search and manage Emby media libraries.
- Remotely refresh the media library.
- Manage notifications for new media entries.

### Task Scheduling (Admin+)

```bash
/remind {time} {content}  # Set a reminder
/list_my_job             # List personal jobs
/delete_job {job_id}     # Delete a job
```

### Management Commands (Owner)

```bash
/set_admin {user_id}  # Set administrator permissions
```

---

## 🔧 Development Guide

### Technology Stack

| Category | Technology |
|----------|-----------|
| **Framework** | Python Telegram Bot |
| **Database** | SQLAlchemy + SQLite |
| **Migration** | Alembic |
| **Scheduling** | APScheduler |
| **HTTP** | aiohttp |
| **External APIs** | TMDB API, QAS API, Emby API |

### Development Environment Setup

1. **Clone repository and install dependencies**
   ```bash
   git clone <repository-url>
   cd tgbot
   pip install -r requirements.txt
   ```

2. **Configure environment variables**
   ```bash
   export TG_BOT_TOKEN=your_token
   export CRYPTO_PASSWORD=your_password
   export CRYPTO_SALT=your_salt
   ```

3. **Initialize database**
   ```bash
   alembic upgrade head
   ```

### Database Migration

```bash
# Generate migration script (automatically detects model changes)
alembic revision --autogenerate -m "Migration description"

# Apply migrations
alembic upgrade head

# Rollback to previous version
alembic downgrade -1

# View migration history
alembic history
```

### Adding a New Model

1. Create a new model file in the `db/models/` directory.
2. Import the new model in `alembic/env.py`.
3. Run `alembic revision --autogenerate -m "Add XXX model"`.
4. Check the generated migration script.
5. Run `alembic upgrade head` to apply the migration.

### Adding a New Command

1. Create or edit a command file in the `api/` directory.
2. Use the `@command` decorator to define the command handler:
   ```python
   from api.base import command

   @command(name="my_command", description="Command description")
   async def my_command_handler(update, context):
       # Command logic
       pass
   ```
3. Configure permissions in `config/config.py` under `ROLE_COMMANDS`.
4. Import the new command module in `main.py`.

### Code Standards

- Follow PEP 8 Python code guidelines.
- Use meaningful variable and function names.
- Add necessary comments and docstrings.
- Store sensitive information using encryption.

---

## 📁 Project Structure

```
tgbot/
├── 📂 api/                    # API and command processing
│   ├── base.py               # Basic command framework
│   ├── commands.py           # Command management
│   ├── user.py               # User management
│   ├── resource.py           # Resource search
│   ├── qas.py                # QAS integration
│   ├── emby.py               # Emby integration
│   ├── ai_config.py          # AI configuration
│   └── user_config.py        # User configuration
│
├── 📂 config/                 # Configuration files
│   ├── config.py             # Main config (permissions, commands, etc.)
│   ├── prod.py               # Production environment config
│   └── test.py               # Test environment config
│
├── 📂 db/                     # Database related
│   ├── 📂 models/            # Data models
│   │   ├── base.py           # Base model
│   │   ├── user.py           # User model
│   │   ├── qas.py            # QAS task model
│   │   ├── emby.py           # Emby config model
│   │   ├── ai_config.py      # AI config model
│   │   └── job.py            # Scheduled task model
│   ├── main.py               # Database initialization
│   └── 📂 data/              # SQLite database files
│
├── 📂 utils/                  # Utility functions
│   ├── ai.py                 # AI service integration
│   ├── qas.py                # QAS utilities
│   ├── emby.py               # Emby utilities
│   ├── quark.py              # Quark Drive utilities
│   ├── crypto.py             # Encryption utilities
   ├── command_middleware.py # Command middleware
   └── common.py             # Common utilities
│
├── 📂 alembic/               # Database migrations
│   ├── versions/             # Migration scripts
│   └── env.py                # Alembic configuration
│
├── main.py                   # Main entry point
├── requirements.txt          # Python dependencies
├── Dockerfile                # Docker build file
└── README.md                 # Project documentation
```

---

## ❓ FAQ

<details>
<summary><b>How to get a Telegram Bot Token?</b></summary>

1. Search for [@BotFather](https://t.me/botfather) in Telegram.
2. Send the `/newbot` command.
3. Follow the prompts to set the bot's name and username.
4. Obtain the Bot Token and configure it in your environment variables.

</details>

<details>
<summary><b>How to get a TMDB API Key?</b></summary>

1. Visit [The Movie Database](https://www.themoviedb.org/).
2. Register and log in to your account.
3. Go to Settings → API.
4. Request an API Key (choose the developer option).
5. Configure the API Key in your environment variables.

</details>

<details>
<summary><b>What to do if I forget my encryption keys?</b></summary>

⚠️ Once the encryption keys (`CRYPTO_PASSWORD` and `CRYPTO_SALT`) are lost, previously encrypted data cannot be decrypted.

**Solution:**
1. Back up the current database.
2. Delete the database files.
3. Set new encryption keys.
4. Re-initialize the database.
5. Users will need to re-configure their personal services.

**Prevention:** Please keep your encryption keys stored securely!

</details>

<details>
<summary><b>How to update to the latest version?</b></summary>

**Docker Deployment:**
```bash
docker compose pull
docker compose up -d
```

**Local Development:**
```bash
git pull
pip install -r requirements.txt
alembic upgrade head
```

</details>

<details>
<summary><b>What if the bot is unresponsive?</b></summary>

**Troubleshooting Steps:**
1. Check if the container/process is running: `docker compose ps` or `ps aux | grep python`.
2. View logs: `docker compose logs -f` or check application logs.
3. Verify if the Bot Token is correct.
4. Check if the network connection is normal.
5. Confirm that the Telegram API is accessible.

</details>

<details>
<summary><b>How to back up data?</b></summary>

Database files are located in the `db/data/` directory (or the path specified by `DATA_PATH`).

**Backup Method:**
```bash
# Docker Deployment
cp -r ./data ./data_backup_$(date +%Y%m%d)

# Local Deployment
cp -r db/data db/data_backup_$(date +%Y%m%d)
```

**Suggestion:** Regularly back up database files, especially before upgrading.

</details>

---

## 🔐 Security Notes

- 🔑 **Keep keys safe**: Secure your Bot Token, API Keys, and encryption keys.
- 🚫 **Do not commit keys**: Ensure `.env` files are included in `.gitignore`.
- 🔒 **Use strong passwords**: `CRYPTO_PASSWORD` and `CRYPTO_SALT` should be at least 16 characters long.
- 👥 **Restrict access**: Reasonably assign Owner, Admin, and User roles.
- 🔄 **Update regularly**: Keep dependency packages updated to fix security vulnerabilities.
- 📦 **Data backup**: Regularly back up database files.

---

## 🙏 Acknowledgements

This project benefited from the following excellent open-source projects during development:

<table>
<tr>
<td align="center" width="25%">
<a href="https://github.com/python-telegram-bot/python-telegram-bot">
<br/>
<b>python-telegram-bot</b>
</a>
<br/>
Telegram Bot API Framework
</td>
<td align="center" width="25%">
<a href="https://github.com/Cp0204/quark-auto-save">
<br/>
<b>quark-auto-save</b>
</a>
<br/>
Quark Drive Auto-download tool
</td>
<td align="center" width="25%">
<a href="https://github.com/fish2018/pansou">
<br/>
<b>pansou</b>
</a>
<br/>
Cloud drive resource search service
</td>
<td align="center" width="25%">
<a href="https://github.com/jiangrui1994/cloudsaver">
<br/>
<b>cloudsaver</b>
</a>
<br/>
Cloud storage management tool
</td>
</tr>
</table>

Thanks to the developers of these projects for their contributions to the open-source community!

---

## 🤝 Contributing

Contributions in the form of code, issue reports, or suggestions are welcome!

### How to Contribute

1. **Fork the repository**.
2. **Create a feature branch** (`git checkout -b feature/AmazingFeature`).
3. **Commit your changes** (`git commit -m 'Add some AmazingFeature'`).
4. **Push to the branch** (`git push origin feature/AmazingFeature`).
5. **Submit a Pull Request**.

### Contribution Guidelines

- Follow existing code styles and standards.
- Add necessary tests and documentation.
- Ensure all tests pass.
- Provide clear commit messages.

---

## 📝 License

This project is licensed under the **Apache License 2.0** - see the [LICENSE](LICENSE) file for details.

```
Copyright 2024 tgbot

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

## 🆘 Getting Help

Encountering problems? Here is how to get help:

1. 📖 **Check Documentation**: Carefully read this README and the FAQ section.
2. 🔍 **Search Issues**: Check if others have encountered similar problems.
3. 📝 **Submit an Issue**: Create a new Issue on GitHub, providing detailed information:
   - Problem description
   - Steps to reproduce
   - Environment info (OS, Python version, etc.)
   - Relevant logs
4. 💬 **Join Discussion**: Communicate in GitHub Discussions.

### Viewing Logs

**Docker Deployment:**
```bash
docker compose logs -f tgbot
```

**Local Development:**
Check application output or log files.

---

<div align="center">

## ⭐ Star History

If this project helped you, please give it a Star ⭐

[![Star History Chart](https://api.star-history.com/svg?repos=2beetle/tgbot&type=Date)](https://star-history.com/#2beetle/tgbot&Date)

---

**⚠️ Disclaimer**

This bot is for personal study and research purposes only. Please comply with relevant laws, regulations, and terms of service. The user assumes all consequences resulting from the use of this project.

---

Made with ❤️ by the tgbot team

[⬆ Back to top](#telegram-media-resource-management-bot)

</div>
