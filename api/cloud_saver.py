import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler

from api.base import command
from config.config import get_allow_roles_command_map
from db.models.log import OperationLog, OperationType
from db.models.user import User
from utils.command_middleware import depends


logger = logging.getLogger(__name__)


@command(name='search_media_resource', description="搜索资源", args="{resource name}")
async def search_media_resource(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    cloud_saver = context.bot_data['cloud_saver']
    if len(context.args) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="缺少资源名称")
    search_content = context.args[0]
    resp = cloud_saver.search(search_content)
    messages = cloud_saver.format_links_by_channel(resp.json().get('data'))

    session.add(
        OperationLog(
            user_id=user.id,
            operation=OperationType.READ,
            description=f"用户{user.tg_id} - {user.username} 搜索资源 {search_content}"
        )
    )
    session.commit()

    for message in messages:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message,
            parse_mode="html"
        )


async def on_search_media_resource_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()

    # 从 callback_data 中提取页码
    _, search_content = query.data.split(":")
    context.args = [search_content]

    await search_media_resource(update, context, session, user)


handlers = [
    CallbackQueryHandler(
        depends(allowed_roles=get_allow_roles_command_map().get('search_media_resource'))(on_search_media_resource_callback),
        pattern=r"^search_media_resource:.*$"),
]