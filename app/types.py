"""Shared type definitions - single source of truth for enums

This module provides the canonical enum definitions used across the entire codebase.
All other modules should import from here to ensure type identity and prevent bugs.
"""
from enum import Enum


class LiftType(str, Enum):
    """Weightlifting movement types - canonical enum for all layers"""
    SQUAT = "squat"
    BENCH = "bench"
    DEADLIFT = "deadlift"
    PRESS = "press"
    POWER_CLEAN = "power_clean"
    CLEAN = "clean"  # Alias for compatibility
    OTHER = "other"


class EnduranceSport(str, Enum):
    """Endurance sport types - canonical enum for all layers"""
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"
    OTHER = "other"


class EnduranceIntensity(str, Enum):
    """Endurance training intensity zones - canonical enum for all layers"""
    Z2 = "z2"  # Zone 2, aerobic, builds R_mito
    HIIT = "hiit"  # High intensity, adds E_fat and interference
    TEMPO = "tempo"
    THRESHOLD = "threshold"
    LONG = "long"
    EASY = "easy"
    OTHER = "other"
