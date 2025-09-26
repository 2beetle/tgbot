from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from db.models.base import Base, CreateTimeUpdateTimeBase
from db.models.user import User


class AIProviderConfig(Base, CreateTimeUpdateTimeBase):
    __tablename__ = 'ai_provider_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    user = relationship(User)

    # AI提供商名称 (openai, deepseek, kimi, etc.)
    provider_name = Column(String(32), nullable=False)

    # API配置（加密存储）
    api_key = Column(String(512), nullable=False)
    host = Column(String(256), nullable=True)
    model = Column(String(128), nullable=True)

    # 是否为默认提供商
    is_default = Column(Boolean, nullable=False, default=False, server_default='0')

    # 提供商特定配置（JSON格式，可选）
    extra_config = Column(String(1024), nullable=True)

    __table_args__ = (
        {'sqlite_autoincrement': True},
    )