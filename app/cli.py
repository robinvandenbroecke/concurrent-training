"""CLI for demo and administration"""
import sys
from datetime import datetime, timedelta
from typing import Optional

import typer
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base
from app.models import (
    Athlete, StrengthSession, EnduranceSession, LiftProfile,
    DayState, LiftDayState, LiftType, EnduranceSport
)
from app.domain.model import (
    ConcurrentTrainingModel, LiftProfile as DomainProfile,
    Autoregulator, RepLevelState
)
from app.services import (
    AthleteService, SessionService, DayUpdateService,
    ReadinessService, AutoregulationService
)
from app.schemas import SetData, RepData

app = typer.Typer(help="Concurrent Training CLI")


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.command()
def init():
    """Initialize database tables"""
    typer.echo("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    typer.echo("✓ Database initialized")


@app.command()
def create_athlete(name: str):
    """Create a new athlete with default profiles"""
    db = next(get_db())
    athlete = AthleteService.create_athlete(db, name)
    typer.echo(f"✓ Created athlete: {athlete.name} (ID: {athlete.id})")
    
    # Show profiles
    profiles = db.query(LiftProfile).filter(LiftProfile.athlete_id == athlete.id).all()
    typer.echo("\nDefault lift profiles:")
    for p in profiles:
        typer.echo(f"  {p.lift.value}: v = {p.a:.3f} - {p.b:.5f}*w")


@app.command()
def demo():
    """Create demo athlete and ingest sample sessions"""
    db = next(get_db())
    
    typer.echo("=== Concurrent Training Demo ===\n")
    
    # 1. Create athlete
    typer.echo("1. Creating demo athlete 'Test Athlete'...")
    athlete = AthleteService.create_athlete(db, "Test Athlete")
    typer.echo(f"   ✓ Athlete ID: {athlete.id}\n")
    
    # 2. Ingest strength session with VBT
    typer.echo("2. Ingesting strength session (Squat with VBT)...")
    
    sets_data = [
        SetData(
            weight=100.0,
            target_reps=5,
            reps=[
                RepData(weight=100.0, velocity=0.45, rep_num=1, rest_before=180),
                RepData(weight=100.0, velocity=0.42, rep_num=2, rest_before=3),
                RepData(weight=100.0, velocity=0.38, rep_num=3, rest_before=3),
                RepData(weight=100.0, velocity=0.35, rep_num=4, rest_before=3),
                RepData(weight=100.0, velocity=0.32, rep_num=5, rest_before=3),
            ]
        ),
        SetData(
            weight=100.0,
            target_reps=5,
            reps=[
                RepData(weight=100.0, velocity=0.40, rep_num=1, rest_before=240),
                RepData(weight=100.0, velocity=0.36, rep_num=2, rest_before=3),
                RepData(weight=100.0, velocity=0.33, rep_num=3, rest_before=3),
                RepData(weight=100.0, velocity=0.30, rep_num=4, rest_before=3),
            ]
        )
    ]
    
    session = SessionService(db).ingest_strength_session(
        athlete_id=athlete.id,
        lift=LiftType.SQUAT,
        start_time=datetime.now() - timedelta(hours=2),
        sets_data=sets_data
    )
    typer.echo(f"   ✓ Session ingested: {session.tonnage:.0f}kg tonnage")
    typer.echo(f"   ✓ {len(session.rep_level_log)} reps tracked\n")
    
    # 3. Ingest endurance session (Z2)
    typer.echo("3. Ingesting Z2 endurance session...")
    end_session = SessionService(db).ingest_endurance_session(
        athlete_id=athlete.id,
        sport=EnduranceSport.CYCLING,
        start_time=datetime.now() - timedelta(days=1, hours=3),
        duration_minutes=45.0,
        intensity_type="z2"
    )
    typer.echo(f"   ✓ Z2 session: {end_session.duration_minutes}min")
    typer.echo(f"   ✓ R_mito contribution: {end_session.u_E_Z2:.1f}\n")
    
    # 4. Ingest HIIT session
    typer.echo("4. Ingesting HIIT running session...")
    hiit_session = SessionService(db).ingest_endurance_session(
        athlete_id=athlete.id,
        sport=EnduranceSport.RUNNING,
        start_time=datetime.now() - timedelta(hours=14),
        duration_minutes=30.0,
        intensity_type="hiit"
    )
    typer.echo(f"   ✓ HIIT session: {hiit_session.duration_minutes}min")
    typer.echo(f"   ✓ Interference contribution: {hiit_session.u_E_HIIT:.1f}\n")
    
    # 5. Update day states
    typer.echo("5. Updating day states...")
    DayUpdateService(db).update_day_state(athlete.id)
    typer.echo("   ✓ Day state computed\n")
    
    # 6. Show readiness
    typer.echo("6. Current readiness scores:")
    readiness = ReadinessService(db).get_readiness(athlete.id)
    typer.echo(f"   Overall: {readiness.overall:.1f}%")
    typer.echo(f"   Endurance: {readiness.endurance:.1f}%")
    typer.echo("\n   Per lift:")
    for lift, score in readiness.per_lift.items():
        typer.echo(f"     {lift}: {score:.1f}%")
    
    typer.echo("\n   Explanations:")
    for exp in readiness.explanations:
        typer.echo(f"     • {exp}")
    
    # 7. Autoregulation demo
    typer.echo("\n7. Autoregulation suggestion for next squat set:")
    from app.schemas import AutoregulateRequest
    
    suggestion = AutoregulationService(db).suggest(
        AutoregulateRequest(
            athlete_id=athlete.id,
            lift=LiftType.SQUAT,
            current_weight=105.0,
            target_v_low=0.35,
            target_v_high=0.45,
            vl_max=20.0,
            planned_reps=5,
            current_reps_done=0
        )
    )
    
    typer.echo(f"   Predicted velocity: {suggestion.predicted_velocity:.3f} m/s")
    typer.echo(f"   Current VL: {suggestion.current_vl:.1f}%")
    typer.echo(f"   Continue: {suggestion.continue_set}")
    if suggestion.load_change != 0:
        typer.echo(f"   Load change: {suggestion.load_change*100:+.1f}%")
    if suggestion.rest_suggestion:
        typer.echo(f"   Rest: {suggestion.rest_suggestion}")
    if suggestion.messages:
        typer.echo(f"   Messages: {', '.join(suggestion.messages)}")
    
    typer.echo("\n=== Demo Complete ===")


@app.command()
def readiness(athlete_id: int):
    """Show current readiness for an athlete"""
    db = next(get_db())
    
    r = ReadinessService(db).get_readiness(athlete_id)
    
    typer.echo(f"Readiness for Athlete {athlete_id} ({r.date})")
    typer.echo(f"Overall: {r.overall:.1f}%")
    typer.echo(f"Endurance: {r.endurance:.1f}%\n")
    
    typer.echo("Per lift:")
    for lift, score in r.per_lift.items():
        typer.echo(f"  {lift:12s}: {score:5.1f}%")
    
    if r.explanations:
        typer.echo("\nFactors:")
        for exp in r.explanations:
            typer.echo(f"  • {exp}")


@app.command()
def update_day(athlete_id: int):
    """Manually trigger day state update"""
    db = next(get_db())
    
    state = DayUpdateService(db).update_day_state(athlete_id)
    
    typer.echo(f"Updated day state for athlete {athlete_id}")
    typer.echo(f"  D_sys: {state.D_sys:.3f}")
    typer.echo(f"  R_mito: {state.R_mito:.3f}")
    typer.echo(f"  E_fat: {state.E_fat:.3f}")


if __name__ == "__main__":
    app()
