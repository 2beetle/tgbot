import datetime
import json
import logging
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

logger = logging.getLogger(__name__)


@command(name='remind', description="提醒", args="{输入包含时间以及内容的自然语言文本}")
async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    def explain_cron(cron):
        week_map = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

        # 解析月份
        month = cron.get('month', '*')
        if month in ['*', '?']:
            month_part = "每月"
        else:
            month_names = [f"{int(m)}月" for m in str(month).split(',')]
            month_part = "、".join(month_names)

        # 解析日或星期
        day = cron.get('day', '*')
        dow = cron.get('day_of_week', '*')
        if day not in ['*', '?']:
            day_part = "、".join([f"{int(d)}号" for d in str(day).split(',')])
        elif dow not in ['*', '?']:
            dow_names = [week_map[int(x)] for x in str(dow).split(',')]
            day_part = "、".join(dow_names)
        else:
            day_part = "每天"

        # 解析时间
        def parse_time_part(value, unit):
            if value == '*':
                return f"每{unit}"
            if value.startswith('*/'):
                return f"每{value[2:]}{unit}"
            # 多个值
            if ',' in value:
                return "、".join([f"{int(v):02d}" for v in value.split(',')])
            return f"{int(value):02d}"

        hour = parse_time_part(str(cron.get('hour', '0')), "小时")
        minute = parse_time_part(str(cron.get('minute', '0')), "分钟")

        # 拼接结果
        if "每" in hour or "每" in minute:
            time_part = f"{hour}{minute}"
        else:
            time_part = f"{hour}:{minute}"

        return f"{month_part}{day_part} {time_part}"

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
请从以下信息中提取时间日期信息或周期信息和具体需要提醒别人的内容：
"{content}"

只需返回JSON格式的结果，包含两个字段：
1. remind_content: 提醒的具体内容
2. trigger：是一次性的提醒还是周期提醒，若一次性的提醒请返回「date」，周期提醒请返回「cron」，只能在 date和cron中选一个
3. run_date: 若trigger为「date」，即是一次性提醒，请返回执行提醒的日期和时间（格式为：YYYY-MM-DD HH:MM:SS），否则为空字符串
4. cron: 若trigger为「cron」，即是周期提醒，请返回json格式的周期信息内容，例如
    1. 每天8点: {{
        'minute': '0',
        'hour': '8',
        'day': '*',
        'month': '*',
        'day_of_week': '*'
    }}
    2. 每周三10点30分{{
        'minute': '30',
        'hour': '10',
        'day': '*',
        'month': '*',
        'day_of_week': '2'
    }}
    ，否则为空字符串
    

EXAMPLE JSON OUTPUT:
{{
    "remind_content": "喝水",
    "trigger": "date",
    "run_date": " 2025-01-01 01:00:00",
    "cron": ""
}}

{{
    "remind_content": "写日记",
    "trigger": "cron",
    "run_date": "",
    "cron": {{
        'minute': '0',
        'hour': '8',
        'day': '*',
        'month': '*',
        'day_of_week': '*'
    }}
}}

如果无法确定具体时间，请使用最合理的推测。
"""
    ai_analysis = await openapi_chat(
        role="你是一个信息提取专家，能够根据要求准确地提取到所需内容",
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


    logger.info(f"remind_data: {remind_data}")

    job_id = str(uuid.uuid4())
    remind_content = remind_data.get('remind_content')
    trigger = remind_data.get('trigger')

    if trigger == 'date':
        run_date = datetime.datetime.strptime(remind_data.get('run_date'), '%Y-%m-%d %H:%M:%S')

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
        reply_message = f'我将会在 {run_date} 提醒你 {remind_content}'

    elif trigger == 'cron':
        async_scheduler.add_job(
            'utils.job:send_message',
            trigger="cron",
            **remind_data.get('cron'),
            kwargs={
                'message': remind_content,
                'chat_id': update.effective_chat.id,
            },
            id=job_id
        )
        reply_message = f'我将会在 {explain_cron(remind_data.get('cron'))} 提醒你 {remind_content}'

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
        text=reply_message
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
