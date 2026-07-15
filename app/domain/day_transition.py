"""Canonical hardening around the pure day engine.

The underlying day engine remains backwards compatible. Production transitions
use this module to normalize lift identifiers, apply time-aware interference,
and replace the universal capacity ceiling with configurable per-lift ceilings.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import math
from typing import Callable, Dict, Iterable, Optional, Sequence

from app.domain.day_engine import (
    DailyImpulses,
    DayEngineParams,
    DayState,
    compute_interference,
    update_day_state,
)


DEFAULT_CAPACITY_CEILINGS: Dict[str, float] = {
    "squat": 320.0,
    "bench": 220.0,
    "deadlift": 360.0,
    "press": 160.0,
    "clean": 240.0,
    "power_clean": 240.0,
}


def canonical_day_params(params: DayEngineParams) -> DayEngineParams:
    """Return params with canonical `power_clean` entries populated.

    Existing `clean` values remain valid aliases, preserving older artifacts.
    """
    omega = dict(params.omega)
    omega.setdefault("power_clean", omega.get("clean", 1.0))
    legs_weights = dict(params.legs_weights)
    legs_weights.setdefault("power_clean", legs_weights.get("clean", 0.8))
    tau_dl = dict(params.tau_Dl)
    tau_dl.setdefault("power_clean", tau_dl.get("clean", 3.0))
    beta_l = dict(params.beta_l)
    beta_l.setdefault("power_clean", beta_l.get("clean", 0.25))
    k_es = dict(params.k_ES_l)
    k_es.setdefault("power_clean", k_es.get("clean", 0.00028))
    return replace(
        params,
        omega=omega,
        legs_weights=legs_weights,
        tau_Dl=tau_dl,
        beta_l=beta_l,
        k_ES_l=k_es,
    )


def interference_timing_factor(
    strength_times: Sequence[datetime],
    hiit_times: Sequence[datetime],
) -> float:
    """Estimate HIIT→strength interference from actual session spacing.

    A preceding HIIT session has maximal effect when close to strength and
    decays exponentially over 24 hours. HIIT performed after all strength work
    receives a conservative 0.5 carry-over factor for next-day readiness.
    """
    if not hiit_times:
        return 1.0
    if not strength_times:
        return 0.5
    preceding_gaps = [
        (strength - hiit).total_seconds() / 3600.0
        for strength in strength_times
        for hiit in hiit_times
        if strength >= hiit
    ]
    if not preceding_gaps:
        return 0.5
    nearest_hours = min(preceding_gaps)
    return max(0.10, min(1.0, math.exp(-nearest_hours / 24.0)))


def _capacity_ceiling(
    lift: str,
    current_capacity: float,
    params: DayEngineParams,
    ceilings: Optional[Dict[str, float]],
) -> float:
    configured = (ceilings or {}).get(lift)
    if configured is None:
        configured = DEFAULT_CAPACITY_CEILINGS.get(lift, params.C_max)
    # Never invalidate an existing real-world anchor that is already above a
    # population default; retain at least 5% headroom.
    return max(float(configured), current_capacity * 1.05, params.C_min + 1.0)


def apply_day_transition(
    current: DayState,
    impulses: DailyImpulses,
    params: DayEngineParams,
    *,
    timing_factor: float = 1.0,
    capacity_ceilings: Optional[Dict[str, float]] = None,
    core_update: Callable[[DayState, DailyImpulses, DayEngineParams], DayState] = update_day_state,
) -> DayState:
    """Apply one daily transition with canonical postconditions."""
    normalized = canonical_day_params(params)
    updated = core_update(current, impulses, normalized)

    # The core engine applies factor 1.0 for compatibility. Replace that
    # component with the actual timing-adjusted interference contribution.
    default_lift, default_sys = compute_interference(impulses.endurance, normalized, timing_factor=1.0)
    timed_lift, timed_sys = compute_interference(
        impulses.endurance,
        normalized,
        timing_factor=max(0.0, min(1.0, timing_factor)),
    )
    updated.D_sys = max(0.0, updated.D_sys - default_sys + timed_sys)

    for lift, lift_state in updated.per_lift.items():
        lift_state.D_l = max(
            0.0,
            lift_state.D_l - default_lift.get(lift, 0.0) + timed_lift.get(lift, 0.0),
        )

        prior = current.get_lift(lift)
        ceiling = _capacity_ceiling(lift, prior.C_l, normalized, capacity_ceilings)
        ratio = max(0.0, min(1.0, prior.C_l / ceiling))
        saturation = (1.0 - ratio) ** normalized.capacity_saturation_alpha
        capacity = (
            prior.C_l
            + normalized.g_l * lift_state.F_l * saturation
            - normalized.h_l * lift_state.D_l
            - normalized.lambda_l
        )
        lift_state.C_l = max(normalized.C_min, min(ceiling, capacity))

    return updated
