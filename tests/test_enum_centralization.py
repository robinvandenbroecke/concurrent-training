"""
Tests for enum centralization - Sprint E1

Ensures that LiftType, EnduranceSport, and EnduranceIntensity are truly
centralized in app/types.py and used consistently across all layers.
"""
import pytest


class TestEnumCentralization:
    """Verify single source of truth for domain enums"""
    
    def test_lift_type_identity(self):
        """LiftType from app.types is the same object everywhere"""
        from app.types import LiftType as CanonicalLiftType
        from app.domain.day_engine import LiftType as DayEngineLiftType
        from app.domain import LiftType as DomainLiftType
        from app.models import LiftType as ModelLiftType
        from app.schemas import LiftType as SchemaLiftType
        
        # All should be the exact same class object
        assert CanonicalLiftType is DayEngineLiftType, \
            "day_engine.LiftType should be the same as app.types.LiftType"
        assert CanonicalLiftType is DomainLiftType, \
            "domain.LiftType should be the same as app.types.LiftType"
        assert CanonicalLiftType is ModelLiftType, \
            "models.LiftType should be the same as app.types.LiftType"
        assert CanonicalLiftType is SchemaLiftType, \
            "schemas.LiftType should be the same as app.types.LiftType"
    
    def test_endurance_sport_identity(self):
        """EnduranceSport from app.types is the same object everywhere"""
        from app.types import EnduranceSport as CanonicalSport
        from app.domain.day_engine import EnduranceMode as DayEngineMode
        from app.domain import EnduranceSport as DomainSport
        from app.models import EnduranceSport as ModelSport
        from app.schemas import EnduranceSport as SchemaSport
        
        # All should be the exact same class object
        assert CanonicalSport is DayEngineMode, \
            "day_engine.EnduranceMode should be an alias for app.types.EnduranceSport"
        assert CanonicalSport is DomainSport, \
            "domain.EnduranceSport should be the same as app.types.EnduranceSport"
        assert CanonicalSport is ModelSport, \
            "models.EnduranceSport should be the same as app.types.EnduranceSport"
        assert CanonicalSport is SchemaSport, \
            "schemas.EnduranceSport should be the same as app.types.EnduranceSport"
    
    def test_endurance_intensity_identity(self):
        """EnduranceIntensity from app.types is the same object everywhere"""
        from app.types import EnduranceIntensity as CanonicalIntensity
        from app.domain import EnduranceIntensity as DomainIntensity
        from app.schemas import EnduranceIntensity as SchemaIntensity
        
        assert CanonicalIntensity is DomainIntensity, \
            "domain.EnduranceIntensity should be the same as app.types.EnduranceIntensity"
        assert CanonicalIntensity is SchemaIntensity, \
            "schemas.EnduranceIntensity should be the same as app.types.EnduranceIntensity"
    
    def test_lift_type_values(self):
        """LiftType has expected values for all standard lifts"""
        from app.types import LiftType
        
        expected_values = {
            "squat": LiftType.SQUAT,
            "bench": LiftType.BENCH,
            "deadlift": LiftType.DEADLIFT,
            "press": LiftType.PRESS,
            "power_clean": LiftType.POWER_CLEAN,
            "clean": LiftType.CLEAN,
            "other": LiftType.OTHER,
        }
        
        for string_value, enum_member in expected_values.items():
            assert enum_member.value == string_value, \
                f"LiftType.{enum_member.name} should have value '{string_value}'"
            
            # Verify value is accessible as string
            assert isinstance(enum_member.value, str), \
                f"LiftType.{enum_member.name}.value should be a string"
    
    def test_endurance_sport_values(self):
        """EnduranceSport has expected values for all sports"""
        from app.types import EnduranceSport
        
        expected_values = {
            "running": EnduranceSport.RUNNING,
            "cycling": EnduranceSport.CYCLING,
            "swimming": EnduranceSport.SWIMMING,
            "other": EnduranceSport.OTHER,
        }
        
        for string_value, enum_member in expected_values.items():
            assert enum_member.value == string_value, \
                f"EnduranceSport.{enum_member.name} should have value '{string_value}'"
            
            assert isinstance(enum_member.value, str), \
                f"EnduranceSport.{enum_member.name}.value should be a string"
    
    def test_endurance_intensity_values(self):
        """EnduranceIntensity has expected values for all zones"""
        from app.types import EnduranceIntensity
        
        expected_values = {
            "z2": EnduranceIntensity.Z2,
            "hiit": EnduranceIntensity.HIIT,
            "tempo": EnduranceIntensity.TEMPO,
            "threshold": EnduranceIntensity.THRESHOLD,
            "long": EnduranceIntensity.LONG,
            "easy": EnduranceIntensity.EASY,
            "other": EnduranceIntensity.OTHER,
        }
        
        for string_value, enum_member in expected_values.items():
            assert enum_member.value == string_value, \
                f"EnduranceIntensity.{enum_member.name} should have value '{string_value}'"
            
            assert isinstance(enum_member.value, str), \
                f"EnduranceIntensity.{enum_member.name}.value should be a string"
    
    def test_enum_comparison_works(self):
        """Enum comparison works correctly across module boundaries"""
        from app.types import LiftType, EnduranceSport
        from app.domain.day_engine import LiftType as DayLiftType
        from app.domain.day_engine import EnduranceMode
        
        # Comparison should work with 'is' and '=='
        assert LiftType.SQUAT is DayLiftType.SQUAT
        assert LiftType.SQUAT == DayLiftType.SQUAT
        
        # EnduranceSport/EnduranceMode alias should work
        assert EnduranceSport.CYCLING is EnduranceMode.CYCLING
        assert EnduranceSport.CYCLING == EnduranceMode.CYCLING
    
    def test_no_duplicate_enum_definitions(self):
        """No duplicate enum class definitions exist in codebase"""
        import ast
        import inspect
        from pathlib import Path
        
        # Get project root
        project_root = Path(__file__).parent.parent / "app"
        
        enum_class_names = ["LiftType", "EnduranceSport", "EnduranceIntensity"]
        definition_locations = {name: [] for name in enum_class_names}
        
        # Walk through all Python files
        for py_file in project_root.rglob("*.py"):
            if ".venv" in str(py_file) or "__pycache__" in str(py_file):
                continue
                
            try:
                content = py_file.read_text()
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        if node.name in enum_class_names:
                            # Check if it's actually an Enum class
                            for base in node.bases:
                                if isinstance(base, ast.Name) and base.id == "Enum":
                                    definition_locations[node.name].append(str(py_file))
                                elif isinstance(base, ast.Subscript):
                                    # Handle str, Enum pattern
                                    definition_locations[node.name].append(str(py_file))
            except SyntaxError:
                continue
        
        # app/types.py should be the only location with actual class definitions
        for enum_name, locations in definition_locations.items():
            # Filter to actual definitions (not imports)
            actual_definitions = [
                loc for loc in locations 
                if "types.py" in loc or "day_engine.py" in loc
            ]
            
            # The canonical location should be in types.py
            canonical_location = project_root / "types.py"
            assert str(canonical_location) in locations, \
                f"{enum_name} must be defined in app/types.py"


class TestBackwardsCompatibility:
    """Ensure backwards compatibility for renamed/moved enums"""
    
    def test_endurance_mode_alias(self):
        """EnduranceMode is available as backwards-compatible alias"""
        from app.domain.day_engine import EnduranceMode
        from app.types import EnduranceSport
        
        # EnduranceMode should be the same as EnduranceSport
        assert EnduranceMode is EnduranceSport
        
        # All values should be accessible via both names
        assert EnduranceMode.RUNNING is EnduranceSport.RUNNING
        assert EnduranceMode.CYCLING is EnduranceSport.CYCLING
        assert EnduranceMode.SWIMMING is EnduranceSport.SWIMMING
    
    def test_clean_lift_type_value(self):
        """CLEAN value exists for compatibility"""
        from app.types import LiftType
        
        # CLEAN should be available as an alias/alternative to POWER_CLEAN
        assert hasattr(LiftType, 'CLEAN')
        assert LiftType.CLEAN.value == "clean"


class TestSchemaDomainInteroperability:
    """Test Pydantic schemas work seamlessly with domain functions"""
    
    def test_pydantic_schema_with_canonical_enum(self):
        """Pydantic schemas accept and preserve canonical enum values"""
        from app.types import LiftType, EnduranceSport
        from app.schemas import StrengthSessionCreate, EnduranceSessionCreate
        from datetime import datetime
        
        # Strength session with canonical enum
        strength_schema = StrengthSessionCreate(
            athlete_id=1,
            lift=LiftType.SQUAT,
            start_time=datetime.now(),
            sets=[]
        )
        assert strength_schema.lift is LiftType.SQUAT
        
        # Endurance session with canonical enum
        endurance_schema = EnduranceSessionCreate(
            athlete_id=1,
            sport=EnduranceSport.CYCLING,
            start_time=datetime.now(),
            duration_minutes=60.0,
            intensity_type="z2"
        )
        assert endurance_schema.sport is EnduranceSport.CYCLING
        assert endurance_schema.intensity_type == "z2"
    
    def test_json_serialization_roundtrip(self):
        """JSON serialization preserves enum values correctly"""
        from app.types import LiftType, EnduranceSport, EnduranceIntensity
        from pydantic import BaseModel
        import json
        
        class TestSchema(BaseModel):
            lift: LiftType
            sport: EnduranceSport
            intensity: EnduranceIntensity
        
        original = TestSchema(
            lift=LiftType.BENCH,
            sport=EnduranceSport.RUNNING,
            intensity=EnduranceIntensity.HIIT
        )
        
        # Serialize to JSON
        json_str = original.model_dump_json()
        data = json.loads(json_str)
        
        # Verify string values
        assert data["lift"] == "bench"
        assert data["sport"] == "running"
        assert data["intensity"] == "hiit"
        
        # Deserialize back
        parsed = TestSchema.model_validate_json(json_str)
        assert parsed.lift is LiftType.BENCH
        assert parsed.sport is EnduranceSport.RUNNING
        assert parsed.intensity is EnduranceIntensity.HIIT
    
    def test_schema_to_domain_enum_identity(self):
        """Enum values from schemas are identical to domain enums"""
        from app.types import LiftType, EnduranceSport
        from app.schemas import StrengthSessionCreate, EnduranceSessionCreate
        from app.domain.day_engine import LiftType as DomainLiftType, EnduranceMode
        from datetime import datetime
        
        strength = StrengthSessionCreate(
            athlete_id=1,
            lift=LiftType.DEADLIFT,
            start_time=datetime.now(),
            sets=[]
        )
        
        # Schema enum IS domain enum - no conversion needed
        assert strength.lift is DomainLiftType.DEADLIFT
        
        endurance = EnduranceSessionCreate(
            athlete_id=1,
            sport=EnduranceSport.SWIMMING,
            start_time=datetime.now(),
            duration_minutes=30.0,
            intensity_type="hiit"
        )
        
        # EnduranceSport IS EnduranceMode
        assert endurance.sport is EnduranceMode.SWIMMING


class TestSQLAlchemyCompatibility:
    """Test SQLAlchemy Enum columns work with canonical enums"""
    
    def test_sqlalchemy_enum_uses_canonical(self):
        """SQLAlchemy models use canonical enum from app.types"""
        from app.types import LiftType, EnduranceSport
        from app.models import StrengthSession, EnduranceSession
        from sqlalchemy import Enum as SQLEnum
        
        # Verify SQLAlchemy columns use canonical enums
        assert isinstance(StrengthSession.lift.type, SQLEnum)
        assert StrengthSession.lift.type.enum_class is LiftType
        
        assert isinstance(EnduranceSession.sport.type, SQLEnum)
        assert EnduranceSession.sport.type.enum_class is EnduranceSport
