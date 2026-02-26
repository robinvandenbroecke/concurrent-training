"""
Performance Engine for quantifying training progress and feeding back into program planning.

Computes deterministic performance metrics from strength and endurance sessions,
detects trends (progress, stagnation, regression), and provides signals for
program adjustments.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import date, timedelta
import json
import math


class TrendDirection(str, Enum):
    """Direction of performance trend."""
    IMPROVING = "improving"
    STABLE = "stable"
    STAGNANT = "stagnant"
    REGRESSING = "regressing"
    OVERREACHING = "overreaching"


class PerformanceSignal(str, Enum):
    """Actionable signals from performance analysis."""
    INCREASE_LOAD = "increase_load"  # Progress detected, can push
    MAINTAIN = "maintain"  # Stable, continue as planned
    REDUCE_VOLUME = "reduce_volume"  # Stagnation, may need change
    DELOAD_SUGGESTED = "deload_suggested"  # Regression/overreaching detected
    OVERREACHING = "overreaching"  # Multiple regressions - deload required


@dataclass
class StrengthSessionMetrics:
    """Performance metrics from a single strength session."""
    lift: str
    session_date: date
    
    # e1RM estimates
    e1rm_est: Optional[float] = None  # Estimated 1RM
    e1rm_method: str = "unknown"  # "vbt", "rpe", "formula"
    
    # Top set data
    top_set_load: Optional[float] = None
    top_set_reps: Optional[int] = None
    top_set_vl: Optional[float] = None  # Velocity loss
    
    # Velocity performance
    perf_y: Optional[float] = None  # v_obs/v_ref, higher is better
    perf_y_reps: Optional[int] = None  # Reps used for perf_y calculation
    
    # Quality flags
    quality_ok: bool = False  # Session met criteria for reliable metrics
    
    def to_dict(self) -> dict:
        return {
            "lift": self.lift,
            "session_date": self.session_date.isoformat(),
            "e1rm_est": self.e1rm_est,
            "e1rm_method": self.e1rm_method,
            "top_set_load": self.top_set_load,
            "top_set_reps": self.top_set_reps,
            "top_set_vl": self.top_set_vl,
            "perf_y": self.perf_y,
            "perf_y_reps": self.perf_y_reps,
            "quality_ok": self.quality_ok,
        }


@dataclass
class EnduranceSessionMetrics:
    """Performance metrics from a single endurance session."""
    sport: str  # "cycling", "running", "swimming"
    session_date: date
    
    # Power-based metrics (cycling)
    best_5min_power: Optional[float] = None
    best_20min_power: Optional[float] = None
    avg_power: Optional[float] = None
    normalized_power: Optional[float] = None
    
    # Pace-based metrics (running/swimming)
    avg_pace: Optional[float] = None  # min/km or min/100m
    best_pace: Optional[float] = None
    
    # Duration and load
    duration_min: float = 0.0
    tss: Optional[float] = None  # Training Stress Score if available
    trimp: Optional[float] = None  # TRIMP score if available
    
    # Quality flags
    quality_ok: bool = False
    
    def to_dict(self) -> dict:
        return {
            "sport": self.sport,
            "session_date": self.session_date.isoformat(),
            "best_5min_power": self.best_5min_power,
            "best_20min_power": self.best_20min_power,
            "avg_power": self.avg_power,
            "normalized_power": self.normalized_power,
            "avg_pace": self.avg_pace,
            "best_pace": self.best_pace,
            "duration_min": self.duration_min,
            "tss": self.tss,
            "trimp": self.trimp,
            "quality_ok": self.quality_ok,
        }


@dataclass
class LiftPerformanceTrend:
    """Performance trend for a specific lift."""
    lift: str
    
    # Current values
    current_e1rm: Optional[float] = None
    current_perf_y: Optional[float] = None
    
    # Historical context
    best_28d_e1rm: Optional[float] = None
    best_90d_e1rm: Optional[float] = None
    best_28d_perf_y: Optional[float] = None
    
    # PR detection
    is_e1rm_pr: bool = False
    is_velocity_pr: bool = False
    
    # Trend analysis
    e1rm_trend: TrendDirection = TrendDirection.STABLE
    perf_y_trend: TrendDirection = TrendDirection.STABLE
    
    # Rolling averages (last 7 days vs previous 7)
    e1rm_7d_avg: Optional[float] = None
    e1rm_prev_7d_avg: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            "lift": self.lift,
            "current_e1rm": self.current_e1rm,
            "current_perf_y": self.current_perf_y,
            "best_28d_e1rm": self.best_28d_e1rm,
            "best_90d_e1rm": self.best_90d_e1rm,
            "best_28d_perf_y": self.best_28d_perf_y,
            "is_e1rm_pr": self.is_e1rm_pr,
            "is_velocity_pr": self.is_velocity_pr,
            "e1rm_trend": self.e1rm_trend.value,
            "perf_y_trend": self.perf_y_trend.value,
            "e1rm_7d_avg": self.e1rm_7d_avg,
            "e1rm_prev_7d_avg": self.e1rm_prev_7d_avg,
        }


@dataclass
class EndurancePerformanceTrend:
    """Performance trend for endurance."""
    sport: str
    
    # Current bests
    current_5min_power: Optional[float] = None
    current_20min_power: Optional[float] = None
    current_avg_pace: Optional[float] = None
    
    # Historical context
    best_28d_5min_power: Optional[float] = None
    best_28d_20min_power: Optional[float] = None
    best_28d_pace: Optional[float] = None
    
    # PR detection
    is_5min_power_pr: bool = False
    is_20min_power_pr: bool = False
    is_pace_pr: bool = False
    
    # Trend analysis
    power_trend: TrendDirection = TrendDirection.STABLE
    pace_trend: TrendDirection = TrendDirection.STABLE
    
    def to_dict(self) -> dict:
        return {
            "sport": self.sport,
            "current_5min_power": self.current_5min_power,
            "current_20min_power": self.current_20min_power,
            "current_avg_pace": self.current_avg_pace,
            "best_28d_5min_power": self.best_28d_5min_power,
            "best_28d_20min_power": self.best_28d_20min_power,
            "best_28d_pace": self.best_28d_pace,
            "is_5min_power_pr": self.is_5min_power_pr,
            "is_20min_power_pr": self.is_20min_power_pr,
            "is_pace_pr": self.is_pace_pr,
            "power_trend": self.power_trend.value,
            "pace_trend": self.pace_trend.value,
        }


@dataclass
class PerformanceReport:
    """Complete performance report for an athlete."""
    athlete_id: str
    report_date: date
    days_analyzed: int
    
    # Per-lift trends
    lift_trends: Dict[str, LiftPerformanceTrend] = field(default_factory=dict)
    
    # Endurance trends by sport
    endurance_trends: Dict[str, EndurancePerformanceTrend] = field(default_factory=dict)
    
    # Overall signals
    overall_signal: PerformanceSignal = PerformanceSignal.MAINTAIN
    signal_reason: str = ""
    
    # Program adjustment recommendations
    volume_adjustment_pct: float = 0.0  # -0.10 to +0.10
    intensity_adjustment_pct: float = 0.0  # -0.05 to +0.05
    suggest_deload: bool = False
    
    def to_dict(self) -> dict:
        return {
            "athlete_id": self.athlete_id,
            "report_date": self.report_date.isoformat(),
            "days_analyzed": self.days_analyzed,
            "lift_trends": {k: v.to_dict() for k, v in self.lift_trends.items()},
            "endurance_trends": {k: v.to_dict() for k, v in self.endurance_trends.items()},
            "overall_signal": self.overall_signal.value,
            "signal_reason": self.signal_reason,
            "volume_adjustment_pct": self.volume_adjustment_pct,
            "intensity_adjustment_pct": self.intensity_adjustment_pct,
            "suggest_deload": self.suggest_deload,
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ============================================================================
# Strength Performance Computation
# ============================================================================

def compute_session_e1rm(
    sets_data: List[Dict],
    vbt_available: bool = True
) -> Tuple[Optional[float], Optional[float], Optional[int], Optional[float], str]:
    """
    Compute e1RM estimate from session sets.
    
    Returns: (e1rm_est, top_set_load, top_set_reps, top_set_vl, method)
    """
    if not sets_data:
        return None, None, None, None, "no_data"
    
    best_set = None
    
    if vbt_available:
        # Find best set: highest load where VL <= 0.25 and reps <= 6
        for set_data in sets_data:
            load = set_data.get("load")
            reps = set_data.get("reps")
            vl = set_data.get("velocity_loss")
            
            if load is None or reps is None:
                continue
            
            # Quality criteria for e1RM estimation
            if vl is not None and vl > 0.25:
                continue
            if reps > 6:
                continue
            
            if best_set is None or load > best_set["load"]:
                best_set = {
                    "load": load,
                    "reps": reps,
                    "vl": vl,
                }
    else:
        # No VBT: use highest load regardless
        for set_data in sets_data:
            load = set_data.get("load")
            reps = set_data.get("reps")
            
            if load is None or reps is None:
                continue
            
            if best_set is None or load > best_set["load"]:
                best_set = {
                    "load": load,
                    "reps": reps,
                    "vl": None,
                }
    
    if best_set is None:
        return None, None, None, None, "no_valid_set"
    
    # Compute e1RM using simple formula: load * (1 + reps/30)
    e1rm = best_set["load"] * (1 + best_set["reps"] / 30)
    method = "vbt" if vbt_available else "formula"
    
    return e1rm, best_set["load"], best_set["reps"], best_set["vl"], method


def compute_session_perf_y(
    sets_data: List[Dict],
    v_ref: float = 0.5  # Reference velocity for normalization
) -> Tuple[Optional[float], Optional[int]]:
    """
    Compute velocity-normalized performance (y = v_obs/v_ref).
    Uses median of first 2 reps from best quality sets.
    
    Returns: (perf_y, reps_used)
    """
    if not sets_data or v_ref <= 0:
        return None, None
    
    y_values = []
    
    for set_data in sets_data:
        reps_data = set_data.get("rep_data", [])
        
        # Take first 2 reps
        for rep in reps_data[:2]:
            v_obs = rep.get("velocity")
            if v_obs is not None and v_obs > 0:
                y_values.append(v_obs / v_ref)
    
    if not y_values:
        return None, None
    
    # Use median
    y_values.sort()
    median_y = y_values[len(y_values) // 2]
    
    return median_y, len(y_values)


def compute_strength_metrics(
    lift: str,
    session_date: date,
    sets_data: List[Dict],
    vbt_available: bool = True,
    v_ref: float = 0.5
) -> StrengthSessionMetrics:
    """
    Compute complete strength metrics for a session.
    
    Args:
        lift: Lift name
        session_date: Date of session
        sets_data: List of set data dicts
        vbt_available: Whether VBT data is available
        v_ref: Reference velocity for normalization
    
    Returns:
        StrengthSessionMetrics
    """
    # Compute e1RM
    e1rm, top_load, top_reps, top_vl, method = compute_session_e1rm(
        sets_data, vbt_available
    )
    
    # Compute perf_y
    perf_y, perf_reps = compute_session_perf_y(sets_data, v_ref)
    
    # Quality check
    quality_ok = (
        e1rm is not None and
        top_load is not None and
        (not vbt_available or (top_vl is not None and top_vl <= 0.25))
    )
    
    return StrengthSessionMetrics(
        lift=lift,
        session_date=session_date,
        e1rm_est=e1rm,
        e1rm_method=method,
        top_set_load=top_load,
        top_set_reps=top_reps,
        top_set_vl=top_vl,
        perf_y=perf_y,
        perf_y_reps=perf_reps,
        quality_ok=quality_ok,
    )


def _compute_median(values: List[float]) -> Optional[float]:
    """Compute median of a list of values."""
    if not values:
        return None
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 0:
        return (sorted_vals[n//2 - 1] + sorted_vals[n//2]) / 2
    return sorted_vals[n//2]


def analyze_lift_trend(
    lift: str,
    sessions: List[StrengthSessionMetrics],
    today: date = None,
    day_states: Optional[List[Dict]] = None
) -> LiftPerformanceTrend:
    """
    Analyze performance trend for a lift over multiple sessions.
    
    Uses 28-day window with specific classification thresholds:
    - progress: delta >= +1.5%
    - stagnation: -1% < delta < +1.5%
    - regression: delta <= -1%
    
    Args:
        lift: Lift name
        sessions: List of session metrics (sorted by date)
        today: Reference date (default: today)
        day_states: Optional day state data for overreaching detection
    
    Returns:
        LiftPerformanceTrend
    """
    today = today or date.today()
    
    if not sessions:
        return LiftPerformanceTrend(lift=lift)
    
    # Filter quality sessions
    quality_sessions = [s for s in sessions if s.quality_ok and s.e1rm_est is not None]
    
    if not quality_sessions:
        return LiftPerformanceTrend(lift=lift)
    
    # Sort by date
    quality_sessions.sort(key=lambda s: s.session_date)
    
    # Current values (most recent)
    current = quality_sessions[-1]
    
    # Define windows
    d28 = today - timedelta(days=28)
    d8 = today - timedelta(days=8)
    d7 = today - timedelta(days=7)
    d90 = today - timedelta(days=90)
    
    # Baseline: median of weeks 2-4 (days -28 to -8)
    baseline_sessions = [s for s in quality_sessions if d28 <= s.session_date < d8]
    baseline_values = [s.e1rm_est for s in baseline_sessions if s.e1rm_est]
    baseline_median = _compute_median(baseline_values) if baseline_values else None
    
    # Recent: median of last 7 days (or last 7 non-null points)
    recent_sessions = [s for s in quality_sessions if s.session_date >= d7]
    if len(recent_sessions) < 2:
        # Use last 7 non-null points
        recent_sessions = quality_sessions[-7:] if len(quality_sessions) >= 7 else quality_sessions
    
    recent_values = [s.e1rm_est for s in recent_sessions if s.e1rm_est]
    recent_median = _compute_median(recent_values) if recent_values else None
    
    # Historical lookups for PR detection
    sessions_28d = [s for s in quality_sessions if s.session_date >= d28]
    sessions_90d = [s for s in quality_sessions if s.session_date >= d90]
    
    # Best values
    best_28d_e1rm = max((s.e1rm_est for s in sessions_28d if s.e1rm_est), default=None)
    best_90d_e1rm = max((s.e1rm_est for s in sessions_90d if s.e1rm_est), default=None)
    best_28d_perf_y = max((s.perf_y for s in sessions_28d if s.perf_y), default=None)
    
    # PR detection (compare current to historical best EXCLUDING current)
    best_90d_e1rm_excl_current = max(
        (s.e1rm_est for s in sessions_90d[:-1] if s.e1rm_est),
        default=None
    ) if len(sessions_90d) > 1 else None
    
    best_28d_perf_y_excl_current = max(
        (s.perf_y for s in sessions_28d[:-1] if s.perf_y),
        default=None
    ) if len(sessions_28d) > 1 else None
    
    is_e1rm_pr = False
    if current.e1rm_est and best_90d_e1rm_excl_current:
        is_e1rm_pr = current.e1rm_est > best_90d_e1rm_excl_current * 1.01  # 1% improvement
    
    is_velocity_pr = False
    if current.perf_y and best_28d_perf_y_excl_current:
        is_velocity_pr = current.perf_y > best_28d_perf_y_excl_current * 1.02  # 2% improvement
    
    # Trend classification with specific thresholds
    e1rm_trend = TrendDirection.STABLE
    delta = None
    
    if recent_median and baseline_median and baseline_median > 0:
        delta = (recent_median - baseline_median) / baseline_median
        
        # Classification thresholds:
        # progress: >= +1.5%
        # stagnation: -1% < delta < +1.5%
        # regression: <= -1%
        if delta >= 0.015:
            e1rm_trend = TrendDirection.IMPROVING
        elif delta <= -0.01:
            e1rm_trend = TrendDirection.REGRESSING
        else:
            e1rm_trend = TrendDirection.STAGNANT
    
    # Check for overreaching: regression + high fatigue
    if e1rm_trend == TrendDirection.REGRESSING and day_states:
        high_fatigue_days = sum(
            1 for ds in day_states[-7:]  # Last 7 days
            if ds.get("D_sys", 0) > 0.25 or ds.get("E_fat", 0) > 0.25
        )
        if high_fatigue_days >= 3:
            e1rm_trend = TrendDirection.OVERREACHING
    
    # Velocity trend (simplified)
    perf_y_trend = TrendDirection.STABLE
    current_perf_y = current.perf_y
    if current_perf_y and best_28d_perf_y and best_28d_perf_y > 0:
        perf_y_delta = (current_perf_y - best_28d_perf_y) / best_28d_perf_y
        if perf_y_delta >= 0.015:
            perf_y_trend = TrendDirection.IMPROVING
        elif perf_y_delta <= -0.01:
            perf_y_trend = TrendDirection.REGRESSING
        else:
            perf_y_trend = TrendDirection.STAGNANT
    
    return LiftPerformanceTrend(
        lift=lift,
        current_e1rm=current.e1rm_est,
        current_perf_y=current.perf_y,
        best_28d_e1rm=best_28d_e1rm,
        best_90d_e1rm=best_90d_e1rm,
        best_28d_perf_y=best_28d_perf_y,
        is_e1rm_pr=is_e1rm_pr,
        is_velocity_pr=is_velocity_pr,
        e1rm_trend=e1rm_trend,
        perf_y_trend=perf_y_trend,
        e1rm_7d_avg=recent_median,
        e1rm_prev_7d_avg=baseline_median,
    )


# ============================================================================
# Endurance Performance Computation
# ============================================================================

def compute_endurance_metrics(
    sport: str,
    session_date: date,
    session_data: Dict
) -> EnduranceSessionMetrics:
    """
    Compute endurance metrics from session data.
    
    Args:
        sport: Sport type (cycling, running, swimming)
        session_date: Date of session
        session_data: Dict with power/pace data
    
    Returns:
        EnduranceSessionMetrics
    """
    # Extract power data if available (cycling)
    best_5min = session_data.get("best_5min_power")
    best_20min = session_data.get("best_20min_power")
    avg_power = session_data.get("avg_power")
    np_power = session_data.get("normalized_power")
    
    # Extract pace data (running/swimming)
    avg_pace = session_data.get("avg_pace")
    best_pace = session_data.get("best_pace")
    
    # Load metrics
    duration = session_data.get("duration_min", 0)
    tss = session_data.get("tss")
    trimp = session_data.get("trimp")
    
    # Quality check
    quality_ok = (
        (best_5min is not None or best_20min is not None) or
        (avg_pace is not None) or
        (avg_power is not None)
    )
    
    return EnduranceSessionMetrics(
        sport=sport,
        session_date=session_date,
        best_5min_power=best_5min,
        best_20min_power=best_20min,
        avg_power=avg_power,
        normalized_power=np_power,
        avg_pace=avg_pace,
        best_pace=best_pace,
        duration_min=duration,
        tss=tss,
        trimp=trimp,
        quality_ok=quality_ok,
    )


def analyze_endurance_trend(
    sport: str,
    sessions: List[EnduranceSessionMetrics],
    today: date = None
) -> EndurancePerformanceTrend:
    """
    Analyze endurance performance trend with TP_proxy calculation.
    
    TP_proxy = 0.95 * best_20min_power (cycling)
    For running/swimming: use pace or TRIMP efficiency
    
    Classification thresholds:
    - progress: delta >= +1.5%
    - stagnation: -1% < delta < +1.5%
    - regression: delta <= -1%
    
    Args:
        sport: Sport type
        sessions: List of session metrics
        today: Reference date
    
    Returns:
        EndurancePerformanceTrend
    """
    today = today or date.today()
    
    if not sessions:
        return EndurancePerformanceTrend(sport=sport)
    
    # Filter quality sessions
    quality_sessions = [s for s in sessions if s.quality_ok]
    
    if not quality_sessions:
        return EndurancePerformanceTrend(sport=sport)
    
    quality_sessions.sort(key=lambda s: s.session_date)
    
    current = quality_sessions[-1]
    
    # Define windows
    d28 = today - timedelta(days=28)
    d8 = today - timedelta(days=8)
    d7 = today - timedelta(days=7)
    
    sessions_28d = [s for s in quality_sessions if s.session_date >= d28]
    
    # Calculate TP_proxy for each session
    def calc_tp_proxy(s: EnduranceSessionMetrics) -> Optional[float]:
        if s.best_20min_power:
            return s.best_20min_power * 0.95  # TP_proxy = 0.95 * best_20min
        elif s.normalized_power:
            return s.normalized_power * 0.90  # Estimate from NP
        elif s.avg_power:
            return s.avg_power * 0.85  # Rough estimate from avg
        return None
    
    # Baseline: median of weeks 2-4 (days -28 to -8)
    baseline_sessions = [s for s in quality_sessions if d28 <= s.session_date < d8]
    baseline_proxies = [calc_tp_proxy(s) for s in baseline_sessions if calc_tp_proxy(s)]
    baseline_median = _compute_median(baseline_proxies) if baseline_proxies else None
    
    # Recent: median of last 7 days
    recent_sessions = [s for s in quality_sessions if s.session_date >= d7]
    if len(recent_sessions) < 2:
        recent_sessions = quality_sessions[-7:] if len(quality_sessions) >= 7 else quality_sessions
    
    recent_proxies = [calc_tp_proxy(s) for s in recent_sessions if calc_tp_proxy(s)]
    recent_median = _compute_median(recent_proxies) if recent_proxies else None
    
    # Best values
    best_28d_5min = max((s.best_5min_power for s in sessions_28d if s.best_5min_power), default=None)
    best_28d_20min = max((s.best_20min_power for s in sessions_28d if s.best_20min_power), default=None)
    best_28d_pace = min((s.avg_pace for s in sessions_28d if s.avg_pace), default=None)
    
    # PR detection (compare to historical best excluding current)
    best_28d_5min_excl_current = max(
        (s.best_5min_power for s in sessions_28d[:-1] if s.best_5min_power),
        default=None
    ) if len(sessions_28d) > 1 else None
    
    best_28d_20min_excl_current = max(
        (s.best_20min_power for s in sessions_28d[:-1] if s.best_20min_power),
        default=None
    ) if len(sessions_28d) > 1 else None
    
    best_28d_pace_excl_current = min(
        (s.avg_pace for s in sessions_28d[:-1] if s.avg_pace),
        default=None
    ) if len(sessions_28d) > 1 else None
    
    is_5min_pr = False
    is_20min_pr = False
    is_pace_pr = False
    
    if current.best_5min_power and best_28d_5min_excl_current:
        is_5min_pr = current.best_5min_power >= best_28d_5min_excl_current * 1.01
    if current.best_20min_power and best_28d_20min_excl_current:
        is_20min_pr = current.best_20min_power >= best_28d_20min_excl_current * 1.01
    if current.avg_pace and best_28d_pace_excl_current:
        is_pace_pr = current.avg_pace <= best_28d_pace_excl_current * 0.99
    
    # Trend classification with specific thresholds
    power_trend = TrendDirection.STABLE
    
    if recent_median and baseline_median and baseline_median > 0:
        delta = (recent_median - baseline_median) / baseline_median
        
        if delta >= 0.015:
            power_trend = TrendDirection.IMPROVING
        elif delta <= -0.01:
            power_trend = TrendDirection.REGRESSING
        else:
            power_trend = TrendDirection.STAGNANT
    
    # Pace trend (for running/swimming) - lower is better
    pace_trend = TrendDirection.STABLE
    baseline_paces = [s.avg_pace for s in baseline_sessions if s.avg_pace]
    recent_paces = [s.avg_pace for s in recent_sessions if s.avg_pace]
    
    if baseline_paces and recent_paces:
        baseline_pace_median = _compute_median(baseline_paces)
        recent_pace_median = _compute_median(recent_paces)
        
        if baseline_pace_median and recent_pace_median and baseline_pace_median > 0:
            pace_delta = (baseline_pace_median - recent_pace_median) / baseline_pace_median  # Reversed
            
            if pace_delta >= 0.015:  # Pace improved by >= 1.5%
                pace_trend = TrendDirection.IMPROVING
            elif pace_delta <= -0.01:  # Pace worsened
                pace_trend = TrendDirection.REGRESSING
            else:
                pace_trend = TrendDirection.STAGNANT
    
    return EndurancePerformanceTrend(
        sport=sport,
        current_5min_power=current.best_5min_power,
        current_20min_power=current.best_20min_power,
        current_avg_pace=current.avg_pace,
        best_28d_5min_power=best_28d_5min,
        best_28d_20min_power=best_28d_20min,
        best_28d_pace=best_28d_pace,
        is_5min_power_pr=is_5min_pr,
        is_20min_power_pr=is_20min_pr,
        is_pace_pr=is_pace_pr,
        power_trend=power_trend,
        pace_trend=pace_trend,
    )


# ============================================================================
# Overall Performance Report
# ============================================================================

def generate_performance_report(
    athlete_id: str,
    strength_sessions: Dict[str, List[StrengthSessionMetrics]],
    endurance_sessions: Dict[str, List[EnduranceSessionMetrics]],
    days: int = 28,
    today: date = None
) -> PerformanceReport:
    """
    Generate complete performance report.
    
    Args:
        athlete_id: Athlete identifier
        strength_sessions: Dict of lift -> list of session metrics
        endurance_sessions: Dict of sport -> list of session metrics
        days: Number of days to analyze
        today: Reference date
    
    Returns:
        PerformanceReport
    """
    today = today or date.today()
    
    report = PerformanceReport(
        athlete_id=athlete_id,
        report_date=today,
        days_analyzed=days,
    )
    
    # Analyze strength trends
    for lift, sessions in strength_sessions.items():
        trend = analyze_lift_trend(lift, sessions, today)
        report.lift_trends[lift] = trend
    
    # Analyze endurance trends
    for sport, sessions in endurance_sessions.items():
        trend = analyze_endurance_trend(sport, sessions, today)
        report.endurance_trends[sport] = trend
    
    # Determine overall signal
    regression_count = 0
    improvement_count = 0
    stagnant_count = 0
    pr_count = 0
    
    for trend in report.lift_trends.values():
        if trend.e1rm_trend == TrendDirection.REGRESSING:
            regression_count += 1
        elif trend.e1rm_trend == TrendDirection.IMPROVING:
            improvement_count += 1
        elif trend.e1rm_trend == TrendDirection.STAGNANT:
            stagnant_count += 1
        
        if trend.is_e1rm_pr or trend.is_velocity_pr:
            pr_count += 1
    
    for trend in report.endurance_trends.values():
        if trend.power_trend == TrendDirection.REGRESSING:
            regression_count += 1
        elif trend.power_trend == TrendDirection.IMPROVING:
            improvement_count += 1
    
    # Determine signal and adjustments
    if regression_count >= 2:
        report.overall_signal = PerformanceSignal.OVERREACHING
        report.signal_reason = f"Multiple lifts showing regression ({regression_count})"
        report.suggest_deload = True
        report.volume_adjustment_pct = -0.15
    elif regression_count == 1 and pr_count == 0:
        report.overall_signal = PerformanceSignal.DELOAD_SUGGESTED
        report.signal_reason = "Regression detected without PRs"
        report.suggest_deload = True
        report.volume_adjustment_pct = -0.10
    elif improvement_count >= 2 and pr_count >= 1:
        report.overall_signal = PerformanceSignal.INCREASE_LOAD
        report.signal_reason = f"Consistent improvement ({improvement_count}) with PRs ({pr_count})"
        report.volume_adjustment_pct = 0.05
        report.intensity_adjustment_pct = 0.02
    elif stagnant_count >= 2 and pr_count == 0:
        report.overall_signal = PerformanceSignal.REDUCE_VOLUME
        report.signal_reason = "Stagnation detected, may need change"
        report.volume_adjustment_pct = -0.05
    else:
        report.overall_signal = PerformanceSignal.MAINTAIN
        report.signal_reason = "Stable performance, continue as planned"
    
    return report


# ============================================================================
# Program Integration
# ============================================================================

def apply_performance_adjustments(
    report: PerformanceReport,
    current_targets: Dict
) -> Dict:
    """
    Apply performance-based adjustments to program targets.
    
    Args:
        report: Performance report
        current_targets: Current program targets dict
    
    Returns:
        Adjusted targets dict
    """
    adjusted = dict(current_targets)
    
    # Apply volume adjustment
    if "target_sets_per_week" in adjusted:
        adjusted["target_sets_per_week"] = int(
            adjusted["target_sets_per_week"] * (1 + report.volume_adjustment_pct)
        )
    
    # Apply intensity adjustment
    if "target_avg_intensity" in adjusted:
        adjusted["target_avg_intensity"] = min(
            0.95,  # Cap at 95%
            adjusted["target_avg_intensity"] * (1 + report.intensity_adjustment_pct)
        )
    
    # Deload trigger
    if report.suggest_deload:
        adjusted["force_deload"] = True
        adjusted["deload_reason"] = report.signal_reason
    
    return adjusted


def should_adjust_microcycle(
    report: PerformanceReport,
    threshold_signal: PerformanceSignal = PerformanceSignal.DELOAD_SUGGESTED
) -> bool:
    """
    Determine if microcycle should be adjusted based on performance.

    Args:
        report: Performance report
        threshold_signal: Minimum signal level to trigger adjustment

    Returns:
        True if adjustment recommended
    """
    signal_order = [
        PerformanceSignal.MAINTAIN,
        PerformanceSignal.INCREASE_LOAD,
        PerformanceSignal.REDUCE_VOLUME,
        PerformanceSignal.DELOAD_SUGGESTED,
        PerformanceSignal.OVERREACHING,
    ]

    current_level = signal_order.index(report.overall_signal)
    threshold_level = signal_order.index(threshold_signal)

    return current_level >= threshold_level


# ============================================================================
# Program Feedback Integration (Sprint 6 Enhanced)
# ============================================================================

@dataclass
class MicrocycleAdjustment:
    """Adjustment to apply to next microcycle based on performance."""
    force_deload: bool = False
    reduce_key_session_intensity: bool = False
    add_stimulus_lifts: List[str] = field(default_factory=list)
    replace_z2_with_tempo: bool = False
    add_hiit_intervals: int = 0
    hold_volume_constant: bool = False
    prioritize_lift: Optional[str] = None
    explanation: str = ""


def compute_microcycle_adjustment(
    report: PerformanceReport,
    priority: str = "balanced",
    microcycles_since_stimulus_change: int = 0
) -> MicrocycleAdjustment:
    """
    Compute adjustments for next microcycle based on performance report.

    Rules:
    A) If overreaching_suspected:
       - force deload microcycle next
       - reduce key sessions intensity by 1 step

    B) If strength priority and lift l stagnating for >=2 microcycles:
       - increase stimulus: add +1 backoff set on that lift's key day
       - OR +2.5% top-set target (choose deterministically)

    C) If endurance priority and TP_proxy stagnating:
       - replace one Z2 with tempo
       - OR add 1 interval set within HIIT cap

    D) If progress:
       - keep planned progression (no extra)

    E) If regression but not overreaching:
       - hold volume constant next week (no planned increase)

    F) If specific lift regressing while others progress:
       - allocate more "quality" to that lift

    Args:
        report: Performance report
        priority: Program priority ("strength", "endurance", "balanced")
        microcycles_since_stimulus_change: Counter for deterministic choices

    Returns:
        MicrocycleAdjustment
    """
    adjustment = MicrocycleAdjustment()

    # A) Overreaching: force deload and reduce intensity
    if report.overall_signal == PerformanceSignal.OVERREACHING:
        adjustment.force_deload = True
        adjustment.reduce_key_session_intensity = True
        adjustment.explanation = "Overreaching detected: forcing deload and reducing key session intensity"
        return adjustment

    # Check for stagnating lifts
    stagnating_lifts = [
        lift for lift, trend in report.lift_trends.items()
        if trend.e1rm_trend == TrendDirection.STAGNANT
    ]

    regressing_lifts = [
        lift for lift, trend in report.lift_trends.items()
        if trend.e1rm_trend == TrendDirection.REGRESSING
    ]

    improving_lifts = [
        lift for lift, trend in report.lift_trends.items()
        if trend.e1rm_trend == TrendDirection.IMPROVING
    ]

    # B) Strength priority with stagnation
    if priority == "strength" and stagnating_lifts and microcycles_since_stimulus_change >= 2:
        # Choose deterministically based on counter
        for lift in stagnating_lifts[:1]:  # Take first stagnating lift
            if microcycles_since_stimulus_change % 2 == 0:
                adjustment.add_stimulus_lifts.append(lift)
                adjustment.explanation = f"Strength stagnation: adding +1 backoff set for {lift}"
            else:
                adjustment.add_stimulus_lifts.append(lift)
                adjustment.explanation = f"Strength stagnation: increasing top-set target +2.5% for {lift}"

    # C) Endurance priority with stagnation
    if priority == "endurance":
        stagnating_endurance = any(
            trend.power_trend == TrendDirection.STAGNANT or trend.power_trend == TrendDirection.REGRESSING
            for trend in report.endurance_trends.values()
        )
        if stagnating_endurance and microcycles_since_stimulus_change >= 2:
            if microcycles_since_stimulus_change % 2 == 0:
                adjustment.replace_z2_with_tempo = True
                adjustment.explanation = "Endurance stagnation: replacing Z2 with tempo"
            else:
                adjustment.add_hiit_intervals = 1
                adjustment.explanation = "Endurance stagnation: adding 1 HIIT interval set"

    # D) Progress: no changes needed
    if report.overall_signal == PerformanceSignal.INCREASE_LOAD:
        adjustment.explanation = "Progress detected: maintaining planned progression"
        return adjustment

    # E) Regression but not overreaching: hold volume
    if report.overall_signal == PerformanceSignal.DELOAD_SUGGESTED:
        adjustment.hold_volume_constant = True
        adjustment.explanation = "Regression detected: holding volume constant"
        return adjustment

    # F) Specific lift regressing while others progress
    for lift in regressing_lifts:
        if lift not in improving_lifts and len(improving_lifts) >= 1:
            adjustment.prioritize_lift = lift
            adjustment.explanation = f"{lift} regressing while others progress: prioritizing quality"
            break

    if not adjustment.explanation:
        adjustment.explanation = report.signal_reason

    return adjustment


def should_force_deload(
    report: PerformanceReport,
    consecutive_regressing_microcycles: int = 0
) -> Tuple[bool, str]:
    """
    Determine if deload should be forced based on performance.

    Args:
        report: Performance report
        consecutive_regressing_microcycles: Number of consecutive regressing microcycles

    Returns:
        (should_deload, reason)
    """
    # Immediate deload for overreaching
    if report.overall_signal == PerformanceSignal.OVERREACHING:
        return True, f"Overreaching: {report.signal_reason}"

    # Deload if suggested
    if report.suggest_deload:
        return True, report.signal_reason

    # Force deload after 2 consecutive regressing microcycles
    if consecutive_regressing_microcycles >= 2:
        return True, f"Two consecutive regressing microcycles ({consecutive_regressing_microcycles})"

    return False, ""


def get_lift_priority_ranking(
    report: PerformanceReport
) -> List[Tuple[str, float]]:
    """
    Rank lifts by performance priority (regressing first, then stagnating, then improving).

    Args:
        report: Performance report

    Returns:
        List of (lift, priority_score) tuples, sorted by priority
    """
    rankings = []

    for lift, trend in report.lift_trends.items():
        if trend.e1rm_trend == TrendDirection.REGRESSING:
            score = 3.0  # Highest priority
        elif trend.e1rm_trend == TrendDirection.STAGNANT:
            score = 2.0  # Medium priority
        elif trend.e1rm_trend == TrendDirection.IMPROVING:
            score = 1.0  # Lower priority
        else:
            score = 0.0

        rankings.append((lift, score))

    # Sort by score descending
    rankings.sort(key=lambda x: x[1], reverse=True)
    return rankings
