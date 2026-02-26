"""
Integration tests for program-goal interaction.

Tests that goal context correctly affects program generation.
"""
import pytest
from datetime import date, timedelta

from app.domain.goal_engine import (
    GoalType,
    PhaseType,
    StrengthTarget,
    EnduranceTarget,
    GoalConfig,
    create_macrocycle,
    get_microcycle_targets_for_phase,
)
from app.domain.program_engine import (
    ProgramMode,
    Priority,
    ProgramConfig,
    create_microcycle_template,
    create_microcycle_with_performance,
)


class TestStrengthPeakTaper:
    """Test strength peak taper phase effects."""
    
    def test_taper_reduces_volume(self):
        """Taper phase reduces volume significantly."""
        goal = GoalConfig(
            goal_id="strength_peak",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength",
            strength_targets=[StrengthTarget(lift="squat", metric="1rm")]
        )
        
        macrocycle = create_macrocycle(goal)
        taper_phase = [p for p in macrocycle.phases if p.phase_type == PhaseType.TAPER][0]
        
        # Taper should have minimal volume
        assert taper_phase.target_sets_per_week == 5
        assert taper_phase.target_intensity == 0.85
    
    def test_taper_avoids_hiit(self):
        """Taper phase should not include HIIT for strength goals."""
        goal = GoalConfig(
            goal_id="strength_peak",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        
        macrocycle = create_macrocycle(goal)
        
        for phase in macrocycle.phases:
            # No HIIT in any phase for pure strength
            assert phase.target_hiit_sessions == 0


class TestEnduranceEventBuildPhase:
    """Test endurance event build phase effects."""
    
    def test_build_increases_quality_sessions(self):
        """Build phase adds threshold/tempo focus."""
        goal = GoalConfig(
            goal_id="5k_race",
            athlete_id="athlete_1",
            goal_type=GoalType.ENDURANCE_EVENT,
            target_date=date.today() + timedelta(days=70),
            priority="endurance",
            endurance_targets=[EnduranceTarget(sport="running", event_type="5k")]
        )
        
        base_targets = get_microcycle_targets_for_phase(PhaseType.BASE, goal)
        build_targets = get_microcycle_targets_for_phase(PhaseType.BUILD, goal)
        
        # Build should have more HIIT than base
        assert build_targets["target_hiit_sessions"] > base_targets["target_hiit_sessions"]
    
    def test_peak_has_race_specific_intensity(self):
        """Peak phase has race-specific intensity."""
        goal = GoalConfig(
            goal_id="5k_race",
            athlete_id="athlete_1",
            goal_type=GoalType.ENDURANCE_EVENT,
            target_date=date.today() + timedelta(days=70),
            priority="endurance"
        )
        
        peak_targets = get_microcycle_targets_for_phase(PhaseType.PEAK, goal)
        
        # Peak should have high intensity
        assert peak_targets["target_hiit_sessions"] == 2


class TestConcurrentGoalPhases:
    """Test concurrent goal phase balance."""
    
    def test_base_builds_durability(self):
        """Base phase for concurrent builds durability."""
        goal = GoalConfig(
            goal_id="hybrid_goal",
            athlete_id="athlete_1",
            goal_type=GoalType.CONCURRENT_EVENT,
            target_date=date.today() + timedelta(days=84),
            priority="balanced"
        )
        
        base_targets = get_microcycle_targets_for_phase(PhaseType.BASE, goal)
        
        # Should have moderate volume and some HIIT
        assert 8 <= base_targets["target_sets_per_week"] <= 12
        assert base_targets["target_hiit_sessions"] >= 1
    
    def test_peak_protects_both_domains(self):
        """Peak phase protects both strength and endurance."""
        goal = GoalConfig(
            goal_id="hybrid_goal",
            athlete_id="athlete_1",
            goal_type=GoalType.CONCURRENT_EVENT,
            target_date=date.today() + timedelta(days=84),
            priority="balanced"
        )
        
        peak_targets = get_microcycle_targets_for_phase(PhaseType.PEAK, goal)
        
        # Should maintain some strength volume
        assert peak_targets["target_sets_per_week"] >= 4
        # Should have quality endurance
        assert peak_targets["target_hiit_sessions"] >= 1


class TestPhaseGuardrails:
    """Test phase guardrails on performance adjustments."""
    
    def test_taper_blocks_volume_increase(self):
        """Taper phase cannot increase volume."""
        from app.domain.goal_engine import should_apply_phase_guardrails
        
        proposed = {
            "volume_adjustment_pct": 0.05,
            "intensity_adjustment_pct": 0.03,
            "add_stimulus_lifts": ["squat"],
            "add_hiit_intervals": 2
        }
        
        adjusted = should_apply_phase_guardrails("taper", proposed)
        
        # Volume should be locked
        assert adjusted["volume_adjustment_pct"] == 0
        assert adjusted["add_stimulus_lifts"] == []
        assert adjusted["add_hiit_intervals"] == 0
        # Intensity limited to 2%
        assert adjusted["intensity_adjustment_pct"] <= 0.02
    
    def test_peak_blocks_extra_volume(self):
        """Peak phase cannot add extra volume."""
        from app.domain.goal_engine import should_apply_phase_guardrails
        
        proposed = {
            "volume_adjustment_pct": 0.05,
            "add_stimulus_lifts": ["squat"]
        }
        
        adjusted = should_apply_phase_guardrails("peak", proposed)
        
        # Extra volume blocked
        assert adjusted["volume_adjustment_pct"] == 0
        assert adjusted["add_stimulus_lifts"] == []
    
    def test_base_allows_normal_adjustments(self):
        """Base phase allows normal performance adjustments."""
        from app.domain.goal_engine import should_apply_phase_guardrails
        
        proposed = {
            "volume_adjustment_pct": 0.05,
            "add_stimulus_lifts": ["squat"],
            "add_hiit_intervals": 1
        }
        
        adjusted = should_apply_phase_guardrails("base", proposed)
        
        # All adjustments preserved
        assert adjusted["volume_adjustment_pct"] == 0.05
        assert adjusted["add_stimulus_lifts"] == ["squat"]
        assert adjusted["add_hiit_intervals"] == 1


class TestProgramGenerationWithGoal:
    """Test program generation with goal context."""
    
    def test_microcycle_uses_goal_block_type(self):
        """Microcycle uses block type from goal phase."""
        goal = GoalConfig(
            goal_id="strength_peak",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        
        macrocycle = create_macrocycle(goal)
        peak_phase = [p for p in macrocycle.phases if p.phase_type == PhaseType.PEAK][0]
        
        # Use phase-specific targets
        targets = get_microcycle_targets_for_phase(peak_phase.phase_type, goal)
        
        assert targets["target_sets_per_week"] == 8  # Peak volume
        assert targets["target_avg_intensity"] == 0.88  # Peak intensity
    
    def test_goal_prioritizes_specific_lifts(self):
        """Goal context prioritizes target lifts in program."""
        goal = GoalConfig(
            goal_id="strength_peak",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength",
            strength_targets=[
                StrengthTarget(lift="squat", metric="1rm"),
                StrengthTarget(lift="bench", metric="1rm")
            ]
        )
        
        # Check lift prioritization
        assert goal.goal_type == GoalType.STRENGTH_PEAK
        assert len(goal.strength_targets) == 2
        assert goal.strength_targets[0].lift == "squat"


class TestDaysToEventCalculation:
    """Test days to event calculation."""
    
    def test_days_to_event_decreases(self):
        """Days to event decreases as date approaches."""
        today = date.today()
        target = today + timedelta(days=84)
        
        days_to_event = (target - today).days
        
        assert days_to_event == 84
        
        # One week later
        days_to_event_later = (target - (today + timedelta(days=7))).days
        assert days_to_event_later == 77


class TestPhaseWeekIndex:
    """Test phase week index calculation."""
    
    def test_phase_week_index_increases(self):
        """Phase week index increases through phase."""
        start_date = date.today()
        
        # Week 0
        week0_date = start_date
        week0_index = (week0_date - start_date).days // 7
        assert week0_index == 0
        
        # Week 1
        week1_date = start_date + timedelta(days=7)
        week1_index = (week1_date - start_date).days // 7
        assert week1_index == 1
        
        # Week 2
        week2_date = start_date + timedelta(days=14)
        week2_index = (week2_date - start_date).days // 7
        assert week2_index == 2


class TestGoalTypeSpecificBehavior:
    """Test goal type specific behaviors."""
    
    def test_strength_peak_has_no_hiit(self):
        """Strength peak goals have no HIIT."""
        goal = GoalConfig(
            goal_id="strength_test",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        
        for phase in PhaseType:
            targets = get_microcycle_targets_for_phase(phase, goal)
            assert targets["target_hiit_sessions"] == 0
    
    def test_endurance_event_has_hiit_in_build_peak(self):
        """Endurance events have HIIT in build and peak."""
        goal = GoalConfig(
            goal_id="5k_race",
            athlete_id="athlete_1",
            goal_type=GoalType.ENDURANCE_EVENT,
            target_date=date.today() + timedelta(days=84),
            priority="endurance"
        )
        
        base_targets = get_microcycle_targets_for_phase(PhaseType.BASE, goal)
        build_targets = get_microcycle_targets_for_phase(PhaseType.BUILD, goal)
        peak_targets = get_microcycle_targets_for_phase(PhaseType.PEAK, goal)
        
        # Build and peak should have HIIT
        assert build_targets["target_hiit_sessions"] > 0
        assert peak_targets["target_hiit_sessions"] > 0


class TestDeterminism:
    """Test deterministic behavior."""
    
    def test_same_goal_same_macrocycle(self):
        """Same goal config produces same macrocycle."""
        target = date.today() + timedelta(days=84)
        
        goal1 = GoalConfig(
            goal_id="test1",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=target,
            priority="strength"
        )
        
        goal2 = GoalConfig(
            goal_id="test2",
            athlete_id="athlete_1",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=target,
            priority="strength"
        )
        
        macrocycle1 = create_macrocycle(goal1)
        macrocycle2 = create_macrocycle(goal2)
        
        # Same phase structure
        assert len(macrocycle1.phases) == len(macrocycle2.phases)
        
        for p1, p2 in zip(macrocycle1.phases, macrocycle2.phases):
            assert p1.target_sets_per_week == p2.target_sets_per_week
            assert p1.target_intensity == p2.target_intensity
            assert p1.target_hiit_sessions == p2.target_hiit_sessions
