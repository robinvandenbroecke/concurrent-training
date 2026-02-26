"""Shared type definitions - single source of truth for enums"""
from enum import Enum


class LiftType(str, Enum):
    """Weightlifting movement types"""
    SQUAT = "squat"
    BENCH = "bench"
    DEADLIFT = "deadlift"
    PRESS = "press"
    POWER_CLEAN = "power_clean"


class EnduranceSport(str, Enum):
    """Endurance sport types"""
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"


class EnduranceIntensity(str, Enum):
    """Endurance training intensity zones"""
    Z2 = "z2"  # Zone 2, aerobic, builds R_mito
    HIIT = "hiit"  # High intensity, adds E_fat and interference
