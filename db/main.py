import os
import sqlite3

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.config import ADMIN_ROLE_NAME, OWNER_ROLE_NAME, USER_ROLE_NAME, TG_DB_PATH, JOB_STORES
from db.models.base import Base
from db.models.user import Role


class Init:
    def __init__(self):
        self.engine = create_engine(f'sqlite:///{TG_DB_PATH}', echo=True)
        self.session_local = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        # # Initialize APScheduler tables first
        # self.init_apscheduler_tables()
        # Then initialize other database tables
        self.init_db()
        # Finally initialize the scheduler for actual use
        self.init_apscheduler()

    def init_apscheduler_tables(self):
        """Initialize APScheduler tables without starting the scheduler"""
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

        # Create a temporary jobstore to initialize tables
        temp_jobstore = SQLAlchemyJobStore(url=f'sqlite:///{TG_DB_PATH}')
        # This will create the necessary tables
        temp_jobstore.start()

    def init_apscheduler(self):
        self.async_scheduler = AsyncIOScheduler(
            jobstores=JOB_STORES,
            timezone=pytz.timezone('Asia/Shanghai')
        )

    def init_db(self):
        Base.metadata.create_all(self.engine)
        self.init_role()

    def init_role(self):
        with self.session_local() as session:
            count = session.query(Role).count()
            if count == 0:
                owner_role = Role(name=OWNER_ROLE_NAME)
                admin_role = Role(name=ADMIN_ROLE_NAME)
                user_role = Role(name=USER_ROLE_NAME)
                session.add(owner_role)
                session.add(admin_role)
                session.add(user_role)
                session.commit()
