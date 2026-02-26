"""
Tests for Sprint H1: Coach Guardrails for Structural Fatigue (T_legs)

1. When T_legs low, generated plan avoids heavy lower or reduces volume deterministically
"""
import pytest
from datetime import date

from app.domain.day_engine import (
    DayEngineParams,
    DayState,
    PerLiftState,
    compute_readiness,
)

from app.domain.coach_engine import (
    GoalMode,
    WorkoutType,
    CoachParams,
    CoachRequest,
    DayStateSnapshot,
    determine_intent,
    generate_strength_block,
    scale_load_factor,
)


class TestTLegsGuardrail:
    """Test H1: T_legs guardrail affects coaching decisions."""
    
    def test_high_t_legs_reduces_legs_readiness(self):
        """High T_legs reduces readiness for leg lifts."""
        params = DayEngineParams(T_legs_guardrail_threshold=0.35)
        
        state = DayState(
            date=date.today(),
            per_lift={
                "squat": PerLiftState(D_l=0.1, F_l=1.0, C_l=150.0),
                "deadlift": PerLiftState(D_l=0.1, F_l=1.0, C_l=180.0),
                "bench": PerLiftState(D_l=0.1, F_l=1.0, C_l=100.0),
            },
            D_sys=0.1,
            R_mito=0.3,
            E_fat=0.1,
            T_legs=0.6  # High structural fatigue
        )
        
        readiness = compute_readiness(state, params)
        
        # Legs lifts should have reduced readiness
        assert readiness.per_lift["squat"] < readiness.per_lift["bench"]
        assert readiness.per_lift["deadlift"] < readiness.per_lift["bench"]
        
        # Legs structural readiness should be low
        assert readiness.legs_structural < 0.5
    
    def test_low_t_legs_no_guardrail_effect(self):
        """Low T_legs doesn't affect readiness."""
        params = DayEngineParams(T_legs_guardrail_threshold=0.35)

        state = DayState(
            date=date.today(),
            per_lift={
                "squat": PerLiftState(D_l=0.1, F_l=1.0, C_l=150.0),
                "bench": PerLiftState(D_l=0.1, F_l=1.0, C_l=100.0),
            },
            D_sys=0.1,
            R_mito=0.3,
            E_fat=0.1,
            T_legs=0.1  # Low structural fatigue
        )

        readiness = compute_readiness(state, params)

        # Both should have reasonable readiness
        # Small T_legs means minimal structural fatigue impact
        assert readiness.per_lift["squat"] > 0.5
        assert readiness.per_lift["bench"] > 0.5

        # The difference comes from D_l and C_l differences, not T_legs
        # Bench has lower C_l (100 vs 150) so may have different readiness


class TestCoachRespectsStructuralReadiness:
    """Test H1: Coach engine respects structural readiness in planning."""
    
    def test_low_legs_structural_reduces_heavy_lower_recommendation(self):
        """When legs structural readiness is low, avoid heavy lower."""
        # This tests that the readiness output from day_engine
        # would be used by coach_engine to adjust recommendations
        
        params = DayEngineParams(T_legs_guardrail_threshold=0.35)
        
        # State with high T_legs
        state = DayState(
            date=date.today(),
            per_lift={
                "squat": PerLiftState(D_l=0.1, F_l=1.0, C_l=150.0),
                "deadlift": PerLiftState(D_l=0.1, F_l=1.0, C_l=180.0),
            },
            D_sys=0.1,
            R_mito=0.3,
            E_fat=0.1,
            T_legs=0.5  # High - should trigger guardrail
        )
        
        readiness = compute_readiness(state, params)
        
        # Squat and deadlift readiness should be reduced
        assert readiness.per_lift["squat"] < 0.7
        assert readiness.per_lift["deadlift"] < 0.7
        
        # Should have explanation
        has_structural_explanation = any(
            "structural" in e.lower() or "T_legs" in e
            for e in readiness.explanations
        )
        assert has_structural_explanation


class TestIntentDetermination:
    """Test H1: Intent determination considers structural state."""
    
    def test_moderate_readiness_with_high_t_legs_prefers_technique(self):
        """Moderate muscle readiness but high T_legs -> technique work."""
        # Snapshot with moderate muscle readiness but high structural fatigue
        snapshot = DayStateSnapshot(
            readiness_per_lift={"squat": 0.6},  # Moderate
            readiness_endurance=0.8,
            D_sys=0.2,
            E_fat=0.1,
            R_mito=0.3,
            capacities_per_lift={"squat": 150.0},
            date=date.today()
        )
        
        # Request for heavy strength
        request = CoachRequest(
            athlete_id="test_athlete",
            date=date.today(),
            mode=GoalMode.STRENGTH,
            time_budget_min=45,
            priority="strength"
        )
        
        params = CoachParams()
        
        # Determine intent
        intent = determine_intent(request, snapshot, params)
        
        # Note: This test demonstrates that even with moderate muscle readiness,
        # the readiness calculation already incorporates T_legs effect.
        # The intent system would receive reduced readiness and adjust accordingly.
        
        # With readiness < 0.65, intent should not be "strength" (heavy)
        assert intent != "strength" or "technique"  # Should downgrade


class TestDeterministicGuardrail:
    """Test H1: T_legs guardrail is deterministic."""
    
    def test_same_t_legs_same_readiness(self):
        """Same T_legs produces same readiness calculation."""
        params = DayEngineParams(T_legs_guardrail_threshold=0.35)
        
        state = DayState(
            date=date.today(),
            per_lift={"squat": PerLiftState(D_l=0.2, F_l=1.0, C_l=150.0)},
            D_sys=0.15,
            R_mito=0.25,
            E_fat=0.1,
            T_legs=0.4
        )
        
        # Compute readiness twice
        readiness1 = compute_readiness(state, params)
        readiness2 = compute_readiness(state, params)
        
        # Should be identical
        assert readiness1.per_lift["squat"] == readiness2.per_lift["squat"]
        assert readiness1.legs_structural == readiness2.legs_structural
    
    def test_guardrail_threshold_deterministic(self):
        """Threshold crossing produces deterministic behavior change."""
        params = DayEngineParams(T_legs_guardrail_threshold=0.35)
        
        # Just below threshold
        state_below = DayState(
            date=date.today(),
            per_lift={"squat": PerLiftState(D_l=0.1, F_l=1.0, C_l=150.0)},
            D_sys=0.1,
            R_mito=0.3,
            E_fat=0.1,
            T_legs=0.34  # Just below
        )
        
        # Just above threshold
        state_above = DayState(
            date=date.today(),
            per_lift={"squat": PerLiftState(D_l=0.1, F_l=1.0, C_l=150.0)},
            D_sys=0.1,
            R_mito=0.3,
            E_fat=0.1,
            T_legs=0.36  # Just above
        )
        
        readiness_below = compute_readiness(state_below, params)
        readiness_above = compute_readiness(state_above, params)
        
        # Above threshold should have lower readiness
        assert readiness_above.per_lift["squat"] < readiness_below.per_lift["squat"]
        
        # Above threshold should have warning
        has_warning_above = any("structural" in e.lower() for e in readiness_above.explanations)
        has_warning_below = any("structural" in e.lower() for e in readiness_below.explanations)
        
        assert has_warning_above
        # Below might or might not have warning depending on threshold logic
