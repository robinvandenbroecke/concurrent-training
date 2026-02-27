"""
Unit tests for rep-level fatigue engine.

Tests verify deterministic behavior and expected physiological patterns:
- Monotonic fatigue accumulation
- Cross-lift system fatigue spillover
- Rest recovery between sets
- R_mito (recovery capacity) effects
- Lift-specific fatigue rates
"""
import pytest
import math
from copy import deepcopy

from app.domain.rep_engine import (
    LiftVelocityProfile,
    RepEngineParams,
    RepInput,
    SetInput,
    SessionInput,
    SessionOutput,
    simulate_strength_session,
    LimitingFactor,
    RepState,
)


class TestLiftVelocityProfile:
    """Test load-velocity profile calculations."""
    
    def test_v_ref_linear(self):
        """Reference velocity follows linear model v = a - b*w."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        
        # At 0 kg, should be ~a
        assert profile.v_ref(0) == pytest.approx(0.55, abs=0.001)
        
        # At 100 kg: 0.55 - 0.0032*100 = 0.23
        assert profile.v_ref(100) == pytest.approx(0.23, abs=0.001)
    
    def test_v_ref_clamped_to_minimum(self):
        """Reference velocity has a floor."""
        profile = LiftVelocityProfile(lift="squat", a=0.5, b=0.01, v_min=0.05)
        
        # At 100 kg: 0.5 - 0.01*100 = -0.5 -> clamped to 0.05
        assert profile.v_ref(100) == 0.05


class TestRepStateBasics:
    """Test internal state tracking."""
    
    def test_initialization(self):
        """State initializes correctly from availability values."""
        params = RepEngineParams()
        state = RepState(
            A_local_init={"squat": 0.9, "bench": 0.95},
            A_sys_init=0.92,
            M_init=0.1,
            params=params
        )
        
        assert state.A_local("squat") == pytest.approx(0.9, abs=0.001)
        assert state.A_local("bench") == pytest.approx(0.95, abs=0.001)
        assert state.A_sys == pytest.approx(0.92, abs=0.001)
        assert state.M == pytest.approx(0.1, abs=0.001)
    
    def test_availability_clamping(self):
        """Availability is clamped to minimum floor."""
        params = RepEngineParams(min_A=0.02)
        state = RepState(
            A_local_init={"squat": 0.001},  # Below minimum
            A_sys_init=0.001,
            M_init=0.0,
            params=params
        )
        
        assert state.A_local("squat") >= 0.02
        assert state.A_sys >= 0.02


class TestMonotonicFatigue:
    """
    Test 1: Monotonic fatigue within set.
    Given constant load and decreasing observed velocities,
    A_l and/or A_sys should decrease across reps and v_pred_next should decrease.
    """
    
    def test_fatigue_accumulates_over_reps(self):
        """Fatigue accumulates monotonically during a set."""
        # Setup: squat set with decreasing velocities (fatiguing)
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        
        session = SessionInput(
            sets=[
                SetInput(
                    lift="squat",
                    load_kg=100.0,
                    velocities=[0.45, 0.42, 0.39, 0.36, 0.33],  # Decreasing
                    rest_before_sec=None
                )
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0
        )
        
        result = simulate_strength_session(session)
        
        # Extract availability trajectory
        reps = result.sets[0].reps
        A_l_values = [r.A_l for r in reps]
        A_sys_values = [r.A_sys for r in reps]
        v_pred_values = [r.v_pred_next for r in reps]
        
        # Availability should decrease (or stay same) monotonically
        for i in range(len(A_l_values) - 1):
            assert A_l_values[i+1] <= A_l_values[i] * 1.01  # Allow tiny numerical noise
            assert A_sys_values[i+1] <= A_sys_values[i] * 1.01
        
        # Predicted velocity should decrease
        for i in range(len(v_pred_values) - 1):
            assert v_pred_values[i+1] < v_pred_values[i]
    
    def test_vl_calculated_correctly(self):
        """Velocity loss percentage is computed correctly."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        
        velocities = [0.50, 0.47, 0.44, 0.41]  # 18% loss
        session = SessionInput(
            sets=[
                SetInput(
                    lift="squat",
                    load_kg=100.0,
                    velocities=velocities,
                    rest_before_sec=None
                )
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0
        )
        
        result = simulate_strength_session(session)
        
        # Expected VL: 1 - (0.41/0.50) = 0.18 = 18%
        expected_vl = 1.0 - (velocities[-1] / velocities[0])
        assert result.sets[0].VL == pytest.approx(expected_vl, abs=0.01)


class TestCrossLiftSpillover:
    """
    Test 2: Cross-lift spillover via A_sys.
    Heavy deadlift set should reduce bench performance via shared A_sys.
    """
    
    def test_system_fatigue_spills_over(self):
        """System fatigue from one lift affects another lift."""
        deadlift_profile = LiftVelocityProfile(lift="deadlift", a=0.50, b=0.0030)
        bench_profile = LiftVelocityProfile(lift="bench", a=0.60, b=0.0028)
        
        # Scenario A: Fresh bench only
        session_fresh = SessionInput(
            sets=[
                SetInput(
                    lift="bench",
                    load_kg=80.0,
                    velocities=[0.50, 0.47, 0.44],
                    rest_before_sec=None
                )
            ],
            profiles={"bench": bench_profile},
            init_A_local={"bench": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0
        )
        
        # Scenario B: Heavy deadlift THEN bench (with minimal rest)
        session_fatigued = SessionInput(
            sets=[
                SetInput(
                    lift="deadlift",
                    load_kg=180.0,
                    velocities=[0.40, 0.36, 0.32],  # Heavy set
                    rest_before_sec=None
                ),
                SetInput(
                    lift="bench",
                    load_kg=80.0,
                    velocities=[0.50, 0.47, 0.44],
                    rest_before_sec=10.0  # Minimal rest - not enough for full recovery
                )
            ],
            profiles={"deadlift": deadlift_profile, "bench": bench_profile},
            init_A_local={"deadlift": 1.0, "bench": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0
        )
        
        result_fresh = simulate_strength_session(session_fresh)
        result_fatigued = simulate_strength_session(session_fatigued)
        
        # Bench set in fatigued scenario should have lower A_sys at start
        fresh_first_rep = result_fresh.sets[0].reps[0]
        fatigued_bench_first_rep = result_fatigued.sets[1].reps[0]
        
        assert fatigued_bench_first_rep.A_sys < fresh_first_rep.A_sys
        
        # Predicted velocity should be lower in fatigued scenario
        assert fatigued_bench_first_rep.v_pred_next < fresh_first_rep.v_pred_next


class TestRestRecovery:
    """
    Test 3: Rest recovery.
    Two identical sets separated by rest should show recovery.
    """
    
    def test_rest_recovery_between_sets(self):
        """Rest period allows partial recovery of availability."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        
        velocities = [0.45, 0.42, 0.39, 0.36]
        
        # Scenario A: No rest between sets
        session_no_rest = SessionInput(
            sets=[
                SetInput(lift="squat", load_kg=100.0, velocities=velocities, rest_before_sec=None),
                SetInput(lift="squat", load_kg=100.0, velocities=velocities, rest_before_sec=5.0)
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.5
        )
        
        # Scenario B: Long rest (180s) between sets
        session_with_rest = SessionInput(
            sets=[
                SetInput(lift="squat", load_kg=100.0, velocities=velocities, rest_before_sec=None),
                SetInput(lift="squat", load_kg=100.0, velocities=velocities, rest_before_sec=180.0)
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.5
        )
        
        result_no_rest = simulate_strength_session(session_no_rest)
        result_with_rest = simulate_strength_session(session_with_rest)
        
        # End of set 1 should have similar fatigue in both scenarios
        A_l_end_set1_no_rest = result_no_rest.sets[0].reps[-1].A_l
        A_l_end_set1_with_rest = result_with_rest.sets[0].reps[-1].A_l
        assert A_l_end_set1_no_rest == pytest.approx(A_l_end_set1_with_rest, abs=0.01)
        
        # Start of set 2 should be better with rest
        A_l_start_set2_no_rest = result_no_rest.sets[1].reps[0].A_l
        A_l_start_set2_with_rest = result_with_rest.sets[1].reps[0].A_l
        
        assert A_l_start_set2_with_rest > A_l_start_set2_no_rest
        
        # System availability should also recover
        A_sys_start_set2_no_rest = result_no_rest.sets[1].reps[0].A_sys
        A_sys_start_set2_with_rest = result_with_rest.sets[1].reps[0].A_sys
        
        assert A_sys_start_set2_with_rest > A_sys_start_set2_no_rest


class TestRMitoEffect:
    """
    Test 4: R_mito effect.
    Higher R_mito should improve recovery during rest.
    """
    
    def test_high_r_mito_improves_recovery(self):
        """Higher recovery capacity leads to better between-set recovery (higher A_M)."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)

        velocities = [0.45, 0.42, 0.39, 0.36]

        # Scenario A: R_mito = 0 (poor recovery capacity)
        session_low = SessionInput(
            sets=[
                SetInput(lift="squat", load_kg=100.0, velocities=velocities, rest_before_sec=None),
                SetInput(lift="squat", load_kg=100.0, velocities=velocities, rest_before_sec=60.0)
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0
        )

        # Scenario B: R_mito = 1.0 (good recovery capacity)
        session_high = SessionInput(
            sets=[
                SetInput(lift="squat", load_kg=100.0, velocities=velocities, rest_before_sec=None),
                SetInput(lift="squat", load_kg=100.0, velocities=velocities, rest_before_sec=60.0)
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=1.0
        )

        result_low = simulate_strength_session(session_low)
        result_high = simulate_strength_session(session_high)

        # Metabolic availability should be higher (more recovered) with higher R_mito
        # This is the primary mechanism - R_mito accelerates metabolic clearance
        A_M_low = result_low.sets[1].reps[0].A_M
        A_M_high = result_high.sets[1].reps[0].A_M

        assert A_M_high > A_M_low, f"R_mito should accelerate metabolic clearance: A_M_low={A_M_low}, A_M_high={A_M_high}"


class TestLiftDifferences:
    """
    Test 5: Lift differences.
    Deadlift should reduce A_sys more than bench for similar normalized y.
    """
    
    def test_deadlift_vs_bench_system_fatigue(self):
        """Deadlift creates more system fatigue than bench press."""
        deadlift_profile = LiftVelocityProfile(lift="deadlift", a=0.50, b=0.0030)
        bench_profile = LiftVelocityProfile(lift="bench", a=0.60, b=0.0028)
        
        # Create scenarios with similar y values (normalized freshness signal)
        # For deadlift at 160kg: v_ref = 0.50 - 0.003*160 = 0.02 -> clamped to 0.05
        # Let's use 140kg: v_ref = 0.50 - 0.003*140 = 0.08
        # v_obs = 0.40 -> y = 0.40/0.08 = 5.0 -> clamped to 1.5
        
        # Actually let's design for y ~ 1.0 (at reference)
        # Deadlift at 100kg: v_ref = 0.50 - 0.30 = 0.20
        # v_obs = 0.20 -> y = 1.0
        
        # Bench at 80kg: v_ref = 0.60 - 0.0028*80 = 0.376
        # v_obs = 0.376 -> y = 1.0
        
        # Use same number of reps with same y progression
        velocities = [1.0, 0.95, 0.90, 0.85]  # Will be scaled by actual v_ref
        
        params = RepEngineParams()
        
        # Scale velocities to actual reference
        dl_v_ref = deadlift_profile.v_ref(140.0)
        bench_v_ref = bench_profile.v_ref(100.0)
        
        dl_velocities = [v * dl_v_ref for v in velocities]
        bench_velocities = [v * bench_v_ref for v in velocities]
        
        session_dl = SessionInput(
            sets=[
                SetInput(lift="deadlift", load_kg=140.0, velocities=dl_velocities, rest_before_sec=None)
            ],
            profiles={"deadlift": deadlift_profile},
            init_A_local={"deadlift": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0
        )
        
        session_bench = SessionInput(
            sets=[
                SetInput(lift="bench", load_kg=100.0, velocities=bench_velocities, rest_before_sec=None)
            ],
            profiles={"bench": bench_profile},
            init_A_local={"bench": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0
        )
        
        result_dl = simulate_strength_session(session_dl)
        result_bench = simulate_strength_session(session_bench)
        
        # Deadlift should reduce A_sys more than bench
        dl_A_sys = result_dl.sets[0].reps[-1].A_sys
        bench_A_sys = result_bench.sets[0].reps[-1].A_sys
        
        assert dl_A_sys < bench_A_sys


class TestDeterminism:
    """
    Test 6: Determinism.
    Same inputs must produce identical outputs.
    """
    
    def test_deterministic_output(self):
        """Running same session twice produces identical results."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        
        session = SessionInput(
            sets=[
                SetInput(
                    lift="squat",
                    load_kg=100.0,
                    velocities=[0.45, 0.42, 0.39, 0.36, 0.33],
                    rest_before_sec=None
                ),
                SetInput(
                    lift="squat",
                    load_kg=100.0,
                    velocities=[0.44, 0.41, 0.38, 0.35],
                    rest_before_sec=120.0
                )
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 0.95},
            init_A_sys=0.98,
            init_M=0.05,
            R_mito=0.5
        )
        
        result1 = simulate_strength_session(session)
        result2 = simulate_strength_session(session)
        
        # Deep comparison
        assert len(result1.sets) == len(result2.sets)
        
        for s1, s2 in zip(result1.sets, result2.sets):
            assert s1.lift == s2.lift
            assert s1.load_kg == s2.load_kg
            assert s1.VL == pytest.approx(s2.VL, abs=1e-10)
            
            assert len(s1.reps) == len(s2.reps)
            for r1, r2 in zip(s1.reps, s2.reps):
                assert r1.v_ref == pytest.approx(r2.v_ref, abs=1e-10)
                assert r1.y == pytest.approx(r2.y, abs=1e-10)
                assert r1.A_l == pytest.approx(r2.A_l, abs=1e-10)
                assert r1.A_sys == pytest.approx(r2.A_sys, abs=1e-10)
                assert r1.A_M == pytest.approx(r2.A_M, abs=1e-10)  # H1: Use A_M instead of M
                assert r1.v_pred_next == pytest.approx(r2.v_pred_next, abs=1e-10)
                assert r1.limiting == r2.limiting

        assert result1.final_A_sys == pytest.approx(result2.final_A_sys, abs=1e-10)
        assert result1.final_A_M == pytest.approx(result2.final_A_M, abs=1e-10)  # H1: Use final_A_M


class TestLimitingFactor:
    """Test classification of limiting factors."""
    
    def test_local_limiting(self):
        """When A_l is lowest, local is limiting."""
        params = RepEngineParams()
        state = RepState(
            A_local_init={"squat": 0.3},  # Very fatigued locally
            A_sys_init=0.9,  # But system is good
            M_init=0.1,  # And metabolic is low
            params=params
        )
        
        limiting = state.get_limiting_factor("squat")
        assert limiting == LimitingFactor.LOCAL
    
    def test_central_limiting(self):
        """When A_sys is lowest, central is limiting."""
        params = RepEngineParams()
        state = RepState(
            A_local_init={"squat": 0.8},
            A_sys_init=0.3,  # Very fatigued system
            M_init=0.1,
            params=params
        )
        
        limiting = state.get_limiting_factor("squat")
        assert limiting == LimitingFactor.CENTRAL
    
    def test_metabolic_limiting(self):
        """When metabolic availability is lowest, metabolic is limiting."""
        # H1: Use high M_init to get low A_M (A_M = exp(-kM*M_init))
        # With kM=0.6 and M_init=3.0, A_M = exp(-1.8) ≈ 0.17
        params = RepEngineParams()
        state = RepState(
            A_local_init={"squat": 0.9},
            A_sys_init=0.9,
            M_init=3.0,  # Legacy conversion gives A_M ≈ 0.17
            params=params
        )

        # Verify A_M is indeed lowest
        assert state.A_M < state.A_local("squat")
        assert state.A_M < state.A_sys

        limiting = state.get_limiting_factor("squat")
        assert limiting == LimitingFactor.METABOLIC


class TestE1RMIntensity:
    """Test that e1RM affects intensity calculation."""
    
    def test_e1rm_affects_phi_calculation(self):
        """Higher relative intensity (load/e1RM) increases fatigue rate."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        
        velocities = [0.45, 0.42, 0.39, 0.36]
        
        # Scenario A: 100kg at 90% of 1RM (e1RM ~111kg)
        session_high_intensity = SessionInput(
            sets=[
                SetInput(lift="squat", load_kg=100.0, velocities=velocities, rest_before_sec=None)
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0,
            e1rm={"squat": 111.0}  # 100/111 = 90% intensity
        )
        
        # Scenario B: 100kg at 70% of 1RM (e1RM ~143kg)
        session_low_intensity = SessionInput(
            sets=[
                SetInput(lift="squat", load_kg=100.0, velocities=velocities, rest_before_sec=None)
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0,
            e1rm={"squat": 143.0}  # 100/143 = 70% intensity
        )
        
        result_high = simulate_strength_session(session_high_intensity)
        result_low = simulate_strength_session(session_low_intensity)
        
        # High intensity should create more fatigue
        A_sys_high = result_high.sets[0].reps[-1].A_sys
        A_sys_low = result_low.sets[0].reps[-1].A_sys
        
        assert A_sys_high < A_sys_low


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_single_rep_set(self):
        """Handle sets with only one rep."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        
        session = SessionInput(
            sets=[
                SetInput(lift="squat", load_kg=100.0, velocities=[0.45], rest_before_sec=None)
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0
        )
        
        result = simulate_strength_session(session)
        
        assert len(result.sets) == 1
        assert len(result.sets[0].reps) == 1
        # VL should be 0 for single rep
        assert result.sets[0].VL == 0.0
    
    def test_empty_velocities(self):
        """Handle empty velocity list."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        
        session = SessionInput(
            sets=[
                SetInput(lift="squat", load_kg=100.0, velocities=[], rest_before_sec=None)
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0
        )
        
        result = simulate_strength_session(session)
        
        assert len(result.sets[0].reps) == 0
        assert result.sets[0].VL == 0.0
    
    def test_missing_profile_defaults(self):
        """Use default profile if lift not in profiles dict."""
        # Don't provide squat profile - should use defaults
        session = SessionInput(
            sets=[
                SetInput(lift="squat", load_kg=100.0, velocities=[0.45, 0.42], rest_before_sec=None)
            ],
            profiles={},  # Empty profiles
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0
        )
        
        # Should not raise error
        result = simulate_strength_session(session)
        assert len(result.sets[0].reps) == 2


class TestMultipleLifts:
    """Test sessions with multiple different lifts."""
    
    def test_complex_session_multiple_lifts(self):
        """Session with squat, bench, and deadlift."""
        profiles = {
            "squat": LiftVelocityProfile(lift="squat", a=0.55, b=0.0032),
            "bench": LiftVelocityProfile(lift="bench", a=0.60, b=0.0028),
            "deadlift": LiftVelocityProfile(lift="deadlift", a=0.50, b=0.0030)
        }
        
        session = SessionInput(
            sets=[
                SetInput(lift="squat", load_kg=140.0, velocities=[0.40, 0.37, 0.34], rest_before_sec=None),
                SetInput(lift="bench", load_kg=100.0, velocities=[0.45, 0.42, 0.39], rest_before_sec=180.0),
                SetInput(lift="deadlift", load_kg=160.0, velocities=[0.35, 0.32], rest_before_sec=300.0)
            ],
            profiles=profiles,
            init_A_local={"squat": 1.0, "bench": 1.0, "deadlift": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.5
        )
        
        result = simulate_strength_session(session)
        
        assert len(result.sets) == 3
        assert result.sets[0].lift == "squat"
        assert result.sets[1].lift == "bench"
        assert result.sets[2].lift == "deadlift"
        
        # Each lift should have its own local fatigue
        assert "squat" in result.final_A_local
        assert "bench" in result.final_A_local
        assert "deadlift" in result.final_A_local
        
        # System fatigue accumulates across all lifts
        assert result.final_A_sys < 1.0
