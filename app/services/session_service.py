"""Canonical session ingestion with timestamp preservation and same-day rebuilds."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

from sqlalchemy.exc import IntegrityError
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
from app.domain.rep_engine import LiftVelocityProfile, SessionInput, SetInput, simulate_strength_session
from app.services.capacity_profile_service import CapacityProfileService
from app.services.capacity_service import get_lift_capacity_estimate
from app.services.engine_orchestrator import EngineOrchestrator
from app.types import EnduranceSport, LiftType


class SessionService:
    """Canonical strength/endurance ingestion service.

    State for a calendar day is rebuilt from the preceding day and all stored
    sessions exactly once, preventing repeated daily decay when multiple
    sessions occur on the same date.
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
        rpes = [item["set_end_rpe"] for item in payload if item.get("set_end_rpe") is not None]
        optional_rpe = max(rpes) if rpes else None
        content_hash = self.orchestrator._compute_strength_content_hash(
            athlete_id, start_time.date(), lift.value, payload, optional_rpe
        )
        existing = self.orchestrator._check_existing_strength_session(athlete_id, content_hash)
        if existing is not None:
            return existing

        profile_db = self.db.query(db_models.LiftProfile).filter(
            db_models.LiftProfile.athlete_id == athlete_id,
            db_models.LiftProfile.lift == lift,
        ).first()
        if profile_db is None:
            raise ValueError(f"No profile found for {lift.value}")
        try:
            profile = LiftVelocityProfile(lift=lift.value, a=float(profile_db.a), b=abs(float(profile_db.b)))
        except ValueError:
            profile = LiftVelocityProfile.calibrated_profile(lift.value)
            profile_db.a, profile_db.b = profile.a, profile.b

        day_state = self.orchestrator._get_or_create_day_state(athlete_id, start_time.date())
        lift_state = day_state.get_lift(lift.value)
        capacity, capacity_source = get_lift_capacity_estimate(
            self.db, athlete_id, lift, start_time.date()
        )
        set_inputs = [
            SetInput(
                lift=lift.value,
                load_kg=item["load_kg"],
                velocities=item["velocities"],
                rest_before_sec=item.get("rest_sec") if index > 0 else None,
                set_end_rpe=item.get("set_end_rpe"),
            )
            for index, item in enumerate(payload)
        ]
        rep_output = simulate_strength_session(SessionInput(
            sets=set_inputs,
            profiles={lift.value: profile},
            init_A_local={lift.value: max(0.02, 1.0 - lift_state.D_l / 2.0)},
            init_A_sys=max(0.02, 1.0 - day_state.D_sys / 2.0),
            init_M=0.0,
            R_mito=day_state.R_mito,
            e1rm={lift.value: capacity},
            params=self.orchestrator.rep_params,
        ))

        total_tonnage = sum(item["load_kg"] * item["reps"] for item in payload)
        total_reps = sum(item["reps"] for item in payload)
        relative_intensity = (
            sum((item["load_kg"] / max(capacity, 1.0)) * item["reps"] for item in payload) / total_reps
            if total_reps else 0.0
        )
        session = db_models.StrengthSession(
            athlete_id=athlete_id,
            lift=lift,
            start_time=start_time,
            end_time=end_time,
            content_hash=content_hash,
            tonnage=total_tonnage,
            avg_intensity=relative_intensity,
            raw_data={
                "sets": payload,
                "source": "api",
                "capacity_estimate": capacity,
                "capacity_source": capacity_source,
                "final_A_local": rep_output.final_A_local,
                "final_A_sys": rep_output.final_A_sys,
                "final_A_M": rep_output.final_A_M,
            },
            rep_level_log=[
                {
                    "set_idx": set_index,
                    "rep_idx": rep_index,
                    "A_l": rep.A_l,
                    "A_sys": rep.A_sys,
                    "A_M": rep.A_M,
                    "v_pred_next": rep.v_pred_next,
                    "y": rep.y,
                    "y_phi": rep.y_phi,
                }
                for set_index, set_output in enumerate(rep_output.sets)
                for rep_index, rep in enumerate(set_output.reps)
            ],
        )
        self.db.add(session)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            existing = self.orchestrator._check_existing_strength_session(athlete_id, content_hash)
            if existing is not None:
                return existing
            raise

        self.orchestrator._compute_strength_performance_snapshot(
            athlete_id,
            lift,
            start_time.date(),
            payload,
            rep_output,
            any(item["velocities"] for item in payload),
        )
        self._rebuild_day(athlete_id, start_time.date())
        self.db.commit()

        # Capacity and breakthrough processing is part of normal ingestion rather
        # than a separate manual workflow.
        capacity_service = CapacityProfileService(self.db)
        for item in payload:
            velocities = item["velocities"]
            velocity_loss = None
            if len(velocities) >= 2 and velocities[0] > 0:
                velocity_loss = max(0.0, min(1.0, 1.0 - velocities[-1] / velocities[0]))
            capacity_service.process_quality_set(
                athlete_id=athlete_id,
                lift=lift,
                load_kg=item["load_kg"],
                reps=item["reps"],
                rpe=item.get("set_end_rpe"),
                velocity_loss=velocity_loss,
                observed_velocity=velocities[0] if velocities else None,
            )
        self.db.refresh(session)
        return session

    def ingest_strength_workout(self, workout: schemas.StrengthWorkoutCreate) -> List[db_models.StrengthSession]:
        sessions: List[db_models.StrengthSession] = []
        for index, exercise in enumerate(workout.exercises):
            sessions.append(self.ingest_strength_session(
                athlete_id=workout.athlete_id,
                lift=exercise.lift,
                start_time=workout.start_time + timedelta(seconds=index),
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
            return DayState(date=previous_day, per_lift=per_lift, D_sys=0.0, R_mito=0.0, E_fat=0.0, T_legs=0.0)

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
                session.lift.value, sets, rep_output=None, athlete_id=athlete_id, session_date=target_date
            )
            for lift_name, value in impulse.per_lift.items():
                per_lift[lift_name] = per_lift.get(lift_name, 0.0) + value
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
