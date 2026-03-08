"""
Sprint V4.4: Compare Day-Level Targets Diagnostic

Reruns replay/validation with different target constructions and compares:
1. heaviest_quality_set_perf_y
2. fixed_load_first_rep_velocity
3. legacy_rep2_rep1_ratio (baseline)

Then runs diagnostics to determine which target is best.
"""
import sys
import os
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from datetime import date
from pathlib import Path
import json
import csv
import statistics
import math
from typing import Dict, List

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.eval.replay import ReplayRunner
from app.eval.strength_targets import get_day_level_strength_target
from app.domain.observation_mapping import (
    calibrate_observation_mapping,
    ObservationMappingParams,
    predict_perf_y_constrained,
)


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./concurrent_training.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def compute_mae(predictions, observed):
    return statistics.mean([abs(p - o) for p, o in zip(predictions, observed)])


def pearson_correlation(x, y):
    n = len(x)
    if n < 2:
        return 0.0
    mean_x, mean_y = statistics.mean(x), statistics.mean(y)
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    den_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    den_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def compute_descriptive_stats(values):
    if not values:
        return {}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    def pct(p):
        idx = int(p / 100.0 * (n - 1))
        return sorted_vals[max(0, min(n - 1, idx))]
    return {
        'mean': round(statistics.mean(sorted_vals), 6),
        'std': round(statistics.stdev(sorted_vals) if n > 1 else 0.0, 6),
        'min': round(min(sorted_vals), 6),
        'max': round(max(sorted_vals), 6),
        'p10': round(pct(10), 6),
        'p50': round(pct(50), 6),
        'p90': round(pct(90), 6),
        'n': n,
    }


class MultiTargetReplayRunner(ReplayRunner):
    """
    Extended replay runner that can use different target constructions.
    """
    
    def __init__(self, db, target_mode: str = "legacy", artifacts_dir: str = "./artifacts"):
        super().__init__(db, artifacts_dir)
        self.target_mode = target_mode
    
    def _extract_observed_perf_y(self, sets_data):
        """Override to use new target constructors."""
        # Get profile from current session context
        # For now, use defaults - in production would fetch athlete's profile
        profile_a = 0.55
        profile_b = 0.003
        
        result = get_day_level_strength_target(
            sets_data=sets_data,
            lift="unknown",  # Will be set by caller
            target_mode=self.target_mode,
            profile_a=profile_a,
            profile_b=profile_b,
            anchor_capacity=None,
            model_capacity=None
        )
        
        return result.target_value
    
    def _replay_strength_session(self, athlete_id, session, dry_run):
        """Override to capture target source metadata."""
        # Call parent but capture more metadata
        session_date = session.start_time.date()
        lift = session.lift
        
        # Get raw data
        raw_data = session.raw_data or {}
        sets_data = raw_data.get("sets", [])
        
        if not sets_data:
            return
        
        # Get target using new constructor
        profile_a = 0.55
        profile_b = 0.003
        
        result = get_day_level_strength_target(
            sets_data=sets_data,
            lift=lift.value,
            target_mode=self.target_mode,
            profile_a=profile_a,
            profile_b=profile_b,
            anchor_capacity=None,
            model_capacity=None
        )
        
        observed_perf_y = result.target_value
        
        # Get prediction from orchestrator
        from app.services.engine_orchestrator import EngineOrchestrator
        orchestrator = EngineOrchestrator(self.db)
        day_state = orchestrator.get_day_state_snapshot(athlete_id, session_date)
        
        pred_constrained = 0.85
        if day_state:
            from app.services.observation_mapping_service import predict_perf_y_operational
            lift_state = day_state.per_lift.get(lift.value, None)
            D_l = getattr(lift_state, 'D_l', 0.0) if lift_state else 0.0
            D_sys = day_state.D_sys
            T_legs = getattr(day_state, 'T_legs', 0.0)
            pred_constrained, _ = predict_perf_y_operational(D_l, D_sys, T_legs, lift.value)
        
        # Log with metadata
        if observed_perf_y:
            self.day_errors.append({
                "date": session_date.isoformat(),
                "lift": lift.value,
                "predicted_model": pred_constrained,
                "predicted_baseline_a": pred_constrained,  # For compatibility
                "predicted_baseline_b": pred_constrained,  # For compatibility
                "predicted_constrained": pred_constrained,
                "observed": observed_perf_y,
                "target_source": result.target_source,
                "raw_value": result.raw_value,
                "chosen_set_idx": result.chosen_set_idx,
                "notes": "; ".join(result.notes) if result.notes else "",
            })
        
        # Apply session to update state
        if not dry_run:
            try:
                sets_converted = self._convert_sets_for_orchestrator(sets_data)
                orchestrator.ingest_strength_session(
                    athlete_id=athlete_id,
                    lift=lift,
                    session_date=session_date,
                    sets_data=sets_converted,
                    vbt_available=True
                )
            except Exception as e:
                print(f"Warning: failed to apply session: {e}")


def run_target_comparison():
    """Run replay with each target mode and compare."""
    print("=" * 80)
    print("SPRINT V4.4: Target Construction Comparison")
    print("=" * 80)
    
    target_modes = [
        ("legacy_rep2_rep1_ratio", "Legacy (rep2/rep1)"),
        ("heaviest_quality_set_perf_y", "Heaviest quality set perf_y"),
        ("fixed_load_first_rep_velocity", "Fixed-load first-rep velocity"),
    ]
    
    results = {}
    artifacts_dir = Path("./artifacts/synth_v2_run_v4_4")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    db = SessionLocal()
    try:
        for mode, description in target_modes:
            print(f"\n{'='*60}")
            print(f"Target: {description}")
            print(f"Mode: {mode}")
            print("="*60)
            
            runner = MultiTargetReplayRunner(db, target_mode=mode, artifacts_dir=str(artifacts_dir))
            
            report = runner.replay(
                athlete_id=299,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 3, 31),
                dry_run=True
            )
            
            # Compute metrics
            if runner.day_errors:
                observed = [e['observed'] for e in runner.day_errors if e['observed'] is not None]
                predicted = [e['predicted_constrained'] for e in runner.day_errors if e['observed'] is not None]
                
                if observed and predicted:
                    mae = compute_mae(predicted, observed)
                    stats = compute_descriptive_stats(observed)
                    
                    # Check scale alignment
                    y_min, y_max = 0.60, 1.10
                    in_bounds = sum(1 for o in observed if y_min <= o <= y_max)
                    
                    results[mode] = {
                        'description': description,
                        'n_samples': len(observed),
                        'mae': round(mae, 4),
                        'target_stats': stats,
                        'scale_alignment': {
                            'in_bounds': in_bounds,
                            'total': len(observed),
                            'fraction_in_bounds': round(in_bounds / len(observed), 4),
                            'mapping_bounds': [y_min, y_max],
                        }
                    }
                    
                    print(f"  Samples: {len(observed)}")
                    print(f"  MAE: {mae:.4f}")
                    print(f"  Target mean: {stats['mean']:.4f}")
                    print(f"  Target range: [{stats['min']:.4f}, {stats['max']:.4f}]")
                    print(f"  In mapping bounds: {in_bounds}/{len(observed)} ({in_bounds/len(observed)*100:.1f}%)")
            
            # Write artifacts
            runner.write_artifacts(f"synth_v2_run_v4_4_{mode}")
    
    finally:
        db.close()
    
    # Save comparison
    with open(artifacts_dir / "target_comparison.json", 'w') as f:
        json.dump(results, f, indent=2)
    
    # Generate recommendation
    print("\n" + "=" * 80)
    print("COMPARISON SUMMARY")
    print("=" * 80)
    
    print(f"\n{'Target':<40} {'MAE':<10} {'Mean':<10} {'In Bounds':<12}")
    print("-" * 80)
    for mode, data in results.items():
        print(f"{data['description']:<40} {data['mae']:<10.4f} "
              f"{data['target_stats']['mean']:<10.4f} "
              f"{data['scale_alignment']['fraction_in_bounds']:<12.1%}")
    
    # Find best by criteria
    best_scale = max(results.items(), key=lambda x: x[1]['scale_alignment']['fraction_in_bounds'])
    best_mae = min(results.items(), key=lambda x: x[1]['mae'])
    
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    print(f"\nBest scale alignment: {best_scale[1]['description']} "
          f"({best_scale[1]['scale_alignment']['fraction_in_bounds']:.1%} in bounds)")
    print(f"Best MAE: {best_mae[1]['description']} (MAE={best_mae[1]['mae']:.4f})")
    
    # Overall recommendation
    if best_scale[0] == best_mae[0]:
        print(f"\n→ RECOMMENDATION: {best_scale[1]['description']}")
        print("  This target has both good scale alignment and lowest MAE.")
    else:
        print("\n→ TRADE-OFF DETECTED:")
        print(f"  - For scale alignment: use {best_scale[1]['description']}")
        print(f"  - For lowest MAE: use {best_mae[1]['description']}")
        print("  - Consider whether scale alignment or raw MAE is more important for your use case.")
    
    return results


def main():
    run_target_comparison()
    print("\n" + "=" * 80)
    print("SPRINT V4.4 COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
