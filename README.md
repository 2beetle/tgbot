<div align="center">

# Telegram 媒体资源管理机器人

**功能丰富的 Telegram 机器人，专注于媒体资源管理、Emby 集成、自动下载和夸克网盘资源管理**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://hub.docker.com/r/beocean/tgbot)

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [配置说明](#-配置说明) • [使用指南](#-使用指南) • [开发文档](#-开发指南)

</div>

---

## 📑 目录

- [功能特性](#-功能特性)
- [快速开始](#-快速开始)
  - [前置要求](#前置要求)
  - [Docker 部署](#docker-部署推荐)
  - [本地开发](#本地开发)
- [配置说明](#-配置说明)
  - [环境变量配置](#环境变量配置)
  - [个人服务配置](#个人服务配置)
- [使用指南](#-使用指南)
  - [基本命令](#基本命令)
  - [资源搜索](#资源搜索)
  - [QAS 下载管理](#qas-下载管理)
  - [Emby 集成](#emby-集成)
- [开发指南](#-开发指南)
- [项目结构](#-项目结构)
- [常见问题](#-常见问题)
- [鸣谢](#-鸣谢)
- [许可证](#-许可证)

---

## ✨ 功能特性

### 📺 媒体资源搜索
- **多平台资源搜索**: 支持 CloudSaver、PanSou 等多个资源搜索平台
- **TMDB 集成**: 集成 The Movie Database API 获取电影/电视剧详细信息
- **资源链接状态检查**: 自动检查夸克网盘链接有效性
- **智能分类**: 支持电视节目、电影分类和多季模式识别

### 🔄 QAS 项目集成
- **Quark Auto Save 集成**: 集成 [QAS 项目](https://github.com/Cp0204/quark-auto-save) 实现夸克网盘自动下载
- **AI 增强功能**: 使用 AI 生成下载参数和正则表达式，智能识别季数
- **任务管理**: 创建、更新、删除、运行下载任务，支持多季电视剧自动分类
- **正则匹配**: 智能文件筛选和重命名规则，支持自定义 pattern 和 replace

### 🎬 Emby 集成
- **媒体库管理**: 搜索和管理 Emby 媒体库资源
- **媒体库刷新**: 远程刷新 Emby 媒体库
- **通知配置**: 管理 Emby 新媒体加入通知
- **元数据获取**: 获取详细的媒体信息和海报

### 🤖 AI 功能
- **智能参数生成**: AI 自动生成下载任务的 pattern 和 replace 规则
- **季数分类**: AI 自动识别和分类电视剧季数
- **多 AI 提供商**: 支持 OpenAI、DeepSeek、Kimi 等多个 AI 服务
- **动态配置**: 通过 `/upsert_configuration` 命令配置，每个用户独立设置 AI 服务

### 👥 用户管理
- **角色权限**: 支持 Owner、Admin、User 三级权限管理
- **命令权限**: 基于角色的命令访问控制
- **用户注册**: 简单的用户注册和权限分配

### 📊 任务调度
- **定时任务**: 支持定时提醒和任务调度
- **作业管理**: 创建、查看、删除定时作业

---

## 🚀 快速开始

### 前置要求

- Docker 和 Docker Compose（推荐）
- 或 Python 3.8+ 环境（本地开发）
- Telegram Bot Token（从 [@BotFather](https://t.me/botfather) 获取）

### Docker 部署（推荐）

1. **创建部署目录**
   ```bash
   mkdir tgbot && cd tgbot
   ```

2. **创建 docker-compose.yml 文件**
   ```yaml
   version: '3.8'

   services:
     tgbot:
       image: beocean/tgbot:latest
       container_name: tgbot
       restart: unless-stopped
       environment:
         # 必需配置
         - TG_BOT_TOKEN=your_telegram_bot_token
         - CRYPTO_PASSWORD=your_strong_password_16chars
         - CRYPTO_SALT=your_random_salt_16chars

         # Telegram 代理配置（可选，用于网络受限地区）
         # - TELEGRAM_PROXY_URL=http://127.0.0.1:7890
         # - TELEGRAM_PROXY_URL=socks5://user:pass@host:port

         # 可选配置
         - TMDB_API_KEY=your_tmdb_api_key
         - TMDB_POSTER_BASE_URL=https://image.tmdb.org/t/p/original
         - PANSOU_HOST=https://your-pansou-host.com
         - CLOUD_SAVER_HOST=https://your-cloud-saver-host.com
         - CLOUD_SAVER_USERNAME=your_username
         - CLOUD_SAVER_PASSWORD=your_password
       volumes:
         - ./data:/app/db/data
   ```

3. **启动服务**
   ```bash
   docker compose up -d
   ```

4. **查看日志**
   ```bash
   docker compose logs -f
   ```

5. **在 Telegram 中使用**
   - 找到你的机器人
   - 发送 `/register` 注册
   - 发送 `/help` 查看可用命令

### 本地开发

1. **克隆仓库**
   ```bash
   git clone <repository-url>
   cd tgbot
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**
   ```bash
   export TG_BOT_TOKEN=your_telegram_bot_token
   export CRYPTO_PASSWORD=your_strong_password_16chars
   export CRYPTO_SALT=your_random_salt_16chars

   # 可选：配置 Telegram 代理（用于网络受限地区）
   # export TELEGRAM_PROXY_URL=http://127.0.0.1:7890
   ```

4. **初始化数据库**
   ```bash
   alembic upgrade head
   ```

5. **运行机器人**
   ```bash
   python main.py
   ```

---

## ⚙️ 配置说明

### 环境变量配置

> ⚠️ **配置方式**：通过系统环境变量设置（`export KEY=value`、Docker `environment` 字段、`systemd`/`Supervisor` 配置等）

#### 必需环境变量

| 变量名 | 说明 | 必需 |
|--------|------|:----:|
| `TG_BOT_TOKEN` | Telegram Bot Token（从 [@BotFather](https://t.me/botfather) 获取） | ✅ |
| `CRYPTO_PASSWORD` | 加密密码（至少16位，用于敏感数据加密） | ✅ |
| `CRYPTO_SALT` | 加密盐值（至少16位，用于敏感数据加密） | ✅ |

> 🔒 **安全提示**：`CRYPTO_PASSWORD` 和 `CRYPTO_SALT` 一旦设置，后续修改会导致已加密数据无法解密，请妥善保管。

#### 可选环境变量

<details>
<summary><b>Telegram 代理配置</b>（点击展开）</summary>

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `TELEGRAM_PROXY_URL` | Telegram Bot 代理地址（用于网络受限地区） | `http://127.0.0.1:7890` 或 `socks5://user:pass@host:port` |

**支持的代理格式：**
- HTTP 代理：`http://host:port`
- HTTPS 代理：`https://host:port`
- SOCKS5 代理：`socks5://host:port` 或 `socks5://user:pass@host:port`

**注意：** 此代理仅用于 Telegram Bot 连接，不影响其他服务（TMDB、CloudSaver 等）的网络请求。

</details>

<details>
<summary><b>TMDB 配置</b>（点击展开）</summary>

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `TMDB_API_KEY` | The Movie Database API Key | - |
| `TMDB_POSTER_BASE_URL` | TMDB 海报基础 URL | `https://image.tmdb.org/t/p/original` |

</details>

<details>
<summary><b>PanSou 配置</b>（点击展开）</summary>

| 变量名 | 说明 |
|--------|------|
| `PANSOU_HOST` | PanSou 搜索服务主机地址 |

</details>

<details>
<summary><b>CloudSaver 配置</b>（点击展开）</summary>

| 变量名 | 说明 |
|--------|------|
| `CLOUD_SAVER_HOST` | CloudSaver 服务主机地址 |
| `CLOUD_SAVER_USERNAME` | CloudSaver 用户名 |
| `CLOUD_SAVER_PASSWORD` | CloudSaver 密码 |

</details>

<details>
<summary><b>其他配置</b>（点击展开）</summary>

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `DATA_PATH` | 数据库存储路径 | `db/data/` |

</details>

### 个人服务配置

通过 `/upsert_configuration` 命令，每个用户可以配置自己的个人服务连接。

#### 支持的服务

<table>
<tr>
<td width="33%">

**🤖 AI 服务**
- OpenAI
- DeepSeek
- Kimi

配置项：API Key、Host、Model

</td>
<td width="33%">

**📥 QAS 服务**
- 夸克自动下载

配置项：Host、API Token、保存路径、匹配规则

</td>
<td width="33%">

**🎬 Emby 服务**
- 媒体库管理

配置项：Host、API Token、用户名、密码

</td>
</tr>
</table>

#### 配置特点

| 特性 | 说明 |
|------|------|
| 🔐 **用户隔离** | 每个用户的配置相互独立，互不干扰 |
| 💬 **交互式配置** | 通过 Telegram 对话引导完成配置 |
| ⚡ **实时生效** | 配置完成后立即生效 |
| 🔒 **安全存储** | 敏感信息加密存储在数据库中 |

#### 配置方式对比

| 配置类型 | 配置方式 | 作用域 | 适用场景 |
|:---------|:---------|:-------|:---------|
| **环境变量** | 系统环境变量 | 全局 | Bot Token、加密密钥等系统级配置 |
| **个人配置** | `/upsert_configuration` | 用户级 | QAS、Emby、AI 等个人服务连接 |

---

## 📖 使用指南

### 基本命令

```bash
/register          # 注册新用户（首次使用必须）
/help              # 显示可用命令列表
/refresh_menu      # 刷新菜单
/my_info           # 查看个人信息
/upsert_configuration  # 配置个人服务（QAS、Emby、AI）
```

### 资源搜索

```bash
/search_tv {剧名}              # 搜索电视剧资源
/search_movie {电影名}         # 搜索电影资源
/search_media_resource {资源名} # 搜索媒体资源
```

**示例：**
```
/search_tv 权力的游戏
/search_movie 肖申克的救赎
```

### QAS 下载管理

QAS (Quark Auto Save) 集成，实现夸克网盘自动下载。

```bash
/qas_add_task {分享链接} {任务名}  # 添加下载任务
/qas_list_task {任务名}           # 列出任务
/qas_delete_task {任务ID}         # 删除任务
/qas_run_script {任务ID}          # 运行任务
/qas_view_task_regex {任务ID}     # 查看任务正则匹配效果
```

**工作流程：**
1. 使用 `/upsert_configuration` 配置 QAS 服务
2. 使用 `/qas_add_task` 添加夸克网盘分享链接
3. AI 自动生成下载参数和正则表达式
4. 使用 `/qas_run_script` 执行下载任务

### Emby 集成

```bash
/emby_list_resource {资源名}    # 列出 Emby 媒体资源
/emby_list_notification         # 列出 Emby 通知配置
```

**功能：**
- 搜索和管理 Emby 媒体库
- 远程刷新媒体库
- 管理新媒体加入通知

### 任务调度（Admin+）

```bash
/remind {时间} {提醒内容}  # 设置提醒
/list_my_job               # 列出个人作业
/delete_job {作业ID}       # 删除作业
```

### 管理命令（Owner）

```bash
/set_admin {用户ID}  # 设置管理员权限
```

---

## 🔧 开发指南

### 技术栈

| 类别 | 技术 |
|------|------|
| **框架** | Python Telegram Bot |
| **数据库** | SQLAlchemy + SQLite |
| **迁移** | Alembic |
| **调度** | APScheduler |
| **HTTP** | aiohttp |
| **外部 API** | TMDB API, QAS API, Emby API |

### 开发环境设置

1. **克隆仓库并安装依赖**
   ```bash
   git clone <repository-url>
   cd tgbot
   pip install -r requirements.txt
   ```

2. **配置环境变量**
   ```bash
   export TG_BOT_TOKEN=your_token
   export CRYPTO_PASSWORD=your_password
   export CRYPTO_SALT=your_salt
   ```

3. **初始化数据库**
   ```bash
   alembic upgrade head
   ```

### 数据库迁移

```bash
# 生成迁移脚本（自动检测模型变更）
alembic revision --autogenerate -m "迁移描述"

# 应用迁移
alembic upgrade head

# 回滚到上一个版本
alembic downgrade -1

# 查看迁移历史
alembic history
```

### 添加新模型

1. 在 `db/models/` 目录下创建新的模型文件
2. 在 `alembic/env.py` 中导入新模型
3. 运行 `alembic revision --autogenerate -m "添加XXX模型"`
4. 检查生成的迁移脚本
5. 运行 `alembic upgrade head` 应用迁移

### 添加新命令

1. 在 `api/` 目录下创建或编辑命令文件
2. 使用 `@command` 装饰器定义命令处理函数
   ```python
   from api.base import command

   @command(name="my_command", description="命令描述")
   async def my_command_handler(update, context):
       # 命令逻辑
       pass
   ```
3. 在 `config/config.py` 的 `ROLE_COMMANDS` 中配置权限
4. 在 `main.py` 中导入新命令模块

### 代码规范

- 遵循 PEP 8 Python 代码规范
- 使用有意义的变量和函数名
- 添加必要的注释和文档字符串
- 敏感信息使用加密存储

---

## 📁 项目结构

```
tgbot/
├── 📂 api/                    # API 和命令处理
│   ├── base.py               # 基础命令框架
│   ├── commands.py           # 命令管理
│   ├── user.py               # 用户管理
│   ├── resource.py           # 资源搜索
│   ├── qas.py                # QAS 集成
│   ├── emby.py               # Emby 集成
│   ├── ai_config.py          # AI 配置
│   └── user_config.py        # 用户配置
│
├── 📂 config/                 # 配置文件
│   ├── config.py             # 主配置（权限、命令等）
│   ├── prod.py               # 生产环境配置
│   └── test.py               # 测试环境配置
│
├── 📂 db/                     # 数据库相关
│   ├── 📂 models/            # 数据模型
│   │   ├── base.py           # 基础模型
│   │   ├── user.py           # 用户模型
│   │   ├── qas.py            # QAS 任务模型
│   │   ├── emby.py           # Emby 配置模型
│   │   ├── ai_config.py      # AI 配置模型
│   │   └── job.py            # 定时任务模型
│   ├── main.py               # 数据库初始化
│   └── 📂 data/              # SQLite 数据库文件
│
├── 📂 utils/                  # 工具函数
│   ├── ai.py                 # AI 服务集成
│   ├── qas.py                # QAS 工具
│   ├── emby.py               # Emby 工具
│   ├── quark.py              # 夸克网盘工具
│   ├── crypto.py             # 加密工具
│   ├── command_middleware.py # 命令中间件
│   └── common.py             # 通用工具
│
├── 📂 alembic/               # 数据库迁移
│   ├── versions/             # 迁移脚本
│   └── env.py                # Alembic 配置
│
├── main.py                   # 主入口文件
├── requirements.txt          # Python 依赖
├── Dockerfile                # Docker 构建文件
└── README.md                 # 项目文档
```

---

## ❓ 常见问题

<details>
<summary><b>如何获取 Telegram Bot Token？</b></summary>

1. 在 Telegram 中搜索 [@BotFather](https://t.me/botfather)
2. 发送 `/newbot` 命令
3. 按照提示设置机器人名称和用户名
4. 获取 Bot Token 并配置到环境变量

</details>

<details>
<summary><b>如何获取 TMDB API Key？</b></summary>

1. 访问 [The Movie Database](https://www.themoviedb.org/)
2. 注册账号并登录
3. 进入 Settings → API
4. 申请 API Key（选择开发者选项）
5. 将 API Key 配置到环境变量

</details>

<details>
<summary><b>加密密钥忘记了怎么办？</b></summary>

⚠️ 加密密钥（`CRYPTO_PASSWORD` 和 `CRYPTO_SALT`）一旦丢失，已加密的数据将无法解密。

**解决方案：**
1. 备份当前数据库
2. 删除数据库文件
3. 重新设置新的加密密钥
4. 重新初始化数据库
5. 用户需要重新配置个人服务

**预防措施：** 请务必妥善保管加密密钥！

</details>

<details>
<summary><b>如何更新到最新版本？</b></summary>

**Docker 部署：**
```bash
docker compose pull
docker compose up -d
```

**本地开发：**
```bash
git pull
pip install -r requirements.txt
alembic upgrade head
```

</details>

<details>
<summary><b>机器人无响应怎么办？</b></summary>

**排查步骤：**
1. 检查容器/进程是否运行：`docker compose ps` 或 `ps aux | grep python`
2. 查看日志：`docker compose logs -f` 或检查应用日志
3. 验证 Bot Token 是否正确
4. 检查网络连接是否正常
5. 确认 Telegram API 是否可访问

</details>

<details>
<summary><b>如何备份数据？</b></summary>

数据库文件位于 `db/data/` 目录（或 `DATA_PATH` 指定的路径）。

**备份方法：**
```bash
# Docker 部署
cp -r ./data ./data_backup_$(date +%Y%m%d)

# 本地部署
cp -r db/data db/data_backup_$(date +%Y%m%d)
```

**建议：** 定期备份数据库文件，特别是在升级前。

</details>

---

## 🔐 安全说明

- 🔑 **妥善保管密钥**：Bot Token、API Key、加密密钥等敏感信息
- 🚫 **不要提交密钥**：确保 `.env` 文件在 `.gitignore` 中
- 🔒 **使用强密码**：`CRYPTO_PASSWORD` 和 `CRYPTO_SALT` 至少16位
- 👥 **限制访问权限**：合理分配 Owner、Admin、User 角色
- 🔄 **定期更新**：及时更新依赖包修复安全漏洞
- 📦 **数据备份**：定期备份数据库文件

---

## 🙏 鸣谢

本项目在开发过程中受益于以下优秀的开源项目：

<table>
<tr>
<td align="center" width="25%">
<a href="https://github.com/python-telegram-bot/python-telegram-bot">
<br/>
<b>python-telegram-bot</b>
</a>
<br/>
Telegram Bot API 框架
</td>
<td align="center" width="25%">
<a href="https://github.com/Cp0204/quark-auto-save">
<br/>
<b>quark-auto-save</b>
</a>
<br/>
夸克网盘自动下载工具
</td>
<td align="center" width="25%">
<a href="https://github.com/fish2018/pansou">
<br/>
<b>pansou</b>
</a>
<br/>
网盘资源搜索服务
</td>
<td align="center" width="25%">
<a href="https://github.com/jiangrui1994/cloudsaver">
<br/>
<b>cloudsaver</b>
</a>
<br/>
云存储管理工具
</td>
</tr>
</table>

感谢这些项目的开发者为开源社区做出的贡献！

---

## 🤝 贡献

欢迎贡献代码、报告问题或提出建议！

### 如何贡献

1. **Fork 本仓库**
2. **创建特性分支** (`git checkout -b feature/AmazingFeature`)
3. **提交更改** (`git commit -m 'Add some AmazingFeature'`)
4. **推送到分支** (`git push origin feature/AmazingFeature`)
5. **提交 Pull Request**

### 贡献指南

- 遵循现有的代码风格和规范
- 添加必要的测试和文档
- 确保所有测试通过
- 提供清晰的提交信息

---

## 📝 许可证

本项目采用 **Apache License 2.0** 许可证 - 详见 [LICENSE](LICENSE) 文件

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

## 🆘 获取帮助

遇到问题？以下是获取帮助的方式：

1. 📖 **查看文档**：仔细阅读本 README 和常见问题部分
2. 🔍 **搜索 Issues**：查看是否有人遇到过类似问题
3. 📝 **提交 Issue**：在 GitHub 上创建新的 Issue，提供详细信息：
   - 问题描述
   - 复现步骤
   - 环境信息（操作系统、Python 版本等）
   - 相关日志
4. 💬 **参与讨论**：在 GitHub Discussions 中交流

### 日志查看

**Docker 部署：**
```bash
docker compose logs -f tgbot
```

**本地开发：**
检查应用输出或日志文件

---

<div align="center">

## ⭐ Star History

如果这个项目对你有帮助，请给它一个 Star ⭐

[![Star History Chart](https://api.star-history.com/svg?repos=2beetle/tgbot&type=Date)](https://star-history.com/#2beetle/tgbot&Date)

---

**⚠️ 免责声明**

本机器人仅供个人学习和研究使用，请遵守相关法律法规和服务条款。使用本项目所产生的一切后果由使用者自行承担。

---

Made with ❤️ by the tgbot team

[⬆ 回到顶部](#telegram-媒体资源管理机器人)

</div>
