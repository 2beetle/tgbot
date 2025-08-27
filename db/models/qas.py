from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from db.models.base import Base, CreateTimeUpdateTimeBase
from db.models.user import User


class QuarkAutoDownloadConfig(Base, CreateTimeUpdateTimeBase):
    __tablename__ = 'qas_config'
    id = Column(Integer, primary_key=True, autoincrement=True)
    api_token = Column(String(256), nullable=False)
    save_path_prefix = Column(String(256), nullable=False, default='/', server_default='/')
    movie_save_path_prefix = Column(String(256), nullable=False, default='/', server_default='/')
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False, unique=True)
    user = relationship(User)
    host = Column(String(256), nullable=False)
    pattern = Column(String(256), nullable=False, default='.*.(mp4|mkv)', server_default='.*.(mp4|mkv)')
    replace = Column(String(256), nullable=False, default='{SXX}E{E}.{EXT}', server_default='{SXX}E{E}.{EXT}')
