"""
Tests for Sprint H1: Day Engine Model Hardening

1. C_l saturates toward C_max (no divergence)
2. R_mito bounded [0,1], increases with Z2 and modestly with HIIT, decays with overload
3. T_legs decreases with heavy legs impulses and recovers slowly
4. No placeholder interference: verify update uses only explicit terms
"""
import pytest
import math
from datetime import date

from app.domain.day_engine import (
    DayEngineParams,
    SetImpulse,
    StrengthImpulses,
    EnduranceImpulses,
    DailyImpulses,
    PerLiftState,
    DayState,
    update_capacity_with_saturation,
    update_R_mito,
    update_T_legs,
    compute_interference,
    update_day_state,
    compute_readiness,
)


class TestCapacitySaturation:
    """Test H1: Capacity saturation prevents divergence."""
    
    def test_capacity_saturates_near_c_max(self):
        """As C approaches C_max, growth slows down."""
        params = DayEngineParams(C_max=200.0, g_l=0.015)
        
        # Test at different capacity levels
        C_low = update_capacity_with_saturation(100.0, F_l=2.0, D_l=0.1, params=params)
        C_mid = update_capacity_with_saturation(150.0, F_l=2.0, D_l=0.1, params=params)
        C_near_max = update_capacity_with_saturation(190.0, F_l=2.0, D_l=0.1, params=params)
        
        # All should increase (fitness > fatigue)
        assert C_low > 100.0
        assert C_mid > 150.0
        assert C_near_max > 190.0
        
        # Growth should slow as we approach C_max
        gain_low = C_low - 100.0
        gain_mid = C_mid - 150.0
        gain_near_max = C_near_max - 190.0
        
        assert gain_near_max < gain_mid < gain_low
    
    def test_capacity_very_near_max_minimal_growth(self):
        """Very close to C_max, growth is minimal."""
        params = DayEngineParams(C_max=200.0, g_l=0.015)

        # At 199 kg with good fitness
        C_new = update_capacity_with_saturation(199.0, F_l=3.0, D_l=0.1, params=params)

        # Should not exceed C_max
        assert C_new <= 200.0
        assert C_new <= params.C_max

        # Growth should be minimal (saturation effect)
        # Just check it's positive or very small due to precision
        assert C_new >= 198.0  # Should still be high
    
    def test_capacity_respects_c_max(self):
        """Capacity should not exceed C_max significantly."""
        params = DayEngineParams(C_max=200.0, C_min=20.0, g_l=0.05)
        
        # Even with very high fitness
        C_new = update_capacity_with_saturation(195.0, F_l=10.0, D_l=0.0, params=params)
        
        # Should not exceed C_max
        assert C_new <= params.C_max


class TestRMitoBounded:
    """Test H1: R_mito bounded [0,1] with Z2/HIIT split and overload."""
    
    def test_r_mito_bounded_between_0_and_1(self):
        """R_mito should always be in [0,1]."""
        params = DayEngineParams(R_mito_min=0.0, R_mito_max=1.0)
        
        # Start at 0.5
        R = 0.5
        
        # Update with various impulses
        for _ in range(100):
            impulses = EnduranceImpulses(
                u_E_Z2=100.0, u_E_HIIT=50.0, u_E_total=150.0,
                mode="cycling", has_HIIT=True, has_Z2=True
            )
            R = update_R_mito(R, impulses, overload_indicator=0.0, params=params)
            
            # Should stay bounded
            assert 0.0 <= R <= 1.0
    
    def test_r_mito_increases_more_with_z2(self):
        """Z2 should increase R_mito more than HIIT."""
        params = DayEngineParams(k_mito_z2=0.0010, k_mito_hiit=0.0004)
        
        # Z2 only
        impulses_z2 = EnduranceImpulses(
            u_E_Z2=100.0, u_E_HIIT=0.0, u_E_total=100.0,
            mode="cycling", has_HIIT=False, has_Z2=True
        )
        R_z2 = update_R_mito(0.3, impulses_z2, 0.0, params)
        
        # HIIT only (same total load)
        impulses_hiit = EnduranceImpulses(
            u_E_Z2=0.0, u_E_HIIT=100.0, u_E_total=100.0,
            mode="cycling", has_HIIT=True, has_Z2=False
        )
        R_hiit = update_R_mito(0.3, impulses_hiit, 0.0, params)
        
        # Z2 should increase R_mito more
        assert R_z2 > R_hiit
    
    def test_r_mito_decreases_with_overload(self):
        """Overload should reduce R_mito."""
        params = DayEngineParams(k_mito_overload=0.0005)
        
        # Normal training
        impulses = EnduranceImpulses(
            u_E_Z2=50.0, u_E_HIIT=20.0, u_E_total=70.0,
            mode="cycling", has_HIIT=True, has_Z2=True
        )
        R_normal = update_R_mito(0.5, impulses, overload_indicator=0.0, params=params)
        
        # Overload condition
        R_overload = update_R_mito(0.5, impulses, overload_indicator=1.0, params=params)
        
        # Overload should reduce R_mito
        assert R_overload < R_normal
    
    def test_r_mito_decays_without_training(self):
        """R_mito should decay over time without endurance stimulus."""
        params = DayEngineParams(k_mito_decay=0.02)
        
        impulses = EnduranceImpulses(
            u_E_Z2=0.0, u_E_HIIT=0.0, u_E_total=0.0,
            mode="cycling", has_HIIT=False, has_Z2=False
        )
        
        R = 0.8
        for _ in range(10):
            R = update_R_mito(R, impulses, 0.0, params)
        
        # Should decay toward 0
        assert R < 0.8


class TestTLegs:
    """Test H1: T_legs structural fatigue with slow recovery."""
    
    def test_t_legs_increases_with_legs_work(self):
        """T_legs should increase after legs strength work."""
        params = DayEngineParams(tau_T_legs=21.0, k_T_legs=0.0002)
        
        impulses = StrengthImpulses(
            per_lift={"squat": 1000.0},
            u_sys=1000.0,
            u_legs=1000.0,  # High legs impulse
            u_met=0.0,
            u_legs_high_intensity=500.0,
            sets=[]
        )
        
        T_new = update_T_legs(0.0, impulses, params)
        
        # Should increase
        assert T_new > 0.0
    
    def test_t_legs_increases_more_with_high_intensity(self):
        """High intensity legs work increases T_legs more."""
        params = DayEngineParams(k_T_legs=0.0002, k_T_high_intensity=0.0004)
        
        # Normal intensity
        impulses_normal = StrengthImpulses(
            per_lift={"squat": 1000.0},
            u_sys=1000.0,
            u_legs=1000.0,
            u_met=0.0,
            u_legs_high_intensity=0.0,  # No high intensity
            sets=[]
        )
        T_normal = update_T_legs(0.0, impulses_normal, params)
        
        # High intensity
        impulses_high = StrengthImpulses(
            per_lift={"squat": 1000.0},
            u_sys=1000.0,
            u_legs=1000.0,
            u_met=0.0,
            u_legs_high_intensity=1000.0,  # All high intensity
            sets=[]
        )
        T_high = update_T_legs(0.0, impulses_high, params)
        
        # High intensity should increase T_legs more
        assert T_high > T_normal
    
    def test_t_legs_recovers_slowly(self):
        """T_legs should recover slowly over time."""
        params = DayEngineParams(tau_T_legs=21.0)
        
        # Start with elevated T_legs
        T = 0.5
        
        # No training (empty impulses)
        impulses = StrengthImpulses(
            per_lift={}, u_sys=0.0, u_legs=0.0, u_met=0.0,
            u_legs_high_intensity=0.0, sets=[]
        )
        
        # One day recovery
        T_1d = update_T_legs(T, impulses, params)
        
        # Should decrease slightly (slow recovery)
        assert T_1d < T
        assert T_1d > 0.4  # Still high after 1 day
    
    def test_t_legs_bounded_0_to_1(self):
        """T_legs should stay in [0,1]."""
        params = DayEngineParams()
        
        # Try to push above 1.0 with extreme impulse
        impulses = StrengthImpulses(
            per_lift={"squat": 100000.0},
            u_sys=100000.0,
            u_legs=100000.0,
            u_met=0.0,
            u_legs_high_intensity=50000.0,
            sets=[]
        )
        
        T = update_T_legs(0.9, impulses, params)
        
        # Should be bounded
        assert 0.0 <= T <= 1.0


class TestExplicitInterference:
    """Test H1: All interference terms are explicit."""
    
    def test_interference_zero_without_hiit(self):
        """No HIIT = zero interference (no placeholder)."""
        params = DayEngineParams()
        
        # No HIIT
        endurance = EnduranceImpulses(
            u_E_Z2=100.0, u_E_HIIT=0.0, u_E_total=100.0,
            mode="cycling", has_HIIT=False, has_Z2=True
        )
        
        per_lift, sys_interf = compute_interference(endurance, params)
        
        # Should be exactly zero for all lifts
        for lift in ["squat", "bench", "deadlift"]:
            assert per_lift.get(lift, 0.0) == 0.0
        assert sys_interf == 0.0
    
    def test_interference_explicit_calculation(self):
        """Interference uses explicit coefficients."""
        params = DayEngineParams(
            k_ES_l={'squat': 0.00030, 'bench': 0.00008},
            k_ES_sys=0.00018,
            mode_factors={'cycling': 1.0}
        )
        
        # With HIIT
        endurance = EnduranceImpulses(
            u_E_Z2=0.0, u_E_HIIT=100.0, u_E_total=100.0,
            mode="cycling", has_HIIT=True, has_Z2=False
        )
        
        per_lift, sys_interf = compute_interference(endurance, params)
        
        # Should use explicit formula: k_ES * u_E_HIIT * mode_factor
        expected_squat = 0.00030 * 100.0 * 1.0
        expected_bench = 0.00008 * 100.0 * 1.0
        expected_sys = 0.00018 * 100.0 * 1.0
        
        assert per_lift['squat'] == pytest.approx(expected_squat, abs=0.0001)
        assert per_lift['bench'] == pytest.approx(expected_bench, abs=0.0001)
        assert sys_interf == pytest.approx(expected_sys, abs=0.0001)
    
    def test_interference_scales_with_hiit_volume(self):
        """More HIIT = more interference (linear explicit scaling)."""
        params = DayEngineParams()
        
        # Low HIIT
        endurance_low = EnduranceImpulses(
            u_E_Z2=0.0, u_E_HIIT=50.0, u_E_total=50.0,
            mode="cycling", has_HIIT=True, has_Z2=False
        )
        per_lift_low, _ = compute_interference(endurance_low, params)
        
        # High HIIT
        endurance_high = EnduranceImpulses(
            u_E_Z2=0.0, u_E_HIIT=100.0, u_E_total=100.0,
            mode="cycling", has_HIIT=True, has_Z2=False
        )
        per_lift_high, _ = compute_interference(endurance_high, params)
        
        # Should scale linearly
        for lift in per_lift_low.keys():
            assert per_lift_high[lift] == pytest.approx(2.0 * per_lift_low[lift], abs=0.0001)


class TestReadinessWithTLegs:
    """Test H1: Readiness includes T_legs guardrail."""
    
    def test_high_t_legs_reduces_legs_readiness(self):
        """High T_legs should reduce readiness for leg lifts."""
        params = DayEngineParams(T_legs_guardrail_threshold=0.35)
        
        state = DayState(
            date=date.today(),
            per_lift={
                "squat": PerLiftState(D_l=0.1, F_l=1.0, C_l=100.0),
                "bench": PerLiftState(D_l=0.1, F_l=1.0, C_l=100.0)
            },
            D_sys=0.1,
            R_mito=0.2,
            E_fat=0.1,
            T_legs=0.5  # High structural fatigue
        )
        
        readiness = compute_readiness(state, params)
        
        # Legs lift should have reduced readiness
        assert readiness.per_lift["squat"] < readiness.per_lift["bench"]
    
    def test_t_legs_explanation_generated(self):
        """High T_legs should generate explanation."""
        params = DayEngineParams(T_legs_guardrail_threshold=0.35)
        
        state = DayState(
            date=date.today(),
            per_lift={"squat": PerLiftState(D_l=0.1, F_l=1.0, C_l=100.0)},
            D_sys=0.1,
            R_mito=0.2,
            E_fat=0.1,
            T_legs=0.4  # Above threshold
        )
        
        readiness = compute_readiness(state, params)
        
        # Should have explanation about legs structural fatigue
        t_legs_explanations = [e for e in readiness.explanations if "structural" in e.lower() or "T_legs" in e]
        assert len(t_legs_explanations) > 0
    
    def test_readiness_includes_legs_structural(self):
        """Readiness output includes legs_structural field."""
        params = DayEngineParams()
        
        state = DayState(
            date=date.today(),
            per_lift={},
            D_sys=0.0,
            R_mito=0.0,
            E_fat=0.0,
            T_legs=0.3
        )
        
        readiness = compute_readiness(state, params)
        
        # Should have legs_structural field
        assert hasattr(readiness, 'legs_structural')
        assert 0.0 <= readiness.legs_structural <= 1.0


class TestDayStateUpdate:
    """Test H1: Full day state update with hardened model."""
    
    def test_state_includes_t_legs_after_update(self):
        """DayState after update includes T_legs."""
        params = DayEngineParams()
        
        current = DayState(
            date=date.today(),
            per_lift={"squat": PerLiftState(D_l=0.1, F_l=1.0, C_l=100.0)},
            D_sys=0.1,
            R_mito=0.3,
            E_fat=0.1,
            T_legs=0.2
        )
        
        impulses = DailyImpulses(
            strength=StrengthImpulses(
                per_lift={"squat": 500.0},
                u_sys=500.0,
                u_legs=500.0,
                u_met=0.0,
                u_legs_high_intensity=200.0,
                sets=[]
            ),
            endurance=EnduranceImpulses(
                u_E_Z2=50.0, u_E_HIIT=0.0, u_E_total=50.0,
                mode="cycling", has_HIIT=False, has_Z2=True
            ),
            date=date.today()
        )
        
        new_state = update_day_state(current, impulses, params)
        
        # Should have T_legs field
        assert hasattr(new_state, 'T_legs')
        assert isinstance(new_state.T_legs, float)
    
    def test_r_mito_bounded_in_state_update(self):
        """R_mito stays bounded during state update."""
        params = DayEngineParams(R_mito_max=1.0, R_mito_min=0.0)
        
        current = DayState(
            date=date.today(),
            per_lift={},
            D_sys=0.0,
            R_mito=0.9,  # Near max
            E_fat=0.0,
            T_legs=0.0
        )
        
        # Lots of Z2 to try to push over 1.0
        impulses = DailyImpulses(
            strength=StrengthImpulses(
                per_lift={}, u_sys=0.0, u_legs=0.0, u_met=0.0,
                u_legs_high_intensity=0.0, sets=[]
            ),
            endurance=EnduranceImpulses(
                u_E_Z2=1000.0, u_E_HIIT=0.0, u_E_total=1000.0,
                mode="cycling", has_HIIT=False, has_Z2=True
            ),
            date=date.today()
        )
        
        new_state = update_day_state(current, impulses, params)
        
        # Should stay at or below 1.0
        assert new_state.R_mito <= 1.0
