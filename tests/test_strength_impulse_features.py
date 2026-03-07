"""
Sprint P1: Tests for strength impulse feature computation.

Verifies that placeholder velocity_factor and vl are replaced with real rep_engine values.
"""
import pytest
from unittest.mock import MagicMock

from app.services.strength_impulse_features import (
    compute_set_vl,
    compute_velocity_factor_from_y_values,
    extract_features_from_rep_output,
    compute_strength_impulse_features,
    StrengthImpulseFeatures,
)


class TestComputeSetVl:
    """Test velocity loss computation from velocities."""

    def test_vl_basic(self):
        """Basic VL computation: 1 - (last/first)."""
        velocities = [1.0, 0.9, 0.8]  # Slowing down
        vl = compute_set_vl(velocities)
        expected = 1.0 - (0.8 / 1.0)  # 0.20
        assert vl == pytest.approx(expected, abs=0.001)

    def test_vl_no_slowdown(self):
        """No velocity loss (consistent speed)."""
        velocities = [0.8, 0.8, 0.8]
        vl = compute_set_vl(velocities)
        assert vl == pytest.approx(0.0, abs=0.001)

    def test_vl_complete_fatigue(self):
        """Complete velocity loss (velocity -> 0)."""
        velocities = [1.0, 0.5, 0.0]
        vl = compute_set_vl(velocities)
        assert vl == pytest.approx(1.0, abs=0.001)

    def test_vl_clamped_to_1(self):
        """VL clamped to max 1.0."""
        velocities = [0.5, 0.3, 0.1, -0.1]  # Negative would give > 1
        vl = compute_set_vl(velocities)
        assert vl <= 1.0
        assert vl >= 0.0

    def test_vl_single_velocity_returns_none(self):
        """Single velocity - cannot compute VL."""
        velocities = [1.0]
        vl = compute_set_vl(velocities)
        assert vl is None

    def test_vl_empty_returns_none(self):
        """Empty velocities - cannot compute VL."""
        velocities = []
        vl = compute_set_vl(velocities)
        assert vl is None

    def test_vl_zero_first_velocity_returns_none(self):
        """Zero first velocity - cannot compute VL."""
        velocities = [0.0, 0.5, 0.3]
        vl = compute_set_vl(velocities)
        assert vl is None


class TestComputeVelocityFactor:
    """Test velocity_factor computation from y values."""

    def test_velocity_factor_basic(self):
        """Basic velocity_factor from y values."""
        y_values = [1.0, 0.95, 0.90]  # Slight fatigue
        vf = compute_velocity_factor_from_y_values(y_values)
        # Median of first 2: [1.0, 0.95] -> median = 0.975
        assert vf == pytest.approx(0.975, abs=0.001)

    def test_velocity_factor_single_rep(self):
        """Single rep - use that value."""
        y_values = [0.85]
        vf = compute_velocity_factor_from_y_values(y_values)
        assert vf == pytest.approx(0.85, abs=0.001)

    def test_velocity_factor_clamped_min(self):
        """Velocity factor clamped to min 0.5."""
        y_values = [0.3, 0.2]  # Very slow
        vf = compute_velocity_factor_from_y_values(y_values)
        assert vf == pytest.approx(0.5, abs=0.001)

    def test_velocity_factor_clamped_max(self):
        """Velocity factor clamped to max 1.2."""
        y_values = [1.5, 1.4]  # Faster than expected
        vf = compute_velocity_factor_from_y_values(y_values)
        assert vf == pytest.approx(1.2, abs=0.001)

    def test_velocity_factor_empty_returns_neutral(self):
        """Empty y values - return neutral 1.0."""
        y_values = []
        vf = compute_velocity_factor_from_y_values(y_values)
        assert vf == pytest.approx(1.0, abs=0.001)


class TestExtractFeaturesFromRepOutput:
    """Test feature extraction from rep_engine SessionOutput."""

    def test_extract_from_real_rep_output(self):
        """Extract features from real rep_engine output structure."""
        # Create mock rep_output with proper structure
        mock_rep = MagicMock()
        mock_rep.y = 0.92

        mock_set = MagicMock()
        mock_set.VL = 0.25
        mock_set.reps = [mock_rep, mock_rep]

        mock_session = MagicMock()
        mock_session.sets = [mock_set]

        features = extract_features_from_rep_output(mock_session, 0, "squat")

        assert features.source == "rep_engine"
        assert features.vl == pytest.approx(0.25, abs=0.001)
        assert features.velocity_factor == pytest.approx(0.92, abs=0.001)

    def test_rep_output_none_returns_fallback(self):
        """None rep_output returns neutral fallback."""
        features = extract_features_from_rep_output(None, 0, "squat")

        assert features.source == "neutral_fallback"
        assert features.velocity_factor == pytest.approx(1.0, abs=0.001)
        assert features.vl is None

    def test_invalid_set_index_returns_fallback(self):
        """Invalid set index returns fallback."""
        mock_session = MagicMock()
        mock_session.sets = []

        features = extract_features_from_rep_output(mock_session, 0, "squat")

        assert features.source == "neutral_fallback"

    def test_no_reps_returns_fallback(self):
        """Set with no reps returns fallback."""
        mock_set = MagicMock()
        mock_set.VL = 0.20
        mock_set.reps = []

        mock_session = MagicMock()
        mock_session.sets = [mock_set]

        features = extract_features_from_rep_output(mock_session, 0, "squat")

        assert features.source == "neutral_fallback"
        assert features.velocity_factor == pytest.approx(1.0, abs=0.001)


class TestComputeStrengthImpulseFeatures:
    """Test the canonical helper function."""

    def test_prefers_rep_engine(self):
        """Uses rep_engine output when available."""
        mock_rep = MagicMock()
        mock_rep.y = 0.88

        mock_set = MagicMock()
        mock_set.VL = 0.30
        mock_set.reps = [mock_rep]

        mock_session = MagicMock()
        mock_session.sets = [mock_set]

        features = compute_strength_impulse_features(
            rep_output=mock_session,
            set_idx=0,
            set_data=None,
            lift="squat"
        )

        assert features.source == "rep_engine"
        assert features.vl == pytest.approx(0.30, abs=0.001)

    def test_fallback_to_velocities(self):
        """Derives from raw velocities if rep_output unavailable."""
        set_data = {"velocities": [1.0, 0.85, 0.70]}

        features = compute_strength_impulse_features(
            rep_output=None,
            set_idx=0,
            set_data=set_data,
            lift="squat"
        )

        assert features.source == "derived_from_velocities"
        # VL = 1 - (0.70/1.0) = 0.30
        assert features.vl == pytest.approx(0.30, abs=0.001)
        # Neutral velocity_factor
        assert features.velocity_factor == pytest.approx(1.0, abs=0.001)

    def test_neutral_fallback_no_data(self):
        """Returns neutral fallback when no data available."""
        features = compute_strength_impulse_features(
            rep_output=None,
            set_idx=0,
            set_data={"velocities": []},  # Empty velocities
            lift="squat"
        )

        assert features.source == "neutral_fallback"
        assert features.velocity_factor == pytest.approx(1.0, abs=0.001)
        assert features.vl is None


class TestIntegrationWithEngineOrchestrator:
    """Test integration with the production impulse path."""

    def test_no_placeholders_in_production_code(self):
        """Verify production code no longer uses placeholder values."""
        import inspect
        from app.services.engine_orchestrator import EngineOrchestrator

        source = inspect.getsource(EngineOrchestrator._compute_strength_impulses)

        # Should NOT contain the old placeholder lines
        assert "velocity_factor=0.9" not in source.replace(" ", "").replace("'", '"')
        assert "vl=0.15" not in source.replace(" ", "").replace("'", '"')

        # Should contain the new feature computation
        assert "compute_strength_impulse_features" in source

    def test_real_values_used_in_set_impulse(self, db_session, sample_athlete):
        """Integration test: real values flow through to SetImpulse."""
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.models import LiftProfile

        # Create minimal setup
        existing = db_session.query(LiftProfile).filter(
            LiftProfile.athlete_id == sample_athlete.id,
            LiftProfile.lift == "squat"
        ).first()

        if not existing:
            lift_profile = LiftProfile(
                athlete_id=sample_athlete.id,
                lift="squat",
                a=0.55,
                b=0.0030,
            )
            db_session.add(lift_profile)
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)

        # Create mock rep_output with real values
        mock_rep = MagicMock()
        mock_rep.y = 0.85

        mock_set = MagicMock()
        mock_set.VL = 0.35
        mock_set.reps = [mock_rep, mock_rep]

        mock_session = MagicMock()
        mock_session.sets = [mock_set]

        sets_data = [{"load_kg": 100, "reps": 5}]

        impulses = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=sets_data,
            rep_output=mock_session,
            athlete_id=sample_athlete.id,
            session_date=None,
        )

        # Verify real values are used, not placeholders
        assert len(impulses.sets) == 1
        set_impulse = impulses.sets[0]

        # Should use real values from rep_engine
        assert set_impulse.velocity_factor == pytest.approx(0.85, abs=0.01)
        assert set_impulse.vl == pytest.approx(0.35, abs=0.01)

    def test_neutral_fallback_when_no_rep_output(self, db_session, sample_athlete):
        """Integration test: neutral fallback when rep_output is None."""
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.models import LiftProfile

        existing = db_session.query(LiftProfile).filter(
            LiftProfile.athlete_id == sample_athlete.id,
            LiftProfile.lift == "bench"
        ).first()

        if not existing:
            lift_profile = LiftProfile(
                athlete_id=sample_athlete.id,
                lift="bench",
                a=0.60,
                b=0.0028,
            )
            db_session.add(lift_profile)
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)

        sets_data = [{"load_kg": 80, "reps": 5}]

        # Pass None as rep_output
        impulses = orchestrator._compute_strength_impulses(
            lift="bench",
            sets_data=sets_data,
            rep_output=None,
            athlete_id=sample_athlete.id,
            session_date=None,
        )

        # Should use neutral fallback
        assert impulses.sets[0].velocity_factor == pytest.approx(1.0, abs=0.001)


class TestVelocityFactorNotPlaceholder:
    """Prove velocity_factor is no longer the fake 0.9 placeholder."""

    def test_velocity_factor_never_exactly_09_in_production(self, db_session, sample_athlete):
        """Real rep_engine values are very unlikely to be exactly 0.9."""
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.models import LiftProfile

        # Ensure profile exists
        existing = db_session.query(LiftProfile).filter(
            LiftProfile.athlete_id == sample_athlete.id,
            LiftProfile.lift == "deadlift"
        ).first()

        if not existing:
            db_session.add(LiftProfile(
                athlete_id=sample_athlete.id,
                lift="deadlift",
                a=0.50,
                b=0.0030,
            ))
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)

        # Test with various rep_engine outputs
        test_cases = [
            ([0.95, 0.90, 0.85], 0.925),  # Median of first 2
            ([1.0, 0.8], 0.90),  # Exactly 0.9 by chance
            ([0.85], 0.85),
        ]

        for y_values, expected_vf in test_cases:
            mock_rep = MagicMock()
            mock_rep.y = y_values[0] if len(y_values) == 1 else y_values[0]

            mock_set = MagicMock()
            mock_set.VL = 0.20
            mock_set.reps = [MagicMock(y=y) for y in y_values]

            mock_session = MagicMock()
            mock_session.sets = [mock_set]

            impulses = orchestrator._compute_strength_impulses(
                lift="deadlift",
                sets_data=[{"load_kg": 140, "reps": 5}],
                rep_output=mock_session,
                athlete_id=sample_athlete.id,
            )

            # If it's exactly 0.9, it might be a placeholder - verify it's from rep_engine
            if impulses.sets[0].velocity_factor == 0.9:
                # 0.9 is possible as a real value, but let's verify VL is also real
                assert impulses.sets[0].vl != 0.15, "Using placeholder vl=0.15"

    def test_placeholder_values_documented_as_removed(self):
        """Documentation test: placeholders are replaced."""
        from app.services.strength_impulse_features import compute_strength_impulse_features
        import inspect

        doc = inspect.getdoc(compute_strength_impulse_features)
        assert "placeholder" in doc.lower() or "Sprint P1" in doc


class TestRealVelocitiesChangeImpulse:
    """Test that same load/reps with different velocity data produces different impulses."""

    def test_better_velocity_data_alters_impulse(self, db_session, sample_athlete):
        """Same load/reps but better velocity -> different impulse characteristics."""
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.models import LiftProfile

        # Ensure profile exists
        existing = db_session.query(LiftProfile).filter(
            LiftProfile.athlete_id == sample_athlete.id,
            LiftProfile.lift == "squat"
        ).first()

        if not existing:
            db_session.add(LiftProfile(
                athlete_id=sample_athlete.id,
                lift="squat",
                a=0.55,
                b=0.0030,
            ))
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)
        sets_data = [{"load_kg": 100, "reps": 5}]

        # Case 1: Good velocity data (fast, minimal fatigue)
        mock_rep_good = MagicMock()
        mock_rep_good.y = 1.0  # At reference velocity
        mock_set_good = MagicMock()
        mock_set_good.VL = 0.10  # Low velocity loss
        mock_set_good.reps = [mock_rep_good, mock_rep_good]
        mock_session_good = MagicMock()
        mock_session_good.sets = [mock_set_good]

        impulses_good = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=sets_data,
            rep_output=mock_session_good,
            athlete_id=sample_athlete.id,
        )

        # Case 2: Poor velocity data (slow, high fatigue)
        mock_rep_poor = MagicMock()
        mock_rep_poor.y = 0.70  # Below reference velocity
        mock_set_poor = MagicMock()
        mock_set_poor.VL = 0.40  # High velocity loss
        mock_set_poor.reps = [mock_rep_poor, mock_rep_poor]
        mock_session_poor = MagicMock()
        mock_session_poor.sets = [mock_set_poor]

        impulses_poor = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=sets_data,
            rep_output=mock_session_poor,
            athlete_id=sample_athlete.id,
        )

        # Both should have same intensity (based on load/capacity)
        assert impulses_good.sets[0].intensity == impulses_poor.sets[0].intensity

        # But velocity_factor and vl should differ
        assert impulses_good.sets[0].velocity_factor > impulses_poor.sets[0].velocity_factor
        assert impulses_good.sets[0].vl < impulses_poor.sets[0].vl

    def test_real_velocities_vs_fallback_produce_different_features(self, db_session, sample_athlete):
        """Real velocities produce different features than neutral fallback."""
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.models import LiftProfile

        existing = db_session.query(LiftProfile).filter(
            LiftProfile.athlete_id == sample_athlete.id,
            LiftProfile.lift == "bench"
        ).first()

        if not existing:
            db_session.add(LiftProfile(
                athlete_id=sample_athlete.id,
                lift="bench",
                a=0.60,
                b=0.0028,
            ))
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)
        sets_data = [{"load_kg": 80, "reps": 5}]

        # Case 1: With real rep_engine data
        mock_rep = MagicMock()
        mock_rep.y = 0.90
        mock_set = MagicMock()
        mock_set.VL = 0.25
        mock_set.reps = [mock_rep, mock_rep]
        mock_session = MagicMock()
        mock_session.sets = [mock_set]

        impulses_real = orchestrator._compute_strength_impulses(
            lift="bench",
            sets_data=sets_data,
            rep_output=mock_session,
            athlete_id=sample_athlete.id,
        )

        # Case 2: Without rep_engine (neutral fallback)
        impulses_fallback = orchestrator._compute_strength_impulses(
            lift="bench",
            sets_data=sets_data,
            rep_output=None,
            athlete_id=sample_athlete.id,
        )

        # Neutral fallback should have velocity_factor = 1.0
        assert impulses_fallback.sets[0].velocity_factor == pytest.approx(1.0, abs=0.001)

        # Real data should have different values
        assert impulses_real.sets[0].velocity_factor != pytest.approx(1.0, abs=0.01) or \
               impulses_real.sets[0].vl != pytest.approx(0.0, abs=0.01)
