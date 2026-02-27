"""Test configuration"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app import models

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///./test.db"


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test"""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Create session
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Drop tables
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def sample_athlete(db_session):
    """Create a sample athlete for testing"""
    athlete = models.Athlete(name="Test Athlete")
    db_session.add(athlete)
    db_session.commit()
    db_session.refresh(athlete)
    
    # Create default lift profiles
    from app.types import LiftType
    default_profiles = {
        LiftType.SQUAT: {"a": 0.55, "b": 0.0032},
        LiftType.BENCH: {"a": 0.60, "b": 0.0028},
        LiftType.DEADLIFT: {"a": 0.50, "b": 0.0030},
    }
    
    for lift, params in default_profiles.items():
        profile = models.LiftProfile(
            athlete_id=athlete.id,
            lift=lift,
            a=params["a"],
            b=params["b"]
        )
        db_session.add(profile)
    
    db_session.commit()
    return athlete


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with overridden dependencies"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()
