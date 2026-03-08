"""
Sprint V5: Model vs Baselines Evaluation

Compares mapping variants M0-M3 against baselines on good targets.
"""
import sys
import os
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from datetime import date, datetime
from pathlib import Path
import json
import csv
import statistics
import math
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.eval.strength_targets import get_day_level_strength_target
from app.eval.baselines import BaselineVelocityThreshold, BaselineBanister
from app.domain.enhanced_observation_mapping import (
    EnhancedMappingParams,
    predict_with_enhanced_mapping,
    calibrate_mapping_variant,
    save_target_specific_params,
    load_params_with_fallback,
)


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./concurrent_training.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@dataclass
class VariantResult:
    """Result for a single mapping variant."""
    variant: str
    target_mode: str
    mae: float
    per_lift_mae: Dict[str, float]
    params: Dict[str, Any]
    n_samples: int


@dataclass  
class ComparisonResult:
    """Complete comparison for a target mode."""
    target_mode: str
    target_description: str
    baseline_a_mae: float
    baseline_b_mae: float
    variant_results: List[VariantResult]
    best_variant: str
    best_mae: float


def compute_mae(predictions, observed):
    if not predictions or not observed or len(predictions) != len(observed):
        return float('nan')
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


class SprintV5Evaluator:
    """Evaluator for Sprint V5 model comparison."""
    
    def __init__(self, db, target_mode: str):
        self.db = db
        self.target_mode = target_mode
        self.day_data: List[Dict] = []
        self.baseline_a = BaselineVelocityThreshold(window_days=7)
        self.baseline_b = BaselineBanister()
    
    def collect_data(self, athlete_id: int, date_from: date, date_to: date):
        """Collect day-level data for evaluation."""
        from app import models
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.domain.day_engine import PerLiftState
        
        orchestrator = EngineOrchestrator(self.db)
        
        sessions = self.db.query(models.StrengthSession).filter(
            models.StrengthSession.athlete_id == athlete_id,
            models.StrengthSession.start_time >= datetime.combine(date_from, datetime.min.time()),
            models.StrengthSession.start_time <= datetime.combine(date_to, datetime.max.time())
        ).order_by(models.StrengthSession.start_time).all()
        
        for session in sessions:
            session_date = session.start_time.date()
            lift = session.lift
            
            raw_data = session.raw_data or {}
            sets_data = raw_data.get("sets", [])
            
            if not sets_data:
                continue
            
            # Get capacity for fixed-load
            capacity = None
            if self.target_mode == "fixed_load_first_rep_velocity":
                profile_db = self.db.query(models.LiftProfile).filter(
                    models.LiftProfile.athlete_id == athlete_id,
                    models.LiftProfile.lift == lift
                ).first()
                if profile_db and profile_db.a > 0 and profile_db.b > 0:
                    capacity = profile_db.a / profile_db.b
            
            # Get target
            result = get_day_level_strength_target(
                sets_data=sets_data,
                lift=lift.value,
                target_mode=self.target_mode,
                profile_a=0.55,
                profile_b=0.003,
                anchor_capacity=None,
                model_capacity=capacity
            )
            
            if result.target_value is None:
                continue
            
            observed = result.target_value
            
            # Get state
            day_state = orchestrator.get_day_state_snapshot(athlete_id, session_date)
            D_l = D_sys = T_legs = 0.0
            
            if day_state:
                lift_state = day_state.per_lift.get(lift.value, PerLiftState())
                D_l = getattr(lift_state, 'D_l', 0.0)
                D_sys = day_state.D_sys
                T_legs = getattr(day_state, 'T_legs', 0.0)
            
            # Baseline predictions
            pred_baseline_a = self.baseline_a.predict_perf_y(lift.value, session_date)
            pred_baseline_b = self.baseline_b.predict_perf_y(lift.value)
            
            self.day_data.append({
                'date': session_date.isoformat(),
                'lift': lift.value,
                'observed': observed,
                'D_l': D_l,
                'D_sys': D_sys,
                'T_legs': T_legs,
                'baseline_a': pred_baseline_a,
                'baseline_b': pred_baseline_b,
            })
            
            # Update baselines
            self.baseline_a.add_observation(lift.value, session_date, observed)
            self.baseline_b.update(
                lift.value, session_date,
                tonnage=session.tonnage or 0,
                intensity=session.avg_intensity or 0.7
            )
        
        return len(self.day_data)
    
    def evaluate_variant(self, variant: str) -> VariantResult:
        """Evaluate a mapping variant."""
        # Calibrate
        calibration = calibrate_mapping_variant(
            self.day_data,
            variant=variant,
            target_mode=self.target_mode,
            grid_steps=8,
            refinement_steps=2
        )
        
        # Compute per-lift MAE
        per_lift_mae = {}
        lifts = list(set(d['lift'] for d in self.day_data))
        
        for lift in lifts:
            lift_data = [d for d in self.day_data if d['lift'] == lift]
            predictions = [
                predict_with_enhanced_mapping(
                    d['D_l'], d['D_sys'], d['T_legs'],
                    calibration.params, lift if variant != "M0" else None
                )
                for d in lift_data
            ]
            observed = [d['observed'] for d in lift_data]
            per_lift_mae[lift] = round(compute_mae(predictions, observed), 4)
        
        # Save params
        save_target_specific_params(calibration.params, self.target_mode, "./artifacts/config")
        
        return VariantResult(
            variant=variant,
            target_mode=self.target_mode,
            mae=round(calibration.train_mae, 4),
            per_lift_mae=per_lift_mae,
            params=calibration.params.to_dict(),
            n_samples=len(self.day_data)
        )
    
    def run_comparison(self) -> ComparisonResult:
        """Run full comparison."""
        # Baseline MAEs
        baseline_a_mae = compute_mae([d['baseline_a'] for d in self.day_data], [d['observed'] for d in self.day_data])
        baseline_b_mae = compute_mae([d['baseline_b'] for d in self.day_data], [d['observed'] for d in self.day_data])
        
        # Evaluate variants
        variants = ["M0", "M1", "M2"]
        variant_results = []
        
        for variant in variants:
            print(f"  Calibrating {variant}...")
            result = self.evaluate_variant(variant)
            variant_results.append(result)
            print(f"    MAE: {result.mae:.4f}")
        
        # Find best
        best = min(variant_results, key=lambda x: x.mae)
        
        descriptions = {
            "heaviest_quality_set_perf_y": "Heaviest quality set perf_y",
            "fixed_load_first_rep_velocity": "Fixed-load first-rep velocity",
        }
        
        return ComparisonResult(
            target_mode=self.target_mode,
            target_description=descriptions.get(self.target_mode, self.target_mode),
            baseline_a_mae=round(baseline_a_mae, 4),
            baseline_b_mae=round(baseline_b_mae, 4),
            variant_results=variant_results,
            best_variant=best.variant,
            best_mae=best.mae
        )


def run_sprint_v5():
    """Run complete Sprint V5 evaluation."""
    print("=" * 80)
    print("SPRINT V5: Model vs Baselines Evaluation")
    print("=" * 80)
    
    target_modes = [
        ("heaviest_quality_set_perf_y", "Heaviest quality set perf_y"),
        ("fixed_load_first_rep_velocity", "Fixed-load first-rep velocity"),
    ]
    
    all_results = []
    artifacts_dir = Path("./artifacts/synth_v2_run_v5")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    db = SessionLocal()
    try:
        for target_mode, description in target_modes:
            print(f"\n{'='*60}")
            print(f"Target: {description}")
            print(f"Mode: {target_mode}")
            print("="*60)
            
            evaluator = SprintV5Evaluator(db, target_mode)
            n_samples = evaluator.collect_data(
                athlete_id=299,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 3, 31),
            )
            print(f"  Collected {n_samples} samples")
            
            result = evaluator.run_comparison()
            all_results.append(result)
            
            print(f"\n  Baseline A MAE: {result.baseline_a_mae:.4f}")
            print(f"  Baseline B MAE: {result.baseline_b_mae:.4f}")
            print(f"  Best variant: {result.best_variant} (MAE={result.best_mae:.4f})")
            
            # Check if model beats baselines
            model_beats_a = result.best_mae < result.baseline_a_mae
            model_beats_b = result.best_mae < result.baseline_b_mae
            print(f"  Model beats Baseline A: {model_beats_a}")
            print(f"  Model beats Baseline B: {model_beats_b}")
    
    finally:
        db.close()
    
    # Generate artifacts
    model_vs_baselines_summary = {}
    per_lift_day_mae = {}
    mapping_variant_comparison = {}
    
    for result in all_results:
        model_vs_baselines_summary[result.target_mode] = {
            'description': result.target_description,
            'baseline_a_mae': result.baseline_a_mae,
            'baseline_b_mae': result.baseline_b_mae,
            'best_model_mae': result.best_mae,
            'best_variant': result.best_variant,
            'model_beats_baseline_a': result.best_mae < result.baseline_a_mae,
            'model_beats_baseline_b': result.best_mae < result.baseline_b_mae,
        }
        
        per_lift_day_mae[result.target_mode] = {
            'description': result.target_description,
            'per_lift_mae': {}
        }
        
        for vr in result.variant_results:
            per_lift_day_mae[result.target_mode]['per_lift_mae'][vr.variant] = vr.per_lift_mae
        
        mapping_variant_comparison[result.target_mode] = {
            'description': result.target_description,
            'variants': {}
        }
        
        for vr in result.variant_results:
            mapping_variant_comparison[result.target_mode]['variants'][vr.variant] = {
                'mae': vr.mae,
                'n_samples': vr.n_samples,
                'params': vr.params,
            }
    
    # Write artifacts
    with open(artifacts_dir / "model_vs_baselines_summary.json", 'w') as f:
        json.dump(model_vs_baselines_summary, f, indent=2)
    
    with open(artifacts_dir / "per_lift_day_mae.json", 'w') as f:
        json.dump(per_lift_day_mae, f, indent=2)
    
    with open(artifacts_dir / "mapping_variant_comparison.json", 'w') as f:
        json.dump(mapping_variant_comparison, f, indent=2)
    
    # Print final report
    print("\n" + "=" * 80)
    print("FINAL REPORT")
    print("=" * 80)
    
    print("\nModel vs Baselines Summary:")
    print(f"{'Target':<40} {'Baseline A':<12} {'Baseline B':<12} {'Best Model':<12} {'Variant':<8}")
    print("-" * 90)
    for result in all_results:
        print(f"{result.target_description:<40} {result.baseline_a_mae:<12.4f} "
              f"{result.baseline_b_mae:<12.4f} {result.best_mae:<12.4f} {result.best_variant:<8}")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    
    # Find best overall
    best_target = min(all_results, key=lambda x: x.best_mae)
    
    print(f"\nBest performing target: {best_target.target_description}")
    print(f"Best variant: {best_target.best_variant}")
    print(f"Best MAE: {best_target.best_mae:.4f}")
    
    if best_target.best_mae < best_target.baseline_a_mae and best_target.best_mae < best_target.baseline_b_mae:
        print("\n→ Model beats BOTH baselines!")
        print(f"  Recommendation: Use {best_target.target_mode} with {best_target.best_variant} as production default")
    elif best_target.best_mae < best_target.baseline_a_mae or best_target.best_mae < best_target.baseline_b_mae:
        print("\n→ Model beats at least one baseline")
        print(f"  Gap to best baseline: {min(best_target.baseline_a_mae, best_target.baseline_b_mae) - best_target.best_mae:.4f}")
    else:
        print("\n→ Model does NOT beat baselines yet")
        gap_a = best_target.best_mae - best_target.baseline_a_mae
        gap_b = best_target.best_mae - best_target.baseline_b_mae
        print(f"  Gap to Baseline A: +{gap_a:.4f}")
        print(f"  Gap to Baseline B: +{gap_b:.4f}")
    
    print(f"\nArtifacts written to: {artifacts_dir}")
    
    return all_results


def main():
    results = run_sprint_v5()
    
    print("\n" + "=" * 80)
    print("SPRINT V5 COMPLETE")
    print("=" * 80)
    
    return results


if __name__ == "__main__":
    main()
