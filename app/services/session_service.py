"""Canonical session ingestion with timestamp preservation and same-day rebuilds."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app import models as db_models
from app import schemas
from app.domain.day_engine import (
    DailyImpulses,
    DayState,
    EnduranceImpulses,
    PerLiftState,
    StrengthImpulses,
    decay_day_state_to_date,
    update_day_state,
)
from app.domain.endurance_engine import compute_endurance_load
from app.services.capacity_service import get_lift_capacity_estimate
from app.services.engine_orchestrator import EngineOrchestrator
from app.types import EnduranceSport, LiftType


class SessionService:
    """Persist sessions through the orchestrator and rebuild each day once.

    The original orchestrator updates state immediately for backward
    compatibility. This service then deterministically rebuilds the entire day
    from the preceding state and all sessions on that date, preventing repeated
    application of one-day decay when multiple sessions occur on the same day.
    """

    def __init__(self, db: Session):
        self.db = db
        self.orchestrator = EngineOrchestrator(db)

    @staticmethod
    def _set_to_dict(set_data: schemas.SetData) -> Dict:
        velocities = [float(rep.velocity) for rep in set_data.reps if rep.velocity is not None]
        rest_sec = set_data.rest_before_sec
        if rest_sec is None and set_data.reps:
            rest_sec = set_data.reps[0].rest_before
        return {
            "load_kg": float(set_data.weight),
            "reps": len(set_data.reps),
            "velocities": velocities,
            "rest_sec": rest_sec,
            "set_end_rpe": set_data.set_end_rpe,
        }

    def ingest_strength_session(
        self,
        athlete_id: int,
        lift: LiftType,
        start_time: datetime,
        sets_data: List[schemas.SetData],
        end_time: Optional[datetime] = None,
    ) -> db_models.StrengthSession:
        payload = [self._set_to_dict(item) for item in sets_data]
        rpes = [item.set_end_rpe for item in sets_data if item.set_end_rpe is not None]
        session, _, _ = self.orchestrator.ingest_strength_session(
            athlete_id=athlete_id,
            lift=lift,
            session_date=start_time.date(),
            sets_data=payload,
            vbt_available=any(item["velocities"] for item in payload),
            optional_rpe=max(rpes) if rpes else None,
        )
        session.start_time = start_time
        session.end_time = end_time
        raw = dict(session.raw_data or {})
        raw["sets"] = payload
        raw["source"] = "api"
        session.raw_data = raw
        self.db.flush()
        self._rebuild_day(athlete_id, start_time.date())
        self.db.commit()
        self.db.refresh(session)
        return session

    def ingest_strength_workout(self, workout: schemas.StrengthWorkoutCreate) -> List[db_models.StrengthSession]:
        """Ingest a multi-lift workout in performed order.

        Exercise records remain queryable through the existing table while one
        final day rebuild aggregates all lifts without extra daily decay.
        """
        sessions: List[db_models.StrengthSession] = []
        for index, exercise in enumerate(workout.exercises):
            # Preserve ordering even when exercises share the same wall-clock
            # timestamp. The day model is rebuilt after each insert and finally
            # once more after the complete workout.
            exercise_time = workout.start_time + timedelta(seconds=index)
            sessions.append(self.ingest_strength_session(
                athlete_id=workout.athlete_id,
                lift=exercise.lift,
                start_time=exercise_time,
                end_time=workout.end_time,
                sets_data=exercise.sets,
            ))
        self._rebuild_day(workout.athlete_id, workout.start_time.date())
        self.db.commit()
        return sessions

    def ingest_endurance_session(
        self,
        athlete_id: int,
        sport: EnduranceSport,
        start_time: datetime,
        duration_minutes: float,
        intensity_type: str,
        *,
        end_time: Optional[datetime] = None,
        power_data: Optional[List[Dict]] = None,
        average_power_w: Optional[float] = None,
        normalized_power_w: Optional[float] = None,
        threshold_power_w: Optional[float] = None,
        average_heartrate: Optional[float] = None,
        rpe: Optional[float] = None,
        source: str = "api",
        external_id: Optional[str] = None,
    ) -> db_models.EnduranceSession:
        load = compute_endurance_load(
            sport=sport.value,
            duration_minutes=duration_minutes,
            declared_intensity=intensity_type,
            power_data=power_data,
            average_power_w=average_power_w,
            normalized_power_w=normalized_power_w,
            threshold_power_w=threshold_power_w,
        )
        session, _, _ = self.orchestrator.ingest_endurance_session(
            athlete_id=athlete_id,
            session_date=start_time.date(),
            sport=sport,
            duration_minutes=duration_minutes,
            intensity_type=load.intensity_type,
            power_data=power_data,
        )
        session.start_time = start_time
        if hasattr(session, "end_time"):
            session.end_time = end_time
        session.intensity_type = load.intensity_type
        session.u_E_Z2 = load.u_z2
        session.u_E_HIIT = load.u_hiit
        raw = dict(session.raw_data or {})
        raw.update({
            "source": source,
            "external_id": external_id,
            "signal_source": load.signal_source,
            "power_data": power_data,
            "average_power_w": load.average_power_w,
            "normalized_power_w": load.normalized_power_w,
            "threshold_power_w": load.threshold_power_w,
            "intensity_factor": load.intensity_factor,
            "average_heartrate": average_heartrate,
            "rpe": rpe,
            "impulses": {"u_E_Z2": load.u_z2, "u_E_HIIT": load.u_hiit},
        })
        session.raw_data = raw
        self.db.flush()
        self._rebuild_day(athlete_id, start_time.date())
        self.db.commit()
        self.db.refresh(session)
        return session

    def _load_previous_state(self, athlete_id: int, target_date: date) -> DayState:
        previous_db = self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == athlete_id,
            db_models.DayState.date < target_date.isoformat(),
        ).order_by(db_models.DayState.date.desc()).first()
        previous_day = target_date - timedelta(days=1)
        if previous_db is None:
            per_lift = {}
            for lift in LiftType:
                capacity, _ = get_lift_capacity_estimate(self.db, athlete_id, lift, previous_day)
                per_lift[lift.value] = PerLiftState(D_l=0.0, F_l=1.0, C_l=capacity)
            return DayState(
                date=previous_day,
                per_lift=per_lift,
                D_sys=0.0,
                R_mito=0.0,
                E_fat=0.0,
                T_legs=0.0,
            )

        lift_rows = self.db.query(db_models.LiftDayState).filter(
            db_models.LiftDayState.athlete_id == athlete_id,
            db_models.LiftDayState.date == previous_db.date,
        ).all()
        state = DayState(
            date=date.fromisoformat(previous_db.date),
            per_lift={
                row.lift.value: PerLiftState(D_l=row.D_l, F_l=row.F_l, C_l=row.C_l)
                for row in lift_rows
            },
            D_sys=previous_db.D_sys,
            R_mito=previous_db.R_mito,
            E_fat=previous_db.E_fat,
            T_legs=getattr(previous_db, "T_legs", 0.0),
        )
        return decay_day_state_to_date(state, previous_day, self.orchestrator.day_params)

    def _rebuild_day(self, athlete_id: int, target_date: date) -> DayState:
        start = datetime.combine(target_date, time.min)
        end = datetime.combine(target_date + timedelta(days=1), time.min)
        strength_sessions = self.db.query(db_models.StrengthSession).filter(
            db_models.StrengthSession.athlete_id == athlete_id,
            db_models.StrengthSession.start_time >= start,
            db_models.StrengthSession.start_time < end,
        ).order_by(db_models.StrengthSession.start_time).all()
        endurance_sessions = self.db.query(db_models.EnduranceSession).filter(
            db_models.EnduranceSession.athlete_id == athlete_id,
            db_models.EnduranceSession.start_time >= start,
            db_models.EnduranceSession.start_time < end,
        ).order_by(db_models.EnduranceSession.start_time).all()

        per_lift: Dict[str, float] = {}
        u_sys = u_legs = u_met = u_legs_hi = 0.0
        set_impulses = []
        for session in strength_sessions:
            sets = (session.raw_data or {}).get("sets", [])
            impulse = self.orchestrator._compute_strength_impulses(
                session.lift.value,
                sets,
                rep_output=None,
                athlete_id=athlete_id,
                session_date=target_date,
            )
            for lift, value in impulse.per_lift.items():
                per_lift[lift] = per_lift.get(lift, 0.0) + value
            u_sys += impulse.u_sys
            u_legs += impulse.u_legs
            u_met += impulse.u_met
            u_legs_hi += impulse.u_legs_high_intensity
            set_impulses.extend(impulse.sets)

        u_z2 = sum(float(item.u_E_Z2 or 0.0) for item in endurance_sessions)
        u_hiit = sum(float(item.u_E_HIIT or 0.0) for item in endurance_sessions)
        hiit_modes = [item.sport.value for item in endurance_sessions if (item.u_E_HIIT or 0.0) > 0]
        if hiit_modes:
            mode = max(hiit_modes, key=self.orchestrator.day_params.get_mode_factor)
        elif endurance_sessions:
            mode = endurance_sessions[-1].sport.value
        else:
            mode = EnduranceSport.CYCLING.value

        base = self._load_previous_state(athlete_id, target_date)
        updated = update_day_state(
            base,
            DailyImpulses(
                strength=StrengthImpulses(
                    per_lift=per_lift,
                    u_sys=u_sys,
                    u_legs=u_legs,
                    u_met=u_met,
                    u_legs_high_intensity=u_legs_hi,
                    sets=set_impulses,
                ),
                endurance=EnduranceImpulses(
                    u_E_Z2=u_z2,
                    u_E_HIIT=u_hiit,
                    u_E_total=u_z2 + u_hiit,
                    mode=mode,
                    has_HIIT=u_hiit > 0,
                    has_Z2=u_z2 > 0,
                ),
                date=target_date,
            ),
            self.orchestrator.day_params,
        )
        updated.date = target_date
        self.orchestrator._persist_day_state(athlete_id, target_date, updated)
        self.db.flush()
        return updated
