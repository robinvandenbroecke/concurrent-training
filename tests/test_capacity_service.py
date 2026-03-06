"""
Tests for Sprint E3: Strength Capacity Anchor + Breakthrough System
"""
import pytest
from datetime import datetime

from app.types import LiftType
from app.services.capacity_service import (
    compute_e1rm_from_set,
    determine_confidence_from_set,
    initialize_lift_capacity,
    is_quality_strength_set,
    detect_breakthrough,
    CapacityInputType,
    CapacityConfidence,
    LIFT_DEFAULT_CAPACITY,
    get_default_capacity,
)


class TestE1RMComputation:
    """Test e1RM computation from sets"""
    
    def test_e1rm_without_rpe(self):
        """e1RM formula without RPE: load * (1 + reps/30)"""
        # 100kg x 5 reps
        e1rm = compute_e1rm_from_set(100, 5)
        expected = 100 * (1 + 5/30)  # 116.67
        assert e1rm == pytest.approx(expected, rel=1e-3)
        
        # 120kg x 1 rep
        e1rm = compute_e1rm_from_set(120, 1)
        expected = 120 * (1 + 1/30)  # 124
        assert e1rm == pytest.approx(expected, rel=1e-3)
    
    def test_e1rm_caps_reps_at_10(self):
        """e1RM formula caps reps at 10"""
        e1rm_10 = compute_e1rm_from_set(100, 10)
        e1rm_15 = compute_e1rm_from_set(100, 15)  # Should use 10
        assert e1rm_10 == e1rm_15
    
    def test_e1rm_with_rpe(self):
        """e1RM formula with RPE adjusts for reps in reserve"""
        # 100kg x 5 reps @ RPE 8 (2 reps in reserve)
        e1rm = compute_e1rm_from_set(100, 5, rpe=8)
        # Adjusted reps = 5 + (10-8) = 7
        expected = 100 * (1 + 7/30)
        assert e1rm == pytest.approx(expected, rel=1e-3)
        
        # RPE 10 = max effort (no adjustment)
        e1rm_max = compute_e1rm_from_set(100, 5, rpe=10)
        expected_max = 100 * (1 + 5/30)
        assert e1rm_max == pytest.approx(expected_max, rel=1e-3)
    
    def test_e1rm_rpe_caps_at_12(self):
        """e1RM with RPE caps adjusted reps at 12"""
        # High reps + high RPE could exceed 12, should cap
        e1rm = compute_e1rm_from_set(100, 10, rpe=6)  # 10 + 4 = 14, capped to 12
        expected = 100 * (1 + 12/30)
        assert e1rm == pytest.approx(expected, rel=1e-3)


class TestConfidenceDetermination:
    """Test confidence level determination"""
    
    def test_high_confidence_low_reps_high_rpe(self):
        """Reps <= 5 AND RPE >= 8 = HIGH confidence"""
        assert determine_confidence_from_set(5, 8) == CapacityConfidence.HIGH
        assert determine_confidence_from_set(3, 9) == CapacityConfidence.HIGH
        assert determine_confidence_from_set(5, 10) == CapacityConfidence.HIGH
    
    def test_medium_confidence_reps_6_to_8(self):
        """Reps <= 8 = MEDIUM confidence"""
        assert determine_confidence_from_set(6, 7) == CapacityConfidence.MEDIUM
        assert determine_confidence_from_set(8, 10) == CapacityConfidence.MEDIUM
    
    def test_medium_confidence_low_reps_low_rpe(self):
        """Reps <= 5 but RPE < 8 = MEDIUM confidence"""
        assert determine_confidence_from_set(5, 7) == CapacityConfidence.MEDIUM
        assert determine_confidence_from_set(3, 6) == CapacityConfidence.MEDIUM
    
    def test_low_confidence_high_reps(self):
        """Reps > 8 = LOW confidence"""
        assert determine_confidence_from_set(9, 10) == CapacityConfidence.LOW
        assert determine_confidence_from_set(12, 10) == CapacityConfidence.LOW
    
    def test_confidence_without_rpe(self):
        """Without RPE, rep count determines confidence"""
        # Without RPE, reps <= 5 but no RPE check means MEDIUM
        assert determine_confidence_from_set(5, None) == CapacityConfidence.MEDIUM
        assert determine_confidence_from_set(8, None) == CapacityConfidence.MEDIUM
        assert determine_confidence_from_set(10, None) == CapacityConfidence.LOW


class TestCapacityInitialization:
    """Test capacity initialization from user input"""
    
    def test_init_from_1rm(self):
        """Initialize from 1RM input"""
        result = initialize_lift_capacity(
            lift=LiftType.SQUAT,
            input_type=CapacityInputType.ONE_RM,
            input_load_kg=150
        )
        
        assert result.anchor_capacity == 150
        assert result.model_capacity == 150
        assert result.confidence == CapacityConfidence.HIGH
        assert result.input_type == CapacityInputType.ONE_RM
    
    def test_init_from_1rm_requires_load(self):
        """1RM input requires load"""
        with pytest.raises(ValueError, match="input_load_kg required"):
            initialize_lift_capacity(
                lift=LiftType.SQUAT,
                input_type=CapacityInputType.ONE_RM
            )
    
    def test_init_from_best_set_no_rpe(self):
        """Initialize from best set without RPE"""
        result = initialize_lift_capacity(
            lift=LiftType.BENCH,
            input_type=CapacityInputType.BEST_SET,
            input_load_kg=100,
            input_reps=5
        )

        expected_e1rm = 100 * (1 + 5/30)  # 116.67
        assert result.anchor_capacity == pytest.approx(expected_e1rm)
        assert result.model_capacity == pytest.approx(expected_e1rm)
        assert result.confidence == CapacityConfidence.MEDIUM  # 5 reps but no RPE = MEDIUM
    
    def test_init_from_best_set_with_rpe(self):
        """Initialize from best set with RPE"""
        result = initialize_lift_capacity(
            lift=LiftType.DEADLIFT,
            input_type=CapacityInputType.BEST_SET,
            input_load_kg=140,
            input_reps=5,
            input_rpe=9
        )
        
        # 5 reps @ RPE 9 = HIGH confidence
        assert result.confidence == CapacityConfidence.HIGH
    
    def test_init_from_best_set_requires_params(self):
        """Best set input requires load and reps"""
        with pytest.raises(ValueError, match="input_load_kg and input_reps required"):
            initialize_lift_capacity(
                lift=LiftType.SQUAT,
                input_type=CapacityInputType.BEST_SET,
                input_load_kg=100
            )
        
        with pytest.raises(ValueError, match="input_load_kg and input_reps required"):
            initialize_lift_capacity(
                lift=LiftType.SQUAT,
                input_type=CapacityInputType.BEST_SET,
                input_reps=5
            )
    
    def test_init_from_unknown(self):
        """Initialize from unknown uses defaults"""
        result = initialize_lift_capacity(
            lift=LiftType.SQUAT,
            input_type=CapacityInputType.UNKNOWN
        )
        
        assert result.anchor_capacity == LIFT_DEFAULT_CAPACITY[LiftType.SQUAT]
        assert result.model_capacity == LIFT_DEFAULT_CAPACITY[LiftType.SQUAT]
        assert result.confidence == CapacityConfidence.LOW
    
    def test_init_unknown_uses_lift_specific_defaults(self):
        """Unknown input uses lift-specific defaults"""
        lifts_to_test = [
            (LiftType.SQUAT, 100.0),
            (LiftType.BENCH, 70.0),
            (LiftType.DEADLIFT, 120.0),
            (LiftType.PRESS, 45.0),
            (LiftType.POWER_CLEAN, 60.0),
        ]
        
        for lift, expected in lifts_to_test:
            result = initialize_lift_capacity(
                lift=lift,
                input_type=CapacityInputType.UNKNOWN
            )
            assert result.anchor_capacity == expected, f"Wrong default for {lift}"
    
    def test_unknown_lift_uses_generic_default(self):
        """Unknown lift type uses generic default"""
        result = initialize_lift_capacity(
            lift=LiftType.OTHER,
            input_type=CapacityInputType.UNKNOWN
        )
        assert result.anchor_capacity == 80.0


class TestQualitySetDetection:
    """Test quality set detection"""
    
    def test_quality_set_basic(self):
        """Basic quality set detection"""
        result = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=150,  # 150/200 = 75%
            reps=5,
            rpe=8,
            velocity_loss=0.20,
            anchor_capacity=200
        )

        assert result.is_quality is True
        assert result.signal.signal_value is not None
        assert result.quality_score > 0
    
    def test_load_too_light_not_quality(self):
        """Load below 75% of anchor is not quality"""
        result = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=100,  # 100/200 = 50% < 75%
            reps=5,
            rpe=8,
            velocity_loss=0.20,
            anchor_capacity=200
        )

        assert result.is_quality is False
        assert "too light" in result.reason.lower()

    def test_too_many_reps_not_quality(self):
        """More than 6 reps is not quality for standard lifts"""
        result = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=150,  # 75%
            reps=8,  # > 6
            rpe=8,
            velocity_loss=0.20,
            anchor_capacity=200
        )

        assert result.is_quality is False
        assert "too many reps" in result.reason.lower()

    def test_high_velocity_loss_not_quality(self):
        """Velocity loss > 25% is not quality"""
        result = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=150,  # 75%
            reps=5,
            rpe=8,
            velocity_loss=0.30,  # > 25%
            anchor_capacity=200
        )

        assert result.is_quality is False
        assert "velocity loss" in result.reason.lower()

    def test_low_rpe_not_quality(self):
        """RPE < 7 is not quality (insufficient effort)"""
        result = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=150,  # 75%
            reps=5,
            rpe=6,
            velocity_loss=0.20,
            anchor_capacity=200
        )

        assert result.is_quality is False
        assert "rpe" in result.reason.lower()

    def test_invalid_anchor_not_quality(self):
        """Invalid anchor capacity returns not quality"""
        result = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=150,
            reps=5,
            rpe=8,
            velocity_loss=0.20,
            anchor_capacity=0
        )

        assert result.is_quality is False
        assert "invalid" in result.reason.lower()

    def test_quality_score_components(self):
        """Quality score considers multiple factors"""
        # High relative load, low VL, high RPE = high score
        result_high = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=180,  # 90%
            reps=3,
            rpe=9,
            velocity_loss=0.10,
            anchor_capacity=200
        )

        # Lower relative load = lower score
        result_lower = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=150,  # 75%
            reps=5,
            rpe=8,
            velocity_loss=0.20,
            anchor_capacity=200
        )

        assert result_high.quality_score > result_lower.quality_score

    def test_optional_params(self):
        """RPE and velocity loss are optional"""
        result = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=150,  # 75%
            reps=5,
            rpe=None,
            velocity_loss=None,
            anchor_capacity=200
        )
        
        assert result.is_quality is True


class TestBreakthroughDetection:
    """Test breakthrough detection"""
    
    def test_no_breakthrough_within_threshold(self):
        """Signal within 2.5% of anchor = no breakthrough"""
        result = detect_breakthrough(
            current_anchor=100,
            current_model=100,
            signal_e1rm=102,  # 2% increase
            provisional_count=0
        )
        
        assert result.is_provisional_breakthrough is False
        assert result.is_confirmed_breakthrough is False
        assert result.new_model_capacity is not None
        assert result.new_anchor_capacity is None
    
    def test_provisional_breakthrough(self):
        """Signal > 2.5% above anchor = provisional breakthrough"""
        result = detect_breakthrough(
            current_anchor=100,
            current_model=100,
            signal_e1rm=105,  # 5% increase
            provisional_count=0
        )
        
        assert result.is_provisional_breakthrough is True
        assert result.is_confirmed_breakthrough is False
        assert result.new_model_capacity is not None
        assert result.new_anchor_capacity is None
        assert result.signal_delta_pct == pytest.approx(5.0, rel=1e-3)
    
    def test_confirmed_breakthrough_after_multiple_signals(self):
        """2 provisional signals = confirmed breakthrough"""
        result = detect_breakthrough(
            current_anchor=100,
            current_model=102,
            signal_e1rm=105,  # 5% increase
            provisional_count=1  # Already had 1 provisional
        )
        
        assert result.is_provisional_breakthrough is True
        assert result.is_confirmed_breakthrough is True
        assert result.new_anchor_capacity == 105  # Anchor updated
        assert result.new_model_capacity == 105  # Model reset to anchor
    
    def test_model_drifts_toward_signal(self):
        """Model capacity drifts toward signal (30% rate)"""
        result = detect_breakthrough(
            current_anchor=100,
            current_model=100,
            signal_e1rm=110,  # 10% signal
            provisional_count=0
        )
        
        # Model should move 30% toward signal: 100 + 0.3*(110-100) = 103
        expected_model = 100 + (110 - 100) * 0.3
        assert result.new_model_capacity == pytest.approx(expected_model)
    
    def test_invalid_anchor_returns_error(self):
        """Invalid anchor returns error result"""
        result = detect_breakthrough(
            current_anchor=0,
            current_model=100,
            signal_e1rm=105,
            provisional_count=0
        )
        
        assert result.is_provisional_breakthrough is False
        assert result.is_confirmed_breakthrough is False
        assert "invalid" in result.reason.lower()
    
    def test_provisional_count_increments(self):
        """Provisional count tracking"""
        result = detect_breakthrough(
            current_anchor=100,
            current_model=100,
            signal_e1rm=105,
            provisional_count=0
        )
        
        # Reason should indicate this is provisional
        assert "provisional" in result.reason.lower()
        assert "1/2" in result.reason  # First of two needed
    
    def test_signal_below_anchor_resets_provisional(self):
        """Signal below anchor resets provisional count"""
        result = detect_breakthrough(
            current_anchor=100,
            current_model=100,
            signal_e1rm=95,  # Below anchor
            provisional_count=1
        )
        
        # No breakthrough, but model drifts down
        assert result.is_provisional_breakthrough is False
        assert result.signal_delta_pct == pytest.approx(-5.0, rel=1e-3)


class TestDefaultCapacity:
    """Test default capacity lookup"""
    
    def test_default_capacities(self):
        """Default capacities for each lift type"""
        assert get_default_capacity(LiftType.SQUAT) == 100.0
        assert get_default_capacity(LiftType.BENCH) == 70.0
        assert get_default_capacity(LiftType.DEADLIFT) == 120.0
        assert get_default_capacity(LiftType.PRESS) == 45.0
        assert get_default_capacity(LiftType.POWER_CLEAN) == 60.0
        assert get_default_capacity(LiftType.CLEAN) == 60.0
        assert get_default_capacity(LiftType.OTHER) == 80.0
