"""Combined multi-lift workout ingestion.

A workout is simulated once in performed order so A_sys and A_M carry across
lifts. Existing per-lift session rows are retained for backwards-compatible
queries and trend analysis.
"""
from __future__ import annotations

from datetime import timedelta
import hashlib
from types import SimpleNamespace
from typing import Dict, List

from sqlalchemy.exc import IntegrityError

from app import models as db_models
from app import schemas
from app.domain.rep_engine import LiftVelocityProfile, SessionInput, SetInput
from app.services.capacity_profile_service import CapacityProfileService
from app.services.capacity_service import get_lift_capacity_estimate
import app.services.engine_orchestrator as engine_module


class CombinedWorkoutIngestor:
    def __init__(self, session_service):
        self.service = session_service
        self.db = session_service.db
        self.orchestrator = session_service.orchestrator

    def ingest(self, workout: schemas.StrengthWorkoutCreate) -> List[db_models.StrengthSession]:
        day_state = self.orchestrator._get_or_create_day_state(
            workout.athlete_id, workout.start_time.date()
        )
        profiles: Dict[str, LiftVelocityProfile] = {}
        capacities: Dict[str, float] = {}
        capacity_sources: Dict[str, str] = {}
        payloads: List[List[Dict]] = []
        combined_sets: List[SetInput] = []
        ranges = []

        for exercise in workout.exercises:
            payload = [self.service._set_to_dict(item) for item in exercise.sets]
            if not payload:
                raise ValueError(f"{exercise.lift.value} has no performed sets")
            payloads.append(payload)
            profile_db = self.db.query(db_models.LiftProfile).filter(
                db_models.LiftProfile.athlete_id == workout.athlete_id,
                db_models.LiftProfile.lift == exercise.lift,
            ).first()
            if profile_db is None:
                raise ValueError(f"No profile found for {exercise.lift.value}")
            try:
                profile = LiftVelocityProfile(
                    lift=exercise.lift.value,
                    a=float(profile_db.a),
                    b=abs(float(profile_db.b)),
                )
            except ValueError:
                profile = LiftVelocityProfile.calibrated_profile(exercise.lift.value)
                profile_db.a, profile_db.b = profile.a, profile.b
            profiles[exercise.lift.value] = profile
            capacity, source = get_lift_capacity_estimate(
                self.db, workout.athlete_id, exercise.lift, workout.start_time.date()
            )
            capacities[exercise.lift.value] = capacity
            capacity_sources[exercise.lift.value] = source

            start_index = len(combined_sets)
            for item in payload:
                combined_sets.append(SetInput(
                    lift=exercise.lift.value,
                    load_kg=item["load_kg"],
                    velocities=item["velocities"],
                    rest_before_sec=item.get("rest_sec") if combined_sets else None,
                    set_end_rpe=item.get("set_end_rpe"),
                ))
            ranges.append((start_index, len(combined_sets)))

        initial_local = {
            lift: max(0.02, 1.0 - day_state.get_lift(lift).D_l / 2.0)
            for lift in profiles
        }
        output = engine_module.simulate_strength_session(SessionInput(
            sets=combined_sets,
            profiles=profiles,
            init_A_local=initial_local,
            init_A_sys=max(0.02, 1.0 - day_state.D_sys / 2.0),
            init_M=0.0,
            R_mito=day_state.R_mito,
            e1rm=capacities,
            params=self.orchestrator.rep_params,
        ))

        sessions: List[db_models.StrengthSession] = []
        running_local = dict(initial_local)
        running_sys = max(0.02, 1.0 - day_state.D_sys / 2.0)
        running_met = 1.0
        capacity_service = CapacityProfileService(self.db)

        for exercise_index, (exercise, payload, index_range) in enumerate(
            zip(workout.exercises, payloads, ranges)
        ):
            first, last = index_range
            exercise_sets = output.sets[first:last]
            for set_output in exercise_sets:
                if set_output.reps:
                    final_rep = set_output.reps[-1]
                    running_local[exercise.lift.value] = final_rep.A_l
                    running_sys = final_rep.A_sys
                    running_met = final_rep.A_M

            rpes = [item.get("set_end_rpe") for item in payload if item.get("set_end_rpe") is not None]
            base_hash = self.orchestrator._compute_strength_content_hash(
                workout.athlete_id,
                workout.start_time.date(),
                exercise.lift.value,
                payload,
                max(rpes) if rpes else None,
            )
            content_hash = hashlib.sha256(
                f"workout:{base_hash}:{workout.start_time.isoformat()}:{exercise_index}".encode()
            ).hexdigest()
            existing = self.orchestrator._check_existing_strength_session(
                workout.athlete_id, content_hash
            )
            if existing is not None:
                sessions.append(existing)
                continue

            total_tonnage = sum(item["load_kg"] * item["reps"] for item in payload)
            total_reps = sum(item["reps"] for item in payload)
            capacity = capacities[exercise.lift.value]
            relative_intensity = (
                sum((item["load_kg"] / max(capacity, 1.0)) * item["reps"] for item in payload)
                / total_reps
                if total_reps else 0.0
            )
            exercise_output = SimpleNamespace(
                sets=exercise_sets,
                final_A_local=dict(running_local),
                final_A_sys=running_sys,
                final_A_M=running_met,
            )
            session = db_models.StrengthSession(
                athlete_id=workout.athlete_id,
                lift=exercise.lift,
                start_time=workout.start_time + timedelta(seconds=exercise_index),
                end_time=workout.end_time,
                content_hash=content_hash,
                tonnage=total_tonnage,
                avg_intensity=relative_intensity,
                raw_data={
                    "sets": payload,
                    "source": "multi_lift_workout",
                    "workout_start_time": workout.start_time.isoformat(),
                    "exercise_index": exercise_index,
                    "capacity_estimate": capacity,
                    "capacity_source": capacity_sources[exercise.lift.value],
                    "final_A_local": dict(running_local),
                    "final_A_sys": running_sys,
                    "final_A_M": running_met,
                },
                rep_level_log=[
                    {
                        "set_idx": local_set_index,
                        "rep_idx": rep_index,
                        "A_l": rep.A_l,
                        "A_sys": rep.A_sys,
                        "A_M": rep.A_M,
                        "v_pred_next": rep.v_pred_next,
                        "y": getattr(rep, "y", None),
                        "y_phi": getattr(rep, "y_phi", None),
                    }
                    for local_set_index, set_output in enumerate(exercise_sets)
                    for rep_index, rep in enumerate(set_output.reps)
                ],
            )
            self.db.add(session)
            try:
                self.db.flush()
            except IntegrityError:
                self.db.rollback()
                existing = self.orchestrator._check_existing_strength_session(
                    workout.athlete_id, content_hash
                )
                if existing is None:
                    raise
                sessions.append(existing)
                continue

            self.orchestrator._compute_strength_performance_snapshot(
                workout.athlete_id,
                exercise.lift,
                workout.start_time.date(),
                payload,
                exercise_output,
                any(item["velocities"] for item in payload),
            )
            sessions.append(session)

            for item in payload:
                velocities = item["velocities"]
                velocity_loss = None
                if len(velocities) >= 2 and velocities[0] > 0:
                    velocity_loss = max(
                        0.0, min(1.0, 1.0 - velocities[-1] / velocities[0])
                    )
                capacity_service.process_quality_set(
                    athlete_id=workout.athlete_id,
                    lift=exercise.lift,
                    load_kg=item["load_kg"],
                    reps=item["reps"],
                    rpe=item.get("set_end_rpe"),
                    velocity_loss=velocity_loss,
                    observed_velocity=velocities[0] if velocities else None,
                )

        self.service._rebuild_day(workout.athlete_id, workout.start_time.date())
        self.db.commit()
        for session in sessions:
            self.db.refresh(session)
        return sessions
