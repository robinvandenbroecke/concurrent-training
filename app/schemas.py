"""Pydantic schemas for API"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime

from app.types import LiftType, EnduranceSport, EnduranceIntensity


# Athlete schemas
class AthleteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class AthleteResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# Strength session schemas
class RepData(BaseModel):
    """Single rep data from VBT"""
    weight: float
    velocity: float
    rep_num: int
    rest_before: float = 0.0  # seconds


class SetData(BaseModel):
    """Single set data"""
    weight: float
    target_reps: int
    reps: List[RepData]


class StrengthSessionCreate(BaseModel):
    athlete_id: int
    lift: LiftType
    start_time: datetime
    sets: List[SetData]


class StrengthSessionResponse(BaseModel):
    id: int
    athlete_id: int
    lift: LiftType
    start_time: datetime
    end_time: Optional[datetime]
    tonnage: float
    avg_intensity: float
    
    class Config:
        from_attributes = True


# Endurance session schemas
class EnduranceSessionCreate(BaseModel):
    athlete_id: int
    sport: EnduranceSport
    start_time: datetime
    duration_minutes: float = Field(..., gt=0)
    intensity_type: str = Field(..., pattern="^(z2|hiit|mixed)$")


class EnduranceSessionResponse(BaseModel):
    id: int
    athlete_id: int
    sport: EnduranceSport
    start_time: datetime
    duration_minutes: float
    intensity_type: str
    u_E_Z2: float
    u_E_HIIT: float
    
    class Config:
        from_attributes = True


# Autoregulation schemas
class AutoregulateRequest(BaseModel):
    athlete_id: int
    lift: LiftType
    current_weight: float
    target_v_low: float = 0.35  # m/s
    target_v_high: float = 0.45  # m/s
    vl_max: float = 20.0  # %
    planned_reps: int = 5
    current_reps_done: int = 0

    # Last few rep observations from the CURRENT set (most recent last).
    # Used to reconstruct within-set fatigue without requiring server-side rep state.
    recent_v_obs: Optional[List[float]] = None  # m/s
    recent_rest_before: Optional[List[float]] = None  # seconds; same length as recent_v_obs


class AutoregulateResponse(BaseModel):
    continue_set: bool
    load_change: float  # Percentage
    rest_suggestion: Optional[str]
    exercise_switch: Optional[str]
    predicted_velocity: float
    current_vl: float
    messages: List[str]


# Readiness schemas
class ReadinessResponse(BaseModel):
    athlete_id: int
    date: str
    overall: float
    per_lift: Dict[str, float]
    endurance: float
    explanations: List[str]


# Trend schemas
class LiftTrendPoint(BaseModel):
    date: str
    D_l: float
    F_l: float
    C_l: float
    readiness: float


class LiftTrendResponse(BaseModel):
    athlete_id: int
    lift: LiftType
    days: int
    data: List[LiftTrendPoint]


class EnduranceTrendPoint(BaseModel):
    date: str
    R_mito: float
    E_fat: float
    readiness: float


class EnduranceTrendResponse(BaseModel):
    athlete_id: int
    days: int
    data: List[EnduranceTrendPoint]


# Error schema
class ErrorResponse(BaseModel):
    detail: str
