"""
Tests for goal engine.

Tests phase scheduling, macrocycle creation, and goal state management.
"""
import pytest
from datetime import date, timedelta

from app.domain.goal_engine import (
    GoalType,
    PhaseType,
    ConcurrentTarget,
    StrengthTarget,
    EnduranceTarget,
    GoalConstraints,
    GoalConfig,
    PhasePlan,
    MacrocycleContext,
    GoalState,
    compute_phase_durations,
    create_macrocycle,
    create_goal_state,
    advance_goal_state,
    get_block_type_for_phase,
    get_microcycle_targets_for_phase,
    should_prioritize_lift_for_goal,
    get_endurance_focus_for_goal,
)


class TestPhaseDurations:
    """Test phase duration computation based on time to event."""
    
    def test_12_week_schedule(self):
        """12+ weeks: full macrocycle with 6w base, 4w build, 1w peak, 1w taper."""
        durations = compute_phase_durations(84)  # Exactly 12 weeks
        
        assert durations[PhaseType.BASE] == 6
        assert durations[PhaseType.BUILD] == 4
        assert durations[PhaseType.PEAK] == 1
        assert durations[PhaseType.TAPER] == 1
        assert sum(durations.values()) == 12
    
    def test_10_week_schedule(self):
        """10 weeks: compressed with 4w base, 3w build."""
        durations = compute_phase_durations(70)  # 10 weeks
        
        assert durations[PhaseType.BASE] == 4
        assert durations[PhaseType.BUILD] == 3
        assert durations[PhaseType.PEAK] == 1
        assert durations[PhaseType.TAPER] == 1
    
    def test_6_week_schedule(self):
        """6 weeks: minimal base with 2w base, 2w build."""
        durations = compute_phase_durations(42)  # 6 weeks
        
        assert durations[PhaseType.BASE] == 2
        assert durations[PhaseType.BUILD] == 2
        assert durations[PhaseType.PEAK] == 1
        assert durations[PhaseType.TAPER] == 1
    
    def test_5_week_schedule(self):
        """5 weeks: minimal base with 2w base, 1w build."""
        durations = compute_phase_durations(35)  # 5 weeks
        
        assert durations[PhaseType.BASE] == 2
        assert durations[PhaseType.BUILD] == 1
        assert durations[PhaseType.PEAK] == 1
        assert durations[PhaseType.TAPER] == 1
    
    def test_3_week_crash_prep(self):
        """3 weeks: crash prep with minimal base."""
        durations = compute_phase_durations(21)  # 3 weeks
        
        # Should have at least build, peak, taper
        assert PhaseType.BUILD in durations
        assert PhaseType.PEAK in durations
        assert PhaseType.TAPER in durations


class TestMacrocycleCreation:
    """Test macrocycle creation."""
    
    def test_strength_peak_macrocycle(self):
        """Create macrocycle for strength peak goal."""
        goal = GoalConfig(
            goal_id="strength_test_2024",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength",
            strength_targets=[
                StrengthTarget(lift="squat", metric="1rm", target_value=180)
            ]
        )
        
        macrocycle = create_macrocycle(goal)
        
        assert len(macrocycle.phases) == 4
        assert macrocycle.phases[0].phase_type == PhaseType.BASE
        assert macrocycle.phases[-1].phase_type == PhaseType.TAPER
        
        # Check phase targets for strength
        base_phase = macrocycle.phases[0]
        assert base_phase.target_sets_per_week == 15
        assert base_phase.target_intensity == 0.75
    
    def test_endurance_event_macrocycle(self):
        """Create macrocycle for endurance event goal."""
        goal = GoalConfig(
            goal_id="5k_race_2024",
            athlete_id="athlete_1",
            goal_type=GoalType.ENDURANCE_EVENT,
            target_date=date.today() + timedelta(days=70),
            priority="endurance",
            endurance_targets=[
                EnduranceTarget(sport="running", event_type="5k", target_value=20.0)
            ]
        )
        
        macrocycle = create_macrocycle(goal)
        
        assert len(macrocycle.phases) == 4
        
        # Check base phase has HIIT allowance for endurance
        base_phase = macrocycle.phases[0]
        assert base_phase.target_hiit_sessions == 1
    
    def test_concurrent_event_macrocycle(self):
        """Create macrocycle for concurrent event goal."""
        goal = GoalConfig(
            goal_id="hybrid_goal_2024",
            athlete_id="athlete_1",
            goal_type=GoalType.CONCURRENT_EVENT,
            target_date=date.today() + timedelta(days=56),
            priority="balanced",
            concurrent_target=ConcurrentTarget.STRONG_AND_DURABLE
        )
        
        macrocycle = create_macrocycle(goal)
        
        assert len(macrocycle.phases) == 4
        
        # Balanced should have moderate targets
        base_phase = macrocycle.phases[0]
        assert base_phase.target_sets_per_week == 10
    
    def test_schedule_fits_exactly_to_target_date(self):
        """Macrocycle ends exactly on target date."""
        target = date.today() + timedelta(days=70)
        goal = GoalConfig(
            goal_id="test_goal",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=target,
            priority="strength"
        )

        macrocycle = create_macrocycle(goal)

        # Last phase should end on or very close to target date (within rounding)
        last_phase = macrocycle.phases[-1]
        date_diff = abs((last_phase.end_date - target).days)
        assert date_diff <= 1, f"Last phase ends {date_diff} days from target"


class TestGoalState:
    """Test goal state management."""
    
    def test_create_initial_goal_state(self):
        """Create initial goal state from macrocycle."""
        goal = GoalConfig(
            goal_id="test_goal",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        
        macrocycle = create_macrocycle(goal)
        state = create_goal_state(goal, macrocycle)
        
        assert state.goal_id == goal.goal_id
        assert state.athlete_id == goal.athlete_id
        assert state.active is True
        assert state.current_phase == PhaseType.BASE
    
    def test_advance_goal_state_to_next_phase(self):
        """Advance goal state when current phase completes."""
        goal = GoalConfig(
            goal_id="test_goal",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        
        macrocycle = create_macrocycle(goal)
        state = create_goal_state(goal, macrocycle)
        
        # Manually set state to end of base phase
        state.phase_end_date = date.today() - timedelta(days=1)
        state.current_phase = PhaseType.BASE
        
        # Advance should move to build
        new_state = advance_goal_state(state, macrocycle)
        
        assert new_state.current_phase == PhaseType.BUILD


class TestProgramIntegration:
    """Test integration with program engine."""
    
    def test_get_block_type_for_phase(self):
        """Map goal phases to program engine block types."""
        assert get_block_type_for_phase(PhaseType.BASE) == "base"
        assert get_block_type_for_phase(PhaseType.BUILD) == "build"
        assert get_block_type_for_phase(PhaseType.PEAK) == "peak"
        assert get_block_type_for_phase(PhaseType.TAPER) == "deload"
    
    def test_get_microcycle_targets_for_strength_peak(self):
        """Get microcycle targets for strength peak goal."""
        goal = GoalConfig(
            goal_id="test_goal",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        
        targets = get_microcycle_targets_for_phase(PhaseType.PEAK, goal)
        
        assert targets["target_sets_per_week"] == 8
        assert targets["target_avg_intensity"] == 0.88
        assert targets["target_hiit_sessions"] == 0
    
    def test_should_prioritize_lift_for_goal(self):
        """Check if lift should be prioritized."""
        goal = GoalConfig(
            goal_id="test_goal",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength",
            strength_targets=[
                StrengthTarget(lift="squat", metric="1rm")
            ]
        )
        
        assert should_prioritize_lift_for_goal("squat", goal) is True
        assert should_prioritize_lift_for_goal("bench", goal) is False
    
    def test_get_endurance_focus_for_goal(self):
        """Get endurance focus from goal."""
        goal = GoalConfig(
            goal_id="test_goal",
            athlete_id="athlete_1",
            goal_type=GoalType.ENDURANCE_EVENT,
            target_date=date.today() + timedelta(days=84),
            priority="endurance",
            endurance_targets=[
                EnduranceTarget(sport="running", event_type="5k")
            ]
        )
        
        focus = get_endurance_focus_for_goal(goal)
        assert focus == "5k"


class TestMacrocycleContext:
    """Test macrocycle context operations."""
    
    def test_get_current_phase(self):
        """Get phase active on a given date."""
        today = date.today()
        goal = GoalConfig(
            goal_id="test_goal",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=today + timedelta(days=84),
            priority="strength"
        )

        macrocycle = create_macrocycle(goal)

        # Current phase should be base
        current = macrocycle.get_current_phase(today)
        assert current.phase_type == PhaseType.BASE

        # Phase near target date should be taper (within rounding tolerance)
        taper_date = goal.target_date - timedelta(days=1)
        taper = macrocycle.get_phase_for_date(taper_date)
        assert taper is not None
        assert taper.phase_type == PhaseType.TAPER
    
    def test_phase_dates_are_contiguous(self):
        """Phases should be contiguous without gaps."""
        goal = GoalConfig(
            goal_id="test_goal",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        
        macrocycle = create_macrocycle(goal)
        
        for i in range(len(macrocycle.phases) - 1):
            current_end = macrocycle.phases[i].end_date
            next_start = macrocycle.phases[i + 1].start_date
            assert next_start == current_end + timedelta(days=1)


class TestDeterminism:
    """Test deterministic behavior."""
    
    def test_same_input_same_schedule(self):
        """Same inputs produce identical macrocycle."""
        target = date.today() + timedelta(days=84)
        goal = GoalConfig(
            goal_id="test_goal",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=target,
            priority="strength"
        )
        
        macrocycle1 = create_macrocycle(goal)
        macrocycle2 = create_macrocycle(goal)
        
        assert len(macrocycle1.phases) == len(macrocycle2.phases)
        
        for p1, p2 in zip(macrocycle1.phases, macrocycle2.phases):
            assert p1.phase_type == p2.phase_type
            assert p1.duration_weeks == p2.duration_weeks
            assert p1.start_date == p2.start_date
            assert p1.end_date == p2.end_date
