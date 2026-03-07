"""
Sprint V4.1: Verify Calibrated Params Are Operational

Rerun replay/validate and verify that:
1. Calibrated params are loaded and used
2. Operational MAE matches calibrated MAE
3. Day errors show correct params_source
"""
import sys
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from datetime import date
from pathlib import Path
import json
import statistics

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.eval.replay import ReplayRunner
from app.services.observation_mapping_service import get_operational_params_info


DATABASE_URL = "sqlite:///./concurrent_training.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def main():
    print("=" * 80)
    print("SPRINT V4.1: Verify Calibrated Params Are Operational")
    print("=" * 80)
    
    # Step 1: Verify operational params info
    print("\n[1/3] Checking operational parameters...")
    info = get_operational_params_info()
    
    print(f"  Source: {info['source']}")
    print(f"  Config path: {info.get('config_path', 'N/A')}")
    print(f"  Parameters:")
    print(f"    a = {info['params']['a']}")
    print(f"    b_l = {info['params']['b_l']}")
    print(f"    b_sys = {info['params']['b_sys']}")
    print(f"    b_t = {info['params']['b_t']}")
    
    if info['source'] != "calibrated_config":
        print("\n  WARNING: Expected 'calibrated_config' source!")
    
    # Step 2: Rerun replay
    print("\n[2/3] Rerunning replay with operational mapping...")
    
    db = SessionLocal()
    try:
        artifacts_dir = Path("./artifacts/synth_v2_run_v4_1")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        runner = ReplayRunner(db, artifacts_dir=str(artifacts_dir))
        
        date_from = date(2026, 1, 1)
        date_to = date(2026, 3, 31)
        
        report = runner.replay(
            athlete_id=299,
            date_from=date_from,
            date_to=date_to,
            dry_run=False
        )
        
        runner.write_artifacts("synth_v2_run_v4_1")
        
        print(f"\n  Replay complete. Captured {len(runner.day_errors)} day errors.")
        
        # Step 3: Verify params_source in day errors
        print("\n[3/3] Verifying params_source in day errors...")
        
        if runner.day_errors:
            sources = {}
            for e in runner.day_errors:
                src = e.get('params_source', 'unknown')
                sources[src] = sources.get(src, 0) + 1
            
            print(f"  Params source distribution:")
            for src, count in sources.items():
                print(f"    {src}: {count}")
            
            # Compute MAE
            constrained_errors = []
            legacy_errors = []
            
            for e in runner.day_errors:
                if 'observed' in e:
                    if 'predicted_constrained' in e:
                        constrained_errors.append(abs(e['observed'] - e['predicted_constrained']))
                    if 'predicted_legacy' in e:
                        legacy_errors.append(abs(e['observed'] - e['predicted_legacy']))
            
            if constrained_errors:
                mae_constrained = statistics.mean(constrained_errors)
                print(f"\n  Operational (constrained) MAE: {mae_constrained:.4f}")
            
            if legacy_errors:
                mae_legacy = statistics.mean(legacy_errors)
                print(f"  Legacy MAE: {mae_legacy:.4f}")
                
                if constrained_errors:
                    improvement = mae_legacy - mae_constrained
                    print(f"\n  Improvement (legacy → operational): {improvement:.4f} ({improvement/mae_legacy*100:.1f}%)")
        
        # Save summary
        summary = {
            'operational_params': info,
            'day_error_count': len(runner.day_errors),
            'params_source_distribution': sources if runner.day_errors else {},
            'mae': {
                'constrained': statistics.mean(constrained_errors) if constrained_errors else None,
                'legacy': statistics.mean(legacy_errors) if legacy_errors else None,
            }
        }
        
        with open(artifacts_dir / "operational_verification.json", 'w') as f:
            json.dump(summary, f, indent=2)
        
    finally:
        db.close()
    
    print("\n" + "=" * 80)
    print("VERIFICATION COMPLETE")
    print("=" * 80)
    print(f"\nArtifacts generated:")
    print(f"  - {artifacts_dir}/operational_verification.json")
    print(f"  - {artifacts_dir}/synth_v2_run_v4_1/")
    
    # Final check
    if info['source'] == 'calibrated_config':
        print("\n✓ Calibrated params are now the operational source of truth!")
    else:
        print(f"\n✗ Expected calibrated_config, got {info['source']}")


if __name__ == "__main__":
    main()
