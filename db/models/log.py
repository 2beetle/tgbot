from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    Enum, ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import enum
from db.models.user import User

from db.models.base import CreateTimeUpdateTimeBase, Base


# 操作类型（CRUD）
class OperationType(enum.Enum):
    CREATE = "CREATE"
    READ   = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"

class OperationLog(Base, CreateTimeUpdateTimeBase):
    __tablename__ = 'operation_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=True)
    user = relationship(User, backref="operation_logs")
    operation = Column(Enum(OperationType), nullable=False)
    target_table = Column(String(64), nullable=True)
    target_id = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
