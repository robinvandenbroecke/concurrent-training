"""Two-parameter critical power model and W' balance.

Fit: linear work-time form  W(t) = CP * t + W'  on user-declared MAXIMAL
efforts. Mean-maximal power mined from ordinary training is not used, because
sub-maximal efforts bias CP downward and W' unpredictably.

Applicability: maximal efforts of 2-20 min. Shorter efforts break the
hyperbola's assumptions (Chorley & Lamb 2020, doi:10.3390/sports8090123).
When every effort is shorter than about 10-12 min, CP is overestimated and W'
underestimated whatever the model; a set that includes efforts of 12-20 min
agrees with the criterion fit (Mattioni Maturana et al. 2018, J Sci Med
Sport). Such a set is therefore accepted but carries a warning.
Three to five efforts on separate days are the conventional minimum
(Muniz-Pumares et al. 2019, J Strength Cond Res 33:584-596). With exactly three
efforts the fit has one degree of freedom, so its standard errors are weak
evidence; that is reported as a warning too.
W'bal: differential form of Skiba et al. (2015); reconstitution kinetics vary
between athletes and with recovery intensity and repeated bouts, so the trace
is an approximation for planning, not a measurement
(Skiba & Clarke 2021, doi:10.1123/ijspp.2021-0205).
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Sequence

MIN_EFFORTS = 3
MIN_DURATION_S = 120.0
MAX_DURATION_S = 1200.0
MAX_SEE_CP_PCT = 5.0
MAX_SEE_WPRIME_PCT = 10.0
LONG_EFFORT_S = 600.0             # at least one effort this long, else CP is biased upward
EFFORT_SPAN_DAYS = 42             # pragmatic: older efforts describe another fitness state


@dataclass(frozen=True)
class CPFit:
    status: str                       # ok | insufficient_data | rejected
    reasons: tuple
    warnings: tuple = ()
    cp_w: Optional[float] = None
    w_prime_j: Optional[float] = None
    se_cp_w: Optional[float] = None
    se_w_prime_j: Optional[float] = None
    r2: Optional[float] = None
    n_efforts: int = 0


def fit_critical_power(efforts: Sequence[tuple], span_days: Optional[int] = None) -> CPFit:
    """efforts: (duration_s, mean_power_w) of maximal efforts.

    Two efforts of the same duration cannot both be maximal: only the best one
    per duration (rounded to the second) enters the fit. ``span_days`` is the
    number of days between the oldest and newest effort when all are dated.
    """
    clean = [(float(t), float(p)) for t, p in efforts
             if math.isfinite(t) and math.isfinite(p) and t > 0 and p > 0]
    in_range = [(t, p) for t, p in clean if MIN_DURATION_S <= t <= MAX_DURATION_S]
    best: dict = {}
    for t, p in in_range:
        key = round(t)
        if key not in best or p > best[key][1]:
            best[key] = (t, p)
    used = [best[key] for key in sorted(best)]
    n = len(used)
    if n < MIN_EFFORTS:
        return CPFit("insufficient_data", ("need_three_maximal_efforts_2_to_20_min",), n_efforts=n)
    times = [t for t, _ in used]
    work = [t * p for t, p in used]
    mt, mw = sum(times) / n, sum(work) / n
    sxx = sum((t - mt) ** 2 for t in times)
    cp = sum((t - mt) * (w - mw) for t, w in zip(times, work)) / sxx
    wp = mw - cp * mt
    ss_res = sum((w - (wp + cp * t)) ** 2 for t, w in zip(times, work))
    ss_tot = sum((w - mw) ** 2 for w in work)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    if n > 2:
        s2 = ss_res / (n - 2)
        se_cp = math.sqrt(s2 / sxx)
        se_wp = math.sqrt(s2 * (1 / n + mt ** 2 / sxx))
    else:  # pragma: no cover - guarded above
        se_cp = se_wp = float("nan")
    common = dict(cp_w=cp, w_prime_j=wp, se_cp_w=se_cp, se_w_prime_j=se_wp, r2=r2, n_efforts=n)
    if cp <= 0 or wp <= 0:
        return CPFit("rejected", ("non_physical_parameters",), **common)
    warnings = []
    if len(clean) != len(in_range):
        warnings.append("efforts_outside_2_to_20_min_ignored")
    if len(in_range) != n:
        warnings.append("repeated_durations_best_effort_used")
    if max(times) < LONG_EFFORT_S:
        warnings.append("no_effort_of_10_min_or_longer_cp_may_be_overestimated")
    if span_days is None:
        warnings.append("effort_dates_unknown")
    elif span_days > EFFORT_SPAN_DAYS:
        warnings.append("efforts_span_more_than_6_weeks")
    if max(times) / min(times) < 2.5:
        warnings.append("durations_too_similar")
    if n == MIN_EFFORTS:
        warnings.append("only_three_efforts_one_degree_of_freedom")
    reasons = []
    if 100 * se_cp / cp > MAX_SEE_CP_PCT:
        reasons.append("cp_standard_error_above_5_percent")
    if 100 * se_wp / wp > MAX_SEE_WPRIME_PCT:
        reasons.append("w_prime_standard_error_above_10_percent")
    # Efforts are not truly maximal/consistent if a longer effort has higher power.
    ordered = sorted(used)
    if any(b[1] >= a[1] for a, b in zip(ordered, ordered[1:])):
        reasons.append("power_not_decreasing_with_duration")
    if reasons:
        return CPFit("rejected", tuple(reasons), tuple(warnings), **common)
    return CPFit("ok", (), tuple(warnings), **common)


def w_prime_balance(power_w: Sequence[Optional[float]], cp_w: float, w_prime_j: float,
                    dt_s: float = 1.0) -> list:
    """Differential W'bal (Skiba 2015), exact per constant-power step.

    Above CP: linear depletion. Below CP: exponential return toward W' with
    rate (CP - P) / W'. ``None`` samples (dropouts) keep the balance unchanged
    and are returned as None: an unknown power is not assumed to be zero.
    The balance may become negative; that signals that the parameters or the
    model do not describe the effort, it is not clipped away.
    """
    if not (cp_w > 0 and w_prime_j > 0 and dt_s > 0):
        raise ValueError("CP, W' and time step must be positive")
    balance = w_prime_j
    out = []
    for p in power_w:
        if p is None:
            out.append(None)
            continue
        if not math.isfinite(p) or p < 0:
            raise ValueError("Power must be finite and non-negative")
        if p > cp_w:
            balance -= (p - cp_w) * dt_s
        else:
            balance = w_prime_j - (w_prime_j - balance) * math.exp(-(cp_w - p) * dt_s / w_prime_j)
        out.append(balance)
    return out
