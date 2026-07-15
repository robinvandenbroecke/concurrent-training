"""FastAPI entry point for the canonical concurrent-training runtime."""
from __future__ import annotations

from datetime import date, timedelta
from html import escape
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.database import Base, engine, get_db
from app.domain.goal_engine import GoalConfig
from app.goal_service import GoalService, get_goal_context_for_program
from app.integrations import StravaAuthError, StravaError, StravaService
from app.performance_service import compute_and_store_performance_report, get_or_compute_performance_report
from app.services import (
    AthleteService,
    AutoregulationService,
    DayUpdateService,
    ReadinessService,
    SessionService,
)
from app.services.capacity_profile_service import CapacityProfileService
from app.services.engine_orchestrator import EngineOrchestrator
from app.types import EnduranceSport, LiftType


if settings.auto_create_tables:
    Base.metadata.create_all(bind=engine)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)):
    if not settings.require_api_key:
        return api_key
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required")
    if not hmac.compare_digest(api_key, settings.admin_api_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return api_key


async def verify_admin_api_key(api_key: Optional[str] = Security(api_key_header)):
    """Admin mutations always require the configured key in every environment."""
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin API key required")
    if not hmac.compare_digest(api_key, settings.admin_api_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin API key")
    return api_key


app = FastAPI(
    title="Concurrent Training API",
    description="Concurrent strength and endurance training with VBT and power-first endurance modeling",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")
protected = APIRouter(dependencies=[Security(verify_api_key)])


@app.get("/")
def root():
    return {"message": "Concurrent Training API", "version": "2.0.0", "ui": "/static/index.html"}


@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "2.0.0", "environment": settings.app_env}


@protected.get("/athletes")
def list_athletes(db: Session = Depends(get_db)):
    return db.query(models.Athlete).order_by(models.Athlete.created_at).all()


@protected.post("/athletes", response_model=schemas.AthleteResponse)
def create_athlete(athlete: schemas.AthleteCreate, db: Session = Depends(get_db)):
    return AthleteService.create_athlete(db, athlete.name)


@protected.get("/athletes/{athlete_id}", response_model=schemas.AthleteResponse)
def get_athlete(athlete_id: int, db: Session = Depends(get_db)):
    athlete = AthleteService.get_athlete(db, athlete_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    return athlete


@protected.post("/sessions/strength", response_model=schemas.StrengthSessionResponse)
def create_strength_session(session: schemas.StrengthSessionCreate, db: Session = Depends(get_db)):
    try:
        return SessionService(db).ingest_strength_session(
            athlete_id=session.athlete_id,
            lift=session.lift,
            start_time=session.start_time,
            end_time=session.end_time,
            sets_data=session.sets,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@protected.post("/sessions/strength-workout")
def create_strength_workout(workout: schemas.StrengthWorkoutCreate, db: Session = Depends(get_db)):
    try:
        sessions = SessionService(db).ingest_strength_workout(workout)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "athlete_id": workout.athlete_id,
        "start_time": workout.start_time,
        "session_ids": [item.id for item in sessions],
        "lifts": [item.lift.value for item in sessions],
        "total_tonnage": sum(item.tonnage for item in sessions),
    }


@protected.post("/sessions/endurance", response_model=schemas.EnduranceSessionResponse)
def create_endurance_session(session: schemas.EnduranceSessionCreate, db: Session = Depends(get_db)):
    power_data = [point.model_dump() for point in session.power_data] if session.power_data else None
    return SessionService(db).ingest_endurance_session(
        athlete_id=session.athlete_id,
        sport=session.sport,
        start_time=session.start_time,
        end_time=session.end_time,
        duration_minutes=session.duration_minutes,
        intensity_type=session.intensity_type,
        power_data=power_data,
        average_power_w=session.average_power_w,
        normalized_power_w=session.normalized_power_w,
        threshold_power_w=session.threshold_power_w,
        average_heartrate=session.average_heartrate,
        rpe=session.rpe,
    )


@protected.post("/strength/autoregulate", response_model=schemas.AutoregulateResponse)
def autoregulate(request: schemas.AutoregulateRequest, db: Session = Depends(get_db)):
    try:
        return AutoregulationService(db).suggest(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@protected.get("/readiness/today", response_model=schemas.ReadinessResponse)
def readiness_today(athlete_id: int = Query(..., gt=0), db: Session = Depends(get_db)):
    return ReadinessService(db).get_readiness(athlete_id)


@protected.get("/readiness/{date_str}", response_model=schemas.ReadinessResponse)
def readiness_for_date(date_str: str, athlete_id: int = Query(..., gt=0), db: Session = Depends(get_db)):
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD") from exc
    return ReadinessService(db).get_readiness(athlete_id, target_date)


@protected.get("/trends/lift", response_model=schemas.LiftTrendResponse)
def lift_trends(
    athlete_id: int = Query(..., gt=0),
    lift: LiftType = Query(...),
    days: int = Query(30, ge=7, le=365),
    db: Session = Depends(get_db),
):
    return ReadinessService(db).get_lift_trends(athlete_id, lift, days)


@protected.get("/trends/endurance", response_model=schemas.EnduranceTrendResponse)
def endurance_trends(
    athlete_id: int = Query(..., gt=0),
    days: int = Query(30, ge=7, le=365),
    db: Session = Depends(get_db),
):
    return ReadinessService(db).get_endurance_trends(athlete_id, days)


@protected.get("/state/day")
def state_day(
    athlete_id: int = Query(..., gt=0),
    target_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    target_date = target_date or date.today()
    state = EngineOrchestrator(db).get_day_state_with_carryover(athlete_id, target_date)
    if state is None:
        raise HTTPException(status_code=404, detail="No state found")
    return {
        "athlete_id": athlete_id,
        "date": target_date.isoformat(),
        "per_lift": {
            lift: {"D_l": item.D_l, "F_l": item.F_l, "C_l": item.C_l}
            for lift, item in state.per_lift.items()
        },
        "D_sys": state.D_sys,
        "R_mito": state.R_mito,
        "E_fat": state.E_fat,
        "T_legs": state.T_legs,
    }


@protected.get("/state/readiness")
def state_readiness(
    athlete_id: int = Query(..., gt=0),
    target_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    output = EngineOrchestrator(db).compute_readiness(athlete_id, target_date or date.today())
    return {
        "athlete_id": athlete_id,
        "date": (target_date or date.today()).isoformat(),
        "overall": output.overall,
        "per_lift": output.per_lift,
        "endurance": output.endurance,
        "legs_structural": output.legs_structural,
        "explanations": output.explanations,
    }


@protected.get("/sessions/recent")
def recent_sessions(
    athlete_id: int = Query(..., gt=0),
    days: int = Query(7, ge=1, le=365),
    db: Session = Depends(get_db),
):
    end_date = date.today()
    sessions = EngineOrchestrator(db).get_recent_sessions(athlete_id, end_date - timedelta(days=days), end_date)
    return {
        "strength": [
            {
                "id": item.id,
                "lift": item.lift.value,
                "start_time": item.start_time,
                "tonnage": item.tonnage,
                "avg_intensity": item.avg_intensity,
            }
            for item in sessions["strength"]
        ],
        "endurance": [
            {
                "id": item.id,
                "sport": item.sport.value,
                "start_time": item.start_time,
                "duration_minutes": item.duration_minutes,
                "intensity_type": item.intensity_type,
                "u_E_Z2": item.u_E_Z2,
                "u_E_HIIT": item.u_E_HIIT,
                "signal_source": (item.raw_data or {}).get("signal_source", "summary"),
            }
            for item in sessions["endurance"]
        ],
    }


@protected.post("/admin/update-day/{athlete_id}", dependencies=[Security(verify_admin_api_key)])
def update_day_state(
    athlete_id: int,
    date_str: Optional[str] = None,
    db: Session = Depends(get_db),
):
    try:
        target_date = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date") from exc
    state = DayUpdateService(db).update_day_state(athlete_id, target_date)
    return {
        "status": "updated",
        "athlete_id": athlete_id,
        "date": target_date.isoformat(),
        "D_sys": state.D_sys,
        "R_mito": state.R_mito,
        "E_fat": state.E_fat,
        "T_legs": state.T_legs,
    }


@protected.get("/performance/report")
def performance_report(
    athlete_id: int = Query(..., gt=0),
    days: int = Query(28, ge=7, le=365),
    force_recompute: bool = False,
    db: Session = Depends(get_db),
):
    return get_or_compute_performance_report(db, athlete_id, days=days, force_recompute=force_recompute).to_dict()


@protected.post("/performance/compute/{athlete_id}", dependencies=[Security(verify_admin_api_key)])
def compute_performance(athlete_id: int, days: int = Query(28, ge=7, le=365), db: Session = Depends(get_db)):
    report = compute_and_store_performance_report(db, athlete_id, days=days)
    return {"status": "computed", "athlete_id": athlete_id, "report": report.to_dict()}


class EnduranceProfileRequest(BaseModel):
    threshold_power_w: Optional[float] = Field(None, gt=0, le=3000)


@protected.put("/endurance/profile/{athlete_id}/{sport}")
def set_endurance_profile(
    athlete_id: int,
    sport: EnduranceSport,
    request: EnduranceProfileRequest,
    db: Session = Depends(get_db),
):
    row = db.query(models.SystemParameters).filter(models.SystemParameters.athlete_id == athlete_id).first()
    if row is None:
        row = models.SystemParameters(athlete_id=athlete_id, params={})
        db.add(row)
    params = dict(row.params or {})
    endurance = dict(params.get("endurance", {}))
    sport_params = dict(endurance.get(sport.value, {}))
    sport_params["threshold_power_w"] = request.threshold_power_w
    endurance[sport.value] = sport_params
    params["endurance"] = endurance
    row.params = params
    db.commit()
    return {"athlete_id": athlete_id, "sport": sport.value, **sport_params}


class CapacityInitRequest(BaseModel):
    athlete_id: int = Field(..., gt=0)
    lift: LiftType
    input_type: str
    input_load_kg: Optional[float] = None
    input_reps: Optional[int] = None
    input_rpe: Optional[float] = None


@protected.post("/strength/capacity/init")
def initialize_capacity(request: CapacityInitRequest, overwrite: bool = False, db: Session = Depends(get_db)):
    try:
        profile = CapacityProfileService(db).initialize_from_input(
            request.athlete_id,
            request.lift,
            request.input_type,
            request.input_load_kg,
            request.input_reps,
            request.input_rpe,
            overwrite,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "athlete_id": profile.athlete_id,
        "lift": profile.lift.value,
        "anchor_capacity": profile.anchor_capacity,
        "model_capacity": profile.model_capacity,
        "confidence": profile.confidence,
    }


@protected.get("/strength/capacity/{athlete_id}")
def capacities(athlete_id: int, db: Session = Depends(get_db)):
    profiles = CapacityProfileService(db).get_all_profiles(athlete_id)
    return {
        "athlete_id": athlete_id,
        "profiles": [
            {
                "lift": item.lift.value,
                "anchor_capacity": item.anchor_capacity,
                "model_capacity": item.model_capacity,
                "confidence": item.confidence,
                "provisional_breakthrough_count": item.provisional_breakthrough_count,
            }
            for item in profiles
        ],
    }


@protected.post("/capacity/process-set")
def process_capacity_set(
    athlete_id: int,
    lift: LiftType,
    load_kg: float,
    reps: int,
    rpe: Optional[float] = None,
    velocity_loss: Optional[float] = None,
    observed_velocity: Optional[float] = None,
    db: Session = Depends(get_db),
):
    return CapacityProfileService(db).process_quality_set(
        athlete_id, lift, load_kg, reps, rpe, velocity_loss, observed_velocity
    )


@protected.post("/capacity/confirm-breakthrough")
def confirm_breakthrough(athlete_id: int, lift: LiftType, db: Session = Depends(get_db)):
    result = CapacityProfileService(db).confirm_provisional_breakthrough(athlete_id, lift)
    if not result:
        raise HTTPException(status_code=400, detail="No provisional breakthrough to confirm")
    return result


@protected.post("/capacity/reset-provisional")
def reset_breakthrough(athlete_id: int, lift: LiftType, db: Session = Depends(get_db)):
    if not CapacityProfileService(db).reset_provisional_breakthroughs(athlete_id, lift):
        raise HTTPException(status_code=404, detail="Capacity profile not found")
    return {"status": "reset", "athlete_id": athlete_id, "lift": lift.value}


@protected.post("/goals/create")
def create_goal(goal_data: dict, db: Session = Depends(get_db)):
    goal = GoalService.create_goal(db, GoalConfig.from_dict(goal_data))
    return {"goal_id": goal.goal_id, "athlete_id": goal.athlete_id, "target_date": goal.target_date}


@protected.post("/goals/activate/{goal_id}")
def activate_goal(goal_id: str, db: Session = Depends(get_db)):
    goal = GoalService.activate_goal(db, goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"status": "activated", "goal_id": goal.goal_id}


@protected.get("/goals/active")
def active_goal(athlete_id: int, db: Session = Depends(get_db)):
    goal = GoalService.get_active_goal(db, athlete_id)
    if not goal:
        return {"has_goal": False}
    context = get_goal_context_for_program(db, athlete_id)
    return {
        "has_goal": True,
        "goal_id": goal.goal_id,
        "goal_type": goal.goal_type,
        "target_date": goal.target_date,
        "priority": goal.priority,
        "block_type": context.get("block_type") if context else None,
        "microcycle_targets": context.get("microcycle_targets") if context else None,
    }


@protected.get("/goals/list")
def list_goals(athlete_id: int, include_inactive: bool = False, db: Session = Depends(get_db)):
    return {"goals": [item.goal_json for item in GoalService.get_all_goals(db, athlete_id, include_inactive)]}


@protected.delete("/goals/{goal_id}")
def delete_goal(goal_id: str, db: Session = Depends(get_db)):
    if not GoalService.delete_goal(db, goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"status": "deleted", "goal_id": goal_id}


@protected.get("/integrations/strava", response_class=HTMLResponse)
def strava_status(athlete_id: int, db: Session = Depends(get_db)):
    service = StravaService(db)
    connection = service.get_connection(athlete_id)
    if not service.is_configured():
        return HTMLResponse("<h1>Strava Integration</h1><p>OAuth is not configured.</p>")
    if connection and connection.is_active:
        name = escape(connection.strava_athlete_name or connection.strava_athlete_id)
        last_sync = escape(connection.last_sync_at.isoformat() if connection.last_sync_at else "Never")
        error = escape(connection.last_sync_error or "")
        return HTMLResponse(
            f"<h1>✅ Connected</h1><p>{name}</p><p>Last sync: {last_sync}</p><p>{error}</p>"
            f"<a href='/integrations/strava/login?athlete_id={athlete_id}'>Reconnect</a>"
            f"<form method='post' action='/integrations/strava/disconnect?athlete_id={athlete_id}'>"
            "<button type='submit'>Disconnect</button></form>"
        )
    return HTMLResponse(
        f"<h1>❌ Not Connected</h1><a href='/integrations/strava/login?athlete_id={athlete_id}'>Connect with Strava</a>"
    )


@protected.get("/integrations/strava/login")
def strava_login(athlete_id: int, db: Session = Depends(get_db)):
    service = StravaService(db)
    if not service.is_configured():
        raise HTTPException(status_code=503, detail="Strava OAuth not configured")
    return RedirectResponse(service.build_authorize_url(athlete_id))


@app.get("/integrations/strava/callback")
def strava_callback(code: str, state: str, scope: str = "", db: Session = Depends(get_db)):
    service = StravaService(db)
    try:
        athlete_id = service.verify_state_token(state)
        token_response = service.exchange_code_for_token(code)
        service.create_or_update_connection(athlete_id, token_response, scope)
    except StravaAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StravaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse(f"/integrations/strava?athlete_id={athlete_id}")


@protected.post("/integrations/strava/sync")
def strava_sync(athlete_id: int, days_back: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    try:
        result = StravaService(db).sync_activities(athlete_id, days_back=days_back)
        return {"status": "success", "athlete_id": athlete_id, **result}
    except StravaAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except StravaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@protected.post("/integrations/strava/disconnect")
def strava_disconnect(athlete_id: int, db: Session = Depends(get_db)):
    if not StravaService(db).disconnect(athlete_id):
        raise HTTPException(status_code=404, detail="No Strava connection found")
    return {"status": "disconnected", "athlete_id": athlete_id}


@protected.get("/legacy/status")
def legacy_status():
    return {
        "use_legacy_model": settings.use_legacy_model,
        "primary_engine": "modular_engines",
        "engine_path": "rep_engine -> day_engine -> performance_engine",
        "legacy_available_for_comparison": True,
    }


app.include_router(protected)
