from datetime import date, timedelta

from app.domain.goal_engine import GoalConfig, GoalType
from app.goal_service import GoalService
from app.services.athlete_service import AthleteService


def _goal(athlete_id: int, goal_id: str, days: int) -> GoalConfig:
    return GoalConfig(
        goal_id=goal_id,
        athlete_id=str(athlete_id),
        goal_type=GoalType.CONCURRENT_EVENT,
        target_date=date.today() + timedelta(days=days),
        priority="balanced",
    )


def test_reactivating_current_goal_remains_active(db_session):
    athlete = AthleteService.create_athlete(db_session, "Reactivation Athlete")
    goal = GoalService.create_goal(db_session, _goal(athlete.id, "current", 90))

    reactivated = GoalService.activate_goal(db_session, goal.goal_id)

    assert reactivated is not None
    assert reactivated.active is True
    assert GoalService.get_active_goal(db_session, athlete.id).id == goal.id


def test_activating_archived_goal_switches_active_row_without_losing_history(db_session):
    athlete = AthleteService.create_athlete(db_session, "Archived Goal Athlete")
    first = GoalService.create_goal(db_session, _goal(athlete.id, "first", 90))
    GoalService.create_goal(db_session, _goal(athlete.id, "second", 120))

    activated = GoalService.activate_goal(db_session, first.goal_id)
    history = GoalService.get_all_goals(db_session, athlete.id, include_inactive=True)

    assert activated.id == first.id
    assert sum(row.active for row in history) == 1
    assert len(history) == 2
