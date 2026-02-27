"""
Tests for performance engine.

Tests strength/endurance metrics computation, trend analysis, and report generation.
"""
import pytest
from datetime import date, timedelta

from app.domain.performance_engine import (
    TrendDirection,
    PerformanceSignal,
    StrengthSessionMetrics,
    EnduranceSessionMetrics,
    LiftPerformanceTrend,
    EndurancePerformanceTrend,
    PerformanceReport,
    compute_session_e1rm,
    compute_session_perf_y,
    compute_strength_metrics,
    analyze_lift_trend,
    compute_endurance_metrics,
    analyze_endurance_trend,
    generate_performance_report,
    apply_performance_adjustments,
    should_adjust_microcycle,
)


class TestE1RMComputation:
    """Test e1RM estimation."""
    
    def test_vbt_based_e1rm(self):
        """e1RM computed from VBT data with quality criteria."""
        sets_data = [
            {"load": 100, "reps": 5, "velocity_loss": 0.20},
            {"load": 105, "reps": 4, "velocity_loss": 0.22},
            {"load": 110, "reps": 3, "velocity_loss": 0.15},  # Best
        ]
        
        e1rm, top_load, top_reps, top_vl, method = compute_session_e1rm(
            sets_data, vbt_available=True
        )
        
        assert e1rm is not None
        assert top_load == 110
        assert top_reps == 3
        assert method == "vbt"
        # e1RM = 110 * (1 + 3/30) = 110 * 1.1 = 121
        assert e1rm == pytest.approx(121.0)
    
    def test_excludes_high_vl_sets(self):
        """Sets with VL > 0.25 are excluded."""
        sets_data = [
            {"load": 100, "reps": 5, "velocity_loss": 0.30},  # Too high
            {"load": 90, "reps": 6, "velocity_loss": 0.15},  # Used
        ]
        
        e1rm, top_load, _, _, _ = compute_session_e1rm(sets_data, vbt_available=True)
        
        assert top_load == 90  # Not 100 because VL was too high
    
    def test_excludes_high_rep_sets(self):
        """Sets with reps > 6 are excluded."""
        sets_data = [
            {"load": 100, "reps": 8, "velocity_loss": 0.15},  # Too many reps
            {"load": 90, "reps": 5, "velocity_loss": 0.15},  # Used
        ]
        
        e1rm, top_load, _, _, _ = compute_session_e1rm(sets_data, vbt_available=True)
        
        assert top_load == 90
    
    def test_fallback_without_vbt(self):
        """Without VBT, uses highest load."""
        sets_data = [
            {"load": 100, "reps": 5},
            {"load": 110, "reps": 3},
        ]
        
        e1rm, top_load, top_reps, _, method = compute_session_e1rm(
            sets_data, vbt_available=False
        )
        
        assert top_load == 110
        assert method == "formula"


class TestPerfYComputation:
    """Test velocity-normalized performance."""
    
    def test_median_of_first_two_reps(self):
        """Uses median of first 2 reps per set."""
        sets_data = [
            {
                "rep_data": [
                    {"velocity": 0.55},  # y = 1.1
                    {"velocity": 0.50},  # y = 1.0
                    {"velocity": 0.45},  # Ignored (3rd rep)
                ]
            },
            {
                "rep_data": [
                    {"velocity": 0.52},  # y = 1.04
                    {"velocity": 0.48},  # y = 0.96
                ]
            }
        ]
        
        perf_y, reps_used = compute_session_perf_y(sets_data, v_ref=0.5)
        
        # Values: 1.1, 1.0, 1.04, 0.96
        # Should be around 1.0-1.04 range
        assert 0.95 <= perf_y <= 1.1
        assert reps_used == 4


class TestStrengthMetrics:
    """Test complete strength metrics computation."""
    
    def test_quality_session(self):
        """Quality session meets all criteria."""
        sets_data = [
            {
                "load": 100,
                "reps": 5,
                "velocity_loss": 0.20,
                "rep_data": [{"velocity": 0.52}, {"velocity": 0.48}]
            }
        ]
        
        metrics = compute_strength_metrics(
            "squat", date(2024, 1, 15), sets_data, vbt_available=True
        )
        
        assert metrics.lift == "squat"
        assert metrics.quality_ok is True
        assert metrics.e1rm_est is not None
        assert metrics.perf_y is not None
    
    def test_poor_quality_without_vbt(self):
        """Session without VBT has lower quality."""
        sets_data = [{"load": 100, "reps": 5}]
        
        metrics = compute_strength_metrics(
            "squat", date(2024, 1, 15), sets_data, vbt_available=False
        )
        
        assert metrics.quality_ok is True  # Still ok with formula
        assert metrics.e1rm_method == "formula"


class TestLiftTrendAnalysis:
    """Test lift performance trend analysis."""
    
    def test_detects_pr(self):
        """Detects e1RM PR."""
        sessions = [
            StrengthSessionMetrics(
                lift="squat",
                session_date=date(2024, 1, 1),
                e1rm_est=100,
                perf_y=1.0,
                quality_ok=True
            ),
            StrengthSessionMetrics(
                lift="squat",
                session_date=date(2024, 1, 15),
                e1rm_est=102,  # > 1% improvement
                perf_y=1.0,
                quality_ok=True
            ),
        ]
        
        trend = analyze_lift_trend("squat", sessions, date(2024, 1, 15))
        
        assert trend.is_e1rm_pr is True
    
    def test_detects_regression(self):
        """Detects performance regression."""
        # Create sessions showing decline
        sessions = []
        base_date = date(2024, 1, 1)
        
        # Previous 7 days: good performance
        for i in range(3):
            sessions.append(StrengthSessionMetrics(
                lift="squat",
                session_date=base_date + timedelta(days=i),
                e1rm_est=110,
                quality_ok=True
            ))
        
        # Current 7 days: declining
        for i in range(3):
            sessions.append(StrengthSessionMetrics(
                lift="squat",
                session_date=base_date + timedelta(days=10+i),
                e1rm_est=100,  # Lower
                quality_ok=True
            ))
        
        trend = analyze_lift_trend("squat", sessions, base_date + timedelta(days=14))
        
        assert trend.e1rm_trend == TrendDirection.REGRESSING
    
    def test_detects_improvement(self):
        """Detects performance improvement."""
        sessions = []
        base_date = date(2024, 1, 1)
        
        # Previous 7 days: baseline
        for i in range(3):
            sessions.append(StrengthSessionMetrics(
                lift="squat",
                session_date=base_date + timedelta(days=i),
                e1rm_est=100,
                quality_ok=True
            ))
        
        # Current 7 days: improving
        for i in range(3):
            sessions.append(StrengthSessionMetrics(
                lift="squat",
                session_date=base_date + timedelta(days=10+i),
                e1rm_est=110,  # Higher
                quality_ok=True
            ))
        
        trend = analyze_lift_trend("squat", sessions, base_date + timedelta(days=14))
        
        assert trend.e1rm_trend == TrendDirection.IMPROVING


class TestEnduranceMetrics:
    """Test endurance metrics computation."""
    
    def test_cycling_power_metrics(self):
        """Computes cycling power metrics."""
        session_data = {
            "best_5min_power": 300,
            "best_20min_power": 280,
            "avg_power": 250,
            "normalized_power": 260,
            "duration_min": 60,
            "tss": 80,
        }
        
        metrics = compute_endurance_metrics(
            "cycling", date(2024, 1, 15), session_data
        )
        
        assert metrics.sport == "cycling"
        assert metrics.best_5min_power == 300
        assert metrics.best_20min_power == 280
        assert metrics.quality_ok is True
    
    def test_running_pace_metrics(self):
        """Computes running pace metrics."""
        session_data = {
            "avg_pace": 5.0,  # min/km
            "best_pace": 4.5,
            "duration_min": 45,
        }
        
        metrics = compute_endurance_metrics(
            "running", date(2024, 1, 15), session_data
        )
        
        assert metrics.sport == "running"
        assert metrics.avg_pace == 5.0
        assert metrics.quality_ok is True


class TestEnduranceTrendAnalysis:
    """Test endurance trend analysis."""
    
    def test_detects_power_pr(self):
        """Detects power PR."""
        sessions = [
            EnduranceSessionMetrics(
                sport="cycling",
                session_date=date(2024, 1, 1),
                best_20min_power=250,
                quality_ok=True
            ),
            EnduranceSessionMetrics(
                sport="cycling",
                session_date=date(2024, 1, 15),
                best_20min_power=260,  # > 1% improvement
                quality_ok=True
            ),
        ]
        
        trend = analyze_endurance_trend("cycling", sessions, date(2024, 1, 15))
        
        assert trend.is_20min_power_pr is True


class TestPerformanceReport:
    """Test complete performance report generation."""
    
    def test_generates_complete_report(self):
        """Generates report with all components."""
        strength_sessions = {
            "squat": [
                StrengthSessionMetrics(
                    lift="squat",
                    session_date=date(2024, 1, 15),
                    e1rm_est=150,
                    perf_y=1.05,
                    quality_ok=True
                )
            ]
        }
        
        endurance_sessions = {
            "cycling": [
                EnduranceSessionMetrics(
                    sport="cycling",
                    session_date=date(2024, 1, 15),
                    best_20min_power=280,
                    quality_ok=True
                )
            ]
        }
        
        report = generate_performance_report(
            "athlete_1",
            strength_sessions,
            endurance_sessions,
            days=28,
            today=date(2024, 1, 15)
        )
        
        assert report.athlete_id == "athlete_1"
        assert "squat" in report.lift_trends
        assert "cycling" in report.endurance_trends
    
    def test_detects_overreaching(self):
        """Detects overreaching signal."""
        # Multiple lifts regressing
        strength_sessions = {
            "squat": [
                StrengthSessionMetrics(
                    lift="squat",
                    session_date=date(2024, 1, 1),
                    e1rm_est=150,
                    quality_ok=True
                ),
                StrengthSessionMetrics(
                    lift="squat",
                    session_date=date(2024, 1, 15),
                    e1rm_est=135,  # 10% drop
                    quality_ok=True
                ),
            ],
            "bench": [
                StrengthSessionMetrics(
                    lift="bench",
                    session_date=date(2024, 1, 1),
                    e1rm_est=100,
                    quality_ok=True
                ),
                StrengthSessionMetrics(
                    lift="bench",
                    session_date=date(2024, 1, 15),
                    e1rm_est=90,  # 10% drop
                    quality_ok=True
                ),
            ]
        }
        
        report = generate_performance_report(
            "athlete_1",
            strength_sessions,
            {},
            days=28,
            today=date(2024, 1, 15)
        )
        
        # Should detect regression
        assert report.overall_signal in [PerformanceSignal.OVERREACHING, PerformanceSignal.DELOAD_SUGGESTED]
    
    def test_detects_progress(self):
        """Detects progress signal for increasing load."""
        base_date = date(2024, 1, 1)

        # Create more data points for trend detection
        squat_sessions = []
        bench_sessions = []

        for i in range(8):  # 8 sessions over 4 weeks
            # Gradual improvement pattern
            e1rm_squat = 140 + (i * 2)  # 140 -> 154
            e1rm_bench = 90 + (i * 1.5)  # 90 -> 100
            perf_y = 1.0 + (i * 0.005)  # Gradual velocity improvement

            squat_sessions.append(StrengthSessionMetrics(
                lift="squat",
                session_date=base_date + timedelta(days=i * 4),
                e1rm_est=e1rm_squat,
                perf_y=perf_y,
                quality_ok=True
            ))

            bench_sessions.append(StrengthSessionMetrics(
                lift="bench",
                session_date=base_date + timedelta(days=i * 4),
                e1rm_est=e1rm_bench,
                perf_y=perf_y,
                quality_ok=True
            ))

        # Final sessions with PRs
        squat_sessions.append(StrengthSessionMetrics(
            lift="squat",
            session_date=base_date + timedelta(days=35),
            e1rm_est=158,  # PR (>10% from start)
            perf_y=1.05,   # Velocity PR
            quality_ok=True
        ))

        bench_sessions.append(StrengthSessionMetrics(
            lift="bench",
            session_date=base_date + timedelta(days=35),
            e1rm_est=102,  # Also improving
            quality_ok=True
        ))

        strength_sessions = {
            "squat": squat_sessions,
            "bench": bench_sessions
        }

        report = generate_performance_report(
            "athlete_1",
            strength_sessions,
            {},
            days=42,
            today=base_date + timedelta(days=35)
        )

        # With 2 lifts improving and at least 1 PR, should signal increase
        assert report.overall_signal == PerformanceSignal.INCREASE_LOAD
        assert report.volume_adjustment_pct > 0


class TestProgramIntegration:
    """Test integration with program engine."""
    
    def test_apply_volume_adjustment(self):
        """Applies volume adjustment to targets."""
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            volume_adjustment_pct=0.05,
            overall_signal=PerformanceSignal.INCREASE_LOAD
        )
        
        targets = {"target_sets_per_week": 12}
        adjusted = apply_performance_adjustments(report, targets)
        
        # 12 * 1.05 = 12.6 -> int = 12
        assert adjusted["target_sets_per_week"] == 12
    
    def test_apply_intensity_adjustment(self):
        """Applies intensity adjustment to targets."""
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            intensity_adjustment_pct=0.02,
            overall_signal=PerformanceSignal.INCREASE_LOAD
        )
        
        targets = {"target_avg_intensity": 0.80}
        adjusted = apply_performance_adjustments(report, targets)
        
        # 0.80 * 1.02 = 0.816
        assert adjusted["target_avg_intensity"] == pytest.approx(0.816)
    
    def test_deload_trigger(self):
        """Triggers deload on regression."""
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            suggest_deload=True,
            signal_reason="Regression detected",
            overall_signal=PerformanceSignal.DELOAD_SUGGESTED
        )
        
        targets = {"target_sets_per_week": 12}
        adjusted = apply_performance_adjustments(report, targets)
        
        assert adjusted.get("force_deload") is True
    
    def test_should_adjust_microcycle(self):
        """Determines if microcycle should be adjusted."""
        report = PerformanceReport(
            athlete_id="test",
            report_date=date.today(),
            days_analyzed=28,
            overall_signal=PerformanceSignal.DELOAD_SUGGESTED
        )
        
        assert should_adjust_microcycle(report) is True
        
        # Should not adjust on maintain
        report.overall_signal = PerformanceSignal.MAINTAIN
        assert should_adjust_microcycle(report) is False


class TestDeterminism:
    """Test deterministic behavior."""
    
    def test_same_input_same_output(self):
        """Same inputs produce same report."""
        sessions = {
            "squat": [
                StrengthSessionMetrics(
                    lift="squat",
                    session_date=date(2024, 1, 15),
                    e1rm_est=150,
                    quality_ok=True
                )
            ]
        }
        
        report1 = generate_performance_report("a", sessions, {}, 28, date(2024, 1, 15))
        report2 = generate_performance_report("a", sessions, {}, 28, date(2024, 1, 15))
        
        assert report1.overall_signal == report2.overall_signal
        assert report1.volume_adjustment_pct == report2.volume_adjustment_pct
