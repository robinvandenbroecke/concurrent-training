"""Basic tests"""
import pytest

from app.models import TrainingSession


def test_training_session_creation(db_session):
    """Test creating a training session"""
    session = TrainingSession(name="Test Session", description="A test session")
    db_session.add(session)
    db_session.commit()
    
    assert session.id is not None
    assert session.name == "Test Session"
    assert session.status == "pending"


def test_import():
    """Test basic imports work"""
    from app import __version__
    assert __version__ == "0.1.0"
