"""
Sprint V1: Strava Bulk Export Adapter (Minimal)

Parses Strava bulk export zip file and creates EnduranceSession records.
"""
import csv
import zipfile
import json
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional, Iterator
import re

from app.types import EnduranceSport


def parse_strava_sport(activity_type: str) -> Optional[EnduranceSport]:
    """Map Strava activity type to our EnduranceSport enum."""
    activity_lower = activity_type.lower()
    
    if "ride" in activity_lower or "cycle" in activity_lower or "bike" in activity_lower:
        return EnduranceSport.CYCLING
    elif "run" in activity_lower:
        return EnduranceSport.RUNNING
    elif "swim" in activity_lower:
        return EnduranceSport.SWIMMING
    
    return None


def is_hiit_heuristic(activity_name: str, activity_type: str) -> bool:
    """
    Simple heuristic to detect HIIT sessions.
    
    Checks for keywords in activity name or type.
    """
    text = f"{activity_name} {activity_type}".lower()
    hiit_keywords = [
        "interval", "hiit", "sprint", "tabata", "ftp", "threshold",
        "race", "competition", "crit", "criterium"
    ]
    return any(kw in text for kw in hiit_keywords)


def parse_duration(elapsed_time_str: str) -> float:
    """Parse duration string to minutes."""
    try:
        # Try as float (seconds)
        seconds = float(elapsed_time_str)
        return seconds / 60.0
    except (ValueError, TypeError):
        # Try as HH:MM:SS or MM:SS
        parts = elapsed_time_str.split(":")
        if len(parts) == 3:  # HH:MM:SS
            return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60.0
        elif len(parts) == 2:  # MM:SS
            return int(parts[0]) + int(parts[1]) / 60.0
        return 0.0


def parse_date(date_str: str) -> Optional[date]:
    """Parse date from various formats."""
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.date()
        except ValueError:
            continue
    
    return None


@dataclass
class StravaActivity:
    """Parsed Strava activity."""
    activity_id: str
    name: str
    activity_type: str
    start_date: date
    duration_minutes: float
    distance_km: Optional[float] = None
    avg_hr: Optional[float] = None
    max_hr: Optional[float] = None
    avg_power: Optional[float] = None
    is_hiit: bool = False
    
    def to_session_dict(self, athlete_id: int) -> Dict:
        """Convert to EnduranceSession-compatible dict."""
        sport = parse_strava_sport(self.activity_type)
        if sport is None:
            return None
        
        # Intensity type heuristic
        if self.is_hiit:
            intensity = "hiit"
        elif self.avg_power and self.avg_power > 200:  # Arbitrary threshold
            intensity = "hiit"
        else:
            intensity = "z2"
        
        return {
            "athlete_id": athlete_id,
            "sport": sport,
            "start_time": datetime.combine(self.start_date, datetime.min.time()),
            "duration_minutes": round(self.duration_minutes, 1),
            "intensity_type": intensity,
            "raw_data": {
                "strava_id": self.activity_id,
                "name": self.name,
                "distance_km": self.distance_km,
                "avg_hr": self.avg_hr,
                "max_hr": self.max_hr,
                "avg_power": self.avg_power,
            }
        }


class StravaExportAdapter:
    """
    Minimal Strava bulk export adapter.
    
    Parses activities.csv from Strava export zip.
    Does NOT parse TCX/FIT files (summary-only).
    """
    
    def __init__(self, zip_path: str):
        self.zip_path = Path(zip_path)
        self.activities: List[StravaActivity] = []
    
    def parse(self) -> List[StravaActivity]:
        """Parse all activities from zip file."""
        if not self.zip_path.exists():
            raise FileNotFoundError(f"Zip file not found: {self.zip_path}")
        
        with zipfile.ZipFile(self.zip_path, 'r') as zf:
            # Find activities.csv
            activities_file = None
            for name in zf.namelist():
                if name.lower().endswith('activities.csv'):
                    activities_file = name
                    break
            
            if not activities_file:
                raise ValueError("No activities.csv found in zip file")
            
            # Parse CSV
            with zf.open(activities_file) as f:
                # Read as text (handle encoding)
                content = f.read().decode('utf-8', errors='replace')
                lines = content.splitlines()
                
                reader = csv.DictReader(lines)
                
                for row in reader:
                    activity = self._parse_row(row)
                    if activity:
                        self.activities.append(activity)
        
        return self.activities
    
    def _parse_row(self, row: Dict[str, str]) -> Optional[StravaActivity]:
        """Parse a single activity row."""
        # Required fields
        activity_id = row.get("Activity ID", "").strip()
        name = row.get("Activity Name", "").strip()
        activity_type = row.get("Activity Type", "").strip()
        
        if not activity_id or not activity_type:
            return None
        
        # Parse date
        date_str = row.get("Activity Date", "")
        start_date = parse_date(date_str)
        if not start_date:
            return None
        
        # Parse duration
        elapsed_time = row.get("Elapsed Time", "0")
        duration_minutes = parse_duration(elapsed_time)
        
        if duration_minutes <= 0:
            return None
        
        # Optional fields
        distance_str = row.get("Distance", "")
        distance_km = None
        try:
            distance_km = float(distance_str) / 1000.0  # Convert meters to km
        except (ValueError, TypeError):
            pass
        
        avg_hr = None
        max_hr = None
        avg_power = None
        
        try:
            avg_hr = float(row.get("Average Heart Rate", ""))
        except (ValueError, TypeError):
            pass
        
        try:
            max_hr = float(row.get("Max Heart Rate", ""))
        except (ValueError, TypeError):
            pass
        
        try:
            avg_power = float(row.get("Average Watts", ""))
        except (ValueError, TypeError):
            pass
        
        # HIIT heuristic
        is_hiit = is_hiit_heuristic(name, activity_type)
        
        return StravaActivity(
            activity_id=activity_id,
            name=name,
            activity_type=activity_type,
            start_date=start_date,
            duration_minutes=duration_minutes,
            distance_km=distance_km,
            avg_hr=avg_hr,
            max_hr=max_hr,
            avg_power=avg_power,
            is_hiit=is_hiit
        )
    
    def import_to_db(self, db_session, athlete_id: int) -> int:
        """
        Import parsed activities to database.
        
        Returns number of sessions imported.
        """
        from app import models
        
        if not self.activities:
            self.parse()
        
        count = 0
        for activity in self.activities:
            session_dict = activity.to_session_dict(athlete_id)
            if not session_dict:
                continue  # Skip non-endurance activities
            
            # Check for existing session (simple heuristic: same date + sport + duration)
            existing = db_session.query(models.EnduranceSession).filter(
                models.EnduranceSession.athlete_id == athlete_id,
                models.EnduranceSession.start_time == session_dict["start_time"],
                models.EnduranceSession.duration_minutes == session_dict["duration_minutes"]
            ).first()
            
            if existing:
                continue  # Skip duplicate
            
            session = models.EnduranceSession(**session_dict)
            db_session.add(session)
            count += 1
        
        db_session.commit()
        return count


# For CLI usage
def import_strava_export(zip_path: str, athlete_id: int, db_session) -> int:
    """
    Import Strava export zip file.
    
    Args:
        zip_path: Path to Strava export zip
        athlete_id: Athlete to import for
        db_session: Database session
    
    Returns:
        Number of sessions imported
    """
    adapter = StravaExportAdapter(zip_path)
    return adapter.import_to_db(db_session, athlete_id)
