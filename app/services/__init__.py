"""Service layer with one canonical runtime model path."""
from app.services.legacy_services import AthleteService
from app.services.session_service import SessionService
from app.services.runtime_services import DayUpdateService, ReadinessService, AutoregulationService
from app.services.engine_orchestrator import EngineOrchestrator
from app.services.workout_service import CombinedWorkoutIngestor


def _ingest_combined_workout(self, workout):
    """Simulate all exercises once so systemic/metabolic state carries across lifts."""
    return CombinedWorkoutIngestor(self).ingest(workout)


# Compose the combined-workout capability onto the canonical service while
# retaining the historical class import path used by integrations and tests.
SessionService.ingest_strength_workout = _ingest_combined_workout

__all__ = [
    "AthleteService",
    "SessionService",
    "DayUpdateService",
    "ReadinessService",
    "AutoregulationService",
    "EngineOrchestrator",
]
