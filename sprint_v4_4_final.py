"""
Sprint V4.4: Complete Target Comparison
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
from typing import Dict, List, Any
from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.eval.replay import ReplayRunner
from app.eval.strength_targets import get_day_level_strength_target


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./concurrent_training.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@dataclass
class TargetComparisonResult:
    mode: str
    description: str
    n_samples: int
    n_missing: int
    target_stats: Dict[str, Any]
    scale_alignment: Dict[str, Any]
    mae_constrained: float
    mae_legacy: float
    feature_correlations: Dict[str, float]
    feature_collinearity: Dict[str, float]
    calibrated_params: Dict[str, float]
    train_mae: float
    per_lift_availability: Dict[str, int]


def compute_mae(predictions, observed):
    if not predictions or not observed:
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


class ConfigurableTargetReplayRunner(ReplayRunner):
    """Replay runner that can switch target modes."""
    
    def __init__(self, db, target_mode: str = "legacy_ratio", artifacts_dir: str = "./artifacts"):
        super().__init__(db, artifacts_dir)
        self.target_mode = target_mode
        self.day_state_data = []
    
    def _extract_observed_perf_y(self, sets_data):
        profile_a = 0.55
        profile_b = 0.003
        
        result = get_day_level_strength_target(
            sets_data=sets_data,
            lift="unknown",
            target_mode=self.target_mode,
            profile_a=profile_a,
            profile_b=profile_b,
            anchor_capacity=None,
            model_capacity=None
        )
        
        return result.target_value
    
    def _replay_strength_session(self, athlete_id, session, dry_run):
        session_date = session.start_time.date()
        lift = session.lift
        
        raw_data = session.raw_data or {}
        sets_data = raw_data.get("sets", [])
        
        if not sets_data:
            return
        
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
        
        from app.services.engine_orchestrator import EngineOrchestrator
        orchestrator = EngineOrchestrator(self.db)
        day_state = orchestrator.get_day_state_snapshot(athlete_id, session_date)
        
        pred_constrained = 0.85
        D_l = D_sys = T_legs = 0.0
        
        if day_state:
            from app.services.observation_mapping_service import predict_perf_y_operational
            lift_state = day_state.per_lift.get(lift.value, None)
            D_l = getattr(lift_state, 'D_l', 0.0) if lift_state else 0.0
            D_sys = day_state.D_sys
            T_legs = getattr(day_state, 'T_legs', 0.0)
            pred_constrained, _ = predict_perf_y_operational(D_l, D_sys, T_legs, lift.value)
        
        if observed_perf_y:
            self.day_errors.append({
                "date": session_date.isoformat(),
                "lift": lift.value,
                "predicted_model": pred_constrained,
                "predicted_baseline_a": pred_constrained,
                "predicted_baseline_b": pred_constrained,
                "predicted_constrained": pred_constrained,
                "observed": observed_perf_y,
                "D_l": D_l,
                "D_sys": D_sys,
                "T_legs": T_legs,
                "target_source": result.target_source,
                "raw_value": result.raw_value,
                "chosen_set_idx": result.chosen_set_idx,
                "notes": "; ".join(result.notes) if result.notes else "",
            })
            
            self.day_state_data.append({
                "date": session_date.isoformat(),
                "lift": lift.value,
                "observed": observed_perf_y,
                "D_l": D_l,
                "D_sys": D_sys,
                "T_legs": T_legs,
                "target_source": result.target_source,
            })
        
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
    print("=" * 80)
    print("SPRINT V4.4: Complete Target Comparison")
    print("=" * 80)
    
    target_modes = [
        ("legacy_ratio", "Legacy ratio (rep2/rep1)"),
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
            
            runner = ConfigurableTargetReplayRunner(
                db, target_mode=mode, artifacts_dir=str(artifacts_dir)
            )
            
            report = runner.replay(
                athlete_id=299,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 3, 31),
                dry_run=True
            )
            
            if runner.day_state_data:
                observed = [d['observed'] for d in runner.day_state_data]
                D_l = [d['D_l'] for d in runner.day_state_data]
                D_sys = [d['D_sys'] for d in runner.day_state_data]
                T_legs = [d['T_legs'] for d in runner.day_state_data]
                
                target_stats = compute_descriptive_stats(observed)
                
                y_min, y_max = 0.60, 1.10
                in_bounds = sum(1 for o in observed if y_min <= o <= y_max)
                scale_alignment = {
                    'in_bounds': in_bounds,
                    'total': len(observed),
                    'fraction_in_bounds': round(in_bounds / len(observed), 4),
                    'mapping_bounds': [y_min, y_max],
                    'target_min': target_stats['min'],
                    'target_max': target_stats['max'],
                }
                
                feature_correlations = {
                    'D_l': round(pearson_correlation(D_l, observed), 4),
                    'D_sys': round(pearson_correlation(D_sys, observed), 4),
                    'T_legs': round(pearson_correlation(T_legs, observed), 4),
                }
                
                feature_collinearity = {
                    'D_l_vs_D_sys': round(pearson_correlation(D_l, D_sys), 4),
                    'D_l_vs_T_legs': round(pearson_correlation(D_l, T_legs), 4),
                    'D_sys_vs_T_legs': round(pearson_correlation(D_sys, T_legs), 4),
                }
                
                from app.domain.observation_mapping import calibrate_observation_mapping
                prepared_rows = [{'observed': d['observed'], **d} for d in runner.day_state_data]
                calibration_result = calibrate_observation_mapping(
                    prepared_rows,
                    per_lift=False,
                    grid_steps=6,
                    refinement_steps=2
                )
                
                calibrated_params = calibration_result.params.to_dict()
                train_mae = round(calibration_result.train_mae, 4)
                
                per_lift_availability = {}
                for d in runner.day_state_data:
                    lift = d['lift']
                    per_lift_availability[lift] = per_lift_availability.get(lift, 0) + 1
                
                predicted_constrained = [d['predicted_constrained'] for d in runner.day_errors if d.get('predicted_constrained')]
                mae_constrained = compute_mae(predicted_constrained, observed)
                
                legacy_predictions = [0.85] * len(observed)
                mae_legacy = compute_mae(legacy_predictions, observed)
                
                total_sessions = 63
                n_samples = len(observed)
                n_missing = total_sessions - n_samples
                
                results[mode] = TargetComparisonResult(
                    mode=mode,
                    description=description,
                    n_samples=n_samples,
                    n_missing=n_missing,
                    target_stats=target_stats,
                    scale_alignment=scale_alignment,
                    mae_constrained=round(mae_constrained, 4),
                    mae_legacy=round(mae_legacy, 4),
                    feature_correlations=feature_correlations,
                    feature_collinearity=feature_collinearity,
                    calibrated_params=calibrated_params,
                    train_mae=train_mae,
                    per_lift_availability=per_lift_availability,
                )
                
                print(f"  Samples: {n_samples}/{total_sessions} ({n_missing} missing)")
                print(f"  Target mean: {target_stats['mean']:.4f}")
                print(f"  Target range: [{target_stats['min']:.4f}, {target_stats['max']:.4f}]")
                print(f"  In mapping bounds: {scale_alignment['fraction_in_bounds']:.1%}")
                print(f"  MAE (constrained): {mae_constrained:.4f}")
                print(f"  MAE (legacy): {mae_legacy:.4f}")
                print(f"  Correlations: D_l={feature_correlations['D_l']:+.4f}, "
                      f"D_sys={feature_correlations['D_sys']:+.4f}, "
                      f"T_legs={feature_correlations['T_legs']:+.4f}")
                print(f"  Calibrated: b_l={calibrated_params['b_l']:.4f}, "
                      f"b_sys={calibrated_params['b_sys']:.4f}, b_t={calibrated_params['b_t']:.4f}")
            
            runner.write_artifacts(f"synth_v2_run_v4_4_{mode}")
    
    finally:
        db.close()
    
    comparison_summary = {}
    target_mode_results = {}
    feature_correlations_by_target = {}
    
    for mode, result in results.items():
        comparison_summary[mode] = {
            'description': result.description,
            'n_samples': result.n_samples,
            'n_missing': result.n_missing,
            'target_stats': result.target_stats,
            'scale_alignment': result.scale_alignment,
            'per_lift_availability': result.per_lift_availability,
        }
        
        target_mode_results[mode] = {
            'description': result.description,
            'mae_constrained': result.mae_constrained,
            'mae_legacy': result.mae_legacy,
            'calibrated_params': result.calibrated_params,
            'train_mae': result.train_mae,
        }
        
        feature_correlations_by_target[mode] = {
            'description': result.description,
            'feature_correlations': result.feature_correlations,
            'feature_collinearity': result.feature_collinearity,
        }
    
    with open(artifacts_dir / "target_comparison_summary.json", 'w') as f:
        json.dump(comparison_summary, f, indent=2)
    
    with open(artifacts_dir / "target_mode_results.json", 'w') as f:
        json.dump(target_mode_results, f, indent=2)
    
    with open(artifacts_dir / "feature_correlations_by_target.json", 'w') as f:
        json.dump(feature_correlations_by_target, f, indent=2)
    
    print("\n" + "=" * 80)
    print("COMPARISON SUMMARY")
    print("=" * 80)
    
    print(f"\n{'Target':<40} {'Samples':<10} {'MAE':<10} {'In Bounds':<12} {'D_l corr':<10} {'D_sys corr':<10}")
    print("-" * 100)
    for mode, result in results.items():
        print(f"{result.description:<40} {result.n_samples:<10} {result.mae_constrained:<10.4f} "
              f"{result.scale_alignment['fraction_in_bounds']:<12.1%} "
              f"{result.feature_correlations['D_l']:<10.4f} "
              f"{result.feature_correlations['D_sys']:<10.4f}")
    
    best_scale = max(results.items(), key=lambda x: x[1].scale_alignment['fraction_in_bounds'])
    best_mae = min(results.items(), key=lambda x: x[1].mae_constrained)
    best_coverage = max(results.items(), key=lambda x: x[1].n_samples)
    
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    
    print(f"\nBest scale alignment: {best_scale[1].description} "
          f"({best_scale[1].scale_alignment['fraction_in_bounds']:.1%} in bounds)")
    print(f"Best MAE: {best_mae[1].description} (MAE={best_mae[1].mae_constrained:.4f})")
    print(f"Best coverage: {best_coverage[1].description} ({best_coverage[1].n_samples} samples)")
    
    print("\n" + "=" * 80)
    print("STATE RELEVANCE ANALYSIS")
    print("=" * 80)
    
    for mode, result in results.items():
        print(f"\n{result.description}:")
        T_legs_corr = abs(result.feature_correlations['T_legs'])
        D_l_corr = abs(result.feature_correlations['D_l'])
        D_sys_corr = abs(result.feature_correlations['D_sys'])
        
        T_legs_dominant = T_legs_corr > D_l_corr * 1.5 and T_legs_corr > D_sys_corr * 1.5
        D_l_relevant = result.calibrated_params['b_l'] > 0.01
        D_sys_relevant = result.calibrated_params['b_sys'] > 0.01
        
        print(f"  T_legs dominant (1.5x): {T_legs_dominant}")
        print(f"  D_l relevant (b_l > 0.01): {D_l_relevant}")
        print(f"  D_sys relevant (b_sys > 0.01): {D_sys_relevant}")
        print(f"  Calibrated coefficients: b_l={result.calibrated_params['b_l']:.4f}, "
              f"b_sys={result.calibrated_params['b_sys']:.4f},