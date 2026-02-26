"""Database models"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, 
    JSON, Enum as SQLEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


class LiftType(str, enum.Enum):
    SQUAT = "squat"
    BENCH = "bench"
    DEADLIFT = "deadlift"
    PRESS = "press"
    POWER_CLEAN = "power_clean"


class EnduranceSport(str, enum.Enum):
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"


class Athlete(Base):
    __tablename__ = "athletes"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    strength_sessions = relationship("StrengthSession", back_populates="athlete")
    endurance_sessions = relationship("EnduranceSession", back_populates="athlete")
    lift_profiles = relationship("LiftProfile", back_populates="athlete")
    day_states = relationship("DayState", back_populates="athlete")
    lift_day_states = relationship("LiftDayState", back_populates="athlete")


class StrengthSession(Base):
    __tablename__ = "strength_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    lift = Column(SQLEnum(LiftType), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True))
    
    # Computed fields
    tonnage = Column(Float, default=0.0)
    avg_intensity = Column(Float, default=0.0)
    
    # Raw data
    raw_data = Column(JSON)
    rep_level_log = Column(JSON)  # List of rep states for debugging
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    athlete = relationship("Athlete", back_populates="strength_sessions")


class EnduranceSession(Base):
    __tablename__ = "endurance_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    sport = Column(SQLEnum(EnduranceSport), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Float, nullable=False)
    intensity_type = Column(String(20))  # z2, hiit, mixed
    
    # Computed fields
    u_E_Z2 = Column(Float, default=0.0)  # Z2 component
    u_E_HIIT = Column(Float, default=0.0)  # HIIT component
    
    # Raw data
    raw_data = Column(JSON)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    athlete = relationship("Athlete", back_populates="endurance_sessions")


class LiftProfile(Base):
    __tablename__ = "lift_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    lift = Column(SQLEnum(LiftType), nullable=False)
    
    # VBT profile: v = a - b*w
    a = Column(Float, nullable=False, default=0.5)  # velocity intercept
    b = Column(Float, nullable=False, default=0.003)  # slope
    
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('athlete_id', 'lift', name='uq_athlete_lift'),
    )
    
    athlete = relationship("Athlete", back_populates="lift_profiles")


class DayState(Base):
    """System-level day states"""
    __tablename__ = "day_states"
    
    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    
    # System states
    D_sys = Column(Float, default=0.0)  # System fatigue
    R_mito = Column(Float, default=0.0)  # Recovery capacity
    E_fat = Column(Float, default=0.0)  # Endurance fatigue
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('athlete_id', 'date', name='uq_athlete_date'),
    )
    
    athlete = relationship("Athlete", back_populates="day_states")


class LiftDayState(Base):
    """Per-lift day states"""
    __tablename__ = "lift_day_states"
    
    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    lift = Column(SQLEnum(LiftType), nullable=False)
    date = Column(String(10), nullable=False)
    
    D_l = Column(Float, default=0.0)  # Per-lift fatigue
    F_l = Column(Float, default=1.0)  # Fitness/adaptation
    C_l = Column(Float, default=100.0)  # Capacity (e1RM-like)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('athlete_id', 'lift', 'date', name='uq_athlete_lift_date'),
    )
    
    athlete = relationship("Athlete", back_populates="lift_day_states")


class SystemParameters(Base):
    """Configurable parameters per athlete"""
    __tablename__ = "system_parameters"
    
    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False, unique=True)
    
    # Stored as JSON for flexibility
    params = Column(JSON, default=dict)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
