import importlib
import logging

import telegram
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from telegram import Update, BotCommandScopeChat
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

from api.base import get_handlers, command, get_bot_commands
from api.commands import set_commands
from config.config import TG_BOT_TOKEN, ROLE_COMMANDS, DEFAULT_COMMANDS

from db.main import Init
from db.models.user import User
from api.base import commands as all_commands
from utils.cloud_saver import CloudSaver
from utils.command_middleware import depends

from api import user
from api import the_movie_db
from api import resource
from api import common
from api import job
from api import qas
from api import emby
from api import ai_config
from api import user_config

from utils.job import tag_done_jobs, check_quark_cookies_validity

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

def register_extra_handlers(app):
    modules = [
        'api.common',
        'api.the_movie_db',
        'api.resource',
        'api.job',
        'api.qas',
        'api.emby',
        'api.ai_config',
        'api.user_config',
    ]
    for module_path in modules:
        try:
            mod = importlib.import_module(module_path)
            handlers = getattr(mod, 'handlers', [])
            for handler in handlers:
                logger.info("Adding handler from %s: %s", module_path, handler)
                app.add_handler(handler)
        except Exception as e:
            logger.error("Failed to load handlers from %s: %s", module_path, e)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    await set_commands(update, context, session)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="I'm a bot, please talk to me!"
    )


@command(name='refresh_menu', description="刷新菜单")
async def refresh_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"Refresh user {update.effective_user.id} commands")
    if not user:
        await context.bot.set_my_commands(DEFAULT_COMMANDS, scope=telegram.BotCommandScopeChat(update.effective_user.id))

    else:
        bot_commands = get_bot_commands()
        command_names = ROLE_COMMANDS.get(user.role.name)
        to_set_commands = list()
        for command_name in command_names:
            to_set_commands.append(bot_commands[command_name])
        await context.bot.set_my_commands(to_set_commands, scope=telegram.BotCommandScopeChat(user.tg_id))

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="刷新菜单成功"
    )

@command(name='help', description="帮助")
async def help_tips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = await context.bot.get_my_commands(scope=BotCommandScopeChat(update.effective_chat.id))
    logger.info(f"user commands: {commands}")
    logger.info(f"all_commands: {all_commands}")
    commands_name = [_['command'] for _ in commands]
    commands = [c for c in all_commands if c['name'] in commands_name]

    # 按功能分组命令
    command_groups = {
        "基础功能": ["register", "help", "refresh_menu", "my_info"],
        "媒体搜索": ["search_tv", "search_movie", "search_media_resource"],
        "配置管理": ["upsert_configuration"],
        "QAS功能": ["qas_add_task", "qas_list_task", "qas_delete_task", "qas_run_script", "qas_view_task_regex", "qas_update_task"],
        "Emby功能": ["emby_list_resource", "emby_list_notification"],
        "提醒功能": ["remind", "list_my_job", "delete_job"]
    }

    # 为命令分组
    grouped_commands = {}
    for group, cmd_names in command_groups.items():
        grouped_commands[group] = []
        for cmd in commands:
            if cmd['name'] in cmd_names:
                grouped_commands[group].append(cmd)

    # 构建帮助消息
    text = "<b>📖 Bot 帮助文档</b>\n\n"

    for group, cmd_list in grouped_commands.items():
        if cmd_list:  # 只显示有命令的组
            text += f"<b>📁 {group}：</b>\n"
            for cmd in cmd_list:
                cmd_text = f"• <code>/{cmd['name']}</code>"
                if cmd['args']:
                    cmd_text += f" <code>{cmd['args']}</code>"
                text += cmd_text + f"\n  📝 {cmd['description']}\n"
            text += "\n"

    # 添加没有分组的命令
    other_commands = []
    for cmd in commands:
        if not any(cmd['name'] in cmd_names for cmd_names in command_groups.values()):
            other_commands.append(cmd)

    if other_commands:
        text += "<b>📁 其他功能：</b>\n"
        for cmd in other_commands:
            cmd_text = f"• <code>/{cmd['name']}</code>"
            if cmd['args']:
                cmd_text += f" <code>{cmd['args']}</code>"
            text += cmd_text + f"\n  📝 {cmd['description']}\n"

    text += "\n<i>💡 提示：点击命令可以直接复制</i>"

    # 如果消息太长，分开发送
    if len(text) > 4096:
        # 分割消息
        parts = []
        current_part = ""
        lines = text.split('\n')

        for line in lines:
            if len(current_part + line + '\n') > 4000:
                parts.append(current_part)
                current_part = line + '\n'
            else:
                current_part += line + '\n'

        if current_part:
            parts.append(current_part)

        # 发送第一部分（包含标题和第一组）
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=parts[0],
            parse_mode="HTML"
        )

        # 发送剩余部分
        for part in parts[1:]:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=part,
                parse_mode="HTML"
            )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode="HTML"
        )

async def post_init(app):
    app.bot_data['async_scheduler'].start()
    app.bot_data['async_scheduler'].add_job(
        tag_done_jobs,
        trigger=IntervalTrigger(minutes=1),
        id="tag_done_jobs",
        replace_existing=True
    )
    app.bot_data['async_scheduler'].add_job(
        check_quark_cookies_validity,
        trigger=IntervalTrigger(hours=6),
        id="check_quark_cookies_validity",
        replace_existing=True
    )


async def post_shutdown(app: telegram.ext.Application):
    """应用关闭时清理资源"""
    logger.info("Shutting down application, cleaning up resources...")

    # 停止调度器
    scheduler = app.bot_data.get('async_scheduler')
    if scheduler:
        scheduler.shutdown()
        logger.info("Scheduler shutdown complete")

    # 关闭 CloudSaver 的 ClientSession
    cloud_saver = app.bot_data.get('cloud_saver')
    if cloud_saver:
        await cloud_saver.close()
        logger.info("CloudSaver session closed")

if __name__ == '__main__':
    init = Init()
    cloud_saver = CloudSaver()

    application = ApplicationBuilder()\
        .token(TG_BOT_TOKEN)\
        .post_init(post_init)\
        .post_shutdown(post_shutdown)\
        .concurrent_updates(True)\
        .build()

    application.bot_data['db_session_local'] = init.session_local
    application.bot_data['cloud_saver'] = cloud_saver
    application.bot_data['async_scheduler'] = init.async_scheduler

    application.add_handler(CommandHandler('start', depends()(start)))
    application.add_handler(CommandHandler('help', help_tips))
    application.add_handler(CommandHandler('refresh_menu', depends()(refresh_menu)))

    for handler in get_handlers():
        logger.info("Adding handler: %s", handler)
        application.add_handler(handler)

    register_extra_handlers(app=application)

    application.run_polling()