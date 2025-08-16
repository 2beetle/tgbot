from sqlalchemy import Table

from db.models import model_engine
from db.models.base import Base

apscheduler_jobs_table = Table('apscheduler_jobs', Base.metadata, autoload_with=model_engine)

class ApschedulerJobs(Base):
    __table__ = apscheduler_jobs_table
