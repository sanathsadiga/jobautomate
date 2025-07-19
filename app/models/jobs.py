
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base
from pydantic import BaseModel

class JobSearchRequest(BaseModel):
    company: str
    role: str
    location: str

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    company = Column(String, nullable=False)
    title = Column(String, nullable=False)
    location = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    apply_url = Column(String, unique=True, nullable=False)
    experience_min = Column(Integer, nullable=True)
    experience_max = Column(Integer, nullable=True)
    match = Column(String, nullable=True)
    match_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
