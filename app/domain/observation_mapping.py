"""
Sprint V4: Constrained Observation Mapping for Day-Level Strength Performance Prediction

Maps internal day-engine states (D_l, D_sys, T_legs) to predicted observed perf_y
using a constrained, monotonic, bounded formulation.

Constraints:
- Monotonic: lower fatigue -> higher predicted performance
- Bounded: output clamped to physiologically plausible range
- Interpretable: coefficients have clear meaning
"""

import json
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
import statistics


@dataclass
class ObservationMappingParams:
    """
    Parameters for constrained observation mapping.
    
    Formula:
        pred = a + b_l * (1 - D_l) + b_sys * (1 - D_sys) + b_t * (1 - T_legs)
        pred = clamp(pred, y_min, y_max)
    
    Constraints enforced:
        - b_l >= 0 (lower local fatigue -> higher performance)
        - b_sys >= 0 (lower systemic fatigue -> higher performance)  
        - b_t >= 0 (lower tissue fatigue -> higher performance)
        - y_min, y_max fixed bounds
    """
    # Base intercept (performance at max fatigue)
    a: float = 0.60
    
    # Coefficients for (1 - fatigue) terms
    b_l: float = 0.25      # Local fatigue coefficient
    b_sys: float = 0.15    # Systemic fatigue coefficient
    b_t: float = 0.10      # Tissue/connective fatigue coefficient
    
    # Output bounds
    y_min: float = 0.60
    y_max: float = 1.10
    
    # Optional per-lift intercepts (additive to base 'a')
    # If None, use global 'a' for all lifts
    per_lift_a: Optional[Dict[str, float]] = None
    
    def __post_init__(self):
        """Enforce constraints on coefficients."""
        # Ensure non-negative coefficients (monotonicity)
        self.b_l = max(0.0, self.b_l)
        self.b_sys = max(0.0, self.b_sys)
        self.b_t = max(0.0, self.b_t)
        
        # Ensure sensible bounds
        self.y_min = max(0.0, min(1.0, self.y_min))
        self.y_max = max(self.y_min, min(2.0, self.y_max))
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'ObservationMappingParams':
        """Create from dictionary."""
        return cls(**d)
    
    @classmethod
    def default_params(cls) -> 'ObservationMappingParams':
        """Get default safe starter parameters."""
        return cls(
            a=0.60,
            b_l=0.25,
            b_sys=0.15,
            b_t=0.10,
            y_min=0.60,
            y_max=1.10,
        )
    
    @classmethod
    def calibrated_params_v1(cls) -> 'ObservationMappingParams':
        """
        Calibrated parameters from Sprint V4.
        These may be updated after calibration.
        """
        return cls(
            a=0.65,
            b_l=0.35,
            b_sys=0.20,
            b_t=0.15,
            y_min=0.60,
            y_max=1.10,
        )


def predict_perf_y_constrained(
    D_l: float,
    D_sys: float,
    T_legs: float,
    params: Optional[ObservationMappingParams] = None,
    lift: Optional[str] = None
) -> float:
    """
    Predict observed perf_y from internal day-engine states.
    
    Uses constrained, monotonic, bounded mapping:
        pred = a + b_l*(1-D_l) + b_sys*(1-D_sys) + b_t*(1-T_legs)
        pred = clamp(pred, y_min, y_max)
    
    Args:
        D_l: Local fatigue for the lift (0-1+, higher = more fatigued)
        D_sys: Systemic fatigue (0-1+, higher = more fatigued)
        T_legs: Legs tissue/connective fatigue (0-1+, higher = more fatigued)
        params: Mapping parameters (uses default if None)
        lift: Optional lift name for per-lift intercept
    
    Returns:
        Predicted perf_y in [y_min, y_max]
    
    Monotonicity guarantees:
        - Lower D_l -> higher or equal pred
        - Lower D_sys -> higher or equal pred
        - Lower T_legs -> higher or equal pred
    """
    if params is None:
        params = ObservationMappingParams.default_params()
    
    # Base intercept with optional per-lift adjustment
    intercept = params.a
    if lift and params.per_lift_a and lift in params.per_lift_a:
        intercept = params.per_lift_a[lift]
    
    # Constrained linear combination of (1 - fatigue) terms
    # Note: We use (1 - fatigue) so that lower fatigue -> higher contribution
    fatigue_terms = (
        params.b_l * max(0.0, 1.0 - D_l) +
        params.b_sys * max(0.0, 1.0 - D_sys) +
        params.b_t * max(0.0, 1.0 - T_legs)
    )
    
    pred = intercept + fatigue_terms
    
    # Enforce bounds
    return max(params.y_min, min(params.y_max, pred))


def compute_readiness_from_states(
    D_l: float,
    D_sys: float,
    w_sys: float = 0.5
) -> float:
    """
    Compute a unified readiness score from individual fatigue states.
    
    This is a legacy helper for backward compatibility.
    New code should use predict_perf_y_constrained directly.
    
    Args:
        D_l: Local fatigue
        D_sys: Systemic fatigue
        w_sys: Weight for systemic vs local fatigue
    
    Returns:
        Readiness score in [0, 1]
    """
    readiness = max(0.0, min(1.0, 1.0 - D_l - w_sys * D_sys))
    return readiness


def predict_perf_y_from_readiness_legacy(readiness: float) -> float:
    """
    LEGACY: Original hand-tuned mapping from readiness to perf_y.
    
    Kept for backward compatibility and comparison purposes.
    
    Formula: perf_y = 0.75 + 0.25 * readiness, clamped to [0.60, 1.10]
    
    Args:
        readiness: Readiness score (0-1)
    
    Returns:
        Predicted perf_y
    """
    pred = 0.75 + 0.25 * readiness
    return max(0.60, min(1.10, pred))


# =============================================================================
# CALIBRATION UTILITIES (No ML libraries)
# =============================================================================

@dataclass
class CalibrationResult:
    """Result of calibration procedure."""
    params: ObservationMappingParams
    train_mae: float
    per_lift_mae: Optional[Dict[str, float]] = None
    iterations: int = 0


def calibrate_observation_mapping(
    day_error_rows: List[Dict],
    per_lift: bool = False,
    grid_steps: int = 10,
    refinement_steps: int = 3
) -> CalibrationResult:
    """
    Calibrate observation mapping parameters using simple grid search.
    
    No ML libraries required. Uses bounded coordinate search with
    constraint enforcement.
    
    Args:
        day_error_rows: List of dicts with keys:
            - 'D_l', 'D_sys', 'T_legs': fatigue states
            - 'observed': actual perf_y
            - 'lift': lift name (optional, for per-lift mode)
        per_lift: If True, fit separate intercepts per lift
        grid_steps: Initial grid resolution
        refinement_steps: Number of refinement iterations
    
    Returns:
        CalibrationResult with best params and MAE
    """
    if not day_error_rows:
        return CalibrationResult(
            params=ObservationMappingParams.default_params(),
            train_mae=float('inf'),
            iterations=0
        )
    
    # Extract data
    lifts = list(set(row.get('lift', 'unknown') for row in day_error_rows))
    
    def compute_mae(params: ObservationMappingParams) -> float:
        """Compute MAE for given parameters."""
        errors = []
        for row in day_error_rows:
            pred = predict_perf_y_constrained(
                D_l=row.get('D_l', 0.0),
                D_sys=row.get('D_sys', 0.0),
                T_legs=row.get('T_legs', 0.0),
                params=params,
                lift=row.get('lift') if per_lift else None
            )
            errors.append(abs(pred - row['observed']))
        return statistics.mean(errors) if errors else float('inf')
    
    def compute_per_lift_mae(params: ObservationMappingParams) -> Dict[str, float]:
        """Compute per-lift MAE."""
        per_lift_errors = {lift: [] for lift in lifts}
        for row in day_error_rows:
            lift = row.get('lift', 'unknown')
            pred = predict_perf_y_constrained(
                D_l=row.get('D_l', 0.0),
                D_sys=row.get('D_sys', 0.0),
                T_legs=row.get('T_legs', 0.0),
                params=params,
                lift=lift if per_lift else None
            )
            if lift in per_lift_errors:
                per_lift_errors[lift].append(abs(pred - row['observed']))
        
        return {
            lift: statistics.mean(errors) if errors else float('inf')
            for lift, errors in per_lift_errors.items()
        }
    
    # Initial search ranges
    param_ranges = {
        'a': (0.2, 1.0),
        'b_l': (0.0, 1.5),
        'b_sys': (0.0, 1.5),
        'b_t': (0.0, 1.5),
    }
    
    best_params = ObservationMappingParams.default_params()
    best_mae = compute_mae(best_params)
    total_iterations = 0
    
    # Grid search with refinement
    for refinement in range(refinement_steps):
        step_size = 1.0 / (grid_steps * (refinement + 1))
        
        for a in _linspace(param_ranges['a'][0], param_ranges['a'][1], grid_steps):
            for b_l in _linspace(param_ranges['b_l'][0], param_ranges['b_l'][1], grid_steps):
                for b_sys in _linspace(param_ranges['b_sys'][0], param_ranges['b_sys'][1], grid_steps):
                    for b_t in _linspace(param_ranges['b_t'][0], param_ranges['b_t'][1], grid_steps):
                        params = ObservationMappingParams(
                            a=a, b_l=b_l, b_sys=b_sys, b_t=b_t,
                            y_min=0.60, y_max=1.10
                        )
                        mae = compute_mae(params)
                        total_iterations += 1
                        
                        if mae < best_mae:
                            best_mae = mae
                            best_params = params
        
        # Refine search around best point
        margin = (param_ranges['a'][1] - param_ranges['a'][0]) / grid_steps
        param_ranges = {
            'a': (max(0.2, best_params.a - margin), min(1.0, best_params.a + margin)),
            'b_l': (max(0.0, best_params.b_l - margin), min(1.5, best_params.b_l + margin)),
            'b_sys': (max(0.0, best_params.b_sys - margin), min(1.5, best_params.b_sys + margin)),
            'b_t': (max(0.0, best_params.b_t - margin), min(1.5, best_params.b_t + margin)),
        }
    
    # Fit per-lift intercepts if requested
    if per_lift:
        per_lift_a = {}
        for lift in lifts:
            lift_rows = [r for r in day_error_rows if r.get('lift') == lift]
            if lift_rows:
                # Optimize just the intercept for this lift
                best_lift_a = best_params.a
                best_lift_mae = float('inf')
                
                for a in _linspace(0.2, 1.0, 20):
                    test_params = ObservationMappingParams(
                        a=best_params.a,  # Base
                        b_l=best_params.b_l,
                        b_sys=best_params.b_sys,
                        b_t=best_params.b_t,
                        y_min=0.60, y_max=1.10,
                        per_lift_a={lift: a}
                    )
                    
                    errors = []
                    for row in lift_rows:
                        pred = predict_perf_y_constrained(
                            D_l=row.get('D_l', 0.0),
                            D_sys=row.get('D_sys', 0.0),
                            T_legs=row.get('T_legs', 0.0),
                            params=test_params,
                            lift=lift
                        )
                        errors.append(abs(pred - row['observed']))
                    
                    mae = statistics.mean(errors)
                    if mae < best_lift_mae:
                        best_lift_mae = mae
                        best_lift_a = a
                
                per_lift_a[lift] = best_lift_a
        
        best_params.per_lift_a = per_lift_a
        best_mae = compute_mae(best_params)  # Recompute with per-lift intercepts
    
    per_lift_mae = compute_per_lift_mae(best_params) if per_lift else None
    
    return CalibrationResult(
        params=best_params,
        train_mae=best_mae,
        per_lift_mae=per_lift_mae,
        iterations=total_iterations
    )


def _linspace(start: float, stop: float, num: int) -> List[float]:
    """Generate evenly spaced values (numpy linspace equivalent)."""
    if num <= 1:
        return [start]
    step = (stop - start) / (num - 1)
    return [start + i * step for i in range(num)]


def validate_mapping_params(data: dict) -> tuple[bool, list[str]]:
    """
    Validate mapping parameters dict.
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    
    # Check required fields
    required_fields = ['a', 'b_l', 'b_sys', 'b_t', 'y_min', 'y_max']
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    if errors:
        return False, errors
    
    # Validate types and ranges
    float_fields = ['a', 'b_l', 'b_sys', 'b_t', 'y_min', 'y_max']
    for field in float_fields:
        try:
            val = float(data[field])
            if field in ['b_l', 'b_sys', 'b_t'] and val < 0:
                errors.append(f"{field} must be >= 0, got {val}")
            if field == 'y_min' and not (0 <= val <= 1):
                errors.append(f"y_min must be in [0, 1], got {val}")
            if field == 'y_max' and not (0.5 <= val <= 2):
                errors.append(f"y_max must be in [0.5, 2], got {val}")
        except (TypeError, ValueError):
            errors.append(f"{field} must be numeric, got {type(data[field])}")
    
    # Validate y_min < y_max
    try:
        if float(data['y_min']) >= float(data['y_max']):
            errors.append(f"y_min must be < y_max")
    except (TypeError, ValueError):
        pass  # Already caught above
    
    return len(errors) == 0, errors


def load_mapping_params(path: str, validate: bool = True, fallback_to_defaults: bool = True) -> ObservationMappingParams:
    """
    Load mapping parameters from JSON file with validation.
    
    Args:
        path: Path to JSON file
        validate: If True, validate params before returning
        fallback_to_defaults: If True and validation fails, return defaults
    
    Returns:
        ObservationMappingParams (loaded or fallback)
    
    Raises:
        ValueError: If validation fails and fallback_to_defaults is False
        FileNotFoundError: If file doesn't exist
    """
    if not os.path.exists(path):
        if fallback_to_defaults:
            print(f"Warning: Params file not found at {path}, using defaults")
            return ObservationMappingParams.default_params()
        raise FileNotFoundError(f"Params file not found: {path}")
    
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        
        # Handle both flat and nested formats
        per_lift = None
        if 'global' in data:
            per_lift = data.get('per_lift') or data.get('per_lift_a')
            data = data['global']
        else:
            per_lift = data.get('per_lift') or data.get('per_lift_a')
        
        if validate:
            is_valid, errors = validate_mapping_params(data)
            if not is_valid:
                error_msg = "; ".join(errors)
                if fallback_to_defaults:
                    print(f"Warning: Invalid params in {path}: {error_msg}. Using defaults.")
                    return ObservationMappingParams.default_params()
                raise ValueError(f"Invalid params in {path}: {error_msg}")
        
        # Build params with per_lift if present
        params = ObservationMappingParams.from_dict(data)
        if per_lift:
            params.per_lift_a = per_lift
        return params
    
    except json.JSONDecodeError as e:
        if fallback_to_defaults:
            print(f"Warning: Invalid JSON in {path}: {e}. Using defaults.")
            return ObservationMappingParams.default_params()
        raise


def save_mapping_params(params: ObservationMappingParams, path: str, create_dirs: bool = True):
    """
    Save mapping parameters to JSON file.
    
    Args:
        params: Parameters to save
        path: Target file path
        create_dirs: If True, create parent directories
    """
    if create_dirs:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    
    with open(path, 'w') as f:
        json.dump(params.to_dict(), f, indent=2)
