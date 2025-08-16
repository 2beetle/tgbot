from sqlalchemy import Column, Integer, ForeignKey, String, TEXT
from sqlalchemy.orm import relationship

from db.models.base import Base, CreateTimeUpdateTimeBase, DeletedTimeBase
from db.models.external import ApschedulerJobs
from db.models.user import User


class UserApschedulerJobs(Base, CreateTimeUpdateTimeBase, DeletedTimeBase):
    __tablename__ = 'user_apscheduler_jobs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user = relationship(User)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    apscheduler_job = relationship(ApschedulerJobs)
    apscheduler_job_id = Column(String, ForeignKey('apscheduler_jobs.id'), nullable=False)
    description = Column(TEXT, nullable=False)