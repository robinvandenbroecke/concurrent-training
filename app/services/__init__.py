"""Service layer with one canonical runtime model path.

Only athlete/session persistence adapters are imported from the compatibility
module. Readiness, trends, daily carry-over, and autoregulation are backed by
the hardened engines.
"""
from app.services.legacy_services import AthleteService, SessionService
from app.services.runtime_services import DayUpdateService, ReadinessService, AutoregulationService
from app.services.engine_orchestrator import EngineOrchestrator

__all__ = [
    "AthleteService",
    "SessionService",
    "DayUpdateService",
    "ReadinessService",
    "AutoregulationService",
    "EngineOrchestrator",
]
