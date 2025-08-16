import datetime
import logging
from os.path import exists

import telegram
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from telegram import Bot

from config.config import TG_BOT_TOKEN
from db.models import model_engine
from db.models.external import ApschedulerJobs
from db.models.job import UserApschedulerJobs

logger = logging.getLogger(__name__)

async def send_message(message: str, chat_id: int):
    bot = telegram.Bot(token=TG_BOT_TOKEN)
    await bot.send_message(
        chat_id=chat_id,
        text=message,
        parse_mode="HTML"
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