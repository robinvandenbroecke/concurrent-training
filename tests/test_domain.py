"""Test suite for concurrent training model"""
import pytest
from datetime import datetime, date
import math

from app.domain.model import (
    ConcurrentTrainingModel, Autoregulator, LiftProfile, LiftType,
    DayLevelState, RepLevelState, SystemParameters, EnduranceSport
)


class TestLiftProfile:
    """Test load-velocity profile"""
    
    def test_v_ref_calculation(self):
        profile = LiftProfile(LiftType.SQUAT, a=0.5, b=0.003)
        v = profile.v_ref(100)
        assert v == pytest.approx(0.2, abs=0.01)
    
    def test_v_ref_floor(self):
        profile = LiftProfile(LiftType.SQUAT, a=0.5, b=0.003)
        v = profile.v_ref(200)  # Would be negative
        assert v == 0.1  # Floor value
    
    def test_1rm_estimate(self):
        profile = LiftProfile(LiftType.SQUAT, a=0.5, b=0.003)
        # At v=0.2, weight=100, 1RM should be higher
        est_1rm = profile.estimate_1rm(100, 0.2)
        assert est_1rm > 100


class TestRepLevelState:
    """Test rep-level fatigue state"""
    
    def test_initial_state(self):
        state = RepLevelState()
        assert state.A_l == 1.0
        assert state.A_sys == 1.0
        assert state.M == 0.0
    
    def test_velocity_prediction_no_fatigue(self):
        state = RepLevelState()  # No fatigue
        v_pred = state.predict_velocity(v_ref=0.5, kM=0.5)
        assert v_pred == pytest.approx(0.5, abs=0.001)
    
    def test_velocity_prediction_with_fatigue(self):
        # Some fatigue
        state = RepLevelState(x_l=-0.1, x_sys=-0.05, M=0.5)
        v_pred = state.predict_velocity(v_ref=0.5, kM=0.5)
        # Should be lower than v_ref
        assert v_pred < 0.5
        assert v_pred > 0


class TestConcurrentTrainingModel:
    """Test core model equations"""
    
    def test_phi_calculation(self):
        model = ConcurrentTrainingModel()
        phi = model.compute_phi(intensity=0.8, v_ratio=1.2)
        assert phi > 0
        # Higher intensity should give higher phi
        phi_low = model.compute_phi(intensity=0.5, v_ratio=1.0)
        assert phi > phi_low
    
    def test_chi_calculation(self):
        model = ConcurrentTrainingModel()
        chi = model.compute_chi(rep_num=5, rest_before=30)
        assert chi > 0
        # More reps = higher chi
        chi_more = model.compute_chi(rep_num=10, rest_before=30)
        assert chi_more > chi
    
    def test_rep_update_reduces_availability(self):
        model = ConcurrentTrainingModel()
        state = RepLevelState()
        
        new_state = model.update_rep_level(
            state,
            weight=100,
            v_obs=0.35,
            v_ref=0.45,
            rep_num=3,
            rest_before=3
        )
        
        # Fatigue should reduce availability
        assert new_state.A_l < state.A_l
        assert new_state.A_sys < state.A_sys
        assert new_state.M > state.M
    
    def test_recovery_increases_availability(self):
        model = ConcurrentTrainingModel()
        # Moderate fatigue, lower metabolic load for realistic recovery
        tired_state = RepLevelState(x_l=-0.5, x_sys=-0.3, M=0.3)
        
        recovered = model.recover_during_rest(
            tired_state,
            delta_t=300,  # 5 min rest
            R_mito=0.5
        )
        
        # Should recover availability and clear metabolic load
        assert recovered.A_l > tired_state.A_l
        assert recovered.A_sys > tired_state.A_sys
        assert recovered.M < tired_state.M
    
    def test_day_state_update(self):
        model = ConcurrentTrainingModel()
        current = DayLevelState(date="2024-01-01")
        
        strength_impulses = {lift: 1000.0 for lift in LiftType}
        
        new_state = model.update_day_state(
            current,
            strength_impulses,
            u_E_Z2=60,
            u_E_HIIT=0,
            u_E_total=60,
            interference_factors={lift: 0 for lift in LiftType}
        )
        
        # Fatigue should accumulate
        assert new_state.D_sys > current.D_sys
        assert new_state.R_mito > current.R_mito  # From Z2
    
    def test_interference_factor_running(self):
        model = ConcurrentTrainingModel()
        interf = model.compute_interference_factor(
            EnduranceSport.RUNNING,
            hours_before_strength=12
        )
        # Running, close to strength = high interference
        assert interf > 1.0
    
    def test_interference_factor_swimming(self):
        model = ConcurrentTrainingModel()
        interf = model.compute_interference_factor(
            EnduranceSport.SWIMMING,
            hours_before_strength=48
        )
        # Swimming, far from strength = low interference
        assert interf < 0.5


class TestAutoregulator:
    """Test autoregulation logic"""
    
    def test_stop_on_high_vl(self):
        model = ConcurrentTrainingModel()
        autoreg = Autoregulator(model)
        
        # Very fatigued state
        state = RepLevelState(x_l=-0.8, x_sys=-0.5, M=2.0)
        
        action = autoreg.suggest_action(
            state,
            target_v_low=0.35,
            target_v_high=0.45,
            vl_max=15.0,
            v_ref=0.5,
            current_reps_done=3,
            planned_reps=5,
            current_weight=100
        )
        
        assert action["continue"] is False
        assert any("loss" in msg.lower() for msg in action["message"])
    
    def test_load_increase_on_good_performance(self):
        model = ConcurrentTrainingModel()
        autoreg = Autoregulator(model)
        
        # Near-perfect state - very high predicted velocity
        # x_l = -0.02 gives A_l ~ 0.98, x_sys = 0 gives A_sys = 1.0
        state = RepLevelState(x_l=-0.02, x_sys=0.0, M=0.0)
        
        action = autoreg.suggest_action(
            state,
            target_v_low=0.35,
            target_v_high=0.45,
            vl_max=20.0,
            v_ref=0.5,  # With A_l=0.98, A_sys=1.0, v_pred ~ 0.49
            current_reps_done=0,
            planned_reps=5,
            current_weight=100
        )
        
        # With v_pred ~ 0.49 > target_v_high (0.45), should suggest load increase
        assert action["load_change"] > 0
    
    def test_readiness_explanations(self):
        model = ConcurrentTrainingModel()
        autoreg = Autoregulator(model)
        
        day_state = DayLevelState(
            date="2024-01-01",
            D_l={LiftType.SQUAT: 0.5, LiftType.BENCH: 0.2},
            D_sys=0.4,
            R_mito=0.6,
            E_fat=0.5
        )
        
        readiness = autoreg.compute_readiness(day_state)
        
        assert "overall" in readiness
        assert "per_lift" in readiness
        assert "explanations" in readiness
        assert len(readiness["explanations"]) > 0
        # Should mention highest fatigue
        assert any("squat" in exp.lower() for exp in readiness["explanations"])


class TestSystemParameters:
    """Test parameter configuration"""
    
    def test_default_parameters(self):
        params = SystemParameters()
        assert params.alpha_l > 0
        assert params.tau_Dl > 0
        assert params.k_mito > 0
    
    def test_custom_parameters(self):
        params = SystemParameters(alpha_l=0.1, tau_Dl=5.0)
        assert params.alpha_l == 0.1
        assert params.tau_Dl == 5.0


class TestEnduranceSplits:
    """Test endurance session splitting"""
    
    def test_z2_split(self):
        model = ConcurrentTrainingModel()
        z2, hiit = model.compute_endurance_splits(60, "z2", EnduranceSport.CYCLING)
        assert z2 == 60
        assert hiit == 0
    
    def test_hiit_split(self):
        model = ConcurrentTrainingModel()
        z2, hiit = model.compute_endurance_splits(30, "hiit", EnduranceSport.RUNNING)
        assert z2 == 0
        assert hiit == 30
    
    def test_mixed_split(self):
        model = ConcurrentTrainingModel()
        z2, hiit = model.compute_endurance_splits(60, "mixed", EnduranceSport.CYCLING)
        assert z2 == 18  # 30%
        assert hiit == 42  # 70%
