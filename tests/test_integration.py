"""Integration tests for concurrent training API"""
import pytest
from datetime import datetime, date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


# Use file-based SQLite for tests to ensure same connection
TEST_DATABASE_URL = "sqlite:///./test_integration.db"


@pytest.fixture(scope="session")
def engine():
    """Create engine once for all tests"""
    return create_engine(
        TEST_DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )


@pytest.fixture(scope="function")
def test_db(engine):
    """Create tables and yield session"""
    TestingSessionLocal = sessionmaker(
        autocommit=False, 
        autoflush=False, 
        bind=engine
    )
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Drop all tables
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(engine):
    """Create a test client with test database"""
    TestingSessionLocal = sessionmaker(
        autocommit=False, 
        autoflush=False, 
        bind=engine
    )
    
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    # Override the dependency
    app.dependency_overrides[get_db] = override_get_db
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    with TestClient(app) as test_client:
        yield test_client
    
    # Cleanup
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


class TestAthleteLifecycle:
    """Test complete athlete lifecycle from creation to trends"""
    
    def test_create_athlete(self, client):
        """Test creating a new athlete"""
        response = client.post("/athletes", json={"name": "Test Athlete"})
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Test Athlete"
        assert "created_at" in data
    
    def test_get_athlete(self, client):
        """Test retrieving an athlete by ID"""
        # Create athlete
        create_response = client.post("/athletes", json={"name": "Jane Doe"})
        assert create_response.status_code == 200
        athlete_id = create_response.json()["id"]
        
        # Get athlete
        response = client.get(f"/athletes/{athlete_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Jane Doe"
    
    def test_get_nonexistent_athlete(self, client):
        """Test retrieving non-existent athlete returns 404"""
        response = client.get("/athletes/999")
        assert response.status_code == 404


class TestReadinessFlow:
    """Test readiness endpoints"""
    
    @pytest.fixture
    def athlete_id(self, client):
        """Create athlete and return ID"""
        response = client.post("/athletes", json={"name": "Readiness Tester"})
        return response.json()["id"]
    
    def test_get_initial_readiness(self, client, athlete_id):
        """Test getting initial readiness for new athlete"""
        response = client.get(f"/readiness/today?athlete_id={athlete_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["athlete_id"] == athlete_id
        assert data["overall"] is None  # Missing history is not 100% readiness
        assert data["endurance"] is None
        assert data["assessment_status"] == "insufficient_data"
        assert all(value is None for value in data["per_lift"].values())
        assert "per_lift" in data
        assert "explanations" in data
        assert len(data["explanations"]) > 0
    
    def test_get_readiness_for_date(self, client, athlete_id):
        """Test getting readiness for specific date"""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        response = client.get(f"/readiness/{yesterday}?athlete_id={athlete_id}")
        assert response.status_code == 200
        assert response.json()["date"] == yesterday
    
    def test_get_readiness_invalid_date(self, client, athlete_id):
        """Test getting readiness with invalid date format"""
        response = client.get(f"/readiness/invalid-date?athlete_id={athlete_id}")
        assert response.status_code == 400


class TestStrengthSession:
    """Test strength session logging"""
    
    @pytest.fixture
    def athlete_id(self, client):
        """Create athlete and return ID"""
        response = client.post("/athletes", json={"name": "Strength Tester"})
        return response.json()["id"]
    
    def test_log_strength_session_single_set(self, client, athlete_id):
        """Test logging a simple strength session"""
        session_data = {
            "athlete_id": athlete_id,
            "lift": "squat",
            "start_time": datetime.now().isoformat(),
            "sets": [
                {
                    "weight": 100.0,
                    "target_reps": 5,
                    "reps": [
                        {"weight": 100.0, "velocity": 0.45, "rep_num": 1, "rest_before": 0.0},
                        {"weight": 100.0, "velocity": 0.42, "rep_num": 2, "rest_before": 3.0},
                        {"weight": 100.0, "velocity": 0.38, "rep_num": 3, "rest_before": 3.0},
                    ]
                }
            ]
        }
        
        response = client.post("/sessions/strength", json=session_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["athlete_id"] == athlete_id
        assert data["lift"] == "squat"
        assert data["tonnage"] > 0
        assert data["avg_intensity"] > 0
    
    def test_log_strength_session_multiple_sets(self, client, athlete_id):
        """Test logging strength session with multiple sets"""
        session_data = {
            "athlete_id": athlete_id,
            "lift": "bench",
            "start_time": datetime.now().isoformat(),
            "sets": [
                {
                    "weight": 80.0,
                    "target_reps": 5,
                    "reps": [
                        {"weight": 80.0, "velocity": 0.50, "rep_num": 1, "rest_before": 0.0},
                        {"weight": 80.0, "velocity": 0.48, "rep_num": 2, "rest_before": 2.5},
                        {"weight": 80.0, "velocity": 0.45, "rep_num": 3, "rest_before": 2.5},
                        {"weight": 80.0, "velocity": 0.42, "rep_num": 4, "rest_before": 2.5},
                        {"weight": 80.0, "velocity": 0.38, "rep_num": 5, "rest_before": 2.5},
                    ]
                },
                {
                    "weight": 80.0,
                    "target_reps": 5,
                    "reps": [
                        {"weight": 80.0, "velocity": 0.46, "rep_num": 1, "rest_before": 180.0},
                        {"weight": 80.0, "velocity": 0.44, "rep_num": 2, "rest_before": 3.0},
                        {"weight": 80.0, "velocity": 0.40, "rep_num": 3, "rest_before": 3.0},
                        {"weight": 80.0, "velocity": 0.37, "rep_num": 4, "rest_before": 3.0},
                        {"weight": 80.0, "velocity": 0.35, "rep_num": 5, "rest_before": 3.0},
                    ]
                },
                {
                    "weight": 75.0,
                    "target_reps": 5,
                    "reps": [
                        {"weight": 75.0, "velocity": 0.52, "rep_num": 1, "rest_before": 180.0},
                        {"weight": 75.0, "velocity": 0.50, "rep_num": 2, "rest_before": 3.0},
                        {"weight": 75.0, "velocity": 0.47, "rep_num": 3, "rest_before": 3.0},
                        {"weight": 75.0, "velocity": 0.45, "rep_num": 4, "rest_before": 3.0},
                        {"weight": 75.0, "velocity": 0.42, "rep_num": 5, "rest_before": 3.0},
                    ]
                }
            ]
        }
        
        response = client.post("/sessions/strength", json=session_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["lift"] == "bench"
        # Total tonnage: (80*5*2) + (75*5) = 800 + 375 = 1175
        assert data["tonnage"] == pytest.approx(1175.0, abs=10.0)
    
    def test_log_strength_invalid_lift(self, client, athlete_id):
        """Test logging strength with invalid lift type"""
        session_data = {
            "athlete_id": athlete_id,
            "lift": "invalid_lift",
            "start_time": datetime.now().isoformat(),
            "sets": []
        }
        
        response = client.post("/sessions/strength", json=session_data)
        assert response.status_code == 422  # Validation error
    
    def test_log_strength_nonexistent_athlete(self, client):
        """Test logging strength for non-existent athlete"""
        session_data = {
            "athlete_id": 999,
            "lift": "squat",
            "start_time": datetime.now().isoformat(),
            "sets": [
                {
                    "weight": 100.0,
                    "target_reps": 5,
                    "reps": [
                        {"weight": 100.0, "velocity": 0.45, "rep_num": 1, "rest_before": 0.0},
                    ]
                }
            ]
        }
        
        response = client.post("/sessions/strength", json=session_data)
        assert response.status_code == 400


class TestEnduranceSession:
    """Test endurance session logging"""
    
    @pytest.fixture
    def athlete_id(self, client):
        """Create athlete and return ID"""
        response = client.post("/athletes", json={"name": "Endurance Tester"})
        return response.json()["id"]
    
    def test_log_endurance_session_z2(self, client, athlete_id):
        """Test logging Z2 endurance session"""
        session_data = {
            "athlete_id": athlete_id,
            "sport": "cycling",
            "start_time": datetime.now().isoformat(),
            "duration_minutes": 60.0,
            "intensity_type": "z2"
        }
        
        response = client.post("/sessions/endurance", json=session_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["athlete_id"] == athlete_id
        assert data["sport"] == "cycling"
        assert data["duration_minutes"] == 60.0
        assert data["intensity_type"] == "z2"
        assert data["u_E_Z2"] == 60.0
        assert data["u_E_HIIT"] == 0.0
    
    def test_log_endurance_session_hiit(self, client, athlete_id):
        """Test logging HIIT endurance session"""
        session_data = {
            "athlete_id": athlete_id,
            "sport": "running",
            "start_time": datetime.now().isoformat(),
            "duration_minutes": 30.0,
            "intensity_type": "hiit"
        }
        
        response = client.post("/sessions/endurance", json=session_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["intensity_type"] == "hiit"
        assert data["u_E_Z2"] == 0.0
        assert data["u_E_HIIT"] == 30.0
    
    def test_log_endurance_session_mixed(self, client, athlete_id):
        """Test logging mixed intensity endurance session"""
        session_data = {
            "athlete_id": athlete_id,
            "sport": "swimming",
            "start_time": datetime.now().isoformat(),
            "duration_minutes": 60.0,
            "intensity_type": "mixed"
        }
        
        response = client.post("/sessions/endurance", json=session_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["intensity_type"] == "mixed"
        assert data["u_E_Z2"] == 18.0  # 30%
        assert data["u_E_HIIT"] == 42.0  # 70%
    
    def test_log_endurance_invalid_intensity(self, client, athlete_id):
        """Test logging endurance with invalid intensity type"""
        session_data = {
            "athlete_id": athlete_id,
            "sport": "running",
            "start_time": datetime.now().isoformat(),
            "duration_minutes": 30.0,
            "intensity_type": "invalid"
        }
        
        response = client.post("/sessions/endurance", json=session_data)
        assert response.status_code == 422
    
    def test_log_endurance_zero_duration(self, client, athlete_id):
        """Test logging endurance with zero duration fails"""
        session_data = {
            "athlete_id": athlete_id,
            "sport": "running",
            "start_time": datetime.now().isoformat(),
            "duration_minutes": 0.0,
            "intensity_type": "z2"
        }
        
        response = client.post("/sessions/endurance", json=session_data)
        assert response.status_code == 422


class TestDayStateUpdate:
    """Test day state update endpoint"""
    
    @pytest.fixture
    def admin_headers(self):
        """Headers with admin API key"""
        return {"X-API-Key": "dev-api-key-change-in-production"}
    
    @pytest.fixture
    def athlete_id(self, client):
        """Create athlete and return ID"""
        response = client.post("/athletes", json={"name": "Day State Tester"})
        return response.json()["id"]
    
    def test_update_day_state(self, client, athlete_id, admin_headers):
        """Test triggering day state update"""
        response = client.post(f"/admin/update-day/{athlete_id}", headers=admin_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "updated"
        assert data["athlete_id"] == athlete_id
        assert "date" in data
        assert "D_sys" in data
        assert "R_mito" in data
        assert "E_fat" in data
    
    def test_update_day_state_with_date(self, client, athlete_id, admin_headers):
        """Test triggering day state update for specific date"""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        response = client.post(f"/admin/update-day/{athlete_id}?date_str={yesterday}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["date"] == yesterday
    
    def test_update_day_state_invalid_date(self, client, athlete_id, admin_headers):
        """Test triggering day state update with invalid date"""
        response = client.post(f"/admin/update-day/{athlete_id}?date_str=invalid", headers=admin_headers)
        assert response.status_code == 400
    
    def test_update_day_state_nonexistent_athlete(self, client, admin_headers):
        """Test updating day state for non-existent athlete"""
        response = client.post("/admin/update-day/999", headers=admin_headers)
        assert response.status_code == 200  # Creates state anyway
    
    def test_update_day_state_no_api_key(self, client, athlete_id):
        """Test that admin endpoint requires API key"""
        response = client.post(f"/admin/update-day/{athlete_id}")
        assert response.status_code == 401
    
    def test_update_day_state_invalid_api_key(self, client, athlete_id):
        """Test that admin endpoint rejects invalid API key"""
        headers = {"X-API-Key": "invalid-key"}
        response = client.post(f"/admin/update-day/{athlete_id}", headers=headers)
        assert response.status_code == 403


class TestAutoregulation:
    """Test autoregulation endpoint"""
    
    @pytest.fixture
    def athlete_id(self, client):
        """Create athlete and return ID"""
        response = client.post("/athletes", json={"name": "Autoreg Tester"})
        return response.json()["id"]
    
    def test_autoregulate_basic(self, client, athlete_id):
        """Test getting autoregulation suggestion"""
        request_data = {
            "athlete_id": athlete_id,
            "lift": "squat",
            "current_weight": 100.0,
            "target_v_low": 0.35,
            "target_v_high": 0.45,
            "vl_max": 20.0,
            "planned_reps": 5,
            "current_reps_done": 0,
            "recent_v_obs": []
        }
        
        response = client.post("/strength/autoregulate", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "continue_set" in data
        assert "load_change" in data
        assert "predicted_velocity" in data
        assert "current_vl" in data
        assert "messages" in data
        assert isinstance(data["messages"], list)
    
    def test_autoregulate_invalid_lift(self, client, athlete_id):
        """Test autoregulation with invalid lift"""
        request_data = {
            "athlete_id": athlete_id,
            "lift": "nonexistent",
            "current_weight": 100.0,
            "target_v_low": 0.35,
            "target_v_high": 0.45,
            "planned_reps": 5,
            "current_reps_done": 0
        }
        
        response = client.post("/strength/autoregulate", json=request_data)
        assert response.status_code == 422


class TestTrends:
    """Test trend endpoints"""
    
    @pytest.fixture
    def athlete_id(self, client):
        """Create athlete and return ID"""
        response = client.post("/athletes", json={"name": "Trends Tester"})
        return response.json()["id"]
    
    def test_get_lift_trends(self, client, athlete_id):
        """Test getting lift trend data"""
        response = client.get(f"/trends/lift?athlete_id={athlete_id}&lift=squat&days=30")
        assert response.status_code == 200
        
        data = response.json()
        assert data["athlete_id"] == athlete_id
        assert data["lift"] == "squat"
        assert data["days"] == 30
        assert "data" in data
        assert isinstance(data["data"], list)
    
    def test_get_lift_trends_default_days(self, client, athlete_id):
        """Test getting lift trends with default days"""
        response = client.get(f"/trends/lift?athlete_id={athlete_id}&lift=bench")
        assert response.status_code == 200
        assert response.json()["days"] == 30
    
    def test_get_lift_trends_invalid_days(self, client, athlete_id):
        """Test getting lift trends with invalid days parameter"""
        response = client.get(f"/trends/lift?athlete_id={athlete_id}&lift=squat&days=500")
        assert response.status_code == 422
    
    def test_get_endurance_trends(self, client, athlete_id):
        """Test getting endurance trend data"""
        response = client.get(f"/trends/endurance?athlete_id={athlete_id}&days=30")
        assert response.status_code == 200
        
        data = response.json()
        assert data["athlete_id"] == athlete_id
        assert data["days"] == 30
        assert "data" in data
        assert isinstance(data["data"], list)
    
    def test_get_endurance_trends_default_days(self, client, athlete_id):
        """Test getting endurance trends with default days"""
        response = client.get(f"/trends/endurance?athlete_id={athlete_id}")
        assert response.status_code == 200
        assert response.json()["days"] == 30


class TestHealthCheck:
    """Test health check endpoint"""
    
    def test_health_check(self, client):
        """Test health check returns healthy"""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
    
    def test_root_redirect(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        assert "message" in response.json()


class TestFullTrainingWorkflow:
    """Test complete training workflow - integration of all components"""
    
    @pytest.fixture
    def admin_headers(self):
        """Headers with admin API key"""
        return {"X-API-Key": "dev-api-key-change-in-production"}
    
    def test_complete_workout_day(self, client, admin_headers):
        """
        Test complete workflow:
        1. Create athlete
        2. Get initial readiness
        3. Log strength session
        4. Log endurance session  
        5. Update day state
        6. Get readiness after training
        7. Get autoregulation suggestion
        8. Get trends
        """
        # 1. Create athlete
        athlete_response = client.post("/athletes", json={"name": "Integration Tester"})
        assert athlete_response.status_code == 200
        athlete_id = athlete_response.json()["id"]
        
        # 2. Get initial readiness
        readiness_response = client.get(f"/readiness/today?athlete_id={athlete_id}")
        assert readiness_response.status_code == 200
        initial_readiness = readiness_response.json()
        assert initial_readiness["overall"] is None
        
        # 3. Log strength session (squat with 3 sets)
        strength_session = {
            "athlete_id": athlete_id,
            "lift": "squat",
            "start_time": datetime.now().isoformat(),
            "sets": [
                {
                    "weight": 100.0,
                    "target_reps": 5,
                    "reps": [
                        {"weight": 100.0, "velocity": 0.45, "rep_num": 1, "rest_before": 0.0},
                        {"weight": 100.0, "velocity": 0.43, "rep_num": 2, "rest_before": 3.0},
                        {"weight": 100.0, "velocity": 0.40, "rep_num": 3, "rest_before": 3.0},
                        {"weight": 100.0, "velocity": 0.37, "rep_num": 4, "rest_before": 3.0},
                        {"weight": 100.0, "velocity": 0.35, "rep_num": 5, "rest_before": 3.0},
                    ]
                },
                {
                    "weight": 100.0,
                    "target_reps": 5,
                    "reps": [
                        {"weight": 100.0, "velocity": 0.43, "rep_num": 1, "rest_before": 180.0},
                        {"weight": 100.0, "velocity": 0.40, "rep_num": 2, "rest_before": 3.0},
                        {"weight": 100.0, "velocity": 0.37, "rep_num": 3, "rest_before": 3.0},
                        {"weight": 100.0, "velocity": 0.35, "rep_num": 4, "rest_before": 3.0},
                        {"weight": 100.0, "velocity": 0.33, "rep_num": 5, "rest_before": 3.0},
                    ]
                },
                {
                    "weight": 95.0,
                    "target_reps": 5,
                    "reps": [
                        {"weight": 95.0, "velocity": 0.47, "rep_num": 1, "rest_before": 180.0},
                        {"weight": 95.0, "velocity": 0.45, "rep_num": 2, "rest_before": 3.0},
                        {"weight": 95.0, "velocity": 0.42, "rep_num": 3, "rest_before": 3.0},
                        {"weight": 95.0, "velocity": 0.40, "rep_num": 4, "rest_before": 3.0},
                        {"weight": 95.0, "velocity": 0.38, "rep_num": 5, "rest_before": 3.0},
                    ]
                }
            ]
        }
        
        strength_response = client.post("/sessions/strength", json=strength_session)
        assert strength_response.status_code == 200
        
        # 4. Log endurance session (30 min Z2 run)
        endurance_session = {
            "athlete_id": athlete_id,
            "sport": "running",
            "start_time": datetime.now().isoformat(),
            "duration_minutes": 30.0,
            "intensity_type": "z2"
        }
        
        endurance_response = client.post("/sessions/endurance", json=endurance_session)
        assert endurance_response.status_code == 200
        
        # 5. Update day state
        update_response = client.post(f"/admin/update-day/{athlete_id}", headers=admin_headers)
        assert update_response.status_code == 200
        
        # 6. Get readiness after training
        final_readiness_response = client.get(f"/readiness/today?athlete_id={athlete_id}")
        assert final_readiness_response.status_code == 200
        final_readiness = final_readiness_response.json()
        
        # After training, readiness may be reduced
        assert "overall" in final_readiness
        assert "per_lift" in final_readiness
        assert "explanations" in final_readiness
        
        # 7. Get autoregulation suggestion for next session
        autoreg_request = {
            "athlete_id": athlete_id,
            "lift": "squat",
            "current_weight": 100.0,
            "target_v_low": 0.35,
            "target_v_high": 0.45,
            "vl_max": 20.0,
            "planned_reps": 5,
            "current_reps_done": 0,
            "recent_v_obs": []
        }
        
        autoreg_response = client.post("/strength/autoregulate", json=autoreg_request)
        assert autoreg_response.status_code == 200
        autoreg = autoreg_response.json()
        assert "continue_set" in autoreg
        assert "load_change" in autoreg
        assert "messages" in autoreg
        
        # 8. Get trends
        # Lift trends
        lift_trends_response = client.get(f"/trends/lift?athlete_id={athlete_id}&lift=squat&days=7")
        assert lift_trends_response.status_code == 200
        lift_trends = lift_trends_response.json()
        assert lift_trends["lift"] == "squat"
        assert "data" in lift_trends
        
        # Endurance trends
        end_trends_response = client.get(f"/trends/endurance?athlete_id={athlete_id}&days=7")
        assert end_trends_response.status_code == 200
        end_trends = end_trends_response.json()
        assert "data" in end_trends
        
        # Verify workflow completed successfully
        print(f"✓ Integration test completed successfully for athlete {athlete_id}")
        print(f"  - Initial readiness: {initial_readiness['assessment_status']}")
        print(f"  - Final readiness: {final_readiness['overall']:.1f}")
        print(f"  - Autoreg suggestion: {autoreg['load_change']:+.1f}% load change")
