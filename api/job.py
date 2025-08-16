import datetime
import math

import pytz
from sqlalchemy.orm import Session
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler

from api.base import command
from config.config import ADMIN_ROLE_NAME, OWNER_ROLE_NAME, get_allow_roles_command_map, TIME_ZONE
from db.models.job import UserApschedulerJobs
from db.models.user import User
from utils.command_middleware import depends


def list_my_job_build_keyboard(page: int, total_page: int) -> InlineKeyboardMarkup:
    buttons = []
    if page < total_page:
        buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"list_my_job:{page + 1}"))
    return InlineKeyboardMarkup([buttons]) if buttons else None


@command(name='list_my_job', description="列出我的任务")
async def list_my_job(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    page_size = 10
    if len(context.args) == 0:
        page = 1
    else:
        page = int(context.args[0])
    base_query = session.query(UserApschedulerJobs).filter(
        UserApschedulerJobs.user_id == user.id,
        UserApschedulerJobs.deleted_at.is_(None),
    )

    count = base_query.count()
    total_page = math.ceil(count / page_size)

    jobs = base_query.offset((page-1)*page_size).limit(page_size).all()

    lines = []
    lines.append(f"<b>一共有 {count} 个任务：</b>")

    for i, job in enumerate(jobs, start=1):
        desc = (job.description or '').strip()
        created_at = job.created_at.replace(tzinfo=pytz.UTC).astimezone(pytz.timezone(TIME_ZONE)).strftime('%Y-%m-%d %H:%M')
        job_id = job.id
        lines.append(f"{i}. <b>ID:</b> {job_id}")
        lines.append(f"<b>描述：</b> {desc}")
        lines.append(f"<b>创建时间：</b> {created_at}")
        lines.append(f"\n")

    text = '\n'.join(lines)

    keyboard = list_my_job_build_keyboard(page, total_page)

    await update.message.reply_text(
        text=text,
        reply_markup=keyboard,
        parse_mode='HTML'
    )


async def on_list_my_job_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()

    _, args = query.data.split(":")
    page = args.split(' ')[0]
    context.args = [int(page)]

    await list_my_job(update, context, session, user)



@command(name='delete_job', description="删除任务", args="{任务 id}")
async def delete_job(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if len(context.args) == 0:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="请输入任务 ID"
        )
    async_scheduler = context.bot_data['async_scheduler']

    job_id = context.args[0]

    job = session.query(UserApschedulerJobs).filter_by(id=job_id).first()

    if job is None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="此任务不存在"
        )
    else:
        if job.user_id != user.id and user.role.name not in [OWNER_ROLE_NAME, ADMIN_ROLE_NAME]:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="权限不足"
            )
        else:
            session.query(UserApschedulerJobs).filter_by(id=job_id).update({
                UserApschedulerJobs.deleted_at: datetime.datetime.utcnow()
            })
            session.commit()
            async_scheduler.remove_job(job_id=job.apscheduler_job_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"删除任务 {job_id} 成功"
            )


handlers = [
    CallbackQueryHandler(
        depends(allowed_roles=get_allow_roles_command_map().get('list_my_job'))(on_list_my_job_callback),
        pattern=r"^list_my_job:.*$")
]