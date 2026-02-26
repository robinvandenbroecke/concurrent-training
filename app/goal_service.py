"""
Goal service layer.

Manages goal CRUD operations and macrocycle context retrieval.
"""
from datetime import date
from typing import Optional, List, Dict

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.domain.goal_engine import (
    GoalConfig,
    GoalState,
    MacrocycleContext,
    PhaseType,
    create_macrocycle,
    create_goal_state,
    get_block_type_for_phase,
    get_microcycle_targets_for_phase,
)
from app.models import Goal as GoalModel


class GoalService:
    """Service for managing training goals."""
    
    @staticmethod
    def create_goal(
        db: Session,
        goal_config: GoalConfig
    ) -> GoalModel:
        """
        Create a new goal with computed macrocycle.
        
        Args:
            db: Database session
            goal_config: Goal configuration
        
        Returns:
            Created Goal model
        """
        # Compute macrocycle
        macrocycle = create_macrocycle(goal_config)
        
        # Create initial goal state
        goal_state = create_goal_state(goal_config, macrocycle)
        
        # Deactivate any existing active goals for this athlete
        existing_active = db.query(GoalModel).filter(
            and_(
                GoalModel.athlete_id == int(goal_config.athlete_id),
                GoalModel.active == True
            )
        ).all()
        
        for g in existing_active:
            g.active = False
        
        # Create new goal
        db_goal = GoalModel(
            goal_id=goal_config.goal_id,
            athlete_id=int(goal_config.athlete_id),
            goal_type=goal_config.goal_type.value,
            target_date=goal_config.target_date.isoformat(),
            priority=goal_config.priority,
            goal_json=goal_config.to_dict(),
            active=True,
            macrocycle_json=macrocycle.to_dict(),
            goal_state_json=goal_state.to_dict()
        )
        
        db.add(db_goal)
        db.commit()
        db.refresh(db_goal)
        
        return db_goal
    
    @staticmethod
    def get_goal(
        db: Session,
        goal_id: str
    ) -> Optional[GoalModel]:
        """Get goal by ID."""
        return db.query(GoalModel).filter(GoalModel.goal_id == goal_id).first()
    
    @staticmethod
    def get_active_goal(
        db: Session,
        athlete_id: int
    ) -> Optional[GoalModel]:
        """Get active goal for athlete."""
        return db.query(GoalModel).filter(
            and_(
                GoalModel.athlete_id == athlete_id,
                GoalModel.active == True
            )
        ).first()
    
    @staticmethod
    def get_all_goals(
        db: Session,
        athlete_id: int,
        include_inactive: bool = False
    ) -> List[GoalModel]:
        """Get all goals for athlete."""
        query = db.query(GoalModel).filter(GoalModel.athlete_id == athlete_id)
        if not include_inactive:
            query = query.filter(GoalModel.active == True)
        return query.order_by(GoalModel.created_at.desc()).all()
    
    @staticmethod
    def activate_goal(
        db: Session,
        goal_id: str
    ) -> Optional[GoalModel]:
        """
        Activate a specific goal (deactivate others).
        
        Args:
            db: Database session
            goal_id: Goal ID to activate
        
        Returns:
            Activated Goal model or None
        """
        goal = db.query(GoalModel).filter(GoalModel.goal_id == goal_id).first()
        if not goal:
            return None
        
        # Deactivate all goals for this athlete
        db.query(GoalModel).filter(
            GoalModel.athlete_id == goal.athlete_id
        ).update({"active": False})
        
        # Activate target goal
        goal.active = True
        
        # Recompute macrocycle from today
        goal_config = GoalConfig.from_dict(goal.goal_json)
        macrocycle = create_macrocycle(goal_config, start_date=date.today())
        goal_state = create_goal_state(goal_config, macrocycle)
        
        goal.macrocycle_json = macrocycle.to_dict()
        goal.goal_state_json = goal_state.to_dict()
        
        db.commit()
        db.refresh(goal)
        
        return goal
    
    @staticmethod
    def update_goal_state(
        db: Session,
        goal_id: str,
        goal_state: GoalState
    ) -> Optional[GoalModel]:
        """Update goal state."""
        goal = db.query(GoalModel).filter(GoalModel.goal_id == goal_id).first()
        if goal:
            goal.goal_state_json = goal_state.to_dict()
            db.commit()
            db.refresh(goal)
        return goal
    
    @staticmethod
    def delete_goal(
        db: Session,
        goal_id: str
    ) -> bool:
        """Delete a goal."""
        goal = db.query(GoalModel).filter(GoalModel.goal_id == goal_id).first()
        if goal:
            db.delete(goal)
            db.commit()
            return True
        return False


def get_goal_context_for_program(
    db: Session,
    athlete_id: int,
    target_date: date = None
) -> Optional[Dict]:
    """
    Get goal context for program engine.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        target_date: Date to get context for (default: today)
    
    Returns:
        Dict with goal context or None
    """
    target_date = target_date or date.today()
    
    goal = GoalService.get_active_goal(db, athlete_id)
    if not goal:
        return None
    
    goal_config = GoalConfig.from_dict(goal.goal_json)
    macrocycle = MacrocycleContext(
        goal_config=goal_config,
        phases=[PhasePlan(**p) for p in goal.macrocycle_json.get("phases", [])]
    )
    goal_state = GoalState.from_dict(goal.goal_state_json) if goal.goal_state_json else None
    
    # Get current phase for date
    current_phase = macrocycle.get_phase_for_date(target_date)
    if not current_phase:
        return None
    
    # Calculate days to event
    days_to_event = (goal_config.target_date - target_date).days
    
    # Calculate phase week index
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
        "goal_state": goal_state.to_dict() if goal_state else None
    }


def should_apply_phase_guardrails(
    phase: str,
    proposed_adjustment: Dict
) -> Dict:
    """
    Apply phase guardrails to performance adjustments.
    
    Rules:
    - Taper: cannot increase volume, only small intensity touches
    - Peak: no extra volume, allow slight intensity adjustment
    - Base/Build: normal performance feedback
    
    Args:
        phase: Current phase string
        proposed_adjustment: Performance adjustment dict
    
    Returns:
        Adjusted adjustment dict
    """
    adjusted = dict(proposed_adjustment)
    
    if phase == PhaseType.TAPER.value:
        # Taper: cannot increase volume
        if adjusted.get("volume_adjustment_pct", 0) > 0:
            adjusted["volume_adjustment_pct"] = 0
        if adjusted.get("add_stimulus_lifts"):
            adjusted["add_stimulus_lifts"] = []
        if adjusted.get("add_hiit_intervals", 0) > 0:
            adjusted["add_hiit_intervals"] = 0
        # Allow small intensity adjustment only
        if adjusted.get("intensity_adjustment_pct", 0) > 0.02:
            adjusted["intensity_adjustment_pct"] = 0.02
        adjusted["phase_guardrail_applied"] = "taper_volume_locked"
    
    elif phase == PhaseType.PEAK.value:
        # Peak: no extra volume
        if adjusted.get("volume_adjustment_pct", 0) > 0:
            adjusted["volume_adjustment_pct"] = 0
        if adjusted.get("add_stimulus_lifts"):
            adjusted["add_stimulus_lifts"] = []
        adjusted["phase_guardrail_applied"] = "peak_no_extra_volume"
    
    return adjusted
