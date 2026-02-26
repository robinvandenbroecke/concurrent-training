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

from .day_engine import (
    DayEngineParams,
    SetImpulse,
    StrengthImpulses,
    EnduranceImpulses,
    DailyImpulses,
    PerLiftState,
    DayState,
    ReadinessOutput,
    compute_strength_impulses,
    compute_endurance_impulses,
    compute_interference,
    update_day_state,
    compute_readiness,
    simulate_day_transition,
    create_initial_state,
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
    # Rep-engine exports
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
    # Day-engine exports
    "DayEngineParams",
    "SetImpulse",
    "StrengthImpulses",
    "EnduranceImpulses",
    "DailyImpulses",
    "PerLiftState",
    "DayState",
    "ReadinessOutput",
    "compute_strength_impulses",
    "compute_endurance_impulses",
    "compute_interference",
    "update_day_state",
    "compute_readiness",
    "simulate_day_transition",
    "create_initial_state",
]
