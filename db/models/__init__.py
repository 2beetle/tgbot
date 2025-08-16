from sqlalchemy import create_engine

from config.config import TG_DB_PATH

model_engine = create_engine(f'sqlite:///{TG_DB_PATH}')