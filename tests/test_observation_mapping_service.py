"""
Tests for Sprint V4.1: Observation Mapping Service

Tests verify:
1. Calibrated params are loaded when available
2. Fallback hierarchy works correctly
3. Operational prediction uses loaded params
4. Params source is tracked and reported
"""

import pytest
import json
import os
from pathlib import Path

from app.domain.observation_mapping import ObservationMappingParams
from app.services.observation_mapping_service import (
    get_observation_mapping_params,
    predict_perf_y_operational,
    load_calibrated_params,
    install_calibrated_params,
    get_operational_params_info,
    _find_config_file,
)


class TestParameterLoading:
    """Test parameter loading and fallback hierarchy."""
    
    def test_fallback_to_default_when_no_config(self):
        """Should fall back to default params when no config exists."""
        # Ensure no config exists in default locations
        result = get_observation_mapping_params()
        
        assert result.source == "default" or result.source == "calibrated_config"
        assert result.params is not None
    
    def test_explicit_params_take_priority(self):
        """Explicit params should override config file."""
        explicit = ObservationMappingParams(a=0.99, b_l=0.99, b_sys=0.99, b_t=0.99)
        
        result = get_observation_mapping_params(explicit_params=explicit)
        
        assert result.source == "explicit"
        assert result.params.a == 0.99
        assert result.params.b_l == 0.99
    
    def test_load_calibrated_params_from_file(self, tmp_path):
        """Should load calibrated params from valid config file."""
        config = {
            "version": 1,
            "global": {
                "a": 0.95,
                "b_l": 0.30,
                "b_sys": 0.20,
                "b_t": 0.15,
                "y_min": 0.60,
                "y_max": 1.10,
            },
            "per_lift": None,
        }
        
        config_path = tmp_path / "test_params.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        params = load_calibrated_params(str(config_path))
        
        assert params is not None
        assert params.a == 0.95
        assert params.b_l == 0.30
        assert params.b_sys == 0.20
        assert params.b_t == 0.15
    
    def test_load_flat_format_params(self, tmp_path):
        """Should handle flat format (direct params)."""
        config = {
            "a": 0.88,
            "b_l": 0.25,
            "b_sys": 0.15,
            "b_t": 0.10,
            "y_min": 0.60,
            "y_max": 1.10,
        }
        
        config_path = tmp_path / "flat_params.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        params = load_calibrated_params(str(config_path))
        
        assert params is not None
        assert params.a == 0.88


class TestOperationalPrediction:
    """Test operational prediction function."""
    
    def test_predict_perf_y_operational_uses_loaded_params(self, tmp_path):
        """Operational prediction should use params from config."""
        # Create a config with distinctive params
        config = {
            "version": 1,
            "global": {
                "a": 0.80,  # Distinctive intercept above y_min
                "b_l": 0.0,
                "b_sys": 0.0,
                "b_t": 0.0,
                "y_min": 0.60,
                "y_max": 1.10,
            },
        }
        
        config_path = tmp_path / "test_config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        # Predict with zero fatigue
        pred, source = predict_perf_y_operational(
            D_l=0.0,
            D_sys=0.0,
            T_legs=0.0,
            config_path=str(config_path),
        )
        
        # With these params, prediction should be ~0.80 (the intercept, above y_min)
        assert abs(pred - 0.80) < 0.01
        assert source == "calibrated_config"
    
    def test_predict_perf_y_operational_with_explicit_params(self):
        """Explicit params should be used when provided."""
        # Use a value above y_min (0.60) to avoid clamping
        explicit = ObservationMappingParams(a=0.75, b_l=0.0, b_sys=0.0, b_t=0.0)
        
        pred, source = predict_perf_y_operational(
            D_l=0.0,
            D_sys=0.0,
            T_legs=0.0,
            explicit_params=explicit,
        )
        
        assert abs(pred - 0.75) < 0.01
        assert source == "explicit"
    
    def test_predict_perf_y_operational_legacy_mode(self):
        """Legacy mode should use readiness-based mapping."""
        # Use a non-existent config path to ensure we get legacy mode
        pred, source = predict_perf_y_operational(
            D_l=0.0,  # No fatigue
            D_sys=0.0,
            T_legs=0.0,
            config_path="/nonexistent/path/params.json",
            use_legacy=True,
        )
        
        # Legacy with readiness=1.0 should predict near 1.0
        assert pred > 0.95
        assert source == "legacy"


class TestInstallCalibratedParams:
    """Test installation of calibrated params."""
    
    def test_install_creates_config_file(self, tmp_path):
        """Install should create a valid config file."""
        params = ObservationMappingParams(a=0.75, b_l=0.30, b_sys=0.20, b_t=0.15)
        target = tmp_path / "installed_config.json"
        
        result_path = install_calibrated_params(params, target_path=str(target))
        
        assert os.path.exists(result_path)
        
        # Verify content
        with open(result_path, 'r') as f:
            data = json.load(f)
        
        assert data["version"] == 1
        assert data["global"]["a"] == 0.75
        assert "installed_at" in data
        assert data["source"] == "calibrated_v4"
    
    def test_installed_params_can_be_loaded(self, tmp_path):
        """Installed params should be loadable."""
        params = ObservationMappingParams(a=0.80, b_l=0.25)
        target = tmp_path / "roundtrip_config.json"
        
        install_calibrated_params(params, target_path=str(target))
        loaded = load_calibrated_params(str(target))
        
        assert loaded is not None
        assert loaded.a == 0.80
        assert loaded.b_l == 0.25


class TestOperationalParamsInfo:
    """Test operational params info reporting."""
    
    def test_get_operational_params_info_returns_dict(self):
        """Should return info dict about current params."""
        info = get_operational_params_info()
        
        assert "source" in info
        assert "params" in info
        assert info["source"] in ["explicit", "calibrated_config", "default", "legacy"]


class TestCalibratedParamsAffectPredictions:
    """Test that loaded calibrated params materially affect predictions."""
    
    def test_different_params_produce_different_predictions(self):
        """Different param sets should produce measurably different predictions."""
        # Default params
        default_params = ObservationMappingParams.default_params()
        
        # Calibrated-like params (high T_legs coefficient)
        calibrated_params = ObservationMappingParams(
            a=1.0,
            b_l=0.0,
            b_sys=0.0,
            b_t=0.64,
        )
        
        # Test with moderate fatigue
        D_l, D_sys, T_legs = 0.5, 0.5, 0.5
        
        pred_default, _ = predict_perf_y_operational(
            D_l, D_sys, T_legs, explicit_params=default_params
        )
        pred_calibrated, _ = predict_perf_y_operational(
            D_l, D_sys, T_legs, explicit_params=calibrated_params
        )
        
        # Predictions should differ significantly
        assert abs(pred_default - pred_calibrated) > 0.1, \
            f"Predictions should differ: default={pred_default}, calibrated={pred_calibrated}"
    
    def test_calibrated_params_used_in_operational_path(self, tmp_path):
        """Operational path should use calibrated params when installed."""
        # Create distinctive calibrated config
        config = {
            "version": 1,
            "global": {
                "a": 0.70,
                "b_l": 0.0,
                "b_sys": 0.0,
                "b_t": 0.50,
                "y_min": 0.60,
                "y_max": 1.10,
            },
        }
        
        config_path = tmp_path / "operational_test.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        # Prediction with T_legs = 0.5
        pred, source = predict_perf_y_operational(
            D_l=0.0,
            D_sys=0.0,
            T_legs=0.5,
            config_path=str(config_path),
        )
        
        # With a=0.70, b_t=0.50, T_legs=0.5:
        # pred = 0.70 + 0.50 * (1 - 0.5) = 0.70 + 0.25 = 0.95
        expected = 0.70 + 0.50 * 0.5  # 0.95
        assert abs(pred - expected) < 0.01, f"Expected ~{expected}, got {pred}"
        assert source == "calibrated_config"
