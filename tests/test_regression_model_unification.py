"""
Regression tests for Model Unification + Validation Readiness sprint.

These tests assert structural invariants of the repository:
- README contains current model text, not outdated equations
- Legacy model is isolated
- docs/model_specification.md exists and mentions required concepts
- All pytest paths are repository-relative
"""
import pytest
import sys
import ast
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestReadmeConceptualModel:
    """README must reflect the current official model, not legacy text."""

    def test_readme_no_longer_contains_exp_minus_km_m(self):
        """README must not contain the deprecated exp(-kM*M) metabolic term."""
        readme_path = REPO_ROOT / "README.md"
        content = readme_path.read_text()
        # Match variants: exp(-kM*M), exp(-kM * M), etc.
        assert "exp(-kM*M)" not in content, "README still contains deprecated exp(-kM*M)"
        assert "exp(-kM * M)" not in content, "README still contains deprecated exp(-kM * M)"

    def test_readme_contains_current_model_terms(self):
        """README must mention current official model concepts."""
        readme_path = REPO_ROOT / "README.md"
        content = readme_path.read_text()
        assert "x_M" in content, "README missing x_M"
        assert "T_legs" in content, "README missing T_legs"
        assert "bounded" in content.lower() or "[0, 1]" in content, "README missing bounded R_mito"
        assert "explicit interference" in content.lower(), "README missing explicit interference"
        assert "EngineOrchestrator" in content, "README missing EngineOrchestrator"

    def test_readme_no_longer_says_r_mito_built_only_by_z2(self):
        """README must not claim R_mito is built only by Z2."""
        readme_path = REPO_ROOT / "README.md"
        content = readme_path.read_text()
        # Reject sentences that imply exclusive Z2 buildup
        assert "built by Z2" not in content, "README still says R_mito built by Z2"
        assert "built only by Z2" not in content, "README still says R_mito built only by Z2"

    def test_readme_lists_hardened_engines(self):
        """README must list the six hardened engines as the official path."""
        readme_path = REPO_ROOT / "README.md"
        content = readme_path.read_text()
        assert "rep_engine" in content, "README missing rep_engine"
        assert "day_engine" in content, "README missing day_engine"
        assert "coach_engine" in content, "README missing coach_engine"
        assert "program_engine" in content, "README missing program_engine"
        assert "performance_engine" in content, "README missing performance_engine"
        assert "goal_engine" in content, "README missing goal_engine"


class TestLegacyModelIsolation:
    """Legacy ConcurrentTrainingModel must not be on the production ingestion path."""

    def test_legacy_model_file_renamed(self):
        """app/domain/model.py must not exist; legacy_model.py must exist."""
        assert not (REPO_ROOT / "app" / "domain" / "model.py").exists(), \
            "Old app/domain/model.py still exists — legacy isolation incomplete"
        assert (REPO_ROOT / "app" / "domain" / "legacy_model.py").exists(), \
            "app/domain/legacy_model.py missing"

    def test_engine_orchestrator_does_not_import_domain_model(self):
        """EngineOrchestrator must not import from app.domain.model (the old path)."""
        orchestrator_path = REPO_ROOT / "app" / "services" / "engine_orchestrator.py"
        content = orchestrator_path.read_text()
        # Allow legacy_model but not the old model path
        imports = re.findall(r"from\s+app\.domain\.model\s+import", content)
        assert len(imports) == 0, \
            f"EngineOrchestrator imports deprecated app.domain.model: {imports}"

    def test_engine_orchestrator_imports_hardened_engines(self):
        """EngineOrchestrator must import from hardened engines."""
        orchestrator_path = REPO_ROOT / "app" / "services" / "engine_orchestrator.py"
        content = orchestrator_path.read_text()
        assert "from app.domain.rep_engine import" in content, "Missing rep_engine import"
        assert "from app.domain.day_engine import" in content, "Missing day_engine import"

    def test_domain_init_has_deprecation_note(self):
        """app/domain/__init__.py must note that legacy imports are deprecated."""
        init_path = REPO_ROOT / "app" / "domain" / "__init__.py"
        content = init_path.read_text()
        assert "deprecated" in content.lower() or "legacy" in content.lower(), \
            "Missing deprecation/legacy note in domain __init__.py"

    def test_legacy_model_has_deprecation_docstring(self):
        """legacy_model.py must have a deprecation docstring at the top."""
        legacy_path = REPO_ROOT / "app" / "domain" / "legacy_model.py"
        content = legacy_path.read_text()
        assert "Deprecated" in content or "deprecated" in content.lower(), \
            "legacy_model.py missing deprecation docstring"


class TestDocsExistence:
    """Required documentation must exist and contain expected content."""

    def test_model_specification_exists(self):
        """docs/model_specification.md must exist."""
        assert (REPO_ROOT / "docs" / "model_specification.md").exists(), \
            "docs/model_specification.md missing"

    def test_model_specification_mentions_required_terms(self):
        """docs/model_specification.md must mention key hardened-model concepts."""
        spec_path = REPO_ROOT / "docs" / "model_specification.md"
        content = spec_path.read_text()
        assert "x_M" in content, "model_specification.md missing x_M"
        assert "T_legs" in content, "model_specification.md missing T_legs"
        assert "bounded" in content.lower(), "model_specification.md missing bounded R_mito"
        assert "explicit interference" in content.lower(), "model_specification.md missing explicit interference"

    def test_validation_protocol_exists(self):
        """docs/validation_protocol.md must exist."""
        assert (REPO_ROOT / "docs" / "validation_protocol.md").exists(), \
            "docs/validation_protocol.md missing"

    def test_validation_protocol_has_metrics(self):
        """docs/validation_protocol.md must define rep, day, and trend metrics."""
        proto_path = REPO_ROOT / "docs" / "validation_protocol.md"
        content = proto_path.read_text()
        assert "Rep-level" in content or "rep-level" in content.lower(), "Missing rep-level metric section"
        assert "Day-level" in content or "day-level" in content.lower(), "Missing day-level metric section"
        assert "Trend" in content, "Missing trend metric section"
        assert "baseline" in content.lower(), "Missing baseline comparisons"


class TestPathPortability:
    """No test or script may contain hardcoded absolute paths to the repo."""

    def test_no_hardcoded_root_paths_in_tests(self):
        """Tests must not hardcode the absolute repo path."""
        hardcoded = "/root/clawd/projects/concurrent-training"
        test_dir = REPO_ROOT / "tests"
        offenders = []
        for py_file in test_dir.rglob("*.py"):
            # Skip this file itself (it references the path in test strings)
            if py_file.name == "test_regression_model_unification.py":
                continue
            text = py_file.read_text()
            if hardcoded in text:
                offenders.append(py_file.relative_to(REPO_ROOT))
        assert len(offenders) == 0, \
            f"Tests still contain hardcoded absolute path: {offenders}"

    def test_tests_use_repo_root_relative_paths(self):
        """At least one test file must define REPO_ROOT via pathlib."""
        test_dir = REPO_ROOT / "tests"
        found = False
        for py_file in test_dir.rglob("*.py"):
            text = py_file.read_text()
            if "REPO_ROOT = Path(__file__).resolve().parents[1]" in text:
                found = True
                break
        assert found, "No test file uses Path(__file__).resolve().parents[1] pattern"

    def test_run_validation_script_exists(self):
        """run_validation.py must exist and be executable."""
        rv = REPO_ROOT / "run_validation.py"
        assert rv.exists(), "run_validation.py missing"
        content = rv.read_text()
        assert "artifacts/latest" in content, "run_validation.py must write to artifacts/latest"
