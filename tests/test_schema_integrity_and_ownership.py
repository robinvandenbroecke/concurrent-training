from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app import models
from app.domain.goal_engine import GoalConfig, GoalType
from app.goal_service import GoalService
from app.services.athlete_service import AthleteService
from app.services.workout_plan_service import WorkoutPlanService, normalize_plan_slot
from app.types import LiftType


def _goal(athlete_id: int, goal_id: str, days: int) -> GoalConfig:
    return GoalConfig(
        goal_id=goal_id,
        athlete_id=str(athlete_id),
        goal_type=GoalType.CONCURRENT_EVENT,
        target_date=date.today() + timedelta(days=days),
        priority="balanced",
    )


def test_new_athlete_has_owner_namespace_and_lift_specific_capacities(db_session):
    athlete = AthleteService.create_athlete(
        db_session,
        "Schema Athlete",
        owner_subject="account:test",
    )
    assert athlete.owner_subject == "account:test"

    states = {
        row.lift: row.C_l
        for row in db_session.query(models.LiftDayState).filter(
            models.LiftDayState.athlete_id == athlete.id
        )
    }
    assert states[LiftType.SQUAT] != states[LiftType.BENCH]
    assert states[LiftType.DEADLIFT] > states[LiftType.PRESS]


def test_owner_filtered_lookup_does_not_cross_namespace(db_session):
    athlete = AthleteService.create_athlete(
        db_session,
        "Owned Athlete",
        owner_subject="account:one",
    )
    assert AthleteService.get_athlete(
        db_session, athlete.id, owner_subject="account:one"
    ) is not None
    assert AthleteService.get_athlete(
        db_session, athlete.id, owner_subject="account:two"
    ) is None


def test_goal_service_preserves_unlimited_inactive_history(db_session):
    athlete = AthleteService.create_athlete(db_session, "Goal Athlete")
    first = GoalService.create_goal(db_session, _goal(athlete.id, "goal-one", 90))
    second = GoalService.create_goal(db_session, _goal(athlete.id, "goal-two", 120))
    third = GoalService.create_goal(db_session, _goal(athlete.id, "goal-three", 150))

    rows = GoalService.get_all_goals(db_session, athlete.id, include_inactive=True)
    assert len(rows) == 3
    assert sum(row.active for row in rows) == 1
    assert GoalService.get_active_goal(db_session, athlete.id).goal_id == third.goal_id
    assert db_session.get(models.Goal, first.id).active is False
    assert db_session.get(models.Goal, second.id).active is False


def test_database_rejects_two_active_goals_for_one_athlete(db_session):
    athlete = AthleteService.create_athlete(db_session, "Unique Goal Athlete")
    GoalService.create_goal(db_session, _goal(athlete.id, "active-one", 90))
    db_session.add(
        models.Goal(
            goal_id="active-two",
            athlete_id=athlete.id,
            goal_type="concurrent_event",
            target_date=(date.today() + timedelta(days=120)).isoformat(),
            priority="balanced",
            goal_json={},
            active=True,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_multiple_workout_slots_can_share_a_calendar_day(db_session):
    athlete = AthleteService.create_athlete(db_session, "Two-a-day Athlete")
    plan_date = date.today() + timedelta(days=1)

    am = WorkoutPlanService.upsert_plan(
        db_session,
        athlete_id=athlete.id,
        plan_date=plan_date,
        slot="AM strength",
        mode="strength",
        plan_json={"session": "squat"},
    )
    pm = WorkoutPlanService.upsert_plan(
        db_session,
        athlete_id=athlete.id,
        plan_date=plan_date,
        slot="pm-endurance",
        mode="endurance",
        plan_json={"session": "cycling"},
    )

    rows = WorkoutPlanService.list_for_date(
        db_session, athlete_id=athlete.id, plan_date=plan_date
    )
    assert {row.slot for row in rows} == {"am_strength", "pm-endurance"}
    assert am.id != pm.id


def test_upsert_replaces_only_the_selected_plan_slot(db_session):
    athlete = AthleteService.create_athlete(db_session, "Upsert Athlete")
    plan_date = date.today() + timedelta(days=2)
    first = WorkoutPlanService.upsert_plan(
        db_session,
        athlete_id=athlete.id,
        plan_date=plan_date,
        slot="primary",
        mode="strength",
        plan_json={"version": 1},
    )
    replacement = WorkoutPlanService.upsert_plan(
        db_session,
        athlete_id=athlete.id,
        plan_date=plan_date,
        slot="primary",
        mode="concurrent",
        plan_json={"version": 2},
    )
    assert replacement.id == first.id
    assert replacement.mode == "concurrent"
    assert replacement.plan_json == {"version": 2}


def test_plan_slot_validation_is_deterministic():
    assert normalize_plan_slot(None) == "primary"
    assert normalize_plan_slot("AM Strength") == "am_strength"
    with pytest.raises(ValueError):
        normalize_plan_slot("invalid/slot")
