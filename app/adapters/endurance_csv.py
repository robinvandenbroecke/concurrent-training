"""
Endurance CSV Adapter

Parses endurance training CSV files and creates EnduranceSession records.
Expected CSV format:
    session_date,session_id,sport,duration_min,is_HIIT,tss,best_20min_w,best_5min_w,np_w,avg_w,intensity_json
    2026-01-02,E001,cycling,60,0,55.0,248.0,325.5,240.9,231.3,"{...}"
    ...

Supports:
- Cycling, running, swimming
- Z2 and HIIT classification
- Power metrics for cycling
- Idempotency via content_hash
"""
import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session

from app.types import EnduranceSport
from app.services.engine_orchestrator import EngineOrchestrator


# Sport mapping
SPORT_MAP = {
    "cycling": EnduranceSport.CYCLING,
    "running": EnduranceSport.RUNNING,
    "swimming": EnduranceSport.SWIMMING,
}


@dataclass
class ImportResult:
    """Result of importing endurance sessions."""
    sessions_created: int
    sessions_skipped: int
    errors: List[str]
    session_ids: List[str]


def parse_date(date_str: str) -> Optional[date]:
    """Parse date from various formats."""
    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def compute_content_hash(
    athlete_id: int,
    session_date: date,
    session_id: str,
    sport: str,
    duration: float
) -> str:
    """Compute deterministic content hash for idempotency."""
    content = f"{athlete_id}:{session_date.isoformat()}:{session_id}:{sport}:{duration}"
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def import_endurance_csv(
    db: Session,
    athlete_id: int,
    csv_path: str,
    dry_run: bool = False
) -> ImportResult:
    """
    Import endurance sessions from CSV file.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        csv_path: Path to CSV file
        dry_run: If True, don't actually create records
    
    Returns:
        ImportResult with statistics
    """
    result = ImportResult(
        sessions_created=0,
        sessions_skipped=0,
        errors=[],
        session_ids=[]
    )
    
    orchestrator = EngineOrchestrator(db)
    path = Path(csv_path)
    
    if not path.exists():
        result.errors.append(f"File not found: {csv_path}")
        return result
    
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row_num, row in enumerate(reader, start=2):
            try:
                # Parse required fields
                session_date = parse_date(row.get('session_date', ''))
                if not session_date:
                    result.errors.append(f"Row {row_num}: Invalid date")
                    continue
                
                session_id = row.get('session_id', '').strip()
                if not session_id:
                    result.errors.append(f"Row {row_num}: Missing session_id")
                    continue
                
                sport_str = row.get('sport', '').lower().strip()
                sport = SPORT_MAP.get(sport_str)
                if not sport:
                    result.errors.append(f"Row {row_num}: Unknown sport '{sport_str}'")
                    continue
                
                duration = float(row.get('duration_min', 0))
                if duration <= 0:
                    result.errors.append(f"Row {row_num}: Invalid duration")
                    continue
                
                # Parse HIIT flag
                is_hiit = int(row.get('is_HIIT', 0)) == 1
                intensity_type = 'hiit' if is_hiit else 'z2'
                
                # Parse optional metrics
                tss = float(row.get('tss', 0)) if row.get('tss') else 0
                best_20min_w = float(row.get('best_20min_w', 0)) if row.get('best_20min_w') else None
                best_5min_w = float(row.get('best_5min_w', 0)) if row.get('best_5min_w') else None
                np_w = float(row.get('np_w', 0)) if row.get('np_w') else None
                avg_w = float(row.get('avg_w', 0)) if row.get('avg_w') else None
                
                # Parse intensity_json if present
                intensity_json = row.get('intensity_json', '{}')
                try:
                    # Handle double-escaped JSON
                    intensity_data = json.loads(intensity_json.replace('""', '"'))
                except:
                    intensity_data = {}
                
                # Compute content hash for idempotency
                content_hash = compute_content_hash(
                    athlete_id, session_date, session_id, sport_str, duration
                )
                
                # Check for existing session
                from app import models
                existing = db.query(models.EnduranceSession).filter(
                    models.EnduranceSession.athlete_id == athlete_id,
                    models.EnduranceSession.content_hash == content_hash
                ).first()
                
                if existing:
                    result.sessions_skipped += 1
                    result.session_ids.append(f"{session_id} (skipped)")
                    continue
                
                if dry_run:
                    result.sessions_created += 1
                    result.session_ids.append(f"{session_id} (dry-run)")
                    continue
                
                # Ingest via orchestrator
                session, day_state, _ = orchestrator.ingest_endurance_session(
                    athlete_id=athlete_id,
                    session_date=session_date,
                    sport=sport,
                    duration_minutes=duration,
                    intensity_type=intensity_type
                )
                
                # Update session with additional data
                session.content_hash = content_hash
                session.raw_data = {
                    'session_id': session_id,
                    'tss': tss,
                    'best_20min_w': best_20min_w,
                    'best_5min_w': best_5min_w,
                    'np_w': np_w,
                    'avg_w': avg_w,
                    'intensity_json': intensity_data
                }
                
                db.commit()
                result.sessions_created += 1
                result.session_ids.append(session_id)
                
            except Exception as e:
                result.errors.append(f"Row {row_num}: {str(e)}")
                continue
    
    return result
