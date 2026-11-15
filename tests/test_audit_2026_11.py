"""Regression tests for the November 2026 audit (see AUDIT_REPORT.md).

The legacy three-compartment model under app.domain stays research code. These
tests pin corrected programming errors and document, as executable facts,
known modelling defects that were deliberately NOT tuned away.
"""
from datetime import date

import pytest

from app.domain.day_engine import (DayEngineParams, SetImpulse, compute_strength_impulses, create_initial_state,
                                   decay_day_state_to_date, simulate_day_transition)
from app.domain.rep_engine import LiftVelocityProfile, SessionInput, SetInput, simulate_strength_session


def _session(sets, initial):
    profile = LiftVelocityProfile("squat", 1.2, 0.006)
    return simulate_strength_session(SessionInput(sets=sets, profiles={"squat": profile}, init_A_local=initial,
                                                  init_A_sys=1.0, init_M=0.0, R_mito=0.0, e1rm={"squat": 150}))


def test_lift_without_initial_state_starts_unfatigued_not_at_the_clamping_floor():
    """LEG-01: the default used to be 2 % availability."""
    sets = [SetInput("squat", 100, [0.60, 0.58, 0.56])]
    unknown, fresh = _session(sets, {}), _session(sets, {"squat": 1.0})
    assert unknown.final_A_local["squat"] == pytest.approx(fresh.final_A_local["squat"])
    assert unknown.sets[0].reps[0].v_pred_next == pytest.approx(fresh.sets[0].reps[0].v_pred_next)
    assert unknown.sets[0].reps[0].v_pred_next > 0.4


def test_known_defect_first_set_counts_more_than_the_same_set_after_a_day_of_rest():
    """LEG-02 (open): the density heuristic is discontinuous at 'no rest recorded'."""
    first = _session([SetInput("squat", 100, [0.6] * 5)], {"squat": 1.0})
    rested = _session([SetInput("squat", 100, [0.6] * 5, rest_before_sec=24 * 3600)], {"squat": 1.0})
    assert first.final_A_sys < rested.final_A_sys          # documents the defect; remove when the model is replaced


def test_known_defect_capacity_integrates_fatigue_and_never_gets_it_back():
    """LEG-03 (open): fatigue is subtracted from capacity cumulatively, unlike a fitness-fatigue model."""
    params = DayEngineParams()
    state = create_initial_state(date(2026, 1, 1), ["squat"], 150.0)
    state.per_lift["squat"].F_l = 0.0
    hard = [SetImpulse("squat", 500.0, 100 / 150, 1.0, 0.3, 5, 0.67)] * 10
    after, _, _ = simulate_day_transition(state, hard, [], params)
    rested = decay_day_state_to_date(after, date(2026, 3, 15), params)
    assert after.per_lift["squat"].C_l < 150.0
    assert rested.per_lift["squat"].D_l < 1e-6
    assert rested.per_lift["squat"].C_l == pytest.approx(after.per_lift["squat"].C_l)


def test_known_defect_impulse_scales_with_absolute_load_at_equal_relative_effort():
    """LEG-04 (open): twice as strong means twice the 'fatigue' for the same relative session."""
    params = DayEngineParams()
    def impulse(capacity):
        sets = [SetImpulse("squat", 0.8 * capacity * 5, 0.8, 1.0, 0.2, 5, 0.8)] * 3
        return compute_strength_impulses(sets, params).per_lift["squat"]
    assert impulse(200) == pytest.approx(2 * impulse(100))


def test_api_key_with_non_ascii_characters_is_refused_without_a_server_error(monkeypatch):
    """SEC-02: hmac.compare_digest raised TypeError (HTTP 500) on a non-ASCII header value."""
    import asyncio

    from fastapi import HTTPException

    from app.config import settings
    from app.main import verify_admin_api_key, verify_api_key
    monkeypatch.setattr(settings, "require_api_key", True)
    for check in (verify_api_key, verify_admin_api_key):
        with pytest.raises(HTTPException) as refused:
            asyncio.run(check("sl\u00f6tel"))
        assert refused.value.status_code == 403
