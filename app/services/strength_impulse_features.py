"""
Sprint P1: Strength impulse feature computation from rep_engine outputs.

Replaces placeholder velocity_factor and vl with real rep_engine-derived values.
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import statistics


@dataclass
class StrengthImpulseFeatures:
    """Real features computed from rep_engine output for a set."""
    velocity_factor: float
    vl: Optional[float]  # None if no velocity data
    source: str  # "rep_engine", "derived_from_velocities", "neutral_fallback"


def compute_set_vl(velocities: List[float]) -> Optional[float]:
    """
    Compute velocity loss (VL) from rep velocities.
    
    Definition: VL = 1 - (last_velocity / first_velocity)
    
    Args:
        velocities: List of observed velocities per rep (m/s)
    
    Returns:
        VL in [0.0, 1.0], or None if fewer than 2 velocities
    """
    if len(velocities) < 2:
        return None
    
    first_v = velocities[0]
    last_v = velocities[-1]
    
    if first_v <= 0:
        return None
    
    vl = 1.0 - (last_v / first_v)
    
    # Clamp to valid range [0.0, 1.0]
    return max(0.0, min(1.0, vl))


def compute_velocity_factor_from_y_values(y_values: List[float]) -> float:
    """
    Compute velocity_factor from rep_engine y values.
    
    y = v_obs / v_ref (normalized freshness signal)
    velocity_factor represents how "good" bar speed was relative to expectation.
    
    Uses median of first 2 reps (or all if fewer), clamped to [0.5, 1.2].
    
    Args:
        y_values: List of y values from rep_engine reps
    
    Returns:
        velocity_factor in [0.5, 1.2]
    """
    if not y_values:
        return 1.0  # Neutral fallback
    
    # Use first 2 reps (or all if fewer)
    y_sample = y_values[:2] if len(y_values) >= 2 else y_values
    
    # Use median for robustness
    y_median = statistics.median(y_sample)
    
    # Clamp to reasonable range
    return max(0.5, min(1.2, y_median))


def extract_features_from_rep_output(
    rep_output: Any,
    set_idx: int,
    lift: str,
) -> StrengthImpulseFeatures:
    """
    Extract real vl and velocity_factor from rep_engine SessionOutput.
    
    Args:
        rep_output: SessionOutput from rep_engine.simulate_strength_session()
        set_idx: Index of the set in the session
        lift: Lift identifier
    
    Returns:
        StrengthImpulseFeatures with real or fallback values
    """
    # No rep_output available - use neutral fallback
    if rep_output is None:
        return StrengthImpulseFeatures(
            velocity_factor=1.0,
            vl=None,
            source="neutral_fallback"
        )
    
    # Try to get the set output
    try:
        sets = rep_output.sets
        if not sets or set_idx >= len(sets):
            return StrengthImpulseFeatures(
                velocity_factor=1.0,
                vl=None,
                source="neutral_fallback"
            )
        
        set_output = sets[set_idx]
        
        # Extract VL directly from rep_engine (already computed)
        vl = getattr(set_output, 'VL', None)
        if vl is not None:
            # rep_engine VL is already a percentage (0.0-1.0)
            vl = float(vl)
        
        # Extract y values from reps for velocity_factor
        reps = getattr(set_output, 'reps', [])
        if reps:
            y_values = [getattr(rep, 'y', 1.0) for rep in reps]
            velocity_factor = compute_velocity_factor_from_y_values(y_values)
            source = "rep_engine"
        else:
            velocity_factor = 1.0
            source = "neutral_fallback"
        
        return StrengthImpulseFeatures(
            velocity_factor=velocity_factor,
            vl=vl,
            source=source
        )
        
    except (AttributeError, IndexError, TypeError):
        # Any error - use neutral fallback
        return StrengthImpulseFeatures(
            velocity_factor=1.0,
            vl=None,
            source="neutral_fallback"
        )


def compute_strength_impulse_features(
    rep_output: Any,
    set_idx: int,
    set_data: Optional[Dict] = None,
    lift: Optional[str] = None,
) -> StrengthImpulseFeatures:
    """
    Canonical helper to compute strength impulse features for a set.
    
    Sprint P1: Replaces placeholder velocity_factor=0.9 and vl=0.15
    with real rep_engine-derived values.
    
    Priority:
    1. rep_engine SessionOutput (if available) - source="rep_engine"
    2. Derived from raw velocities (if rep_output unavailable) - source="derived_from_velocities"
    3. Neutral fallback (no velocity data) - source="neutral_fallback", velocity_factor=1.0
    
    Args:
        rep_output: SessionOutput from rep_engine, or None
        set_idx: Index of the set in the session
        set_data: Optional raw set data with velocities
        lift: Optional lift identifier
    
    Returns:
        StrengthImpulseFeatures with velocity_factor, vl, and source
    """
    # Try rep_engine output first
    if rep_output is not None:
        features = extract_features_from_rep_output(rep_output, set_idx, lift or "")
        if features.source == "rep_engine":
            return features
    
    # Fallback: derive from raw velocities if available
    if set_data is not None:
        velocities = set_data.get("velocities", [])
        if velocities and len(velocities) >= 2:
            vl = compute_set_vl(velocities)
            # Without rep_engine y values, use neutral velocity_factor
            return StrengthImpulseFeatures(
                velocity_factor=1.0,
                vl=vl,
                source="derived_from_velocities"
            )
    
    # Final fallback: neutral values (explicit, documented)
    return StrengthImpulseFeatures(
        velocity_factor=1.0,  # Neutral: v_obs == v_ref
        vl=None,
        source="neutral_fallback"
    )
