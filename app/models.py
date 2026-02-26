"""Example model - replace with your own"""
from sqlalchemy import Column, String, Text

from app.database import BaseModel


class TrainingSession(BaseModel):
    """Training session model"""
    __tablename__ = "training_sessions"
    
    name = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(50), default="pending")
