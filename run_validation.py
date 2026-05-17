#!/usr/bin/env python3
"""
run_validation.py — Thin wrapper for model validation.

Calls existing evaluation functions and writes artifacts to artifacts/latest/.

Usage:
    python run_validation.py --source synthetic --athletes 10 --days 90
    python run_validation.py --source db --athlete-id 1 --days 90
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

from app.database import SessionLocal
from app import models
from app.eval.validation import (
    compute_rep_level_metrics,
    compute_day_level_strength_metrics,
    compute_trend_classification_metrics,
    RepLevelMetrics,
    DayLevelMetrics,
    TrendClassificationMetrics,
)
from app.eval.baselines import BaselineVelocityThreshold, BaselineBanister


def _ensure_artifacts_dir() -> Path:
    d = REPO_ROOT / "artifacts" / "latest"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_synthetic_data(athlete_id: int, days: int):
    """Load synthetic athlete data if available."""
    db = SessionLocal()
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    strength_sessions = db.query(models.StrengthSession).filter(
        models.StrengthSession.athlete_id == athlete_id,
        models.StrengthSession.start_time >= start_date,
        models.StrengthSession.start_time <= end_date,
    ).order_by(models.StrengthSession.start_time).all()

    day_states = db.query(models.DayState).filter(
        models.DayState.athlete_id == athlete_id,
        models.DayState.date >= start_date.isoformat(),
        models.DayState.date <= end_date.isoformat(),
    ).order_by(models.DayState.date).all()

    return strength_sessions, day_states


def _compute_baselines(sessions, lift="squat"):
    """Run simple baselines on session history."""
    baseline_a = BaselineVelocityThreshold(window_days=7)
    baseline_b = BaselineBanister()

    for sess in sessions:
        if not hasattr(sess, 'raw_data') or not sess.raw_data:
            continue
        # Add dummy observations for baselines
        baseline_a.add_observation(lift, sess.start_time.date(), 0.85)
        baseline_b.update(lift, sess.start_time.date(), tonnage=getattr(sess, 'tonnage', 1000), intensity=0.75)

    pred_a = baseline_a.predict_perf_y(lift, date.today())
    pred_b = baseline_b.predict_perf_y(lift)
    return {"vbt_threshold": pred_a, "banister": pred_b}


def run_validation(athlete_id: int, days: int, source: str = "db") -> dict:
    """Run validation and return report dict."""
    strength_sessions, day_states = _load_synthetic_data(athlete_id, days)

    report = {
        "run_date": date.today().isoformat(),
        "data_source": source,
        "n_athletes": 1,
        "hold_out_days": days,
        "athlete_id": athlete_id,
        "metrics": {},
        "baselines": {},
    }

    if not strength_sessions:
        report["note"] = "No strength sessions found for athlete in date range."
        return report

    # Rep-level metrics (if VBT data exists)
    rep_metrics = compute_rep_level_metrics(strength_sessions)
    if rep_metrics:
        report["metrics"]["rep_rmse"] = rep_metrics.rmse
        report["metrics"]["rep_mae"] = rep_metrics.mae
        report["metrics"]["rep_n"] = rep_metrics.n_samples

    # Day-level metrics
    day_metrics = compute_day_level_strength_metrics(strength_sessions, day_states)
    if day_metrics:
        report["metrics"]["day_mae"] = day_metrics.mae
        report["metrics"]["day_mape"] = day_metrics.mape
        report["metrics"]["day_n"] = day_metrics.n_samples

    # Baselines
    report["baselines"] = _compute_baselines(strength_sessions)

    return report


def main():
    parser = argparse.ArgumentParser(description="Run concurrent-training model validation")
    parser.add_argument("--source", choices=["synthetic", "db"], default="db", help="Data source")
    parser.add_argument("--athlete-id", type=int, default=1, help="Athlete ID")
    parser.add_argument("--athletes", type=int, default=1, help="Number of athletes (synthetic)")
    parser.add_argument("--days", type=int, default=90, help="Look-back days")
    args = parser.parse_args()

    artifacts_dir = _ensure_artifacts_dir()

    report = run_validation(args.athlete_id, args.days, source=args.source)

    out_path = artifacts_dir / "validation_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Validation complete. Report written to: {out_path}")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
