"""Service layer with one canonical runtime model path."""
from app.services.legacy_services import AthleteService
from app.services.session_service import SessionService
from app.services.runtime_services import DayUpdateService, ReadinessService, AutoregulationService
from app.services.engine_orchestrator import EngineOrchestrator
from app.services.workout_service import CombinedWorkoutIngestor
from app.services.velocity_profile_service import VelocityProfileService


_base_ingest_strength_session = SessionService.ingest_strength_session


def _ingest_strength_with_profile_calibration(self, *args, **kwargs):
    session = _base_ingest_strength_session(self, *args, **kwargs)
    VelocityProfileService(self.db).update_from_recent_sessions(
        session.athlete_id,
        session.lift,
        reference_date=session.start_time.date(),
    )
    return session


def _ingest_combined_workout(self, workout):
    """Simulate all exercises once so systemic/metabolic state carries across lifts."""
    sessions = CombinedWorkoutIngestor(self).ingest(workout)
    calibrator = VelocityProfileService(self.db)
    seen = set()
    for session in sessions:
        if session.lift in seen:
            continue
        seen.add(session.lift)
        calibrator.update_from_recent_sessions(
            session.athlete_id,
            session.lift,
            reference_date=session.start_time.date(),
        )
    return sessions


# Compose canonical ingestion capabilities while retaining the historical class
# import path used by integrations and tests.
SessionService.ingest_strength_session = _ingest_strength_with_profile_calibration
SessionService.ingest_strength_workout = _ingest_combined_workout

__all__ = [
    "AthleteService",
    "SessionService",
    "DayUpdateService",
    "ReadinessService",
    "AutoregulationService",
    "EngineOrchestrator",
]
