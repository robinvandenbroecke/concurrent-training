"""
Performance service layer.

Orchestrates performance metric computation, storage, and feedback to program engine.
"""
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
import json

from sqlalchemy.orm import Session

from app.domain.performance_engine import (
    StrengthSessionMetrics,
    EnduranceSessionMetrics,
    PerformanceReport,
    compute_strength_metrics,
    compute_endurance_metrics,
    generate_performance_report,
    apply_performance_adjustments,
    should_adjust_microcycle,
    PerformanceSignal,
)
from app.models import PerformanceSnapshot, StrengthSession, EnduranceSession


def fetch_strength_sessions_for_analysis(
    db: Session,
    athlete_id: int,
    days: int = 28,
    end_date: date = None
) -> Dict[str, List[StrengthSessionMetrics]]:
    """
    Fetch and convert strength sessions for performance analysis.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        days: Number of days to look back
        end_date: End date (default: today)
    
    Returns:
        Dict of lift -> list of StrengthSessionMetrics
    """
    end_date = end_date or date.today()
    start_date = end_date - timedelta(days=days)
    
    # Query sessions
    sessions = db.query(StrengthSession).filter(
        StrengthSession.athlete_id == athlete_id,
        StrengthSession.start_time >= start_date.isoformat(),
        StrengthSession.start_time <= (end_date + timedelta(days=1)).isoformat()
    ).all()
    
    # Group by lift and convert
    lift_sessions: Dict[str, List[StrengthSessionMetrics]] = {}
    
    for session in sessions:
        lift = session.lift.value if hasattr(session.lift, 'value') else str(session.lift)
        
        if lift not in lift_sessions:
            lift_sessions[lift] = []
        
        # Parse raw_data for set information
        raw_data = session.raw_data or {}
        sets_data = raw_data.get("sets", [])
        
        # Compute metrics
        metrics = compute_strength_metrics(
            lift=lift,
            session_date=session.start_time.date() if hasattr(session.start_time, 'date') else end_date,
            sets_data=sets_data,
            vbt_available=bool(session.rep_level_log),
            v_ref=raw_data.get("v_ref", 0.5)
        )
        
        # Override with stored data if available
        if session.tonnage and session.avg_intensity:
            # Use stored values to enhance metrics
            pass
        
        lift_sessions[lift].append(metrics)
    
    return lift_sessions


def fetch_endurance_sessions_for_analysis(
    db: Session,
    athlete_id: int,
    days: int = 28,
    end_date: date = None
) -> Dict[str, List[EnduranceSessionMetrics]]:
    """
    Fetch and convert endurance sessions for performance analysis.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        days: Number of days to look back
        end_date: End date (default: today)
    
    Returns:
        Dict of sport -> list of EnduranceSessionMetrics
    """
    end_date = end_date or date.today()
    start_date = end_date - timedelta(days=days)
    
    # Query sessions
    sessions = db.query(EnduranceSession).filter(
        EnduranceSession.athlete_id == athlete_id,
        EnduranceSession.start_time >= start_date.isoformat(),
        EnduranceSession.start_time <= (end_date + timedelta(days=1)).isoformat()
    ).all()
    
    # Group by sport and convert
    sport_sessions: Dict[str, List[EnduranceSessionMetrics]] = {}
    
    for session in sessions:
        sport = session.sport.value if hasattr(session.sport, 'value') else str(session.sport)
        
        if sport not in sport_sessions:
            sport_sessions[sport] = []
        
        # Parse raw_data for power/pace info
        raw_data = session.raw_data or {}
        
        session_data = {
            "best_5min_power": raw_data.get("best_5min_power"),
            "best_20min_power": raw_data.get("best_20min_power"),
            "avg_power": raw_data.get("avg_power"),
            "normalized_power": raw_data.get("normalized_power"),
            "avg_pace": raw_data.get("avg_pace"),
            "best_pace": raw_data.get("best_pace"),
            "duration_min": session.duration_minutes,
            "tss": raw_data.get("tss"),
            "trimp": raw_data.get("trimp"),
        }
        
        # Compute metrics
        metrics = compute_endurance_metrics(
            sport=sport,
            session_date=session.start_time.date() if hasattr(session.start_time, 'date') else end_date,
            session_data=session_data
        )
        
        sport_sessions[sport].append(metrics)
    
    return sport_sessions


def compute_and_store_performance_report(
    db: Session,
    athlete_id: int,
    days: int = 28,
    report_date: date = None
) -> PerformanceReport:
    """
    Compute performance report and store snapshot.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        days: Number of days to analyze
        report_date: Report date (default: today)
    
    Returns:
        PerformanceReport
    """
    report_date = report_date or date.today()
    
    # Fetch sessions
    strength_sessions = fetch_strength_sessions_for_analysis(
        db, athlete_id, days, report_date
    )
    endurance_sessions = fetch_endurance_sessions_for_analysis(
        db, athlete_id, days, report_date
    )
    
    # Generate report
    report = generate_performance_report(
        athlete_id=str(athlete_id),
        strength_sessions=strength_sessions,
        endurance_sessions=endurance_sessions,
        days=days,
        today=report_date
    )
    
    # Store snapshot
    snapshot = PerformanceSnapshot(
        athlete_id=athlete_id,
        snapshot_date=report_date.isoformat(),
        days_analyzed=days,
        metrics_json=report.to_dict(),
        overall_signal=report.overall_signal.value,
        suggest_deload=report.suggest_deload,
        volume_adjustment_pct=report.volume_adjustment_pct,
        intensity_adjustment_pct=report.intensity_adjustment_pct,
    )
    
    db.add(snapshot)
    db.commit()
    
    return report


def get_latest_performance_report(
    db: Session,
    athlete_id: int,
    max_age_days: int = 7
) -> Optional[PerformanceReport]:
    """
    Get latest performance report if not too old.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        max_age_days: Maximum age of report to return
    
    Returns:
        PerformanceReport or None
    """
    snapshot = db.query(PerformanceSnapshot).filter(
        PerformanceSnapshot.athlete_id == athlete_id
    ).order_by(PerformanceSnapshot.snapshot_date.desc()).first()
    
    if not snapshot:
        return None
    
    # Check age
    snapshot_date = date.fromisoformat(snapshot.snapshot_date)
    age_days = (date.today() - snapshot_date).days
    
    if age_days > max_age_days:
        return None
    
    # Reconstruct report from JSON
    return PerformanceReport(
        athlete_id=str(athlete_id),
        report_date=snapshot_date,
        days_analyzed=snapshot.days_analyzed,
        # Parse from metrics_json
        **snapshot.metrics_json
    )


def get_or_compute_performance_report(
    db: Session,
    athlete_id: int,
    days: int = 28,
    force_recompute: bool = False
) -> PerformanceReport:
    """
    Get cached report or compute new one.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        days: Number of days to analyze
        force_recompute: Force new computation even if cached
    
    Returns:
        PerformanceReport
    """
    if not force_recompute:
        cached = get_latest_performance_report(db, athlete_id)
        if cached:
            return cached
    
    return compute_and_store_performance_report(db, athlete_id, days)


def apply_performance_to_program_targets(
    report: PerformanceReport,
    current_targets: Dict
) -> Dict:
    """
    Apply performance report adjustments to program targets.
    
    Args:
        report: Performance report
        current_targets: Current program targets
    
    Returns:
        Adjusted targets
    """
    return apply_performance_adjustments(report, current_targets)


def should_trigger_deload_from_performance(
    report: PerformanceReport,
    min_signal: PerformanceSignal = PerformanceSignal.DELOAD_SUGGESTED
) -> Tuple[bool, str]:
    """
    Determine if performance signals warrant a deload.
    
    Args:
        report: Performance report
        min_signal: Minimum signal level to trigger deload
    
    Returns:
        (should_deload, reason)
    """
    if report.suggest_deload:
        return True, report.signal_reason
    
    if should_adjust_microcycle(report, min_signal):
        return True, f"Performance signal: {report.overall_signal.value}"
    
    return False, ""


def get_performance_summary_for_coach(
    report: PerformanceReport
) -> Dict:
    """
    Get condensed performance summary for coach engine.
    
    Args:
        report: Performance report
    
    Returns:
        Summary dict
    """
    return {
        "overall_signal": report.overall_signal.value,
        "suggest_deload": report.suggest_deload,
        "volume_adjustment_pct": report.volume_adjustment_pct,
        "intensity_adjustment_pct": report.intensity_adjustment_pct,
        "prs_last_28d": sum(
            1 for t in report.lift_trends.values()
            if t.is_e1rm_pr or t.is_velocity_pr
        ),
        "lifts_regressing": sum(
            1 for t in report.lift_trends.values()
            if t.e1rm_trend.value == "regressing"
        ),
        "lifts_improving": sum(
            1 for t in report.lift_trends.values()
            if t.e1rm_trend.value == "improving"
        ),
    }
