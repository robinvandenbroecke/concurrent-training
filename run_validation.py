#!/usr/bin/env python3
"""Retrospective runtime diagnostics; not leakage-free scientific validation.

Use research/evaluate.py with an explicit provenance-labelled event log for a
prefix-only evaluation. Existing mutable profiles/states cannot prove as-of use.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, timedelta
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app import models
from app.database import SessionLocal
from app.domain.day_engine import DayState, PerLiftState, decay_day_state_to_date
from app.eval.baselines import BaselineBanister, BaselineVelocityThreshold
from app.eval.strength_targets import target_heaviest_quality_set_perf_y
from app.eval.validation import compute_rep_level_metrics, compute_trend_classification_metrics
from app.services.capacity_service import get_lift_capacity_estimate
from app.services.engine_orchestrator import EngineOrchestrator
from app.services.observation_mapping_service import predict_perf_y_operational
from app.types import LiftType

REPO_ROOT = Path(__file__).resolve().parent
ARTIFACTS_LATEST = "artifacts/latest"


def _mae(pairs: List[Tuple[float, float]]) -> Optional[float]:
    if not pairs:
        return None
    return round(sum(abs(pred - obs) for pred, obs in pairs) / len(pairs), 6)


def _rmse(pairs: List[Tuple[float, float]]) -> Optional[float]:
    if not pairs:
        return None
    return round(math.sqrt(sum((pred - obs) ** 2 for pred, obs in pairs) / len(pairs)), 6)


def _prepare_sets(raw_sets: List[Dict]) -> List[Dict]:
    prepared = []
    for item in raw_sets or []:
        row = dict(item)
        velocities = list(row.get("velocities", []))
        row["velocities"] = velocities
        row["rpe"] = row.get("rpe", row.get("set_end_rpe"))
        if len(velocities) >= 2 and velocities[0] and velocities[-1]:
            row["vl"] = max(0.0, min(1.0, 1.0 - velocities[-1] / velocities[0]))
        prepared.append(row)
    return prepared


def _session_target(db, session) -> Optional[float]:
    profile = db.query(models.LiftProfile).filter(
        models.LiftProfile.athlete_id == session.athlete_id,
        models.LiftProfile.lift == session.lift,
    ).first()
    if profile is None:
        return None
    capacity, _ = get_lift_capacity_estimate(
        db, session.athlete_id, session.lift, session.start_time.date()
    )
    result = target_heaviest_quality_set_perf_y(
        _prepare_sets((session.raw_data or {}).get("sets", [])),
        profile_a=float(profile.a),
        profile_b=abs(float(profile.b)),
        model_capacity=capacity,
    )
    return result.target_value


def _state_before_date(db, athlete_id: int, target_date: date, params) -> DayState:
    row = db.query(models.DayState).filter(
        models.DayState.athlete_id == athlete_id,
        models.DayState.date < target_date.isoformat(),
    ).order_by(models.DayState.date.desc()).first()
    if row is None:
        return DayState(
            date=target_date,
            per_lift={lift.value: PerLiftState() for lift in LiftType},
            D_sys=0.0,
            R_mito=0.0,
            E_fat=0.0,
            T_legs=0.0,
        )
    lift_rows = db.query(models.LiftDayState).filter(
        models.LiftDayState.athlete_id == athlete_id,
        models.LiftDayState.date == row.date,
    ).all()
    state = DayState(
        date=date.fromisoformat(row.date),
        per_lift={
            item.lift.value: PerLiftState(D_l=item.D_l, F_l=item.F_l, C_l=item.C_l)
            for item in lift_rows
        },
        D_sys=row.D_sys,
        R_mito=row.R_mito,
        E_fat=row.E_fat,
        T_legs=getattr(row, "T_legs", 0.0),
    )
    return decay_day_state_to_date(state, target_date, params)


def _model_prediction(db, orchestrator: EngineOrchestrator, session) -> float:
    state = _state_before_date(db, session.athlete_id, session.start_time.date(), orchestrator.day_params)
    lift_state = state.get_lift(session.lift.value)
    prediction, _ = predict_perf_y_operational(
        D_l=lift_state.D_l,
        D_sys=state.D_sys,
        T_legs=state.T_legs,
        lift=session.lift.value,
    )
    return float(prediction)


def _rep_pairs(session) -> List[Tuple[float, float]]:
    sets = _prepare_sets((session.raw_data or {}).get("sets", []))
    logs = session.rep_level_log or []
    by_set: Dict[int, Dict[int, Dict]] = defaultdict(dict)
    for row in logs:
        by_set[int(row.get("set_idx", 0))][int(row.get("rep_idx", 0))] = row
    pairs = []
    for set_index, set_data in enumerate(sets):
        velocities = set_data.get("velocities", [])
        for rep_index in range(max(0, len(velocities) - 1)):
            log = by_set.get(set_index, {}).get(rep_index)
            if log and log.get("v_pred_next") is not None and velocities[rep_index + 1] is not None:
                pairs.append((float(log["v_pred_next"]), float(velocities[rep_index + 1])))
    return pairs


def _rolling_prediction(history: List[Tuple[date, float]], ref_date: date) -> float:
    values = [(d, value) for d, value in history if ref_date - timedelta(days=30) <= d < ref_date]
    if not values:
        return 0.9375
    last = values[-1][1]
    best = max(value for _, value in values)
    readiness = last / best if best > 0 else 0.75
    return max(0.60, min(1.10, readiness))


def _classify(delta: float) -> str:
    if delta > 0.015:
        return "progress"
    if delta < -0.015:
        return "regression"
    return "stagnation"


def validate_athlete(db, athlete_id: int, days: int) -> Dict:
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    sessions = db.query(models.StrengthSession).filter(
        models.StrengthSession.athlete_id == athlete_id,
        models.StrengthSession.start_time >= start_date,
        models.StrengthSession.start_time < end_date + timedelta(days=1),
    ).order_by(models.StrengthSession.start_time).all()

    usable = [(session, _session_target(db, session)) for session in sessions]
    usable = [(session, target) for session, target in usable if target is not None]
    unique_dates = sorted({session.start_time.date() for session, _ in usable})
    if not usable or len(unique_dates) < 2:
        return {"athlete_id": athlete_id, "note": "Insufficient target-bearing sessions", "n_sessions": len(usable)}

    split_index = max(1, min(len(unique_dates) - 1, int(math.floor(0.70 * len(unique_dates)))))
    cutoff = unique_dates[split_index]
    orchestrator = EngineOrchestrator(db)
    velocity_baseline = BaselineVelocityThreshold(window_days=7)
    banister = BaselineBanister()
    rolling_history: Dict[str, List[Tuple[date, float]]] = defaultdict(list)

    pairs_by_lift = defaultdict(lambda: defaultdict(list))
    rows = []
    rep_pairs = []
    previous_test = {}
    predicted_trends, observed_trends = [], []

    for session, observed in usable:
        lift = session.lift.value
        session_date = session.start_time.date()
        model_pred = _model_prediction(db, orchestrator, session)
        baseline_a = velocity_baseline.predict_perf_y(lift, session_date)
        baseline_b = banister.predict_perf_y(lift)
        baseline_c = _rolling_prediction(rolling_history[lift], session_date)

        if session_date >= cutoff:
            predictions = {
                "model": model_pred,
                "velocity_threshold": baseline_a,
                "banister": baseline_b,
                "rolling_30d": baseline_c,
            }
            for name, prediction in predictions.items():
                pairs_by_lift[lift][name].append((prediction, observed))
            rows.append({
                "date": session_date.isoformat(),
                "lift": lift,
                "observed": observed,
                **{f"predicted_{name}": value for name, value in predictions.items()},
            })
            rep_pairs.extend(_rep_pairs(session))
            if lift in previous_test:
                prior_pred, prior_obs = previous_test[lift]
                predicted_trends.append(_classify(model_pred - prior_pred))
                observed_trends.append(_classify(observed - prior_obs))
            previous_test[lift] = (model_pred, observed)

        # Update every baseline only after making the current prediction.
        velocity_baseline.add_observation(lift, session_date, observed)
        intensity = float(session.avg_intensity or 0.75)
        if intensity > 2.0:
            capacity, _ = get_lift_capacity_estimate(db, athlete_id, session.lift, session_date)
            intensity = min(1.2, intensity / max(capacity, 1.0))
        banister.update(lift, session_date, float(session.tonnage or 0.0), intensity)
        rolling_history[lift].append((session_date, observed))

    per_lift = {}
    aggregate = defaultdict(list)
    for lift, models_by_name in pairs_by_lift.items():
        per_lift[lift] = {}
        for name, pairs in models_by_name.items():
            per_lift[lift][name] = {"mae": _mae(pairs), "rmse": _rmse(pairs), "n": len(pairs)}
            aggregate[name].extend(pairs)

    rep_metrics = compute_rep_level_metrics(
        [pred for pred, _ in rep_pairs], [obs for _, obs in rep_pairs]
    )
    trend = compute_trend_classification_metrics(predicted_trends, observed_trends)
    return {
        "athlete_id": athlete_id,
        "date_from": start_date.isoformat(),
        "date_to": end_date.isoformat(),
        "train_fraction": 0.70,
        "test_start": cutoff.isoformat(),
        "target_mode": "heaviest_quality_set_perf_y",
        "n_target_sessions": len(usable),
        "n_test_sessions": len(rows),
        "metrics": {
            "aggregate": {
                name: {"mae": _mae(pairs), "rmse": _rmse(pairs), "n": len(pairs)}
                for name, pairs in aggregate.items()
            },
            "per_lift": per_lift,
            "rep_level": {"rmse": rep_metrics.rmse, "mae": rep_metrics.mae, "n": rep_metrics.n_samples},
            "trend": {
                "accuracy": trend.accuracy,
                "f1_macro": trend.f1,
                "n": trend.n_samples,
                "confusion_matrix": trend.confusion_matrix,
            },
        },
        "predictions": rows,
    }


def run_validation(source: str, athlete_id: int, athletes: int, days: int) -> Dict:
    db = SessionLocal()
    try:
        if source == "db":
            athlete_ids = [athlete_id]
        else:
            athlete_ids = [
                row.id for row in db.query(models.Athlete).order_by(models.Athlete.id).limit(athletes).all()
            ]
        reports = [validate_athlete(db, item, days) for item in athlete_ids]
        return {
            "run_date": date.today().isoformat(),
            "data_source": "database_provenance_unverified",
            "requested_source": source,
            "scientific_validation": False,
            "n_athletes": len(athlete_ids),
            "holdout_policy": "per-athlete first 70% dates train, final 30% dates test",
            "no_lookahead": False,
            "limitations": [
                "Current mutable load-velocity/capacity profiles can contain later observations",
                "Persisted day states and stored rep predictions lack complete model-version provenance",
                "Synthetic/real provenance cannot be inferred from a command-line label",
                "Legacy baseline calibration and update exposure are not equivalent",
                "Use research/evaluate.py for isolated prefix-only evaluation",
            ],
            "reports": reports,
        }
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["synthetic", "db"], default="db")
    parser.add_argument("--athlete-id", type=int, default=1)
    parser.add_argument("--athletes", type=int, default=10)
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()

    output = run_validation(args.source, args.athlete_id, args.athletes, args.days)
    directory = REPO_ROOT / ARTIFACTS_LATEST
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "validation_report.json"
    path.write_text(json.dumps(output, indent=2, default=str))
    print(f"Validation complete. Report written to: {path}")
    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()

