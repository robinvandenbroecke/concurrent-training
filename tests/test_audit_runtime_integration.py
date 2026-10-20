from datetime import datetime
import pytest
from app import schemas, models
from app.services import SessionService
from app.types import LiftType


def test_count_only_workout_keeps_every_rep(db_session, sample_athlete):
    data=schemas.StrengthWorkoutCreate(
        athlete_id=sample_athlete.id,start_time=datetime(2026,1,2,18),
        exercises=[schemas.StrengthExerciseData(lift=LiftType.SQUAT,sets=[schemas.SetData(
            weight=60,target_reps=5,set_end_rpe=8,
            reps=[schemas.RepData(weight=60,rep_num=i+1) for i in range(5)]
        )])])
    session=SessionService(db_session).ingest_strength_workout(data)[0]
    assert session.tonnage == 300
    assert session.raw_data['sets'][0]['velocities'] == [None]*5
    assert len(session.rep_level_log) == 5
    assert all(row['observation_available'] is False for row in session.rep_level_log)
    assert session.raw_data['final_A_sys'] < 1


def test_missing_readiness_is_null(client,sample_athlete):
    response=client.get('/readiness/today',params={'athlete_id':sample_athlete.id})
    assert response.status_code == 200
    assert response.json()['overall'] is None
    assert response.json()['assessment_status'] == 'insufficient_data'


def test_saved_threshold_used_on_ingest(client,sample_athlete):
    response=client.put(f'/endurance/profile/{sample_athlete.id}/cycling',json={'threshold_power_w':200})
    assert response.status_code == 200
    response=client.post('/sessions/endurance',json={
        'athlete_id':sample_athlete.id,'sport':'cycling','start_time':'2026-01-01T12:00:00',
        'duration_minutes':60,'intensity_type':'z2','average_power_w':200})
    assert response.status_code == 200
    assert response.json()['u_E_HIIT'] == 60
    assert response.json()['u_E_Z2'] == 0


def test_no_velocity_does_not_trigger_load_increase(client,sample_athlete):
    response=client.post('/strength/autoregulate',json={
        'athlete_id':sample_athlete.id,'lift':'squat','current_weight':60,'current_reps_done':2,'planned_reps':5})
    assert response.status_code == 200
    assert response.json()['load_change'] == 0
    assert response.json()['predicted_velocity'] is None


def test_empty_performed_set_is_rejected(client,sample_athlete):
    response=client.post('/sessions/strength',json={
        'athlete_id':sample_athlete.id,'lift':'squat','start_time':'2026-01-01T12:00:00',
        'sets':[{'weight':60,'target_reps':5,'reps':[]}]})
    assert response.status_code == 400


def test_missing_velocity_endpoints_do_not_become_measured_vl():
    from app.services.strength_impulse_features import normalize_velocities, compute_set_vl
    values = normalize_velocities([None, .5, .4, None])
    assert values == [None, .5, .4, None]
    assert compute_set_vl(values) is None
    assert normalize_velocities([.5, float('nan')]) is None


def test_missing_early_velocities_do_not_use_late_fatigued_reps_as_freshness():
    from app.services.strength_impulse_features import compute_velocity_factor_from_raw_velocities
    assert compute_velocity_factor_from_raw_velocities([None, None, .2, .1], 60, 'squat') is None
