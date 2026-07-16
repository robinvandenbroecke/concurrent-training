"""Slot-aware workout-plan persistence."""
from __future__ import annotations

from datetime import date
import re
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app import models


_SLOT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,49}$")


def normalize_plan_slot(slot: Optional[str]) -> str:
    normalized = (slot or "primary").strip().lower().replace(" ", "_")
    if not _SLOT_PATTERN.fullmatch(normalized):
        raise ValueError(
            "slot must be 1-50 characters and contain only lowercase letters, "
            "numbers, underscores or hyphens"
        )
    return normalized


class WorkoutPlanService:
    """Create or replace a logical plan slot without clobbering other sessions."""

    @staticmethod
    def upsert_plan(
        db: Session,
        *,
        athlete_id: int,
        plan_date: date | str,
        mode: str,
        plan_json: Dict,
        slot: Optional[str] = None,
        readiness_snapshot: Optional[Dict] = None,
        is_adapted: bool = False,
        original_plan_id: Optional[int] = None,
    ) -> models.WorkoutPlan:
        date_text = plan_date.isoformat() if isinstance(plan_date, date) else str(plan_date)
        normalized_slot = normalize_plan_slot(slot)
        row = db.query(models.WorkoutPlan).filter(
            models.WorkoutPlan.athlete_id == athlete_id,
            models.WorkoutPlan.date == date_text,
            models.WorkoutPlan.slot == normalized_slot,
        ).first()
        if row is None:
            row = models.WorkoutPlan(
                athlete_id=athlete_id,
                date=date_text,
                slot=normalized_slot,
                mode=mode,
                plan_json=plan_json,
            )
            db.add(row)

        row.mode = mode
        row.plan_json = plan_json
        row.readiness_snapshot = readiness_snapshot or {}
        row.is_adapted = is_adapted
        row.original_plan_id = original_plan_id
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(row)
        return row

    @staticmethod
    def list_for_date(
        db: Session,
        *,
        athlete_id: int,
        plan_date: date | str,
    ) -> list[models.WorkoutPlan]:
        date_text = plan_date.isoformat() if isinstance(plan_date, date) else str(plan_date)
        return db.query(models.WorkoutPlan).filter(
            models.WorkoutPlan.athlete_id == athlete_id,
            models.WorkoutPlan.date == date_text,
        ).order_by(models.WorkoutPlan.slot, models.WorkoutPlan.id).all()
