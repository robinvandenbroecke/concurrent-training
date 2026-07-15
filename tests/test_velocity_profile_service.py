from datetime import date, datetime

from app import models
from app.services.velocity_profile_service import VelocityProfileService
from app.types import LiftType


def test_velocity_profile_updates_from_multiple_real_loads(db_session, sample_athlete):
    sets = []
    for load, velocity in [(40, 0.80), (40, 0.79), (60, 0.66), (60, 0.65), (80, 0.52), (80, 0.51)]:
        sets.append({"load_kg": load, "reps": 3, "velocities": [velocity, velocity - 0.03]})
    session = models.StrengthSession(
        athlete_id=sample_athlete.id,
        lift=LiftType.SQUAT,
        start_time=datetime(2026, 1, 15, 18, 0),
        content_hash="velocity-profile-test",
        tonnage=1000,
        avg_intensity=0.6,
        raw_data={"sets": sets},
        rep_level_log=[],
    )
    db_session.add(session)
    db_session.commit()

    profile = db_session.query(models.LiftProfile).filter(
        models.LiftProfile.athlete_id == sample_athlete.id,
        models.LiftProfile.lift == LiftType.SQUAT,
    ).one()
    old_a, old_b = profile.a, profile.b
    result = VelocityProfileService(db_session).update_from_recent_sessions(
        sample_athlete.id,
        LiftType.SQUAT,
        reference_date=date(2026, 1, 15),
    )
    db_session.refresh(profile)

    assert result["updated"] is True
    assert result["distinct_loads"] == 3
    assert result["observations"] == 6
    assert profile.a != old_a
    assert profile.b != old_b
    assert profile.b > 0


def test_velocity_profile_does_not_move_on_sparse_data(db_session, sample_athlete):
    profile = db_session.query(models.LiftProfile).filter(
        models.LiftProfile.athlete_id == sample_athlete.id,
        models.LiftProfile.lift == LiftType.BENCH,
    ).one()
    old = (profile.a, profile.b)
    result = VelocityProfileService(db_session).update_from_recent_sessions(
        sample_athlete.id,
        LiftType.BENCH,
        reference_date=date(2026, 1, 15),
    )
    db_session.refresh(profile)
    assert result["updated"] is False
    assert (profile.a, profile.b) == old
