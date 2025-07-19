from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
import urllib.parse

# Load from env or hardcode temporarily
DB_USER = "job_user"
DB_PASS_RAW = "Sanaths1@"  # Use actual password here
DB_PASS = urllib.parse.quote_plus(DB_PASS_RAW)  # Encodes special chars correctly
DB_HOST = "localhost"
DB_NAME = "job_scraper"

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()

# Dependency for FastAPI endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
