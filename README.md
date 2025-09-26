# Telegram 媒体资源管理机器人

一个功能丰富的 Telegram 机器人，专注于媒体资源管理、Emby 集成、自动下载和夸克网盘资源管理。

## 🚀 主要功能

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

## 🔧 技术栈

- **框架**: Python Telegram Bot
- **数据库**: SQLAlchemy + SQLite
- **迁移**: Alembic
- **调度**: APScheduler
- **HTTP**: aiohttp
- **API**: TMDB API

## 📋 环境变量配置

### 必需环境变量

| 变量名 | 说明 | 示例值 | 必需 |
|--------|------|--------|:----:|
| `TG_BOT_TOKEN` | Telegram Bot Token | `123456789:ABCdefGHIjklMNOpqrsTUVwxyz` | ✅ |
| `DATA_PATH` | 数据库路径（可选，默认在 db/data/ 目录下） | `/path/to/data` | ❌ |

### TMDB 配置

| 变量名 | 说明 | 示例值 | 必需 |
|--------|------|--------|:----:|
| `TMDB_API_KEY` | The Movie Database API Key | `your_tmdb_api_key` | ❌ |
| `TMDB_POSTER_BASE_URL` | TMDB 海报基础 URL（可选） | `https://image.tmdb.org/t/p/original` | ❌ |


### PanSou 配置（可选）

| 变量名 | 说明 | 示例值 | 必需 |
|--------|------|--------|:---:|
| `PANSOU_HOST` | PanSou 搜索服务主机地址 | `https://your-pansou-host.com` | ❌ |

### CloudSaver 配置（可选）

| 变量名 | 说明 | 示例值 | 必需 |
|--------|------|--------|:---:|
| `CLOUD_SAVER_HOST` | CloudSaver 服务主机地址 | `https://your-cloud-saver-host.com` | ❌ |
| `CLOUD_SAVER_USERNAME` | CloudSaver 用户名 | `your_username` | ❌ |
| `CLOUD_SAVER_PASSWORD` | CloudSaver 密码 | `your_password` | ❌ |

## ⚙️ 个人服务配置

### `/upsert_configuration` 命令

通过 `/upsert_configuration` 命令，每个 Telegram 用户可以配置自己的个人服务连接，这些配置存储在数据库中，每个用户相互独立。

#### 可配置的服务

**AI 服务配置：**
- **支持提供商**: OpenAI、DeepSeek、Kimi
- **必需字段**: API Key、Host、Model（所有字段都必须显式配置）
- **配置方式**: 通过 `/upsert_configuration` 命令动态配置
- **特点**: 每个用户独立配置，加密存储，无默认配置

**QAS (Quark Auto Save) 配置：**
- **host**: QAS 服务主机地址
- **api_token**: QAS API 令牌
- **save_path_prefix**: TV 保存路径前缀
- **movie_save_path_prefix**: 电影保存路径前缀
- **pattern**: 文件匹配正则表达式
- **replace**: 文件重命名模板

**Emby 配置：**
- **host**: Emby 服务器地址
- **api_token**: Emby API 令牌
- **username**: 管理员用户名
- **password**: 管理员密码

#### 配置特点

✅ **用户隔离**: 每个用户的配置相互独立，互不干扰
✅ **交互式配置**: 通过 Telegram 对话引导完成配置
✅ **实时生效**: 配置完成后立即生效
✅ **安全存储**: 敏感信息加密存储在数据库中

#### 与全局环境变量的区别

| 配置类型 | 配置方式 | 作用域 | 适用场景 |
|:---------|:---------|:-------|:---------|
| **环境变量** | `.env` 文件 | 全局 | 系统级配置，如 API 密钥、数据库连接 |
| **个人配置** | `/upsert_configuration` 命令 | 用户级 | 个人服务连接，如 QAS、Emby 服务器 |

🔍 **示例**:
- 环境变量 `TG_BOT_TOKEN` 是整个机器人的 Telegram 令牌（全局）
- 个人配置 `QAS host` 是每个用户自己的 QAS 服务地址（用户级）

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd tgbot
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

创建 `.env` 文件并配置必要的环境变量：

```bash
TG_BOT_TOKEN=your_telegram_bot_token
TMDB_API_KEY=your_tmdb_api_key
```

### 4. 初始化数据库

```bash
# 生成数据库迁移
alembic upgrade head
```

### 5. 运行机器人

```bash
python main.py
```

## 📖 使用说明

### 基本命令

#### 用户命令
- `/register` - 注册新用户
- `/help` - 显示可用命令列表
- `/refresh_menu` - 刷新菜单
- `/my_info` - 查看个人信息

#### 资源搜索
- `/search_tv {剧名}` - 搜索电视剧
- `/search_movie {电影名}` - 搜索电影
- `/search_media_resource {资源名}` - 搜索媒体资源

#### QAS (夸克自动下载)
- `/qas_add_task {分享链接} {任务名}` - 添加下载任务
- `/qas_list_task {任务名}` - 列出任务
- `/qas_delete_task {任务ID}` - 删除任务
- `/qas_run_script {任务ID}` - 运行任务
- `/qas_view_task_regex {任务ID}` - 查看任务正则匹配效果

#### Emby 集成
- `/emby_list_resource {资源名}` - 列出 Emby 媒体资源
- `/emby_list_notification` - 列出 Emby 通知配置

#### 配置管理
- `/upsert_configuration` - 配置个人服务连接（QAS、Emby、AI 服务）

#### 任务调度 (Admin+)
- `/remind {时间} {提醒内容}` - 设置提醒
- `/list_my_job` - 列出个人作业
- `/delete_job {作业ID}` - 删除作业

#### 管理命令 (Owner)
- `/set_admin {用户ID}` - 设置管理员

## 🔧 开发指南

### 添加新模型
1. 在 `db/models` 中创建新的模型文件
2. 在 `alembic/env.py` 中导入新模型
3. 运行 `alembic revision --autogenerate -m "描述"`
4. 运行 `alembic upgrade head`

### 添加新命令
1. 在 `api` 目录下创建新的命令文件
2. 使用 `@command` 装饰器定义命令
3. 在 `config/config.py` 的 `ROLE_COMMANDS` 中配置权限
4. 在 `main.py` 中导入新命令模块

### 数据库迁移

```bash
# 生成迁移脚本
alembic revision --autogenerate -m "迁移描述"

# 应用迁移
alembic upgrade head

# 回滚迁移
alembic downgrade -1
```

## 📁 项目结构

```
tgbot/
├── api/                    # API 和命令处理
│   ├── base.py            # 基础命令框架
│   ├── commands.py        # 命令管理
│   ├── emby.py           # Emby 集成
│   ├── qas.py            # 夸克自动下载
│   ├── resource.py       # 资源搜索
│   └── ...
├── config/                # 配置文件
│   ├── config.py         # 主配置
│   ├── prod.py           # 生产环境配置
│   └── test.py           # 测试环境配置
├── db/                    # 数据库相关
│   ├── models/           # 数据模型
│   ├── main.py           # 数据库初始化
│   └── data/             # SQLite 数据库文件
├── utils/                 # 工具函数
│   ├── ai.py             # AI 服务集成
│   ├── emby.py           # Emby 工具
│   ├── qas.py            # QAS 工具
│   └── ...
├── alembic/              # 数据库迁移
├── main.py               # 主入口文件
└── requirements.txt      # 依赖列表
```

## 🔐 安全说明

- 妥善保管 Telegram Bot Token 和其他 API 密钥
- 建议在生产环境中使用环境变量存储敏感信息
- 定期更新依赖包以确保安全性
- 限制机器人的访问权限，避免未授权使用

## 📝 许可证

本项目采用 MIT 许可证 - 详见 LICENSE 文件

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来改进这个项目！

## 🆘 支持

如遇到问题，请：
1. 查看日志文件了解详细错误信息
2. 检查环境变量配置是否正确
3. 确保所有依赖服务正常运行
4. 在 GitHub 提交 Issue 寻求帮助

---

**注意**: 本机器人仅供个人学习和研究使用，请遵守相关法律法规和服务条款。