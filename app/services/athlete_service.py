"""Canonical athlete persistence service."""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app import models as db_models
from app.config import settings
from app.services.capacity_service import LIFT_SPECIFIC_DEFAULTS
from app.types import LiftType


DEFAULT_VELOCITY_PROFILES = {
    LiftType.SQUAT: {"a": 0.55, "b": 0.0032},
    LiftType.BENCH: {"a": 0.60, "b": 0.0028},
    LiftType.DEADLIFT: {"a": 0.50, "b": 0.0030},
    LiftType.PRESS: {"a": 0.58, "b": 0.0025},
    LiftType.POWER_CLEAN: {"a": 0.75, "b": 0.0040},
    LiftType.CLEAN: {"a": 0.75, "b": 0.0040},
    LiftType.OTHER: {"a": 0.55, "b": 0.0030},
}


class AthleteService:
    """Create and retrieve athletes within a stable ownership namespace."""

    @staticmethod
    def create_athlete(
        db: Session,
        name: str,
        *,
        owner_subject: Optional[str] = None,
    ) -> db_models.Athlete:
        owner = (owner_subject or settings.default_owner_subject).strip()
        if not owner:
            raise ValueError("owner_subject cannot be empty")

        athlete = db_models.Athlete(name=name.strip(), owner_subject=owner)
        db.add(athlete)
        try:
            db.flush()

            for lift in LiftType:
                profile_params = DEFAULT_VELOCITY_PROFILES[lift]
                db.add(
                    db_models.LiftProfile(
                        athlete_id=athlete.id,
                        lift=lift,
                        a=profile_params["a"],
                        b=profile_params["b"],
                    )
                )

            today = date.today().isoformat()
            db.add(
                db_models.DayState(
                    athlete_id=athlete.id,
                    date=today,
                    D_sys=0.0,
                    R_mito=0.0,
                    E_fat=0.0,
                    T_legs=0.0,
                )
            )
            for lift in LiftType:
                db.add(
                    db_models.LiftDayState(
                        athlete_id=athlete.id,
                        lift=lift,
                        date=today,
                        D_l=0.0,
                        F_l=1.0,
                        C_l=float(LIFT_SPECIFIC_DEFAULTS.get(lift, 100.0)),
                    )
                )

            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(athlete)
        return athlete

    @staticmethod
    def get_athlete(
        db: Session,
        athlete_id: int,
        *,
        owner_subject: Optional[str] = None,
    ) -> Optional[db_models.Athlete]:
        query = db.query(db_models.Athlete).filter(db_models.Athlete.id == athlete_id)
        if owner_subject is not None:
            query = query.filter(db_models.Athlete.owner_subject == owner_subject)
        return query.first()

    @staticmethod
    def list_athletes(
        db: Session,
        *,
        owner_subject: Optional[str] = None,
    ) -> list[db_models.Athlete]:
        query = db.query(db_models.Athlete)
        if owner_subject is not None:
            query = query.filter(db_models.Athlete.owner_subject == owner_subject)
        return query.order_by(db_models.Athlete.created_at, db_models.Athlete.id).all()
