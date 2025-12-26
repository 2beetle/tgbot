from sqlalchemy import Column, Integer, String, ForeignKey, JSON
from sqlalchemy.orm import relationship

from db.models.base import Base, CreateTimeUpdateTimeBase


class Role(Base, CreateTimeUpdateTimeBase):
    __tablename__ = 'role'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True)


class User(Base, CreateTimeUpdateTimeBase):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(Integer, unique=True, nullable=False)
    chat_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, nullable=False)
    role_id = Column(Integer, ForeignKey('role.id'), nullable=False)
    role = relationship("Role", backref="users")
    configuration = Column(JSON, nullable=True, default=None)