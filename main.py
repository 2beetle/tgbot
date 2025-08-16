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
from api import cloud_saver
from api import common
from api import job
from api import qas
from api import emby

from utils.job import tag_done_jobs

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

def register_extra_handlers(app):
    modules = [
        'api.common',
        'api.the_movie_db',
        'api.cloud_saver',
        'api.job',
        'api.qas',
        'api.emby',
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
    text = "<b>📖 可用命令列表：</b>\n"
    text += "<pre>命令       参数         描述\n"
    text += "-------------------------------\n"
    for cmd in commands:
        text += f"/{cmd['name']:<10} {cmd['args']:<12} {cmd['description']}\n"
    text += "</pre>"

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

if __name__ == '__main__':
    init = Init()
    cloud_saver = CloudSaver()

    application = ApplicationBuilder()\
        .token(TG_BOT_TOKEN)\
        .post_init(post_init)\
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