"""Conservative athlete-specific load–velocity profile calibration."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import statistics
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app import models
from app.services.capacity_service import get_lift_capacity_estimate
from app.types import LiftType


class VelocityProfileService:
    def __init__(self, db: Session):
        self.db = db

    def update_from_recent_sessions(
        self,
        athlete_id: int,
        lift: LiftType,
        *,
        reference_date: Optional[date] = None,
        days_back: int = 120,
        blend: float = 0.20,
    ) -> Dict:
        """Fit `v = a - b*load` from first-rep velocities.

        Requires at least three distinct loads and six observations in a
        submaximal range. New coefficients are blended into the existing
        profile to avoid unstable jumps from noisy VBT measurements.
        """
        reference_date = reference_date or date.today()
        profile = self.db.query(models.LiftProfile).filter(
            models.LiftProfile.athlete_id == athlete_id,
            models.LiftProfile.lift == lift,
        ).first()
        if profile is None:
            return {"updated": False, "reason": "missing_profile"}

        capacity, source = get_lift_capacity_estimate(
            self.db, athlete_id, lift, reference_date
        )
        start = datetime.combine(reference_date - timedelta(days=days_back), datetime.min.time())
        end = datetime.combine(reference_date + timedelta(days=1), datetime.min.time())
        sessions = self.db.query(models.StrengthSession).filter(
            models.StrengthSession.athlete_id == athlete_id,
            models.StrengthSession.lift == lift,
            models.StrengthSession.start_time >= start,
            models.StrengthSession.start_time < end,
        ).order_by(models.StrengthSession.start_time).all()

        by_load = defaultdict(list)
        for session in sessions:
            for item in (session.raw_data or {}).get("sets", []):
                try:
                    load = float(item.get("load_kg"))
                    velocities = item.get("velocities") or []
                    first_velocity = float(velocities[0])
                except (TypeError, ValueError, IndexError):
                    continue
                relative = load / max(capacity, 1.0)
                if not 0.30 <= relative <= 0.92:
                    continue
                if not 0.05 <= first_velocity <= 2.0:
                    continue
                by_load[round(load, 2)].append(first_velocity)

        observations = sum(len(values) for values in by_load.values())
        if len(by_load) < 3 or observations < 6:
            return {
                "updated": False,
                "reason": "insufficient_data",
                "distinct_loads": len(by_load),
                "observations": observations,
                "capacity_source": source,
            }

        # Median per load prevents frequently repeated warm-up loads from
        # dominating the regression.
        pairs = sorted((load, statistics.median(values)) for load, values in by_load.items())
        loads = [load for load, _ in pairs]
        velocities = [velocity for _, velocity in pairs]
        mean_load = statistics.mean(loads)
        mean_velocity = statistics.mean(velocities)
        denominator = sum((load - mean_load) ** 2 for load in loads)
        if denominator <= 0:
            return {"updated": False, "reason": "degenerate_loads"}
        slope = sum(
            (load - mean_load) * (velocity - mean_velocity)
            for load, velocity in pairs
        ) / denominator
        fitted_b = -slope
        fitted_a = mean_velocity + fitted_b * mean_load

        if not (0.0001 <= fitted_b <= 0.02 and 0.20 <= fitted_a <= 3.0):
            return {
                "updated": False,
                "reason": "non_physiological_fit",
                "fitted_a": fitted_a,
                "fitted_b": fitted_b,
            }

        blend = max(0.0, min(1.0, float(blend)))
        old_a, old_b = float(profile.a), float(profile.b)
        profile.a = (1.0 - blend) * old_a + blend * fitted_a
        profile.b = (1.0 - blend) * old_b + blend * fitted_b
        self.db.commit()
        return {
            "updated": True,
            "old_a": old_a,
            "old_b": old_b,
            "fitted_a": fitted_a,
            "fitted_b": fitted_b,
            "new_a": profile.a,
            "new_b": profile.b,
            "distinct_loads": len(by_load),
            "observations": observations,
            "capacity_source": source,
        }
