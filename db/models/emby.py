from sqlalchemy import Integer, Column, String, ForeignKey
from sqlalchemy.orm import relationship

from db.models.base import Base, CreateTimeUpdateTimeBase
from db.models.user import User


class EmbyConfig(Base, CreateTimeUpdateTimeBase):
    __tablename__ = 'emby_config'
    id = Column(Integer, primary_key=True, autoincrement=True)
    api_token = Column(String(256), nullable=False)
    username = Column(String(256), nullable=False, server_default="admin")
    password = Column(String(256), nullable=False, server_default="admin")
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False, unique=True)
    user = relationship(User)
    host = Column(String(256), nullable=False)