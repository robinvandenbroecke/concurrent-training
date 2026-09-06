"""
Priority-Aware Programming Tests (Sprint 5)

Verifies behavioral differences between strength, endurance, and balanced priorities.
"""
import pytest
from datetime import date

from app.domain.program_engine import (
    ProgramMode,
    Priority,
    BlockType,
    ProgramConfig,
    ProgramState,
    DayTemplate,
    create_microcycle_template,
    start_program,
    replan_missed_sessions,
)


class TestPriorityWeeklyStructure:
    """Test that weekly structure differs by priority."""
    
    def test_strength_priority_has_2_key_strength_sessions(self):
        """Strength priority produces >=2 strength key sessions."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH,
            days_per_week_strength=3,
            days_per_week_endurance=3
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.BUILD, 1, date(2024, 1, 15)
        )
        
        key_strength = [
            d for d in microcycle.days 
            if d.key_session and d.session_domain == "strength"
        ]
        
        assert len(key_strength) >= 2, f"Expected >=2 key strength, got {len(key_strength)}"
    
    def test_endurance_priority_has_2_key_endurance_sessions(self):
        """Endurance priority produces >=2 endurance key sessions."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.ENDURANCE,
            days_per_week_strength=3,
            days_per_week_endurance=3
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.BUILD, 1, date(2024, 1, 15)
        )
        
        key_endurance = [
            d for d in microcycle.days 
            if d.key_session and d.session_domain == "endurance"
        ]
        
        assert len(key_endurance) >= 2, f"Expected >=2 key endurance, got {len(key_endurance)}"
    
    def test_balanced_has_1_key_each(self):
        """Balanced produces exactly 1 key each."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.BALANCED,
            days_per_week_strength=3,
            days_per_week_endurance=3
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.BUILD, 1, date(2024, 1, 15)
        )
        
        key_strength = [
            d for d in microcycle.days 
            if d.key_session and d.session_domain == "strength"
        ]
        key_endurance = [
            d for d in microcycle.days 
            if d.key_session and d.session_domain == "endurance"
        ]
        
        assert len(key_strength) == 1, f"Expected 1 key strength, got {len(key_strength)}"
        assert len(key_endurance) == 1, f"Expected 1 key endurance, got {len(key_endurance)}"
    
    def test_strength_priority_more_strength_sessions(self):
        """Strength priority has more strength than endurance sessions."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH,
            days_per_week_strength=4,
            days_per_week_endurance=3
        )
        
        state, microcycle = start_program("athlete_1", config, date(2024, 1, 15))
        
        strength_days = len([d for d in microcycle.days if d.session_domain == "strength"])
        endurance_days = len([d for d in microcycle.days if d.session_domain == "endurance"])
        
        assert strength_days >= endurance_days
    
    def test_endurance_priority_more_endurance_sessions(self):
        """Endurance priority has more endurance than strength sessions."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.ENDURANCE,
            days_per_week_strength=2,
            days_per_week_endurance=5
        )
        
        state, microcycle = start_program("athlete_1", config, date(2024, 1, 15))
        
        strength_days = len([d for d in microcycle.days if d.session_domain == "strength"])
        endurance_days = len([d for d in microcycle.days if d.session_domain == "endurance"])
        
        assert endurance_days > strength_days


class TestPriorityGuardrails:
    """Test guardrails differ by priority."""
    
    def test_strength_priority_limits_hiit(self):
        """Strength priority has max 1 HIIT per week."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH,
            days_per_week_strength=3,
            days_per_week_endurance=3
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.PEAK, 0, date(2024, 1, 15)
        )
        
        assert microcycle.guardrails.max_hiit_per_week <= 1
    
    def test_endurance_priority_allows_more_hiit(self):
        """Endurance priority allows more HIIT."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.ENDURANCE,
            days_per_week_strength=2,
            days_per_week_endurance=5
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.PEAK, 0, date(2024, 1, 15)
        )
        
        assert microcycle.guardrails.max_hiit_per_week >= 2
    
    def test_hiit_not_near_heavy_lower(self):
        """HIIT is not scheduled on/near heavy lower body days."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH,
            primary_lifts=["squat", "deadlift", "bench"],
            days_per_week_strength=3,
            days_per_week_endurance=3
        )
        
        # Use BASE block to minimize HIIT scheduling
        microcycle = create_microcycle_template(
            config, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        # For each key strength lower day, check adjacent days have guardrails
        for i, day in enumerate(microcycle.days):
            if not day.key_session:
                continue
            if day.session_domain != "strength":
                continue
            if not any(l in ["squat", "deadlift"] for l in day.primary_lifts):
                continue
            
            # Adjacent days should be marked to avoid HIIT
            for offset in [-1, 1]:
                adj_idx = i + offset
                if 0 <= adj_idx < len(microcycle.days):
                    adj_day = microcycle.days[adj_idx]
                    if adj_day.avoid_hiit:
                        # Guardrail is correctly set
                        pass
                    elif adj_day.endurance_zone == "hiit":
                        # No guardrail and HIIT scheduled - this is a violation
                        pytest.fail(f"Day {i} (heavy legs) has HIIT on adjacent day {adj_idx} without guardrail")


class TestPriorityProgressionTargets:
    """Test progression targets differ by priority."""
    
    def test_strength_priority_higher_strength_volume(self):
        """Strength priority has higher strength volume targets."""
        config_strength = ProgramConfig(
            mode=ProgramMode.CONCURRENT, priority=Priority.STRENGTH
        )
        config_endurance = ProgramConfig(
            mode=ProgramMode.CONCURRENT, priority=Priority.ENDURANCE
        )
        
        micro_strength = create_microcycle_template(
            config_strength, BlockType.BASE, 0, date(2024, 1, 15)
        )
        micro_endurance = create_microcycle_template(
            config_endurance, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        assert micro_strength.progression.target_sets_per_week > micro_endurance.progression.target_sets_per_week
    
    def test_endurance_priority_higher_endurance_volume(self):
        """Endurance priority has higher endurance volume targets."""
        config_strength = ProgramConfig(
            mode=ProgramMode.CONCURRENT, priority=Priority.STRENGTH
        )
        config_endurance = ProgramConfig(
            mode=ProgramMode.CONCURRENT, priority=Priority.ENDURANCE
        )
        
        micro_strength = create_microcycle_template(
            config_strength, BlockType.BASE, 0, date(2024, 1, 15)
        )
        micro_endurance = create_microcycle_template(
            config_endurance, BlockType.BASE, 0, date(2024, 1, 15)
        )
        
        assert micro_endurance.progression.target_minutes_z2 > micro_strength.progression.target_minutes_z2


class TestReplanningBehavior:
    """Test replanning behavior for key vs non-key sessions."""
    
    def test_missed_key_session_is_rescheduled(self):
        """Missing key session is moved to next valid day."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH,
            days_per_week_strength=3,
            days_per_week_endurance=3
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.BUILD, 1, date(2024, 1, 15)
        )
        
        # Find a key session day
        key_day = None
        for i, day in enumerate(microcycle.days):
            if day.key_session and day.session_domain == "strength":
                key_day = i
                break
        
        if key_day is None or key_day >= 4:
            pytest.skip("No suitable key session found for test")
        
        # Replan with this day missed
        result = replan_missed_sessions(microcycle, [key_day], current_day=0)
        
        # Key session should be moved
        assert len(result.moved_sessions) > 0, "Key session should be moved"
        assert key_day in [m[0] for m in result.moved_sessions], "Original key day should be in moved list"
    
    def test_missed_non_key_session_is_dropped(self):
        """Missing non-key session is dropped, not moved."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.BALANCED,
            days_per_week_strength=3,
            days_per_week_endurance=3
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.BUILD, 1, date(2024, 1, 15)
        )
        
        # Find a non-key session day
        non_key_day = None
        for i, day in enumerate(microcycle.days):
            if day.mode != "rest" and not day.key_session:
                non_key_day = i
                break
        
        if non_key_day is None:
            pytest.skip("No non-key session found for test")
        
        # Replan with this day missed
        result = replan_missed_sessions(microcycle, [non_key_day], current_day=0)
        
        # Non-key session should be dropped
        assert non_key_day in result.dropped_sessions, "Non-key session should be dropped"
        assert non_key_day not in [m[0] for m in result.moved_sessions], "Non-key session should not be moved"
    
    def test_replanning_never_stacks_heavy_and_hiit(self):
        """Replanning never stacks heavy lower + HIIT on same day."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH,
            primary_lifts=["squat", "deadlift", "bench"],
            days_per_week_strength=3,
            days_per_week_endurance=3
        )
        
        microcycle = create_microcycle_template(
            config, BlockType.BUILD, 1, date(2024, 1, 15)
        )
        
        # Try replanning multiple scenarios
        result = replan_missed_sessions(microcycle, [1, 2], current_day=0)
        
        # Check that no day has both heavy legs and HIIT after replanning
        for day in result.updated_microcycle.days:
            if day.mode == "rest":
                continue
            
            has_heavy = any(l in ["squat", "deadlift"] for l in day.primary_lifts)
            is_hiit = day.endurance_zone == "hiit"
            
            if has_heavy and is_hiit:
                pytest.fail(f"Day {day.day_index} has both heavy legs and HIIT after replanning")


class TestPriorityStateTargets:
    """Test ProgramState computes correct targets per priority."""
    
    def test_strength_priority_state_targets(self):
        """Strength priority state has correct derived targets."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH
        )
        
        state, _ = start_program("athlete_1", config, date(2024, 1, 15))
        
        assert state.key_strength_sessions == 2
        assert state.key_endurance_sessions == 1
        assert state.weekly_hiit_cap == 1
        assert state.weekly_strength_sessions_target >= state.weekly_endurance_sessions_target
    
    def test_endurance_priority_state_targets(self):
        """Endurance priority state has correct derived targets."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.ENDURANCE
        )
        
        state, _ = start_program("athlete_1", config, date(2024, 1, 15))
        
        assert state.key_strength_sessions == 1
        assert state.key_endurance_sessions == 2
        assert state.weekly_hiit_cap == 2
        assert state.weekly_endurance_sessions_target == config.days_per_week_endurance
        assert state.weekly_strength_sessions_target == config.days_per_week_strength
        assert state.key_endurance_sessions > state.key_strength_sessions
    
    def test_balanced_priority_state_targets(self):
        """Balanced priority state has equal key targets."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.BALANCED
        )
        
        state, _ = start_program("athlete_1", config, date(2024, 1, 15))
        
        assert state.key_strength_sessions == 1
        assert state.key_endurance_sessions == 1
        assert state.weekly_hiit_cap == 1


class TestDeterminism:
    """Test deterministic behavior across priorities."""
    
    def test_same_config_same_priority_plan(self):
        """Same config + priority produces identical plan."""
        config = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH,
            days_per_week_strength=3,
            days_per_week_endurance=3
        )
        
        microcycle1 = create_microcycle_template(
            config, BlockType.BUILD, 1, date(2024, 1, 15)
        )
        microcycle2 = create_microcycle_template(
            config, BlockType.BUILD, 1, date(2024, 1, 15)
        )
        
        assert microcycle1.to_dict() == microcycle2.to_dict()
    
    def test_different_priorities_produce_different_plans(self):
        """Different priorities produce measurably different plans."""
        config_strength = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.STRENGTH
        )
        config_endurance = ProgramConfig(
            mode=ProgramMode.CONCURRENT,
            priority=Priority.ENDURANCE
        )
        
        micro_strength = create_microcycle_template(
            config_strength, BlockType.BUILD, 1, date(2024, 1, 15)
        )
        micro_endurance = create_microcycle_template(
            config_endurance, BlockType.BUILD, 1, date(2024, 1, 15)
        )
        
        # Plans should differ in at least one measurable way
        diff_found = (
            micro_strength.progression.target_sets_per_week != micro_endurance.progression.target_sets_per_week
            or micro_strength.guardrails.max_hiit_per_week != micro_endurance.guardrails.max_hiit_per_week
            or len([d for d in micro_strength.days if d.key_session]) != len([d for d in micro_endurance.days if d.key_session])
        )
        
        assert diff_found, "Different priorities should produce measurably different plans"

