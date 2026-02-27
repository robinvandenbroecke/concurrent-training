"""
Sprint V1: GoldenCheetah OpenData Adapter (Minimal)

Parses GoldenCheetah activity summaries and creates EnduranceSession records.
"""
import json
import csv
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

from app.types import EnduranceSport


@dataclass
class GCActivity:
    """Parsed GoldenCheetah activity summary."""
    activity_id: str
    sport: str
    start_date: date
    duration_minutes: float
    distance_km: Optional[float] = None
    avg_power: Optional[float] = None
    np_power: Optional[float] = None  # Normalized power
    avg_hr: Optional[float] = None
    tss: Optional[float] = None  # Training Stress Score
    intensity_factor: Optional[float] = None
    
    def to_session_dict(self, athlete_id: int) -> Optional[Dict]:
        """Convert to EnduranceSession-compatible dict."""
        # Map sport
        sport_map = {
            "bike": EnduranceSport.CYCLING,
            "cycling": EnduranceSport.CYCLING,
            "run": EnduranceSport.RUNNING,
            "running": EnduranceSport.RUNNING,
            "swim": EnduranceSport.SWIMMING,
            "swimming": EnduranceSport.SWIMMING,
        }
        
        sport = sport_map.get(self.sport.lower())
        if sport is None:
            return None
        
        # Intensity type from TSS/duration or IF
        intensity = "z2"  # Default
        if self.tss and self.duration_minutes > 0:
            tss_per_hour = self.tss / (self.duration_minutes / 60)
            if tss_per_hour > 70:  # High stress
                intensity = "hiit"
            elif tss_per_hour > 50:  # Moderate
                intensity = "mixed"
        elif self.intensity_factor:
            if self.intensity_factor > 0.9:
                intensity = "hiit"
            elif self.intensity_factor > 0.75:
                intensity = "mixed"
        
        return {
            "athlete_id": athlete_id,
            "sport": sport,
            "start_time": datetime.combine(self.start_date, datetime.min.time()),
            "duration_minutes": round(self.duration_minutes, 1),
            "intensity_type": intensity,
            "raw_data": {
                "gc_id": self.activity_id,
                "distance_km": self.distance_km,
                "avg_power": self.avg_power,
                "np_power": self.np_power,
                "avg_hr": self.avg_hr,
                "tss": self.tss,
                "intensity_factor": self.intensity_factor,
            }
        }


class GoldenCheetahAdapter:
    """
    Minimal GoldenCheetah OpenData adapter.
    
    Reads precomputed activity summaries from JSON or CSV.
    Does NOT parse .fit/.tcx files directly (summary-only for V1).
    """
    
    def __init__(self, data_path: str):
        self.data_path = Path(data_path)
        self.activities: List[GCActivity] = []
    
    def parse_json_summaries(self, filename: str = "activities.json") -> List[GCActivity]:
        """Parse activities from JSON summary file."""
        json_file = self.data_path / filename
        
        if not json_file.exists():
            raise FileNotFoundError(f"JSON file not found: {json_file}")
        
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        # Handle both list format and dict format
        activities_list = data if isinstance(data, list) else data.get("activities", [])
        
        for act in activities_list:
            activity = self._parse_json_activity(act)
            if activity:
                self.activities.append(activity)
        
        return self.activities
    
    def parse_csv_summaries(self, filename: str = "activities.csv") -> List[GCActivity]:
        """Parse activities from CSV summary file."""
        csv_file = self.data_path / filename
        
        if not csv_file.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_file}")
        
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                activity = self._parse_csv_activity(row)
                if activity:
                    self.activities.append(activity)
        
        return self.activities
    
    def _parse_json_activity(self, data: Dict) -> Optional[GCActivity]:
        """Parse a single JSON activity object."""
        activity_id = str(data.get("id", ""))
        sport = data.get("sport", data.get(" Sport", "")).strip()
        
        if not sport:
            return None
        
        # Parse date
        date_str = data.get("date", data.get("start", ""))
        start_date = self._parse_date(date_str)
        if not start_date:
            return None
        
        # Parse duration (seconds to minutes)
        duration_sec = data.get("duration", data.get("Duration", 0))
        try:
            duration_minutes = float(duration_sec) / 60.0
        except (ValueError, TypeError):
            duration_minutes = 0.0
        
        if duration_minutes <= 0:
            return None
        
        # Optional metrics
        distance = data.get("distance", data.get("Distance"))
        distance_km = float(distance) / 1000.0 if distance else None
        
        avg_power = self._safe_float(data.get("average_power", data.get("Avg Power")))
        np_power = self._safe_float(data.get("normalized_power", data.get("NP")))
        avg_hr = self._safe_float(data.get("average_hr", data.get("Avg HR")))
        tss = self._safe_float(data.get("tss", data.get("TSS")))
        if_ = self._safe_float(data.get("intensity_factor", data.get("IF")))
        
        return GCActivity(
            activity_id=activity_id,
            sport=sport,
            start_date=start_date,
            duration_minutes=duration_minutes,
            distance_km=distance_km,
            avg_power=avg_power,
            np_power=np_power,
            avg_hr=avg_hr,
            tss=tss,
            intensity_factor=if_
        )
    
    def _parse_csv_activity(self, row: Dict[str, str]) -> Optional[GCActivity]:
        """Parse a single CSV activity row."""
        # Try various column name conventions
        activity_id = row.get("id", row.get("ID", "")).strip()
        sport = row.get("sport", row.get("Sport", row.get(" Sport", ""))).strip()
        
        if not sport:
            return None
        
        # Parse date
        date_str = row.get("date", row.get("Date", row.get("start", "")))
        start_date = self._parse_date(date_str)
        if not start_date:
            return None
        
        # Parse duration
        duration_str = row.get("duration", row.get("Duration", "0"))
        try:
            duration_minutes = float(duration_str) / 60.0
        except (ValueError, TypeError):
            duration_minutes = 0.0
        
        if duration_minutes <= 0:
            return None
        
        # Optional fields
        distance_km = self._safe_float(row.get("distance", row.get("Distance")))
        if distance_km and distance_km > 1000:  # Likely in meters
            distance_km = distance_km / 1000.0
        
        avg_power = self._safe_float(row.get("average_power", row.get("Avg Power")))
        np_power = self._safe_float(row.get("normalized_power", row.get("NP")))
        avg_hr = self._safe_float(row.get("average_hr", row.get("Avg HR")))
        tss = self._safe_float(row.get("tss", row.get("TSS")))
        if_ = self._safe_float(row.get("intensity_factor", row.get("IF")))
        
        return GCActivity(
            activity_id=activity_id,
            sport=sport,
            start_date=start_date,
            duration_minutes=duration_minutes,
            distance_km=distance_km,
            avg_power=avg_power,
            np_power=np_power,
            avg_hr=avg_hr,
            tss=tss,
            intensity_factor=if_
        )
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date from various formats."""
        if not date_str:
            return None
        
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.date()
            except ValueError:
                continue
        
        return None
    
    def _safe_float(self, value) -> Optional[float]:
        """Safely convert to float."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def import_to_db(self, db_session, athlete_id: int, file_format: str = "json") -> int:
        """
        Import parsed activities to database.
        
        Args:
            db_session: Database session
            athlete_id: Athlete to import for
            file_format: "json" or "csv"
        
        Returns:
            Number of sessions imported
        """
        from app import models
        
        if not self.activities:
            if file_format == "json":
                self.parse_json_summaries()
            else:
                self.parse_csv_summaries()
        
        count = 0
        for activity in self.activities:
            session_dict = activity.to_session_dict(athlete_id)
            if not session_dict:
                continue
            
            # Check for existing
            existing = db_session.query(models.EnduranceSession).filter(
                models.EnduranceSession.athlete_id == athlete_id,
                models.EnduranceSession.start_time == session_dict["start_time"],
                models.EnduranceSession.duration_minutes == session_dict["duration_minutes"]
            ).first()
            
            if existing:
                continue
            
            session = models.EnduranceSession(**session_dict)
            db_session.add(session)
            count += 1
        
        db_session.commit()
        return count


# For CLI usage
def import_gc_data(
    data_path: str,
    athlete_id: int,
    db_session,
    file_format: str = "json"
) -> int:
    """
    Import GoldenCheetah data.
    
    Args:
        data_path: Path to GoldenCheetah data directory
        athlete_id: Athlete to import for
        db_session: Database session
        file_format: "json" or "csv"
    
    Returns:
        Number of sessions imported
    """
    adapter = GoldenCheetahAdapter(data_path)
    return adapter.import_to_db(db_session, athlete_id, file_format)
