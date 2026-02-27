"""
Sprint V1: Tests for baseline models
"""
import pytest
from datetime import date, timedelta

from app.eval.baselines import (
    BanisterState,
    BanisterParams,
    BaselineVelocityThreshold,
    BaselineBanister,
    BaselineEndurance,
)


class TestBanisterState:
    """Test Banister fitness-fatigue state."""
    
    def test_initial_state(self):
        """Initial state should have fitness=1, fatigue=0."""
        state = BanisterState()
        assert state.fitness == 1.0
        assert state.fatigue == 0.0
        assert state.form == 1.0
    
    def test_form_calculation(self):
        """Form = fitness - fatigue."""
        state = BanisterState(fitness=1.2, fatigue=0.3)
        assert state.form == pytest.approx(0.9, abs=1e-9)
    
    def test_predicted_perf_y(self):
        """Test perf_y prediction from form."""
        state = BanisterState(fitness=1.2, fatigue=0.2)
        pred = state.predicted_perf_y()
        
        # form = 1.0, normalized ~0.75, pred ~1.0
        assert 0.75 <= pred <= 1.0


class TestBanisterParams:
    """Test Banister parameter updates."""
    
    def test_update_with_zero_impulse(self):
        """Update with zero impulse should only decay."""
        params = BanisterParams()
        state = BanisterState(fitness=1.0, fatigue=0.5)
        
        new_state = params.update(state, impulse=0.0, days=1)
        
        # Both should decay
        assert new_state.fitness < state.fitness
        assert new_state.fatigue < state.fatigue
    
    def test_update_with_impulse(self):
        """Update with impulse should increase fitness and fatigue."""
        params = BanisterParams()
        state = BanisterState(fitness=1.0, fatigue=0.0)
        
        new_state = params.update(state, impulse=100.0, days=1)
        
        # Both should increase from impulse (after decay)
        assert new_state.fitness > 0.5  # Should have added from impulse
        assert new_state.fatigue > 0.0
    
    def test_fatigue_decays_faster(self):
        """Fatigue should decay faster than fitness (shorter tau)."""
        params = BanisterParams(tau_fitness=30.0, tau_fatigue=7.0)
        state = BanisterState(fitness=1.0, fatigue=1.0)
        
        new_state = params.update(state, impulse=0.0, days=7)
        
        # Fatigue should decay more
        fitness_decay = 1.0 - new_state.fitness
        fatigue_decay = 1.0 - new_state.fatigue
        assert fatigue_decay > fitness_decay


class TestBaselineVelocityThreshold:
    """Test Baseline A: velocity-threshold heuristic."""
    
    def test_initial_readiness(self):
        """Initial readiness should be neutral (0.75)."""
        baseline = BaselineVelocityThreshold()
        readiness = baseline.predict_readiness("squat", date.today())
        assert readiness == 0.75
    
    def test_readiness_with_history(self):
        """Readiness based on recent vs reference performance."""
        baseline = BaselineVelocityThreshold(window_days=7)
        
        # Add observations
        today = date.today()
        for i in range(10):
            d = today - timedelta(days=i)
            baseline.add_observation("squat", d, 0.90)  # Consistent performance
        
        # Recent same as reference -> readiness ~1.0
        readiness = baseline.predict_readiness("squat", today)
        assert readiness > 0.9
    
    def test_readiness_decline(self):
        """Lower recent performance -> lower readiness."""
        baseline = BaselineVelocityThreshold(window_days=7)
        
        today = date.today()
        
        # Old good performances
        for i in range(5, 10):
            d = today - timedelta(days=i)
            baseline.add_observation("squat", d, 0.95)
        
        # Recent poor performance
        for i in range(3):
            d = today - timedelta(days=i)
            baseline.add_observation("squat", d, 0.80)
        
        readiness = baseline.predict_readiness("squat", today)
        assert readiness < 0.9  # Should be reduced


class TestBaselineBanister:
    """Test Baseline B: Banister fitness-fatigue model."""
    
    def test_initial_state(self):
        """Initial state should be fresh."""
        baseline = BaselineBanister()
        readiness = baseline.predict_readiness("squat")
        
        # Initial form ~1.0, normalized ~0.75
        assert readiness > 0.5
    
    def test_update_changes_state(self):
        """Training updates should change state."""
        baseline = BaselineBanister()
        
        # Get initial state
        initial_state = baseline._get_or_create_state("squat")
        initial_fitness = initial_state.fitness
        initial_fatigue = initial_state.fatigue
        
        # Add heavy training
        baseline.update("squat", date.today(), tonnage=5000, intensity=0.8)
        
        # State should change
        new_state = baseline._get_or_create_state("squat")
        # Fitness and/or fatigue should have changed
        assert (new_state.fitness != initial_fitness or 
                new_state.fatigue != initial_fatigue)
    
    def test_compute_impulse(self):
        """Impulse calculation."""
        baseline = BaselineBanister()
        
        # Higher tonnage + intensity = higher impulse
        impulse1 = baseline.compute_impulse(1000, 0.7)
        impulse2 = baseline.compute_impulse(2000, 0.7)
        
        assert impulse2 > impulse1


class TestBaselineEndurance:
    """Test endurance baseline."""
    
    def test_initial_stable(self):
        """With no history, predict stable."""
        baseline = BaselineEndurance()
        stable = baseline.predict_stable(date.today())
        assert stable is True
    
    def test_increasing_load_stable(self):
        """Increasing load -> predict stable/improve."""
        baseline = BaselineEndurance(window_days=7)
        
        today = date.today()
        
        # Older lower load
        for i in range(5, 10):
            d = today - timedelta(days=i)
            baseline.add_observation(d, 50.0)
        
        # Recent higher load
        for i in range(3):
            d = today - timedelta(days=i)
            baseline.add_observation(d, 70.0)
        
        stable = baseline.predict_stable(today)
        assert stable is True  # Increasing load = stable/improve prediction
    
    def test_decreasing_load_decline(self):
        """Decreasing load -> predict decline."""
        baseline = BaselineEndurance(window_days=7)
        
        today = date.today()
        
        # Older higher load
        for i in range(5, 10):
            d = today - timedelta(days=i)
            baseline.add_observation(d, 70.0)
        
        # Recent lower load
        for i in range(3):
            d = today - timedelta(days=i)
            baseline.add_observation(d, 40.0)
        
        stable = baseline.predict_stable(today)
        assert stable is False  # Decreasing load = decline prediction
