import logging
from typing import List, Optional

import telegram
from sqlalchemy.orm import Session
from telegram import Update, BotCommand, BotCommandScopeDefault
from telegram.ext import ContextTypes

from api.base import get_bot_commands
from config.config import ROLE_COMMANDS
from db.models.user import User

logger = logging.getLogger(__name__)


async def set_commands(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, users: Optional[List[User]]=None):
    if not users:
        users = session.query(User).all()
    logger.info(f"Setting {len(users)} users commands")
    await context.bot.set_my_commands([
        BotCommand('register', "注册"),
        BotCommand('refresh_menu', "刷新菜单"),
    ], scope=BotCommandScopeDefault())

    bot_commands = get_bot_commands()
    for user in users:
        if not user:
            continue
        command_names = ROLE_COMMANDS.get(user.role.name)
        to_set_commands = list()
        for command_name in command_names:
            to_set_commands.append(bot_commands[command_name])
        await context.bot.set_my_commands(to_set_commands, scope=telegram.BotCommandScopeChat(user.tg_id))


