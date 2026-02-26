"""
Integration tests for program-goal integration.

Tests that goal context properly influences program generation.
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
    get_block_type_for_phase,
)
from app.domain.program_engine import (
    ProgramConfig,
    ProgramMode,
    Priority,
    BlockType,
    create_microcycle_template,
)


class TestGoalInfluencesBlockType:
    """Test that goal phase influences program block type."""
    
    def test_base_phase_uses_base_block(self):
        """BASE phase maps to base block type."""
        block = get_block_type_for_phase(PhaseType.BASE)
        assert block == "base"
        assert BlockType(block) == BlockType.BASE
    
    def test_build_phase_uses_build_block(self):
        """BUILD phase maps to build block type."""
        block = get_block_type_for_phase(PhaseType.BUILD)
        assert block == "build"
        assert BlockType(block) == BlockType.BUILD
    
    def test_peak_phase_uses_peak_block(self):
        """PEAK phase maps to peak block type."""
        block = get_block_type_for_phase(PhaseType.PEAK)
        assert block == "peak"
        assert BlockType(block) == BlockType.PEAK
    
    def test_taper_phase_uses_deload_block(self):
        """TAPER phase maps to deload block (reduced volume)."""
        block = get_block_type_for_phase(PhaseType.TAPER)
        assert block == "deload"
        assert BlockType(block) == BlockType.DELOAD


class TestGoalModifiesProgramStructure:
    """Test that goal modifies program structure."""
    
    def test_strength_goal_increases_strength_sessions(self):
        """Strength goal increases strength session count."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH,
            days_per_week_strength=4,
            days_per_week_endurance=2
        )
        
        microcycle = create_microcycle_template(
            config=config,
            block_type=BlockType.BUILD,
            week_index=1,
            start_date=date.today()
        )
        
        strength_days = [d for d in microcycle.days if d.session_domain == "strength"]
        assert len(strength_days) >= 3
    
    def test_endurance_goal_increases_endurance_sessions(self):
        """Endurance goal increases endurance session count."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.ENDURANCE,
            days_per_week_strength=2,
            days_per_week_endurance=5
        )
        
        microcycle = create_microcycle_template(
            config=config,
            block_type=BlockType.BUILD,
            week_index=1,
            start_date=date.today()
        )
        
        endurance_days = [d for d in microcycle.days if d.session_domain == "endurance"]
        assert len(endurance_days) >= 4


class TestPhaseSpecificVolume:
    """Test volume adjustments based on phase."""
    
    def test_base_phase_higher_volume(self):
        """BASE phase has higher volume targets."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        macrocycle = create_macrocycle(goal)
        
        base_phase = next(p for p in macrocycle.phases if p.phase_type == PhaseType.BASE)
        peak_phase = next(p for p in macrocycle.phases if p.phase_type == PhaseType.PEAK)
        
        assert base_phase.target_sets_per_week > peak_phase.target_sets_per_week
    
    def test_taper_phase_reduced_volume(self):
        """TAPER phase has significantly reduced volume."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        macrocycle = create_macrocycle(goal)
        
        base_phase = next(p for p in macrocycle.phases if p.phase_type == PhaseType.BASE)
        taper_phase = next(p for p in macrocycle.phases if p.phase_type == PhaseType.TAPER)
        
        # Taper should be ~30-50% of base volume
        assert taper_phase.target_sets_per_week < base_phase.target_sets_per_week * 0.6


class TestGoalTypeSpecificTargets:
    """Test that different goal types produce different targets."""
    
    def test_strength_vs_endurance_intensity(self):
        """Strength goal has higher intensity than endurance."""
        strength_goal = GoalConfig(
            goal_id="strength",
            athlete_id="123",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        endurance_goal = GoalConfig(
            goal_id="endurance",
            athlete_id="123",
            goal_type=GoalType.ENDURANCE_EVENT,
            target_date=date.today() + timedelta(days=84),
            priority="endurance"
        )
        
        from app.domain.goal_engine import get_microcycle_targets_for_phase
        
        strength_targets = get_microcycle_targets_for_phase(PhaseType.BUILD, strength_goal)
        endurance_targets = get_microcycle_targets_for_phase(PhaseType.BUILD, endurance_goal)
        
        assert strength_targets["target_avg_intensity"] > endurance_targets["target_avg_intensity"]
    
    def test_endurance_has_hiit_in_build(self):
        """Endurance goal includes HIIT in build phase."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.ENDURANCE_EVENT,
            target_date=date.today() + timedelta(days=84),
            priority="endurance"
        )
        
        from app.domain.goal_engine import get_microcycle_targets_for_phase
        
        build_targets = get_microcycle_targets_for_phase(PhaseType.BUILD, goal)
        
        assert build_targets["target_hiit_sessions"] >= 1
    
    def test_strength_minimal_hiit(self):
        """Strength goal minimizes HIIT."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        
        from app.domain.goal_engine import get_microcycle_targets_for_phase
        
        build_targets = get_microcycle_targets_for_phase(PhaseType.BUILD, goal)
        
        assert build_targets["target_hiit_sessions"] == 0


class TestConcurrentGoalPriorities:
    """Test concurrent goal with different priorities."""
    
    def test_strength_priority_concurrent(self):
        """Concurrent goal with strength priority favors strength."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.CONCURRENT_EVENT,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        
        from app.domain.goal_engine import get_microcycle_targets_for_phase
        
        base_targets = get_microcycle_targets_for_phase(PhaseType.BASE, goal)
        
        # Should have more sets than endurance-priority
        assert base_targets["target_sets_per_week"] >= 10
    
    def test_endurance_priority_concurrent(self):
        """Concurrent goal with endurance priority favors endurance."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.CONCURRENT_EVENT,
            target_date=date.today() + timedelta(days=84),
            priority="endurance"
        )
        
        from app.domain.goal_engine import get_microcycle_targets_for_phase
        
        base_targets = get_microcycle_targets_for_phase(PhaseType.BASE, goal)
        
        # Should have fewer strength sets, more HIIT
        assert base_targets["target_sets_per_week"] <= 9
        assert base_targets["target_hiit_sessions"] >= 1


class TestTimeBasedPhaseProgression:
    """Test phase progression based on time to event."""
    
    def test_12_week_progression(self):
        """12 week macrocycle has all phases."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=84),
            priority="strength"
        )
        macrocycle = create_macrocycle(goal)
        
        phase_types = [p.phase_type for p in macrocycle.phases]
        
        assert PhaseType.BASE in phase_types
        assert PhaseType.BUILD in phase_types
        assert PhaseType.PEAK in phase_types
        assert PhaseType.TAPER in phase_types
    
    def test_short_prep_minimal_phases(self):
        """Short prep (<4 weeks) has minimal phases."""
        goal = GoalConfig(
            goal_id="test",
            athlete_id="123",
            goal_type=GoalType.STRENGTH_PEAK,
            target_date=date.today() + timedelta(days=21),
            priority="strength"
        )
        macrocycle = create_macrocycle(goal)
        
        # Should have at least build, peak, taper
        phase_types = [p.phase_type for p in macrocycle.phases]
        assert PhaseType.TAPER in phase_types
        assert PhaseType.PEAK in phase_types


class TestGoalLiftPrioritization:
    """Test that goal lifts are prioritized in program."""
    
    def test_goal_lifts_in_key_sessions(self):
        """Goal lifts appear in key sessions."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH,
            primary_lifts=["squat", "bench", "deadlift"],
            days_per_week_strength=3
        )
        
        microcycle = create_microcycle_template(
            config=config,
            block_type=BlockType.BUILD,
            week_index=1,
            start_date=date.today()
        )
        
        # Should have key sessions with primary lifts
        key_sessions = [d for d in microcycle.days if d.key_session]
        assert len(key_sessions) >= 1
        
        # At least one key session should have squat or deadlift
        has_lower = any(
            "squat" in (d.primary_lifts or []) or "deadlift" in (d.primary_lifts or [])
            for d in key_sessions
        )
        assert has_lower


class TestDeterminism:
    """Test deterministic goal-program integration."""
    
    def test_same_goal_same_program_structure(self):
        """Same goal produces same program structure."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH,
            days_per_week_strength=3,
            days_per_week_endurance=3
        )
        
        start = date(2024, 3, 15)
        
        microcycle1 = create_microcycle_template(
            config=config,
            block_type=BlockType.BUILD,
            week_index=1,
            start_date=start
        )
        microcycle2 = create_microcycle_template(
            config=config,
            block_type=BlockType.BUILD,
            week_index=1,
            start_date=start
        )
        
        # Should have same structure
        assert len(microcycle1.days) == len(microcycle2.days)
        
        for d1, d2 in zip(microcycle1.days, microcycle2.days):
            assert d1.mode == d2.mode
            assert d1.key_session == d2.key_session
