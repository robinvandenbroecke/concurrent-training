"""Goal persistence and macrocycle context."""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.domain.goal_engine import (
    GoalConfig,
    GoalState,
    MacrocycleContext,
    PhasePlan,
    PhaseType,
    create_goal_state,
    create_macrocycle,
    get_block_type_for_phase,
    get_microcycle_targets_for_phase,
)
from app.models import Goal as GoalModel


class GoalService:
    """Manage goals while enforcing one active goal per athlete."""

    @staticmethod
    def create_goal(db: Session, goal_config: GoalConfig) -> GoalModel:
        macrocycle = create_macrocycle(goal_config)
        goal_state = create_goal_state(goal_config, macrocycle)
        athlete_id = int(goal_config.athlete_id)

        try:
            db.query(GoalModel).filter(
                GoalModel.athlete_id == athlete_id,
                GoalModel.active.is_(True),
            ).update({"active": False}, synchronize_session=False)
            db.flush()

            db_goal = GoalModel(
                goal_id=goal_config.goal_id,
                athlete_id=athlete_id,
                goal_type=goal_config.goal_type.value,
                target_date=goal_config.target_date.isoformat(),
                priority=goal_config.priority,
                goal_json=goal_config.to_dict(),
                active=True,
                macrocycle_json=macrocycle.to_dict(),
                goal_state_json=goal_state.to_dict(),
            )
            db.add(db_goal)
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(db_goal)
        return db_goal

    @staticmethod
    def get_goal(db: Session, goal_id: str) -> Optional[GoalModel]:
        return db.query(GoalModel).filter(GoalModel.goal_id == goal_id).first()

    @staticmethod
    def get_active_goal(db: Session, athlete_id: int) -> Optional[GoalModel]:
        return db.query(GoalModel).filter(
            GoalModel.athlete_id == athlete_id,
            GoalModel.active.is_(True),
        ).first()

    @staticmethod
    def get_all_goals(
        db: Session,
        athlete_id: int,
        include_inactive: bool = False,
    ) -> List[GoalModel]:
        query = db.query(GoalModel).filter(GoalModel.athlete_id == athlete_id)
        if not include_inactive:
            query = query.filter(GoalModel.active.is_(True))
        return query.order_by(GoalModel.created_at.desc(), GoalModel.id.desc()).all()

    @staticmethod
    def activate_goal(db: Session, goal_id: str) -> Optional[GoalModel]:
        goal = db.query(GoalModel).filter(GoalModel.goal_id == goal_id).first()
        if goal is None:
            return None

        goal_config = GoalConfig.from_dict(goal.goal_json)
        macrocycle = create_macrocycle(goal_config, start_date=date.today())
        goal_state = create_goal_state(goal_config, macrocycle)

        try:
            db.query(GoalModel).filter(
                GoalModel.athlete_id == goal.athlete_id,
                GoalModel.active.is_(True),
            ).update({"active": False}, synchronize_session=False)
            db.flush()

            # The bulk update bypasses the identity map. Refresh before setting
            # active=True so reactivating the already-active row is not lost as
            # a no-op by SQLAlchemy's dirty-state tracking.
            db.refresh(goal)
            goal.active = True
            goal.macrocycle_json = macrocycle.to_dict()
            goal.goal_state_json = goal_state.to_dict()
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(goal)
        return goal

    @staticmethod
    def update_goal_state(
        db: Session,
        goal_id: str,
        goal_state: GoalState,
    ) -> Optional[GoalModel]:
        goal = db.query(GoalModel).filter(GoalModel.goal_id == goal_id).first()
        if goal is None:
            return None
        try:
            goal.goal_state_json = goal_state.to_dict()
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(goal)
        return goal

    @staticmethod
    def delete_goal(db: Session, goal_id: str) -> bool:
        goal = db.query(GoalModel).filter(GoalModel.goal_id == goal_id).first()
        if goal is None:
            return False
        try:
            db.delete(goal)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return True


def get_goal_context_for_program(
    db: Session,
    athlete_id: int,
    target_date: Optional[date] = None,
) -> Optional[Dict]:
    target_date = target_date or date.today()
    goal = GoalService.get_active_goal(db, athlete_id)
    if goal is None:
        return None

    goal_config = GoalConfig.from_dict(goal.goal_json)
    macrocycle = MacrocycleContext(
        goal_config=goal_config,
        phases=[PhasePlan(**phase) for phase in goal.macrocycle_json.get("phases", [])],
    )
    goal_state = GoalState.from_dict(goal.goal_state_json) if goal.goal_state_json else None
    current_phase = macrocycle.get_phase_for_date(target_date)
    if current_phase is None:
        return None

    days_to_event = (goal_config.target_date - target_date).days
    phase_week_index = (target_date - current_phase.start_date).days // 7
    return {
        "goal_id": goal.goal_id,
        "goal_type": goal.goal_type,
        "target_date": goal_config.target_date.isoformat(),
        "days_to_event": days_to_event,
        "current_phase": current_phase.phase_type.value,
        "phase_start_date": current_phase.start_date.isoformat(),
        "phase_end_date": current_phase.end_date.isoformat(),
        "phase_week_index": phase_week_index,
        "priority": goal.priority,
        "block_type": get_block_type_for_phase(current_phase.phase_type),
        "microcycle_targets": get_microcycle_targets_for_phase(
            current_phase.phase_type, goal_config
        ),
        "goal_config": goal_config.to_dict(),
        "macrocycle": macrocycle.to_dict(),
        "goal_state": goal_state.to_dict() if goal_state else None,
    }


def should_apply_phase_guardrails(phase: str, proposed_adjustment: Dict) -> Dict:
    """Apply phase-specific safety guardrails to a proposed adjustment."""
    adjusted = dict(proposed_adjustment)

    if phase == PhaseType.TAPER.value:
        if adjusted.get("volume_adjustment_pct", 0) > 0:
            adjusted["volume_adjustment_pct"] = 0
        if adjusted.get("add_stimulus_lifts"):
            adjusted["add_stimulus_lifts"] = []
        if adjusted.get("add_hiit_intervals", 0) > 0:
            adjusted["add_hiit_intervals"] = 0
        if adjusted.get("intensity_adjustment_pct", 0) > 0.02:
            adjusted["intensity_adjustment_pct"] = 0.02
        adjusted["phase_guardrail_applied"] = "taper_volume_locked"

    elif phase == PhaseType.PEAK.value:
        if adjusted.get("volume_adjustment_pct", 0) > 0:
            adjusted["volume_adjustment_pct"] = 0
        if adjusted.get("add_stimulus_lifts"):
            adjusted["add_stimulus_lifts"] = []
        adjusted["phase_guardrail_applied"] = "peak_no_extra_volume"

    return adjusted
