"""Tests for enhanced observation mapping variants."""
import pytest
import sys
import os
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.domain.enhanced_observation_mapping import (
    EnhancedMappingParams,
    predict_with_enhanced_mapping,
    calibrate_mapping_variant,
    save_target_specific_params,
    load_params_with_fallback,
    get_config_path,
)


class TestPerLiftIntercepts:
    """Test M1: per-lift intercepts change predictions."""
    
    def test_per_lift_intercepts_change_predictions(self):
        """Same states, different lifts -> different predictions under M1."""
        params = EnhancedMappingParams(
            a=0.60,
            b_l=0.25,
            b_sys=0.15,
            b_t=0.10,
            per_lift_a={
                "squat": 0.70,
                "bench": 0.65,
            },
            mapping_variant="M1"
        )
        
        # Same fatigue states
        D_l, D_sys, T_legs = 0.3, 0.2, 0.1
        
        pred_squat = predict_with_enhanced_mapping(D_l, D_sys, T_legs, params, "squat")
        pred_bench = predict_with_enhanced_mapping(D_l, D_sys, T_legs, params, "bench")
        pred_default = predict_with_enhanced_mapping(D_l, D_sys, T_legs, params, None)
        
        # Predictions should differ
        assert pred_squat != pred_bench, "Per-lift intercepts should produce different predictions"
        # Verify squat uses per-lift intercept (0.70) and default uses global (0.60)
        expected_squat = 0.70 + 0.25 * (1 - 0.3) + 0.15 * (1 - 0.2) + 0.10 * (1 - 0.1)
        expected_default = 0.60 + 0.25 * (1 - 0.3) + 0.15 * (1 - 0.2) + 0.10 * (1 - 0.1)
        assert abs(pred_squat - expected_squat) < 0.001
        assert abs(pred_default - expected_default) < 0.001


class TestPerLiftDlSlope:
    """Test M2: per-lift D_l slope changes predictions."""
    
    def test_per_lift_dl_slope_changes_predictions(self):
        """Same D_sys/T_legs but different lift-specific D_l slope -> predictions differ under M2."""
        params = EnhancedMappingParams(
            a=0.60,
            b_l=0.25,  # Global fallback
            b_sys=0.15,
            b_t=0.10,
            per_lift_a={"squat": 0.70, "bench": 0.65},
            per_lift_b_l={"squat": 0.40, "bench": 0.20},  # Different D_l slopes
            mapping_variant="M2"
        )
        
        # Same states
        D_l, D_sys, T_legs = 0.5, 0.3, 0.2
        
        pred_squat = predict_with_enhanced_mapping(D_l, D_sys, T_legs, params, "squat")
        pred_bench = predict_with_enhanced_mapping(D_l, D_sys, T_legs, params, "bench")
        
        # Should use different b_l values
        expected_squat = 0.70 + 0.40 * 0.5 + 0.15 * 0.7 + 0.10 * 0.8
        expected_bench = 0.65 + 0.20 * 0.5 + 0.15 * 0.7 + 0.10 * 0.8
        
        assert abs(pred_squat - expected_squat) < 0.001
        assert abs(pred_bench - expected_bench) < 0.001
        assert pred_squat != pred_bench


class TestTargetSpecificParams:
    """Test M3: target-specific params load correctly."""
    
    def test_target_specific_params_save_and_load(self, tmp_path):
        """Params for different targets are stored and loaded separately."""
        # Create params for heaviest target
        params_heaviest = EnhancedMappingParams(
            a=0.65,
            b_l=0.30,
            b_sys=0.20,
            b_t=0.15,
            target_mode="heaviest_quality_set_perf_y",
            mapping_variant="M1"
        )
        
        # Create params for fixed-load target
        params_fixed = EnhancedMappingParams(
            a=0.55,
            b_l=0.35,
            b_sys=0.10,
            b_t=0.20,
            target_mode="fixed_load_first_rep_velocity",
            mapping_variant="M1"
        )
        
        base_dir = str(tmp_path / "config")
        
        # Save both
        save_target_specific_params(params_heaviest, "heaviest_quality_set_perf_y", base_dir)
        save_target_specific_params(params_fixed, "fixed_load_first_rep_velocity", base_dir)
        
        # Load and verify
        loaded_heaviest = load_params_with_fallback("heaviest_quality_set_perf_y", "M1", base_dir)
        loaded_fixed = load_params_with_fallback("fixed_load_first_rep_velocity", "M1", base_dir)
        
        assert loaded_heaviest.a == 0.65
        assert loaded_fixed.a == 0.55
        assert loaded_heaviest.target_mode == "heaviest_quality_set_perf_y"
        assert loaded_fixed.target_mode == "fixed_load_first_rep_velocity"
    
    def test_fallback_hierarchy(self, tmp_path):
        """Fallback hierarchy works correctly."""
        base_dir = str(tmp_path / "config")
        
        # Only save M0 for heaviest
        params_m0 = EnhancedMappingParams(a=0.70, mapping_variant="M0", target_mode="heaviest")
        save_target_specific_params(params_m0, "heaviest", base_dir)
        
        # Request M1 - should fall back to M0
        loaded = load_params_with_fallback("heaviest", "M1", base_dir)
        assert loaded.a == 0.70


class TestMappingBoundedAndMonotonic:
    """Test that mappings preserve boundedness and monotonicity."""
    
    def test_output_is_bounded(self):
        """Predictions are always within [y_min, y_max]."""
        params = EnhancedMappingParams(y_min=0.60, y_max=1.10)
        
        # Extreme inputs
        test_cases = [
            (0.0, 0.0, 0.0),   # No fatigue
            (1.0, 1.0, 1.0),   # Max fatigue
            (2.0, 2.0, 2.0),   # Extreme fatigue
            (-1.0, -1.0, -1.0), # Negative (should be clamped)
        ]
        
        for D_l, D_sys, T_legs in test_cases:
            pred = predict_with_enhanced_mapping(D_l, D_sys, T_legs, params)
            assert 0.60 <= pred <= 1.10, f"Prediction {pred} out of bounds for inputs ({D_l}, {D_sys}, {T_legs})"
    
    def test_monotonicity_lower_fatigue_higher_pred(self):
        """Lower fatigue -> higher or equal prediction."""
        params = EnhancedMappingParams(a=0.60, b_l=0.25, b_sys=0.15, b_t=0.10)
        
        base = predict_with_enhanced_mapping(0.5, 0.5, 0.5, params)
        
        # Lower D_l -> higher pred
        lower_dl = predict_with_enhanced_mapping(0.3, 0.5, 0.5, params)
        assert lower_dl >= base
        
        # Lower D_sys -> higher pred
        lower_dsys = predict_with_enhanced_mapping(0.5, 0.3, 0.5, params)
        assert lower_dsys >= base
        
        # Lower T_legs -> higher pred
        lower_t = predict_with_enhanced_mapping(0.5, 0.5, 0.3, params)
        assert lower_t >= base


class TestCalibrationProducesValidParams:
    """Test that calibration produces valid parameters."""
    
    def test_calibration_produces_bounded_params(self):
        """Calibrated params satisfy all constraints."""
        # Simple fixture data
        day_data = [
            {'D_l': 0.3, 'D_sys': 0.2, 'T_legs': 0.1, 'observed': 0.9, 'lift': 'squat'},
            {'D_l': 0.5, 'D_sys': 0.4, 'T_legs': 0.2, 'observed': 0.8, 'lift': 'squat'},
            {'D_l': 0.2, 'D_sys': 0.1, 'T_legs': 0.05, 'observed': 0.95, 'lift': 'bench'},
        ]
        
        for variant in ["M0", "M1", "M2"]:
            result = calibrate_mapping_variant(day_data, variant=variant, grid_steps=5, refinement_steps=1)
            
            params = result.params
            assert params.b_l >= 0, f"{variant}: b_l must be >= 0"
            assert params.b_sys >= 0, f"{variant}: b_sys must be >= 0"
            assert params.b_t >= 0, f"{variant}: b_t must be >= 0"
            assert params.y_min < params.y_max, f"{variant}: y_min must be < y_max"


class TestArtifactsGenerated:
    """Test that variant comparison artifacts are generated."""
    
    ARTIFACTS_DIR = REPO_ROOT / "artifacts" / "synth_v2_run_v5"
    
    def test_model_vs_baselines_summary_artifact_generated(self):
        """model_vs_baselines_summary.json exists with required fields."""
        artifact_path = self.ARTIFACTS_DIR / "model_vs_baselines_summary.json"
        
        if not artifact_path.exists():
            pytest.skip("Artifacts not yet generated - run sprint_v5_model_comparison.py first")
        
        with open(artifact_path) as f:
            data = json.load(f)
        
        for target_mode in ["heaviest_quality_set_perf_y", "fixed_load_first_rep_velocity"]:
            if target_mode in data:
                assert "baseline_a_mae" in data[target_mode]
                assert "baseline_b_mae" in data[target_mode]
                assert "best_model_mae" in data[target_mode]
                assert "best_variant" in data[target_mode]
    
    def test_mapping_variant_comparison_artifact_generated(self):
        """mapping_variant_comparison.json exists with all variants."""
        artifact_path = self.ARTIFACTS_DIR / "mapping_variant_comparison.json"
        
        if not artifact_path.exists():
            pytest.skip("Artifacts not yet generated - run sprint_v5_model_comparison.py first")
        
        with open(artifact_path) as f:
            data = json.load(f)
        
        for target_mode in data.values():
            assert "variants" in target_mode
            variants = target_mode["variants"]
            for variant in ["M0", "M1", "M2"]:
                if variant in variants:
                    assert "mae" in variants[variant]
                    assert "params" in variants[variant]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
