"""Individual load-velocity (L-V) profile for one exercise, one device and one
velocity metric.

Scope and evidence
------------------
* The inverse linear L-V relation is used descriptively inside the measured
  load range only. Extrapolation to a 1RM is NOT reported as a measurement:
  an individual-participant meta-analysis found a standard error of about 10 %
  and a systematic overestimation of 1RM (Greig et al. 2023,
  doi:10.1007/s40279-023-01854-9).
* Mean concentric, mean propulsive and peak velocity are different
  measurements and are never pooled (Weakley et al. 2021,
  doi:10.1007/s40279-020-01382-w).
* A deviation from the profile is a measured performance difference under the
  stated protocol. It is not a measurement of fatigue, readiness or reserve.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Sequence

MIN_POINTS = 4
MIN_DISTINCT_LOADS = 3
MIN_RELATIVE_RANGE = 0.25   # (max-min)/max of the calibration loads
MIN_R2 = 0.90

# Two-sided 95 % Student-t quantiles by residual degrees of freedom. A profile
# is fitted on few points, so the normal value 1.96 would call ordinary noise a
# change far more often than 5 % of the time (18 % for one observation at 2
# degrees of freedom; 8 % versus 2 % in the simulation of tests/test_science_engine.py).
_T95 = (12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145,
        2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048,
        2.045, 2.042)


def t_critical_95(degrees_of_freedom: int) -> float:
    if degrees_of_freedom < 1:
        return float("inf")
    if degrees_of_freedom <= len(_T95):
        return _T95[degrees_of_freedom - 1]
    return 2.021 if degrees_of_freedom <= 40 else 2.000 if degrees_of_freedom <= 60 else 1.980 if degrees_of_freedom <= 120 else 1.960


@dataclass(frozen=True)
class LVPoint:
    load_kg: float
    velocity_ms: float
    date: str


@dataclass(frozen=True)
class LVProfile:
    status: str                      # ok | insufficient_data | rejected
    reasons: tuple
    n_points: int = 0
    distinct_loads: int = 0
    load_min_kg: Optional[float] = None
    load_max_kg: Optional[float] = None
    intercept_ms: Optional[float] = None
    slope_ms_per_kg: Optional[float] = None   # negative
    r2: Optional[float] = None
    residual_sd_ms: Optional[float] = None
    mean_load_kg: Optional[float] = None
    sxx: Optional[float] = None

    def in_range(self, load_kg: float) -> bool:
        return self.status == "ok" and self.load_min_kg <= load_kg <= self.load_max_kg

    def expected(self, load_kg: float) -> Optional[float]:
        """Expected velocity; None outside the calibrated range (no extrapolation)."""
        if not self.in_range(load_kg):
            return None
        return self.intercept_ms + self.slope_ms_per_kg * load_kg

    def prediction_sd(self, load_kg: float) -> Optional[float]:
        """Standard deviation of a NEW single observation at this load."""
        if not self.in_range(load_kg):
            return None
        lever = 1.0 + 1.0 / self.n_points + ((load_kg - self.mean_load_kg) ** 2) / self.sxx
        return self.residual_sd_ms * math.sqrt(lever)

    def noise_limit(self) -> Optional[float]:
        """|standardised deviation| below which a new observation is ordinary noise (95 %)."""
        return t_critical_95(self.n_points - 2) if self.status == "ok" else None


def fit_profile(points: Sequence[LVPoint]) -> LVProfile:
    clean = [p for p in points if math.isfinite(p.load_kg) and math.isfinite(p.velocity_ms)
             and p.load_kg > 0 and 0 < p.velocity_ms <= 3.0]
    n = len(clean)
    loads = sorted({round(p.load_kg, 2) for p in clean})
    reasons = []
    if n < MIN_POINTS:
        reasons.append("too_few_points")
    if len(loads) < MIN_DISTINCT_LOADS:
        reasons.append("too_few_distinct_loads")
    if loads and (loads[-1] - loads[0]) / loads[-1] < MIN_RELATIVE_RANGE:
        reasons.append("load_range_too_narrow")
    if reasons:
        return LVProfile("insufficient_data", tuple(reasons), n, len(loads),
                         loads[0] if loads else None, loads[-1] if loads else None)
    mean_w = sum(p.load_kg for p in clean) / n
    mean_v = sum(p.velocity_ms for p in clean) / n
    sxx = sum((p.load_kg - mean_w) ** 2 for p in clean)
    sxy = sum((p.load_kg - mean_w) * (p.velocity_ms - mean_v) for p in clean)
    slope = sxy / sxx
    intercept = mean_v - slope * mean_w
    ss_res = sum((p.velocity_ms - (intercept + slope * p.load_kg)) ** 2 for p in clean)
    ss_tot = sum((p.velocity_ms - mean_v) ** 2 for p in clean)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    sd = math.sqrt(ss_res / (n - 2)) if n > 2 else float("nan")
    common = dict(n_points=n, distinct_loads=len(loads), load_min_kg=loads[0], load_max_kg=loads[-1],
                  intercept_ms=intercept, slope_ms_per_kg=slope, r2=r2, residual_sd_ms=sd,
                  mean_load_kg=mean_w, sxx=sxx)
    if slope >= 0:
        return LVProfile("rejected", ("velocity_does_not_decrease_with_load",), **common)
    if r2 < MIN_R2:
        return LVProfile("rejected", ("poor_linear_fit",), **common)
    return LVProfile("ok", (), **common)


def velocity_loss(velocities: Sequence[Optional[float]]) -> Optional[float]:
    """Within-set velocity loss relative to the fastest measured rep.

    Returns None unless the last rep and at least one earlier rep were
    measured. A missing measurement is never converted into 0 % loss.
    Definition follows the fastest-rep convention used in the velocity-loss
    literature (Jukic et al. 2023, doi:10.1007/s40279-022-01754-4).
    """
    if len(velocities) < 2 or velocities[-1] is None:
        return None
    earlier = [v for v in velocities[:-1] if v is not None]
    if not earlier:
        return None
    fastest = max(earlier + [velocities[-1]])
    if fastest <= 0:
        return None
    return max(0.0, 1.0 - velocities[-1] / fastest)
