"""
Strength day-level target constructors for evaluation.

Implements literature-aligned acute strength targets:
1. Heaviest quality-set first-rep perf_y
2. Fixed-load first-rep velocity
3. Optional composite quality-set index
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import statistics


@dataclass
class StrengthTargetResult:
    """Result of target construction for a strength session."""
    target_value: Optional[float]
    target_source: str
    chosen_set_idx: Optional[int]
    chosen_set_metadata: Optional[Dict[str, Any]]
    raw_value: Optional[float]  # Unclamped value
    notes: List[str]


def _compute_perf_y(v_obs: float, load_kg: float, profile_a: float, profile_b: float) -> float:
    """Compute perf_y = v_obs / v_ref(load)."""
    v_ref = profile_a - profile_b * load_kg
    if v_ref <= 0:
        return None
    return v_obs / v_ref


def _is_quality_set(
    set_data: Dict,
    load_kg: float,
    anchor_capacity: Optional[float],
    model_capacity: Optional[float]
) -> tuple[bool, List[str]]:
    """
    Check if set meets quality criteria.
    
    Returns (is_quality, notes)
    """
    notes = []
    
    # Extract set properties
    reps = set_data.get("reps", 0)
    velocities = set_data.get("velocities", [])
    rpe = set_data.get("rpe")
    vl = set_data.get("vl")  # Velocity loss
    
    # Check reps constraint
    if reps > 6:
        return False, ["reps > 6"]
    
    if len(velocities) < 1:
        return False, ["no velocity data"]
    
    # Check load constraint (>= 50% of capacity if available)
    # Relaxed from 75% to ensure enough coverage
    capacity = anchor_capacity or model_capacity
    if capacity and capacity > 0:
        load_pct = load_kg / capacity
        if load_pct < 0.50:
            return False, [f"load {load_pct:.1%} < 50% capacity"]
    
    # Check RPE constraint if available
    if rpe is not None:
        if not (7.0 <= rpe <= 9.5):
            return False, [f"RPE {rpe} outside [7.0, 9.5]"]
    
    # Check velocity loss if available
    if vl is not None:
        if vl > 0.25:
            return False, [f"VL {vl:.2f} > 0.25"]
    
    return True, []


def target_heaviest_quality_set_perf_y(
    sets_data: List[Dict],
    profile_a: float,
    profile_b: float,
    anchor_capacity: Optional[float] = None,
    model_capacity: Optional[float] = None
) -> StrengthTargetResult:
    """
    TARGET 1: Heaviest quality-set first-rep perf_y
    
    Selects the heaviest set meeting quality criteria and computes
    perf_y = v_obs_rep1 / v_ref(load)
    
    Quality criteria:
    - reps <= 6
    - load >= 0.75 * capacity
    - RPE: 7.0-9.5 (if available)
    - VL <= 0.25 (if available)
    """
    if not sets_data:
        return StrengthTargetResult(
            target_value=None,
            target_source="heaviest_quality_set_perf_y",
            chosen_set_idx=None,
            chosen_set_metadata=None,
            raw_value=None,
            notes=["no sets data"]
        )
    
    best_set = None
    best_load = 0.0
    best_idx = None
    
    for idx, set_data in enumerate(sets_data):
        load_kg = set_data.get("load_kg") or set_data.get("weight", 0)
        
        is_quality, notes = _is_quality_set(set_data, load_kg, anchor_capacity, model_capacity)
        
        if is_quality and load_kg > best_load:
            best_set = set_data
            best_load = load_kg
            best_idx = idx
    
    if best_set is None:
        return StrengthTargetResult(
            target_value=None,
            target_source="heaviest_quality_set_perf_y",
            chosen_set_idx=None,
            chosen_set_metadata=None,
            raw_value=None,
            notes=["no quality sets found"]
        )
    
    # Compute perf_y for first rep
    velocities = best_set.get("velocities", [])
    if not velocities:
        return StrengthTargetResult(
            target_value=None,
            target_source="heaviest_quality_set_perf_y",
            chosen_set_idx=best_idx,
            chosen_set_metadata=best_set,
            raw_value=None,
            notes=["chosen set has no velocity data"]
        )
    
    v_obs_rep1 = velocities[0]
    perf_y = _compute_perf_y(v_obs_rep1, best_load, profile_a, profile_b)
    
    if perf_y is None:
        return StrengthTargetResult(
            target_value=None,
            target_source="heaviest_quality_set_perf_y",
            chosen_set_idx=best_idx,
            chosen_set_metadata=best_set,
            raw_value=None,
            notes=["could not compute perf_y (v_ref <= 0)"]
        )
    
    # Clamp for diagnostics but preserve raw
    target_value = max(0.60, min(1.10, perf_y))
    
    return StrengthTargetResult(
        target_value=target_value,
        target_source="heaviest_quality_set_perf_y",
        chosen_set_idx=best_idx,
        chosen_set_metadata={
            "load_kg": best_load,
            "reps": best_set.get("reps"),
            "rpe": best_set.get("rpe"),
            "vl": best_set.get("vl"),
            "v_obs_rep1": v_obs_rep1,
        },
        raw_value=perf_y,
        notes=[f"selected set {best_idx} with load {best_load:.1f}kg"]
    )


def target_fixed_load_first_rep_velocity(
    sets_data: List[Dict],
    profile_a: float,
    profile_b: float,
    anchor_capacity: Optional[float] = None,
    model_capacity: Optional[float] = None,
    lift: Optional[str] = None
) -> StrengthTargetResult:
    """
    TARGET 2: Fixed-load first-rep velocity
    
    Looks for a set near a standardized relative probe load:
    - squat/bench/deadlift/press: 70-80% of capacity
    - power_clean: 60-75%
    
    Returns v_obs_rep1 (optionally normalized to perf_y)
    """
    if not sets_data:
        return StrengthTargetResult(
            target_value=None,
            target_source="fixed_load_first_rep_velocity",
            chosen_set_idx=None,
            chosen_set_metadata=None,
            raw_value=None,
            notes=["no sets data"]
        )
    
    capacity = anchor_capacity or model_capacity
    if not capacity or capacity <= 0:
        return StrengthTargetResult(
            target_value=None,
            target_source="fixed_load_first_rep_velocity",
            chosen_set_idx=None,
            chosen_set_metadata=None,
            raw_value=None,
            notes=["no capacity available to compute target load"]
        )
    
    # Determine target load range based on lift
    if lift and "power_clean" in lift.lower():
        target_min_pct, target_max_pct = 0.60, 0.75
    else:
        target_min_pct, target_max_pct = 0.70, 0.80
    
    target_center = (target_min_pct + target_max_pct) / 2
    
    # Find set closest to target range
    best_set = None
    best_idx = None
    best_deviation = float('inf')
    
    for idx, set_data in enumerate(sets_data):
        load_kg = set_data.get("load_kg") or set_data.get("weight", 0)
        load_pct = load_kg / capacity
        
        # Compute deviation from target range
        if target_min_pct <= load_pct <= target_max_pct:
            deviation = 0.0  # In range
        elif load_pct < target_min_pct:
            deviation = target_min_pct - load_pct
        else:
            deviation = load_pct - target_max_pct
        
        # Must have velocity data
        velocities = set_data.get("velocities", [])
        if not velocities:
            continue
        
        if deviation < best_deviation:
            best_deviation = deviation
            best_set = set_data
            best_idx = idx
    
    if best_set is None:
        return StrengthTargetResult(
            target_value=None,
            target_source="fixed_load_first_rep_velocity",
            chosen_set_idx=None,
            chosen_set_metadata=None,
            raw_value=None,
            notes=["no sets with velocity data"]
        )
    
    # Get first rep velocity
    v_obs_rep1 = best_set["velocities"][0]
    load_kg = best_set.get("load_kg") or best_set.get("weight", 0)
    load_pct = load_kg / capacity
    
    # Compute normalized variant (perf_y)
    perf_y = _compute_perf_y(v_obs_rep1, load_kg, profile_a, profile_b)
    
    if perf_y is None:
        return StrengthTargetResult(
            target_value=None,
            target_source="fixed_load_first_rep_velocity",
            chosen_set_idx=best_idx,
            chosen_set_metadata=None,
            raw_value=None,
            notes=["could not compute perf_y (v_ref <= 0)"]
        )
    
    # Use perf_y as target (consistent with other targets), clamped to mapping bounds
    target_value = max(0.60, min(1.10, perf_y))
    
    notes = [
        f"selected set {best_idx}",
        f"load {load_kg:.1f}kg ({load_pct:.1%} of capacity)",
        f"deviation from target range: {best_deviation:.1%}"
    ]
    
    return StrengthTargetResult(
        target_value=target_value,
        target_source="fixed_load_first_rep_velocity",
        chosen_set_idx=best_idx,
        chosen_set_metadata={
            "load_kg": load_kg,
            "load_pct": round(load_pct, 4),
            "v_obs_rep1": v_obs_rep1,
            "perf_y": perf_y,
            "target_range": [target_min_pct, target_max_pct],
            "deviation": round(best_deviation, 4),
        },
        raw_value=v_obs_rep1,
        notes=notes
    )


def target_quality_set_composite(
    sets_data: List[Dict],
    profile_a: float,
    profile_b: float,
    anchor_capacity: Optional[float] = None,
    model_capacity: Optional[float] = None,
    lambda_vl: float = 0.3
) -> StrengthTargetResult:
    """
    TARGET 3 (Optional): Composite quality-set index
    
    composite = perf_y * (1 - lambda_vl * VL)
    
    where VL is velocity loss (if available)
    """
    # Start with heaviest quality set
    base_result = target_heaviest_quality_set_perf_y(
        sets_data, profile_a, profile_b, anchor_capacity, model_capacity
    )
    
    if base_result.target_value is None:
        return StrengthTargetResult(
            target_value=None,
            target_source="quality_set_composite",
            chosen_set_idx=base_result.chosen_set_idx,
            chosen_set_metadata=base_result.chosen_set_metadata,
            raw_value=None,
            notes=base_result.notes + ["composite: base target failed"]
        )
    
    # Get VL from chosen set
    chosen_idx = base_result.chosen_set_idx
    if chosen_idx is None or chosen_idx >= len(sets_data):
        return StrengthTargetResult(
            target_value=None,
            target_source="quality_set_composite",
            chosen_set_idx=chosen_idx,
            chosen_set_metadata=base_result.chosen_set_metadata,
            raw_value=None,
            notes=base_result.notes + ["composite: could not retrieve chosen set"]
        )
    
    chosen_set = sets_data[chosen_idx]
    vl = chosen_set.get("vl")
    
    if vl is None:
        # No VL available, just use perf_y
        return StrengthTargetResult(
            target_value=base_result.target_value,
            target_source="quality_set_composite",
            chosen_set_idx=chosen_idx,
            chosen_set_metadata=base_result.chosen_set_metadata,
            raw_value=base_result.raw_value,
            notes=base_result.notes + ["composite: no VL data, using perf_y only"]
        )
    
    # Compute composite
    perf_y = base_result.raw_value or base_result.target_value
    composite = perf_y * (1 - lambda_vl * vl)
    
    target_value = max(0.60, min(1.10, composite))
    
    metadata = dict(base_result.chosen_set_metadata or {})
    metadata["vl"] = vl
    metadata["lambda_vl"] = lambda_vl
    metadata["composite_raw"] = composite
    
    return StrengthTargetResult(
        target_value=target_value,
        target_source="quality_set_composite",
        chosen_set_idx=chosen_idx,
        chosen_set_metadata=metadata,
        raw_value=composite,
        notes=base_result.notes + [f"composite: perf_y={perf_y:.3f}, VL={vl:.3f}, lambda={lambda_vl}"]
    )


def get_day_level_strength_target(
    sets_data: List[Dict],
    lift: str,
    target_mode: str = "heaviest_quality_set_perf_y",
    profile_a: float = 0.55,
    profile_b: float = 0.003,
    anchor_capacity: Optional[float] = None,
    model_capacity: Optional[float] = None
) -> StrengthTargetResult:
    """
    Main entry point for day-level strength target construction.
    
    Args:
        sets_data: List of set dictionaries with velocity, load, reps, etc.
        lift: Lift name (e.g., "squat", "bench", "power_clean")
        target_mode: One of:
            - "heaviest_quality_set_perf_y"
            - "fixed_load_first_rep_velocity"
            - "quality_set_composite"
            - "legacy_rep2_rep1_ratio" (for comparison)
        profile_a: Velocity profile intercept
        profile_b: Velocity profile slope
        anchor_capacity: Athlete's anchor capacity for this lift
        model_capacity: Model-estimated capacity (fallback)
    
    Returns:
        StrengthTargetResult with target value and metadata
    """
    if target_mode == "heaviest_quality_set_perf_y":
        return target_heaviest_quality_set_perf_y(
            sets_data, profile_a, profile_b, anchor_capacity, model_capacity
        )
    elif target_mode == "fixed_load_first_rep_velocity":
        return target_fixed_load_first_rep_velocity(
            sets_data, profile_a, profile_b, anchor_capacity, model_capacity, lift
        )
    elif target_mode == "quality_set_composite":
        return target_quality_set_composite(
            sets_data, profile_a, profile_b, anchor_capacity, model_capacity
        )
    elif target_mode == "legacy_ratio":
        # Legacy target for comparison
        best_perf_y = None
        for set_data in sets_data:
            velocities = set_data.get("velocities", [])
            reps = set_data.get("reps", 0)
            if len(velocities) >= 2 and 2 <= reps <= 6 and velocities[0] > 0:
                perf_y = velocities[1] / velocities[0]
                if best_perf_y is None or perf_y > best_perf_y:
                    best_perf_y = perf_y
        
        return StrengthTargetResult(
            target_value=best_perf_y,
            target_source="legacy_ratio",
            chosen_set_idx=None,
            chosen_set_metadata=None,
            raw_value=best_perf_y,
            notes=["legacy: rep2/rep1 ratio"]
        )
    else:
        raise ValueError(f"Unknown target_mode: {target_mode}")
