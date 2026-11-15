"""Regression checks for the review of the returned strength package."""
from datetime import date

import pytest
from pydantic import ValidationError
from app.science import concurrent as cm
from app.science.concurrent_service import _local_days, _moment, _wall, _prepare, plan_week
from app.science.contract import EngineRequest, PlanRequest, SessionIn, SetIn
from app.science.service import _endurance


def test_equivalent_offsets_are_the_same_instant_and_naive_time_is_unknown():
    base = dict(id='s', date='2026-11-15', type='kracht')
    a = SessionIn(**base, startTime='2026-11-15T18:00:00+01:00')
    b = SessionIn(**base, startTime='2026-11-15T17:00:00Z')
    assert _wall(a) == _wall(b)
    naive = SessionIn(**base, startTime='2026-11-15T18:00:00')
    assert _wall(naive, 'Europe/Brussels') == (_local_days(date(2026, 11, 15), 12, 'Europe/Brussels'), False)


def test_calendar_slots_use_the_local_zone_across_daylight_saving():
    zone = 'Europe/Brussels'
    before = _local_days(date(2026, 3, 28), 8, zone)
    after = _local_days(date(2026, 3, 29), 8, zone)
    assert (after - before) * 24 == pytest.approx(23)
    assert _moment(after, zone) == '2026-03-29T08:00+02:00'
    with pytest.raises(ValueError, match='does not exist'):
        _local_days(date(2026, 3, 29), 2.5, zone)
    with pytest.raises(ValidationError):
        EngineRequest(asOfDate='2026-03-01', timeZone='not/a/zone')
    plan = plan_week(PlanRequest(asOfDate='2026-03-28', timeZone=zone,
        availableDates=['2026-03-29'], slotHours=[8],
        planSessions=[dict(label='lift', kind='strength_lower', workSets=5)]))
    assert plan['options'][0]['sessions'][0]['start'] == '2026-03-29T08:00+02:00'


def test_full_history_hyperparameter_selection_is_not_used_in_prediction_test(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('full-history time-constant selection leaks future outcomes')
    monkeypatch.setattr(cm, 'select_time_constants', forbidden)
    request = EngineRequest(asOfDate='2026-11-15')
    _, constants, info, _, _ = _prepare(request, [], _endurance(request))
    assert constants == cm.TimeConstants()
    assert info['reason'] == 'fixed_before_walk_forward_validation'


def test_cp_fitted_to_the_same_efforts_does_not_calibrate_interaction():
    request = EngineRequest(asOfDate='2026-11-15', endurance=dict(maximalEfforts=[
        dict(date=f'2026-11-{i+1:02}', durationSeconds=t, powerW=250+18000/t)
        for i, t in enumerate([120, 180, 300, 420, 600, 900])]))
    endurance = _endurance(request)
    assert endurance['cp_model']['status'] == 'ok'
    _, _, _, results, data = _prepare(request, [], endurance)
    assert data['endurance_reference'] == 'cp_fit_on_the_same_efforts_circular'
    assert results['endurance']['status'] == 'prior_only'
    assert results['endurance']['observations'] == 0


def test_velocity_cannot_exist_for_unperformed_repetitions():
    with pytest.raises(ValidationError):
        SetIn(setNum=1, weight=80, completedReps=0, velocities=[0.5])
    assert SetIn(setNum=1, weight=80, completedReps=3, velocities=[]).velocities == []


def test_engine_calculation_slots_are_bounded_and_released_after_errors():
    from fastapi import HTTPException
    from app.api_v3 import _calculate, _calculation_slots
    assert _calculation_slots.acquire(blocking=False)
    assert _calculation_slots.acquire(blocking=False)
    try:
        with pytest.raises(HTTPException) as error:
            _calculate(lambda _: None, None)
        assert error.value.status_code == 429
    finally:
        _calculation_slots.release()
        _calculation_slots.release()
    def fail(_):
        raise ValueError('failed calculation')
    with pytest.raises(ValueError):
        _calculate(fail, None)
    assert _calculate(lambda _: 'ready', None) == 'ready'


def test_future_maximal_efforts_do_not_enter_the_as_of_fit():
    request = EngineRequest(asOfDate='2026-11-01', endurance=dict(maximalEfforts=[
        dict(date=f'2026-11-{i+2:02}', durationSeconds=t, powerW=250+18000/t)
        for i, t in enumerate([180, 360, 720])]))
    assert _endurance(request)['cp_model']['efforts_used'] == 0
