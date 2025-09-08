import asyncio
import logging
from collections import defaultdict

from sqlalchemy.orm import Session
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler

from api.base import command
from config.config import get_allow_roles_command_map
from db.models.log import OperationLog, OperationType
from db.models.user import User
from utils.command_middleware import depends
from utils.pansou import PanSou
from utils.quark import Quark

logger = logging.getLogger(__name__)


@command(name='search_media_resource', description="搜索资源", args="{resource name}")
async def search_media_resource(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    async def cs_task(search_content: str):
        cloud_saver = context.bot_data['cloud_saver']
        resp = await cloud_saver.search(search_content)
        return resp.json().get('data')

    async def ps_task(search_content: str):
        p = PanSou()
        data = await p.search(search_content)
        return data.get('data')

    if len(context.args) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="缺少资源名称")
    search_content = context.args[0]

    cloud_saver = context.bot_data['cloud_saver']
    p = PanSou()

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="资源搜索中，请稍等",
        parse_mode="html"
    )

    cs_result, ps_result = await asyncio.gather(
        cs_task(search_content),
        ps_task(search_content)
    )

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="资源搜索已完成，正在校验资源有效性，请稍等",
        parse_mode="html"
    )

    all_links = defaultdict(list)
    links_valid = dict()

    # cs
    for channel_data in cs_result:
        for item in channel_data.get("list", []):
            for link in item.get("cloudLinks", []):
                url = link.get("link")
                if url:
                    all_links[cloud_saver.cloud_type_map.get(link.get("cloudType", "").upper())].append(url)
                    links_valid[url] = '状态未知'
    # ps
    for cloud_type, resources in ps_result.get('merged_by_type').items():
        for resource in resources:
            all_links[p.cloud_type_map.get(cloud_type)].append(resource.get('url'))
            links_valid[resource.get('url')] = '状态未知'

    # 查看夸克链接的状态
    quark = Quark()
    quark_links_valid = await quark.links_valid(links=all_links.get('夸克网盘', []))

    # 更新各网盘链接状态
    links_valid.update(quark_links_valid)

    # cs
    cs_messages = await cloud_saver.format_links_by_cloud_type(cs_result, links_valid)

    # ps
    ps_messages = await p.format_links_by_cloud_type(ps_result, links_valid)

    messages = cs_messages + ps_messages

    session.add(
        OperationLog(
            user_id=user.id,
            operation=OperationType.READ,
            description=f"用户{user.tg_id} - {user.username} 搜索资源 {search_content}"
        )
    )
    session.commit()

    for message in messages:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=message,
                parse_mode="html"
            )
        except Exception as e:
            logger.error(f"resource reply (text: {message}) error: {e}")
            continue


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