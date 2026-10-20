from datetime import date, datetime, timedelta

import pytest

from app.domain.day_engine import (
    DailyImpulses,
    DayEngineParams,
    DayState,
    EnduranceImpulses,
    PerLiftState,
    StrengthImpulses,
)
from app.domain.day_transition import (
    apply_day_transition,
    canonical_day_params,
    interference_timing_factor,
)


def empty_strength():
    return StrengthImpulses(
        per_lift={}, u_sys=0.0, u_legs=0.0, u_met=0.0,
        u_legs_high_intensity=0.0, sets=[]
    )


def test_power_clean_is_normalized_across_day_parameters():
    params = canonical_day_params(DayEngineParams())
    assert params.omega["power_clean"] == params.omega["clean"]
    assert params.legs_weights["power_clean"] == params.legs_weights["clean"]
    assert params.tau_Dl["power_clean"] == params.tau_Dl["clean"]
    assert params.k_ES_l["power_clean"] == params.k_ES_l["clean"]


def test_interference_timing_uses_actual_spacing():
    hiit = datetime(2026, 1, 1, 8, 0)
    close_strength = hiit + timedelta(hours=1)
    distant_strength = hiit + timedelta(hours=24)
    close = interference_timing_factor([close_strength], [hiit])
    distant = interference_timing_factor([distant_strength], [hiit])
    assert close > distant
    assert close <= 1.0
    assert distant == pytest.approx(2.718281828 ** -1, rel=1e-3)


def test_capacity_is_bounded_by_lift_specific_ceiling():
    current = DayState(
        date=date(2026, 1, 1),
        per_lift={"press": PerLiftState(D_l=0.0, F_l=100.0, C_l=159.9)},
    )
    impulses = DailyImpulses(
        strength=empty_strength(),
        endurance=EnduranceImpulses(
            u_E_Z2=0.0, u_E_HIIT=0.0, u_E_total=0.0,
            mode="cycling", has_HIIT=False, has_Z2=False,
        ),
        date=date(2026, 1, 2),
    )
    updated = apply_day_transition(
        current, impulses, DayEngineParams(), capacity_ceilings={"press": 160.0}
    )
    assert updated.per_lift["press"].C_l <= 160.0
    assert updated.per_lift["press"].C_l >= DayEngineParams().C_min


def test_timing_factor_replaces_default_interference():
    current = DayState(
        date=date(2026, 1, 1),
        per_lift={"squat": PerLiftState(D_l=0.0, F_l=1.0, C_l=100.0)},
    )
    impulses = DailyImpulses(
        strength=empty_strength(),
        endurance=EnduranceImpulses(
            u_E_Z2=0.0, u_E_HIIT=60.0, u_E_total=60.0,
            mode="running", has_HIIT=True, has_Z2=False,
        ),
        date=date(2026, 1, 2),
    )
    full = apply_day_transition(current, impulses, DayEngineParams(), timing_factor=1.0)
    reduced = apply_day_transition(current, impulses, DayEngineParams(), timing_factor=0.25)
    assert reduced.per_lift["squat"].D_l < full.per_lift["squat"].D_l
    assert reduced.D_sys < full.D_sys
