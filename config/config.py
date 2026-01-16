import os
from collections import defaultdict
from typing import List

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from telegram import BotCommand

TIME_ZONE = "Asia/Shanghai"

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'db/data')
TG_DB_PATH = os.path.join(DATA_PATH, 'tgbot.db')

TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN')

# 加密配置 - 必需的环境变量
CRYPTO_PASSWORD = os.getenv('CRYPTO_PASSWORD')
CRYPTO_SALT = os.getenv('CRYPTO_SALT')

# 验证必需的加密环境变量
if not CRYPTO_PASSWORD:
    raise ValueError("环境变量 CRYPTO_PASSWORD 未配置，必须设置加密密码")
if not CRYPTO_SALT:
    raise ValueError("环境变量 CRYPTO_SALT 未配置，必须设置加密盐值")
if len(CRYPTO_PASSWORD) < 16:
    raise ValueError("CRYPTO_PASSWORD 长度必须至少16位，建议更长的强密码")
if len(CRYPTO_SALT) < 16:
    raise ValueError("CRYPTO_SALT 长度必须至少16位，建议更长的随机字符串")

OWNER_ROLE_NAME = 'owner'
ADMIN_ROLE_NAME = 'admin'
USER_ROLE_NAME = 'user'

DEFAULT_COMMANDS = [
        BotCommand('register', "注册"),
        BotCommand('refresh_menu', "刷新菜单"),
    ]

ROLE_COMMANDS = {
        USER_ROLE_NAME: ["help", 'refresh_menu', "my_info",
                         'search_tv', 'search_movie',
                         'search_media_resource',
                         "upsert_configuration",
                         'qas_list_task', 'qas_list_err_task', 'qas_add_task', 'qas_delete_task', 'qas_run_script', 'qas_view_task_regex',
                         'emby_list_resource', 'emby_list_notification'
                         ],

        ADMIN_ROLE_NAME: ["help", 'refresh_menu', "my_info",
                          'search_tv', 'search_movie',
                          'search_media_resource',
                          'remind', 'list_my_job', 'delete_job',
                          "upsert_configuration",
                          'qas_list_task', 'qas_list_err_task', 'qas_add_task', 'qas_delete_task', 'qas_run_script', 'qas_view_task_regex',
                          'emby_list_resource', 'emby_list_notification'
                          ],

        OWNER_ROLE_NAME: ["help", 'refresh_menu', "my_info", 'set_admin',
                          'search_tv', 'search_movie',
                          'search_media_resource',
                          'remind', 'list_my_job', 'delete_job',
                          "upsert_configuration",
                          'qas_list_task', 'qas_list_err_task', 'qas_add_task', 'qas_delete_task', 'qas_run_script', 'qas_view_task_regex', 'qas_tag_start_file',
                          'emby_list_resource', 'emby_list_notification'
                          ],
    }

def get_allow_roles_command_map() -> dict:
    result = defaultdict(list)
    for role, commands in ROLE_COMMANDS.items():
        for command in commands:
            result[command].append(role)
    return result

TMDB_API_KEY = os.environ.get('TMDB_API_KEY')
TMDB_POSTER_BASE_URL = os.environ.get('TMDB_POSTER_BASE_URL', 'https://image.tmdb.org/t/p/original')

# CloudSaver
CLOUD_SAVER_HOST = os.environ.get('CLOUD_SAVER_HOST')
CLOUD_SAVER_USERNAME = os.environ.get('CLOUD_SAVER_USERNAME')
CLOUD_SAVER_PASSWORD = os.environ.get('CLOUD_SAVER_PASSWORD')

# 网盘类型常量（用于代码引用，避免硬编码）
CLOUD_TYPE_QUARK = "夸克网盘"
CLOUD_TYPE_ALIPAN = "阿里云盘"
CLOUD_TYPE_123PAN = "123网盘"
CLOUD_TYPE_XUNLEI = "迅雷云盘"
CLOUD_TYPE_BAIDUPAN = "百度网盘"
CLOUD_TYPE_UC = "UC网盘"
CLOUD_TYPE_WETRANSFER = "WeTransfer"

# 网盘类型配置（全局唯一值）
CLOUD_TYPE_MAP = {
    "QUARK": CLOUD_TYPE_QUARK,
    "ALIPAN": CLOUD_TYPE_ALIPAN,
    "ALIYUN": CLOUD_TYPE_ALIPAN,
    "123PAN": CLOUD_TYPE_123PAN,
    "PAN123": CLOUD_TYPE_123PAN,
    "XUNLEI": CLOUD_TYPE_XUNLEI,
    "WETRANSFER": CLOUD_TYPE_WETRANSFER,
    "BAIDUPAN": CLOUD_TYPE_BAIDUPAN,
    "UC": CLOUD_TYPE_UC,
    "quark": CLOUD_TYPE_QUARK,
    "baidu": CLOUD_TYPE_BAIDUPAN,
}

# 所有可用的网盘类型名称
AVAILABLE_CLOUD_TYPES = set(CLOUD_TYPE_MAP.values())

JOB_STORES = {
    'default': SQLAlchemyJobStore(url=f'sqlite:///{TG_DB_PATH}')
}

AI_API_KEYS = {
    'openai': {
        'host': os.environ.get('OPENAI_HOST'),
        'api_key': os.environ.get('OPENAI_API_KEY'),
        'model': os.environ.get('OPENAI_MODEL'),
    },
    'deepseek': {
        'host': os.environ.get('DEEPSEEK_HOST'),
        'api_key': os.environ.get('DEEPSEEK_API_KEY'),
        'model': os.environ.get('DEEPSEEK_MODEL'),
    },
    'kimi': {
        'host': os.environ.get('KIMI_HOST'),
        'api_key': os.environ.get('KIMI_API_KEY'),
        'model': os.environ.get('KIMI_MODEL'),
    }
}

AI_PROVIDER = os.environ.get('AI_PROVIDER', 'kimi').lower()
AI_HOST = AI_API_KEYS[AI_PROVIDER]['host']
AI_API_KEY = AI_API_KEYS[AI_PROVIDER]['api_key']
AI_MODEL = AI_API_KEYS[AI_PROVIDER]['model']


if os.getenv("ENV") == "TEST":
    from config.test import *
else:
    from config.prod import *