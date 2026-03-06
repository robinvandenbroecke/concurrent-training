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
from app.domain.day_engine import PerLiftState, DayState

def main():
    db = SessionLocal()
    athlete_id = 1
    
    artifacts_dir = Path('./artifacts/eval_strength_2026_01')
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Get sessions
    sessions = db.query(models.StrengthSession).filter(
        models.StrengthSession.athlete_id == athlete_id
    ).order_by(models.StrengthSession.start_time).all()
    
    # Get endurance sessions too
    endurance_sessions = db.query(models.EnduranceSession).filter(
        models.EnduranceSession.athlete_id == athlete_id
    ).order_by(models.EnduranceSession.start_time).all()
    
    from_date = min(sessions[0].start_time.date(), endurance_sessions[0].start_time.date()) if endurance_sessions else sessions[0].start_time.date()
    to_date = max(sessions[-1].start_time.date(), endurance_sessions[-1].start_time.date()) if endurance_sessions else sessions[-1].start_time.date()
    
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
    
    # v9.2: Get day states from DB with carryover for missing days
    from datetime import timedelta
    from app.services.engine_orchestrator import EngineOrchestrator
    
    orchestrator = EngineOrchestrator(db)
    
    # Query day states from DB for each calendar day
    day_data = []
    current_date = from_date
    previous_state = None
    
    while current_date <= to_date:
        date_str = current_date.isoformat()
        
        # First check if day state exists in DB
        day_state_db = db.query(models.DayState).filter(
            models.DayState.athlete_id == athlete_id,
            models.DayState.date == date_str
        ).first()
        
        if day_state_db:
            # Use DB state directly
            lift_states_db = db.query(models.LiftDayState).filter(
                models.LiftDayState.athlete_id == athlete_id,
                models.LiftDayState.date == date_str
            ).all()
            
            per_lift = {}
            for ls in lift_states_db:
                per_lift[ls.lift.value] = PerLiftState(
                    D_l=ls.D_l,
                    F_l=ls.F_l,
                    C_l=ls.C_l
                )
            
            day_state = DayState(
                date=current_date,
                per_lift=per_lift,
                D_sys=day_state_db.D_sys,
                R_mito=day_state_db.R_mito,
                E_fat=day_state_db.E_fat,
                T_legs=getattr(day_state_db, 'T_legs', 0.0)
            )
            previous_state = day_state
        elif previous_state:
            # Decay from previous state
            from app.domain.day_engine import decay_day_state_to_date, DayEngineParams
            day_state = decay_day_state_to_date(previous_state, current_date, DayEngineParams())
        else:
            # No prior state - skip
            current_date += timedelta(days=1)
            continue
        
        day_entry = {
            'date': current_date.isoformat(),
            'D_sys': day_state.D_sys,
            'R_mito': day_state.R_mito,
            'E_fat': day_state.E_fat,
            'T_legs': day_state.T_legs
        }
        
        # Add per-lift states
        for lift, lift_state in day_state.per_lift.items():
            day_entry[f"D_l_{lift}"] = lift_state.D_l
            day_entry[f"F_l_{lift}"] = lift_state.F_l
            day_entry[f"C_l_{lift}"] = lift_state.C_l
        
        day_data.append(day_entry)
        current_date += timedelta(days=1)
    
    print(f"Day states collected: {len(day_data)} (from DB with carryover)")
    
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
    
    # Endurance summary
    if endurance_sessions:
        print()
        print(f"{'Sport':<15} {'Sessions':>10} {'Duration':>12} {'Z2/HIIT':>10}")
        print('-'*60)
        
        sport_metrics = defaultdict(lambda: {'sessions': 0, 'duration': 0, 'z2': 0, 'hiit': 0})
        for e in endurance_sessions:
            sport = e.sport.value
            sport_metrics[sport]['sessions'] += 1
            sport_metrics[sport]['duration'] += e.duration_minutes
            if e.u_E_HIIT > 0:
                sport_metrics[sport]['hiit'] += 1
            else:
                sport_metrics[sport]['z2'] += 1
        
        for sport in sorted(sport_metrics.keys()):
            m = sport_metrics[sport]
            z2_hiit = f"{m['z2']}Z2/{m['hiit']}HIIT"
            print(f"{sport:<15} {m['sessions']:>10} {m['duration']:>11.0f}m {z2_hiit:>10}")
    
    # Save trend eval
    trend_eval = {
        'athlete_id': athlete_id,
        'date_range': [str(from_date), str(to_date)],
        'total_sessions': len(sessions),
        'total_endurance_sessions': len(endurance_sessions),
        'day_states_tracked': len(day_data),
        'lift_metrics': dict(lift_metrics),
        'sport_metrics': dict(sport_metrics) if endurance_sessions else {},
        'notes': [
            'No VBT data available (velocity coverage 0%)',
            'Rep-level predictions based on model internal state',
            'Day-level states tracked via EngineOrchestrator',
            'Includes both strength and endurance training data'
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
