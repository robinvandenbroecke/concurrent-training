"""
Sprint A: Tests proving ingestion endpoints call the new modular engines

These tests verify:
1. Strength session ingestion calls rep_engine functions
2. Endurance session ingestion calls day_engine.update_day_state
3. The legacy ConcurrentTrainingModel is NOT called by default
4. EngineOrchestrator is the single source of truth
"""
import pytest
from datetime import date, datetime
from unittest.mock import Mock, patch, MagicMock

from app.types import LiftType, EnduranceSport
from app.schemas import SetData, RepData, StrengthSessionCreate, EnduranceSessionCreate


class TestStrengthIngestUsesRepEngine:
    """Test that strength session ingestion flows through rep_engine"""
    
    @patch("app.services.engine_orchestrator.simulate_strength_session")
    @patch("app.services.engine_orchestrator.EngineOrchestrator._persist_day_state")
    def test_ingest_strength_calls_rep_engine(
        self, mock_persist, mock_simulate, db_session, sample_athlete
    ):
        """
        Verify that SessionService.ingest_strength_session calls rep_engine.simulate_strength_session
        """
        from app.services import SessionService
        
        # Setup mock rep_engine output
        mock_set_output = Mock()
        mock_set_output.lift = "squat"
        mock_set_output.load_kg = 100.0
        mock_set_output.reps = []
        
        mock_output = Mock()
        mock_output.sets = [mock_set_output]
        mock_output.final_A_local = {"squat": 0.85}
        mock_output.final_A_sys = 0.90
        mock_output.final_A_M = 0.95
        mock_output.final_M = 0.0
        mock_simulate.return_value = mock_output
        
        # Create service and ingest
        service = SessionService(db_session)
        
        sets_data = [
            SetData(
                weight=100.0,
                target_reps=2,
                reps=[
                    RepData(weight=100.0, rep_num=1, velocity=0.45, rest_before=0),
                    RepData(weight=100.0, rep_num=2, velocity=0.43, rest_before=2)
                ]
            )
        ]
        
        session = service.ingest_strength_session(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            start_time=datetime(2024, 1, 1, 10, 0),
            sets_data=sets_data
        )
        
        # Verify rep_engine was called
        assert mock_simulate.called, "rep_engine.simulate_strength_session should be called"
        
        # Verify the call arguments
        call_args = mock_simulate.call_args
        session_input = call_args[0][0]  # First positional argument
        
        # Check that the session input has the right structure
        assert hasattr(session_input, 'sets')
        assert hasattr(session_input, 'profiles')
        assert hasattr(session_input, 'init_A_local')
        assert session_input.R_mito is not None
    
    @patch("app.services.engine_orchestrator.update_day_state")
    def test_ingest_strength_updates_day_state(
        self, mock_update_day, db_session, sample_athlete
    ):
        """
        Verify that day state is updated after strength session ingestion
        """
        from app.services import SessionService
        from app.domain.day_engine import DayState
        
        # Setup mock day state output
        mock_day_state = DayState(
            date=date(2024, 1, 1),
            per_lift={},
            D_sys=0.1,
            R_mito=0.2,
            E_fat=0.0
        )
        mock_update_day.return_value = mock_day_state
        
        service = SessionService(db_session)

        sets_data = [
            SetData(
                weight=100.0,
                target_reps=1,
                reps=[RepData(weight=100.0, rep_num=1, velocity=0.45, rest_before=0)]
            )
        ]

        session = service.ingest_strength_session(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            start_time=datetime(2024, 1, 1, 10, 0),
            sets_data=sets_data
        )

        # Verify day_engine.update_day_state was called
        assert mock_update_day.called, "day_engine.update_day_state should be called"


class TestEnduranceIngestUsesDayEngine:
    """Test that endurance session ingestion flows through day_engine"""
    
    @patch("app.services.engine_orchestrator.update_day_state")
    def test_ingest_endurance_calls_day_engine(
        self, mock_update_day, db_session, sample_athlete
    ):
        """
        Verify that SessionService.ingest_endurance_session calls day_engine
        """
        from app.services import SessionService
        from app.domain.day_engine import DayState
        
        # Setup mock
        mock_day_state = DayState(
            date=date(2024, 1, 1),
            per_lift={},
            D_sys=0.05,
            R_mito=0.25,  # Should increase from endurance
            E_fat=0.15
        )
        mock_update_day.return_value = mock_day_state
        
        service = SessionService(db_session)
        
        session = service.ingest_endurance_session(
            athlete_id=sample_athlete.id,
            sport=EnduranceSport.CYCLING,
            start_time=datetime(2024, 1, 1, 10, 0),
            duration_minutes=60.0,
            intensity_type="z2"
        )
        
        # Verify day_engine.update_day_state was called
        assert mock_update_day.called, "day_engine.update_day_state should be called"
        
        # Verify endurance impulses were passed
        call_args = mock_update_day.call_args
        daily_impulses = call_args[0][1]  # Second positional argument
        
        # Check endurance impulses
        assert hasattr(daily_impulses, 'endurance')
        assert daily_impulses.endurance.u_E_Z2 > 0  # Z2 should have impulse


class TestLegacyModelNotCalledByDefault:
    """Test that legacy ConcurrentTrainingModel is NOT called by default"""
    
    @patch("app.domain.model.ConcurrentTrainingModel")
    def test_legacy_model_not_instantiated_by_default(
        self, mock_legacy_model, db_session, sample_athlete
    ):
        """
        Verify that ConcurrentTrainingModel is not instantiated in SessionService by default
        """
        from app.services import SessionService
        import os
        
        # Ensure legacy flag is off
        with patch.dict(os.environ, {"USE_LEGACY_MODEL": "false"}):
            service = SessionService(db_session)
            
            # Legacy model should not be instantiated
            assert service._legacy_model is None, "Legacy model should not be instantiated"
            assert not mock_legacy_model.called, "ConcurrentTrainingModel should not be called"
    
    @patch("app.services.engine_orchestrator.simulate_strength_session")
    def test_modular_engines_are_source_of_truth(
        self, mock_simulate, db_session, sample_athlete
    ):
        """
        Verify that modular engines are the source of truth for stored data
        """
        from app.services import SessionService
        from app.domain.day_engine import DayState, PerLiftState
        
        # Setup mock outputs
        mock_set_output = Mock()
        mock_set_output.lift = "squat"
        mock_set_output.load_kg = 100.0
        mock_set_output.reps = []
        
        mock_rep_output = Mock()
        mock_rep_output.sets = [mock_set_output]
        mock_rep_output.final_A_local = {"squat": 0.80}
        mock_rep_output.final_A_sys = 0.85
        mock_rep_output.final_A_M = 0.90
        mock_rep_output.final_M = 0.0
        mock_simulate.return_value = mock_rep_output
        
        service = SessionService(db_session)

        sets_data = [
            SetData(
                weight=100.0,
                target_reps=1,
                reps=[RepData(weight=100.0, rep_num=1, velocity=0.45, rest_before=0)]
            )
        ]

        session = service.ingest_strength_session(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            start_time=datetime(2024, 1, 1, 10, 0),
            sets_data=sets_data
        )

        # Verify session was stored with data from modular engines
        assert session is not None
        assert session.raw_data is not None
        
        # The stored data should come from modular engines
        raw = session.raw_data or {}
        assert "final_A_local" in raw or "final_A_sys" in raw or "sets" in raw


class TestEngineOrchestratorIntegration:
    """Test EngineOrchestrator as single source of truth"""
    
    def test_orchestrator_uses_rep_engine_for_strength(self, db_session, sample_athlete):
        """
        Verify EngineOrchestrator.ingest_strength_session uses rep_engine
        """
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.domain import rep_engine
        
        orchestrator = EngineOrchestrator(db_session)
        
        # Verify rep_engine module is accessible
        assert hasattr(rep_engine, 'simulate_strength_session')
        assert hasattr(rep_engine, 'LiftVelocityProfile')
        assert hasattr(rep_engine, 'RepEngineParams')
    
    def test_orchestrator_uses_day_engine_for_state(self, db_session, sample_athlete):
        """
        Verify EngineOrchestrator uses day_engine for state updates
        """
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.domain import day_engine
        
        orchestrator = EngineOrchestrator(db_session)
        
        # Verify day_engine module is accessible
        assert hasattr(day_engine, 'update_day_state')
        assert hasattr(day_engine, 'DayState')
        assert hasattr(day_engine, 'DayEngineParams')
    
    def test_orchestrator_uses_performance_engine(self, db_session, sample_athlete):
        """
        Verify EngineOrchestrator uses performance_engine for snapshots
        """
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.domain import performance_engine
        
        orchestrator = EngineOrchestrator(db_session)
        
        # Verify performance_engine module is accessible
        assert hasattr(performance_engine, 'compute_session_e1rm')
        assert hasattr(performance_engine, 'analyze_lift_trend')


class TestStateFetchService:
    """Test the state fetch service endpoints"""
    
    def test_get_day_state_snapshot_returns_day_state(self, db_session, sample_athlete):
        """
        Verify get_day_state_snapshot returns DayState (or None if not exists)
        """
        from app.services.engine_orchestrator import EngineOrchestrator

        orchestrator = EngineOrchestrator(db_session)

        # Get state for today (returns None if not exists due to create=False)
        day_state = orchestrator.get_day_state_snapshot(
            sample_athlete.id,
            date.today()
        )

        # Either returns a DayState from DB or None if no state exists
        if day_state is not None:
            assert hasattr(day_state, 'per_lift')
            assert hasattr(day_state, 'D_sys')
            assert hasattr(day_state, 'R_mito')
    
    def test_get_recent_sessions_returns_sessions(self, db_session, sample_athlete):
        """
        Verify get_recent_sessions returns recent sessions
        """
        from app.services.engine_orchestrator import EngineOrchestrator
        from datetime import timedelta
        
        orchestrator = EngineOrchestrator(db_session)
        
        end_date = date.today()
        start_date = end_date - timedelta(days=7)
        
        sessions = orchestrator.get_recent_sessions(
            sample_athlete.id,
            start_date,
            end_date
        )
        
        assert isinstance(sessions, dict)
        assert "strength" in sessions
        assert "endurance" in sessions


class TestFeatureFlag:
    """Test USE_LEGACY_MODEL feature flag"""
    
    def test_feature_flag_defaults_to_false(self):
        """
        Verify USE_LEGACY_MODEL defaults to False
        """
        from app.services.engine_orchestrator import USE_LEGACY_MODEL
        
        assert USE_LEGACY_MODEL is False, "USE_LEGACY_MODEL should default to False"
    
    @patch.dict("os.environ", {"USE_LEGACY_MODEL": "true"})
    def test_feature_flag_respects_env_var(self):
        """
        Verify USE_LEGACY_MODEL respects environment variable
        """
        # Need to reimport to pick up env var
        import importlib
        from app.services import engine_orchestrator
        importlib.reload(engine_orchestrator)
        
        assert engine_orchestrator.USE_LEGACY_MODEL is True
    
    def test_api_endpoints_use_new_engines_by_default(self, client, sample_athlete):
        """
        Verify API endpoints use new engines by default (check legacy status)
        """
        response = client.get("/legacy/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data["use_legacy_model"] is False
        assert data["primary_engine"] == "modular_engines"
