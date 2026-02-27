"""
Services package - connects domain model to persistence

SPRINT A: CONSOLIDATION - Single Source of Truth
- EngineOrchestrator is the primary service for session ingestion
- Legacy services available for backward compatibility
"""
from app.services.legacy_services import (
    AthleteService,
    SessionService,
    DayUpdateService,
    ReadinessService,
    AutoregulationService,
)
from app.services.engine_orchestrator import EngineOrchestrator

__all__ = [
    "AthleteService",
    "SessionService",
    "DayUpdateService",
    "ReadinessService",
    "AutoregulationService",
    "EngineOrchestrator",
]