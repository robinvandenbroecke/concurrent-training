"""
Goal service layer.

Manages goal CRUD operations and provides goal context to program engine.
"""
from datetime import date
from typing import Optional, List, Dict

from sqlalchemy.orm import Session

from app.domain.goal_engine import (
    GoalConfig,
    GoalState,
    MacrocycleContext,
    create_macrocycle,
    create_goal_state,
    advance_goal_state,
    get_block_type_for_phase,
    get_microcycle_targets_for_phase,
)
from app.models import Goal as GoalModel


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
    # Create macrocycle
    macrocycle = create_macrocycle(goal_config)
    
    # Create initial goal state
    goal_state = create_goal_state(goal_config, macrocycle)
    
    # Get current phase info
    current_phase = macrocycle.get_current_phase()
    
    # Create database record
    goal_db = GoalModel(
        goal_id=goal_config.goal_id,
        athlete_id=int(goal_config.athlete_id) if goal_config.athlete_id.isdigit() else 0,
        goal_type=goal_config.goal_type.value,
        target_date=goal_config.target_date.isoformat(),
        priority=goal_config.priority,
        goal_json=goal_config.to_dict(),
        active=True,
        current_phase=goal_state.current_phase.value,
        phase_start_date=current_phase.start_date.isoformat() if current_phase else None,
        phase_end_date=current_phase.end_date.isoformat() if current_phase else None,
        macrocycle_json=macrocycle.to_dict()
    )
    
    db.add(goal_db)
    db.commit()
    db.refresh(goal_db)
    
    return goal_db


def get_goal(
    db: Session,
    athlete_id: int,
    goal_id: str
) -> Optional[GoalModel]:
    """
    Get goal by athlete_id and goal_id.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        goal_id: Goal ID
    
    Returns:
        Goal model or None
    """
    return db.query(GoalModel).filter(
        GoalModel.athlete_id == athlete_id,
        GoalModel.goal_id == goal_id
    ).first()


def get_active_goal(
    db: Session,
    athlete_id: int
) -> Optional[GoalModel]:
    """
    Get active goal for athlete.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
    
    Returns:
        Active Goal model or None
    """
    return db.query(GoalModel).filter(
        GoalModel.athlete_id == athlete_id,
        GoalModel.active == True
    ).first()


def get_goal_config(
    db: Session,
    athlete_id: int,
    goal_id: str
) -> Optional[GoalConfig]:
    """
    Get GoalConfig from database.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        goal_id: Goal ID
    
    Returns:
        GoalConfig or None
    """
    goal_db = get_goal(db, athlete_id, goal_id)
    if not goal_db:
        return None
    
    return GoalConfig.from_dict(goal_db.goal_json)


def activate_goal(
    db: Session,
    athlete_id: int,
    goal_id: str
) -> Optional[GoalModel]:
    """
    Activate a goal (deactivates others for same athlete).
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        goal_id: Goal ID to activate
    
    Returns:
        Activated Goal model or None
    """
    # Deactivate all other goals
    db.query(GoalModel).filter(
        GoalModel.athlete_id == athlete_id,
        GoalModel.active == True
    ).update({"active": False})
    
    # Activate target goal
    goal_db = get_goal(db, athlete_id, goal_id)
    if goal_db:
        goal_db.active = True
        db.commit()
        db.refresh(goal_db)
    
    return goal_db


def deactivate_goal(
    db: Session,
    athlete_id: int,
    goal_id: str
) -> Optional[GoalModel]:
    """
    Deactivate a goal.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        goal_id: Goal ID to deactivate
    
    Returns:
        Deactivated Goal model or None
    """
    goal_db = get_goal(db, athlete_id, goal_id)
    if goal_db:
        goal_db.active = False
        db.commit()
        db.refresh(goal_db)
    
    return goal_db


def update_goal_state(
    db: Session,
    athlete_id: int,
    goal_id: str
) -> Optional[GoalModel]:
    """
    Update goal state (advance phase if needed).
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        goal_id: Goal ID
    
    Returns:
        Updated Goal model or None
    """
    goal_db = get_goal(db, athlete_id, goal_id)
    if not goal_db or not goal_db.active:
        return None
    
    # Reconstruct goal state and macrocycle
    goal_config = GoalConfig.from_dict(goal_db.goal_json)
    macrocycle = MacrocycleContext(
        goal_config=goal_config,
        phases=[]  # Would need to reconstruct from macrocycle_json
    )
    
    goal_state = GoalState(
        goal_id=goal_id,
        athlete_id=str(athlete_id),
        active=True,
        current_phase=goal_db.current_phase,
        phase_start_date=date.fromisoformat(goal_db.phase_start_date) if goal_db.phase_start_date else date.today(),
        phase_end_date=date.fromisoformat(goal_db.phase_end_date) if goal_db.phase_end_date else date.today(),
        last_phase_update_date=date.today()
    )
    
    # Advance if needed
    updated_state = advance_goal_state(goal_state, macrocycle)
    
    # Save changes
    goal_db.current_phase = updated_state.current_phase.value
    if updated_state.phase_start_date:
        goal_db.phase_start_date = updated_state.phase_start_date.isoformat()
    if updated_state.phase_end_date:
        goal_db.phase_end_date = updated_state.phase_end_date.isoformat()
    
    db.commit()
    db.refresh(goal_db)
    
    return goal_db


def list_goals(
    db: Session,
    athlete_id: int,
    active_only: bool = False
) -> List[GoalModel]:
    """
    List goals for athlete.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        active_only: Only return active goals
    
    Returns:
        List of Goal models
    """
    query = db.query(GoalModel).filter(GoalModel.athlete_id == athlete_id)
    
    if active_only:
        query = query.filter(GoalModel.active == True)
    
    return query.order_by(GoalModel.created_at.desc()).all()


def get_goal_context_for_program(
    db: Session,
    athlete_id: int
) -> Optional[Dict]:
    """
    Get goal context for program engine.
    
    Returns structured data that program_engine can use to adjust microcycles.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
    
    Returns:
        Dict with goal context or None
    """
    goal_db = get_active_goal(db, athlete_id)
    if not goal_db:
        return None
    
    goal_config = GoalConfig.from_dict(goal_db.goal_json)
    
    return {
        "has_goal": True,
        "goal_id": goal_db.goal_id,
        "goal_type": goal_db.goal_type,
        "target_date": goal_db.target_date,
        "priority": goal_db.priority,
        "current_phase": goal_db.current_phase,
        "phase_start_date": goal_db.phase_start_date,
        "phase_end_date": goal_db.phase_end_date,
        "block_type": get_block_type_for_phase(goal_db.current_phase),
        "targets": get_microcycle_targets_for_phase(
            goal_db.current_phase,
            goal_config
        ),
        "strength_targets": [t.to_dict() for t in goal_config.strength_targets],
        "endurance_targets": [t.to_dict() for t in goal_config.endurance_targets],
    }


def delete_goal(
    db: Session,
    athlete_id: int,
    goal_id: str
) -> bool:
    """
    Delete a goal.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        goal_id: Goal ID
    
    Returns:
        True if deleted, False if not found
    """
    goal_db = get_goal(db, athlete_id, goal_id)
    if not goal_db:
        return False
    
    db.delete(goal_db)
    db.commit()
    return True
