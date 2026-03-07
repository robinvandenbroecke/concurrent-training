"""
Sprint V4.1: Observation Mapping Service

Provides the canonical source of truth for observation mapping parameters
with a safe fallback hierarchy.

Fallback hierarchy:
1. Explicitly supplied params (for experiments)
2. Persisted calibrated params from config
3. Safe default constrained params
4. Legacy mapping (only if explicitly requested)
"""

import json
import os
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from pathlib import Path

from app.domain.observation_mapping import (
    ObservationMappingParams,
    predict_perf_y_constrained,
    predict_perf_y_from_readiness_legacy,
    load_mapping_params,
    save_mapping_params,
    validate_mapping_params,
)


# Canonical paths for mapping parameters (in order of preference)
DEFAULT_CONFIG_PATHS = [
    # Runtime artifact (highest priority - latest calibration)
    "./artifacts/config/observation_mapping_params.json",
    # Stable config in app directory
    "./app/config/observation_mapping_params.json",
    # Fallback to calibrated v4 results
    "./artifacts/synth_v2_run_v4/calibrated_mapping_params.json",
]


@dataclass
class MappingParamsWithSource:
    """Mapping parameters with metadata about their source."""
    params: ObservationMappingParams
    source: str  # "explicit" | "calibrated_config" | "default" | "legacy"
    config_path: Optional[str] = None


def _find_config_file() -> Optional[str]:
    """Find the first available config file."""
    for path in DEFAULT_CONFIG_PATHS:
        if os.path.exists(path):
            return path
    return None


def load_calibrated_params(config_path: Optional[str] = None) -> Optional[ObservationMappingParams]:
    """
    Load calibrated parameters from config file with validation.
    
    Args:
        config_path: Explicit path to config file, or None to search default locations
    
    Returns:
        ObservationMappingParams if found and valid, None otherwise
    """
    path = config_path or _find_config_file()
    
    if not path or not os.path.exists(path):
        return None
    
    try:
        # Use domain layer validation
        params = load_mapping_params(path, validate=True, fallback_to_defaults=False)
        return params
    
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"Warning: Failed to load calibrated params from {path}: {e}")
        return None


def get_observation_mapping_params(
    explicit_params: Optional[ObservationMappingParams] = None,
    config_path: Optional[str] = None,
    use_legacy: bool = False,
) -> MappingParamsWithSource:
    """
    Get observation mapping parameters following the fallback hierarchy.
    
    Fallback hierarchy:
        1. explicit_params (if provided)
        2. Calibrated params from config file
        3. Default constrained params
        4. Legacy mode (only if use_legacy=True)
    
    Args:
        explicit_params: Explicitly provided params (highest priority)
        config_path: Path to config file, or None to search defaults
        use_legacy: If True, return legacy mode instead of default params
    
    Returns:
        MappingParamsWithSource with params and metadata
    """
    # 1. Explicit params
    if explicit_params is not None:
        return MappingParamsWithSource(
            params=explicit_params,
            source="explicit",
            config_path=None
        )
    
    # 2. Calibrated params from config
    calibrated = load_calibrated_params(config_path)
    if calibrated is not None:
        path = config_path or _find_config_file()
        return MappingParamsWithSource(
            params=calibrated,
            source="calibrated_config",
            config_path=path
        )
    
    # 3. Default constrained params (or legacy if requested)
    if use_legacy:
        # Return default params but mark as legacy mode
        # The actual legacy prediction uses a different function
        return MappingParamsWithSource(
            params=ObservationMappingParams.default_params(),
            source="legacy",
            config_path=None
        )
    else:
        return MappingParamsWithSource(
            params=ObservationMappingParams.default_params(),
            source="default",
            config_path=None
        )


def predict_perf_y_operational(
    D_l: float,
    D_sys: float,
    T_legs: float,
    lift: Optional[str] = None,
    explicit_params: Optional[ObservationMappingParams] = None,
    config_path: Optional[str] = None,
    use_legacy: bool = False,
) -> Tuple[float, str]:
    """
    Operational prediction function that uses the proper parameter hierarchy.
    
    This is the main entry point for production day-level perf_y prediction.
    
    Args:
        D_l: Local fatigue
        D_sys: Systemic fatigue
        T_legs: Tissue/connective fatigue
        lift: Optional lift name for per-lift intercepts
        explicit_params: Optional explicit params for experiments
        config_path: Optional explicit config path
        use_legacy: If True, use legacy readiness-based mapping
    
    Returns:
        Tuple of (predicted_perf_y, params_source)
    """
    params_with_source = get_observation_mapping_params(
        explicit_params=explicit_params,
        config_path=config_path,
        use_legacy=use_legacy,
    )
    
    if use_legacy:
        # Legacy path: readiness -> perf_y
        from app.domain.observation_mapping import compute_readiness_from_states
        readiness = compute_readiness_from_states(D_l, D_sys)
        pred = predict_perf_y_from_readiness_legacy(readiness)
        return pred, params_with_source.source
    
    # Constrained mapping path
    pred = predict_perf_y_constrained(
        D_l=D_l,
        D_sys=D_sys,
        T_legs=T_legs,
        params=params_with_source.params,
        lift=lift,
    )
    
    return pred, params_with_source.source


def install_calibrated_params(
    params: ObservationMappingParams,
    target_path: str = "./artifacts/config/observation_mapping_params.json",
    create_dirs: bool = True,
) -> str:
    """
    Install calibrated parameters as the operational source of truth.
    
    Args:
        params: Calibrated parameters to install
        target_path: Where to write the config
        create_dirs: If True, create parent directories
    
    Returns:
        Path to installed config file
    """
    path = Path(target_path)
    
    if create_dirs:
        path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write with metadata using domain layer save
    output = {
        "version": 1,
        "global": {
            "a": params.a,
            "b_l": params.b_l,
            "b_sys": params.b_sys,
            "b_t": params.b_t,
            "y_min": params.y_min,
            "y_max": params.y_max,
        },
        "per_lift": params.per_lift_a,
        "installed_at": str(__import__('datetime').datetime.now()),
        "source": "calibrated_v4",
    }
    
    with open(path, 'w') as f:
        json.dump(output, f, indent=2)
    
    return str(path)


def get_operational_params_info() -> Dict:
    """
    Get information about currently operational parameters.
    
    Returns:
        Dict with source, path, and parameter values
    """
    params_with_source = get_observation_mapping_params()
    
    return {
        "source": params_with_source.source,
        "config_path": params_with_source.config_path,
        "params": params_with_source.params.to_dict(),
    }
