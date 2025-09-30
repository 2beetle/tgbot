from sqlalchemy import Table, Column, String, DateTime, LargeBinary
from sqlalchemy.dialects.sqlite import VARCHAR
import logging

from db.models import model_engine
from db.models.base import Base

logger = logging.getLogger(__name__)

# 动态检查表是否存在，如果不存在则创建定义
from sqlalchemy import inspect
inspector = inspect(model_engine)

def validate_apscheduler_table_structure():
    """验证apscheduler_jobs表结构是否与APScheduler 3.11.0匹配"""
    try:
        columns = inspector.get_columns('apscheduler_jobs')
        column_names = {col['name'] for col in columns}
        column_types = {col['name']: type(col['type']).__name__ for col in columns}

        # APScheduler 3.11.0 期望的表结构
        expected_columns = {'id', 'next_run_time', 'job_state'}
        expected_types = {
            'id': 'VARCHAR',
            'next_run_time': 'DATETIME',
            'job_state': 'LargeBinary'  # SQLite中BLOB对应LargeBinary
        }

        # 检查列名
        if column_names != expected_columns:
            logger.warning(f"apscheduler_jobs表列名不匹配。期望: {expected_columns}, 实际: {column_names}")
            return False

        # 检查列类型（宽松匹配）
        for col_name, expected_type in expected_types.items():
            actual_type = column_types[col_name]
            if expected_type not in actual_type and actual_type not in expected_type:
                logger.warning(f"apscheduler_jobs表列'{col_name}'类型不匹配。期望: {expected_type}, 实际: {actual_type}")
                return False

        return True

    except Exception as e:
        logger.error(f"验证apscheduler_jobs表结构时出错: {e}")
        return False

if inspector.has_table('apscheduler_jobs'):
    # 表已存在，先验证结构
    if validate_apscheduler_table_structure():
        # 结构匹配，直接加载
        apscheduler_jobs_table = Table('apscheduler_jobs', Base.metadata, autoload_with=model_engine)
        logger.info("成功加载现有的apscheduler_jobs表")
    else:
        # 结构不匹配，记录警告但仍加载（避免启动失败）
        logger.warning("apscheduler_jobs表结构与APScheduler期望不匹配，可能导致问题")
        apscheduler_jobs_table = Table('apscheduler_jobs', Base.metadata, autoload_with=model_engine)
else:
    # 表不存在，创建与APScheduler 3.11.0完全匹配的表定义
    # APScheduler官方表结构：id(VARCHAR(191)), next_run_time(DATETIME), job_state(BLOB)
    apscheduler_jobs_table = Table(
        'apscheduler_jobs',
        Base.metadata,
        Column('id', VARCHAR(191), primary_key=True, nullable=False),
        Column('next_run_time', DateTime, nullable=True),
        Column('job_state', LargeBinary, nullable=False)
    )
    logger.info("创建了apscheduler_jobs表定义，等待APScheduler自动创建表")

class ApschedulerJobs(Base):
    __table__ = apscheduler_jobs_table
