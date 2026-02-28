#!/usr/bin/env python3
"""
Generate error CSV files for evaluation.
"""
import csv
from pathlib import Path

import sys
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from app.database import SessionLocal
from app import models

def main():
    db = SessionLocal()
    athlete_id = 1
    
    artifacts_dir = Path('./artifacts/eval_strength_2026_01')
    
    # Since we don't have ground truth, create template/error structure
    # showing what would be tracked with VBT data
    
    # Rep-level errors (placeholder structure)
    rep_errors = []
    sessions = db.query(models.StrengthSession).filter(
        models.StrengthSession.athlete_id == athlete_id
    ).all()
    
    for s in sessions:
        raw = s.raw_data or {}
        rep_log = s.rep_level_log or []
        
        for entry in rep_log:
            rep_errors.append({
                'session_id': s.id,
                'date': s.start_time.date().isoformat(),
                'lift': s.lift.value,
                'set_idx': entry.get('set_idx', 0),
                'rep_idx': entry.get('rep_idx', 0),
                'predicted_velocity': entry.get('v_pred_next', 'N/A'),
                'actual_velocity': 'NO_GROUND_TRUTH',
                'error': 'N/A',
                'abs_error': 'N/A',
                'A_local': entry.get('A_l', 'N/A'),
                'A_sys': entry.get('A_sys', 'N/A'),
                'A_M': entry.get('A_M', 'N/A'),
                'note': 'VBT data required for error calculation'
            })
    
    # Write rep_errors.csv
    with open(artifacts_dir / 'rep_errors.csv', 'w', newline='') as f:
        if rep_errors:
            writer = csv.DictWriter(f, fieldnames=rep_errors[0].keys())
            writer.writeheader()
            writer.writerows(rep_errors)
        else:
            f.write('session_id,date,lift,set_idx,rep_idx,predicted_velocity,actual_velocity,error,abs_error,A_local,A_sys,A_M,note\n')
            f.write('N/A,N/A,N/A,N/A,N/A,N/A,NO_DATA,NO_DATA,NO_DATA,N/A,N/A,N/A,No rep-level log available\n')
    
    # Day-level errors
    day_states = db.query(models.DayState).filter(
        models.DayState.athlete_id == athlete_id
    ).order_by(models.DayState.date).all()
    
    day_errors = []
    for ds in day_states:
        # Get readiness for this day
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.domain.day_engine import compute_readiness
        from app.domain.day_engine import DayState as DomainDayState, PerLiftState
        
        # Build domain state
        lift_states = db.query(models.LiftDayState).filter(
            models.LiftDayState.athlete_id == athlete_id,
            models.LiftDayState.date == ds.date
        ).all()
        
        per_lift = {}
        for ls in lift_states:
            per_lift[ls.lift.value] = PerLiftState(D_l=ls.D_l, F_l=ls.F_l, C_l=ls.C_l)
        
        domain_state = DomainDayState(
            date=ds.date,
            per_lift=per_lift,
            D_sys=ds.D_sys,
            R_mito=ds.R_mito,
            E_fat=ds.E_fat,
            T_legs=ds.T_legs
        )
        
        from app.domain.day_engine import DayEngineParams
        params = DayEngineParams()
        readiness = compute_readiness(domain_state, params)
        
        day_errors.append({
            'date': ds.date,
            'D_sys': ds.D_sys,
            'R_mito': ds.R_mito,
            'E_fat': ds.E_fat,
            'T_legs': ds.T_legs,
            'readiness_overall': readiness.overall,
            'predicted_readiness': 'N/A',
            'actual_readiness': 'NO_GROUND_TRUTH',
            'error': 'N/A',
            'note': 'Subjective readiness scores required for validation'
        })
    
    # Write day_errors.csv
    with open(artifacts_dir / 'day_errors.csv', 'w', newline='') as f:
        if day_errors:
            writer = csv.DictWriter(f, fieldnames=day_errors[0].keys())
            writer.writeheader()
            writer.writerows(day_errors)
    
    print('='*60)
    print('ERROR CSV FILES GENERATED')
    print('='*60)
    print(f'  rep_errors.csv: {len(rep_errors)} entries')
    print(f'  day_errors.csv: {len(day_errors)} entries')
    print()
    print('Note: Ground truth data not available in current dataset.')
    print('      These files show the structure for when VBT/subjective')
    print('      data becomes available.')

if __name__ == '__main__':
    main()
