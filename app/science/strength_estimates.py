"""Repetition-based 1RM ESTIMATE with an explicit uncertainty band.

This is an estimate from load, repetitions and self-reported proximity to
failure. It is never called a measured 1RM.

Equation: Brzycki (1993), 1RM = load * 36 / (37 - repetitions to failure).
It returns the load itself for a true single and is continuous above it. The
Epley form used before (load * (1 + r/30), special-cased to the load at r = 1)
jumped by 3-5 % between a single at RPE 10 and a single at RPE 9.5. Both
equations were derived on small samples and lose accuracy above about ten
repetitions, hence the cap below; neither is validated for sets stopped short
of failure, where the repetitions in reserve are a self-report.

People mis-judge repetitions in reserve by roughly one repetition on average
(they have more left than they think), with wide heterogeneity (Halperin et al.
2022, doi:10.1007/s40279-021-01559-x). The band propagates that error only. It
does not contain the error of the equation and is not a confidence interval.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

MAX_REPS_TO_FAILURE = 12
MIN_RPE = 7.0
METHOD = "brzycki_with_reported_rir"


@dataclass(frozen=True)
class E1RM:
    status: str
    reason: Optional[str] = None
    value_kg: Optional[float] = None
    low_kg: Optional[float] = None
    high_kg: Optional[float] = None
    reps_to_failure: Optional[float] = None


def _brzycki(load: float, reps_to_failure: float) -> float:
    return load * 36.0 / (37.0 - max(1.0, reps_to_failure))


def estimate_e1rm(load_kg: float, reps: int, rpe: Optional[float]) -> E1RM:
    if load_kg <= 0 or reps < 1:
        return E1RM("not_applicable", "no_external_load_or_reps")
    if rpe is None:
        return E1RM("insufficient_data", "rpe_missing")
    if rpe < MIN_RPE:
        return E1RM("insufficient_data", "set_too_far_from_failure")
    rir = max(0.0, 10.0 - rpe)
    rtf = reps + rir
    if rtf > MAX_REPS_TO_FAILURE:
        return E1RM("insufficient_data", "too_many_repetitions")
    return E1RM("ok", None, _brzycki(load_kg, rtf), _brzycki(load_kg, max(float(reps), rtf - 1.0)),
                _brzycki(load_kg, rtf + 2.0), rtf)
