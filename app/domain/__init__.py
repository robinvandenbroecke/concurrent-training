"""Domain model package"""

from app.types import LiftType, EnduranceSport, EnduranceIntensity

from .model import (
    ConcurrentTrainingModel,
    Autoregulator,
    LiftProfile,
    DayLevelState,
    RepLevelState,
    SystemParameters,
)

from .rep_engine import (
    LiftVelocityProfile,
    RepEngineParams,
    RepInput,
    SetInput,
    SessionInput,
    RepOutput,
    SetOutput,
    SessionOutput,
    simulate_strength_session,
    LimitingFactor,
    RepState,
)

__all__ = [
    # Original model exports
    "ConcurrentTrainingModel",
    "Autoregulator",
    "LiftProfile",
    "LiftType",
    "EnduranceSport",
    "EnduranceIntensity",
    "DayLevelState",
    "RepLevelState",
    "SystemParameters",
    # New rep-engine exports
    "LiftVelocityProfile",
    "RepEngineParams",
    "RepInput",
    "SetInput",
    "SessionInput",
    "RepOutput",
    "SetOutput",
    "SessionOutput",
    "simulate_strength_session",
    "LimitingFactor",
    "RepState",
]
