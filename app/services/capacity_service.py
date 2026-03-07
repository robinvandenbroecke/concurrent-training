"""
Sprint E3 Refined: Strength Capacity Anchor + Breakthrough System v2

Refined implementation with:
- Lift-specific quality criteria (different for power_clean)
- Confidence-dependent breakthrough thresholds
- Partial anchor updates (alpha blending)
- Model capacity tracking with signal smoothing
- 21-day window for provisional breakthroughs
- No aggressive downward anchor updates

Inspired by Xert-style profile updates for endurance.
"""
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple, Union
from datetime import datetime, date, timedelta
from enum import Enum

from app.types import LiftType


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


class SignalType(str, Enum):
    """Type of performance signal."""
    E1RM = "e1rm"
    VELOCITY = "velocity"
    CLEAN_LOAD = "clean_load"


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
class PerformanceSignal:
    """Extracted performance signal from a set or session."""
    signal_value: float
    signal_type: SignalType
    quality_passed: bool
    quality_score: float  # 0-1
    reason: str = ""


@dataclass
class QualitySetResult:
    """Result of quality set evaluation."""
    is_quality: bool
    signal: Optional[PerformanceSignal] = None
    quality_score: float = 0.0  # 0-1
    reason: str = ""
    
    # Backwards compatibility property
    @property
    def estimated_e1rm(self) -> Optional[float]:
        """Backwards compatibility alias for signal.signal_value."""
        if self.signal is not None:
            return self.signal.signal_value
        return None


@dataclass
class BreakthroughDetectionResult:
    """Result of breakthrough detection."""
    is_provisional_breakthrough: bool
    is_confirmed_breakthrough: bool
    new_anchor_capacity: Optional[float] = None
    new_model_capacity: Optional[float] = None
    signal_delta_pct: float = 0.0
    reason: str = ""


# Configuration constants
PROVISIONAL_WINDOW_DAYS = 21  # Window for counting provisional breakthroughs
STRONG_SIGNAL_THRESHOLD_PCT = 4.0  # % above anchor for immediate confirmation
ANCHOR_UPDATE_ALPHA = 0.5  # Partial update factor (0.5 = halfway to signal)
MODEL_CAPACITY_BLEND = 0.3  # Weight for recent signal in model capacity
CONFIRMED_PROVISIONAL_COUNT = 2  # Provisional signals needed for confirmation

# Sprint E2.1: Lift-specific default capacities (kg)
# Used as final fallback when no profile, day-state, or performance data exists
LIFT_SPECIFIC_DEFAULTS: Dict[LiftType, float] = {
    LiftType.SQUAT: 140.0,
    LiftType.BENCH: 100.0,
    LiftType.DEADLIFT: 180.0,
    LiftType.PRESS: 70.0,
    LiftType.POWER_CLEAN: 95.0,
    LiftType.CLEAN: 95.0,
    LiftType.OTHER: 100.0,
}


def normalize_lift_type(lift: Union[LiftType, str]) -> LiftType:
    """Normalize lift type string or enum to canonical LiftType."""
    if isinstance(lift, LiftType):
        return lift
    
    lift_lower = str(lift).lower().strip()
    
    # Handle aliases
    aliases = {
        'clean': LiftType.CLEAN,
        'power_clean': LiftType.POWER_CLEAN,
        'power clean': LiftType.POWER_CLEAN,
        'squat': LiftType.SQUAT,
        'bench': LiftType.BENCH,
        'bench_press': LiftType.BENCH,
        'bench press': LiftType.BENCH,
        'deadlift': LiftType.DEADLIFT,
        'press': LiftType.PRESS,
        'overhead_press': LiftType.PRESS,
        'overhead press': LiftType.PRESS,
        'shoulder_press': LiftType.PRESS,
        'shoulder press': LiftType.PRESS,
    }
    
    if lift_lower in aliases:
        return aliases[lift_lower]
    
    # Try direct enum lookup
    try:
        return LiftType(lift_lower)
    except ValueError:
        return LiftType.OTHER


def _extract_capacity_from_performance_snapshot(
    snapshot_metrics: Dict,
    lift: LiftType,
) -> Optional[float]:
    """
    Extract lift-specific capacity estimate from performance snapshot metrics.
    
    Looks for e1RM estimate or current strength metric in the snapshot data.
    Supports multiple schema formats for flexibility.
    
    Args:
        snapshot_metrics: The metrics_json from a PerformanceSnapshot
        lift: The lift type to find capacity for
    
    Returns:
        Capacity value if found and valid, None otherwise
    """
    if not snapshot_metrics:
        return None
    
    lift_value = lift.value
    
    # Format 1: lifts.<lift>.e1rm_estimate (most specific)
    lifts_data = snapshot_metrics.get("lifts", {})
    if lift_value in lifts_data:
        lift_data = lifts_data[lift_value]
        if isinstance(lift_data, dict):
            # Try e1rm_estimate first
            e1rm = lift_data.get("e1rm_estimate")
            if e1rm and e1rm > 0:
                return float(e1rm)
            # Fallback to current_estimate or capacity
            for key in ["current_estimate", "capacity", "e1rm"]:
                val = lift_data.get(key)
                if val and val > 0:
                    return float(val)
    
    # Format 2: strength.<lift>.e1rm (alternative schema)
    strength_data = snapshot_metrics.get("strength", {})
    if lift_value in strength_data:
        lift_data = strength_data[lift_value]
        if isinstance(lift_data, dict):
            for key in ["e1rm_estimate", "e1rm", "current_estimate", "capacity"]:
                val = lift_data.get(key)
                if val and val > 0:
                    return float(val)
    
    # Format 3: data.e1rm_est or data.lift_e1rm (from strength performance snapshot)
    data = snapshot_metrics.get("data", {})
    if isinstance(data, dict):
        # Direct e1rm_est at top level of data
        e1rm_est = data.get("e1rm_est")
        if e1rm_est and e1rm_est > 0:
            # Check if lift matches (if specified in snapshot)
            snapshot_lift = data.get("lift")
            if snapshot_lift is None or snapshot_lift == lift_value:
                return float(e1rm_est)
    
    # Format 4: Check session_type strength and subtype
    session_type = snapshot_metrics.get("session_type", "")
    subtype = snapshot_metrics.get("subtype", "")
    if session_type == "strength" and subtype == lift_value:
        data = snapshot_metrics.get("data", {})
        if isinstance(data, dict):
            e1rm_est = data.get("e1rm_est")
            if e1rm_est and e1rm_est > 0:
                return float(e1rm_est)
    
    return None


def get_lift_capacity_estimate(
    db,
    athlete_id: Optional[int],
    lift: Union[LiftType, str],
    query_date: Optional[date] = None,
) -> Tuple[float, str]:
    """
    Sprint E2.2: Canonical capacity lookup for production strength impulse path.
    
    Lookup hierarchy (in order of preference):
    1) LiftCapacityProfile.model_capacity - latest profile for athlete + lift on/before query_date
    2) Lift day-state capacity C_l - latest available lift/day state on/before query_date
    3) Performance snapshot / e1RM-derived estimate - latest reliable lift-specific metric
    4) Lift-specific default fallback (NEVER returns 200kg universal fallback)
    
    Edge cases:
    - If db is None or athlete_id is None: skips DB-backed sources, goes directly to default
    - On any DB error: returns lift-specific default with source "default"
    
    Args:
        db: SQLAlchemy session (can be None)
        athlete_id: Athlete ID (can be None)
        lift: Lift type (string or LiftType enum)
        query_date: Date for lookup (default: today)
    
    Returns:
        Tuple of (capacity_value, source_string)
        Source strings: "capacity_profile" | "day_state" | "performance" | "default"
    """
    lift_normalized = normalize_lift_type(lift)
    
    # Edge case: No DB or no athlete_id - go directly to lift-specific default
    if db is None or athlete_id is None:
        default_capacity = LIFT_SPECIFIC_DEFAULTS.get(lift_normalized, 100.0)
        return (default_capacity, "default")
    
    try:
        from sqlalchemy import desc
        import app.models as db_models
        
        if query_date is None:
            query_date = date.today()
        
        query_date_str = query_date.isoformat() if isinstance(query_date, date) else str(query_date)
        
        # 1) Try LiftCapacityProfile.model_capacity (preferred)
        profile = db.query(db_models.LiftCapacityProfile).filter(
            db_models.LiftCapacityProfile.athlete_id == athlete_id,
            db_models.LiftCapacityProfile.lift == lift_normalized,
        ).order_by(desc(db_models.LiftCapacityProfile.updated_at)).first()
        
        if profile and profile.model_capacity > 0:
            return (float(profile.model_capacity), "capacity_profile")
        
        # 2) Try Lift day-state capacity C_l
        lift_day_state = db.query(db_models.LiftDayState).filter(
            db_models.LiftDayState.athlete_id == athlete_id,
            db_models.LiftDayState.lift == lift_normalized,
            db_models.LiftDayState.date <= query_date_str,
        ).order_by(desc(db_models.LiftDayState.date)).first()
        
        if lift_day_state and lift_day_state.C_l and lift_day_state.C_l > 0:
            return (float(lift_day_state.C_l), "day_state")
        
        # 3) Try Performance snapshot / e1RM-derived estimate
        # Find the most recent performance snapshot on or before query_date
        if hasattr(db_models, 'PerformanceSnapshot'):
            performance_snapshot = db.query(db_models.PerformanceSnapshot).filter(
                db_models.PerformanceSnapshot.athlete_id == athlete_id,
                db_models.PerformanceSnapshot.snapshot_date <= query_date_str,
            ).order_by(desc(db_models.PerformanceSnapshot.snapshot_date)).first()
            
            if performance_snapshot and performance_snapshot.metrics_json:
                capacity = _extract_capacity_from_performance_snapshot(
                    performance_snapshot.metrics_json,
                    lift_normalized
                )
                if capacity and capacity > 0:
                    return (float(capacity), "performance")
        
        # 4) Lift-specific default fallback (NEVER 200kg)
        default_capacity = LIFT_SPECIFIC_DEFAULTS.get(lift_normalized, 100.0)
        return (default_capacity, "default")
        
    except Exception:
        # On any error, return lift-specific default (never 200kg)
        default_capacity = LIFT_SPECIFIC_DEFAULTS.get(lift_normalized, 100.0)
        return (default_capacity, "default")


# Confidence-dependent breakthrough thresholds
def get_breakthrough_threshold(confidence: CapacityConfidence) -> float:
    """Get breakthrough threshold % based on confidence level."""
    thresholds = {
        CapacityConfidence.HIGH: 2.5,
        CapacityConfidence.MEDIUM: 2.0,
        CapacityConfidence.LOW: 1.5,
    }
    return thresholds.get(confidence, 2.0)


def compute_e1rm_from_set(load_kg: float, reps: int, rpe: Optional[float] = None) -> float:
    """
    Compute e1RM estimate from a single set.
    
    Formula without RPE: load * (1 + min(reps, 10) / 30)
    With RPE: adjusts based on RPE (lower RPE = higher estimated 1RM)
    """
    reps = min(reps, 10)
    
    if rpe is None:
        return load_kg * (1 + reps / 30)
    else:
        reps_in_reserve = 10 - rpe
        adjusted_reps = reps + reps_in_reserve
        adjusted_reps = min(adjusted_reps, 12)
        return load_kg * (1 + adjusted_reps / 30)


def determine_confidence_from_set(
    reps: int,
    rpe: Optional[float] = None
) -> CapacityConfidence:
    """Determine confidence level based on set parameters."""
    if reps <= 5 and rpe is not None and rpe >= 8:
        return CapacityConfidence.HIGH
    elif reps <= 8:
        return CapacityConfidence.MEDIUM
    else:
        return CapacityConfidence.LOW


def is_quality_strength_set(
    lift: LiftType,
    load_kg: float,
    reps: int,
    rpe: Optional[float] = None,
    velocity_loss: Optional[float] = None,
    observed_velocity: Optional[float] = None,
    anchor_capacity: float = 0.0,
) -> QualitySetResult:
    """
    Determine if a set is "quality" for capacity estimation.
    
    Lift-specific criteria:
    - Squat/Bench/Deadlift/Press: reps <= 6, load >= 0.75*anchor, RPE 7.0-9.5, VL <= 0.25
    - Power Clean: reps <= 3, load >= 0.70*anchor, velocity quality preferred
    """
    if anchor_capacity <= 0:
        return QualitySetResult(is_quality=False, reason="Invalid anchor capacity")
    
    relative_load = load_kg / anchor_capacity
    
    # Lift-specific criteria
    if lift in (LiftType.POWER_CLEAN, LiftType.CLEAN):
        # Olympic lift criteria
        if reps > 3:
            return QualitySetResult(is_quality=False, reason=f"Too many reps for clean ({reps} > 3)")
        if relative_load < 0.70:
            return QualitySetResult(is_quality=False, reason=f"Load too light ({relative_load:.1%} < 70%)")
        
        # For cleans, velocity data is preferred
        quality_score = min(1.0, relative_load)
        if observed_velocity is not None:
            # Good velocity indicates quality
            quality_score *= min(1.0, observed_velocity / 1.0)  # Normalize to 1.0 m/s
            signal_type = SignalType.VELOCITY
            signal_value = observed_velocity
        else:
            signal_type = SignalType.CLEAN_LOAD
            signal_value = load_kg
        
        signal = PerformanceSignal(
            signal_value=signal_value,
            signal_type=signal_type,
            quality_passed=True,
            quality_score=quality_score,
            reason="Quality clean set"
        )
        return QualitySetResult(is_quality=True, signal=signal, quality_score=quality_score)
    
    else:
        # Standard lift criteria (squat, bench, deadlift, press, other)
        if reps > 6:
            return QualitySetResult(is_quality=False, reason=f"Too many reps ({reps} > 6)")
        if relative_load < 0.75:
            return QualitySetResult(is_quality=False, reason=f"Load too light ({relative_load:.1%} < 75%)")
        if rpe is not None and (rpe < 7.0 or rpe > 9.5):
            return QualitySetResult(is_quality=False, reason=f"RPE out of range ({rpe}, need 7.0-9.5)")
        if velocity_loss is not None and velocity_loss > 0.25:
            return QualitySetResult(is_quality=False, reason=f"Velocity loss too high ({velocity_loss:.1%} > 25%)")
        
        # Compute quality score
        quality_score = min(1.0, relative_load)
        if velocity_loss is not None:
            quality_score *= (1 - velocity_loss / 0.25)  # Penalize higher VL
        if rpe is not None:
            # Ideal RPE is 8-9, penalize deviations
            rpe_factor = 1.0 - abs(rpe - 8.5) / 2.0
            quality_score *= max(0.5, rpe_factor)
        
        # Compute e1RM signal
        e1rm = compute_e1rm_from_set(load_kg, reps, rpe)
        
        signal = PerformanceSignal(
            signal_value=e1rm,
            signal_type=SignalType.E1RM,
            quality_passed=True,
            quality_score=quality_score,
            reason="Quality strength set"
        )
        return QualitySetResult(is_quality=True, signal=signal, quality_score=quality_score)


def extract_strength_performance_signal(
    lift: LiftType,
    load_kg: float,
    reps: int,
    rpe: Optional[float] = None,
    velocity_loss: Optional[float] = None,
    observed_velocity: Optional[float] = None,
    reference_velocity: Optional[float] = None,
    anchor_capacity: float = 0.0,
) -> PerformanceSignal:
    """
    Extract performance signal from a set.
    
    For non-clean lifts: computes e1RM
    For cleans: uses load or velocity quality
    """
    quality_result = is_quality_strength_set(
        lift=lift,
        load_kg=load_kg,
        reps=reps,
        rpe=rpe,
        velocity_loss=velocity_loss,
        observed_velocity=observed_velocity,
        anchor_capacity=anchor_capacity
    )
    
    if not quality_result.is_quality:
        return PerformanceSignal(
            signal_value=0.0,
            signal_type=SignalType.E1RM,
            quality_passed=False,
            quality_score=0.0,
            reason=quality_result.reason
        )
    
    return quality_result.signal


def detect_provisional_breakthrough(
    anchor_capacity: float,
    signal: PerformanceSignal,
    confidence: CapacityConfidence,
) -> bool:
    """
    Detect if signal qualifies as provisional breakthrough.
    
    Threshold depends on confidence:
    - high: +2.5%
    - medium: +2.0%
    - low: +1.5%
    """
    if not signal.quality_passed or anchor_capacity <= 0:
        return False
    
    threshold_pct = get_breakthrough_threshold(confidence)
    delta_pct = (signal.signal_value - anchor_capacity) / anchor_capacity * 100
    
    return delta_pct >= threshold_pct


def detect_confirmed_breakthrough(
    provisional_count: int,
    last_provisional_at: Optional[datetime],
    signal: PerformanceSignal,
    anchor_capacity: float,
) -> bool:
    """
    Detect if breakthrough should be confirmed.
    
    Confirmed if:
    A) Two provisional within 21 days
    B) One strong signal >= 4% above anchor
    """
    if not signal.quality_passed or anchor_capacity <= 0:
        return False
    
    delta_pct = (signal.signal_value - anchor_capacity) / anchor_capacity * 100
    
    # Strong signal immediate confirmation
    if delta_pct >= STRONG_SIGNAL_THRESHOLD_PCT:
        return True
    
    # Two provisional within window
    if provisional_count >= 1 and last_provisional_at is not None:
        days_since = (datetime.utcnow() - last_provisional_at).days
        if days_since <= PROVISIONAL_WINDOW_DAYS:
            return True
    
    return False


def apply_confirmed_breakthrough(
    current_anchor: float,
    signal_value: float,
    alpha: float = ANCHOR_UPDATE_ALPHA,
) -> float:
    """
    Apply confirmed breakthrough with partial anchor update.
    
    new_anchor = old_anchor + alpha * (signal - old_anchor)
    
    Default alpha = 0.5 (move halfway toward signal)
    """
    if current_anchor <= 0:
        return signal_value
    
    new_anchor = current_anchor + alpha * (signal_value - current_anchor)
    return new_anchor


def update_model_capacity(
    anchor_capacity: float,
    smoothed_recent_signal: Optional[float],
    blend_weight: float = MODEL_CAPACITY_BLEND,
) -> float:
    """
    Update model capacity as blend of anchor and recent signal.
    
    model_capacity = (1 - blend) * anchor + blend * smoothed_signal
    
    If no recent signal, model_capacity = anchor_capacity
    """
    if smoothed_recent_signal is None:
        return anchor_capacity
    
    model = (1 - blend_weight) * anchor_capacity + blend_weight * smoothed_recent_signal
    return model


def detect_breakthrough_v2(
    anchor_capacity: float,
    model_capacity: float,
    signal: PerformanceSignal,
    confidence: CapacityConfidence,
    provisional_count: int = 0,
    last_provisional_at: Optional[datetime] = None,
) -> BreakthroughDetectionResult:
    """
    Refined breakthrough detection with confidence-dependent thresholds.
    
    Returns updated capacities and breakthrough status.
    """
    if anchor_capacity <= 0 or not signal.quality_passed:
        return BreakthroughDetectionResult(
            is_provisional_breakthrough=False,
            is_confirmed_breakthrough=False,
            new_model_capacity=model_capacity,
            reason="Invalid signal or anchor"
        )
    
    delta_pct = (signal.signal_value - anchor_capacity) / anchor_capacity * 100
    
    # Check for confirmed breakthrough first
    is_confirmed = detect_confirmed_breakthrough(
        provisional_count=provisional_count,
        last_provisional_at=last_provisional_at,
        signal=signal,
        anchor_capacity=anchor_capacity
    )
    
    if is_confirmed:
        # Partial anchor update
        new_anchor = apply_confirmed_breakthrough(anchor_capacity, signal.signal_value)
        # Model blends new anchor with signal
        new_model = update_model_capacity(new_anchor, signal.signal_value)
        
        return BreakthroughDetectionResult(
            is_provisional_breakthrough=True,
            is_confirmed_breakthrough=True,
            new_anchor_capacity=new_anchor,
            new_model_capacity=new_model,
            signal_delta_pct=delta_pct,
            reason=f"Confirmed breakthrough ({delta_pct:+.1f}%): anchor {anchor_capacity:.1f} -> {new_anchor:.1f}"
        )
    
    # Check for provisional breakthrough
    is_provisional = detect_provisional_breakthrough(
        anchor_capacity=anchor_capacity,
        signal=signal,
        confidence=confidence
    )
    
    if is_provisional:
        # Model drifts toward signal
        new_model = update_model_capacity(anchor_capacity, signal.signal_value)
        
        return BreakthroughDetectionResult(
            is_provisional_breakthrough=True,
            is_confirmed_breakthrough=False,
            new_model_capacity=new_model,
            signal_delta_pct=delta_pct,
            reason=f"Provisional breakthrough ({provisional_count + 1}/{CONFIRMED_PROVISIONAL_COUNT}): {delta_pct:+.1f}%"
        )
    
    # No breakthrough: model still drifts slightly toward signal if positive
    if delta_pct > 0:
        new_model = update_model_capacity(anchor_capacity, signal.signal_value, blend_weight=0.15)
    else:
        # No aggressive downward updates - keep model close to anchor
        new_model = model_capacity
    
    return BreakthroughDetectionResult(
        is_provisional_breakthrough=False,
        is_confirmed_breakthrough=False,
        new_model_capacity=new_model,
        signal_delta_pct=delta_pct,
        reason=f"No breakthrough ({delta_pct:+.1f}%)"
    )


def should_reduce_anchor(
    poor_signal_count: int,
    first_poor_signal_at: Optional[datetime],
    recent_high_fatigue: bool = False,
) -> bool:
    """
    Determine if anchor should be reduced.
    
    Conservative rule: only reduce after 3+ poor signals across >=21 days
    and no high fatigue context.
    
    For now (V1): returns False (skip downward anchor updates)
    """
    # V1: Skip all downward anchor updates
    return False


def initialize_lift_capacity(
    lift: LiftType,
    input_type: CapacityInputType,
    input_load_kg: Optional[float] = None,
    input_reps: Optional[int] = None,
    input_rpe: Optional[float] = None
) -> CapacityInitializationResult:
    """Initialize capacity profile from user input."""
    if input_type == CapacityInputType.ONE_RM:
        if input_load_kg is None:
            raise ValueError("input_load_kg required for 1rm input_type")
        
        anchor = input_load_kg
        model = input_load_kg
        confidence = CapacityConfidence.HIGH
        
    elif input_type == CapacityInputType.BEST_SET:
        if input_load_kg is None or input_reps is None:
            raise ValueError("input_load_kg and input_reps required for best_set input_type")
        
        e1rm = compute_e1rm_from_set(input_load_kg, input_reps, input_rpe)
        anchor = e1rm
        model = e1rm
        confidence = determine_confidence_from_set(input_reps, input_rpe)
        
    elif input_type == CapacityInputType.UNKNOWN:
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


def get_default_capacity(lift: LiftType) -> float:
    """Get default capacity for a lift type."""
    return LIFT_DEFAULT_CAPACITY.get(lift, 80.0)


# Backwards compatibility wrapper for old detect_breakthrough signature
def detect_breakthrough(
    current_anchor: float,
    current_model: float,
    signal_e1rm: float,
    provisional_count: int = 0,
    confirmation_threshold_pct: float = 2.5,
    confirmation_required_count: int = 2,
    model_adjustment_rate: float = 0.3,
) -> BreakthroughDetectionResult:
    """
    Backwards-compatible wrapper for detect_breakthrough_v2.
    
    Takes signal_e1rm as float (old signature) instead of PerformanceSignal (new signature).
    Implements old-style confirmation logic (count-based, not time-based).
    """
    if current_anchor <= 0:
        return BreakthroughDetectionResult(
            is_provisional_breakthrough=False,
            is_confirmed_breakthrough=False,
            reason="Invalid anchor capacity"
        )
    
    delta_pct = (signal_e1rm - current_anchor) / current_anchor * 100
    
    # Check if signal meets provisional threshold
    is_provisional = delta_pct >= confirmation_threshold_pct
    
    if not is_provisional:
        # Model drifts toward signal
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
    
    # Old logic: confirmed if count reaches required (no time window)
    is_confirmed = new_provisional_count >= confirmation_required_count
    
    if is_confirmed:
        # Old behavior: full anchor update (not partial)
        new_anchor = signal_e1rm
        new_model = signal_e1rm
        
        return BreakthroughDetectionResult(
            is_provisional_breakthrough=True,
            is_confirmed_breakthrough=True,
            new_anchor_capacity=new_anchor,
            new_model_capacity=new_model,
            signal_delta_pct=delta_pct,
            reason=f"Confirmed breakthrough: {delta_pct:+.1f}% improvement"
        )
    else:
        # Provisional only
        new_model = current_model + (signal_e1rm - current_model) * model_adjustment_rate
        
        return BreakthroughDetectionResult(
            is_provisional_breakthrough=True,
            is_confirmed_breakthrough=False,
            new_model_capacity=new_model,
            signal_delta_pct=delta_pct,
            reason=f"Provisional breakthrough ({new_provisional_count}/{confirmation_required_count}): {delta_pct:+.1f}%"
        )


# Keep backwards compatibility for the old QualitySetResult too
QualitySetResultWithE1RM = QualitySetResult
