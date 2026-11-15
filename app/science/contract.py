"""Versioned request/response contract between clients and the engine.

The request mirrors the session records the web app already stores per user
(Supabase ``ct_training_sessions.payload``); unknown fields are ignored so
older and newer clients keep working. Measurements are never modified: the
engine only reads them. ``None`` always means "not measured".
"""
from __future__ import annotations

from datetime import date as _date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.science import CONTRACT_VERSION

MAX_SESSIONS = 3000
MAX_POWER_SAMPLES = 6 * 3600
DATE = r"^\d{4}-\d{2}-\d{2}$"


class _In(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _calendar_date(value):
    """The pattern accepts 2026-02-30; the engine must refuse it, not crash on it."""
    if value is not None:
        try:
            _date.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError("not an existing calendar date") from None
    return value


class VelocityMeta(_In):
    metric: Literal["mean_concentric", "mean_propulsive", "peak", "unspecified"] = "unspecified"
    deviceId: str = Field("unspecified", max_length=64)
    source: Literal["manual", "file", "ble", "unspecified"] = "unspecified"


class SetIn(_In):
    setNum: int = Field(ge=1, le=100)
    weight: float = Field(ge=0, le=1000)
    completedReps: int = Field(ge=0, le=100)
    velocities: List[Optional[float]] = Field(default_factory=list, max_length=100)
    rpe: Optional[float] = Field(None, ge=1, le=10)
    kind: Literal["work", "warmup"] = "work"
    velocityMeta: Optional[VelocityMeta] = None

    @field_validator("velocities")
    @classmethod
    def _velocity_range(cls, values):
        for v in values:
            if v is not None and not (0 < v <= 3.0):
                raise ValueError("velocity must be within (0, 3] m/s or null")
        return values

    @model_validator(mode="after")
    def _velocity_count(self):
        if len(self.velocities) > self.completedReps:
            raise ValueError("more velocity entries than completed repetitions")
        return self


class ExerciseIn(_In):
    exerciseId: Optional[str] = Field(None, max_length=64)
    lift: str = Field("other", max_length=32)
    power: bool = False                       # explosive/power exercise per the client catalogue
    loadType: Literal["weight", "bodyweight", "assistance"] = "weight"
    region: Literal["lower", "upper", "full", "unknown"] = "unknown"
    sets: List[SetIn] = Field(default_factory=list, max_length=60)


class PowerStream(_In):
    sampleSeconds: float = Field(1.0, gt=0, le=60)
    watts: List[Optional[float]] = Field(max_length=MAX_POWER_SAMPLES)

    @field_validator("watts")
    @classmethod
    def _watts_range(cls, values):
        for v in values:
            if v is not None and not (0 <= v <= 3000):
                raise ValueError("power must be within [0, 3000] W or null")
        return values


class PowerSummaryIn(_In):
    """Exact sufficient statistics of a 1 Hz power recording (see activity_files)."""
    recordedSeconds: float = Field(ge=0, le=7 * 24 * 3600)
    missingSeconds: float = Field(0, ge=0, le=7 * 24 * 3600)
    meanW: float = Field(ge=0, le=3000)
    sumSquaresW2s: float = Field(ge=0, le=3000 ** 2 * 7 * 24 * 3600)


class EnduranceIn(_In):
    sport: str = Field("other", max_length=32)
    durationMinutes: float = Field(ge=0, le=10080)
    intensityType: str = Field("other", max_length=32)
    rpe: Optional[float] = Field(None, ge=1, le=10)
    averagePowerW: Optional[float] = Field(None, ge=0, le=3000)
    power: Optional[PowerStream] = None
    powerSummary: Optional[PowerSummaryIn] = None


class SessionIn(_In):
    id: str = Field(max_length=128)
    date: str = Field(pattern=DATE)
    type: Literal["kracht", "duur"]
    durationMinutes: float = Field(0, ge=0, le=10080)
    startTime: Optional[str] = Field(None, max_length=40)   # ISO-8601 instant
    exercises: List[ExerciseIn] = Field(default_factory=list, max_length=60)
    enduranceResult: Optional[EnduranceIn] = None

    @field_validator("id", mode="before")
    @classmethod
    def _id_to_text(cls, value):
        return str(value)

    _real_date = field_validator("date")(_calendar_date)


class MaximalEffort(_In):
    durationSeconds: float = Field(gt=0, le=7200)
    powerW: float = Field(gt=0, le=3000)
    date: Optional[str] = Field(None, pattern=DATE)

    _real_date = field_validator("date")(_calendar_date)


class EnduranceProfile(_In):
    sport: str = "cycling"
    maximalEfforts: List[MaximalEffort] = Field(default_factory=list, max_length=20)
    criticalPowerW: Optional[float] = Field(None, gt=0, le=1000)     # user-entered test result
    wPrimeJ: Optional[float] = Field(None, gt=0, le=100000)
    thresholdPowerW: Optional[float] = Field(None, gt=0, le=1000)    # e.g. FTP; not CP


class EngineRequest(_In):
    contractVersion: str = CONTRACT_VERSION
    timeZone: str = Field("UTC", max_length=64)
    asOfDate: str = Field(pattern=DATE)                 # the client's local calendar date
    sessions: List[SessionIn] = Field(default_factory=list, max_length=MAX_SESSIONS)
    endurance: EnduranceProfile = Field(default_factory=EnduranceProfile)

    @field_validator("timeZone")
    @classmethod
    def _time_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("unknown IANA time zone") from None
        return value

    _real_date = field_validator("asOfDate")(_calendar_date)

    @model_validator(mode="after")
    def _one_record_per_session_id(self):
        """The same id twice with different content is a conflict the client must resolve.

        Exact repeats (a retried upload, a double import) are dropped by the
        engine and counted; they are never added up.
        """
        seen = {}
        for session in self.sessions:
            previous = seen.setdefault(session.id, session)
            if previous is not session and previous != session:
                raise ValueError(f"conflicting records share session id {session.id!r}")
        return self


class PlanSessionIn(_In):
    """One session to place. Doses are relative: work sets, or minutes at a share of the reference power."""
    label: str = Field(max_length=64)
    kind: Literal["strength_lower", "strength_upper", "strength_full", "endurance", "endurance_swim"]
    workSets: int = Field(0, ge=0, le=60)
    minutes: float = Field(0, ge=0, le=600)
    relativeIntensity: float = Field(0.7, ge=0.3, le=1.5)    # power / reference power, or a declared estimate
    key: bool = False                                        # a session whose quality matters most


class PlanRequest(EngineRequest):
    planSessions: List[PlanSessionIn] = Field(min_length=1, max_length=14)
    availableDates: List[str] = Field(min_length=1, max_length=14)
    slotHours: List[float] = Field(default_factory=lambda: [8.0, 18.0], min_length=1, max_length=3)
    priority: Literal["kracht", "duur", "balans"] = "balans"

    @field_validator("availableDates")
    @classmethod
    def _real_dates(cls, values):
        for value in values:
            if not isinstance(value, str) or len(value) != 10:
                raise ValueError("dates must be YYYY-MM-DD")
            _calendar_date(value)
        if len(set(values)) != len(values):
            raise ValueError("dates must be distinct")
        return values

    @field_validator("slotHours")
    @classmethod
    def _hours(cls, values):
        if any(not (0 <= v < 24) for v in values) or len(set(values)) != len(values):
            raise ValueError("slot hours must be distinct and within [0, 24)")
        return values
