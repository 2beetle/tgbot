import os
from collections import defaultdict
from typing import List

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from telegram import BotCommand

TIME_ZONE = "Asia/Shanghai"

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'db/data')
TG_DB_PATH = os.path.join(DATA_PATH, 'tgbot.db')

TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN')

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
                         'qas_list_task', 'qas_add_task', 'qas_delete_task', 'qas_run_script', 'qas_view_task_regex',
                         'emby_list_resource', 'emby_list_notification'
                         ],

        ADMIN_ROLE_NAME: ["help", 'refresh_menu', "my_info",
                          'search_tv', 'search_movie',
                          'search_media_resource',
                          'remind', 'list_my_job', 'delete_job',
                          "upsert_configuration",
                          'qas_list_task', 'qas_add_task', 'qas_delete_task', 'qas_run_script', 'qas_view_task_regex',
                          'emby_list_resource', 'emby_list_notification'
                          ],

        OWNER_ROLE_NAME: ["help", 'refresh_menu', "my_info", 'set_admin',
                          'search_tv', 'search_movie',
                          'search_media_resource',
                          'remind', 'list_my_job', 'delete_job',
                          "upsert_configuration",
                          'qas_list_task', 'qas_add_task', 'qas_delete_task', 'qas_run_script', 'qas_view_task_regex',
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