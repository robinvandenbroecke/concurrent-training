"""Test configuration and fixtures"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base


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
