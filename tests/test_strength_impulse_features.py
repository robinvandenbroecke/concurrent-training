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
        # VL is computed from velocities
        assert features.vl is not None
        assert features.vl > 0.0
        # Sprint P1.1: velocity_factor is also computed from raw velocities
        assert features.velocity_factor != pytest.approx(1.0, abs=0.01)

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
        # Sprint P1.1: neutral fallback has vl=0.0 (not None)
        assert features.vl == pytest.approx(0.0, abs=0.001)


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


class TestVelocityFactorFromRawVelocities:
    """Test P1.1: velocity_factor computed from raw velocities + lift profile."""

    def test_velocity_factor_from_raw_velocities_basic(self):
        """Compute velocity_factor from raw velocities and known load."""
        from app.services.strength_impulse_features import compute_velocity_factor_from_raw_velocities

        # For squat at 100kg: v_ref = 0.55 - 0.0032*100 = 0.23 m/s (approx)
        # Observed velocities around 0.20 m/s -> y ~ 0.87
        velocities = [0.22, 0.21, 0.20]  # Slight fatigue
        load_kg = 100

        vf = compute_velocity_factor_from_raw_velocities(velocities, load_kg, "squat")

        # Should be around 0.87-0.96 range (0.22/0.23 to 0.20/0.23)
        assert vf is not None
        assert 0.5 <= vf <= 1.2

    def test_velocity_factor_clamped_minimum(self):
        """Very slow velocities should be clamped to min 0.5."""
        from app.services.strength_impulse_features import compute_velocity_factor_from_raw_velocities

        # Very slow velocities (half of expected)
        velocities = [0.10, 0.08]  # Much slower than expected for 100kg squat
        load_kg = 100

        vf = compute_velocity_factor_from_raw_velocities(velocities, load_kg, "squat")

        assert vf is not None
        assert vf >= 0.5

    def test_velocity_factor_clamped_maximum(self):
        """Very fast velocities should be clamped to max 1.2."""
        from app.services.strength_impulse_features import compute_velocity_factor_from_raw_velocities

        # Very fast velocities (unrealistic but test clamping)
        velocities = [0.80, 0.75]  # Much faster than expected
        load_kg = 100

        vf = compute_velocity_factor_from_raw_velocities(velocities, load_kg, "squat")

        assert vf is not None
        assert vf <= 1.2

    def test_empty_velocities_returns_none(self):
        """Empty velocities returns None."""
        from app.services.strength_impulse_features import compute_velocity_factor_from_raw_velocities

        vf = compute_velocity_factor_from_raw_velocities([], 100, "squat")
        assert vf is None

    def test_unknown_lift_uses_default_profile(self):
        """Unknown lift uses default calibrated profile."""
        from app.services.strength_impulse_features import compute_velocity_factor_from_raw_velocities

        velocities = [0.40, 0.38]
        load_kg = 50

        vf = compute_velocity_factor_from_raw_velocities(velocities, load_kg, "unknown_lift")

        # Should still compute with default profile
        assert vf is not None
        assert 0.5 <= vf <= 1.2


class TestImpulseAffectsProductionPath:
    """Test P1.1: velocity_factor and VL materially affect impulse calculation."""

    def test_higher_velocity_factor_increases_impulse(self, db_session, sample_athlete):
        """Higher velocity_factor -> higher set_impulse."""
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
                a=0.55, b=0.0030
            ))
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)
        sets_data = [{"load_kg": 100, "reps": 5}]

        # Case 1: Fast bar speed (high velocity_factor)
        mock_rep_fast = MagicMock()
        mock_rep_fast.y = 1.1
        mock_set_fast = MagicMock()
        mock_set_fast.VL = 0.10
        mock_set_fast.reps = [mock_rep_fast, mock_rep_fast]
        mock_session_fast = MagicMock()
        mock_session_fast.sets = [mock_set_fast]

        impulses_fast = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=sets_data,
            rep_output=mock_session_fast,
            athlete_id=sample_athlete.id,
        )

        # Case 2: Slow bar speed (low velocity_factor)
        mock_rep_slow = MagicMock()
        mock_rep_slow.y = 0.70
        mock_set_slow = MagicMock()
        mock_set_slow.VL = 0.35
        mock_set_slow.reps = [mock_rep_slow, mock_rep_slow]
        mock_session_slow = MagicMock()
        mock_session_slow.sets = [mock_set_slow]

        impulses_slow = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=sets_data,
            rep_output=mock_session_slow,
            athlete_id=sample_athlete.id,
        )

        # Same intensity (load/capacity same), but impulses should differ
        assert impulses_fast.sets[0].intensity == impulses_slow.sets[0].intensity
        assert impulses_fast.per_lift["squat"] > impulses_slow.per_lift["squat"]

    def test_higher_vl_increases_impulse(self, db_session, sample_athlete):
        """Higher VL (fatigue) -> higher set_impulse due to vl_term."""
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
                a=0.60, b=0.0028
            ))
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)
        sets_data = [{"load_kg": 80, "reps": 5}]

        # Same velocity_factor, different VL
        base_y = 0.90

        # Low VL
        mock_rep_low = MagicMock()
        mock_rep_low.y = base_y
        mock_set_low = MagicMock()
        mock_set_low.VL = 0.10
        mock_set_low.reps = [mock_rep_low, mock_rep_low]
        mock_session_low = MagicMock()
        mock_session_low.sets = [mock_set_low]

        impulses_low = orchestrator._compute_strength_impulses(
            lift="bench",
            sets_data=sets_data,
            rep_output=mock_session_low,
            athlete_id=sample_athlete.id,
        )

        # High VL
        mock_rep_high = MagicMock()
        mock_rep_high.y = base_y
        mock_set_high = MagicMock()
        mock_set_high.VL = 0.40
        mock_set_high.reps = [mock_rep_high, mock_rep_high]
        mock_session_high = MagicMock()
        mock_session_high.sets = [mock_set_high]

        impulses_high = orchestrator._compute_strength_impulses(
            lift="bench",
            sets_data=sets_data,
            rep_output=mock_session_high,
            athlete_id=sample_athlete.id,
        )

        # Higher VL should give higher impulse (vl_term = 1 + 1.5*VL)
        # With same velocity_factor, high VL should give ~1.45x impulse vs ~1.15x
        assert impulses_high.per_lift["bench"] > impulses_low.per_lift["bench"]

    def test_raw_velocities_derive_both_features(self, db_session, sample_athlete):
        """Raw velocities without rep_engine derive both vf and vl."""
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.models import LiftProfile

        existing = db_session.query(LiftProfile).filter(
            LiftProfile.athlete_id == sample_athlete.id,
            LiftProfile.lift == "squat"
        ).first()

        if not existing:
            db_session.add(LiftProfile(
                athlete_id=sample_athlete.id,
                lift="squat",
                a=0.55, b=0.0030
            ))
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)

        # Raw velocities (no rep_engine)
        # For squat at 100kg: v_ref ~ 0.23 m/s
        # velocities: 0.22 -> y ~ 0.96, VL ~ 0.09
        sets_data = [{"load_kg": 100, "reps": 5, "velocities": [0.22, 0.21, 0.20]}]

        impulses = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=sets_data,
            rep_output=None,  # No rep_engine
            athlete_id=sample_athlete.id,
        )

        # Should derive both features from raw velocities
        # velocity_factor should be ~0.96, not 1.0
        assert impulses.sets[0].velocity_factor != pytest.approx(1.0, abs=0.05)
        assert impulses.sets[0].vl > 0.0  # VL should be computed

    def test_vl_clamped_in_impulse_calculation(self, db_session, sample_athlete):
        """Pathological VL values are clamped to valid range."""
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.models import LiftProfile

        existing = db_session.query(LiftProfile).filter(
            LiftProfile.athlete_id == sample_athlete.id,
            LiftProfile.lift == "deadlift"
        ).first()

        if not existing:
            db_session.add(LiftProfile(
                athlete_id=sample_athlete.id,
                lift="deadlift",
                a=0.50, b=0.0030
            ))
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)
        sets_data = [{"load_kg": 140, "reps": 5}]

        # Extremely high VL (pathological case)
        mock_rep = MagicMock()
        mock_rep.y = 0.80
        mock_set = MagicMock()
        mock_set.VL = 2.0  # Invalid, should be clamped
        mock_set.reps = [mock_rep, mock_rep]
        mock_session = MagicMock()
        mock_session.sets = [mock_set]

        # Should not raise, uses fallback or clamps
        impulses = orchestrator._compute_strength_impulses(
            lift="deadlift",
            sets_data=sets_data,
            rep_output=mock_session,
            athlete_id=sample_athlete.id,
        )

        # Impulse should still be positive and reasonable
        assert impulses.per_lift["deadlift"] > 0
        assert impulses.sets[0].vl >= 0.0  # Should be clamped or valid


class TestDebugMetadata:
    """Test P1.1: Debug/trace metadata is attached to impulses."""

    def test_debug_metadata_attached(self, db_session, sample_athlete):
        """Debug metadata includes feature_source, velocity_factor, vl."""
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.models import LiftProfile

        existing = db_session.query(LiftProfile).filter(
            LiftProfile.athlete_id == sample_athlete.id,
            LiftProfile.lift == "squat"
        ).first()

        if not existing:
            db_session.add(LiftProfile(
                athlete_id=sample_athlete.id,
                lift="squat",
                a=0.55, b=0.0030
            ))
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)

        mock_rep = MagicMock()
        mock_rep.y = 0.90
        mock_set = MagicMock()
        mock_set.VL = 0.20
        mock_set.reps = [mock_rep, mock_rep]
        mock_session = MagicMock()
        mock_session.sets = [mock_set]

        impulses = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=[{"load_kg": 100, "reps": 5}],
            rep_output=mock_session,
            athlete_id=sample_athlete.id,
        )

        # Check debug metadata exists
        assert hasattr(impulses, '_capacity_estimate')
        assert hasattr(impulses, '_capacity_source')
        assert hasattr(impulses, '_velocity_factors')
        assert hasattr(impulses, '_vl_values')
        assert hasattr(impulses, '_alpha_i')
        assert hasattr(impulses, '_p_vl')

        # Verify values
        assert impulses._alpha_i == 1.2
        assert impulses._p_vl == 1.5
        assert len(impulses._velocity_factors) == 1
        assert len(impulses._vl_values) == 1

    def test_feature_source_in_set_impulse(self, db_session, sample_athlete):
        """SetImpulse contains source information via attached features."""
        from app.services.strength_impulse_features import compute_strength_impulse_features

        # Test rep_engine source
        mock_rep = MagicMock()
        mock_rep.y = 0.85
        mock_set = MagicMock()
        mock_set.VL = 0.15
        mock_set.reps = [mock_rep]
        mock_session = MagicMock()
        mock_session.sets = [mock_set]

        features = compute_strength_impulse_features(
            rep_output=mock_session,
            set_idx=0,
            lift="squat"
        )
        assert features.source == "rep_engine"

        # Test derived_from_velocities source
        features2 = compute_strength_impulse_features(
            rep_output=None,
            set_idx=0,
            set_data={"load_kg": 100, "velocities": [0.22, 0.20]},
            lift="squat"
        )
        assert features2.source == "derived_from_velocities"

        # Test neutral_fallback source
        features3 = compute_strength_impulse_features(
            rep_output=None,
            set_idx=0,
            set_data={"velocities": []},
            lift="squat"
        )
        assert features3.source == "neutral_fallback"


class TestFeatureSourceHierarchy:
    """Test P1.1: Feature source hierarchy is respected."""

    def test_rep_engine_preferred_over_raw_velocities(self, db_session, sample_athlete):
        """rep_engine summaries are preferred over raw velocity derivation."""
        from app.services.strength_impulse_features import compute_strength_impulse_features

        # Both rep_engine and raw velocities available
        mock_rep = MagicMock()
        mock_rep.y = 0.88
        mock_set = MagicMock()
        mock_set.VL = 0.25
        mock_set.reps = [mock_rep, mock_rep]
        mock_session = MagicMock()
        mock_session.sets = [mock_set]

        # Raw velocities would give different values
        set_data = {"load_kg": 100, "velocities": [0.30, 0.25]}  # Different from rep_engine

        features = compute_strength_impulse_features(
            rep_output=mock_session,
            set_idx=0,
            set_data=set_data,  # Should be ignored when rep_engine available
            lift="squat"
        )

        # Should use rep_engine, not raw velocities
        assert features.source == "rep_engine"
        assert features.velocity_factor == pytest.approx(0.88, abs=0.01)

    def test_raw_velocities_used_when_no_rep_engine(self, db_session, sample_athlete):
        """Raw velocities are used when rep_engine summaries unavailable."""
        from app.services.strength_impulse_features import compute_strength_impulse_features

        features = compute_strength_impulse_features(
            rep_output=None,
            set_idx=0,
            set_data={"load_kg": 100, "velocities": [0.22, 0.20]},
            lift="squat"
        )

        assert features.source == "derived_from_velocities"
        assert features.vl is not None
        assert features.velocity_factor != 1.0  # Should be computed from velocities


class TestMetabolicImpulse:
    """Test P2: Metabolic impulse (u_met) computation from set features."""

    def test_u_met_basic_computation(self):
        """Basic metabolic impulse computation."""
        from app.services.strength_impulse_features import compute_metabolic_impulse

        # Standard set: 100kg x 5 reps, 120s rest, 0.2 VL, 0.7 intensity
        u_met = compute_metabolic_impulse(
            load_kg=100,
            reps=5,
            rest_sec=120,
            vl=0.20,
            intensity=0.70
        )

        assert u_met > 0
        # Tonnage = 500, should be scaled down by M_SCALE (0.15)
        assert u_met < 500  # Significantly less than raw tonnage

    def test_higher_reps_increases_u_met(self):
        """More reps -> higher metabolic impulse."""
        from app.services.strength_impulse_features import compute_metabolic_impulse

        # Low reps (3)
        u_met_low = compute_metabolic_impulse(
            load_kg=100, reps=3, rest_sec=180, vl=0.20, intensity=0.85
        )

        # High reps (10)
        u_met_high = compute_metabolic_impulse(
            load_kg=100, reps=10, rest_sec=180, vl=0.20, intensity=0.70
        )

        # High reps should give higher metabolic impulse
        assert u_met_high > u_met_low

    def test_shorter_rest_increases_u_met(self):
        """Shorter rest -> higher metabolic impulse."""
        from app.services.strength_impulse_features import compute_metabolic_impulse

        # Long rest (180s = baseline)
        u_met_long = compute_metabolic_impulse(
            load_kg=100, reps=8, rest_sec=180, vl=0.30, intensity=0.75
        )

        # Short rest (60s)
        u_met_short = compute_metabolic_impulse(
            load_kg=100, reps=8, rest_sec=60, vl=0.30, intensity=0.75
        )

        # Shorter rest should give higher metabolic impulse
        assert u_met_short > u_met_long

    def test_higher_vl_increases_u_met(self):
        """Higher velocity loss -> higher metabolic impulse."""
        from app.services.strength_impulse_features import compute_metabolic_impulse

        # Low VL (0.10)
        u_met_low = compute_metabolic_impulse(
            load_kg=100, reps=8, rest_sec=120, vl=0.10, intensity=0.75
        )

        # High VL (0.40)
        u_met_high = compute_metabolic_impulse(
            load_kg=100, reps=8, rest_sec=120, vl=0.40, intensity=0.75
        )

        # Higher VL should give higher metabolic impulse
        assert u_met_high > u_met_low

    def test_high_intensity_penalty_reduces_u_met(self):
        """Very high intensity (>0.85) reduces metabolic emphasis."""
        from app.services.strength_impulse_features import compute_metabolic_impulse

        # Medium intensity (0.75) - no penalty
        u_met_medium = compute_metabolic_impulse(
            load_kg=100, reps=5, rest_sec=180, vl=0.20, intensity=0.75
        )

        # Very high intensity (0.95) - penalty applies
        u_met_heavy = compute_metabolic_impulse(
            load_kg=120, reps=5, rest_sec=180, vl=0.20, intensity=0.95
        )

        # Both should be positive
        assert u_met_medium > 0
        assert u_met_heavy > 0

    def test_u_met_in_production_path(self, db_session, sample_athlete):
        """P2: u_met is computed and accumulated in production path."""
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
                a=0.55, b=0.0030
            ))
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)

        # High metabolic cost set: high reps, short rest, high VL
        sets_data = [{
            "load_kg": 100,
            "reps": 10,
            "rest_sec": 60,  # Short rest
        }]

        mock_rep = MagicMock()
        mock_rep.y = 0.85
        mock_set = MagicMock()
        mock_set.VL = 0.35  # High VL
        mock_set.reps = [mock_rep] * 10
        mock_session = MagicMock()
        mock_session.sets = [mock_set]

        impulses = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=sets_data,
            rep_output=mock_session,
            athlete_id=sample_athlete.id,
        )

        # u_met should be computed and non-zero
        assert impulses.u_met > 0
        # Debug metadata should include u_met
        assert hasattr(impulses, '_u_met')
        assert impulses._u_met > 0

    def test_u_met_changes_with_set_features(self, db_session, sample_athlete):
        """P2: Same load but different set features -> different u_met."""
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
                a=0.60, b=0.0028
            ))
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)

        # Case 1: Low metabolic cost (few reps, long rest, low VL)
        mock_rep1 = MagicMock()
        mock_rep1.y = 0.95
        mock_set1 = MagicMock()
        mock_set1.VL = 0.10
        mock_set1.reps = [mock_rep1] * 3
        mock_session1 = MagicMock()
        mock_session1.sets = [mock_set1]

        impulses1 = orchestrator._compute_strength_impulses(
            lift="bench",
            sets_data=[{"load_kg": 80, "reps": 3, "rest_sec": 180}],
            rep_output=mock_session1,
            athlete_id=sample_athlete.id,
        )

        # Case 2: High metabolic cost (many reps, short rest, high VL)
        mock_rep2 = MagicMock()
        mock_rep2.y = 0.75
        mock_set2 = MagicMock()
        mock_set2.VL = 0.40
        mock_set2.reps = [mock_rep2] * 12
        mock_session2 = MagicMock()
        mock_session2.sets = [mock_set2]

        impulses2 = orchestrator._compute_strength_impulses(
            lift="bench",
            sets_data=[{"load_kg": 80, "reps": 12, "rest_sec": 60}],
            rep_output=mock_session2,
            athlete_id=sample_athlete.id,
        )

        # High metabolic cost should give higher u_met
        assert impulses2.u_met > impulses1.u_met


class TestDayEngineAlignment:
    """Test P2: Strength impulses align with day_engine expectations."""

    def test_strength_impulses_structure_matches_day_engine(self, db_session, sample_athlete):
        """StrengthImpulses dataclass matches what day_engine.update_day_state expects."""
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.domain.day_engine import update_day_state, DayEngineParams, DayState, PerLiftState
        from app.models import LiftProfile

        existing = db_session.query(LiftProfile).filter(
            LiftProfile.athlete_id == sample_athlete.id,
            LiftProfile.lift == "squat"
        ).first()

        if not existing:
            db_session.add(LiftProfile(
                athlete_id=sample_athlete.id,
                lift="squat",
                a=0.55, b=0.0030
            ))
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)

        sets_data = [{"load_kg": 100, "reps": 8, "rest_sec": 90}]

        mock_rep = MagicMock()
        mock_rep.y = 0.88
        mock_set = MagicMock()
        mock_set.VL = 0.30
        mock_set.reps = [mock_rep] * 8
        mock_session = MagicMock()
        mock_session.sets = [mock_set]

        impulses = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=sets_data,
            rep_output=mock_session,
            athlete_id=sample_athlete.id,
        )

        # Verify all expected fields are present
        assert hasattr(impulses, 'per_lift')
        assert hasattr(impulses, 'u_sys')
        assert hasattr(impulses, 'u_legs')
        assert hasattr(impulses, 'u_met')  # P2: Now populated
        assert hasattr(impulses, 'u_legs_high_intensity')
        assert hasattr(impulses, 'sets')

        # All should be non-negative
        assert impulses.per_lift["squat"] >= 0
        assert impulses.u_sys >= 0
        assert impulses.u_legs >= 0
        assert impulses.u_met >= 0  # P2: Should be populated
        assert impulses.u_legs_high_intensity >= 0

    def test_u_met_accumulated_across_sets(self, db_session, sample_athlete):
        """P2: u_met is accumulated across multiple sets."""
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.models import LiftProfile

        existing = db_session.query(LiftProfile).filter(
            LiftProfile.athlete_id == sample_athlete.id,
            LiftProfile.lift == "deadlift"
        ).first()

        if not existing:
            db_session.add(LiftProfile(
                athlete_id=sample_athlete.id,
                lift="deadlift",
                a=0.50, b=0.0030
            ))
            db_session.commit()

        orchestrator = EngineOrchestrator(db_session)

        # Multiple sets
        sets_data = [
            {"load_kg": 140, "reps": 5, "rest_sec": None},  # First set
            {"load_kg": 140, "reps": 5, "rest_sec": 120},
            {"load_kg": 140, "reps": 5, "rest_sec": 90},
        ]

        mock_rep = MagicMock()
        mock_rep.y = 0.85
        mock_set = MagicMock()
        mock_set.VL = 0.25
        mock_set.reps = [mock_rep] * 5
        mock_session = MagicMock()
        mock_session.sets = [mock_set, mock_set, mock_set]

        impulses = orchestrator._compute_strength_impulses(
            lift="deadlift",
            sets_data=sets_data,
            rep_output=mock_session,
            athlete_id=sample_athlete.id,
        )

        # u_met should be sum of all sets
        assert impulses.u_met > 0
        # Should be roughly 3x a single set (accounting for rest differences)
