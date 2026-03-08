"""
Sprint V5: Enhanced Observation Mapping Variants

Implements M0-M3 mapping variants for competitive model performance:
- M0: Current constrained mapping (global intercept + shared slopes)
- M1: Per-lift intercepts
- M2: Per-lift D_l slope
- M3: Target-specific calibrated params
"""
import json
import os
import statistics
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from pathlib import Path


@dataclass
class EnhancedMappingParams:
    """
    Enhanced parameters for observation mapping with per-lift and target-specific support.
    
    Formula (base):
        pred = a + b_l * (1 - D_l) + b_sys * (1 - D_sys) + b_t * (1 - T_legs)
        pred = clamp(pred, y_min, y_max)
    
    With per-lift intercepts (M1):
        intercept = per_lift_a.get(lift, a)
    
    With per-lift D_l slope (M2):
        b_l_effective = per_lift_b_l.get(lift, b_l)
    """
    # Base parameters
    a: float = 0.60  # Global intercept
    b_l: float = 0.25  # Local fatigue coefficient
    b_sys: float = 0.15  # Systemic fatigue coefficient
    b_t: float = 0.10  # Tissue fatigue coefficient
    
    # Output bounds
    y_min: float = 0.60
    y_max: float = 1.10
    
    # Per-lift parameters (M1, M2)
    per_lift_a: Optional[Dict[str, float]] = None  # Per-lift intercepts
    per_lift_b_l: Optional[Dict[str, float]] = None  # Per-lift D_l slopes (M2)
    
    # Metadata
    target_mode: Optional[str] = None  # Which target this is calibrated for
    mapping_variant: str = "M0"  # M0, M1, M2, M3
    updated_at: Optional[str] = None
    
    def __post_init__(self):
        """Enforce constraints."""
        self.b_l = max(0.0, self.b_l)
        self.b_sys = max(0.0, self.b_sys)
        self.b_t = max(0.0, self.b_t)
        self.y_min = max(0.0, min(1.0, self.y_min))
        self.y_max = max(self.y_min, min(2.0, self.y_max))
        
        # Ensure per-lift params are non-negative
        if self.per_lift_a:
            self.per_lift_a = {k: max(0.0, min(2.0, v)) for k, v in self.per_lift_a.items()}
        if self.per_lift_b_l:
            self.per_lift_b_l = {k: max(0.0, v) for k, v in self.per_lift_b_l.items()}
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'EnhancedMappingParams':
        """Create from dictionary."""
        # Filter to only valid fields
        valid_fields = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**valid_fields)
    
    def get_intercept(self, lift: Optional[str] = None) -> float:
        """Get effective intercept for lift."""
        if lift and self.per_lift_a and lift in self.per_lift_a:
            return self.per_lift_a[lift]
        return self.a
    
    def get_b_l(self, lift: Optional[str] = None) -> float:
        """Get effective D_l coefficient for lift."""
        if lift and self.per_lift_b_l and lift in self.per_lift_b_l:
            return self.per_lift_b_l[lift]
        return self.b_l


def predict_with_enhanced_mapping(
    D_l: float,
    D_sys: float,
    T_legs: float,
    params: EnhancedMappingParams,
    lift: Optional[str] = None
) -> float:
    """
    Predict perf_y using enhanced mapping with per-lift support.
    
    Args:
        D_l: Local fatigue
        D_sys: Systemic fatigue
        T_legs: Tissue fatigue
        params: Enhanced mapping parameters
        lift: Optional lift name for per-lift params
    
    Returns:
        Predicted perf_y in [y_min, y_max]
    """
    # Get effective parameters
    intercept = params.get_intercept(lift)
    b_l = params.get_b_l(lift)
    
    # Compute prediction
    fatigue_terms = (
        b_l * max(0.0, 1.0 - D_l) +
        params.b_sys * max(0.0, 1.0 - D_sys) +
        params.b_t * max(0.0, 1.0 - T_legs)
    )
    
    pred = intercept + fatigue_terms
    
    # Enforce bounds
    return max(params.y_min, min(params.y_max, pred))


@dataclass
class CalibrationResult:
    """Result of calibration."""
    params: EnhancedMappingParams
    train_mae: float
    per_lift_mae: Optional[Dict[str, float]] = None
    iterations: int = 0


def calibrate_mapping_variant(
    day_error_rows: List[Dict],
    variant: str = "M0",
    target_mode: Optional[str] = None,
    grid_steps: int = 8,
    refinement_steps: int = 2
) -> CalibrationResult:
    """
    Calibrate mapping variant using grid search.
    
    Args:
        day_error_rows: List of dicts with D_l, D_sys, T_legs, observed, lift
        variant: "M0", "M1", "M2", or "M3"
        target_mode: Target mode name (for M3)
        grid_steps: Grid resolution
        refinement_steps: Number of refinement passes
    
    Returns:
        CalibrationResult with best params
    """
    if not day_error_rows:
        return CalibrationResult(
            params=EnhancedMappingParams.default_for_variant(variant, target_mode),
            train_mae=float('inf'),
            iterations=0
        )
    
    lifts = list(set(row.get('lift', 'unknown') for row in day_error_rows))
    
    def compute_mae(params: EnhancedMappingParams) -> float:
        errors = []
        for row in day_error_rows:
            pred = predict_with_enhanced_mapping(
                D_l=row.get('D_l', 0.0),
                D_sys=row.get('D_sys', 0.0),
                T_legs=row.get('T_legs', 0.0),
                params=params,
                lift=row.get('lift') if variant in ["M1", "M2", "M3"] else None
            )
            errors.append(abs(pred - row['observed']))
        return statistics.mean(errors) if errors else float('inf')
    
    # Initial parameter ranges
    param_ranges = {
        'a': (0.2, 1.0),
        'b_l': (0.0, 1.5),
        'b_sys': (0.0, 1.5),
        'b_t': (0.0, 1.5),
    }
    
    best_params = EnhancedMappingParams.default_for_variant(variant, target_mode)
    best_mae = compute_mae(best_params)
    total_iterations = 0
    
    # Grid search
    for refinement in range(refinement_steps):
        for a in _linspace(param_ranges['a'][0], param_ranges['a'][1], grid_steps):
            for b_l in _linspace(param_ranges['b_l'][0], param_ranges['b_l'][1], grid_steps):
                for b_sys in _linspace(param_ranges['b_sys'][0], param_ranges['b_sys'][1], grid_steps):
                    for b_t in _linspace(param_ranges['b_t'][0], param_ranges['b_t'][1], grid_steps):
                        params = EnhancedMappingParams(
                            a=a, b_l=b_l, b_sys=b_sys, b_t=b_t,
                            y_min=0.60, y_max=1.10,
                            mapping_variant=variant,
                            target_mode=target_mode
                        )
                        mae = compute_mae(params)
                        total_iterations += 1
                        
                        if mae < best_mae:
                            best_mae = mae
                            best_params = params
        
        # Refine
        margin = (param_ranges['a'][1] - param_ranges['a'][0]) / grid_steps
        param_ranges = {
            'a': (max(0.2, best_params.a - margin), min(1.0, best_params.a + margin)),
            'b_l': (max(0.0, best_params.b_l - margin), min(1.5, best_params.b_l + margin)),
            'b_sys': (max(0.0, best_params.b_sys - margin), min(1.5, best_params.b_sys + margin)),
            'b_t': (max(0.0, best_params.b_t - margin), min(1.5, best_params.b_t + margin)),
        }
    
    # Fit per-lift parameters for M1, M2, M3
    if variant in ["M1", "M2", "M3"]:
        per_lift_a = {}
        per_lift_b_l = {}
        
        for lift in lifts:
            lift_rows = [r for r in day_error_rows if r.get('lift') == lift]
            if not lift_rows:
                continue
            
            # Fit per-lift intercept (M1, M2, M3)
            if variant in ["M1", "M2", "M3"]:
                best_lift_a = best_params.a
                best_lift_mae = float('inf')
                
                for a in _linspace(0.2, 1.0, 15):
                    test_params = EnhancedMappingParams(
                        a=best_params.a,
                        b_l=best_params.b_l,
                        b_sys=best_params.b_sys,
                        b_t=best_params.b_t,
                        y_min=0.60, y_max=1.10,
                        per_lift_a={lift: a},
                        mapping_variant=variant,
                        target_mode=target_mode
                    )
                    
                    errors = []
                    for row in lift_rows:
                        pred = predict_with_enhanced_mapping(
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
            
            # Fit per-lift D_l slope (M2, M3)
            if variant in ["M2", "M3"]:
                best_lift_b_l = best_params.b_l
                best_lift_mae = float('inf')
                
                for b_l in _linspace(0.0, 1.5, 15):
                    test_params = EnhancedMappingParams(
                        a=best_params.a,
                        b_l=best_params.b_l,
                        b_sys=best_params.b_sys,
                        b_t=best_params.b_t,
                        y_min=0.60, y_max=1.10,
                        per_lift_a={lift: per_lift_a.get(lift, best_params.a)},
                        per_lift_b_l={lift: b_l},
                        mapping_variant=variant,
                        target_mode=target_mode
                    )
                    
                    errors = []
                    for row in lift_rows:
                        pred = predict_with_enhanced_mapping(
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
                        best_lift_b_l = b_l
                
                per_lift_b_l[lift] = best_lift_b_l
        
        best_params.per_lift_a = per_lift_a if per_lift_a else None
        best_params.per_lift_b_l = per_lift_b_l if per_lift_b_l else None
        best_mae = compute_mae(best_params)
    
    # Compute per-lift MAE
    per_lift_mae = {}
    for lift in lifts:
        lift_rows = [r for r in day_error_rows if r.get('lift') == lift]
        if lift_rows:
            errors = []
            for row in lift_rows:
                pred = predict_with_enhanced_mapping(
                    D_l=row.get('D_l', 0.0),
                    D_sys=row.get('D_sys', 0.0),
                    T_legs=row.get('T_legs', 0.0),
                    params=best_params,
                    lift=lift
                )
                errors.append(abs(pred - row['observed']))
            per_lift_mae[lift] = round(statistics.mean(errors), 4)
    
    return CalibrationResult(
        params=best_params,
        train_mae=best_mae,
        per_lift_mae=per_lift_mae,
        iterations=total_iterations
    )


def _linspace(start: float, stop: float, num: int) -> List[float]:
    """Generate evenly spaced values."""
    if num <= 1:
        return [start]
    step = (stop - start) / (num - 1)
    return [start + i * step for i in range(num)]


# Default params factory
EnhancedMappingParams.default_for_variant = lambda cls, variant, target_mode=None: EnhancedMappingParams(
    a=0.60,
    b_l=0.25,
    b_sys=0.15,
    b_t=0.10,
    y_min=0.60,
    y_max=1.10,
    mapping_variant=variant,
    target_mode=target_mode
)


# Config storage
def get_config_path(target_mode: str, variant: str = "M0", base_dir: str = "./artifacts/config") -> str:
    """Get path for storing/loading target-specific params."""
    filename = f"observation_mapping_{target_mode}_{variant}.json"
    return os.path.join(base_dir, filename)


def save_target_specific_params(
    params: EnhancedMappingParams,
    target_mode: str,
    base_dir: str = "./artifacts/config"
):
    """Save params with target mode metadata."""
    params.target_mode = target_mode
    params.updated_at = str(datetime.now()) if 'datetime' in dir() else None
    
    path = get_config_path(target_mode, params.mapping_variant, base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    with open(path, 'w') as f:
        json.dump(params.to_dict(), f, indent=2)


def load_target_specific_params(
    target_mode: str,
    variant: str = "M0",
    base_dir: str = "./artifacts/config",
    fallback_to_defaults: bool = True
) -> EnhancedMappingParams:
    """Load params for specific target mode."""
    path = get_config_path(target_mode, variant, base_dir)
    
    if not os.path.exists(path):
        if fallback_to_defaults:
            return EnhancedMappingParams.default_for_variant(variant, target_mode)
        raise FileNotFoundError(f"No params for {target_mode} variant {variant}")
    
    with open(path) as f:
        data = json.load(f)
    
    return EnhancedMappingParams.from_dict(data)


def load_params_with_fallback(
    target_mode: str,
    variant: str = "M0",
    base_dir: str = "./artifacts/config"
) -> EnhancedMappingParams:
    """
    Load params with fallback hierarchy:
    1. explicit params for this target_mode and variant
    2. params for this target_mode with default variant
    3. safe default params for this target_mode
    4. generic default params
    """
    # Try 1: exact match
    try:
        return load_target_specific_params(target_mode, variant, base_dir, fallback_to_defaults=False)
    except FileNotFoundError:
        pass
    
    # Try 2: target mode with M0
    if variant != "M0":
        try:
            return load_target_specific_params(target_mode, "M0", base_dir, fallback_to_defaults=False)
        except FileNotFoundError:
            pass
    
    # Try 3 & 4: defaults
    return EnhancedMappingParams.default_for_variant(variant, target_mode)
