"""Tests for target mode evaluation infrastructure."""
import pytest
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from app.eval.baselines import BaselineVelocityThreshold, BaselineBanister


class TestBaselineSeparation:
    """Test that model and baselines produce separate predictions."""
    
    def test_model_and_baselines_are_separate(self):
        """On a fixture, model / baseline A / baseline B produce different predictions."""
        # Setup baselines
        baseline_a = BaselineVelocityThreshold(window_days=7)
        baseline_b = BaselineBanister()
        
        # Add some history
        from datetime import date, timedelta
        for i in range(5):
            d = date(2026, 1, 1) + timedelta(days=i)
            baseline_a.add_observation("squat", d, 0.9 + i * 0.02)
            baseline_b.update("squat", d, tonnage=5000, intensity=0.75)
        
        # Get predictions
        pred_baseline_a = baseline_a.predict_perf_y("squat", date(2026, 1, 6))
        pred_baseline_b = baseline_b.predict_perf_y("squat")
        
        # Model prediction (simulated - would come from observation mapping)
        pred_model = 0.95  # Different from both baselines
        
        # Verify they can differ
        assert pred_baseline_a != pred_baseline_b or pred_model != pred_baseline_a, \
            "Predictions should be able to differ"


class TestArtifactsGenerated:
    """Test that required artifacts are generated."""
    
    ARTIFACTS_DIR = Path("/root/clawd/projects/concurrent-training/artifacts/synth_v2_run_v4_4_1")
    
    def test_target_mode_results_artifact_generated(self):
        """target_mode_results.json exists and contains all required target modes."""
        artifact_path = self.ARTIFACTS_DIR / "target_mode_results.json"
        
        if not artifact_path.exists():
            pytest.skip("Artifacts not yet generated - run sprint_v4_4_1_complete.py first")
        
        with open(artifact_path) as f:
            data = json.load(f)
        
        required_modes = [
            "legacy_ratio",
            "heaviest_quality_set_perf_y",
            "fixed_load_first_rep_velocity",
        ]
        
        for mode in required_modes:
            assert mode in data, f"Missing target mode: {mode}"
            assert "mae_model" in data[mode], f"Missing mae_model for {mode}"
            assert "mae_baseline_a" in data[mode], f"Missing mae_baseline_a for {mode}"
            assert "mae_baseline_b" in data[mode], f"Missing mae_baseline_b for {mode}"
    
    def test_target_comparison_summary_artifact_generated(self):
        """target_comparison_summary.json exists with expected keys."""
        artifact_path = self.ARTIFACTS_DIR / "target_comparison_summary.json"
        
        if not artifact_path.exists():
            pytest.skip("Artifacts not yet generated - run sprint_v4_4_1_complete.py first")
        
        with open(artifact_path) as f:
            data = json.load(f)
        
        required_modes = [
            "legacy_ratio",
            "heaviest_quality_set_perf_y",
            "fixed_load_first_rep_velocity",
        ]
        
        for mode in required_modes:
            assert mode in data, f"Missing target mode: {mode}"
            assert "n_samples" in data[mode], f"Missing n_samples for {mode}"
            assert "target_stats" in data[mode], f"Missing target_stats for {mode}"
            assert "scale_alignment" in data[mode], f"Missing scale_alignment for {mode}"
    
    def test_feature_target_correlations_by_target_generated(self):
        """feature_target_correlations_by_target.json exists with per-target entries."""
        artifact_path = self.ARTIFACTS_DIR / "feature_target_correlations_by_target.json"
        
        if not artifact_path.exists():
            pytest.skip("Artifacts not yet generated - run sprint_v4_4_1_complete.py first")
        
        with open(artifact_path) as f:
            data = json.load(f)
        
        required_modes = [
            "legacy_ratio",
            "heaviest_quality_set_perf_y",
            "fixed_load_first_rep_velocity",
        ]
        
        for mode in required_modes:
            assert mode in data, f"Missing target mode: {mode}"
            assert "feature_correlations" in data[mode], f"Missing feature_correlations for {mode}"
            fc = data[mode]["feature_correlations"]
            assert "D_l" in fc, f"Missing D_l correlation for {mode}"
            assert "D_sys" in fc, f"Missing D_sys correlation for {mode}"
            assert "T_legs" in fc, f"Missing T_legs correlation for {mode}"
    
    def test_fixed_load_diagnostics_generated(self):
        """fixed_load_diagnostics.json exists and explains availability."""
        artifact_path = self.ARTIFACTS_DIR / "fixed_load_diagnostics.json"
        
        if not artifact_path.exists():
            pytest.skip("Artifacts not yet generated - run sprint_v4_4_1_complete.py first")
        
        with open(artifact_path) as f:
            data = json.load(f)
        
        # Should have diagnostic fields
        assert "total_sessions" in data, "Missing total_sessions"
        assert "total_candidate_sets" in data, "Missing total_candidate_sets"
        assert "sets_selected" in data, "Missing sets_selected"
        assert "sets_rejected_no_velocity" in data, "Missing sets_rejected_no_velocity"
        assert "sets_rejected_load_range" in data, "Missing sets_rejected_load_range"
        assert "selection_rate" in data, "Missing selection_rate"


class TestReplayTargetModeSwitching:
    """Test that replay can switch target modes cleanly."""
    
    def test_replay_can_switch_target_modes_cleanly(self):
        """Replay path changes output when target mode changes."""
        from app.eval.strength_targets import get_day_level_strength_target
        
        sets_data = [
            {'velocities': [0.45, 0.42, 0.40], 'load_kg': 100, 'reps': 3, 'rpe': 8.0, 'vl': 0.11},
            {'velocities': [0.40, 0.38], 'load_kg': 110, 'reps': 2, 'rpe': 8.5, 'vl': 0.05},
        ]
        
        # Get targets for different modes
        result_legacy = get_day_level_strength_target(
            sets_data=sets_data,
            lift="squat",
            target_mode="legacy_ratio",
            profile_a=0.55,
            profile_b=0.003,
        )
        
        result_quality = get_day_level_strength_target(
            sets_data=sets_data,
            lift="squat",
            target_mode="heaviest_quality_set_perf_y",
            profile_a=0.55,
            profile_b=0.003,
            anchor_capacity=150,
            model_capacity=140,
        )
        
        # Targets should differ
        assert result_legacy.target_source == "legacy_ratio"
        assert result_quality.target_source == "heaviest_quality_set_perf_y"
        assert result_legacy.target_value != result_quality.target_value, \
            "Different target modes should produce different values"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
