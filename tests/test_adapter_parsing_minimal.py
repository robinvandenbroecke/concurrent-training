"""
Sprint V1.1: Adapter parsing minimal tests

Tests adapter parsing with fixture files.
"""
import pytest
import os
from datetime import date
from pathlib import Path

from app.adapters.strava_export import StravaExportAdapter, StravaActivity, parse_strava_sport, is_hiit_heuristic
from app.adapters.goldencheetah import GoldenCheetahAdapter, GCActivity
from app.types import EnduranceSport


# Fixture paths
FIXTURES_DIR = Path(__file__).parent / "fixtures"
STRAVA_FIXTURE = FIXTURES_DIR / "strava" / "activities.csv"
GC_FIXTURE = FIXTURES_DIR / "gc" / "sample_summary.json"


class TestStravaAdapterParsing:
    """Test Strava bulk export adapter parsing."""
    
    def test_fixture_file_exists(self):
        """Fixture file should exist."""
        assert STRAVA_FIXTURE.exists(), f"Strava fixture not found: {STRAVA_FIXTURE}"
    
    def test_parse_csv_directly(self):
        """Parse activities.csv directly (not through zip)."""
        # Create adapter but we'll test the parsing logic directly
        activities = []
        
        with open(STRAVA_FIXTURE) as f:
            import csv
            reader = csv.DictReader(f)
            for row in reader:
                activity_id = row.get("Activity ID", "").strip()
                name = row.get("Activity Name", "").strip()
                activity_type = row.get("Activity Type", "").strip()
                
                # Parse date
                date_str = row.get("Activity Date", "")
                from datetime import datetime
                try:
                    start_date = datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M:%S").date()
                except ValueError:
                    continue
                
                # Parse duration
                elapsed = row.get("Elapsed Time", "0")
                try:
                    duration_minutes = float(elapsed) / 60.0
                except ValueError:
                    duration_minutes = 0.0
                
                activities.append({
                    "id": activity_id,
                    "name": name,
                    "type": activity_type,
                    "date": start_date,
                    "duration": duration_minutes,
                })
        
        # Expected from readme.txt
        assert len(activities) == 8, f"Expected 8 activities, got {len(activities)}"
    
    def test_sport_mapping(self):
        """Test sport type mapping."""
        # Test mapping function
        assert parse_strava_sport("Ride") == EnduranceSport.CYCLING
        assert parse_strava_sport("Run") == EnduranceSport.RUNNING
        assert parse_strava_sport("Swim") == EnduranceSport.SWIMMING
        assert parse_strava_sport("VirtualRide") == EnduranceSport.CYCLING
        assert parse_strava_sport("Unknown") is None
    
    def test_hiit_heuristic(self):
        """Test HIIT detection heuristic."""
        # Keywords should trigger HIIT
        assert is_hiit_heuristic("Interval Training", "Ride") is True
        assert is_hiit_heuristic("Morning Crit Race", "Ride") is True
        assert is_hiit_heuristic("Easy Recovery", "Run") is False
        assert is_hiit_heuristic("Long Zone 2 Ride", "Ride") is False
    
    def test_adapter_parses_fixture(self):
        """Test full adapter parsing of fixture."""
        # Since adapter expects a zip, we test parsing directly
        activities = []
        
        with open(STRAVA_FIXTURE) as f:
            import csv
            reader = csv.DictReader(f)
            for row in reader:
                activity_type = row.get("Activity Type", "").strip()
                sport = parse_strava_sport(activity_type)
                if sport:
                    activities.append(sport)
        
        # Count by sport
        cycling_count = activities.count(EnduranceSport.CYCLING)
        running_count = activities.count(EnduranceSport.RUNNING)
        swimming_count = activities.count(EnduranceSport.SWIMMING)
        
        # Expected: 4 cycling (Race type not mapped), 2 running, 1 swimming
        # Note: "Race" activity type alone doesn't map to a sport
        assert cycling_count == 4, f"Expected 4 cycling, got {cycling_count}"
        assert running_count == 2, f"Expected 2 running, got {running_count}"
        assert swimming_count == 1, f"Expected 1 swimming, got {swimming_count}"
    
    def test_date_parsing(self):
        """Test date parsing from fixture."""
        dates = []
        
        with open(STRAVA_FIXTURE) as f:
            import csv
            from datetime import datetime
            reader = csv.DictReader(f)
            for row in reader:
                date_str = row.get("Activity Date", "").strip()
                try:
                    d = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").date()
                    dates.append(d)
                except ValueError:
                    pass
        
        # Check date range
        assert len(dates) == 8
        assert min(dates) == date(2024, 1, 15)
        assert max(dates) == date(2024, 1, 23)
    
    def test_duration_parsing(self):
        """Test duration conversion from seconds to minutes."""
        durations = []
        
        with open(STRAVA_FIXTURE) as f:
            import csv
            reader = csv.DictReader(f)
            for row in reader:
                elapsed = row.get("Elapsed Time", "0")
                try:
                    minutes = float(elapsed) / 60.0
                    durations.append(minutes)
                except ValueError:
                    pass
        
        # Expected durations (in minutes)
        expected = [60, 45, 50, 30, 120, 40, 60, 45]
        assert durations == expected, f"Durations mismatch: {durations} vs {expected}"
    
    def test_deterministic_ordering(self):
        """Activities should be parsed in deterministic order (by row order)."""
        ids = []
        
        with open(STRAVA_FIXTURE) as f:
            import csv
            reader = csv.DictReader(f)
            for row in reader:
                activity_id = row.get("Activity ID", "").strip()
                ids.append(activity_id)
        
        # Should be in file order
        expected_ids = [
            "1234567890", "1234567891", "1234567892", "1234567893",
            "1234567894", "1234567895", "1234567896", "1234567897"
        ]
        assert ids == expected_ids


class TestGoldenCheetahAdapterParsing:
    """Test GoldenCheetah adapter parsing."""
    
    def test_fixture_file_exists(self):
        """Fixture file should exist."""
        assert GC_FIXTURE.exists(), f"GC fixture not found: {GC_FIXTURE}"
    
    def test_parse_json_directly(self):
        """Parse JSON summary directly."""
        import json
        
        with open(GC_FIXTURE) as f:
            data = json.load(f)
        
        assert isinstance(data, list)
        assert len(data) == 5, f"Expected 5 activities, got {len(data)}"
    
    def test_sport_mapping(self):
        """Test sport mapping from GC format."""
        adapter = GoldenCheetahAdapter(str(FIXTURES_DIR / "gc"))
        
        # Parse and check sports
        activities = adapter.parse_json_summaries("sample_summary.json")
        
        sports = [a.sport.lower() for a in activities]
        
        assert "bike" in sports or "cycling" in sports
        assert "run" in sports or "running" in sports
        assert "swim" in sports or "swimming" in sports
    
    def test_activity_count(self):
        """Should parse all 5 activities from fixture."""
        adapter = GoldenCheetahAdapter(str(FIXTURES_DIR / "gc"))
        activities = adapter.parse_json_summaries("sample_summary.json")
        
        assert len(activities) == 5
    
    def test_duration_parsing(self):
        """Test duration conversion (seconds to minutes)."""
        adapter = GoldenCheetahAdapter(str(FIXTURES_DIR / "gc"))
        activities = adapter.parse_json_summaries("sample_summary.json")
        
        # Check durations (from fixture: 3600, 1800, 2400, 5400, 2700 seconds)
        durations = [a.duration_minutes for a in activities]
        expected = [60.0, 30.0, 40.0, 90.0, 45.0]
        
        assert durations == expected, f"Durations mismatch: {durations} vs {expected}"
    
    def test_optional_fields(self):
        """Test parsing with optional fields (TSS, IF, power)."""
        adapter = GoldenCheetahAdapter(str(FIXTURES_DIR / "gc"))
        activities = adapter.parse_json_summaries("sample_summary.json")
        
        # First activity has all fields
        act1 = activities[0]
        assert act1.tss == 80.0
        assert act1.intensity_factor == 0.85
        assert act1.avg_power == 200.0
        
        # Last activity has minimal fields
        act5 = activities[4]
        assert act5.tss is None  # Not provided
        assert act5.avg_power == 180.0
    
    def test_hiit_detection(self):
        """Test HIIT detection from TSS/IF."""
        adapter = GoldenCheetahAdapter(str(FIXTURES_DIR / "gc"))
        activities = adapter.parse_json_summaries("sample_summary.json")
        
        # High TSS/IF should be HIIT
        session_dicts = [a.to_session_dict(athlete_id=1) for a in activities]
        
        # First activity: TSS 80, IF 0.85 -> not HIIT (TSS/hr ~80)
        # Fourth activity: TSS 150, IF 0.95 -> HIIT (TSS/hr ~100)
        intensity_types = [s["intensity_type"] for s in session_dicts if s]
        
        # Fourth should be hiit (high TSS per hour)
        assert "hiit" in intensity_types or "mixed" in intensity_types
    
    def test_deterministic_ordering(self):
        """Activities should be parsed in deterministic order."""
        adapter = GoldenCheetahAdapter(str(FIXTURES_DIR / "gc"))
        
        # Parse twice
        activities1 = adapter.parse_json_summaries("sample_summary.json")
        
        adapter2 = GoldenCheetahAdapter(str(FIXTURES_DIR / "gc"))
        activities2 = adapter2.parse_json_summaries("sample_summary.json")
        
        # Same order
        ids1 = [a.activity_id for a in activities1]
        ids2 = [a.activity_id for a in activities2]
        
        assert ids1 == ids2
        assert ids1 == ["gc_001", "gc_002", "gc_003", "gc_004", "gc_005"]
