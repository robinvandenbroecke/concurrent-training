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
    CoachParams,
    SetPrescription,
    ExerciseBlock,
    StrengthWorkout,
    EnduranceSession,
    ConcurrentWorkout,
    WorkoutPlan,
    IntraSetState,
    IntraSetAction,
    determine_workout_type,
    generate_strength_workout,
    generate_endurance_workout,
    generate_workout,
    adapt_workout,
    intra_set_decision,
)


class TestWorkoutTypeDetermination:
    """Test workout type selection based on readiness."""
    
    def test_low_readiness_selects_technique(self):
        """Low readiness triggers technique day."""
        params = CoachParams(readiness_low=0.55)
        
        workout_type = determine_workout_type(0.50, 0.80, params)
        assert workout_type == WorkoutType.TECHNIQUE
    
    def test_high_readiness_selects_strength(self):
        """High readiness allows strength work."""
        params = CoachParams(readiness_low=0.55)
        
        workout_type = determine_workout_type(0.80, 0.80, params)
        assert workout_type == WorkoutType.STRENGTH
    
    def test_system_readiness_affects_selection(self):
        """Low system readiness affects workout type."""
        params = CoachParams(readiness_low=0.55)
        
        workout_type = determine_workout_type(0.80, 0.40, params)
        assert workout_type == WorkoutType.TECHNIQUE


class TestStrengthWorkoutGeneration:
    """Test strength workout generation."""
    
    def test_generates_primary_lifts(self):
        """Workout includes primary lifts."""
        lifts = ["squat", "bench", "deadlift"]
        readiness = {"squat": 0.85, "bench": 0.80, "deadlift": 0.75}
        capacities = {"squat": 150.0, "bench": 100.0, "deadlift": 180.0}
        
        workout, explanations = generate_strength_workout(
            lifts, readiness, capacities, 0.80, 0.20
        )
        
        assert len(workout.blocks) > 0
        assert len(workout.primary_lifts) >= 1
    
    def test_low_system_readiness_reduces_volume(self):
        """Low system readiness reduces number of lifts and volume."""
        lifts = ["squat", "bench", "deadlift"]
        readiness = {"squat": 0.85, "bench": 0.80, "deadlift": 0.75}
        capacities = {"squat": 150.0, "bench": 100.0, "deadlift": 180.0}
        
        workout_low, _ = generate_strength_workout(
            lifts, readiness, capacities, 0.40, 0.20  # Low system
        )
        
        workout_high, _ = generate_strength_workout(
            lifts, readiness, capacities, 0.90, 0.20  # High system
        )
        
        # Low system should have fewer lifts
        assert len(workout_low.blocks) <= len(workout_high.blocks)
        
        # Low system should be technique focus
        assert workout_low.workout_type == WorkoutType.TECHNIQUE
    
    def test_endurance_fatigue_avoids_legs(self):
        """High endurance fatigue avoids heavy leg work."""
        lifts = ["squat", "bench", "deadlift"]
        readiness = {"squat": 0.85, "bench": 0.80, "deadlift": 0.75}
        capacities = {"squat": 150.0, "bench": 100.0, "deadlift": 180.0}
        
        workout, explanations = generate_strength_workout(
            lifts, readiness, capacities, 0.80, 0.60  # High E_fat
        )
        
        # Should avoid squat/deadlift
        primary_lifts = workout.primary_lifts
        assert "squat" not in primary_lifts or len(primary_lifts) == 1
        assert "deadlift" not in primary_lifts or len(primary_lifts) == 1
    
    def test_technique_day_has_lower_load(self):
        """Technique days use lower load percentages."""
        lifts = ["squat"]
        readiness = {"squat": 0.45}  # Low readiness
        capacities = {"squat": 150.0}
        
        workout, _ = generate_strength_workout(
            lifts, readiness, capacities, 0.80, 0.20
        )
        
        assert workout.workout_type == WorkoutType.TECHNIQUE
        
        # Load should be lower
        block = workout.blocks[0]
        for set_presc in block.sets:
            assert set_presc.load_value <= 0.65  # Technique load
    
    def test_strength_workout_has_top_set_and_backoffs(self):
        """Strength workouts include top set and back-off sets."""
        lifts = ["squat"]
        readiness = {"squat": 0.90}  # High readiness
        capacities = {"squat": 150.0}
        
        workout, _ = generate_strength_workout(
            lifts, readiness, capacities, 0.85, 0.10
        )
        
        assert workout.workout_type == WorkoutType.STRENGTH
        
        block = workout.blocks[0]
        # Should have top set (higher load) and back-offs
        assert len(block.sets) >= 2
        assert block.sets[0].load_value > block.sets[1].load_value


class TestEnduranceWorkoutGeneration:
    """Test endurance workout generation."""
    
    def test_low_endurance_readiness_short_z2(self):
        """Low endurance readiness gives short Z2."""
        session, explanations = generate_endurance_workout(
            readiness_endurance=0.40,
            endurance_fatigue=0.30,
            time_budget_minutes=60,
            has_legs_strength_today=False
        )
        
        assert session.session_type == "z2"
        assert session.duration_minutes <= 30
    
    def test_high_fatigue_plus_strength_avoids_hiit(self):
        """High fatigue + strength gives Z2 only."""
        session, explanations = generate_endurance_workout(
            readiness_endurance=0.80,
            endurance_fatigue=0.50,
            time_budget_minutes=60,
            has_legs_strength_today=True
        )
        
        assert session.session_type == "z2"
        assert "avoid" in session.notes.lower() or "avoid" in explanations[0].lower()
    
    def test_good_readiness_allows_hiit(self):
        """Good readiness and low fatigue allows HIIT."""
        session, explanations = generate_endurance_workout(
            readiness_endurance=0.90,
            endurance_fatigue=0.10,
            time_budget_minutes=60,
            has_legs_strength_today=False
        )
        
        assert session.session_type == "hiit"
        assert session.intervals is not None
    
    def test_limited_time_short_hiit(self):
        """Limited time gives short HIIT."""
        session, explanations = generate_endurance_workout(
            readiness_endurance=0.80,
            endurance_fatigue=0.20,
            time_budget_minutes=30,
            has_legs_strength_today=False
        )
        
        assert session.session_type == "hiit"
        assert session.duration_minutes <= 30


class TestFullWorkoutGeneration:
    """Test complete workout generation."""
    
    def test_generate_strength_only(self):
        """Generate strength-only workout."""
        plan, explanations = generate_workout(
            goal_mode=GoalMode.STRENGTH,
            lifts=["squat", "bench"],
            readiness={"squat": 0.85, "bench": 0.80},
            capacities={"squat": 150.0, "bench": 100.0},
            system_readiness=0.80,
            endurance_readiness=0.70,
            endurance_fatigue=0.20,
            time_budget_minutes=60
        )
        
        assert plan.goal_mode == GoalMode.STRENGTH
        assert isinstance(plan.workout, StrengthWorkout)
        assert len(explanations) > 0
    
    def test_generate_endurance_only(self):
        """Generate endurance-only workout."""
        plan, explanations = generate_workout(
            goal_mode=GoalMode.ENDURANCE,
            lifts=["squat", "bench"],
            readiness={"squat": 0.85, "bench": 0.80},
            capacities={"squat": 150.0, "bench": 100.0},
            system_readiness=0.80,
            endurance_readiness=0.85,
            endurance_fatigue=0.20,
            time_budget_minutes=60
        )
        
        assert plan.goal_mode == GoalMode.ENDURANCE
        assert isinstance(plan.workout, EnduranceSession)
    
    def test_generate_concurrent(self):
        """Generate concurrent workout."""
        plan, explanations = generate_workout(
            goal_mode=GoalMode.CONCURRENT,
            lifts=["squat", "bench"],
            readiness={"squat": 0.85, "bench": 0.80},
            capacities={"squat": 150.0, "bench": 100.0},
            system_readiness=0.80,
            endurance_readiness=0.75,
            endurance_fatigue=0.20,
            time_budget_minutes=90
        )
        
        assert plan.goal_mode == GoalMode.CONCURRENT
        assert isinstance(plan.workout, ConcurrentWorkout)
        assert plan.workout.strength is not None
        assert plan.workout.endurance is not None
    
    def test_concurrent_has_recovery_between(self):
        """Concurrent workout specifies recovery between sessions."""
        plan, _ = generate_workout(
            goal_mode=GoalMode.CONCURRENT,
            lifts=["squat", "bench"],
            readiness={"squat": 0.85, "bench": 0.80},
            capacities={"squat": 150.0, "bench": 100.0},
            system_readiness=0.80,
            endurance_readiness=0.75,
            endurance_fatigue=0.20,
            time_budget_minutes=90
        )
        
        assert plan.workout.recovery_between_hours >= 4.0


class TestWorkoutAdaptation:
    """Test workout adaptation based on changed readiness."""
    
    def test_no_change_when_readiness_stable(self):
        """No adaptation when readiness unchanged."""
        original = WorkoutPlan(
            date=date.today(),
            goal_mode=GoalMode.STRENGTH,
            workout=StrengthWorkout(
                workout_type=WorkoutType.STRENGTH,
                blocks=[],
                estimated_duration_minutes=45
            ),
            explanations=["Original plan"],
            readiness_at_generation={"squat": 0.85, "system": 0.80}
        )
        
        adapted = adapt_workout(
            original,
            current_readiness={"squat": 0.84, "system": 0.81},
            system_readiness=0.81
        )
        
        # Should note that we proceed as planned
        assert len(adapted.explanations) >= len(original.explanations)
    
    def test_adaptation_when_readiness_drops(self):
        """Adaptation triggered when readiness drops significantly."""
        original = WorkoutPlan(
            date=date.today(),
            goal_mode=GoalMode.STRENGTH,
            workout=StrengthWorkout(
                workout_type=WorkoutType.STRENGTH,
                blocks=[],
                estimated_duration_minutes=45
            ),
            explanations=["Original plan"],
            readiness_at_generation={"squat": 0.85, "system": 0.80}
        )
        
        adapted = adapt_workout(
            original,
            current_readiness={"squat": 0.60, "system": 0.80},  # Big drop
            system_readiness=0.80
        )
        
        # Should note the adaptation
        assert any("drop" in e.lower() for e in adapted.explanations)


class TestIntraSetDecisions:
    """Test real-time intra-session decisions."""
    
    def test_proceed_when_no_data(self):
        """Proceed when no velocity data yet."""
        state = IntraSetState(
            exercise="squat",
            set_number=1,
            target_reps=5,
            reps_completed=0,
            velocities=[],
            load_kg=140.0,
            rest_before_set=180
        )
        
        prescription = SetPrescription(
            set_number=1,
            target_reps=5,
            load_method=LoadMethod.PERCENT_C,
            load_value=0.90,
            rest_seconds=180,
            vl_max=0.20
        )
        
        action = intra_set_decision(state, prescription)
        
        assert action.action == ActionType.PROCEED
    
    def test_stop_when_velocity_floor_reached(self):
        """Stop set when velocity below floor."""
        state = IntraSetState(
            exercise="squat",
            set_number=1,
            target_reps=5,
            reps_completed=3,
            velocities=[0.45, 0.40, 0.20],  # Last rep very slow
            load_kg=140.0,
            rest_before_set=180
        )
        
        prescription = SetPrescription(
            set_number=1,
            target_reps=5,
            load_method=LoadMethod.PERCENT_C,
            load_value=0.90,
            rest_seconds=180,
            vl_max=0.20
        )
        
        params = CoachParams(velocity_floor=0.25)
        action = intra_set_decision(state, prescription, params)
        
        assert action.action == ActionType.STOP_SET
        assert action.stop_current_set
    
    def test_stop_when_vl_max_reached(self):
        """Stop set when VL exceeds limit."""
        state = IntraSetState(
            exercise="squat",
            set_number=1,
            target_reps=5,
            reps_completed=3,
            velocities=[0.50, 0.40, 0.35],  # 30% VL
            load_kg=140.0,
            rest_before_set=180
        )
        
        prescription = SetPrescription(
            set_number=1,
            target_reps=5,
            load_method=LoadMethod.PERCENT_C,
            load_value=0.90,
            rest_seconds=180,
            vl_max=0.20
        )
        
        params = CoachParams(vl_stop_threshold=0.30)
        action = intra_set_decision(state, prescription, params)
        
        # VL = (0.50-0.35)/0.50 = 0.30 = 30%, at threshold
        assert action.action == ActionType.STOP_SET
    
    def test_increase_load_when_vl_low(self):
        """Increase load next set when VL very low."""
        state = IntraSetState(
            exercise="squat",
            set_number=1,
            target_reps=5,
            reps_completed=5,
            velocities=[0.50, 0.48, 0.47, 0.46, 0.45],  # Only 10% VL
            load_kg=140.0,
            rest_before_set=180
        )
        
        prescription = SetPrescription(
            set_number=1,
            target_reps=5,
            load_method=LoadMethod.PERCENT_C,
            load_value=0.90,
            rest_seconds=180,
            vl_max=0.20
        )
        
        action = intra_set_decision(state, prescription)
        
        assert action.action == ActionType.INCREASE_LOAD
        assert action.load_adjustment_percent > 0
    
    def test_decrease_load_when_vl_high(self):
        """Decrease load next set when VL high but not exceeding stop threshold."""
        state = IntraSetState(
            exercise="squat",
            set_number=1,
            target_reps=5,
            reps_completed=5,
            velocities=[0.50, 0.44, 0.40, 0.38, 0.36],  # 28% VL - high but under stop threshold
            load_kg=140.0,
            rest_before_set=180
        )

        prescription = SetPrescription(
            set_number=1,
            target_reps=5,
            load_method=LoadMethod.PERCENT_C,
            load_value=0.90,
            rest_seconds=180,
            vl_max=0.30  # Higher VL max so we don't stop
        )

        params = CoachParams(vl_stop_threshold=0.35)  # Higher stop threshold
        action = intra_set_decision(state, prescription, params)

        assert action.action == ActionType.DECREASE_LOAD
        assert action.load_adjustment_percent < 0
    
    def test_next_exercise_when_target_hit(self):
        """Move to next exercise when target reps completed with good VL."""
        state = IntraSetState(
            exercise="squat",
            set_number=1,
            target_reps=5,
            reps_completed=5,
            velocities=[0.50, 0.46, 0.44, 0.42, 0.40],  # 20% VL
            load_kg=140.0,
            rest_before_set=180
        )
        
        prescription = SetPrescription(
            set_number=1,
            target_reps=5,
            load_method=LoadMethod.PERCENT_C,
            load_value=0.90,
            rest_seconds=180,
            vl_max=0.25
        )
        
        action = intra_set_decision(state, prescription)
        
        assert action.action == ActionType.NEXT_EXERCISE


class TestDeterminism:
    """Test deterministic behavior."""
    
    def test_same_inputs_same_workout(self):
        """Same inputs produce identical workouts."""
        lifts = ["squat", "bench"]
        readiness = {"squat": 0.85, "bench": 0.80}
        capacities = {"squat": 150.0, "bench": 100.0}
        
        plan1, _ = generate_workout(
            GoalMode.STRENGTH, lifts, readiness, capacities,
            0.80, 0.70, 0.20, 60
        )
        
        plan2, _ = generate_workout(
            GoalMode.STRENGTH, lifts, readiness, capacities,
            0.80, 0.70, 0.20, 60
        )
        
        assert plan1.goal_mode == plan2.goal_mode
        assert len(plan1.workout.blocks) == len(plan2.workout.blocks)
        assert plan1.workout.workout_type == plan2.workout.workout_type


class TestExplanations:
    """Test that explanations are generated."""
    
    def test_strength_workout_has_explanations(self):
        """Strength workout includes explanations."""
        _, explanations = generate_strength_workout(
            lifts=["squat", "bench"],
            readiness={"squat": 0.85, "bench": 0.80},
            capacities={"squat": 150.0, "bench": 100.0},
            system_readiness=0.80,
            endurance_fatigue=0.20
        )
        
        assert len(explanations) > 0
        # Should mention readiness
        assert any("readiness" in e.lower() for e in explanations)
    
    def test_endurance_workout_has_explanations(self):
        """Endurance workout includes explanations."""
        _, explanations = generate_endurance_workout(
            readiness_endurance=0.60,
            endurance_fatigue=0.30,
            time_budget_minutes=60,
            has_legs_strength_today=False
        )
        
        assert len(explanations) > 0
    
    def test_full_plan_has_explanations(self):
        """Full workout plan includes explanations."""
        plan, _ = generate_workout(
            goal_mode=GoalMode.CONCURRENT,
            lifts=["squat", "bench"],
            readiness={"squat": 0.85, "bench": 0.80},
            capacities={"squat": 150.0, "bench": 100.0},
            system_readiness=0.80,
            endurance_readiness=0.75,
            endurance_fatigue=0.20,
            time_budget_minutes=90
        )
        
        assert len(plan.explanations) > 0
        assert len(plan.explanations) >= 2  # Should have both strength and endurance notes
