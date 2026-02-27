"""Database models"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, 
    JSON, Enum as SQLEnum, UniqueConstraint, Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.types import LiftType, EnduranceSport


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
    lift = Column(SQLEnum(LiftType, name="lift_type"), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True))

    # HOTFIX: Idempotency - content hash for duplicate detection
    content_hash = Column(String(64), nullable=True)

    # Computed fields
    tonnage = Column(Float, default=0.0)
    avg_intensity = Column(Float, default=0.0)

    # Raw data
    raw_data = Column(JSON)
    rep_level_log = Column(JSON)  # List of rep states for debugging

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('athlete_id', 'content_hash', name='uq_strength_session_hash'),
    )

    athlete = relationship("Athlete", back_populates="strength_sessions")


class EnduranceSession(Base):
    __tablename__ = "endurance_sessions"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    sport = Column(SQLEnum(EnduranceSport, name="endurance_sport"), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Float, nullable=False)
    intensity_type = Column(String(20))  # z2, hiit, mixed

    # HOTFIX: Idempotency - content hash for duplicate detection
    content_hash = Column(String(64), nullable=True)

    # Computed fields
    u_E_Z2 = Column(Float, default=0.0)  # Z2 component
    u_E_HIIT = Column(Float, default=0.0)  # HIIT component

    # Raw data
    raw_data = Column(JSON)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('athlete_id', 'content_hash', name='uq_endurance_session_hash'),
    )

    athlete = relationship("Athlete", back_populates="endurance_sessions")


class LiftProfile(Base):
    __tablename__ = "lift_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    lift = Column(SQLEnum(LiftType, name="lift_type"), nullable=False)
    
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
    T_legs = Column(Float, default=0.0, nullable=False)  # Structural/connective tissue fatigue
    
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
    lift = Column(SQLEnum(LiftType, name="lift_type"), nullable=False)
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


class WorkoutPlan(Base):
    """Generated workout plans"""
    __tablename__ = "workout_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    mode = Column(String(20), nullable=False)  # strength/endurance/concurrent
    
    # Plan stored as JSON
    plan_json = Column(JSON, nullable=False)
    
    # Readiness snapshot at generation time
    readiness_snapshot = Column(JSON, default=dict)
    
    # Status
    is_adapted = Column(Boolean, default=False)
    original_plan_id = Column(Integer, ForeignKey("workout_plans.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('athlete_id', 'date', name='uq_athlete_workout_date'),
    )
    
    athlete = relationship("Athlete")


class PerformanceSnapshot(Base):
    """Performance snapshots for trend analysis"""
    __tablename__ = "performance_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    snapshot_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    days_analyzed = Column(Integer, default=28)
    
    # Complete performance report as JSON
    metrics_json = Column(JSON, nullable=False)
    
    # Summary fields for quick queries
    overall_signal = Column(String(30), default="maintain")
    suggest_deload = Column(Boolean, default=False)
    volume_adjustment_pct = Column(Float, default=0.0)
    intensity_adjustment_pct = Column(Float, default=0.0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('athlete_id', 'snapshot_date', name='uq_athlete_perf_date'),
    )
    
    athlete = relationship("Athlete")


class Goal(Base):
    """Training goals for event-driven periodization"""
    __tablename__ = "goals"
    
    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(String(50), nullable=False, unique=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    
    # Goal configuration
    goal_type = Column(String(30), nullable=False)  # strength_peak, endurance_event, concurrent_event
    target_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    priority = Column(String(20), default="balanced")  # strength, endurance, balanced
    
    # Complete goal config as JSON
    goal_json = Column(JSON, nullable=False)
    
    # Active status
    active = Column(Boolean, default=True)
    
    # Goal state (current phase, etc.)
    goal_state_json = Column(JSON, nullable=True)
    
    # Macrocycle context (computed from goal)
    macrocycle_json = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('athlete_id', 'active', name='uq_athlete_active_goal'),
    )
    
    athlete = relationship("Athlete")
