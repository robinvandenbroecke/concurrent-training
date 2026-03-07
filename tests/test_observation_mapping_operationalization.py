"""
Tests for Sprint V4.1: Observation Mapping Operationalization

Tests verify:
1. Loaded calibrated params override defaults
2. Missing params file uses default constrained
3. Corrupt params file falls back safely
4. Replay uses calibrated params
5. Params source metadata is tracked
"""

import pytest
import json
import os
import tempfile
from pathlib import Path

from app.domain.observation_mapping import (
    ObservationMappingParams,
    load_mapping_params,
    save_mapping_params,
    validate_mapping_params,
)
from app.services.observation_mapping_service import (
    get_observation_mapping_params,
    predict_perf_y_operational,
    load_calibrated_params,
    install_calibrated_params,
)


class TestLoadedCalibratedParamsOverrideDefaults:
    """Test that calibrated params override defaults when present."""
    
    def test_loaded_calibrated_params_override_defaults(self, tmp_path):
        """
        Create a temp calibrated params file with non-default values,
        call the real prediction path, assert output uses loaded params.
        """
        # Create config with distinctive non-default values
        config = {
            "version": 1,
            "global": {
                "a": 0.90,  # Different from default 0.60
                "b_l": 0.0,
                "b_sys": 0.0,
                "b_t": 0.0,
                "y_min": 0.60,
                "y_max": 1.10,
            },
        }
        
        config_path = tmp_path / "calibrated.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        # Get params through service layer
        params_with_source = get_observation_mapping_params(config_path=str(config_path))
        
        assert params_with_source.source == "calibrated_config"
        assert params_with_source.params.a == 0.90  # Not default 0.60
    
    def test_prediction_uses_loaded_params(self, tmp_path):
        """Prediction output should reflect loaded params, not defaults."""
        # Config with high intercept
        config = {
            "global": {
                "a": 0.95,
                "b_l": 0.0,
                "b_sys": 0.0,
                "b_t": 0.0,
                "y_min": 0.60,
                "y_max": 1.10,
            },
        }
        
        config_path = tmp_path / "high_intercept.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        pred, source = predict_perf_y_operational(
            D_l=0.0, D_sys=0.0, T_legs=0.0,
            config_path=str(config_path)
        )
        
        # Should use high intercept from config, not default
        assert pred > 0.90  # Default would be ~0.95
        assert source == "calibrated_config"


class TestMissingParamsFileFallback:
    """Test fallback to defaults when params file is missing."""
    
    def test_missing_params_file_uses_default_constrained(self):
        """No file present -> default constrained params are used cleanly."""
        # Use a path that doesn't exist
        params_with_source = get_observation_mapping_params(
            config_path="/nonexistent/path/params.json"
        )
        
        # Should fall back to default
        assert params_with_source.source == "default"
        assert params_with_source.params is not None
        # Should have default values
        assert params_with_source.params.y_min == 0.60
        assert params_with_source.params.y_max == 1.10
    
    def test_prediction_with_missing_file(self):
        """Prediction should work with defaults when file missing."""
        pred, source = predict_perf_y_operational(
            D_l=0.0, D_sys=0.0, T_legs=0.0,
            config_path="/nonexistent/path/params.json"
        )
        
        assert source == "default"
        assert 0.60 <= pred <= 1.10  # Within default bounds


class TestCorruptParamsFileFallback:
    """Test safe fallback when params file is corrupt."""
    
    def test_corrupt_json_falls_back_safely(self, tmp_path):
        """Invalid JSON -> fallback to defaults, no crash."""
        corrupt_path = tmp_path / "corrupt.json"
        with open(corrupt_path, 'w') as f:
            f.write("{invalid json content")
        
        # Should not crash, should fall back
        params = load_mapping_params(
            str(corrupt_path),
            validate=True,
            fallback_to_defaults=True
        )
        
        # Should get defaults
        assert params.a == 0.60  # Default value
    
    def test_invalid_fields_falls_back_safely(self, tmp_path):
        """Invalid field values -> fallback to defaults."""
        config = {
            "a": "not_a_number",  # Invalid type
            "b_l": -0.5,  # Negative (should be >= 0)
            "b_sys": 0.0,
            "b_t": 0.0,
            "y_min": 0.60,
            "y_max": 1.10,
        }
        
        config_path = tmp_path / "invalid_fields.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        # Should fall back to defaults
        params = load_mapping_params(
            str(config_path),
            validate=True,
            fallback_to_defaults=True
        )
        
        assert params.a == 0.60  # Default
    
    def test_validation_detects_errors(self):
        """Validation should detect specific errors."""
        invalid_data = {
            "a": 0.5,
            # Missing required fields
        }
        
        is_valid, errors = validate_mapping_params(invalid_data)
        
        assert not is_valid
        assert len(errors) > 0
        assert any("Missing required field" in e for e in errors)


class TestReplayUsesCalibratedParams:
    """Test that replay uses calibrated params when available."""
    
    def test_replay_uses_calibrated_params(self, tmp_path):
        """
        Run a small replay scenario with calibrated params file,
        assert replay output differs from default-param replay.
        """
        # Create distinctive calibrated config
        config = {
            "global": {
                "a": 0.70,  # Low intercept
                "b_l": 0.0,
                "b_sys": 0.0,
                "b_t": 0.0,
                "y_min": 0.60,
                "y_max": 1.10,
            },
        }
        
        config_path = tmp_path / "replay_test.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        # Get params (simulating what replay would do)
        params_with_source = get_observation_mapping_params(config_path=str(config_path))
        
        assert params_with_source.source == "calibrated_config"
        assert params_with_source.params.a == 0.70
        
        # Prediction with these params should differ from default
        pred_calibrated, _ = predict_perf_y_operational(
            D_l=0.0, D_sys=0.0, T_legs=0.0,
            config_path=str(config_path)
        )
        
        pred_default, _ = predict_perf_y_operational(
            D_l=0.0, D_sys=0.0, T_legs=0.0,
            config_path="/nonexistent/path.json"
        )
        
        # Predictions should differ
        assert abs(pred_calibrated - pred_default) > 0.05


class TestParamsSourceMetadata:
    """Test that params source metadata is tracked correctly."""
    
    def test_params_source_metadata_explicit(self):
        """Source should be 'explicit' when explicit params provided."""
        explicit = ObservationMappingParams(a=0.80)
        
        result = get_observation_mapping_params(explicit_params=explicit)
        
        assert result.source == "explicit"
    
    def test_params_source_metadata_calibrated(self, tmp_path):
        """Source should be 'calibrated_config' when loaded from file."""
        config = {"global": {"a": 0.80, "b_l": 0.0, "b_sys": 0.0, "b_t": 0.0, "y_min": 0.60, "y_max": 1.10}}
        
        config_path = tmp_path / "source_test.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        result = get_observation_mapping_params(config_path=str(config_path))
        
        assert result.source == "calibrated_config"
        assert result.config_path == str(config_path)
    
    def test_params_source_metadata_default(self):
        """Source should be 'default' when no file exists."""
        result = get_observation_mapping_params(
            config_path="/nonexistent/path.json"
        )
        
        assert result.source == "default"
    
    def test_operational_prediction_returns_source(self, tmp_path):
        """Operational prediction should return source metadata."""
        config = {"global": {"a": 0.80, "b_l": 0.0, "b_sys": 0.0, "b_t": 0.0, "y_min": 0.60, "y_max": 1.10}}
        
        config_path = tmp_path / "source_pred.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        pred, source = predict_perf_y_operational(
            D_l=0.0, D_sys=0.0, T_legs=0.0,
            config_path=str(config_path)
        )
        
        assert source == "calibrated_config"


class TestPerLiftIntercepts:
    """Test per-lift intercept functionality."""
    
    def test_per_lift_intercepts_loaded_and_applied(self, tmp_path):
        """Per-lift intercepts should be loaded and affect predictions."""
        config = {
            "global": {
                "a": 0.60,
                "b_l": 0.0,
                "b_sys": 0.0,
                "b_t": 0.0,
                "y_min": 0.60,
                "y_max": 1.10,
            },
            "per_lift": {
                "squat": 0.90,
                "bench": 0.70,
            },
        }
        
        config_path = tmp_path / "per_lift.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        # Load params
        params = load_calibrated_params(str(config_path))
        
        assert params.per_lift_a is not None
        assert params.per_lift_a["squat"] == 0.90
        assert params.per_lift_a["bench"] == 0.70
        
        # Predictions should differ by lift
        pred_squat, _ = predict_perf_y_operational(
            D_l=0.0, D_sys=0.0, T_legs=0.0,
            config_path=str(config_path),
            lift="squat"
        )
        pred_bench, _ = predict_perf_y_operational(
            D_l=0.0, D_sys=0.0, T_legs=0.0,
            config_path=str(config_path),
            lift="bench"
        )
        
        assert pred_squat > pred_bench


class TestInstallAndRoundtrip:
    """Test install workflow."""
    
    def test_install_creates_valid_config(self, tmp_path):
        """Install should create a valid, loadable config."""
        params = ObservationMappingParams(a=0.75, b_l=0.30, b_sys=0.20, b_t=0.15)
        target = tmp_path / "installed.json"
        
        install_calibrated_params(params, target_path=str(target))
        
        # Should be loadable
        loaded = load_calibrated_params(str(target))
        assert loaded is not None
        assert loaded.a == 0.75
        assert loaded.b_l == 0.30
    
    def test_installed_params_are_operational(self, tmp_path):
        """Installed params should work in operational path."""
        params = ObservationMappingParams(a=0.85)
        target = tmp_path / "operational.json"
        
        install_calibrated_params(params, target_path=str(target))
        
        pred, source = predict_perf_y_operational(
            D_l=0.0, D_sys=0.0, T_legs=0.0,
            config_path=str(target)
        )
        
        assert source == "calibrated_config"
        assert pred > 0.80
