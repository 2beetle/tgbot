import datetime
import json
import uuid

import pytz
from sqlalchemy.orm import Session
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler

from api.base import command
from config.config import TIME_ZONE, AI_API_KEYS
from db.models.job import UserApschedulerJobs
from db.models.user import User
from utils.ai import openapi_chat
from utils.job import send_message


@command(name='remind', description="提醒", args="{输入包含时间以及内容的自然语言文本}")
async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if len(context.args) == 0:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="请说出需要提醒的事项以及时间"
        )
        return
    content = ' '.join(context.args)
    async_scheduler = context.bot_data['async_scheduler']

    # 解析任务
    prompt = f"""
当前时间是{datetime.datetime.now(pytz.timezone(TIME_ZONE)).strftime("%Y-%m-%d %H:%M:%S")}
请从以下信息中提取时间日期信息和具体需要提醒别人的内容：
"{content}"

只需返回JSON格式的结果，包含两个字段：
1. remind_content: 提醒的具体内容
2. run_date: 执行提醒的日期和时间（格式为：YYYY-MM-DD HH:MM:SS）

EXAMPLE JSON OUTPUT:
{{
    "remind_content": "喝水",
    "run_date": " 2025-01-01 01:00:00"
}}

如果无法确定具体时间，请使用最合理的推测。
如果完全无法提取时间信息，请将run_date设为null。
"""
    ai_analysis = await openapi_chat(
        role="你是一个提取信息的助手，你需要从信息中提取时间信息和具体需要提醒别人的内容",
        prompt=prompt,
        host=AI_API_KEYS.get('kimi').get('host'),
        api_key=AI_API_KEYS.get('kimi').get('api_key'),
        model=AI_API_KEYS.get('kimi').get('model'),
    )

    # 清理可能的非JSON内容
    ai_analysis = ai_analysis.strip()
    if ai_analysis.startswith("```json"):
        ai_analysis = ai_analysis[7:]
    if ai_analysis.endswith("```"):
        ai_analysis = ai_analysis[:-3]

    remind_data = json.loads(ai_analysis)

    run_date = datetime.datetime.strptime(remind_data.get('run_date'), '%Y-%m-%d %H:%M:%S')
    remind_content = remind_data.get('remind_content')

    job_id = str(uuid.uuid4())

    async_scheduler.add_job(
        'utils.job:send_message',
        trigger="date",
        run_date=run_date,
        kwargs={
            'message': remind_content,
            'chat_id': update.effective_chat.id,
        },
        id=job_id
    )

    session.add(
        UserApschedulerJobs(
            user_id=user.id,
            apscheduler_job_id=job_id,
            description=content,
        )
    )
    session.commit()

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f'我将会在 {run_date} 提醒你 {remind_content}'
    )


def upsert_configuration_build_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton("QAS", callback_data=f"upsert_qas_configuration"),
        InlineKeyboardButton("Emby", callback_data=f"upsert_emby_configuration")
    ]
    return InlineKeyboardMarkup([buttons]) if buttons else None



@command(name='upsert_configuration', description="插入或更新相关配置")
async def upsert_configuration(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    await update.message.reply_text(
        text="选择你要新增或更新的配置",
        reply_markup=upsert_configuration_build_keyboard()
    )

async def cancel_conversation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("操作已取消")
    return ConversationHandler.END

handlers = [
    CallbackQueryHandler(
            cancel_conversation_callback,
            pattern=r"^cancel_conversation$"
    )
]
