"""
Tests for LiftVelocityProfile validation and calibration.
"""
import pytest
from app.domain.rep_engine import LiftVelocityProfile


class TestProfileSignAndScale:
    """Test that profile parameters are correctly validated."""
    
    def test_profile_b_must_be_positive(self):
        """b must be > 0 so v_ref decreases with higher load."""
        with pytest.raises(ValueError, match="b must be > 0"):
            LiftVelocityProfile(lift="squat", a=0.55, b=-0.003)
        
        with pytest.raises(ValueError, match="b must be > 0"):
            LiftVelocityProfile(lift="squat", a=0.55, b=0)
    
    def test_profile_b_positive_decreases_with_load(self):
        """With b > 0, v_ref should decrease as load increases."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        
        v_at_0kg = profile.v_ref(0)
        v_at_50kg = profile.v_ref(50)
        v_at_100kg = profile.v_ref(100)
        v_at_200kg = profile.v_ref(200)
        
        assert v_at_0kg > v_at_50kg > v_at_100kg > v_at_200kg
        assert v_at_0kg == 0.55  # Unclamped at 0kg
    
    def test_profile_a_must_be_positive(self):
        """a must be > 0 for realistic velocity intercept."""
        with pytest.raises(ValueError, match="a must be > 0"):
            LiftVelocityProfile(lift="squat", a=0, b=0.003)
        
        with pytest.raises(ValueError, match="a must be > 0"):
            LiftVelocityProfile(lift="squat", a=-0.5, b=0.003)


class TestProfileRange:
    """Test that v_ref stays within realistic bounds."""
    
    def test_v_ref_at_50kg_stays_under_2ms(self):
        """v_ref at 50kg should be <= 2.0 m/s."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        v = profile.v_ref(50)
        assert v <= 2.0, f"v_ref at 50kg should be <= 2.0 m/s, got {v}"
        assert v > 0.05, f"v_ref at 50kg should be > 0.05 m/s, got {v}"
    
    def test_v_ref_at_200kg_stays_under_2ms(self):
        """v_ref at 200kg should be <= 2.0 m/s (clamped if needed)."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        v = profile.v_ref(200)
        assert v <= 2.0, f"v_ref at 200kg should be <= 2.0 m/s, got {v}"
        # At 200kg with these params: 0.55 - 0.0032*200 = 0.55 - 0.64 = -0.09
        # Should be clamped to v_min=0.05
        assert v >= 0.05, f"v_ref at 200kg should be >= 0.05 m/s, got {v}"
    
    def test_v_ref_clamped_to_v_max(self):
        """v_ref should never exceed v_max (2.0 m/s)."""
        # Create profile with high intercept
        profile = LiftVelocityProfile(lift="custom", a=2.5, b=0.001, v_max=2.0)
        v = profile.v_ref(0)
        assert v == 2.0, f"v_ref should be clamped to v_max=2.0, got {v}"
    
    def test_v_ref_clamped_to_v_min(self):
        """v_ref should never go below v_min (0.05 m/s)."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        v = profile.v_ref(1000)  # Very high load
        assert v == 0.05, f"v_ref should be clamped to v_min=0.05, got {v}"


class TestCalibratedProfile:
    """Test the calibrated_profile factory method."""
    
    def test_squat_default_profile(self):
        """Squat should have realistic default values."""
        profile = LiftVelocityProfile.calibrated_profile("squat")
        assert profile.a == 0.55
        assert profile.b == 0.0032
        assert profile.lift == "squat"
    
    def test_bench_default_profile(self):
        """Bench should have realistic default values."""
        profile = LiftVelocityProfile.calibrated_profile("bench")
        assert profile.a == 0.60
        assert profile.b == 0.0028
    
    def test_deadlift_default_profile(self):
        """Deadlift should have realistic default values."""
        profile = LiftVelocityProfile.calibrated_profile("deadlift")
        assert profile.a == 0.50
        assert profile.b == 0.0030
    
    def test_unknown_lift_uses_sensible_defaults(self):
        """Unknown lifts should get sensible defaults."""
        profile = LiftVelocityProfile.calibrated_profile("unknown_lift")
        assert profile.b > 0
        assert profile.a > 0
        # Should not raise
        v = profile.v_ref(100)
        assert 0.05 <= v <= 2.0


class TestProfileValidationInEval:
    """Test that eval doesn't produce exploding predictions."""
    
    def test_eval_no_exploding_pred(self):
        """Run a small synthetic set; v_pred must be within [0.05, 2.0] m/s."""
        from app.domain.rep_engine import simulate_strength_session, SessionInput, SetInput, RepEngineParams
        
        profile = LiftVelocityProfile.calibrated_profile("squat")
        
        session = SessionInput(
            sets=[
                SetInput(
                    lift="squat",
                    load_kg=100,
                    velocities=[0.60, 0.58, 0.55, 0.52, 0.50],
                    rest_before_sec=None
                )
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=1.0,
            params=RepEngineParams()
        )
        
        result = simulate_strength_session(session)
        
        # Check all predicted velocities are in valid range
        for set_result in result.sets:
            for rep_result in set_result.reps:
                v_pred = rep_result.v_pred_next
                assert 0.05 <= v_pred <= 2.0, \
                    f"v_pred {v_pred} m/s out of range [0.05, 2.0]"
    
    def test_invalid_profile_is_sanitized(self):
        """Test that negative b is properly sanitized."""
        # This simulates loading a bad profile from DB
        a_val = 0.7
        b_val = -0.15  # Invalid!
        
        # Sanitize
        if b_val <= 0:
            b_val = abs(b_val) if b_val != 0 else 0.003
        if a_val <= 0:
            a_val = 0.55
        
        # Should now work without error
        profile = LiftVelocityProfile(lift="squat", a=a_val, b=b_val)
        v = profile.v_ref(100)
        assert 0.05 <= v <= 2.0, f"Sanitized profile produced v={v}"
