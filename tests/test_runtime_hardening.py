from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.config import settings
from app.domain.endurance_engine import compute_endurance_load
from app.integrations.secure_strava import StravaService
from app.schemas import RepData, SetData, StrengthExerciseData, StrengthWorkoutCreate
from app.services import AutoregulationService, DayUpdateService, ReadinessService, SessionService
import app.services.engine_orchestrator as engine_module
from app.types import LiftType


def test_runtime_services_do_not_export_legacy_readiness_path():
    assert ReadinessService.__module__.endswith("runtime_services")
    assert DayUpdateService.__module__.endswith("runtime_services")
    assert AutoregulationService.__module__.endswith("runtime_services")
    assert SessionService.__module__.endswith("session_service")


def test_default_day_target_is_quality_set_target():
    assert settings.day_level_strength_target_mode == "heaviest_quality_set_perf_y"


def test_cycling_power_with_threshold_is_primary_signal():
    load = compute_endurance_load(
        sport="cycling",
        duration_minutes=60,
        declared_intensity="hiit",
        average_power_w=180,
        normalized_power_w=190,
        threshold_power_w=250,
    )
    assert load.signal_source == "power"
    assert load.intensity_type == "z2"
    assert load.intensity_factor == pytest.approx(0.76)
    assert load.u_z2 > 0
    assert load.u_hiit == 0


def test_power_without_threshold_is_explicit_fallback():
    load = compute_endurance_load(
        sport="cycling",
        duration_minutes=45,
        declared_intensity="mixed",
        average_power_w=210,
    )
    assert load.signal_source == "power_unscaled"
    assert load.u_z2 == pytest.approx(13.5)
    assert load.u_hiit == pytest.approx(31.5)


def _two_lift_workout(athlete_id: int) -> StrengthWorkoutCreate:
    return StrengthWorkoutCreate(
        athlete_id=athlete_id,
        start_time=datetime(2026, 1, 1, 18, 0),
        exercises=[
            StrengthExerciseData(
                lift=LiftType.SQUAT,
                sets=[SetData(
                    weight=100,
                    target_reps=3,
                    set_end_rpe=8.0,
                    reps=[
                        RepData(weight=100, velocity=0.50, rep_num=1),
                        RepData(weight=100, velocity=0.46, rep_num=2),
                    ],
                )],
            ),
            StrengthExerciseData(
                lift=LiftType.BENCH,
                sets=[SetData(
                    weight=80,
                    target_reps=3,
                    set_end_rpe=8.0,
                    reps=[
                        RepData(weight=80, velocity=0.45, rep_num=1),
                        RepData(weight=80, velocity=0.41, rep_num=2),
                    ],
                )],
            ),
        ],
    )


def test_multi_lift_workout_schema_preserves_order_and_rpe():
    workout = _two_lift_workout(1)
    assert [item.lift for item in workout.exercises] == [LiftType.SQUAT, LiftType.BENCH]
    assert workout.exercises[0].sets[0].set_end_rpe == 8.0


def test_multi_lift_workout_uses_one_rep_engine_run(db_session, sample_athlete):
    workout = _two_lift_workout(sample_athlete.id)
    actual = engine_module.simulate_strength_session
    with patch("app.services.engine_orchestrator.simulate_strength_session", wraps=actual) as mocked:
        sessions = SessionService(db_session).ingest_strength_workout(workout)
    assert mocked.call_count == 1
    assert [item.lift for item in sessions] == [LiftType.SQUAT, LiftType.BENCH]
    assert all((item.raw_data or {}).get("source") == "multi_lift_workout" for item in sessions)
    assert sessions[1].raw_data["final_A_sys"] <= sessions[0].raw_data["final_A_sys"]


def test_strava_oauth_state_is_signed_and_expires():
    service = StravaService(db=None)
    state = service._generate_state_token(42)
    assert service.verify_state_token(state) == 42
    athlete, timestamp, signature = state.split(":", 2)
    tampered = f"43:{timestamp}:{signature}"
    with pytest.raises(Exception):
        service.verify_state_token(tampered)
