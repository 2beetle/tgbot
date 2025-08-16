import datetime
from contextlib import contextmanager

from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, declared_attr

# 定义数据库和基础类
Base = declarative_base()

class CreateTimeUpdateTimeBase:
    @declared_attr
    def created_at(cls):
        return Column(DateTime, default=datetime.datetime.utcnow)

    @declared_attr
    def updated_at(cls):
        return Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class DeletedTimeBase:
    @declared_attr
    def deleted_at(cls):
        return Column(DateTime, default=None, nullable=True)