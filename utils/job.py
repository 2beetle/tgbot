import datetime
import logging

import telegram
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config.config import TG_BOT_TOKEN
from db.models import model_engine
from db.models.external import ApschedulerJobs
from db.models.job import UserApschedulerJobs
from db.models.user import User

logger = logging.getLogger(__name__)

async def send_message(message: str, chat_id: int):
    bot = telegram.Bot(token=TG_BOT_TOKEN)
    await bot.send_message(
        chat_id=chat_id,
        text=message,
        parse_mode="HTML"
    )


async def send_reminder_message(message: str, chat_id: int, job_id: str):
    bot = telegram.Bot(token=TG_BOT_TOKEN)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("完成 ✅", callback_data=f"remind_done:{job_id}")]])
    await bot.send_message(
        chat_id=chat_id,
        text=message,
        parse_mode="HTML",
        reply_markup=keyboard
    )


async def tag_done_jobs():
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=model_engine)
    with session_local() as session:
        subquery = (
            session.query(UserApschedulerJobs.id)
            .outerjoin(
                ApschedulerJobs, UserApschedulerJobs.apscheduler_job_id == ApschedulerJobs.id
            )
            .filter(
                ApschedulerJobs.id == None,
                UserApschedulerJobs.deleted_at.is_(None)
            )
            .subquery()
        )

        session.query(UserApschedulerJobs).filter(UserApschedulerJobs.id.in_(select(subquery))).update(
            {UserApschedulerJobs.deleted_at: datetime.datetime.utcnow()},
            synchronize_session=False
        )
        session.commit()
        logger.info(f"标记删除已完成任务")


async def check_quark_cookies_validity():
    """检查所有用户的夸克网盘 Cookies 是否有效"""
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=model_engine)
    with session_local() as session:
        # 查询所有配置了夸克 cookies 的用户
        users = session.query(User).filter(
            User.configuration.isnot(None)
        ).all()

        for user in users:
            # 检查用户是否配置了夸克 cookies
            if not user.configuration or not user.configuration.get('quark_cookies'):
                continue

            try:
                # 获取解密后的 cookies
                from api.user_config import get_user_quark_cookies
                quark_cookies = await get_user_quark_cookies(user)

                if not quark_cookies:
                    continue

                # 检查 cookies 是否有效
                from utils.quark import Quark
                quark = Quark(cookies=quark_cookies)
                account_info = await quark.get_account_info()

                if not account_info:
                    # Cookies 已过期,发送通知
                    logger.warning(f"用户 {user.username} (ID: {user.id}) 的夸克网盘 Cookies 已过期")

                    message = (
                        "⚠️ <b>夸克网盘 Cookies 已过期</b>\n\n"
                        "您的夸克网盘 Cookies 已失效，请重新配置。\n"
                        "使用 /upsert_configuration 命令更新「夸克网盘」Cookies。"
                    )

                    await send_message(message, user.chat_id)
                else:
                    logger.info(f"用户 {user.username} (ID: {user.id}) 的夸克网盘 Cookies 有效")

            except Exception as e:
                logger.error(f"检查用户 {user.username} (ID: {user.id}) 的夸克 Cookies 时出错: {e}")

