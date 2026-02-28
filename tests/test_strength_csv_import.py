"""
Tests for strength CSV adapter v2.

Tests parsing, validation, and import functionality.
"""
import pytest
from datetime import date
from pathlib import Path

from app.adapters.strength_csv import (
    parse_strength_csv,
    parse_lift_code,
    parse_date,
    convert_to_sets_data,
    import_strength_sessions,
    import_strength_csv,
    LIFT_CODE_MAP,
)
from app.types import LiftType


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def fixture_path():
    """Path to test fixture."""
    return Path(__file__).parent.parent / "fixtures" / "strength" / "strength_log_v2.csv"


@pytest.fixture
def sample_csv_content():
    """Sample CSV content for testing."""
    return """session_date,session_id,lift_code,sets,reps,weight_kg,rest_seconds,rpe,velocity_m_per_s
2024-01-15,sq_001,squat,1,5,100,180,8,0.45
2024-01-15,sq_001,squat,2,5,100,180,8,0.42
2024-01-15,sq_001,squat,3,5,100,180,8,0.38
2024-01-17,bp_001,bench,1,5,80,180,7,0.50
"""


# ============================================================================
# Unit Tests
# ============================================================================

class TestLiftCodeParsing:
    """Test lift code mapping."""
    
    def test_squat_codes(self):
        assert parse_lift_code("sq") == LiftType.SQUAT
        assert parse_lift_code("squat") == LiftType.SQUAT
        assert parse_lift_code("SQ") == LiftType.SQUAT
        assert parse_lift_code("SQUAT") == LiftType.SQUAT
    
    def test_bench_codes(self):
        assert parse_lift_code("bp") == LiftType.BENCH
        assert parse_lift_code("bench") == LiftType.BENCH
    
    def test_press_codes(self):
        assert parse_lift_code("press") == LiftType.PRESS
        assert parse_lift_code("ohp") == LiftType.PRESS
    
    def test_deadlift_codes(self):
        assert parse_lift_code("dl") == LiftType.DEADLIFT
        assert parse_lift_code("deadlift") == LiftType.DEADLIFT
    
    def test_clean_codes(self):
        assert parse_lift_code("pc") == LiftType.POWER_CLEAN
        assert parse_lift_code("clean") == LiftType.POWER_CLEAN
    
    def test_unknown_code_returns_none(self):
        assert parse_lift_code("unknown") is None
        assert parse_lift_code("") is None


class TestDateParsing:
    """Test date parsing from various formats."""
    
    def test_iso_format(self):
        assert parse_date("2024-01-15") == date(2024, 1, 15)
    
    def test_slashes(self):
        assert parse_date("2024/01/15") == date(2024, 1, 15)
    
    def test_dmy_format(self):
        assert parse_date("15-01-2024") == date(2024, 1, 15)
        assert parse_date("15/01/2024") == date(2024, 1, 15)
    
    def test_invalid_date_returns_none(self):
        assert parse_date("invalid") is None
        assert parse_date("") is None
        assert parse_date("not-a-date") is None


class TestParseStrengthCSV:
    """Test CSV parsing functionality."""
    
    def test_parse_fixture_file(self, fixture_path):
        """Test parsing the actual fixture file."""
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")
        
        sessions = parse_strength_csv(str(fixture_path))
        
        # Should have 4 unique sessions
        assert len(sessions) == 4
        
        # Check first session (sq_001)
        sq1 = sessions[0]
        assert sq1.session_id == "sq_001"
        assert sq1.session_date == date(2024, 1, 15)
        assert sq1.lift == LiftType.SQUAT
        assert len(sq1.sets) == 3
        
        # Check set details
        first_set = sq1.sets[0]
        assert first_set.set_num == 1
        assert first_set.reps == 5
        assert first_set.weight_kg == 100.0
        assert first_set.rest_seconds == 180.0
        assert first_set.rpe == 8.0
        assert first_set.velocities == [0.45]
    
    def test_sessions_sorted_by_date(self, fixture_path):
        """Sessions should be returned sorted by date."""
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")
        
        sessions = parse_strength_csv(str(fixture_path))
        
        dates = [s.session_date for s in sessions]
        assert dates == sorted(dates)
    
    def test_sets_sorted_by_set_num(self, fixture_path):
        """Sets within a session should be sorted by set number."""
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")
        
        sessions = parse_strength_csv(str(fixture_path))
        
        for session in sessions:
            set_nums = [s.set_num for s in session.sets]
            assert set_nums == sorted(set_nums)
    
    def test_optional_velocity(self, fixture_path):
        """Velocity should be optional."""
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")
        
        sessions = parse_strength_csv(str(fixture_path))
        
        # Find deadlift session (no velocity)
        dl_session = next((s for s in sessions if s.lift == LiftType.DEADLIFT), None)
        assert dl_session is not None
        
        # Deadlift sets should have empty velocities
        for set_data in dl_session.sets:
            assert set_data.velocities == []
    
    def test_missing_file_raises_error(self):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            parse_strength_csv("/nonexistent/file.csv")
    
    def test_invalid_lift_code_raises_error(self, tmp_path):
        """Should raise ValueError for unknown lift codes."""
        csv_content = """session_date,session_id,lift_code,sets,reps,weight_kg,rest_seconds,rpe,velocity_m_per_s
2024-01-15,xxx_001,unknown_lift,1,5,100,180,8,
"""
        csv_file = tmp_path / "invalid.csv"
        csv_file.write_text(csv_content)
        
        with pytest.raises(ValueError, match="Unknown lift code"):
            parse_strength_csv(str(csv_file))
    
    def test_invalid_date_raises_error(self, tmp_path):
        """Should raise ValueError for invalid dates."""
        csv_content = """session_date,session_id,lift_code,sets,reps,weight_kg,rest_seconds,rpe,velocity_m_per_s
invalid-date,sq_001,squat,1,5,100,180,8,
"""
        csv_file = tmp_path / "invalid.csv"
        csv_file.write_text(csv_content)
        
        with pytest.raises(ValueError, match="Invalid date format"):
            parse_strength_csv(str(csv_file))
    
    def test_empty_file_raises_error(self, tmp_path):
        """Should raise ValueError for empty file."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")
        
        with pytest.raises(ValueError, match="no headers"):
            parse_strength_csv(str(csv_file))


class TestConvertToSetsData:
    """Test conversion to sets_data format."""
    
    def test_basic_conversion(self):
        from app.adapters.strength_csv import ParsedSet
        
        parsed_sets = [
            ParsedSet(set_num=1, reps=5, weight_kg=100.0, rest_seconds=180.0, rpe=8.0, velocities=[0.45]),
            ParsedSet(set_num=2, reps=5, weight_kg=100.0, rest_seconds=180.0, rpe=8.0, velocities=[0.42]),
        ]
        
        sets_data = convert_to_sets_data(parsed_sets)
        
        assert len(sets_data) == 2
        assert sets_data[0]["load_kg"] == 100.0
        assert sets_data[0]["reps"] == 5
        assert sets_data[0]["velocities"] == [0.45]
        assert sets_data[0]["rest_sec"] is None  # First set has no rest
        
        assert sets_data[1]["load_kg"] == 100.0
        assert sets_data[1]["rest_sec"] == 180.0  # Second set has rest
    
    def test_no_velocity(self):
        from app.adapters.strength_csv import ParsedSet
        
        parsed_sets = [
            ParsedSet(set_num=1, reps=5, weight_kg=100.0, rest_seconds=None, rpe=None, velocities=[]),
        ]
        
        sets_data = convert_to_sets_data(parsed_sets)
        
        assert sets_data[0]["velocities"] == []


# ============================================================================
# Integration Tests
# ============================================================================

class TestImportStrengthSessions:
    """Test importing sessions into database."""
    
    def test_dry_run_does_not_create_records(self, db_session, fixture_path):
        """Dry run should not create any database records."""
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")
        
        from app import models
        
        # Create athlete first
        from app.services import AthleteService
        athlete = AthleteService.create_athlete(db_session, "Test Athlete")
        
        # Count sessions before
        count_before = db_session.query(models.StrengthSession).count()
        
        # Parse and import with dry_run
        parsed = parse_strength_csv(str(fixture_path))
        result = import_strength_sessions(db_session, athlete.id, parsed, dry_run=True)
        
        # Count sessions after
        count_after = db_session.query(models.StrengthSession).count()
        
        assert count_before == count_after
        assert result.sessions_created == 0
        assert len(result.session_ids) == 4  # But session IDs should be returned
    
    def test_import_creates_sessions(self, db_session, fixture_path):
        """Import should create sessions in database."""
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")
        
        from app import models
        
        # Create athlete
        from app.services import AthleteService
        athlete = AthleteService.create_athlete(db_session, "Test Athlete")
        
        # Import
        parsed = parse_strength_csv(str(fixture_path))
        result = import_strength_sessions(db_session, athlete.id, parsed, dry_run=False)
        
        # Verify results
        assert result.sessions_created == 4
        assert result.sessions_skipped == 0
        assert result.sets_total == 12  # 3+3+3+3 sets
        assert len(result.errors) == 0
        
        # Verify database state
        sessions = db_session.query(models.StrengthSession).filter(
            models.StrengthSession.athlete_id == athlete.id
        ).all()
        assert len(sessions) == 4
    
    def test_idempotent_import(self, db_session, fixture_path):
        """Importing same file twice should skip duplicates."""
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")
        
        from app.services import AthleteService
        athlete = AthleteService.create_athlete(db_session, "Test Athlete")
        
        # First import
        parsed = parse_strength_csv(str(fixture_path))
        result1 = import_strength_sessions(db_session, athlete.id, parsed, dry_run=False)
        assert result1.sessions_created == 4
        assert result1.sessions_skipped == 0
        
        # Second import (same data)
        parsed2 = parse_strength_csv(str(fixture_path))
        result2 = import_strength_sessions(db_session, athlete.id, parsed2, dry_run=False)
        assert result2.sessions_created == 0
        assert result2.sessions_skipped == 4


class TestImportStrengthCSV:
    """Test the main import_strength_csv function."""
    
    def test_full_import_flow(self, db_session, fixture_path):
        """Test the complete import flow."""
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")
        
        from app.services import AthleteService
        athlete = AthleteService.create_athlete(db_session, "Test Athlete")
        
        result = import_strength_csv(db_session, athlete.id, str(fixture_path))
        
        assert result.sessions_created == 4
        assert len(result.errors) == 0


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_session_id_skipped(self, tmp_path):
        """Rows with empty session_id should be skipped."""
        csv_content = """session_date,session_id,lift_code,sets,reps,weight_kg,rest_seconds,rpe,velocity_m_per_s
2024-01-15,,squat,1,5,100,180,8,
"""
        csv_file = tmp_path / "empty_id.csv"
        csv_file.write_text(csv_content)
        
        sessions = parse_strength_csv(str(csv_file))
        assert len(sessions) == 0  # Should be empty (row skipped)
    
    def test_single_set_session(self, tmp_path):
        """Session with single set should work."""
        csv_content = """session_date,session_id,lift_code,sets,reps,weight_kg,rest_seconds,rpe,velocity_m_per_s
2024-01-15,sq_001,squat,1,5,100,,8,
"""
        csv_file = tmp_path / "single.csv"
        csv_file.write_text(csv_content)
        
        sessions = parse_strength_csv(str(csv_file))
        assert len(sessions) == 1
        assert len(sessions[0].sets) == 1
        assert sessions[0].sets[0].rest_seconds is None
    
    def test_whitespace_in_headers(self, tmp_path):
        """Should handle whitespace in column headers."""
        csv_content = """ session_date , session_id , lift_code , sets , reps , weight_kg , rest_seconds , rpe , velocity_m_per_s 
2024-01-15,sq_001,squat,1,5,100,180,8,
"""
        csv_file = tmp_path / "whitespace.csv"
        csv_file.write_text(csv_content)
        
        sessions = parse_strength_csv(str(csv_file))
        assert len(sessions) == 1
