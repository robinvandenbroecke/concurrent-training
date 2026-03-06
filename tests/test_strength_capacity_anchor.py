"""
Tests for Sprint E3 Refined: Strength Capacity Anchor + Breakthrough System
"""
import pytest
from datetime import datetime, timedelta

from app.types import LiftType
from app.services.capacity_service import (
    compute_e1rm_from_set,
    determine_confidence_from_set,
    initialize_lift_capacity,
    is_quality_strength_set,
    detect_breakthrough_v2,
    extract_strength_performance_signal,
    detect_provisional_breakthrough,
    detect_confirmed_breakthrough,
    apply_confirmed_breakthrough,
    update_model_capacity,
    get_breakthrough_threshold,
    CapacityInputType,
    CapacityConfidence,
    SignalType,
    LIFT_DEFAULT_CAPACITY,
    PROVISIONAL_WINDOW_DAYS,
    STRONG_SIGNAL_THRESHOLD_PCT,
    ANCHOR_UPDATE_ALPHA,
)


class TestE1RMComputation:
    """Test e1RM computation from sets"""
    
    def test_e1rm_without_rpe(self):
        """e1RM formula without RPE: load * (1 + reps/30)"""
        e1rm = compute_e1rm_from_set(100, 5)
        expected = 100 * (1 + 5/30)
        assert e1rm == pytest.approx(expected, rel=1e-3)
    
    def test_e1rm_with_rpe(self):
        """e1RM formula with RPE adjusts for reps in reserve"""
        # 100kg x 5 reps @ RPE 8 (2 reps in reserve -> 7 effective reps)
        e1rm = compute_e1rm_from_set(100, 5, rpe=8)
        expected = 100 * (1 + 7/30)
        assert e1rm == pytest.approx(expected, rel=1e-3)


class TestBreakthroughThresholds:
    """Test confidence-dependent breakthrough thresholds"""
    
    def test_high_confidence_threshold(self):
        """High confidence: 2.5% threshold"""
        assert get_breakthrough_threshold(CapacityConfidence.HIGH) == 2.5
    
    def test_medium_confidence_threshold(self):
        """Medium confidence: 2.0% threshold"""
        assert get_breakthrough_threshold(CapacityConfidence.MEDIUM) == 2.0
    
    def test_low_confidence_threshold(self):
        """Low confidence: 1.5% threshold"""
        assert get_breakthrough_threshold(CapacityConfidence.LOW) == 1.5


class TestQualitySetDetectionRefined:
    """Test refined quality set detection with lift-specific criteria"""
    
    def test_squat_quality_set(self):
        """Squat: reps <= 6, load >= 75%, RPE 7-9.5, VL <= 25%"""
        result = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=150,  # 75% of 200
            reps=5,
            rpe=8.0,
            velocity_loss=0.20,
            anchor_capacity=200
        )
        assert result.is_quality is True
        assert result.signal.signal_type == SignalType.E1RM
    
    def test_squat_too_many_reps(self):
        """Squat with > 6 reps fails quality"""
        result = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=150,
            reps=8,
            rpe=8.0,
            anchor_capacity=200
        )
        assert result.is_quality is False
        assert "too many reps" in result.reason.lower()
    
    def test_squat_load_too_light(self):
        """Squat with < 75% load fails quality"""
        result = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=140,  # 70% of 200
            reps=5,
            rpe=8.0,
            anchor_capacity=200
        )
        assert result.is_quality is False
        assert "load too light" in result.reason.lower()
    
    def test_squat_rpe_too_low(self):
        """Squat with RPE < 7 fails quality"""
        result = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=150,
            reps=5,
            rpe=6.5,
            anchor_capacity=200
        )
        assert result.is_quality is False
        assert "rpe out of range" in result.reason.lower()
    
    def test_squat_rpe_too_high(self):
        """Squat with RPE > 9.5 fails quality"""
        result = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=150,
            reps=5,
            rpe=10.0,
            anchor_capacity=200
        )
        assert result.is_quality is False
    
    def test_squat_velocity_loss_too_high(self):
        """Squat with VL > 25% fails quality"""
        result = is_quality_strength_set(
            lift=LiftType.SQUAT,
            load_kg=150,
            reps=5,
            rpe=8.0,
            velocity_loss=0.30,
            anchor_capacity=200
        )
        assert result.is_quality is False
        assert "velocity loss" in result.reason.lower()
    
    def test_power_clean_quality_set(self):
        """Power clean: reps <= 3, load >= 70%"""
        result = is_quality_strength_set(
            lift=LiftType.POWER_CLEAN,
            load_kg=70,  # 70% of 100
            reps=2,
            anchor_capacity=100
        )
        assert result.is_quality is True
        assert result.signal.signal_type == SignalType.CLEAN_LOAD
    
    def test_power_clean_too_many_reps(self):
        """Power clean with > 3 reps fails quality"""
        result = is_quality_strength_set(
            lift=LiftType.POWER_CLEAN,
            load_kg=70,
            reps=5,
            anchor_capacity=100
        )
        assert result.is_quality is False
        assert "too many reps" in result.reason.lower()
    
    def test_power_clean_load_too_light(self):
        """Power clean with < 70% load fails quality"""
        result = is_quality_strength_set(
            lift=LiftType.POWER_CLEAN,
            load_kg=60,  # 60% of 100
            reps=2,
            anchor_capacity=100
        )
        assert result.is_quality is False
    
    def test_power_clean_with_velocity(self):
        """Power clean uses velocity signal when available"""
        result = is_quality_strength_set(
            lift=LiftType.POWER_CLEAN,
            load_kg=70,
            reps=2,
            observed_velocity=1.2,
            anchor_capacity=100
        )
        assert result.is_quality is True
        assert result.signal.signal_type == SignalType.VELOCITY


class TestPerformanceSignalExtraction:
    """Test performance signal extraction"""
    
    def test_extract_signal_squat(self):
        """Extract e1RM signal from squat set"""
        signal = extract_strength_performance_signal(
            lift=LiftType.SQUAT,
            load_kg=150,
            reps=5,
            rpe=8.0,
            anchor_capacity=200
        )
        
        assert signal.quality_passed is True
        assert signal.signal_type == SignalType.E1RM
        assert signal.signal_value > 150  # e1RM > load
    
    def test_extract_signal_clean(self):
        """Extract velocity/load signal from clean"""
        signal = extract_strength_performance_signal(
            lift=LiftType.POWER_CLEAN,
            load_kg=70,
            reps=2,
            observed_velocity=1.2,
            anchor_capacity=100
        )
        
        assert signal.quality_passed is True
        assert signal.signal_type == SignalType.VELOCITY
        assert signal.signal_value == 1.2
    
    def test_extract_signal_not_quality(self):
        """Return failed signal for non-quality set"""
        signal = extract_strength_performance_signal(
            lift=LiftType.SQUAT,
            load_kg=100,  # Too light
            reps=5,
            rpe=8.0,
            anchor_capacity=200
        )
        
        assert signal.quality_passed is False
        assert signal.quality_score == 0.0


class TestProvisionalBreakthroughDetection:
    """Test provisional breakthrough detection"""
    
    def test_provisional_high_confidence(self):
        """High confidence: 2.5% threshold"""
        signal = extract_strength_performance_signal(
            lift=LiftType.SQUAT,
            load_kg=155,  # ~180 e1RM vs 150 anchor = 20% increase
            reps=5,
            rpe=8.0,
            anchor_capacity=150
        )
        
        is_provisional = detect_provisional_breakthrough(
            anchor_capacity=150,
            signal=signal,
            confidence=CapacityConfidence.HIGH
        )
        assert is_provisional is True
    
    def test_provisional_low_confidence_lower_threshold(self):
        """Low confidence: 1.5% threshold (easier)"""
        signal = extract_strength_performance_signal(
            lift=LiftType.SQUAT,
            load_kg=153,  # ~178 e1RM vs 150 anchor = 18.7% increase
            reps=5,
            rpe=8.0,
            anchor_capacity=150
        )
        
        is_provisional = detect_provisional_breakthrough(
            anchor_capacity=150,
            signal=signal,
            confidence=CapacityConfidence.LOW
        )
        assert is_provisional is True
    
    def test_not_provisional_below_threshold(self):
        """Signal below threshold is not provisional"""
        signal = extract_strength_performance_signal(
            lift=LiftType.SQUAT,
            load_kg=151,  # ~176 e1RM vs 150 anchor = 17.3% increase
            reps=5,
            rpe=8.0,
            anchor_capacity=150
        )
        
        # Even with low confidence (1.5% threshold), this should pass
        # Actually with e1RM formula, 151x5@8 = 151 * (1 + 7/30) = 151 * 1.233 = 186.2
        # So let's use a smaller increase
        
        signal2 = extract_strength_performance_signal(
            lift=LiftType.SQUAT,
            load_kg=140,  # ~172.7 e1RM vs 170 anchor = 1.6% increase (barely above low threshold)
            reps=5,
            rpe=8.0,
            anchor_capacity=170
        )
        
        is_provisional = detect_provisional_breakthrough(
            anchor_capacity=170,
            signal=signal2,
            confidence=CapacityConfidence.HIGH  # 2.5% threshold
        )
        assert is_provisional is False  # Below 2.5% threshold


class TestConfirmedBreakthroughDetection:
    """Test confirmed breakthrough detection"""
    
    def test_confirmed_strong_signal(self):
        """Signal >= 4% above anchor confirms immediately"""
        signal = extract_strength_performance_signal(
            lift=LiftType.SQUAT,
            load_kg=156,  # ~192.5 e1RM vs 150 anchor = 28.3% increase
            reps=5,
            rpe=8.0,
            anchor_capacity=150
        )
        
        is_confirmed = detect_confirmed_breakthrough(
            provisional_count=0,
            last_provisional_at=None,
            signal=signal,
            anchor_capacity=150
        )
        assert is_confirmed is True
    
    def test_confirmed_two_provisional_within_window(self):
        """Two provisional within 21 days confirms"""
        signal = extract_strength_performance_signal(
            lift=LiftType.SQUAT,
            load_kg=154,  # ~190 e1RM vs 150 anchor = 26.7% increase
            reps=5,
            rpe=8.0,
            anchor_capacity=150
        )
        
        recent_date = datetime.utcnow() - timedelta(days=5)
        
        is_confirmed = detect_confirmed_breakthrough(
            provisional_count=1,
            last_provisional_at=recent_date,
            signal=signal,
            anchor_capacity=150
        )
        assert is_confirmed is True
    
    def test_not_confirmed_outside_window(self):
        """Provisional outside 21-day window doesn't confirm"""
        # Use a signal that is above provisional threshold (2.5%) but below strong threshold (4%)
        # For 150 anchor: 2.5% = 153.75, 4% = 156. So signal ~154.5 (3% increase)
        signal = extract_strength_performance_signal(
            lift=LiftType.SQUAT,
            load_kg=142,  # ~175 e1RM vs 170 anchor = 2.9% (provisional but not strong)
            reps=5,
            rpe=8.0,
            anchor_capacity=170
        )

        old_date = datetime.utcnow() - timedelta(days=30)

        is_confirmed = detect_confirmed_breakthrough(
            provisional_count=1,
            last_provisional_at=old_date,
            signal=signal,
            anchor_capacity=170
        )
        assert is_confirmed is False  # Outside 21-day window, no confirmation


class TestPartialAnchorUpdate:
    """Test partial anchor update (alpha blending)"""
    
    def test_anchor_update_alpha_0_5(self):
        """Default alpha=0.5 moves anchor halfway to signal"""
        new_anchor = apply_confirmed_breakthrough(
            current_anchor=100,
            signal_value=110,
            alpha=0.5
        )
        
        # new_anchor = 100 + 0.5 * (110 - 100) = 105
        assert new_anchor == 105.0
    
    def test_anchor_update_alpha_0_3(self):
        """Alpha=0.3 moves anchor 30% toward signal"""
        new_anchor = apply_confirmed_breakthrough(
            current_anchor=100,
            signal_value=110,
            alpha=0.3
        )
        
        # new_anchor = 100 + 0.3 * (110 - 100) = 103
        assert new_anchor == 103.0


class TestModelCapacityUpdate:
    """Test model capacity blending"""
    
    def test_model_blend_with_signal(self):
        """Model = 0.7*anchor + 0.3*signal (default blend)"""
        model = update_model_capacity(
            anchor_capacity=100,
            smoothed_recent_signal=110,
            blend_weight=0.3
        )
        
        # model = 0.7 * 100 + 0.3 * 110 = 70 + 33 = 103
        assert model == 103.0
    
    def test_model_without_signal(self):
        """Model equals anchor when no signal"""
        model = update_model_capacity(
            anchor_capacity=100,
            smoothed_recent_signal=None
        )
        
        assert model == 100.0


class TestBreakthroughDetectionV2:
    """Test refined breakthrough detection"""
    
    def test_confirmed_strong_signal_v2(self):
        """Strong signal >= 4% confirms immediately"""
        signal = extract_strength_performance_signal(
            lift=LiftType.SQUAT,
            load_kg=156,
            reps=5,
            rpe=8.0,
            anchor_capacity=150
        )
        
        result = detect_breakthrough_v2(
            anchor_capacity=150,
            model_capacity=150,
            signal=signal,
            confidence=CapacityConfidence.HIGH,
            provisional_count=0,
            last_provisional_at=None
        )
        
        assert result.is_confirmed_breakthrough is True
        assert result.new_anchor_capacity is not None
        assert result.new_model_capacity is not None
    
    def test_provisional_then_confirmed(self):
        """First signal provisional, second confirms"""
        # Use signal that is provisional (>=2.5%) but not strong (<4%)
        # For 200 anchor: 2.5% = 205, 4% = 208. So ~206 is perfect
        signal = extract_strength_performance_signal(
            lift=LiftType.SQUAT,
            load_kg=167,  # ~206 e1RM vs 200 anchor = 3% (provisional but not strong)
            reps=5,
            rpe=8.0,
            anchor_capacity=200
        )

        # First signal - provisional only
        result1 = detect_breakthrough_v2(
            anchor_capacity=200,
            model_capacity=200,
            signal=signal,
            confidence=CapacityConfidence.HIGH,
            provisional_count=0,
            last_provisional_at=None
        )

        assert result1.is_provisional_breakthrough is True
        assert result1.is_confirmed_breakthrough is False

        # Second signal (within window) - should now confirm
        recent_date = datetime.utcnow() - timedelta(days=3)
        result2 = detect_breakthrough_v2(
            anchor_capacity=200,
            model_capacity=result1.new_model_capacity,
            signal=signal,
            confidence=CapacityConfidence.HIGH,
            provisional_count=1,
            last_provisional_at=recent_date
        )

        assert result2.is_confirmed_breakthrough is True
    
    def test_no_breakthrough_signal_below_threshold(self):
        """Signal below threshold doesn't trigger breakthrough"""
        signal = extract_strength_performance_signal(
            lift=LiftType.SQUAT,
            load_kg=140,
            reps=5,
            rpe=8.0,
            anchor_capacity=200  # Only 70% of anchor
        )
        
        # Actually this won't be quality because load < 75% of anchor
        # Let's create a signal that is quality but below breakthrough threshold
        signal2 = extract_strength_performance_signal(
            lift=LiftType.SQUAT,
            load_kg=152,  # 76% of 200, e1RM ~187.5 = -6.25% from anchor
            reps=5,
            rpe=8.0,
            anchor_capacity=200
        )
        
        result = detect_breakthrough_v2(
            anchor_capacity=200,
            model_capacity=200,
            signal=signal2,
            confidence=CapacityConfidence.HIGH,
            provisional_count=0,
            last_provisional_at=None
        )
        
        assert result.is_provisional_breakthrough is False
        assert result.is_confirmed_breakthrough is False


class TestInitialization:
    """Test capacity initialization"""
    
    def test_init_from_1rm(self):
        """Initialize from 1RM"""
        result = initialize_lift_capacity(
            lift=LiftType.SQUAT,
            input_type=CapacityInputType.ONE_RM,
            input_load_kg=150
        )
        
        assert result.anchor_capacity == 150
        assert result.model_capacity == 150
        assert result.confidence == CapacityConfidence.HIGH
    
    def test_init_from_best_set(self):
        """Initialize from best set computes e1RM"""
        result = initialize_lift_capacity(
            lift=LiftType.BENCH,
            input_type=CapacityInputType.BEST_SET,
            input_load_kg=100,
            input_reps=5,
            input_rpe=8
        )
        
        expected_e1rm = 100 * (1 + 7/30)  # With RPE 8 adjustment
        assert result.anchor_capacity == pytest.approx(expected_e1rm, rel=1e-3)
        assert result.confidence == CapacityConfidence.HIGH  # 5 reps, RPE 8
    
    def test_init_unknown(self):
        """Initialize unknown uses defaults"""
        result = initialize_lift_capacity(
            lift=LiftType.SQUAT,
            input_type=CapacityInputType.UNKNOWN
        )
        
        assert result.anchor_capacity == LIFT_DEFAULT_CAPACITY[LiftType.SQUAT]
        assert result.confidence == CapacityConfidence.LOW
