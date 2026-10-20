"""Database models."""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.types import EnduranceSport, LiftType


class Athlete(Base):
    __tablename__ = "athletes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    # Ownership foundation for a later account/authentication layer. Existing
    # single-tenant installations are migrated to the local namespace.
    owner_subject = Column(
        String(255), nullable=False, default="local", server_default="local", index=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

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
    content_hash = Column(String(64), nullable=False)
    tonnage = Column(Float, default=0.0)
    avg_intensity = Column(Float, default=0.0)
    raw_data = Column(JSON)
    rep_level_log = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("athlete_id", "content_hash", name="uq_strength_session_hash"),
    )

    athlete = relationship("Athlete", back_populates="strength_sessions")


class EnduranceSession(Base):
    __tablename__ = "endurance_sessions"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    sport = Column(SQLEnum(EnduranceSport, name="endurance_sport"), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Float, nullable=False)
    intensity_type = Column(String(20))
    content_hash = Column(String(64), nullable=False)
    u_E_Z2 = Column(Float, default=0.0)
    u_E_HIIT = Column(Float, default=0.0)
    raw_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("athlete_id", "content_hash", name="uq_endurance_session_hash"),
    )

    athlete = relationship("Athlete", back_populates="endurance_sessions")


class LiftProfile(Base):
    __tablename__ = "lift_profiles"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    lift = Column(SQLEnum(LiftType, name="lift_type"), nullable=False)
    a = Column(Float, nullable=False, default=0.5)
    b = Column(Float, nullable=False, default=0.003)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("athlete_id", "lift", name="uq_athlete_lift"),
    )

    athlete = relationship("Athlete", back_populates="lift_profiles")


class DayState(Base):
    """System-level day states."""

    __tablename__ = "day_states"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    date = Column(String(10), nullable=False)
    D_sys = Column(Float, default=0.0)
    R_mito = Column(Float, default=0.0)
    E_fat = Column(Float, default=0.0)
    T_legs = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("athlete_id", "date", name="uq_athlete_date"),
    )

    athlete = relationship("Athlete", back_populates="day_states")


class LiftDayState(Base):
    """Per-lift day states."""

    __tablename__ = "lift_day_states"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    lift = Column(SQLEnum(LiftType, name="lift_type"), nullable=False)
    date = Column(String(10), nullable=False)
    D_l = Column(Float, default=0.0)
    F_l = Column(Float, default=1.0)
    C_l = Column(Float, default=100.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("athlete_id", "lift", "date", name="uq_athlete_lift_date"),
    )

    athlete = relationship("Athlete", back_populates="lift_day_states")


class SystemParameters(Base):
    """Configurable parameters per athlete."""

    __tablename__ = "system_parameters"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False, unique=True)
    params = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class WorkoutPlan(Base):
    """Generated workout plans.

    ``slot`` permits multiple planned sessions on one calendar day while still
    making repeated generation for the same logical slot idempotent.
    """

    __tablename__ = "workout_plans"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    date = Column(String(10), nullable=False)
    slot = Column(
        String(50), nullable=False, default="primary", server_default="primary"
    )
    mode = Column(String(20), nullable=False)
    plan_json = Column(JSON, nullable=False)
    readiness_snapshot = Column(JSON, default=dict)
    is_adapted = Column(Boolean, default=False)
    original_plan_id = Column(Integer, ForeignKey("workout_plans.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "athlete_id", "date", "slot", name="uq_athlete_workout_date_slot"
        ),
        Index("ix_workout_plans_athlete_date", "athlete_id", "date"),
    )

    athlete = relationship("Athlete")


class PerformanceSnapshot(Base):
    """Performance snapshots for trend analysis."""

    __tablename__ = "performance_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    snapshot_date = Column(String(10), nullable=False)
    days_analyzed = Column(Integer, default=28)
    metrics_json = Column(JSON, nullable=False)
    overall_signal = Column(String(30), default="maintain")
    suggest_deload = Column(Boolean, default=False)
    volume_adjustment_pct = Column(Float, default=0.0)
    intensity_adjustment_pct = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("athlete_id", "snapshot_date", name="uq_athlete_perf_date"),
    )

    athlete = relationship("Athlete")


class Goal(Base):
    """Training goals for event-driven periodization.

    Historical inactive goals are unrestricted. A partial unique index enforces
    at most one active goal per athlete.
    """

    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(String(50), nullable=False, unique=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    goal_type = Column(String(30), nullable=False)
    target_date = Column(String(10), nullable=False)
    priority = Column(String(20), default="balanced")
    goal_json = Column(JSON, nullable=False)
    active = Column(Boolean, default=True, nullable=False, server_default=text("1"))
    goal_state_json = Column(JSON, nullable=True)
    macrocycle_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index(
            "uq_goals_one_active_per_athlete",
            "athlete_id",
            unique=True,
            postgresql_where=text("active IS TRUE"),
            sqlite_where=text("active = 1"),
        ),
        Index("ix_goals_athlete_created_at", "athlete_id", "created_at"),
    )

    athlete = relationship("Athlete")


class StravaConnection(Base):
    """Strava OAuth connection for an athlete."""

    __tablename__ = "strava_connections"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False, unique=True)
    strava_athlete_id = Column(String(50), nullable=False)
    strava_athlete_name = Column(String(255), nullable=True)
    access_token = Column(String(255), nullable=False)
    refresh_token = Column(String(255), nullable=False)
    expires_at = Column(Integer, nullable=False)
    accepted_scopes = Column(String(255), nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_error = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    athlete = relationship("Athlete")


class LiftCapacityProfile(Base):
    """Stable anchor and operational capacity for a lift."""

    __tablename__ = "lift_capacity_profiles"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    lift = Column(SQLEnum(LiftType, name="lift_type"), nullable=False)
    input_type = Column(String(20), nullable=False)
    input_load_kg = Column(Float, nullable=True)
    input_reps = Column(Integer, nullable=True)
    input_rpe = Column(Float, nullable=True)
    anchor_capacity = Column(Float, nullable=False)
    model_capacity = Column(Float, nullable=False)
    confidence = Column(String(20), nullable=False, default="low")
    provisional_breakthrough_count = Column(Integer, default=0)
    last_provisional_at = Column(DateTime(timezone=True), nullable=True)
    last_confirmed_breakthrough_at = Column(DateTime(timezone=True), nullable=True)
    last_signal_value = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "athlete_id", "lift", name="uq_athlete_lift_capacity"
        ),
    )

    athlete = relationship("Athlete")
