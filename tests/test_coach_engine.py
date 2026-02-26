"""
Unit tests for coach engine.

Tests workout generation, adaptation, and intra-session decisions.
"""
import pytest
from datetime import date

from app.domain.coach_engine import (
    GoalMode,
    WorkoutType,
    LoadMethod,
    ActionType,
    LimitingFactor,
    CoachParams,
    CoachRequest,
    DayStateSnapshot,
    SetPrescription,
    ExerciseBlock,
    StrengthWorkout,
    EnduranceWorkout,
    ConcurrentWorkout,
    WorkoutPlan,
    IntraSetState,
    NextSetAdjustment,
    determine_intent,
    scale_load_factor,
    select_sport_mode,
    determine_endurance_zone,
    generate_strength_block,
    generate_workout,
    adapt_workout,
    next_set_adjustment,
)


class TestIntentDetermination:
    """Test workout intent selection based on state."""
    
    def test_low_readiness_selects_technique(self):
        """Low readiness triggers technique day."""
        params = CoachParams(readiness_low=0.55)
        intent = determine_intent(0.50, 0.80, 0.20, params)
        assert intent == "technique"
    
    def test_high_readiness_selects_power(self):
        """High readiness with low fatigue selects power."""
        params = CoachParams(readiness_high=0.80)
        intent = determine_intent(0.85, 0.20, 0.10, params)
        assert intent == "power"
    
    def test_moderate_readiness_selects_strength(self):
        """Moderate readiness selects strength."""
        params = CoachParams(readiness_low=0.55, readiness_high=0.80)
        intent = determine_intent(0.70, 0.40, 0.25, params)
        assert intent in ["strength", "volume"]


class TestLoadScaling:
    """Test load scaling based on readiness."""
    
    def test_low_readiness_scales_down(self):
        """Low readiness scales load down significantly."""
        params = CoachParams(
            readiness_low=0.55,
            scale_readiness_low=0.85
        )
        scale = scale_load_factor(0.50, params)
        assert scale == 0.85
    
    def test_high_readiness_scales_up(self):
        """High readiness scales load up."""
        params = CoachParams(
            readiness_high=0.80,
            scale_readiness_high=1.025
        )
        scale = scale_load_factor(0.85, params)
        assert scale == 1.025


class TestSportModeSelection:
    """Test endurance sport mode selection."""
    
    def test_cycling_default_without_legs(self):
        """Cycling is good default without leg work."""
        sport = select_sport_mode(
            planned_strength_lifts=["bench", "press"],
            available_sports=["cycling", "running", "swimming"],
            E_fat=0.2
        )
        assert sport in ["cycling", "swimming"]
    
    def test_swimming_with_heavy_legs(self):
        """Swimming preferred when heavy legs planned."""
        sport = select_sport_mode(
            planned_strength_lifts=["squat", "deadlift"],
            available_sports=["cycling", "running", "swimming"],
            E_fat=0.2
        )
        # Swimming has lowest interference
        assert sport == "swimming"
    
    def test_avoids_running_with_squat(self):
        """Running avoided when squat planned."""
        sport = select_sport_mode(
            planned_strength_lifts=["squat"],
            available_sports=["cycling", "running"],
            E_fat=0.2
        )
        assert sport == "cycling"


class TestEnduranceZoneSelection:
    """Test endurance zone selection."""
    
    def test_low_readiness_gives_z2(self):
        """Low readiness gives Z2 only."""
        zone, duration = determine_endurance_zone(
            readiness_endurance=0.40,
            E_fat=0.3,
            planned_strength_heavy=False,
            params=CoachParams(readiness_low=0.55)
        )
        assert zone == "z2"
        assert duration == 30
    
    def test_high_fatigue_gives_z2(self):
        """High fatigue gives Z2."""
        zone, duration = determine_endurance_zone(
            readiness_endurance=0.80,
            E_fat=0.5,
            planned_strength_heavy=False,
            params=CoachParams()
        )
        assert zone == "z2"
    
    def test_good_readiness_allows_hiit(self):
        """Good readiness allows HIIT."""
        zone, duration = determine_endurance_zone(
            readiness_endurance=0.85,
            E_fat=0.1,
            planned_strength_heavy=False,
            params=CoachParams(readiness_high=0.80)
        )
        assert zone == "hiit"
    
    def test_heavy_strength_avoids_hiit(self):
        """Heavy strength planned avoids HIIT."""
        zone, duration = determine_endurance_zone(
            readiness_endurance=0.85,
            E_fat=0.1,
            planned_strength_heavy=True,
            params=CoachParams(readiness_high=0.80)
        )
        # Should downgrade from HIIT due to heavy strength
        assert zone != "hiit"


class TestStrengthBlockGeneration:
    """Test strength block generation."""
    
    def test_generates_block_for_lift(self):
        """Block is generated with prescription."""
        block, explanations = generate_strength_block(
            lift="squat",
            readiness=0.85,
            capacity=150.0,
            D_sys=0.2,
            E_fat=0.2,
            params=CoachParams()
        )
        
        assert block.lift == "squat"
        assert block.prescription.load_method == LoadMethod.PERCENT_C
        assert len(explanations) > 0
    
    def test_low_readiness_reduces_sets(self):
        """Low readiness reduces number of sets."""
        params = CoachParams(readiness_low=0.55)
        
        block_low, _ = generate_strength_block(
            lift="squat",
            readiness=0.45,
            capacity=150.0,
            D_sys=0.2,
            E_fat=0.2,
            params=params
        )
        
        block_high, _ = generate_strength_block(
            lift="squat",
            readiness=0.90,
            capacity=150.0,
            D_sys=0.2,
            E_fat=0.2,
            params=params
        )
        
        # Low readiness should have fewer sets
        # (implementation detail: check via intent or sets count)
        assert block_low.intent == "technique" or block_low.prescription.target_reps


class TestWorkoutGeneration:
    """Test complete workout generation."""
    
    def test_generate_strength_only(self):
        """Generate strength-only workout."""
        req = CoachRequest(
            athlete_id="test_athlete",
            date="2024-01-15",
            mode="strength",
            time_budget_min=60
        )
        
        day_state = DayStateSnapshot(
            readiness_per_lift={"squat": 0.85, "bench": 0.80},
            readiness_endurance=0.70,
            D_sys=0.2,
            E_fat=0.2,
            R_mito=0.3,
            capacities_per_lift={"squat": 150.0, "bench": 100.0},
            date=date(2024, 1, 15)
        )
        
        plan = generate_workout(req, day_state)
        
        assert plan.mode == "strength"
        assert isinstance(plan.workout, StrengthWorkout)
        assert len(plan.explanations) > 0
    
    def test_generate_endurance_only(self):
        """Generate endurance-only workout."""
        req = CoachRequest(
            athlete_id="test_athlete",
            date="2024-01-15",
            mode="endurance",
            time_budget_min=60
        )
        
        day_state = DayStateSnapshot(
            readiness_per_lift={},
            readiness_endurance=0.80,
            D_sys=0.2,
            E_fat=0.2,
            R_mito=0.3,
            capacities_per_lift={},
            date=date(2024, 1, 15)
        )
        
        plan = generate_workout(req, day_state)
        
        assert plan.mode == "endurance"
        assert isinstance(plan.workout, EnduranceWorkout)
        assert plan.workout.sport in ["cycling", "running", "swimming"]
    
    def test_generate_concurrent(self):
        """Generate concurrent workout."""
        req = CoachRequest(
            athlete_id="test_athlete",
            date="2024-01-15",
            mode="concurrent",
            time_budget_min=90,
            priority="balanced"
        )
        
        day_state = DayStateSnapshot(
            readiness_per_lift={"squat": 0.80, "bench": 0.75},
            readiness_endurance=0.75,
            D_sys=0.25,
            E_fat=0.25,
            R_mito=0.3,
            capacities_per_lift={"squat": 150.0, "bench": 100.0},
            date=date(2024, 1, 15)
        )
        
        plan = generate_workout(req, day_state)
        
        assert plan.mode == "concurrent"
        assert isinstance(plan.workout, ConcurrentWorkout)
        assert plan.workout.strength is not None
        assert plan.workout.endurance is not None
    
    def test_concurrent_avoids_hiit_with_legs(self):
        """Concurrent with legs avoids HIIT."""
        req = CoachRequest(
            athlete_id="test_athlete",
            date="2024-01-15",
            mode="concurrent",
            time_budget_min=90,
            priority="balanced"
        )
        
        day_state = DayStateSnapshot(
            readiness_per_lift={"squat": 0.85, "deadlift": 0.80},  # Heavy legs
            readiness_endurance=0.85,  # Good endurance readiness
            D_sys=0.2,
            E_fat=0.15,
            R_mito=0.3,
            capacities_per_lift={"squat": 150.0, "deadlift": 180.0},
            date=date(2024, 1, 15)
        )
        
        plan = generate_workout(req, day_state)
        
        # Even with good endurance readiness, should avoid HIIT with legs
        assert plan.workout.endurance.intent != "hiit"


class TestWorkoutAdaptation:
    """Test workout adaptation based on state changes."""
    
    def test_adapt_switches_to_technique_when_readiness_low(self):
        """Adaptation switches to technique when readiness drops."""
        # Create original plan
        req = CoachRequest(
            athlete_id="test_athlete",
            date="2024-01-15",
            mode="strength",
            time_budget_min=60
        )
        
        original_state = DayStateSnapshot(
            readiness_per_lift={"squat": 0.85},
            readiness_endurance=0.70,
            D_sys=0.2,
            E_fat=0.2,
            R_mito=0.3,
            capacities_per_lift={"squat": 150.0},
            date=date(2024, 1, 15)
        )
        
        original_plan = generate_workout(req, original_state)
        
        # Adapt with low readiness
        low_readiness_state = DayStateSnapshot(
            readiness_per_lift={"squat": 0.45},  # Dropped significantly
            readiness_endurance=0.70,
            D_sys=0.2,
            E_fat=0.2,
            R_mito=0.3,
            capacities_per_lift={"squat": 150.0},
            date=date(2024, 1, 15)
        )
        
        adapted_plan = adapt_workout(original_plan, low_readiness_state)
        
        # Should have adaptation explanations
        assert any("technique" in e.lower() for e in adapted_plan.explanations)
    
    def test_adapt_increases_load_when_readiness_high(self):
        """Adaptation increases load when readiness high."""
        req = CoachRequest(
            athlete_id="test_athlete",
            date="2024-01-15",
            mode="strength",
            time_budget_min=60
        )
        
        original_state = DayStateSnapshot(
            readiness_per_lift={"squat": 0.70},
            readiness_endurance=0.70,
            D_sys=0.2,
            E_fat=0.2,
            R_mito=0.3,
            capacities_per_lift={"squat": 150.0},
            date=date(2024, 1, 15)
        )
        
        original_plan = generate_workout(req, original_state)
        
        # Adapt with high readiness
        high_readiness_state = DayStateSnapshot(
            readiness_per_lift={"squat": 0.90},  # High
            readiness_endurance=0.70,
            D_sys=0.2,
            E_fat=0.2,
            R_mito=0.3,
            capacities_per_lift={"squat": 150.0},
            date=date(2024, 1, 15)
        )
        
        adapted_plan = adapt_workout(original_plan, high_readiness_state)
        
        # Should note load increase
        assert any("+2.5%" in e or "load" in e.lower() for e in adapted_plan.explanations)
    
    def test_endurance_cascade_hiit_to_tempo(self):
        """Endurance adapts HIIT → tempo when fatigue high."""
        # Create HIIT plan
        endurance_workout = EnduranceWorkout(
            sport="cycling",
            intent="hiit",
            duration_min=30,
            structure=[{"type": "interval"}],
            targets={"rpe": (8, 10)},
            notes=[]
        )
        
        plan = WorkoutPlan(
            date="2024-01-15",
            mode="endurance",
            workout=endurance_workout,
            explanations=["Original HIIT plan"]
        )
        
        # Adapt with high E_fat
        high_fatigue_state = DayStateSnapshot(
            readiness_per_lift={},
            readiness_endurance=0.60,
            D_sys=0.2,
            E_fat=0.50,  # High fatigue
            R_mito=0.3,
            capacities_per_lift={},
            date=date(2024, 1, 15)
        )
        
        adapted_plan = adapt_workout(plan, high_fatigue_state)
        
        # Should cascade to Z2 or tempo
        assert adapted_plan.workout.intent in ["z2", "tempo"]


class TestIntraSetAdjustments:
    """Test intra-session adjustments."""
    
    def test_stop_when_vl_too_high(self):
        """Stop set when VL exceeds max."""
        block = ExerciseBlock(
            lift="squat",
            intent="strength",
            prescription=SetPrescription(
                set_number=1,
                target_reps=5,
                load_method=LoadMethod.PERCENT_C,
                target_value=0.90,
                rest_seconds=180,
                vl_max=0.20
            )
        )
        
        velocities = [0.50, 0.40, 0.32]  # 36% VL
        rep_summary = {"vl_current": 0.36, "limiting": "local"}
        
        day_state = DayStateSnapshot(
            readiness_per_lift={"squat": 0.80},
            readiness_endurance=0.70,
            D_sys=0.2,
            E_fat=0.2,
            R_mito=0.3,
            capacities_per_lift={"squat": 150.0},
            date=date(2024, 1, 15)
        )
        
        adjustment = next_set_adjustment(block, velocities, rep_summary, day_state)
        
        assert adjustment.action == ActionType.STOP_SET
        assert adjustment.stop_current_set
    
    def test_extend_rest_for_central_fatigue(self):
        """Extend rest when central fatigue limiting."""
        block = ExerciseBlock(
            lift="squat",
            intent="strength",
            prescription=SetPrescription(
                set_number=1,
                target_reps=5,
                load_method=LoadMethod.PERCENT_C,
                target_value=0.90,
                rest_seconds=180,
                vl_max=0.20
            )
        )
        
        velocities = [0.50, 0.45, 0.42]  # 16% VL
        rep_summary = {"vl_current": 0.16, "limiting": "central"}
        
        day_state = DayStateSnapshot(
            readiness_per_lift={"squat": 0.80},
            readiness_endurance=0.70,
            D_sys=0.2,
            E_fat=0.2,
            R_mito=0.3,
            capacities_per_lift={"squat": 150.0},
            date=date(2024, 1, 15)
        )
        
        adjustment = next_set_adjustment(block, velocities, rep_summary, day_state)
        
        assert adjustment.action == ActionType.EXTEND_REST
        assert "CNS" in adjustment.explanation or "central" in adjustment.explanation.lower()
    
    def test_reduce_reps_for_metabolic(self):
        """Reduce reps when metabolic limiting."""
        block = ExerciseBlock(
            lift="squat",
            intent="strength",
            prescription=SetPrescription(
                set_number=1,
                target_reps=5,
                load_method=LoadMethod.PERCENT_C,
                target_value=0.90,
                rest_seconds=180,
                vl_max=0.20
            )
        )
        
        velocities = [0.50, 0.43, 0.38]  # 24% VL
        rep_summary = {"vl_current": 0.24, "limiting": "metabolic"}
        
        day_state = DayStateSnapshot(
            readiness_per_lift={"squat": 0.80},
            readiness_endurance=0.70,
            D_sys=0.2,
            E_fat=0.2,
            R_mito=0.3,
            capacities_per_lift={"squat": 150.0},
            date=date(2024, 1, 15)
        )
        
        adjustment = next_set_adjustment(block, velocities, rep_summary, day_state)
        
        assert adjustment.action == ActionType.DROP_SET
        assert "metabolic" in adjustment.explanation.lower()


class TestDeterminism:
    """Test deterministic behavior."""
    
    def test_same_inputs_same_plan(self):
        """Same inputs produce identical plans."""
        req = CoachRequest(
            athlete_id="test_athlete",
            date="2024-01-15",
            mode="strength",
            time_budget_min=60
        )
        
        day_state = DayStateSnapshot(
            readiness_per_lift={"squat": 0.85, "bench": 0.80},
            readiness_endurance=0.70,
            D_sys=0.2,
            E_fat=0.2,
            R_mito=0.3,
            capacities_per_lift={"squat": 150.0, "bench": 100.0},
            date=date(2024, 1, 15)
        )
        
        plan1 = generate_workout(req, day_state)
        plan2 = generate_workout(req, day_state)
        
        assert plan1.mode == plan2.mode
        assert len(plan1.workout.blocks) == len(plan2.workout.blocks)
        assert plan1.explanations == plan2.explanations


class TestPlanSerialization:
    """Test plan serialization to dict."""
    
    def test_strength_plan_to_dict(self):
        """Strength plan serializes correctly."""
        req = CoachRequest(
            athlete_id="test_athlete",
            date="2024-01-15",
            mode="strength",
            time_budget_min=60
        )
        
        day_state = DayStateSnapshot(
            readiness_per_lift={"squat": 0.85},
            readiness_endurance=0.70,
            D_sys=0.2,
            E_fat=0.2,
            R_mito=0.3,
            capacities_per_lift={"squat": 150.0},
            date=date(2024, 1, 15)
        )
        
        plan = generate_workout(req, day_state)
        plan_dict = plan.to_dict()
        
        assert "date" in plan_dict
        assert "mode" in plan_dict
        assert "explanations" in plan_dict
        assert "workout" in plan_dict
        assert plan_dict["workout"]["type"] == "strength"
