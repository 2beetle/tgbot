import asyncio
import logging

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.config import JOB_STORES

logger = logging.getLogger(__name__)

async def main():
    scheduler = AsyncIOScheduler(
        jobstores=JOB_STORES,
        timezone=pytz.timezone('Asia/Shanghai')
    )
    scheduler.start()
    scheduler.shutdown()

    logger.info("Initialization finished")

if __name__ == '__main__':
    asyncio.run(main())