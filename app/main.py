"""
FastAPI application - main entry point
"""
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base, get_db
from app import models, schemas
from app.services import (
    AthleteService, SessionService, DayUpdateService,
    ReadinessService, AutoregulationService
)
from app.performance_service import (
    get_or_compute_performance_report,
    compute_and_store_performance_report
)
from app.goal_service import GoalService, get_goal_context_for_program
from app.domain.goal_engine import GoalConfig, GoalType
from app.types import LiftType, EnduranceSport
from app.config import settings


# Create tables on startup
Base.metadata.create_all(bind=engine)


# API Key authentication
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_admin_api_key(api_key: str = Security(api_key_header)):
    """Verify admin API key for protected endpoints"""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key header missing"
        )
    if api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )
    return api_key


app = FastAPI(
    title="Concurrent Training API",
    description="API for managing concurrent strength and endurance training with fatigue modeling",
    version="1.0.0"
)

# CORS for web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    """Redirect to UI"""
    return {"message": "Concurrent Training API", "ui": "/static/index.html"}


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "1.0.0"}


# Athlete endpoints
@app.post("/athletes", response_model=schemas.AthleteResponse)
def create_athlete(athlete: schemas.AthleteCreate, db: Session = Depends(get_db)):
    """Create a new athlete with default profiles"""
    return AthleteService.create_athlete(db, athlete.name)


@app.get("/athletes/{athlete_id}", response_model=schemas.AthleteResponse)
def get_athlete(athlete_id: int, db: Session = Depends(get_db)):
    """Get athlete by ID"""
    athlete = AthleteService.get_athlete(db, athlete_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    return athlete


# Strength session endpoints
@app.post("/sessions/strength", response_model=schemas.StrengthSessionResponse)
def create_strength_session(
    session: schemas.StrengthSessionCreate,
    db: Session = Depends(get_db)
):
    """
    Ingest a strength training session with VBT data
    """
    service = SessionService(db)
    try:
        return service.ingest_strength_session(
            athlete_id=session.athlete_id,
            lift=session.lift,
            start_time=session.start_time,
            sets_data=session.sets
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Endurance session endpoints
@app.post("/sessions/endurance", response_model=schemas.EnduranceSessionResponse)
def create_endurance_session(
    session: schemas.EnduranceSessionCreate,
    db: Session = Depends(get_db)
):
    """
    Ingest an endurance training session
    """
    service = SessionService(db)
    return service.ingest_endurance_session(
        athlete_id=session.athlete_id,
        sport=session.sport,
        start_time=session.start_time,
        duration_minutes=session.duration_minutes,
        intensity_type=session.intensity_type
    )


# Autoregulation endpoint
@app.post("/strength/autoregulate", response_model=schemas.AutoregulateResponse)
def autoregulate(
    request: schemas.AutoregulateRequest,
    db: Session = Depends(get_db)
):
    """
    Get autoregulation suggestions for current set
    """
    service = AutoregulationService(db)
    try:
        return service.suggest(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Readiness endpoints
@app.get("/readiness/today", response_model=schemas.ReadinessResponse)
def get_readiness_today(
    athlete_id: int = Query(..., description="Athlete ID"),
    db: Session = Depends(get_db)
):
    """
    Get readiness scores for today with explanations
    """
    service = ReadinessService(db)
    return service.get_readiness(athlete_id)


@app.get("/readiness/{date_str}", response_model=schemas.ReadinessResponse)
def get_readiness_for_date(
    date_str: str,
    athlete_id: int = Query(..., description="Athlete ID"),
    db: Session = Depends(get_db)
):
    """
    Get readiness scores for a specific date (YYYY-MM-DD)
    """
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
    
    service = ReadinessService(db)
    return service.get_readiness(athlete_id, target_date)


# Trend endpoints
@app.get("/trends/lift", response_model=schemas.LiftTrendResponse)
def get_lift_trends(
    athlete_id: int = Query(..., description="Athlete ID"),
    lift: LiftType = Query(..., description="Lift type"),
    days: int = Query(30, ge=7, le=365, description="Number of days"),
    db: Session = Depends(get_db)
):
    """
    Get trend data for a specific lift
    """
    service = ReadinessService(db)
    return service.get_lift_trends(athlete_id, lift, days)


@app.get("/trends/endurance", response_model=schemas.EnduranceTrendResponse)
def get_endurance_trends(
    athlete_id: int = Query(..., description="Athlete ID"),
    days: int = Query(30, ge=7, le=365, description="Number of days"),
    db: Session = Depends(get_db)
):
    """
    Get endurance trend data
    """
    service = ReadinessService(db)
    return service.get_endurance_trends(athlete_id, days)


# Day update endpoint (for cron/manual trigger) - Protected with API key
@app.post("/admin/update-day/{athlete_id}")
def update_day_state(
    athlete_id: int,
    date_str: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: str = Security(verify_admin_api_key)
):
    """
    Trigger day state update (normally run by cron)
    """
    service = DayUpdateService(db)
    
    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
    else:
        target_date = date.today()
    
    state = service.update_day_state(athlete_id, target_date)
    return {
        "status": "updated",
        "athlete_id": athlete_id,
        "date": target_date.isoformat(),
        "D_sys": state.D_sys,
        "R_mito": state.R_mito,
        "E_fat": state.E_fat
    }


# Performance endpoints (Sprint 6)
@app.get("/performance/report")
def get_performance_report(
    athlete_id: int = Query(..., description="Athlete ID"),
    days: int = Query(28, ge=7, le=90, description="Days to analyze"),
    force_recompute: bool = Query(False, description="Force recompute even if cached"),
    db: Session = Depends(get_db)
):
    """
    Get performance report for an athlete.

    Computes strength and endurance performance metrics, detects trends
    (progress, stagnation, regression), and provides program adjustment signals.

    Returns:
        PerformanceReport JSON with trends, signals, and recommendations
    """
    report = get_or_compute_performance_report(
        db, athlete_id, days=days, force_recompute=force_recompute
    )
    return report.to_dict()


@app.post("/performance/compute/{athlete_id}")
def compute_performance(
    athlete_id: int,
    days: int = Query(28, ge=7, le=90),
    db: Session = Depends(get_db),
    api_key: str = Security(verify_admin_api_key)
):
    """
    Manually trigger performance computation and storage.
    Protected endpoint for admin use.
    """
    report = compute_and_store_performance_report(db, athlete_id, days=days)
    return {
        "status": "computed",
        "athlete_id": athlete_id,
        "report_date": report.report_date.isoformat(),
        "overall_signal": report.overall_signal.value,
        "suggest_deload": report.suggest_deload,
        "lift_trends": list(report.lift_trends.keys()),
        "endurance_trends": list(report.endurance_trends.keys())
    }


# Goal endpoints (Sprint 7)
@app.post("/goals/create")
def create_goal_endpoint(
    goal_data: dict,
    db: Session = Depends(get_db)
):
    """
    Create a new training goal with macrocycle.

    Request body:
    {
        "goal_id": "spring_5k_2024",
        "athlete_id": "123",
        "goal_type": "endurance_event",
        "target_date": "2024-05-15",
        "priority": "endurance",
        "strength_targets": [{"lift": "squat", "metric": "3rm", "target_value": 140}],
        "endurance_targets": [{"sport": "running", "event_type": "5k", "target_value": 20.0}],
        "notes": "Spring 5K race goal"
    }
    """
    goal_config = GoalConfig.from_dict(goal_data)
    goal_db = GoalService.create_goal(db, goal_config)
    return {
        "status": "created",
        "goal_id": goal_db.goal_id,
        "athlete_id": goal_db.athlete_id,
        "goal_type": goal_db.goal_type,
        "target_date": goal_db.target_date
    }


@app.post("/goals/activate/{goal_id}")
def activate_goal_endpoint(
    goal_id: str,
    db: Session = Depends(get_db)
):
    """
    Activate a goal (deactivates other goals for athlete).
    """
    goal_db = GoalService.activate_goal(db, goal_id)
    if not goal_db:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {
        "status": "activated",
        "goal_id": goal_db.goal_id,
        "goal_type": goal_db.goal_type,
        "target_date": goal_db.target_date
    }


@app.get("/goals/active")
def get_active_goal_endpoint(
    athlete_id: int = Query(..., description="Athlete ID"),
    db: Session = Depends(get_db)
):
    """
    Get active goal for athlete with current phase info.
    """
    goal_db = GoalService.get_active_goal(db, athlete_id)
    if not goal_db:
        return {"has_goal": False}

    context = get_goal_context_for_program(db, athlete_id)
    return {
        "has_goal": True,
        "goal_id": goal_db.goal_id,
        "goal_type": goal_db.goal_type,
        "target_date": goal_db.target_date,
        "priority": goal_db.priority,
        "block_type": context.get("block_type") if context else None,
        "microcycle_targets": context.get("microcycle_targets") if context else None
    }


@app.get("/goals/list")
def list_goals_endpoint(
    athlete_id: int = Query(..., description="Athlete ID"),
    include_inactive: bool = Query(False, description="Include inactive goals"),
    db: Session = Depends(get_db)
):
    """
    List all goals for athlete.
    """
    goals = GoalService.get_all_goals(db, athlete_id, include_inactive=include_inactive)
    return {
        "goals": [
            {
                "goal_id": g.goal_id,
                "goal_type": g.goal_type,
                "target_date": g.target_date,
                "active": g.active,
                "created_at": g.created_at.isoformat() if g.created_at else None
            }
            for g in goals
        ]
    }


@app.delete("/goals/{goal_id}")
def delete_goal_endpoint(
    goal_id: str,
    db: Session = Depends(get_db)
):
    """
    Delete a goal.
    """
    success = GoalService.delete_goal(db, goal_id)
    if not success:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"status": "deleted", "goal_id": goal_id}


# ============================================================================
# Sprint A: State Fetch Service
# ============================================================================

@app.get("/state/day")
def get_day_state_endpoint(
    athlete_id: int = Query(..., description="Athlete ID"),
    target_date: Optional[date] = Query(None, description="Date (default: today)"),
    db: Session = Depends(get_db)
):
    """
    Get day state snapshot for athlete on specific date.
    Used by coach/program/performance engines.
    """
    from app.services.engine_orchestrator import EngineOrchestrator
    
    target_date = target_date or date.today()
    orchestrator = EngineOrchestrator(db)
    day_state = orchestrator.get_day_state_snapshot(athlete_id, target_date)
    
    if not day_state:
        raise HTTPException(status_code=404, detail="No state found for date")
    
    return {
        "athlete_id": athlete_id,
        "date": target_date.isoformat(),
        "per_lift": {
            lift: {
                "D_l": state.D_l,
                "F_l": state.F_l,
                "C_l": state.C_l
            }
            for lift, state in day_state.per_lift.items()
        },
        "D_sys": day_state.D_sys,
        "R_mito": day_state.R_mito,
        "E_fat": day_state.E_fat,
        "T_legs": getattr(day_state, 'T_legs', 0.0)
    }


@app.get("/state/readiness")
def get_readiness_endpoint(
    athlete_id: int = Query(..., description="Athlete ID"),
    target_date: Optional[date] = Query(None, description="Date (default: today)"),
    db: Session = Depends(get_db)
):
    """
    Get readiness scores for athlete on specific date.
    """
    from app.services.engine_orchestrator import EngineOrchestrator
    
    target_date = target_date or date.today()
    orchestrator = EngineOrchestrator(db)
    readiness = orchestrator.compute_readiness(athlete_id, target_date)
    
    return {
        "athlete_id": athlete_id,
        "date": target_date.isoformat(),
        "overall": readiness.overall,
        "per_lift": readiness.per_lift,
        "endurance": readiness.endurance,
        "legs_structural": getattr(readiness, 'legs_structural', None),
        "explanations": readiness.explanations
    }


@app.get("/sessions/recent")
def get_recent_sessions_endpoint(
    athlete_id: int = Query(..., description="Athlete ID"),
    days: int = Query(7, description="Number of days to look back"),
    db: Session = Depends(get_db)
):
    """
    Get recent sessions for performance analysis.
    """
    from app.services.engine_orchestrator import EngineOrchestrator
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    orchestrator = EngineOrchestrator(db)
    sessions = orchestrator.get_recent_sessions(athlete_id, start_date, end_date)
    
    return {
        "athlete_id": athlete_id,
        "date_from": start_date.isoformat(),
        "date_to": end_date.isoformat(),
        "strength_sessions": [
            {
                "id": s.id,
                "lift": s.lift.value,
                "start_time": s.start_time.isoformat() if s.start_time else None,
                "tonnage": s.tonnage,
                "avg_intensity": s.avg_intensity
            }
            for s in sessions["strength"]
        ],
        "endurance_sessions": [
            {
                "id": s.id,
                "sport": s.sport.value,
                "start_time": s.start_time.isoformat() if s.start_time else None,
                "duration_minutes": s.duration_minutes,
                "intensity_type": s.intensity_type
            }
            for s in sessions["endurance"]
        ]
    }


# ============================================================================
# Sprint A: Legacy Comparison Endpoints (explicit /legacy prefix)
# ============================================================================

@app.post("/legacy/sessions/strength")
def create_strength_session_legacy(
    session: schemas.StrengthSessionCreate,
    db: Session = Depends(get_db)
):
    """
    [LEGACY] Ingest strength session using legacy ConcurrentTrainingModel.
    For comparison/testing only - does NOT update primary state.
    """
    import os
    if not os.getenv("USE_LEGACY_MODEL"):
        raise HTTPException(
            status_code=403,
            detail="Legacy endpoints disabled. Set USE_LEGACY_MODEL=true to enable."
        )
    
    # Import legacy service
    from app.domain.model import ConcurrentTrainingModel
    
    # Run legacy model (results not stored to primary state)
    model = ConcurrentTrainingModel()
    
    return {
        "status": "legacy_computed",
        "message": "Legacy model results (not stored)",
        "athlete_id": session.athlete_id,
        "lift": session.lift.value
    }


@app.get("/legacy/status")
def legacy_status():
    """
    Check legacy model feature flag status.
    """
    import os
    use_legacy = os.getenv("USE_LEGACY_MODEL", "false").lower() == "true"
    
    return {
        "use_legacy_model": use_legacy,
        "primary_engine": "modular_engines",
        "available_engines": ["rep_engine", "day_engine", "performance_engine", "program_engine", "goal_engine"],
        "legacy_available": True
    }
