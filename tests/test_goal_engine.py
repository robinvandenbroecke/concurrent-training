"""
Tests for goal engine.

Tests goal configuration, phase scheduling, and macrocycle creation.
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


class TestPhaseDurationComputation:
    """Test phase duration computation based on time to event."""
    
    def test_12_weeks_plus_full_macrocycle(self):
        """12+ weeks gets full macrocycle."""
        durations = compute_phase_durations(84)  # 12 weeks
        
        assert durations[PhaseType.BASE] == 6
        assert durations[PhaseType.BUILD] == 4
        assert durations[PhaseType.PEAK] == 1
        assert durations[PhaseType.TAPER] == 1
        assert sum(durations.values()) == 12
    
    def test_10_weeks_compressed(self):
        """8-11 weeks gets compressed macrocycle."""
        durations = compute_phase_durations(70)  # 10 weeks
        
        assert durations[PhaseType.BASE] == 4
        assert durations[PhaseType.BUILD] == 3
        assert durations[PhaseType.PEAK] == 1
        assert durations[PhaseType.TAPER] == 1
        assert sum(durations.values()) == 9
    
    def test_6_weeks_minimal(self):
        """4-7 weeks gets minimal base."""
        durations = compute_phase_durations(42)  # 6 weeks
        
        assert durations[PhaseType.BASE] == 2
        assert durations[PhaseType.BUILD] == 2  # >=42d so 2 weeks
        assert durations[PhaseType.PEAK] == 1
        assert durations[PhaseType.TAPER] == 1
    
    def test_5_weeks_shorter_build(self):
        """<42d gets shorter build."""
        durations = compute_phase_durations(35)  # 5 weeks
        
        assert durations[PhaseType.BASE] == 2
        assert durations[PhaseType.BUILD] == 1  # <42d so 1 week
        assert durations[PhaseType.PEAK] == 1
        assert durations[PhaseType.TAPER] == 1
    
    def test_3_weeks_crash_prep(self):
        """<4 weeks gets crash prep."""
        durations = compute_phase_durations(21)  # 3 weeks
        
        # Should have minimal or no base
        assert PhaseType.TAPER in durations
        assert PhaseType.PEAK in durations
        assert PhaseType.BUILD in durations


class TestMacrocycleCreation:
    """Test macrocycle creation."""
    
    def test_strength_peak_macrocycle(self):
        """Create strength peak macrocycle."""
        goal = GoalConfig(
            goal_id="test_strength",
            athlete_id="123",
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
        assert macrocycle.phases[-1].end_date == goal.target_date - timedelta(days=1)
    
    def test_endurance_event_macrocycle(self):
        """Create endurance event macrocycle."""
        goal = GoalConfig(
            goal_id="test_endurance",
            athlete_id="123",
            goal_type=GoalType.ENDURANCE_EVENT,
            target_date=date.today() + timedelta(days=70),
            priority="endurance",
            endurance_targets=[
                EnduranceTarget(sport="running", event_type="5k", target_value=20.0)
            ]
        )
        
        macrocycle = create_macrocycle(goal)
        
        assert len(macrocycle.phases) >= 3
        # Endurance goals should have HIIT in build/peak
        build_phase = next(p for p in macrocycle.phases if p.phase_type == PhaseType.BUILD)
        assert build_phase.target_hiit_sessions >= 1
    
    def test_concurrent_event_macrocycle(self):
        """Create concurrent event macrocycle."""
        goal = GoalConfig(
            goal_id="test_concurrent",
            athlete_id="123",
            goal_type=GoalType.CONCURRENT_EVENT,
            target_date=date.today() + timedelta(days=56),
            priority="balanced",
            concurrent_target=ConcurrentTarget.STRONG_AND_DURABLE
        )
        
        macrocycle = create_macrocycle(goal)
        
        assert len(macrocycle.phases) >= 3
        # Balanced should have moderate targets
        base_phase = next(p for p in macrocycle.phases if p.phase_type == PhaseType.BASE)
        assert 8 <= base_phase.target_sets_per_week <= 12
    
    def test_macrocycle_hits_target_date(self):
        """Macrocycle end date matches target date (within a few days)."""
        target = date(2024, 6, 15)
        goal = GoalConfig(
            goal_id="test_date",
            athlete_id="123",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=target,
            priority="strength"
        )

        macrocycle = create_macrocycle(goal, start_date=date(2024, 3, 15))

        last_phase = macrocycle.phases[-1]
        # End date should be at or very near target date (within a few days due to week rounding)
        days_diff = abs((last_phase.end_date - (target - timedelta(days=1))).days)
        assert days_diff <= 3, f"End date {last_phase.end_date} too far from target {target}"


class TestGoalState:
    """Test goal state management."""
    
    def test_create_initial_goal_state(self):
        """Create initial goal state from macrocycle."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        macrocycle = create_macrocycle(goal)
        
        state = create_goal_state(goal, macrocycle)
        
        assert state.goal_id == goal.goal_id
        assert state.active is True
        assert state.current_phase == PhaseType.BASE
        assert state.microcycles_completed_in_phase == 0
    
    def test_advance_goal_state_to_next_phase(self):
        """Advance goal state when phase complete."""
        today = date.today()
        state = GoalState(
            goal_id="test",
            athlete_id="123",
            active=True,
            current_phase=PhaseType.BASE,
            phase_start_date=today - timedelta(days=10),
            phase_end_date=today - timedelta(days=1),  # Past
            last_phase_update_date=today - timedelta(days=10)
        )
        
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=today + timedelta(days=60),
            priority="strength"
        )
        macrocycle = create_macrocycle(goal, start_date=today - timedelta(days=10))
        
        updated = advance_goal_state(state, macrocycle)
        
        # Should have advanced
        assert updated.current_phase != PhaseType.BASE
        assert updated.microcycles_completed_in_phase == 0
    
    def test_no_advance_if_phase_not_complete(self):
        """Don't advance if phase not complete."""
        today = date.today()
        state = GoalState(
            goal_id="test",
            athlete_id="123",
            active=True,
            current_phase=PhaseType.BASE,
            phase_start_date=today - timedelta(days=3),
            phase_end_date=today + timedelta(days=4),  # Future
            last_phase_update_date=today - timedelta(days=3),
            microcycles_completed_in_phase=1
        )
        
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=today + timedelta(days=60),
            priority="strength"
        )
        macrocycle = create_macrocycle(goal, start_date=today - timedelta(days=3))
        
        updated = advance_goal_state(state, macrocycle)
        
        # Should stay in same phase
        assert updated.current_phase == PhaseType.BASE


class TestPhaseToBlockMapping:
    """Test phase to program block mapping."""
    
    def test_base_phase_maps_to_base_block(self):
        """BASE phase maps to base block."""
        assert get_block_type_for_phase(PhaseType.BASE) == "base"
    
    def test_build_phase_maps_to_build_block(self):
        """BUILD phase maps to build block."""
        assert get_block_type_for_phase(PhaseType.BUILD) == "build"
    
    def test_peak_phase_maps_to_peak_block(self):
        """PEAK phase maps to peak block."""
        assert get_block_type_for_phase(PhaseType.PEAK) == "peak"
    
    def test_taper_phase_maps_to_deload_block(self):
        """TAPER phase maps to deload block."""
        assert get_block_type_for_phase(PhaseType.TAPER) == "deload"


class TestMicrocycleTargets:
    """Test microcycle targets for phases."""
    
    def test_strength_peak_targets(self):
        """Strength peak goal has correct targets per phase."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        
        base_targets = get_microcycle_targets_for_phase(PhaseType.BASE, goal)
        peak_targets = get_microcycle_targets_for_phase(PhaseType.PEAK, goal)
        
        # Base: higher volume, lower intensity
        assert base_targets["target_sets_per_week"] > peak_targets["target_sets_per_week"]
        assert base_targets["target_avg_intensity"] < peak_targets["target_avg_intensity"]
        
        # Peak: minimal HIIT
        assert peak_targets["target_hiit_sessions"] == 0
    
    def test_endurance_event_targets(self):
        """Endurance event goal has correct targets per phase."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.ENDURANCE_EVENT,
            target_date=date.today() + timedelta(days=84),
            priority="endurance"
        )
        
        build_targets = get_microcycle_targets_for_phase(PhaseType.BUILD, goal)
        
        # Endurance: HIIT in build phase
        assert build_targets["target_hiit_sessions"] >= 1
    
    def test_concurrent_balanced_targets(self):
        """Concurrent balanced goal has moderate targets."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.CONCURRENT_EVENT,
            target_date=date.today() + timedelta(days=84),
            priority="balanced"
        )
        
        base_targets = get_microcycle_targets_for_phase(PhaseType.BASE, goal)
        
        # Balanced: moderate volume
        assert 8 <= base_targets["target_sets_per_week"] <= 12


class TestGoalPrioritization:
    """Test goal-based prioritization."""
    
    def test_prioritize_goal_lift(self):
        """Should prioritize lifts in goal targets."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength",
            strength_targets=[
                StrengthTarget(lift="squat", metric="1rm")
            ]
        )
        
        assert should_prioritize_lift_for_goal("squat", goal) is True
        assert should_prioritize_lift_for_goal("bench", goal) is False
    
    def test_endurance_focus_from_goal(self):
        """Get endurance focus from goal."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.ENDURANCE_EVENT,
            target_date=date.today() + timedelta(days=84),
            priority="endurance",
            endurance_targets=[
                EnduranceTarget(sport="running", event_type="5k")
            ]
        )
        
        focus = get_endurance_focus_for_goal(goal)
        assert focus == "5k"


class TestGoalSerialization:
    """Test goal config serialization."""
    
    def test_round_trip_serialization(self):
        """Config survives round-trip through JSON."""
        original = GoalConfig(
            goal_id="test_roundtrip",
            athlete_id="123",
            goal_type=GoalType.CONCURRENT_EVENT,
            target_date=date(2024, 6, 15),
            priority="balanced",
            strength_targets=[
                StrengthTarget(lift="squat", metric="3rm", target_value=140)
            ],
            endurance_targets=[
                EnduranceTarget(sport="cycling", event_type="long_ride")
            ],
            concurrent_target=ConcurrentTarget.STRONG_AND_DURABLE,
            notes="Test goal"
        )
        
        json_str = original.to_json()
        restored = GoalConfig.from_dict(original.to_dict())
        
        assert restored.goal_id == original.goal_id
        assert restored.goal_type == original.goal_type
        assert restored.target_date == original.target_date
        assert restored.strength_targets[0].lift == "squat"
        assert restored.endurance_targets[0].sport == "cycling"
        assert restored.concurrent_target == ConcurrentTarget.STRONG_AND_DURABLE


class TestDeterminism:
    """Test deterministic behavior."""
    
    def test_same_goal_same_macrocycle(self):
        """Same goal config produces same macrocycle."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date(2024, 6, 15),
            priority="strength"
        )
        
        start = date(2024, 3, 15)
        macrocycle1 = create_macrocycle(goal, start_date=start)
        macrocycle2 = create_macrocycle(goal, start_date=start)
        
        assert len(macrocycle1.phases) == len(macrocycle2.phases)
        for p1, p2 in zip(macrocycle1.phases, macrocycle2.phases):
            assert p1.phase_type == p2.phase_type
            assert p1.duration_weeks == p2.duration_weeks
            assert p1.start_date == p2.start_date
