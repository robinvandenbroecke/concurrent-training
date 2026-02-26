"""
Tests for Sprint 5: Priority-Aware Programming.

Verifies that different priorities produce measurably different weekly plans.
"""
import pytest
from datetime import date

from app.domain.program_engine import (
    ProgramMode,
    BlockType,
    Priority,
    ProgramConfig,
    ProgramState,
    DayTemplate,
    get_priority_weekly_targets,
    create_microcycle_template,
    start_program,
    replan_missed_session,
    compress_week,
    get_weekly_summary,
)


class TestPriorityWeeklyTargets:
    """Test priority-based weekly targets."""
    
    def test_strength_priority_targets(self):
        """Strength priority has more strength sessions."""
        targets = get_priority_weekly_targets(Priority.STRENGTH)
        
        assert targets["strength_sessions"] == 4
        assert targets["endurance_sessions"] == 2
        assert targets["hiit_cap"] == 1
        assert targets["key_strength_sessions"] == 2
    
    def test_endurance_priority_targets(self):
        """Endurance priority has more endurance sessions."""
        targets = get_priority_weekly_targets(Priority.ENDURANCE)
        
        assert targets["endurance_sessions"] == 5
        assert targets["strength_sessions"] == 2
        assert targets["hiit_cap"] == 2
        assert targets["key_endurance_sessions"] == 2
    
    def test_balanced_targets(self):
        """Balanced priority has equal distribution."""
        targets = get_priority_weekly_targets(Priority.BALANCED)
        
        assert targets["strength_sessions"] == 3
        assert targets["endurance_sessions"] == 3
        assert targets["key_strength_sessions"] == 1
        assert targets["key_endurance_sessions"] == 1


class TestProgramConfigPriority:
    """Test ProgramConfig priority handling."""
    
    def test_strength_mode_defaults_to_strength_priority(self):
        """Strength mode ignores priority setting."""
        config = ProgramConfig(
            mode=ProgramMode.STRENGTH,
            priority=Priority.ENDURANCE  # Should be ignored
        )
        
        assert config.effective_priority == Priority.STRENGTH
    
    def test_endurance_mode_defaults_to_endurance_priority(self):
        """Endurance mode ignores priority setting."""
        config = ProgramConfig(
            mode=ProgramMode.ENDURANCE,
            priority=Priority.STRENGTH  # Should be ignored
        )
        
        assert config.effective_priority == Priority.ENDURANCE
    
    def test_concurrent_mode_uses_priority(self):
        """Concurrent mode respects priority setting."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH
        )
        
        assert config.effective_priority == Priority.STRENGTH


class TestPriorityAwareMicrocycleGeneration:
    """Test that microcycles differ by priority."""
    
    def test_strength_priority_has_more_strength_days(self):
        """Strength priority generates more strength days."""
        strength_config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH
        )
        endurance_config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.ENDURANCE
        )
        
        strength_cycle = create_microcycle_template(
            strength_config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        endurance_cycle = create_microcycle_template(
            endurance_config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        strength_days_s = len([d for d in strength_cycle.days if d.mode == "strength"])
        strength_days_e = len([d for d in endurance_cycle.days if d.mode == "strength"])
        
        assert strength_days_s >= strength_days_e
    
    def test_endurance_priority_has_more_endurance_days(self):
        """Endurance priority generates more endurance days."""
        strength_config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH
        )
        endurance_config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.ENDURANCE
        )
        
        strength_cycle = create_microcycle_template(
            strength_config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        endurance_cycle = create_microcycle_template(
            endurance_config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        endurance_days_s = len([d for d in strength_cycle.days if d.mode == "endurance"])
        endurance_days_e = len([d for d in endurance_cycle.days if d.mode == "endurance"])
        
        assert endurance_days_e >= endurance_days_s
    
    def test_strength_priority_has_higher_strength_volume(self):
        """Strength priority has higher weekly strength volume targets."""
        strength_config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH
        )
        endurance_config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.ENDURANCE
        )
        
        strength_cycle = create_microcycle_template(
            strength_config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        endurance_cycle = create_microcycle_template(
            endurance_config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        assert strength_cycle.progression.target_sets_per_week > endurance_cycle.progression.target_sets_per_week
    
    def test_endurance_priority_has_higher_endurance_volume(self):
        """Endurance priority has higher weekly endurance volume targets."""
        strength_config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH
        )
        endurance_config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.ENDURANCE
        )
        
        strength_cycle = create_microcycle_template(
            strength_config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        endurance_cycle = create_microcycle_template(
            endurance_config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        assert endurance_cycle.progression.target_minutes_z2 > strength_cycle.progression.target_minutes_z2
    
    def test_different_priorities_produce_different_plans(self):
        """Different priorities produce measurably different plans."""
        priorities = [Priority.STRENGTH, Priority.ENDURANCE, Priority.BALANCED]
        cycles = []
        
        for priority in priorities:
            config = ProgramConfig(
                mode=ProgramMode.CONCURRENT,
                priority=priority
            )
            cycle = create_microcycle_template(
                config, BlockType.BUILD, 1, date(2024, 1, 15)
            )
            cycles.append(cycle)
        
        # All three should be different
        assert cycles[0].progression.target_sets_per_week != cycles[1].progression.target_sets_per_week
        assert cycles[1].progression.target_sets_per_week != cycles[2].progression.target_sets_per_week


class TestKeySessionMarking:
    """Test key session identification."""
    
    def test_strength_priority_marks_heavy_lower_as_key(self):
        """Strength priority marks heavy lower body days as key."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH,
            primary_lifts=["squat", "deadlift", "bench"]
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        # Find days with heavy lower
        heavy_lower_days = [
            d for d in microcycle.days 
            if any(l in ["squat", "deadlift"] for l in d.primary_lifts)
        ]
        
        # At least one should be marked key
        assert any(d.key_session for d in heavy_lower_days)
    
    def test_endurance_priority_marks_long_day_as_key(self):
        """Endurance priority marks long endurance day as key."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.ENDURANCE
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        # Find the longest endurance day
        endurance_days = [d for d in microcycle.days if d.mode in ("endurance", "concurrent")]
        
        # At least one should be marked key
        assert any(d.key_session for d in endurance_days)
    
    def test_hiit_sessions_avoid_heavy_lower(self):
        """HIIT days are marked to avoid heavy lower."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.BALANCED
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.PEAK, 0, date(2024, 1, 15)
        )
        
        # Find HIIT days
        hiit_days = [d for d in microcycle.days if d.endurance_zone == "hiit"]
        
        # HIIT days should avoid heavy legs
        for day in hiit_days:
            assert day.avoid_heavy_legs, f"Day {day.day_index} with HIIT should avoid heavy legs"


class TestDayTemplateFields:
    """Test new DayTemplate priority-aware fields."""
    
    def test_day_template_has_session_domain(self):
        """DayTemplate has session_domain field."""
        config = ProgramConfig(mode=ProgramMode.STRENGTH)
        
        microcycle = create_microcycle_template(
            config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        for day in microcycle.days:
            assert hasattr(day, 'session_domain')
            assert day.session_domain in ["strength", "endurance", "concurrent", "rest"]
    
    def test_day_template_has_avoid_flags(self):
        """DayTemplate has avoid_hiit and avoid_heavy_legs flags."""
        config = ProgramConfig(mode=ProgramMode.CONCURRENT)
        
        microcycle = create_microcycle_template(
            config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        for day in microcycle.days:
            assert hasattr(day, 'avoid_hiit')
            assert hasattr(day, 'avoid_heavy_legs')
            assert isinstance(day.avoid_hiit, bool)
            assert isinstance(day.avoid_heavy_legs, bool)


class TestProgramStatePriorityTargets:
    """Test ProgramState stores priority-aware targets."""
    
    def test_start_program_sets_weekly_targets(self):
        """start_program sets weekly targets based on priority."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH
        )
        
        state, _ = start_program("athlete_1", config, date(2024, 1, 15))
        
        assert state.weekly_strength_sessions_target == 4
        assert state.weekly_endurance_sessions_target == 2
        assert state.weekly_hiit_cap == 1
        assert state.key_strength_sessions == 2
    
    def test_endurance_priority_different_targets(self):
        """Endurance priority has different weekly targets."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.ENDURANCE
        )
        
        state, _ = start_program("athlete_1", config, date(2024, 1, 15))
        
        assert state.weekly_strength_sessions_target == 2
        assert state.weekly_endurance_sessions_target == 5
        assert state.weekly_hiit_cap == 2
        assert state.key_endurance_sessions == 2


class TestReplanningLogic:
    """Test priority-aware replanning."""
    
    def test_key_session_is_moved(self):
        """Key sessions are moved to new day when missed."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        # Find a key session
        key_day = None
        for day in microcycle.days:
            if day.key_session:
                key_day = day
                break
        
        if key_day:
            missed_date = date(2024, 1, 15 + key_day.day_index)
            new_day = replan_missed_session(
                microcycle, missed_date, [], Priority.STRENGTH
            )
            
            assert new_day is not None, "Key session should be rescheduled"
    
    def test_non_key_session_is_discarded(self):
        """Non-key sessions are discarded when missed."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.ENDURANCE
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        # Find a non-key session
        non_key_day = None
        for day in microcycle.days:
            if not day.key_session and day.mode != "rest":
                non_key_day = day
                break
        
        if non_key_day:
            missed_date = date(2024, 1, 15 + non_key_day.day_index)
            new_day = replan_missed_session(
                microcycle, missed_date, [], Priority.ENDURANCE
            )
            
            assert new_day is None, "Non-key session should be discarded"


class TestWeeklySummary:
    """Test weekly summary generation."""
    
    def test_summary_counts_sessions(self):
        """Summary correctly counts sessions."""
        config = ProgramConfig(mode=ProgramMode.CONCURRENT)
        
        microcycle = create_microcycle_template(
            config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        summary = get_weekly_summary(microcycle)
        
        assert "total_sessions" in summary
        assert "strength_sessions" in summary
        assert "endurance_sessions" in summary
        assert "key_sessions" in summary
    
    def test_summary_counts_hiit_and_heavy_legs(self):
        """Summary counts HIIT and heavy legs sessions."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.BALANCED
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.PEAK, 0, date(2024, 1, 15)
        )
        
        summary = get_weekly_summary(microcycle)
        
        assert "hiit_sessions" in summary
        assert "heavy_legs_sessions" in summary
        assert isinstance(summary["hiit_sessions"], int)
        assert isinstance(summary["heavy_legs_sessions"], int)
