#!/usr/bin/env python3
"""
Comprehensive evaluation script for strength data.
"""
import json
import csv
from datetime import date
from pathlib import Path
from collections import defaultdict

import sys
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from app.database import SessionLocal
from app import models

def main():
    db = SessionLocal()
    athlete_id = 1
    
    # Create artifacts dir
    artifacts_dir = Path('./artifacts/eval_strength_2026_01')
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Get all sessions
    sessions = db.query(models.StrengthSession).filter(
        models.StrengthSession.athlete_id == athlete_id
    ).order_by(models.StrengthSession.start_time).all()
    
    if not sessions:
        print("No sessions found!")
        return
    
    from_date = sessions[0].start_time.date()
    to_date = sessions[-1].start_time.date()
    
    print('='*60)
    print('CONCURRENT-TRAINING EVALUATION REPORT')
    print('='*60)
    print(f'Athlete: {athlete_id}')
    print(f'Date Range: {from_date} to {to_date}')
    print(f'Total Sessions: {len(sessions)}')
    
    # DATA QUALITY TABLE
    print('\n' + '='*60)
    print('1. DATA QUALITY TABLE')
    print('='*60)
    
    lift_data = defaultdict(lambda: {
        'sessions': 0, 'sets': 0, 'reps': 0, 
        'with_vel': 0, 'total_sets': 0, 'missing_load': 0,
        'missing_rest': 0
    })
    
    for s in sessions:
        lift = s.lift.value
        lift_data[lift]['sessions'] += 1
        
        raw = s.raw_data or {}
        sets = raw.get('sets', [])
        lift_data[lift]['sets'] += len(sets)
        
        for set_data in sets:
            reps = set_data.get('reps', 0)
            vels = set_data.get('velocities', [])
            load = set_data.get('load_kg', 0)
            rest = set_data.get('rest_sec')
            
            lift_data[lift]['reps'] += reps
            lift_data[lift]['total_sets'] += 1
            
            if len(vels) >= 2:
                lift_data[lift]['with_vel'] += 1
            if load == 0:
                lift_data[lift]['missing_load'] += 1
            if rest is None:
                lift_data[lift]['missing_rest'] += 1
    
    print(f"{'Lift':<15} {'Sess':>6} {'Sets':>6} {'Reps':>8} {'Vel>=2':>8} {'Cov%':>8}")
    print('-'*60)
    for lift in sorted(lift_data.keys()):
        d = lift_data[lift]
        cov = (d['with_vel'] / max(d['total_sets'], 1)) * 100
        print(f"{lift:<15} {d['sessions']:>6} {d['sets']:>6} {d['reps']:>8} {d['with_vel']:>8} {cov:>7.1f}%")
    
    # REPS DISTRIBUTION
    print('\n' + '='*60)
    print('2. REPS DISTRIBUTION')
    print('='*60)
    
    reps_dist = defaultdict(int)
    for s in sessions:
        raw = s.raw_data or {}
        for set_data in raw.get('sets', []):
            reps = set_data.get('reps', 0)
            reps_dist[reps] += 1
    
    max_count = max(reps_dist.values()) if reps_dist else 1
    for reps in sorted(reps_dist.keys()):
        count = reps_dist[reps]
        bar_len = int((count / max_count) * 25)
        bar = '█' * bar_len
        print(f"{reps:>3} reps: {count:>4} sets {bar}")
    
    # Save summary
    summary = {
        'athlete_id': athlete_id,
        'date_range': [str(from_date), str(to_date)],
        'total_sessions': len(sessions),
        'lift_data': dict(lift_data),
        'reps_distribution': dict(reps_dist)
    }
    
    with open(artifacts_dir / 'summary.json', 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    print(f'\n✓ Summary saved to: {artifacts_dir}/summary.json')

if __name__ == '__main__':
    main()
