"""
Sprint P1/P2: Strength impulse feature computation from rep_engine outputs.

Replaces placeholder velocity_factor and vl with real rep_engine-derived values.
Adds metabolic impulse (u_met) computation aligned with day_engine expectations.
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import statistics

from app.domain.rep_engine import LiftVelocityProfile


# Sprint P2: Metabolic impulse constants
K_REP = 0.10      # Reps density factor
K_REST = 0.50     # Rest factor (shorter rest = higher metabolic cost)
K_VL_MET = 1.5    # VL metabolic factor
K_INT = 0.30      # Intensity penalty factor (heavy low-rep = less metabolic)
M_SCALE = 0.15    # Metabolic scaling factor
INTENSITY_PENALTY_MIN = 0.6  # Floor for intensity penalty


def normalize_velocities(raw_velocities: Any) -> Optional[List[float]]:
    """
    Sprint P2: Normalize velocities input to a list of floats.
    
    Handles:
    - JSON string -> parse to list
    - Python list -> validate floats
    - Invalid/malformed -> None
    
    Args:
        raw_velocities: Raw velocities input (JSON string, list, or other)
    
    Returns:
        List of float velocities, or None if invalid
    """
    if raw_velocities is None:
        return None
    
    velocities = None
    
    # Handle JSON string
    if isinstance(raw_velocities, str):
        try:
            import json
            velocities = json.loads(raw_velocities)
        except (json.JSONDecodeError, ValueError):
            return None
    elif isinstance(raw_velocities, (list, tuple)):
        velocities = raw_velocities
    else:
        return None
    
    # Validate and convert to floats
    if not velocities or not isinstance(velocities, (list, tuple)):
        return None
    
    try:
        normalized = [float(v) for v in velocities if v is not None]
        return normalized if len(normalized) >= 1 else None
    except (ValueError, TypeError):
        return None


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


def compute_velocity_factor_from_raw_velocities(
    velocities: List[float],
    load_kg: float,
    lift: str,
) -> Optional[float]:
    """
    Compute velocity_factor from raw velocities using calibrated lift profile.
    
    Calculates y_i = v_obs_i / v_ref(load) for each rep, then takes median
    of first 1-2 reps as velocity_factor.
    
    Args:
        velocities: List of observed velocities (m/s)
        load_kg: Load in kg
        lift: Lift identifier
    
    Returns:
        velocity_factor in [0.5, 1.2], or None if cannot compute
    """
    if not velocities or len(velocities) < 1:
        return None
    
    try:
        # Get calibrated profile for this lift
        profile = LiftVelocityProfile.calibrated_profile(lift)
        v_ref = profile.v_ref(load_kg)
        
        if v_ref <= 0:
            return None
        
        # Compute y = v_obs / v_ref for each rep
        y_values = [v / v_ref for v in velocities if v > 0]
        
        if not y_values:
            return None
        
        # Use median of first 1-2 reps
        y_sample = y_values[:2] if len(y_values) >= 2 else y_values
        y_median = statistics.median(y_sample)
        
        # Clamp to valid range
        return max(0.5, min(1.2, y_median))
        
    except Exception:
        return None


def compute_strength_impulse_features(
    rep_output: Any,
    set_idx: int,
    set_data: Optional[Dict] = None,
    lift: Optional[str] = None,
) -> StrengthImpulseFeatures:
    """
    Canonical helper to compute strength impulse features for a set.
    
    Sprint P1.1: Replaces placeholder velocity_factor=0.9 and vl=0.15
    with real rep_engine-derived values. Now derives velocity_factor from
    raw velocities when rep_engine summaries are unavailable.
    
    Priority:
    A) rep_engine SessionOutput with y values - source="rep_engine"
    B) Raw velocities JSON with lift profile - source="derived_from_velocities"
       - vl = 1 - last/first
       - velocity_factor = median(y_i) from v_obs/v_ref
    C) Neutral fallback - source="neutral_fallback", velocity_factor=1.0, vl=0.0
    
    Args:
        rep_output: SessionOutput from rep_engine, or None
        set_idx: Index of the set in the session
        set_data: Optional raw set data with velocities and load
        lift: Optional lift identifier
    
    Returns:
        StrengthImpulseFeatures with velocity_factor, vl, and source
    """
    # A) Try rep_engine output first
    if rep_output is not None:
        features = extract_features_from_rep_output(rep_output, set_idx, lift or "")
        if features.source == "rep_engine":
            return features
    
    # B) Derive from raw velocities if available
    if set_data is not None:
        # Sprint P2: Normalize velocities (handles JSON string, list, etc.)
        raw_velocities = set_data.get("velocities", [])
        velocities = normalize_velocities(raw_velocities)
        load_kg = set_data.get("load_kg", 0)
        
        if velocities and len(velocities) >= 2:
            vl = compute_set_vl(velocities)
            
            # Sprint P1.1: Also compute velocity_factor from raw velocities
            velocity_factor = compute_velocity_factor_from_raw_velocities(
                velocities, load_kg, lift or ""
            )
            
            if velocity_factor is not None:
                return StrengthImpulseFeatures(
                    velocity_factor=velocity_factor,
                    vl=vl,
                    source="derived_from_velocities"
                )
            else:
                # Could not compute velocity_factor, but have VL
                return StrengthImpulseFeatures(
                    velocity_factor=1.0,
                    vl=vl,
                    source="derived_from_velocities"
                )
    
    # C) Neutral fallback: no velocity data
    return StrengthImpulseFeatures(
        velocity_factor=1.0,  # Neutral: v_obs == v_ref
        vl=0.0,
        source="neutral_fallback"
    )


def compute_metabolic_impulse(
    load_kg: float,
    reps: int,
    rest_sec: Optional[float],
    vl: float,
    intensity: float,
) -> float:
    """
    Sprint P2: Compute metabolic impulse (u_met) for a strength set.

    Formula:
    - tonnage = load_kg * reps
    - rep_density_factor = 1 + K_REP * max(0, reps - 3)
    - rest_factor = 1 + K_REST * max(0, (180 - rest_sec) / 180)
    - vl_factor = 1 + K_VL_MET * vl
    - intensity_penalty = max(INTENSITY_PENALTY_MIN, 1 - K_INT * max(0, intensity - 0.85))
    - set_metabolic_impulse = tonnage * rep_density_factor * rest_factor * vl_factor * intensity_penalty * M_SCALE

    Interpretation:
    - More reps -> higher metabolic cost
    - Shorter rest (<180s) -> higher metabolic cost
    - Higher VL -> higher metabolic cost
    - Very heavy low-rep work (>85% intensity) -> relatively less metabolic emphasis

    Args:
        load_kg: Load in kg
        reps: Number of reps
        rest_sec: Rest before this set in seconds (None for first set)
        vl: Velocity loss (0.0-1.0)
        intensity: Relative intensity (load/capacity, 0.0-1.0)

    Returns:
        Metabolic impulse contribution for this set
    """
    tonnage = load_kg * reps

    # Reps density factor: more reps = more metabolic
    rep_density_factor = 1.0 + K_REP * max(0, reps - 3)

    # Rest factor: shorter rest = more metabolic (default 180s if None/first set)
    rest_sec = rest_sec if rest_sec is not None else 180.0
    rest_factor = 1.0 + K_REST * max(0.0, (180.0 - rest_sec) / 180.0)

    # VL factor: higher fatigue = more metabolic
    vl_factor = 1.0 + K_VL_MET * vl

    # Intensity penalty: very heavy low-rep = less metabolic emphasis
    intensity_penalty = max(
        INTENSITY_PENALTY_MIN,
        1.0 - K_INT * max(0.0, intensity - 0.85)
    )

    return tonnage * rep_density_factor * rest_factor * vl_factor * intensity_penalty * M_SCALE
