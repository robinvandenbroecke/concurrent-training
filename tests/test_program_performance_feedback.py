"""
Integration tests for program-performance feedback loop.

Tests that performance signals correctly trigger program adjustments.
"""
import pytest
from datetime import date, timedelta

from app.domain.performance_engine import (
    TrendDirection,
    PerformanceSignal,
    StrengthSessionMetrics,
    EnduranceSessionMetrics,
    PerformanceReport,
    MicrocycleAdjustment,
    compute_microcycle_adjustment,
    should_force_deload,
    get_lift_priority_ranking,
)

from app.domain.program_engine import (
    ProgramConfig,
    ProgramState,
    ProgramMode,
    Priority,
    BlockType,
)


class TestOverreachingForcesDeload:
    """Test that overreaching forces deload microcycle."""
    
    def test_overreaching_signal_forces_deload(self):
        """Overreaching detection forces deload."""
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            overall_signal=PerformanceSignal.OVERREACHING,
            signal_reason="Multiple regressions with high fatigue",
            suggest_deload=True
        )
        
        adjustment = compute_microcycle_adjustment(
            report, priority="balanced"
        )
        
        assert adjustment.force_deload is True
        assert adjustment.reduce_key_session_intensity is True
        assert "Overreaching" in adjustment.explanation
    
    def test_should_force_deload_function(self):
        """should_force_deload returns True for overreaching."""
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            overall_signal=PerformanceSignal.OVERREACHING,
            signal_reason="High fatigue",
            suggest_deload=True
        )
        
        should_deload, reason = should_force_deload(report)
        
        assert should_deload is True
        assert "Overreaching" in reason
    
    def test_consecutive_regressions_force_deload(self):
        """Two consecutive regressing microcycles force deload."""
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            overall_signal=PerformanceSignal.MAINTAIN,
            suggest_deload=False
        )
        
        should_deload, reason = should_force_deload(
            report, consecutive_regressing_microcycles=2
        )
        
        assert should_deload is True
        assert "Two consecutive" in reason


class TestStagnationAddsStimulus:
    """Test that stagnating lifts get extra stimulus."""
    
    def test_strength_stagnation_adds_backoff_set(self):
        """Stagnating strength lift adds +1 backoff set."""
        from app.domain.performance_engine import LiftPerformanceTrend
        
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            lift_trends={
                "squat": LiftPerformanceTrend(
                    lift="squat",
                    e1rm_trend=TrendDirection.STAGNANT,
                    current_e1rm=150
                )
            },
            overall_signal=PerformanceSignal.REDUCE_VOLUME
        )
        
        # Even counter = add backoff set
        adjustment = compute_microcycle_adjustment(
            report, priority="strength", microcycles_since_stimulus_change=2
        )
        
        assert "squat" in adjustment.add_stimulus_lifts
        assert "backoff set" in adjustment.explanation or "top-set" in adjustment.explanation
    
    def test_strength_stagnation_increases_top_set_on_odd_counter(self):
        """Stagnating strength lift increases top-set on odd counter."""
        from app.domain.performance_engine import LiftPerformanceTrend
        
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            lift_trends={
                "squat": LiftPerformanceTrend(
                    lift="squat",
                    e1rm_trend=TrendDirection.STAGNANT,
                    current_e1rm=150
                )
            },
            overall_signal=PerformanceSignal.MAINTAIN
        )
        
        # Odd counter = increase top-set
        adjustment = compute_microcycle_adjustment(
            report, priority="strength", microcycles_since_stimulus_change=3
        )
        
        assert "squat" in adjustment.add_stimulus_lifts
    
    def test_no_stimulus_if_recently_changed(self):
        """No stimulus change if <2 microcycles since last change."""
        from app.domain.performance_engine import LiftPerformanceTrend
        
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            lift_trends={
                "squat": LiftPerformanceTrend(
                    lift="squat",
                    e1rm_trend=TrendDirection.STAGNANT,
                    current_e1rm=150
                )
            }
        )
        
        adjustment = compute_microcycle_adjustment(
            report, priority="strength", microcycles_since_stimulus_change=0
        )
        
        # Should not add stimulus if < 2 microcycles
        assert len(adjustment.add_stimulus_lifts) == 0


class TestEnduranceStagnation:
    """Test that endurance stagnation modifies endurance templates."""
    
    def test_endurance_stagnation_replaces_z2_with_tempo(self):
        """Stagnating endurance replaces Z2 with tempo."""
        from app.domain.performance_engine import EndurancePerformanceTrend
        
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            endurance_trends={
                "cycling": EndurancePerformanceTrend(
                    sport="cycling",
                    power_trend=TrendDirection.STAGNANT,
                    current_20min_power=280
                )
            },
            overall_signal=PerformanceSignal.MAINTAIN
        )
        
        # Even counter = replace Z2 with tempo
        adjustment = compute_microcycle_adjustment(
            report, priority="endurance", microcycles_since_stimulus_change=2
        )
        
        assert adjustment.replace_z2_with_tempo is True
        assert "tempo" in adjustment.explanation
    
    def test_endurance_stagnation_adds_hiit_intervals(self):
        """Stagnating endurance adds HIIT intervals."""
        from app.domain.performance_engine import EndurancePerformanceTrend
        
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            endurance_trends={
                "cycling": EndurancePerformanceTrend(
                    sport="cycling",
                    power_trend=TrendDirection.STAGNANT,
                    current_20min_power=280
                )
            }
        )
        
        # Odd counter = add HIIT
        adjustment = compute_microcycle_adjustment(
            report, priority="endurance", microcycles_since_stimulus_change=3
        )
        
        assert adjustment.add_hiit_intervals == 1
        assert "HIIT" in adjustment.explanation


class TestProgressMaintainsPlan:
    """Test that progress maintains planned progression."""
    
    def test_progress_keeps_planned_progression(self):
        """Progress signal maintains current plan."""
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            overall_signal=PerformanceSignal.INCREASE_LOAD,
            signal_reason="Consistent improvement with PRs"
        )
        
        adjustment = compute_microcycle_adjustment(
            report, priority="balanced"
        )
        
        assert adjustment.force_deload is False
        assert adjustment.replace_z2_with_tempo is False
        assert len(adjustment.add_stimulus_lifts) == 0
        assert "maintaining" in adjustment.explanation.lower() or "progress" in adjustment.explanation.lower()


class TestRegressionHoldsVolume:
    """Test that regression holds volume constant."""
    
    def test_regression_holds_volume(self):
        """Regression signal holds volume constant."""
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            overall_signal=PerformanceSignal.DELOAD_SUGGESTED,
            signal_reason="Regression detected"
        )
        
        adjustment = compute_microcycle_adjustment(
            report, priority="balanced"
        )
        
        assert adjustment.hold_volume_constant is True
        assert "holding" in adjustment.explanation.lower() or "Regression" in adjustment.explanation


class TestLiftPriorityRanking:
    """Test lift priority ranking based on trends."""
    
    def test_regressing_lifts_ranked_highest(self):
        """Regressing lifts get highest priority."""
        from app.domain.performance_engine import LiftPerformanceTrend
        
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            lift_trends={
                "squat": LiftPerformanceTrend(
                    lift="squat",
                    e1rm_trend=TrendDirection.REGRESSING,
                    current_e1rm=140
                ),
                "bench": LiftPerformanceTrend(
                    lift="bench",
                    e1rm_trend=TrendDirection.IMPROVING,
                    current_e1rm=100
                ),
                "deadlift": LiftPerformanceTrend(
                    lift="deadlift",
                    e1rm_trend=TrendDirection.STAGNANT,
                    current_e1rm=180
                )
            }
        )
        
        rankings = get_lift_priority_ranking(report)
        
        # Regressing (squat) should be first
        assert rankings[0][0] == "squat"
        assert rankings[0][1] == 3.0  # Highest score
        
        # Stagnant (deadlift) should be second
        assert rankings[1][0] == "deadlift"
        assert rankings[1][1] == 2.0
        
        # Improving (bench) should be last
        assert rankings[2][0] == "bench"
        assert rankings[2][1] == 1.0
    
    def test_regressing_lift_prioritized_for_quality(self):
        """Regressing lift while others progress gets prioritized."""
        from app.domain.performance_engine import LiftPerformanceTrend
        
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            lift_trends={
                "squat": LiftPerformanceTrend(
                    lift="squat",
                    e1rm_trend=TrendDirection.REGRESSING,
                    current_e1rm=140
                ),
                "bench": LiftPerformanceTrend(
                    lift="bench",
                    e1rm_trend=TrendDirection.IMPROVING,
                    current_e1rm=105
                )
            }
        )
        
        adjustment = compute_microcycle_adjustment(
            report, priority="strength"
        )
        
        # Should prioritize squat since it's regressing while bench improves
        assert adjustment.prioritize_lift == "squat"


class TestDeterminism:
    """Test deterministic behavior of adjustments."""
    
    def test_same_report_same_adjustment(self):
        """Same inputs produce same adjustment."""
        from app.domain.performance_engine import LiftPerformanceTrend
        
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            lift_trends={
                "squat": LiftPerformanceTrend(
                    lift="squat",
                    e1rm_trend=TrendDirection.STAGNANT
                )
            }
        )
        
        adj1 = compute_microcycle_adjustment(
            report, priority="strength", microcycles_since_stimulus_change=2
        )
        adj2 = compute_microcycle_adjustment(
            report, priority="strength", microcycles_since_stimulus_change=2
        )
        
        assert adj1.force_deload == adj2.force_deload
        assert adj1.replace_z2_with_tempo == adj2.replace_z2_with_tempo
        assert adj1.add_stimulus_lifts == adj2.add_stimulus_lifts
