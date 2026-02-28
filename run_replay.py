#!/usr/bin/env python3
"""
Replay and validation runner for strength data.
"""
import json
import csv
from datetime import date
from pathlib import Path
from collections import defaultdict
import statistics

import sys
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from app.database import SessionLocal
from app import models
from app.eval.replay import ReplayRunner
from app.services.engine_orchestrator import EngineOrchestrator

def main():
    db = SessionLocal()
    athlete_id = 1
    
    artifacts_dir = Path('./artifacts/eval_strength_2026_01')
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Get sessions
    sessions = db.query(models.StrengthSession).filter(
        models.StrengthSession.athlete_id == athlete_id
    ).order_by(models.StrengthSession.start_time).all()
    
    from_date = sessions[0].start_time.date()
    to_date = sessions[-1].start_time.date()
    
    print('='*60)
    print('3. REPLAY & VALIDATION ANALYSIS')
    print('='*60)
    
    # Get all rep-level data from sessions
    rep_predictions = []
    day_states = []
    
    for s in sessions:
        raw = s.raw_data or {}
        rep_log = s.rep_level_log or []
        
        # Process rep-level log if available
        for entry in rep_log:
            pred = {
                'session_id': s.id,
                'lift': s.lift.value,
                'date': s.start_time.date().isoformat(),
                'set_idx': entry.get('set_idx', 0),
                'rep_idx': entry.get('rep_idx', 0),
                'A_l': entry.get('A_l'),
                'A_sys': entry.get('A_sys'),
                'A_M': entry.get('A_M'),
            }
            rep_predictions.append(pred)
    
    print(f"Rep-level entries collected: {len(rep_predictions)}")
    
    # Get day states
    day_states_db = db.query(models.DayState).filter(
        models.DayState.athlete_id == athlete_id
    ).order_by(models.DayState.date).all()
    
    print(f"Day states collected: {len(day_states_db)}")
    
    # Create day-level data
    day_data = []
    for ds in day_states_db:
        day_entry = {
            'date': ds.date,
            'D_sys': ds.D_sys,
            'R_mito': ds.R_mito,
            'E_fat': ds.E_fat,
            'T_legs': ds.T_legs
        }
        
        # Get per-lift states
        lift_states = db.query(models.LiftDayState).filter(
            models.LiftDayState.athlete_id == athlete_id,
            models.LiftDayState.date == ds.date
        ).all()
        
        for ls in lift_states:
            day_entry[f"D_l_{ls.lift.value}"] = ls.D_l
            day_entry[f"F_l_{ls.lift.value}"] = ls.F_l
            day_entry[f"C_l_{ls.lift.value}"] = ls.C_l
        
        day_data.append(day_entry)
    
    # Save day states
    with open(artifacts_dir / 'day_states.json', 'w') as f:
        json.dump(day_data, f, indent=2)
    
    # Calculate basic metrics
    print('\n' + '='*60)
    print('4. METRICS SUMMARY')
    print('='*60)
    
    # Per-lift breakdown
    lift_metrics = defaultdict(lambda: {'sessions': 0, 'tonnage': 0, 'avg_intensity': []})
    
    for s in sessions:
        lift = s.lift.value
        lift_metrics[lift]['sessions'] += 1
        lift_metrics[lift]['tonnage'] += s.tonnage
        lift_metrics[lift]['avg_intensity'].append(s.avg_intensity)
    
    print(f"{'Lift':<15} {'Sessions':>10} {'Tonnage':>12} {'Avg Int':>10}")
    print('-'*60)
    for lift in sorted(lift_metrics.keys()):
        m = lift_metrics[lift]
        avg_int = sum(m['avg_intensity']) / len(m['avg_intensity']) if m['avg_intensity'] else 0
        print(f"{lift:<15} {m['sessions']:>10} {m['tonnage']:>12.1f} {avg_int:>10.2f}")
    
    # Save trend eval
    trend_eval = {
        'athlete_id': athlete_id,
        'date_range': [str(from_date), str(to_date)],
        'total_sessions': len(sessions),
        'day_states_tracked': len(day_data),
        'lift_metrics': dict(lift_metrics),
        'notes': [
            'No VBT data available (velocity coverage 0%)',
            'Rep-level predictions based on model internal state',
            'Day-level states tracked via EngineOrchestrator'
        ]
    }
    
    with open(artifacts_dir / 'trend_eval.json', 'w') as f:
        json.dump(trend_eval, f, indent=2, default=str)
    
    print(f'\n✓ Trend eval saved to: {artifacts_dir}/trend_eval.json')
    
    # List all artifacts
    print('\n' + '='*60)
    print('5. ARTIFACTS GENERATED')
    print('='*60)
    for f in sorted(artifacts_dir.iterdir()):
        size = f.stat().st_size
        print(f"  {f.name:<30} {size:>10} bytes")

if __name__ == '__main__':
    main()
