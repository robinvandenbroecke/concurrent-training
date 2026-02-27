"""
Unit tests for day-level state engine.

Tests verify deterministic day-to-day state transitions and readiness computation.
"""
import pytest
from datetime import date, timedelta

from app.domain.day_engine import (
    DayEngineParams,
    SetImpulse,
    StrengthImpulses,
    EnduranceImpulses,
    DailyImpulses,
    PerLiftState,
    DayState,
    ReadinessOutput,
    compute_strength_impulses,
    compute_endurance_impulses,
    compute_interference,
    update_day_state,
    compute_readiness,
    simulate_day_transition,
    create_initial_state,
    LiftType,
)


class TestStrengthImpulses:
    """Test strength impulse calculations."""
    
    def test_single_set_impulse(self):
        """Basic set computes impulse correctly."""
        params = DayEngineParams()
        
        sets = [
            SetImpulse(
                lift="squat",
                tonnage=500.0,  # 100kg x 5 reps
                intensity=0.8,  # 80% of capacity
                velocity_factor=1.0,  # Fresh
                vl=0.10,  # 10% velocity loss
                reps=5
            )
        ]
        
        impulses = compute_strength_impulses(sets, params)
        
        # P = 1 + 1.5 * 0.10 = 1.15
        # I^alpha = 0.8^1.2 = 0.756
        # u_set = 500 * 0.756 * 1.0 * 1.15 = 434.7
        assert impulses.per_lift["squat"] > 400.0
        assert impulses.u_sys > 0.0  # Squat contributes to system
        assert impulses.u_legs > 0.0  # Squat is legs
    
    def test_multiple_sets_aggregate(self):
        """Multiple sets per lift aggregate impulses."""
        params = DayEngineParams()
        
        sets = [
            SetImpulse("squat", 400.0, 0.75, 1.0, 0.08, 5),
            SetImpulse("squat", 400.0, 0.75, 1.0, 0.12, 5),
            SetImpulse("bench", 300.0, 0.70, 1.0, 0.10, 5),
        ]
        
        impulses = compute_strength_impulses(sets, params)
        
        # Squat should have higher impulse than bench (tonnage + omega)
        assert impulses.per_lift["squat"] > impulses.per_lift["bench"]
        
        # Should have both lifts
        assert "squat" in impulses.per_lift
        assert "bench" in impulses.per_lift
    
    def test_deadlift_higher_system_impact(self):
        """Deadlift has higher omega than bench."""
        params = DayEngineParams()
        
        # Same tonnage for both
        sets_dl = [SetImpulse("deadlift", 500.0, 0.75, 1.0, 0.10, 5)]
        sets_bp = [SetImpulse("bench", 500.0, 0.75, 1.0, 0.10, 5)]
        
        impulses_dl = compute_strength_impulses(sets_dl, params)
        impulses_bp = compute_strength_impulses(sets_bp, params)
        
        # Deadlift omega=1.3, bench omega=0.7
        assert impulses_dl.u_sys > impulses_bp.u_sys
    
    def test_high_rep_metabolic_impulse(self):
        """High rep sets contribute to metabolic impulse."""
        params = DayEngineParams()
        
        sets_low = [SetImpulse("squat", 500.0, 0.70, 1.0, 0.10, 5)]
        sets_high = [SetImpulse("squat", 500.0, 0.70, 1.0, 0.15, 10)]
        
        impulses_low = compute_strength_impulses(sets_low, params)
        impulses_high = compute_strength_impulses(sets_high, params)
        
        # High rep should have metabolic contribution
        assert impulses_high.u_met > impulses_low.u_met


class TestEnduranceImpulses:
    """Test endurance impulse calculations."""
    
    def test_z2_session(self):
        """Z2 session contributes only to Z2 component."""
        sessions = [
            ("cycling", 60.0, "z2"),  # 60 min Z2
        ]
        
        impulses = compute_endurance_impulses(sessions, DayEngineParams())
        
        assert impulses.u_E_Z2 == 60.0
        assert impulses.u_E_HIIT == 0.0
        assert impulses.has_Z2
        assert not impulses.has_HIIT
    
    def test_hiit_session(self):
        """HIIT session contributes only to HIIT component."""
        sessions = [
            ("running", 30.0, "hiit"),  # 30 min HIIT
        ]
        
        impulses = compute_endurance_impulses(sessions, DayEngineParams())
        
        assert impulses.u_E_Z2 == 0.0
        assert impulses.u_E_HIIT == 30.0
        assert impulses.has_HIIT
        assert not impulses.has_Z2
    
    def test_mixed_session_split(self):
        """Mixed session splits between Z2 and HIIT."""
        sessions = [
            ("cycling", 60.0, "mixed"),  # 30% Z2, 70% HIIT
        ]
        
        impulses = compute_endurance_impulses(sessions, DayEngineParams())
        
        assert impulses.u_E_Z2 == pytest.approx(18.0, abs=0.1)  # 30%
        assert impulses.u_E_HIIT == pytest.approx(42.0, abs=0.1)  # 70%
        assert impulses.has_Z2
        assert impulses.has_HIIT


class TestInterference:
    """Test endurance-to-strength interference."""
    
    def test_no_hiit_no_interference(self):
        """Z2-only produces no interference."""
        endurance = EnduranceImpulses(
            u_E_Z2=60.0,
            u_E_HIIT=0.0,
            u_E_total=60.0,
            mode="cycling",
            has_HIIT=False,
            has_Z2=True
        )
        
        params = DayEngineParams()
        per_lift, sys = compute_interference(endurance, params)
        
        assert all(v == 0.0 for v in per_lift.values())
        assert sys == 0.0
    
    def test_hiit_creates_interference(self):
        """HIIT creates interference, higher for legs."""
        endurance = EnduranceImpulses(
            u_E_Z2=0.0,
            u_E_HIIT=30.0,
            u_E_total=30.0,
            mode="running",  # mode_factor=1.3
            has_HIIT=True,
            has_Z2=False
        )
        
        params = DayEngineParams()
        per_lift, sys = compute_interference(endurance, params)
        
        # Interference should exist
        assert per_lift["squat"] > 0.0
        assert sys > 0.0
        
        # Running has higher mode factor than cycling
        endurance_cycling = EnduranceImpulses(
            u_E_Z2=0.0, u_E_HIIT=30.0, u_E_total=30.0,
            mode="cycling", has_HIIT=True, has_Z2=False
        )
        per_lift_cycle, _ = compute_interference(endurance_cycling, params)
        
        # Running > cycling interference
        assert per_lift["squat"] > per_lift_cycle["squat"]
    
    def test_squat_more_interference_than_bench(self):
        """Legs lifts get more interference than upper body."""
        endurance = EnduranceImpulses(
            u_E_Z2=0.0,
            u_E_HIIT=30.0,
            u_E_total=30.0,
            mode="running",
            has_HIIT=True,
            has_Z2=False
        )
        
        params = DayEngineParams()
        per_lift, _ = compute_interference(endurance, params)
        
        # Squat k_ES=0.00030, bench k_ES=0.00008
        assert per_lift["squat"] > per_lift["bench"]


class TestDayStateUpdate:
    """Test day-to-day state transitions."""
    
    def test_strength_increases_fatigue(self):
        """Test 1: Strength-only day increases D_l for that lift."""
        current = create_initial_state(date(2024, 1, 1), ["squat"])
        
        sets = [SetImpulse("squat", 1000.0, 0.80, 1.0, 0.12, 5)]
        
        new_state, impulses, readiness = simulate_day_transition(
            current, sets, [], DayEngineParams()
        )
        
        # Fatigue should increase
        assert new_state.per_lift["squat"].D_l > current.per_lift["squat"].D_l
        
        # Readiness should decrease
        assert readiness.per_lift["squat"] < 1.0
    
    def test_z2_increases_r_mito(self):
        """Test 2: Z2 increases R_mito."""
        current = create_initial_state(date(2024, 1, 1), ["squat"])
        
        # Compare Z2 vs no endurance
        new_with_z2, _, _ = simulate_day_transition(
            current, [], [("cycling", 60.0, "z2")], DayEngineParams()
        )
        
        new_no_end, _, _ = simulate_day_transition(
            current, [], [], DayEngineParams()
        )
        
        # Z2 should increase R_mito
        assert new_with_z2.R_mito > new_no_end.R_mito
    
    def test_hiit_interference_affects_squat_more(self):
        """Test 3: HIIT running increases interference for squat more than bench."""
        current = create_initial_state(date(2024, 1, 1), ["squat", "bench"])
        
        sets = [
            SetImpulse("squat", 500.0, 0.75, 1.0, 0.10, 5),
            SetImpulse("bench", 300.0, 0.70, 1.0, 0.10, 5),
        ]
        
        # With HIIT running interference
        new_with_hiit, _, _ = simulate_day_transition(
            current, sets, [("running", 30.0, "hiit")], DayEngineParams()
        )
        
        # Squat should be more affected than bench
        squat_fatigue = new_with_hiit.per_lift["squat"].D_l
        bench_fatigue = new_with_hiit.per_lift["bench"].D_l
        
        # Squat starts with higher interference coefficient
        # Plus has direct strength impulse, so should accumulate more
        assert squat_fatigue > bench_fatigue
    
    def test_legs_strength_increases_e_fat(self):
        """Test 4: Legs strength increases E_fat."""
        current = create_initial_state(date(2024, 1, 1), ["squat", "bench"])
        
        # Heavy legs session
        legs_sets = [SetImpulse("squat", 1500.0, 0.80, 1.0, 0.15, 5)]
        
        # Upper body only
        upper_sets = [SetImpulse("bench", 800.0, 0.70, 1.0, 0.10, 5)]
        
        new_legs, _, _ = simulate_day_transition(
            current, legs_sets, [], DayEngineParams()
        )
        
        new_upper, _, _ = simulate_day_transition(
            current, upper_sets, [], DayEngineParams()
        )
        
        # Legs session should increase E_fat more
        assert new_legs.E_fat > new_upper.E_fat
    
    def test_rest_decay(self):
        """Fatigue decays on rest days (no impulses)."""
        # Start with fatigued state
        current = create_initial_state(date(2024, 1, 1), ["squat"])
        current.per_lift["squat"].D_l = 0.5
        current.D_sys = 0.3
        
        # Rest day
        new_state, _, _ = simulate_day_transition(
            current, [], [], DayEngineParams()
        )
        
        # Fatigue should decay
        assert new_state.per_lift["squat"].D_l < current.per_lift["squat"].D_l
        assert new_state.D_sys < current.D_sys


class TestRmitoEffects:
    """Test recovery capacity effects."""
    
    def test_high_r_mito_speeds_decay(self):
        """Higher R_mito accelerates fatigue decay."""
        # Start with fatigued state
        current_low = create_initial_state(date(2024, 1, 1), ["squat"])
        current_low.per_lift["squat"].D_l = 0.5
        current_low.R_mito = 0.0  # Poor recovery
        
        current_high = create_initial_state(date(2024, 1, 1), ["squat"])
        current_high.per_lift["squat"].D_l = 0.5
        current_high.R_mito = 1.0  # Good recovery
        
        # Rest day
        params = DayEngineParams()
        
        new_low, _, _ = simulate_day_transition(current_low, [], [], params)
        new_high, _, _ = simulate_day_transition(current_high, [], [], params)
        
        # Higher R_mito should lead to more decay
        decay_low = current_low.per_lift["squat"].D_l - new_low.per_lift["squat"].D_l
        decay_high = current_high.per_lift["squat"].D_l - new_high.per_lift["squat"].D_l
        
        assert decay_high > decay_low


class TestDeterminism:
    """Test 5: Deterministic outputs."""
    
    def test_same_inputs_same_outputs(self):
        """Same inputs produce identical outputs."""
        current = create_initial_state(date(2024, 1, 1), ["squat", "bench"])
        
        sets = [
            SetImpulse("squat", 800.0, 0.75, 1.0, 0.10, 5),
            SetImpulse("bench", 500.0, 0.70, 1.0, 0.08, 5),
        ]
        
        endurance = [("cycling", 45.0, "z2")]
        
        params = DayEngineParams()
        
        # Run twice
        new1, imp1, ready1 = simulate_day_transition(current, sets, endurance, params)
        new2, imp2, ready2 = simulate_day_transition(current, sets, endurance, params)
        
        # Should be identical
        assert new1.per_lift["squat"].D_l == pytest.approx(new2.per_lift["squat"].D_l, abs=1e-10)
        assert new1.D_sys == pytest.approx(new2.D_sys, abs=1e-10)
        assert new1.R_mito == pytest.approx(new2.R_mito, abs=1e-10)
        assert ready1.overall == pytest.approx(ready2.overall, abs=1e-10)


class TestReadiness:
    """Test readiness computation."""
    
    def test_fresh_state_high_readiness(self):
        """Fresh state has high readiness."""
        state = create_initial_state(date(2024, 1, 1), ["squat"])
        
        readiness = compute_readiness(state, DayEngineParams())
        
        assert readiness.per_lift["squat"] == pytest.approx(1.0, abs=0.01)
        assert readiness.endurance == pytest.approx(1.0, abs=0.01)
        assert readiness.overall > 0.95
    
    def test_fatigued_state_low_readiness(self):
        """Fatigued state has low readiness."""
        state = create_initial_state(date(2024, 1, 1), ["squat"])
        state.per_lift["squat"].D_l = 0.6
        state.D_sys = 0.4
        state.E_fat = 0.6
        
        readiness = compute_readiness(state, DayEngineParams())
        
        # Should be low
        assert readiness.per_lift["squat"] < 0.5
        assert readiness.endurance <= 0.5  # clamp(1 - 0.6) = 0.4
        assert readiness.overall < 0.6
        
        # Should have explanations
        assert len(readiness.explanations) > 0
    
    def test_system_fatigue_explanation(self):
        """High D_sys generates explanation."""
        state = create_initial_state(date(2024, 1, 1), ["squat"])
        state.D_sys = 0.5
        
        readiness = compute_readiness(state, DayEngineParams())
        
        # Should mention system fatigue
        assert any("system" in e.lower() for e in readiness.explanations)


class TestCapacityEvolution:
    """Test capacity (C_l) changes over time."""
    
    def test_training_increases_capacity(self):
        """Repeated training increases capacity (with proper recovery)."""
        state = create_initial_state(date(2024, 1, 1), ["squat"])
        initial_C = state.per_lift["squat"].C_l

        # Simulate training blocks with rest days for recovery
        # 4 weeks: 3 training days, 1 rest day per week
        sets = [SetImpulse("squat", 600.0, 0.70, 1.0, 0.08, 5)]  # Moderate load

        for week in range(4):
            # 3 training days
            for _ in range(3):
                state, _, _ = simulate_day_transition(state, sets, [], DayEngineParams())
            # 1 rest day
            state, _, _ = simulate_day_transition(state, [], [], DayEngineParams())

        # Capacity should increase from training (with recovery)
        assert state.per_lift["squat"].C_l > initial_C
    
    def test_detraining_decreases_capacity(self):
        """Rest days without training can decrease capacity."""
        # Note: with lambda_l=0 (v1 default), no detraining
        # Test with small lambda
        params = DayEngineParams(lambda_l=0.5)
        
        state = create_initial_state(date(2024, 1, 1), ["squat"])
        state.per_lift["squat"].F_l = 10.0  # High fitness
        initial_C = state.per_lift["squat"].C_l
        
        # Simulate 30 rest days
        for _ in range(30):
            state, _, _ = simulate_day_transition(state, [], [], params)
        
        # With lambda_l > 0, capacity should decrease from detraining
        # (Note: in v1 default lambda=0, this won't happen)
        if params.lambda_l > 0:
            assert state.per_lift["squat"].C_l < initial_C


class TestMultiDaySimulation:
    """Test multi-day training blocks."""
    
    def test_typical_week(self):
        """Simulate a typical training week."""
        state = create_initial_state(date(2024, 1, 1), ["squat", "bench", "deadlift"])
        
        params = DayEngineParams()
        
        # Day 1: Heavy squat
        state, _, r1 = simulate_day_transition(
            state,
            [SetImpulse("squat", 1200.0, 0.80, 1.0, 0.15, 5)],
            [],
            params
        )
        
        # Day 2: Bench + Z2 (recovery)
        state, _, r2 = simulate_day_transition(
            state,
            [SetImpulse("bench", 600.0, 0.75, 1.0, 0.10, 5)],
            [("cycling", 45.0, "z2")],
            params
        )
        
        # Day 3: Deadlift
        state, _, r3 = simulate_day_transition(
            state,
            [SetImpulse("deadlift", 1000.0, 0.78, 1.0, 0.12, 5)],
            [],
            params
        )
        
        # Squat readiness should be better on day 3 (2 days recovery)
        # than on day 2 (1 day recovery)
        # (Note: we don't track day 2 readiness for squat specifically,
        # but we can verify the pattern)
        
        # Endurance fatigue should be present from deadlift (legs strength)
        # k_SE * u_legs contributes to E_fat
        assert state.E_fat > 0.0
        
        # R_mito should be elevated from Z2
        assert state.R_mito > 0.0


class TestPriming:
    """Test Z2 priming effect on strength adaptation."""
    
    def test_priming_increases_fitness_gain(self):
        """Z2 priming increases F_l gain from strength training."""
        state = create_initial_state(date(2024, 1, 1), ["squat"])
        
        sets = [SetImpulse("squat", 800.0, 0.75, 1.0, 0.10, 5)]
        
        # Without priming
        new_no_prime, _, _ = simulate_day_transition(
            state, sets, [], DayEngineParams(), has_priming=False
        )
        
        # With priming (Z2 within last 36h)
        new_prime, _, _ = simulate_day_transition(
            state, sets, [], DayEngineParams(), has_priming=True
        )
        
        # Fitness gain should be higher with priming
        assert new_prime.per_lift["squat"].F_l > new_no_prime.per_lift["squat"].F_l
