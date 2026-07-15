"""Pydantic schemas for the API."""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Re-export canonical enums for backwards-compatible imports.
from app.types import EnduranceIntensity, EnduranceSport, LiftType


class AthleteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class AthleteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class RepData(BaseModel):
    """Single rep observation. Velocity may be absent for non-VBT logging."""
    weight: float = Field(..., gt=0)
    velocity: Optional[float] = Field(None, gt=0, le=3.0)
    rep_num: int = Field(..., ge=1)
    rest_before: float = Field(0.0, ge=0, le=3600)


class SetData(BaseModel):
    weight: float = Field(..., gt=0)
    target_reps: int = Field(..., ge=1, le=100)
    reps: List[RepData]
    rest_before_sec: Optional[float] = Field(None, ge=0, le=3600)
    set_end_rpe: Optional[float] = Field(None, ge=1, le=10)


class StrengthSessionCreate(BaseModel):
    athlete_id: int = Field(..., gt=0)
    lift: LiftType
    start_time: datetime
    end_time: Optional[datetime] = None
    # Kept constructible with an empty list for compatibility and dry-run tools.
    # Runtime ingestion rejects sessions without performed sets.
    sets: List[SetData]

    @model_validator(mode="after")
    def validate_times(self):
        if self.end_time and self.end_time < self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class StrengthExerciseData(BaseModel):
    lift: LiftType
    sets: List[SetData] = Field(..., min_length=1)


class StrengthWorkoutCreate(BaseModel):
    """A complete multi-lift workout in performed order."""
    athlete_id: int = Field(..., gt=0)
    start_time: datetime
    end_time: Optional[datetime] = None
    exercises: List[StrengthExerciseData] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_times(self):
        if self.end_time and self.end_time < self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class StrengthSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    athlete_id: int
    lift: LiftType
    start_time: datetime
    end_time: Optional[datetime]
    tonnage: float
    avg_intensity: float


class PowerPoint(BaseModel):
    power: float = Field(..., gt=0, le=3000)
    timestamp: Optional[float] = None


class EnduranceSessionCreate(BaseModel):
    athlete_id: int = Field(..., gt=0)
    sport: EnduranceSport
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: float = Field(..., gt=0, le=1440)
    intensity_type: str = Field("z2", pattern="^(z2|hiit|mixed)$")
    power_data: Optional[List[PowerPoint]] = None
    average_power_w: Optional[float] = Field(None, gt=0, le=3000)
    normalized_power_w: Optional[float] = Field(None, gt=0, le=3000)
    threshold_power_w: Optional[float] = Field(None, gt=0, le=3000)
    average_heartrate: Optional[float] = Field(None, gt=20, le=260)
    rpe: Optional[float] = Field(None, ge=1, le=10)

    @model_validator(mode="after")
    def validate_times(self):
        if self.end_time and self.end_time < self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class EnduranceSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    athlete_id: int
    sport: EnduranceSport
    start_time: datetime
    duration_minutes: float
    intensity_type: str
    u_E_Z2: float
    u_E_HIIT: float


class AutoregulateRequest(BaseModel):
    athlete_id: int = Field(..., gt=0)
    lift: LiftType
    current_weight: float = Field(..., gt=0)
    target_v_low: float = Field(0.35, gt=0, le=3.0)
    target_v_high: float = Field(0.45, gt=0, le=3.0)
    vl_max: float = Field(20.0, ge=0, le=100)
    planned_reps: int = Field(5, ge=1, le=100)
    current_reps_done: int = Field(0, ge=0, le=100)
    recent_v_obs: Optional[List[float]] = None
    recent_rest_before: Optional[List[float]] = None

    @model_validator(mode="after")
    def validate_velocity_band(self):
        if self.target_v_high < self.target_v_low:
            raise ValueError("target_v_high must be >= target_v_low")
        return self


class AutoregulateResponse(BaseModel):
    continue_set: bool
    load_change: float
    rest_suggestion: Optional[str]
    exercise_switch: Optional[str]
    predicted_velocity: float
    current_vl: float
    messages: List[str]


class ReadinessResponse(BaseModel):
    athlete_id: int
    date: str
    overall: float
    per_lift: Dict[str, float]
    endurance: float
    explanations: List[str]


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


class ErrorResponse(BaseModel):
    detail: str
