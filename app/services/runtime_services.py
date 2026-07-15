"""Canonical runtime services backed by the hardened engines.

The legacy service module is retained only for explicit comparison endpoints.
All normal readiness, trend, autoregulation, and daily carry-over operations
must use this module.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app import models as db_models
from app import schemas
from app.domain.day_engine import compute_readiness
from app.domain.rep_engine import LiftVelocityProfile, RepEngineParams, SessionInput, SetInput, simulate_strength_session
from app.services.capacity_service import get_lift_capacity_estimate
from app.services.engine_orchestrator import EngineOrchestrator
from app.types import LiftType


class DayUpdateService:
    """Advance the canonical state to a requested day without replaying sessions."""

    def __init__(self, db: Session):
        self.db = db
        self.orchestrator = EngineOrchestrator(db)

    def update_day_state(self, athlete_id: int, target_date: Optional[date] = None):
        target_date = target_date or date.today()
        state = self.orchestrator.get_day_state_with_carryover(athlete_id, target_date)
        if state is None:
            state = self.orchestrator._get_or_create_day_state(athlete_id, target_date)
        self.orchestrator._persist_day_state(athlete_id, target_date, state)
        self.db.commit()
        return self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == athlete_id,
            db_models.DayState.date == target_date.isoformat(),
        ).one()


class ReadinessService:
    """Read canonical day-engine readiness and trend data."""

    def __init__(self, db: Session):
        self.db = db
        self.orchestrator = EngineOrchestrator(db)

    def get_readiness(self, athlete_id: int, target_date: Optional[date] = None) -> schemas.ReadinessResponse:
        target_date = target_date or date.today()
        state = self.orchestrator.get_day_state_with_carryover(athlete_id, target_date)
        if state is None:
            return schemas.ReadinessResponse(
                athlete_id=athlete_id,
                date=target_date.isoformat(),
                overall=100.0,
                per_lift={lift.value: 100.0 for lift in LiftType},
                endurance=100.0,
                explanations=["No training data yet"],
            )
        output = compute_readiness(state, self.orchestrator.day_params)
        return schemas.ReadinessResponse(
            athlete_id=athlete_id,
            date=target_date.isoformat(),
            overall=round(output.overall * 100.0, 1),
            per_lift={lift: round(value * 100.0, 1) for lift, value in output.per_lift.items()},
            endurance=round(output.endurance * 100.0, 1),
            explanations=output.explanations,
        )

    def get_lift_trends(self, athlete_id: int, lift: LiftType, days: int = 30) -> schemas.LiftTrendResponse:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        lift_states = self.db.query(db_models.LiftDayState).filter(
            db_models.LiftDayState.athlete_id == athlete_id,
            db_models.LiftDayState.lift == lift,
            db_models.LiftDayState.date >= start_date.isoformat(),
            db_models.LiftDayState.date <= end_date.isoformat(),
        ).order_by(db_models.LiftDayState.date).all()
        system_by_date = {
            row.date: row for row in self.db.query(db_models.DayState).filter(
                db_models.DayState.athlete_id == athlete_id,
                db_models.DayState.date >= start_date.isoformat(),
                db_models.DayState.date <= end_date.isoformat(),
            ).all()
        }
        data = []
        for row in lift_states:
            system = system_by_date.get(row.date)
            d_sys = system.D_sys if system else 0.0
            readiness = max(0.0, min(1.0, 1.0 - row.D_l - self.orchestrator.day_params.w_sys * d_sys))
            data.append(schemas.LiftTrendPoint(
                date=row.date,
                D_l=row.D_l,
                F_l=row.F_l,
                C_l=row.C_l,
                readiness=round(readiness * 100.0, 1),
            ))
        return schemas.LiftTrendResponse(athlete_id=athlete_id, lift=lift, days=days, data=data)

    def get_endurance_trends(self, athlete_id: int, days: int = 30) -> schemas.EnduranceTrendResponse:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        rows = self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == athlete_id,
            db_models.DayState.date >= start_date.isoformat(),
            db_models.DayState.date <= end_date.isoformat(),
        ).order_by(db_models.DayState.date).all()
        data = [
            schemas.EnduranceTrendPoint(
                date=row.date,
                R_mito=row.R_mito,
                E_fat=row.E_fat,
                readiness=round(max(0.0, min(1.0, 1.0 - row.E_fat)) * 100.0, 1),
            )
            for row in rows
        ]
        return schemas.EnduranceTrendResponse(athlete_id=athlete_id, days=days, data=data)


class AutoregulationService:
    """Generate deterministic next-set guidance from the hardened rep engine."""

    def __init__(self, db: Session):
        self.db = db
        self.orchestrator = EngineOrchestrator(db)

    def suggest(self, request: schemas.AutoregulateRequest) -> schemas.AutoregulateResponse:
        profile_db = self.db.query(db_models.LiftProfile).filter(
            db_models.LiftProfile.athlete_id == request.athlete_id,
            db_models.LiftProfile.lift == request.lift,
        ).first()
        if profile_db is None:
            raise ValueError(f"No profile for lift {request.lift}")

        state = self.orchestrator.get_day_state_with_carryover(request.athlete_id, date.today())
        if state is None:
            state = self.orchestrator._get_or_create_day_state(request.athlete_id, date.today())
        lift_name = request.lift.value
        lift_state = state.get_lift(lift_name)
        capacity, _ = get_lift_capacity_estimate(
            self.db, request.athlete_id, lift_name, date.today()
        )
        profile = LiftVelocityProfile(lift=lift_name, a=profile_db.a, b=abs(profile_db.b))
        recent = [float(v) for v in (request.recent_v_obs or []) if v and v > 0]
        set_input = SetInput(
            lift=lift_name,
            load_kg=request.current_weight,
            velocities=recent,
            rest_before_sec=None,
        )
        output = simulate_strength_session(SessionInput(
            sets=[set_input],
            profiles={lift_name: profile},
            init_A_local={lift_name: max(0.02, 1.0 - lift_state.D_l / 2.0)},
            init_A_sys=max(0.02, 1.0 - state.D_sys / 2.0),
            init_M=0.0,
            R_mito=state.R_mito,
            e1rm={lift_name: capacity},
            params=RepEngineParams(),
        ))
        v_ref = profile.v_ref(request.current_weight)
        predicted = v_ref * output.final_A_local.get(lift_name, 1.0) * output.final_A_sys * output.final_A_M
        current_vl = 0.0
        if len(recent) >= 2 and recent[0] > 0:
            current_vl = max(0.0, 100.0 * (1.0 - recent[-1] / recent[0]))

        continue_set = request.current_reps_done < request.planned_reps and current_vl <= request.vl_max
        load_change = 0.0
        messages = []
        if not continue_set:
            messages.append("Stop the set: planned reps or velocity-loss limit reached")
        elif predicted < request.target_v_low:
            load_change = -0.025
            messages.append("Predicted velocity below target; reduce load 2.5%")
        elif predicted > request.target_v_high and current_vl < 0.5 * request.vl_max:
            load_change = 0.025
            messages.append("Velocity high with low loss; increase load 2.5%")
        else:
            messages.append("Continue at the current load")

        rest_suggestion = None
        if current_vl > 0.75 * request.vl_max:
            rest_suggestion = "Extend rest before the next set"

        return schemas.AutoregulateResponse(
            continue_set=continue_set,
            load_change=load_change,
            rest_suggestion=rest_suggestion,
            exercise_switch=None,
            predicted_velocity=round(predicted, 3),
            current_vl=round(current_vl, 1),
            messages=messages,
        )
