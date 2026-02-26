"""
FastAPI application - main entry point
"""
from contextlib import asynccontextmanager
from datetime import date
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
