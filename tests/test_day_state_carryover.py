"""
Test day state carryover between days without sessions.

These tests verify that day states properly decay and carry over when there are
gaps between training sessions, rather than resetting to zero.
"""
import pytest
from datetime import date, timedelta
from app.domain.day_engine import DayState, PerLiftState, DailyImpulses, EnduranceImpulses, StrengthImpulses, decay_day_state_to_date, update_day_state, DayEngineParams


class TestDayStateCarryover:
    """Test that day states carry over with proper decay."""
    
    @pytest.fixture
    def params(self):
        return DayEngineParams()
    
    def test_decay_day_state_to_same_date_returns_copy(self, params):
        """Decay to same date should return a copy with same values."""
        d = date(2026, 1, 1)
        state = DayState(
            date=d,
            per_lift={'bench': PerLiftState(D_l=1.5, F_l=2.0, C_l=100.0)},
            D_sys=0.8,
            R_mito=0.4,
            E_fat=0.3,
            T_legs=0.5
        )
        
        result = decay_day_state_to_date(state, d, params)
        
        assert result.date == d
        assert result.per_lift['bench'].D_l == 1.5
        assert result.per_lift['bench'].F_l == 2.0
        assert result.D_sys == 0.8
        assert result.R_mito == 0.4
        assert result.E_fat == 0.3
        assert result.T_legs == 0.5
    
    def test_decay_day_state_forward_one_day(self, params):
        """Decay should reduce fatigue values over one day."""
        d1 = date(2026, 1, 1)
        d2 = date(2026, 1, 2)
        
        state = DayState(
            date=d1,
            per_lift={'bench': PerLiftState(D_l=1.5, F_l=2.0, C_l=100.0)},
            D_sys=0.8,
            R_mito=0.4,
            E_fat=0.3,
            T_legs=0.5
        )
        
        result = decay_day_state_to_date(state, d2, params)
        
        assert result.date == d2
        # Fatigue should decay (be lower after one day)
        assert result.per_lift['bench'].D_l < 1.5
        assert result.per_lift['bench'].D_l > 0
        assert result.D_sys < 0.8
        assert result.D_sys > 0
        assert result.R_mito < 0.4
        assert result.R_mito > 0
        assert result.E_fat < 0.3
        assert result.E_fat > 0
        assert result.T_legs < 0.5
        assert result.T_legs > 0
    
    def test_decay_day_state_forward_multiple_days(self, params):
        """Decay should progressively reduce fatigue over multiple days."""
        d1 = date(2026, 1, 1)
        d5 = date(2026, 1, 6)  # 5 days later
        
        state = DayState(
            date=d1,
            per_lift={'bench': PerLiftState(D_l=2.0, F_l=2.0, C_l=100.0)},
            D_sys=1.0,
            R_mito=0.5,
            E_fat=0.5,
            T_legs=1.0
        )
        
        result = decay_day_state_to_date(state, d5, params)
        
        assert result.date == d5
        # After 5 days, fatigue should be significantly lower
        assert result.per_lift['bench'].D_l < 1.0  # Roughly half
        assert result.D_sys < 0.5
        # T_legs has slower decay (longer time constant), so should still be elevated
        assert result.T_legs < 1.0
        assert result.T_legs > 0.5  # But should have decayed some
    
    def test_decay_preserves_fitness_decay_too(self, params):
        """Fitness (F_l) should also decay over time."""
        d1 = date(2026, 1, 1)
        d10 = date(2026, 1, 11)
        
        state = DayState(
            date=d1,
            per_lift={'bench': PerLiftState(D_l=0.0, F_l=2.0, C_l=100.0)},
            D_sys=0.0,
            R_mito=0.0,
            E_fat=0.0,
            T_legs=0.0
        )
        
        result = decay_day_state_to_date(state, d10, params)
        
        # Fitness should decay
        assert result.per_lift['bench'].F_l < 2.0
        assert result.per_lift['bench'].F_l > 0
    
    def test_decay_does_not_mutate_original(self, params):
        """Original state should not be modified."""
        d1 = date(2026, 1, 1)
        d2 = date(2026, 1, 2)
        
        state = DayState(
            date=d1,
            per_lift={'bench': PerLiftState(D_l=1.5, F_l=2.0, C_l=100.0)},
            D_sys=0.8,
            R_mito=0.4,
            E_fat=0.3,
            T_legs=0.5
        )
        
        result = decay_day_state_to_date(state, d2, params)
        
        # Original should be unchanged
        assert state.date == d1
        assert state.per_lift['bench'].D_l == 1.5
        assert state.D_sys == 0.8
    
    def test_decay_raises_on_past_date(self, params):
        """Should raise error if target date is before current date."""
        d1 = date(2026, 1, 5)
        d2 = date(2026, 1, 1)  # Before d1
        
        state = DayState(
            date=d1,
            per_lift={},
            D_sys=0.0,
            R_mito=0.0,
            E_fat=0.0,
            T_legs=0.0
        )
        
        with pytest.raises(ValueError, match="target_date.*must be >= current.date"):
            decay_day_state_to_date(state, d2, params)
    
    def test_decay_multiple_lifts(self, params):
        """Should decay all lifts in per_lift dict."""
        d1 = date(2026, 1, 1)
        d3 = date(2026, 1, 4)
        
        state = DayState(
            date=d1,
            per_lift={
                'bench': PerLiftState(D_l=1.5, F_l=2.0, C_l=100.0),
                'squat': PerLiftState(D_l=2.0, F_l=2.5, C_l=100.0),
                'deadlift': PerLiftState(D_l=2.5, F_l=3.0, C_l=100.0),
            },
            D_sys=1.0,
            R_mito=0.5,
            E_fat=0.4,
            T_legs=0.8
        )
        
        result = decay_day_state_to_date(state, d3, params)
        
        assert 'bench' in result.per_lift
        assert 'squat' in result.per_lift
        assert 'deadlift' in result.per_lift
        assert result.per_lift['bench'].D_l < 1.5
        assert result.per_lift['squat'].D_l < 2.0
        assert result.per_lift['deadlift'].D_l < 2.5


class TestUpdateDayStateDateHandling:
    """Test that update_day_state preserves date correctly."""
    
    @pytest.fixture
    def params(self):
        return DayEngineParams()
    
    def test_update_preserves_same_date(self, params):
        """update_day_state should keep the same date, not increment."""
        d = date(2026, 1, 15)
        
        current = DayState(
            date=d,
            per_lift={'bench': PerLiftState(D_l=0.5, F_l=2.0, C_l=100.0)},
            D_sys=0.3,
            R_mito=0.2,
            E_fat=0.1,
            T_legs=0.2
        )
        
        impulses = DailyImpulses(
            endurance=EnduranceImpulses(u_E_Z2=0.0, u_E_HIIT=0.0, u_E_total=0.0, mode='running', has_HIIT=False, has_Z2=False),
            strength=StrengthImpulses(per_lift={}, u_sys=0.0, u_legs=0.0, u_met=0.0, u_legs_high_intensity=0.0, sets=[]),
            date=d
        )
        
        result = update_day_state(current, impulses, params)
        
        # Date should be the SAME, not incremented
        assert result.date == d
        assert result.date != d + timedelta(days=1)
    
    def test_update_with_session_does_not_change_date(self, params):
        """Even with impulses, date should remain the same."""
        d = date(2026, 1, 20)
        
        current = DayState(
            date=d,
            per_lift={'bench': PerLiftState(D_l=0.0, F_l=1.0, C_l=100.0)},
            D_sys=0.0,
            R_mito=0.0,
            E_fat=0.0,
            T_legs=0.0
        )
        
        impulses = DailyImpulses(
            endurance=EnduranceImpulses(u_E_Z2=0.0, u_E_HIIT=0.0, u_E_total=0.0, mode='running', has_HIIT=False, has_Z2=False),
            strength=StrengthImpulses(per_lift={'bench': 10.0}, u_sys=10.0, u_legs=0.0, u_met=0.0, u_legs_high_intensity=0.0, sets=[]),
            date=d
        )
        
        result = update_day_state(current, impulses, params)
        
        assert result.date == d


class TestDayStateContinuityScenario:
    """Integration test simulating real usage scenario."""
    
    @pytest.fixture
    def params(self):
        return DayEngineParams()
    
    def test_three_day_gap_carryover(self, params):
        """Simulate: Train Jan 1, rest Jan 2-4, train Jan 5.
        
        State on Jan 5 should be decayed from Jan 1, not reset to zero.
        """
        d1 = date(2026, 1, 1)
        d2 = date(2026, 1, 2)
        d3 = date(2026, 1, 3)
        d4 = date(2026, 1, 4)
        d5 = date(2026, 1, 5)
        
        # Day 1: Heavy training
        day1_state = DayState(
            date=d1,
            per_lift={'squat': PerLiftState(D_l=2.0, F_l=2.5, C_l=100.0)},
            D_sys=1.2,
            R_mito=0.3,
            E_fat=0.2,
            T_legs=1.0
        )
        
        # Days 2-4: No training - state decays
        day2_state = decay_day_state_to_date(day1_state, d2, params)
        day3_state = decay_day_state_to_date(day2_state, d3, params)
        day4_state = decay_day_state_to_date(day3_state, d4, params)
        
        # Day 5: New training - should start from decayed state
        impulses = DailyImpulses(
            endurance=EnduranceImpulses(u_E_Z2=0.0, u_E_HIIT=0.0, u_E_total=0.0, mode='running', has_HIIT=False, has_Z2=False),
            strength=StrengthImpulses(per_lift={'squat': 15.0}, u_sys=15.0, u_legs=15.0, u_met=0.0, u_legs_high_intensity=15.0, sets=[]),
            date=d5
        )
        day5_state = update_day_state(day4_state, impulses, params)
        day5_state.date = d5  # Set correct date
        
        # T_legs should be > 0 (carried over and decayed, then updated)
        assert day5_state.T_legs > 0
        # Should be less than original 1.0 (decayed over 4 days) + new training
        assert day5_state.T_legs < 2.0
        
        # System fatigue should also show carryover
        assert day5_state.D_sys > 0
    
    def test_t_legs_never_resets_to_zero(self, params):
        """T_legs should never reset to zero between sessions."""
        d1 = date(2026, 1, 1)
        d7 = date(2026, 1, 8)
        d14 = date(2026, 1, 15)
        
        # High T_legs after heavy squats
        state = DayState(
            date=d1,
            per_lift={'squat': PerLiftState(D_l=1.0, F_l=2.0, C_l=100.0)},
            D_sys=0.5,
            R_mito=0.2,
            E_fat=0.1,
            T_legs=2.0  # High structural fatigue
        )
        
        # Week later
        week_later = decay_day_state_to_date(state, d7, params)
        
        # T_legs should have decayed but NOT to zero
        assert week_later.T_legs > 0
        assert week_later.T_legs < 2.0
        
        # Two weeks later
        two_weeks = decay_day_state_to_date(state, d14, params)
        
        # Still not zero (very slow decay)
        assert two_weeks.T_legs > 0
