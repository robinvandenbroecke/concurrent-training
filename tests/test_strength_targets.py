"""Tests for strength_targets module."""
import pytest
import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.eval.strength_targets import (
    get_day_level_strength_target,
    target_heaviest_quality_set_perf_y,
    target_fixed_load_first_rep_velocity,
    StrengthTargetResult,
)


class TestHeaviestQualitySetPerfY:
    """Test heaviest quality set target constructor."""
    
    def test_heaviest_quality_set_perf_y_selects_heaviest_valid_set(self):
        """Among several sets, it should choose the heaviest one satisfying quality criteria."""
        sets_data = [
            {'velocities': [0.45, 0.42, 0.40], 'load_kg': 100, 'reps': 3, 'rpe': 8.0, 'vl': 0.11},
            {'velocities': [0.40, 0.38], 'load_kg': 110, 'reps': 2, 'rpe': 8.5, 'vl': 0.05},
            {'velocities': [0.35], 'load_kg': 120, 'reps': 1, 'rpe': 9.0, 'vl': 0.0},
        ]
        
        result = target_heaviest_quality_set_perf_y(
            sets_data=sets_data,
            profile_a=0.55,
            profile_b=0.003,
            anchor_capacity=150,
            model_capacity=140
        )
        
        assert result.chosen_set_idx == 2
        assert result.target_source == "heaviest_quality_set_perf_y"
        assert "selected set 2 with load 120.0kg" in result.notes
        assert result.target_value is not None
    
    def test_heaviest_quality_skips_reps_over_6(self):
        """Sets with reps > 6 should be excluded."""
        sets_data = [
            {'velocities': [0.40], 'load_kg': 110, 'reps': 2, 'rpe': 8.0},
            {'velocities': [0.30], 'load_kg': 130, 'reps': 8, 'rpe': 9.0},  # Too many reps
        ]
        
        result = target_heaviest_quality_set_perf_y(
            sets_data=sets_data,
            profile_a=0.55,
            profile_b=0.003
        )
        
        assert result.chosen_set_idx == 0
    
    def test_heaviest_quality_checks_rpe_range(self):
        """Sets with RPE outside [7.0, 9.5] should be excluded."""
        sets_data = [
            {'velocities': [0.40], 'load_kg': 110, 'reps': 2, 'rpe': 6.0},  # RPE too low
            {'velocities': [0.35], 'load_kg': 120, 'reps': 2, 'rpe': 8.0},
        ]
        
        result = target_heaviest_quality_set_perf_y(
            sets_data=sets_data,
            profile_a=0.55,
            profile_b=0.003
        )
        
        assert result.chosen_set_idx == 1
    
    def test_heaviest_quality_checks_vl_threshold(self):
        """Sets with VL > 0.25 should be excluded."""
        sets_data = [
            {'velocities': [0.40], 'load_kg': 110, 'reps': 2, 'vl': 0.30},  # VL too high
            {'velocities': [0.35], 'load_kg': 100, 'reps': 2, 'vl': 0.10},
        ]
        
        result = target_heaviest_quality_set_perf_y(
            sets_data=sets_data,
            profile_a=0.55,
            profile_b=0.003
        )
        
        assert result.chosen_set_idx == 1


class TestFixedLoadFirstRepVelocity:
    """Test fixed-load target constructor."""
    
    def test_fixed_load_selects_nearest_probe_set(self):
        """With several candidate loads, it picks the closest to target zone."""
        sets_data = [
            {'velocities': [0.45], 'load_kg': 130, 'reps': 1},  # 93% of 140 (too high)
            {'velocities': [0.48], 'load_kg': 110, 'reps': 1},  # 79% of 140 (ideal, closest)
            {'velocities': [0.50], 'load_kg': 90, 'reps': 1},   # 64% of 140 (too low)
        ]
        
        result = target_fixed_load_first_rep_velocity(
            sets_data=sets_data,
            profile_a=0.55,
            profile_b=0.003,
            anchor_capacity=None,
            model_capacity=140,
            lift="squat"
        )
        
        # 79% is closest to 70-80% target zone (deviation = 0%)
        assert result.chosen_set_idx == 1
        assert result.target_source == "fixed_load_first_rep_velocity"
        assert 0.70 <= result.chosen_set_metadata['load_pct'] <= 0.80


class TestTargetReturnsNone:
    """Test that targets return None when no valid data exists."""
    
    def test_target_returns_none_if_no_valid_set(self):
        """No valid velocity/quality data -> returns None safely."""
        result = get_day_level_strength_target(
            sets_data=[],
            lift="squat",
            target_mode="heaviest_quality_set_perf_y",
            profile_a=0.55,
            profile_b=0.003
        )
        
        assert result.target_value is None
        assert "no sets data" in result.notes
    
    def test_target_returns_none_if_no_velocity_data(self):
        """Sets without velocity data -> returns None."""
        sets_data = [
            {'load_kg': 100, 'reps': 3},  # No velocities
        ]
        
        result = get_day_level_strength_target(
            sets_data=sets_data,
            lift="squat",
            target_mode="heaviest_quality_set_perf_y",
            profile_a=0.55,
            profile_b=0.003
        )
        
        assert result.target_value is None


class TestTargetScale:
    """Test that target scale is more plausible than legacy ratio."""
    
    def test_heaviest_quality_scale_more_plausible_than_legacy(self):
        """New target should be in more realistic range than rep2/rep1-style legacy ratio."""
        sets_data = [
            {'velocities': [0.45, 0.42], 'load_kg': 100, 'reps': 2, 'rpe': 8.0},
        ]
        
        legacy_result = get_day_level_strength_target(
            sets_data=sets_data,
            lift="squat",
            target_mode="legacy_ratio",
            profile_a=0.55,
            profile_b=0.003
        )
        
        new_result = get_day_level_strength_target(
            sets_data=sets_data,
            lift="squat",
            target_mode="heaviest_quality_set_perf_y",
            profile_a=0.55,
            profile_b=0.003
        )
        
        # Legacy is rep2/rep1 = 0.42/0.45 = 0.93
        # New is perf_y = v_obs / v_ref, typically 0.7-1.1
        assert legacy_result.target_value == pytest.approx(0.933, abs=0.01)
        assert new_result.target_value is not None
        # New target should be in expected mapping bounds [0.6, 1.1]
        assert 0.6 <= new_result.target_value <= 1.1


class TestAllTargetModes:
    """Test all supported target modes."""
    
    def test_all_target_modes_supported(self):
        """All target modes should work without errors."""
        sets_data = [
            {'velocities': [0.45, 0.42, 0.40], 'load_kg': 100, 'reps': 3, 'rpe': 8.0, 'vl': 0.11},
        ]
        
        modes = [
            "legacy_ratio",
            "heaviest_quality_set_perf_y",
            "fixed_load_first_rep_velocity",
            "quality_set_composite",
        ]
        
        for mode in modes:
            result = get_day_level_strength_target(
                sets_data=sets_data,
                lift="squat",
                target_mode=mode,
                profile_a=0.55,
                profile_b=0.003,
                anchor_capacity=150,
                model_capacity=140
            )
            
            assert isinstance(result, StrengthTargetResult)
            assert result.target_source == mode


class TestFixedLoadTarget:
    """Test fixed-load target returns perf_y within bounds."""
    
    def test_fixed_load_returns_perf_y_in_bounds(self):
        """Fixed-load target should return perf_y (not raw velocity) within mapping bounds."""
        sets_data = [
            {'velocities': [0.50], 'load_kg': 100, 'reps': 1},  # 71% of 140
        ]
        
        result = target_fixed_load_first_rep_velocity(
            sets_data=sets_data,
            profile_a=0.55,
            profile_b=0.003,
            anchor_capacity=None,
            model_capacity=140,
            lift="squat"
        )
        
        # Should return perf_y in [0.6, 1.1], not raw velocity (0.5)
        assert result.target_value is not None
        assert 0.6 <= result.target_value <= 1.1
        assert result.chosen_set_metadata is not None
        assert 'perf_y' in result.chosen_set_metadata


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
