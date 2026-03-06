"""
Sprint E3: Strength Capacity Anchor + Breakthrough System

Service for managing lift-specific capacity profiles with:
- anchor_capacity: Stable reference (updated only by confirmed breakthroughs)
- model_capacity: Operational estimate (used in planning/intensity)

Inspired by Xert-style profile updates for endurance.
"""
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
from datetime import datetime, date
from enum import Enum

from app.types import LiftType
from app.domain.performance_engine import compute_session_e1rm


class CapacityInputType(str, Enum):
    """How the initial capacity was determined."""
    ONE_RM = "1rm"
    BEST_SET = "best_set"
    UNKNOWN = "unknown"


class CapacityConfidence(str, Enum):
    """Confidence level in capacity estimate."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Conservative defaults for unknown input (kg)
LIFT_DEFAULT_CAPACITY: Dict[LiftType, float] = {
    LiftType.SQUAT: 100.0,
    LiftType.BENCH: 70.0,
    LiftType.DEADLIFT: 120.0,
    LiftType.PRESS: 45.0,
    LiftType.POWER_CLEAN: 60.0,
    LiftType.CLEAN: 60.0,
    LiftType.OTHER: 80.0,
}


@dataclass
class CapacityInitializationResult:
    """Result of capacity initialization."""
    anchor_capacity: float
    model_capacity: float
    confidence: CapacityConfidence
    input_type: CapacityInputType


@dataclass
class QualitySetResult:
    """Result of quality set evaluation."""
    is_quality: bool
    estimated_e1rm: Optional[float] = None
    quality_score: float = 0.0  # 0-1, higher is better
    reason: str = ""


@dataclass
class BreakthroughDetectionResult:
    """Result of breakthrough detection."""
    is_provisional_breakthrough: bool
    is_confirmed_breakthrough: bool
    new_anchor_capacity: Optional[float] = None
    new_model_capacity: Optional[float] = None
    signal_delta_pct: float = 0.0  # % difference from current anchor
    reason: str = ""


def compute_e1rm_from_set(load_kg: float, reps: int, rpe: Optional[float] = None) -> float:
    """
    Compute e1RM estimate from a single set.
    
    Formula without RPE: load * (1 + min(reps, 10) / 30)
    With RPE: adjusts based on RPE (lower RPE = higher estimated 1RM)
    
    Args:
        load_kg: Load in kilograms
        reps: Number of reps performed
        rpe: Optional RPE rating (6-10)
    
    Returns:
        Estimated 1RM in kg
    """
    reps = min(reps, 10)  # Cap at 10 reps for formula
    
    if rpe is None:
        # Simple formula: load * (1 + reps/30)
        return load_kg * (1 + reps / 30)
    else:
        # Adjust based on RPE: lower RPE means more reps in reserve
        # RPE 10 = max effort, RPE 6 = 4 reps in reserve
        # Adjust load to estimated 1RM load using reps in reserve
        reps_in_reserve = 10 - rpe
        adjusted_reps = reps + reps_in_reserve
        adjusted_reps = min(adjusted_reps, 12)  # Cap adjustment
        return load_kg * (1 + adjusted_reps / 30)


def determine_confidence_from_set(
    reps: int,
    rpe: Optional[float] = None
) -> CapacityConfidence:
    """
    Determine confidence level based on set parameters.
    
    Rules:
    - reps <= 5 AND RPE >= 8: HIGH
    - reps <= 8: MEDIUM  
    - otherwise: LOW
    
    Args:
        reps: Number of reps performed
        rpe: Optional RPE rating (6-10)
    
    Returns:
        Confidence level
    """
    if reps <= 5 and rpe is not None and rpe >= 8:
        return CapacityConfidence.HIGH
    elif reps <= 8:
        return CapacityConfidence.MEDIUM
    else:
        return CapacityConfidence.LOW


def initialize_lift_capacity(
    lift: LiftType,
    input_type: CapacityInputType,
    input_load_kg: Optional[float] = None,
    input_reps: Optional[int] = None,
    input_rpe: Optional[float] = None
) -> CapacityInitializationResult:
    """
    Initialize capacity profile from user input.
    
    Args:
        lift: The lift type
        input_type: How the capacity was determined
        input_load_kg: Load in kg (for 1rm or best_set)
        input_reps: Reps performed (for best_set)
        input_rpe: RPE rating 6-10 (optional for best_set)
    
    Returns:
        CapacityInitializationResult with anchor and model capacity
    
    Raises:
        ValueError: If input parameters are invalid
    """
    if input_type == CapacityInputType.ONE_RM:
        if input_load_kg is None:
            raise ValueError("input_load_kg required for 1rm input_type")
        
        anchor = input_load_kg
        model = input_load_kg
        confidence = CapacityConfidence.HIGH
        
    elif input_type == CapacityInputType.BEST_SET:
        if input_load_kg is None or input_reps is None:
            raise ValueError("input_load_kg and input_reps required for best_set input_type")
        
        # Compute e1RM from set
        e1rm = compute_e1rm_from_set(input_load_kg, input_reps, input_rpe)
        
        anchor = e1rm
        model = e1rm
        confidence = determine_confidence_from_set(input_reps, input_rpe)
        
    elif input_type == CapacityInputType.UNKNOWN:
        # Use conservative defaults
        default = LIFT_DEFAULT_CAPACITY.get(lift, 80.0)
        anchor = default
        model = default
        confidence = CapacityConfidence.LOW
        
    else:
        raise ValueError(f"Unknown input_type: {input_type}")
    
    return CapacityInitializationResult(
        anchor_capacity=anchor,
        model_capacity=model,
        confidence=confidence,
        input_type=input_type
    )


def is_quality_strength_set(
    lift: LiftType,
    load_kg: float,
    reps: int,
    rpe: Optional[float],
    velocity_loss: Optional[float],
    anchor_capacity: float,
    min_relative_load: float = 0.70,  # At least 70% of capacity
    max_reps: int = 12,  # More than 12 reps not reliable for strength
    max_velocity_loss: float = 0.30,  # VL > 30% indicates fatigue
) -> QualitySetResult:
    """
    Determine if a set is "quality" for capacity estimation.
    
    Quality criteria:
    1. Load is at least min_relative_load % of anchor capacity
    2. Reps <= max_reps (high rep sets not reliable)
    3. Velocity loss <= max_velocity_loss (if available)
    4. RPE >= 7 (if available, indicates sufficient effort)
    
    Args:
        lift: The lift type
        load_kg: Load in kg
        reps: Reps performed
        rpe: Optional RPE (6-10)
        velocity_loss: Optional velocity loss % (0-1)
        anchor_capacity: Current anchor capacity
        min_relative_load: Minimum % of capacity to qualify
        max_reps: Maximum reps to qualify
        max_velocity_loss: Maximum velocity loss to qualify
    
    Returns:
        QualitySetResult with quality determination and estimated e1RM
    """
    if anchor_capacity <= 0:
        return QualitySetResult(
            is_quality=False,
            reason="Invalid anchor capacity"
        )
    
    relative_load = load_kg / anchor_capacity
    
    # Check load threshold
    if relative_load < min_relative_load:
        return QualitySetResult(
            is_quality=False,
            reason=f"Load too light ({relative_load:.1%} < {min_relative_load:.0%})"
        )
    
    # Check rep count
    if reps > max_reps:
        return QualitySetResult(
            is_quality=False,
            reason=f"Too many reps ({reps} > {max_reps})"
        )
    
    # Check velocity loss if available
    if velocity_loss is not None and velocity_loss > max_velocity_loss:
        return QualitySetResult(
            is_quality=False,
            reason=f"Velocity loss too high ({velocity_loss:.1%} > {max_velocity_loss:.0%})"
        )
    
    # Check RPE if available (should be sufficient effort)
    if rpe is not None and rpe < 7:
        return QualitySetResult(
            is_quality=False,
            reason=f"RPE too low ({rpe} < 7)"
        )
    
    # Compute quality score (0-1)
    quality_score = min(1.0, relative_load)
    if velocity_loss is not None:
        quality_score *= (1 - velocity_loss)
    if rpe is not None:
        quality_score *= (rpe - 6) / 4  # Normalize RPE 7-10 to 0.25-1.0
    
    # Compute estimated e1RM from this set
    estimated_e1rm = compute_e1rm_from_set(load_kg, reps, rpe)
    
    return QualitySetResult(
        is_quality=True,
        estimated_e1rm=estimated_e1rm,
        quality_score=quality_score,
        reason="Quality set"
    )


def detect_breakthrough(
    current_anchor: float,
    current_model: float,
    signal_e1rm: float,
    provisional_count: int = 0,
    confirmation_threshold_pct: float = 2.5,  # Need 2.5% improvement for provisional
    confirmation_required_count: int = 2,  # Need 2 provisional signals for confirmation
    model_adjustment_rate: float = 0.3,  # Model moves 30% toward signal
) -> BreakthroughDetectionResult:
    """
    Detect breakthroughs from performance signals.
    
    Breakthrough logic:
    1. Provisional breakthrough: signal exceeds anchor by threshold_pct
    2. Confirmed breakthrough: provisional_count + 1 >= confirmation_required_count
    
    Args:
        current_anchor: Current anchor capacity
        current_model: Current model capacity
        signal_e1rm: New performance signal (e1RM estimate)
        provisional_count: Current count of provisional breakthroughs
        confirmation_threshold_pct: % improvement needed for provisional
        confirmation_required_count: Provisional signals needed for confirmation
        model_adjustment_rate: How fast model adjusts to signals
    
    Returns:
        BreakthroughDetectionResult
    """
    if current_anchor <= 0:
        return BreakthroughDetectionResult(
            is_provisional_breakthrough=False,
            is_confirmed_breakthrough=False,
            reason="Invalid anchor capacity"
        )
    
    # Calculate delta from anchor
    delta_pct = (signal_e1rm - current_anchor) / current_anchor * 100
    
    # Check for provisional breakthrough
    is_provisional = delta_pct >= confirmation_threshold_pct
    
    if not is_provisional:
        # No breakthrough, but model may still drift toward signal
        new_model = current_model + (signal_e1rm - current_model) * model_adjustment_rate
        
        return BreakthroughDetectionResult(
            is_provisional_breakthrough=False,
            is_confirmed_breakthrough=False,
            new_model_capacity=new_model,
            signal_delta_pct=delta_pct,
            reason=f"Signal within normal range ({delta_pct:+.1f}%)"
        )
    
    # Provisional breakthrough detected
    new_provisional_count = provisional_count + 1
    
    # Check for confirmed breakthrough
    is_confirmed = new_provisional_count >= confirmation_required_count
    
    if is_confirmed:
        # Confirm breakthrough: update anchor to signal
        new_anchor = signal_e1rm
        new_model = signal_e1rm  # Reset model to confirmed value
        
        return BreakthroughDetectionResult(
            is_provisional_breakthrough=True,
            is_confirmed_breakthrough=True,
            new_anchor_capacity=new_anchor,
            new_model_capacity=new_model,
            signal_delta_pct=delta_pct,
            reason=f"Confirmed breakthrough: {delta_pct:+.1f}% improvement"
        )
    else:
        # Provisional only: model drifts toward signal, anchor stays
        new_model = current_model + (signal_e1rm - current_model) * model_adjustment_rate
        
        return BreakthroughDetectionResult(
            is_provisional_breakthrough=True,
            is_confirmed_breakthrough=False,
            new_model_capacity=new_model,
            signal_delta_pct=delta_pct,
            reason=f"Provisional breakthrough ({new_provisional_count}/{confirmation_required_count}): {delta_pct:+.1f}%"
        )


def get_default_capacity(lift: LiftType) -> float:
    """Get default capacity for a lift type."""
    return LIFT_DEFAULT_CAPACITY.get(lift, 80.0)
