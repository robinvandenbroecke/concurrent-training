"""
Strength CSV Adapter v2

Parses strength training CSV files and creates StrengthSession records.
Expected CSV format:
    session_date,session_id,lift_code,sets,reps,weight_kg,rest_seconds,rpe,velocity_m_per_s
    2024-01-15,sq_001,squat,3,5,100,180,8,0.45
    2024-01-15,sq_001,squat,3,5,100,180,8,0.42
    ...

Supports:
- Multiple sets per session (grouped by session_id)
- Optional velocity data (VBT)
- Optional RPE
- Automatic lift code mapping
- Chronological ingestion with state updates
"""
import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy.orm import Session

from app.types import LiftType
from app.services.engine_orchestrator import EngineOrchestrator


# Lift code mapping (customize as needed)
LIFT_CODE_MAP = {
    "sq": LiftType.SQUAT,
    "squat": LiftType.SQUAT,
    "bp": LiftType.BENCH,
    "bench": LiftType.BENCH,
    "press": LiftType.PRESS,
    "ohp": LiftType.PRESS,
    "shoulder press": LiftType.PRESS,
    "strict shoulder press": LiftType.PRESS,
    "push press": LiftType.PRESS,
    "dl": LiftType.DEADLIFT,
    "deadlift": LiftType.DEADLIFT,
    "romanian deadlift": LiftType.DEADLIFT,
    "pc": LiftType.POWER_CLEAN,
    "clean": LiftType.POWER_CLEAN,
    "power clean": LiftType.POWER_CLEAN,
    "power_clean": LiftType.POWER_CLEAN,
    "other": None,  # Skip unsupported lifts
}


@dataclass
class ParsedSet:
    """Single parsed set from CSV."""
    set_num: int
    reps: int
    weight_kg: float
    rest_seconds: Optional[float]
    rpe: Optional[float]
    velocities: List[float] = field(default_factory=list)


@dataclass
class ParsedSession:
    """Parsed strength session grouped by session_id."""
    session_id: str
    session_date: date
    lift: LiftType
    sets: List[ParsedSet]


@dataclass
class ImportResult:
    """Result of importing strength sessions."""
    sessions_created: int
    sessions_skipped: int
    sets_total: int
    errors: List[str]
    session_ids: List[str]


def parse_lift_code(lift_code: str) -> Optional[LiftType]:
    """Map lift code string to LiftType enum."""
    return LIFT_CODE_MAP.get(lift_code.lower().strip())


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


def parse_velocity(velocity_str: str) -> Optional[float]:
    """Parse velocity string to float."""
    if not velocity_str or velocity_str.strip() == "":
        return None
    try:
        v = float(velocity_str)
        # Sanity check: velocity should be between 0.1 and 1.0 m/s for most lifts
        if 0.05 <= v <= 2.0:
            return v
        return None
    except (ValueError, TypeError):
        return None


def parse_optional_float(value_str: str) -> Optional[float]:
    """Parse optional float value."""
    if not value_str or value_str.strip() == "":
        return None
    try:
        return float(value_str)
    except (ValueError, TypeError):
        return None


def parse_strength_csv(path: str) -> List[ParsedSession]:
    """
    Parse strength CSV file into grouped sessions.
    
    Supports two formats:
    - Legacy: session_date,session_id,lift_code,sets,reps,weight_kg,rest_seconds,rpe,velocity_m_per_s
    - Robin's format: session_date,session_id,session_label,lift,lift_code,set_index,load_kg,reps,rest_sec,rpe,velocities
    
    Args:
        path: Path to CSV file
        
    Returns:
        List of ParsedSession objects, sorted by date
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If CSV format is invalid
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    
    # Read all rows and group by session_id
    rows_by_session: Dict[str, List[Dict]] = {}
    
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        if not reader.fieldnames:
            raise ValueError("CSV file is empty or has no headers")
        
        # Normalize fieldnames (strip whitespace, lowercase)
        fieldnames = [fn.strip().lower() for fn in reader.fieldnames]
        
        # Check which format we're dealing with
        has_robin_format = 'set_index' in fieldnames or 'rest_sec' in fieldnames
        has_legacy_format = 'sets' in fieldnames or 'rest_seconds' in fieldnames
        
        # Required fields depend on format
        if has_robin_format:
            required_fields = ['session_date', 'session_id', 'lift_code', 'set_index', 'reps', 'load_kg']
        else:
            required_fields = ['session_date', 'session_id', 'lift_code', 'sets', 'reps', 'weight_kg']
        
        missing = [f for f in required_fields if f not in fieldnames]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        
        for row_idx, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
            # Normalize keys
            row = {k.strip().lower(): v for k, v in row.items()}
            
            session_id = row.get('session_id', '').strip()
            if not session_id:
                continue  # Skip rows without session_id
            
            # Skip unsupported lifts (lift_code = "other")
            lift_code = row.get('lift_code', '').strip().lower()
            if lift_code == 'other':
                continue
            
            if session_id not in rows_by_session:
                rows_by_session[session_id] = []
            
            rows_by_session[session_id].append((row_idx, row))
    
    # Convert grouped rows to ParsedSession objects
    sessions: List[ParsedSession] = []
    
    for session_id, rows in rows_by_session.items():
        # Get session-level data from first row
        first_row_idx, first_row = rows[0]
        
        # Parse date
        session_date = parse_date(first_row.get('session_date', ''))
        if not session_date:
            raise ValueError(f"Row {first_row_idx}: Invalid date format")
        
        # Parse lift code
        lift = parse_lift_code(first_row.get('lift_code', ''))
        if not lift:
            raise ValueError(f"Row {first_row_idx}: Unknown lift code '{first_row.get('lift_code')}'")
        
        # Parse sets
        sets: List[ParsedSet] = []
        for row_idx, row in rows:
            try:
                # Support both formats for set number
                if 'set_index' in row:
                    set_num = int(row.get('set_index', 0))
                else:
                    set_num = int(row.get('sets', 0))
                
                reps = int(row.get('reps', 0))
                
                # Support both weight_kg and load_kg
                weight_str = row.get('load_kg', row.get('weight_kg', '0'))
                weight_kg = float(weight_str) if weight_str.strip() else 0.0
                
                # Skip rows with invalid weight (e.g., empty load_kg)
                if weight_kg <= 0:
                    continue
                
                # Support both rest_sec and rest_seconds
                rest_str = row.get('rest_sec', row.get('rest_seconds', ''))
                rest_seconds = parse_optional_float(rest_str)
                
                rpe = parse_optional_float(row.get('rpe', ''))
                
                # Parse velocities if present (Robin format has 'velocities' column)
                velocities = []
                vel_str = row.get('velocities', row.get('velocity_m_per_s', ''))
                if vel_str and vel_str.strip():
                    # Try to parse as JSON list first
                    try:
                        # Handle JSON array like "[0.65, 0.62, 0.58, 0.55, 0.52]"
                        import json
                        vel_list = json.loads(vel_str)
                        if isinstance(vel_list, list):
                            for v in vel_list:
                                if isinstance(v, (int, float)) and 0.05 <= v <= 2.0:
                                    velocities.append(float(v))
                        elif isinstance(vel_list, (int, float)):
                            v = float(vel_list)
                            if 0.05 <= v <= 2.0:
                                velocities.append(v)
                    except (json.JSONDecodeError, ValueError, TypeError):
                        # Fall back to single value parsing
                        vel = parse_velocity(vel_str)
                        if vel:
                            velocities.append(vel)
                
                sets.append(ParsedSet(
                    set_num=set_num,
                    reps=reps,
                    weight_kg=weight_kg,
                    rest_seconds=rest_seconds,
                    rpe=rpe,
                    velocities=velocities
                ))
            except (ValueError, TypeError) as e:
                raise ValueError(f"Row {row_idx}: Parse error - {e}")
        
        # Skip sessions with no valid sets
        if not sets:
            continue
        
        # Sort sets by set_num
        sets.sort(key=lambda s: s.set_num)
        
        sessions.append(ParsedSession(
            session_id=session_id,
            session_date=session_date,
            lift=lift,
            sets=sets
        ))
    
    # Sort sessions by date
    sessions.sort(key=lambda s: s.session_date)
    
    return sessions


def convert_to_sets_data(parsed_sets: List[ParsedSet]) -> List[Dict[str, Any]]:
    """
    Convert ParsedSet objects to sets_data format expected by EngineOrchestrator.
    
    Args:
        parsed_sets: List of ParsedSet objects
        
    Returns:
        List of dicts with keys: load_kg, reps, velocities, rest_sec
    """
    sets_data = []
    for i, s in enumerate(parsed_sets):
        set_data = {
            "load_kg": s.weight_kg,
            "reps": s.reps,
            "velocities": s.velocities if s.velocities else [],
            "rest_sec": s.rest_seconds if i > 0 else None,  # No rest before first set
            "rpe": s.rpe,
        }
        sets_data.append(set_data)
    return sets_data


def import_strength_sessions(
    db: Session,
    athlete_id: int,
    parsed_sessions: List[ParsedSession],
    dry_run: bool = False
) -> ImportResult:
    """
    Import parsed strength sessions into database.
    
    Args:
        db: Database session
        athlete_id: Athlete ID to associate sessions with
        parsed_sessions: List of ParsedSession objects
        dry_run: If True, don't actually create records
        
    Returns:
        ImportResult with counts and errors
    """
    orchestrator = EngineOrchestrator(db)
    result = ImportResult(
        sessions_created=0,
        sessions_skipped=0,
        sets_total=0,
        errors=[],
        session_ids=[]
    )
    
    for session in parsed_sessions:
        try:
            # Convert to sets_data format
            sets_data = convert_to_sets_data(session.sets)
            result.sets_total += len(sets_data)
            
            if dry_run:
                result.session_ids.append(session.session_id)
                continue
            
            # Check if athlete has profile for this lift
            from app import models
            profile = db.query(models.LiftProfile).filter(
                models.LiftProfile.athlete_id == athlete_id,
                models.LiftProfile.lift == session.lift
            ).first()
            
            if not profile:
                # Create default profile
                from app.services import AthleteService
                AthleteService.create_athlete(db, f"temp_{athlete_id}")  # Ensure athlete exists
                
                # Re-check profile after creation
                profile = db.query(models.LiftProfile).filter(
                    models.LiftProfile.athlete_id == athlete_id,
                    models.LiftProfile.lift == session.lift
                ).first()
                
                if not profile:
                    result.errors.append(f"No profile for {session.lift.value}, skipping session {session.session_id}")
                    continue
            
            # Ingest via orchestrator
            strength_session, day_state, perf_snapshot = orchestrator.ingest_strength_session(
                athlete_id=athlete_id,
                lift=session.lift,
                session_date=session.session_date,
                sets_data=sets_data,
                vbt_available=any(s.velocities for s in session.sets),
                optional_rpe=session.sets[0].rpe if session.sets else None
            )
            
            if perf_snapshot.get("idempotent"):
                result.sessions_skipped += 1
            else:
                result.sessions_created += 1
                result.session_ids.append(session.session_id)
                
        except Exception as e:
            result.errors.append(f"Session {session.session_id}: {str(e)}")
    
    if not dry_run:
        db.commit()
    
    return result


def import_strength_csv(
    db: Session,
    athlete_id: int,
    csv_path: str,
    dry_run: bool = False
) -> ImportResult:
    """
    Import strength sessions from CSV file.
    
    This is the main entry point - parses CSV and imports sessions.
    
    Args:
        db: Database session
        athlete_id: Athlete ID
        csv_path: Path to CSV file
        dry_run: If True, parse but don't create records
        
    Returns:
        ImportResult with counts and errors
    """
    # Parse CSV
    parsed_sessions = parse_strength_csv(csv_path)
    
    # Import sessions
    return import_strength_sessions(db, athlete_id, parsed_sessions, dry_run)
