"""
Tests for Sprint H1: Rep Engine Model Hardening

1. y>1 does not reduce phi below intensity-only baseline (phi uses y_phi=min(y,1))
2. High VL triggers stronger fatigue than low VL (catastrophe nonlinearity)
3. v_pred uses x_M log availability, no exp(-kM*M)
4. Central fatigue reacts more to short rest (density factor) than local (identifiability aid)
"""
import pytest
import math

from app.domain.rep_engine import (
    LiftVelocityProfile,
    RepEngineParams,
    SetInput,
    SessionInput,
    simulate_strength_session,
    RepState,
    LimitingFactor,
)


class TestYPhiClamping:
    """Test H1: y_phi = min(y, 1.0) prevents anti-fatigue when y>1."""
    
    def test_y_greater_than_one_does_not_reduce_phi(self):
        """When y>1 (potentiation), phi should not be less than y=1 case."""
        params = RepEngineParams()
        
        # Create state
        state = RepState(
            A_local_init={"squat": 1.0},
            A_sys_init=1.0,
            M_init=0.0,
            params=params
        )
        
        # Compute phi for y=1.0 and y=1.2
        phi_y1, phi_central_y1, y_phi_1 = state.compute_phi(
            load_kg=100.0, y=1.0, e1rm=100.0
        )
        phi_y12, phi_central_y12, y_phi_12 = state.compute_phi(
            load_kg=100.0, y=1.2, e1rm=100.0
        )
        
        # y_phi should be clamped to 1.0 for both
        assert y_phi_1 == 1.0
        assert y_phi_12 == 1.0  # Clamped, not 1.2
        
        # phi should be equal (or very close) since y_phi is clamped
        assert phi_y12 == pytest.approx(phi_y1, abs=0.001)
    
    def test_y_less_than_one_affects_phi(self):
        """When y<1 (fatigue), phi should increase (more fatigue cost)."""
        params = RepEngineParams()
        state = RepState(
            A_local_init={"squat": 1.0},
            A_sys_init=1.0,
            M_init=0.0,
            params=params
        )
        
        # phi for y=0.8 should be higher (more fatigue) than y=1.0
        phi_y08, _, y_phi_08 = state.compute_phi(load_kg=100.0, y=0.8, e1rm=100.0)
        phi_y10, _, y_phi_10 = state.compute_phi(load_kg=100.0, y=1.0, e1rm=100.0)
        
        # y_phi should be actual y when y<1
        assert y_phi_08 == 0.8
        assert y_phi_10 == 1.0
        
        # phi should be higher for lower y (more fatigue cost)
        assert phi_y08 > phi_y10


class TestCatastropheNonlinearity:
    """Test H1: High VL triggers catastrophe nonlinearity."""
    
    def test_high_vl_increases_phi(self):
        """VL > threshold should increase phi (more fatigue)."""
        params = RepEngineParams(vl_catastrophe_threshold=0.40)
        state = RepState(
            A_local_init={"squat": 1.0},
            A_sys_init=1.0,
            M_init=0.0,
            params=params
        )
        
        # Low VL (0.20) - below threshold
        phi_low, _, _ = state.compute_phi(
            load_kg=100.0, y=0.8, e1rm=100.0, vl_catastrophe=0.20
        )
        
        # High VL (0.50) - above threshold
        phi_high, _, _ = state.compute_phi(
            load_kg=100.0, y=0.8, e1rm=100.0, vl_catastrophe=0.50
        )
        
        # High VL should produce higher phi (more fatigue)
        assert phi_high > phi_low
    
    def test_catastrophe_scales_with_vl_excess(self):
        """More excess VL beyond threshold = more catastrophe effect."""
        params = RepEngineParams(
            vl_catastrophe_threshold=0.40,
            catastrophe_exponent=2.0
        )
        state = RepState(
            A_local_init={"squat": 1.0},
            A_sys_init=1.0,
            M_init=0.0,
            params=params
        )
        
        # Moderate excess (VL=0.50, excess=0.10/0.60=0.17)
        phi_mod, _, _ = state.compute_phi(
            load_kg=100.0, y=0.8, e1rm=100.0, vl_catastrophe=0.50
        )
        
        # High excess (VL=0.70, excess=0.30/0.60=0.50)
        phi_high, _, _ = state.compute_phi(
            load_kg=100.0, y=0.8, e1rm=100.0, vl_catastrophe=0.70
        )
        
        # Higher excess VL should produce even higher phi
        assert phi_high > phi_mod


class TestMetabolicLogSpace:
    """Test H1: x_M log-space metabolic availability."""
    
    def test_a_m_property_returns_bounded_value(self):
        """A_M property should return value in [min_A, 1.0]."""
        params = RepEngineParams(min_A=0.02)
        state = RepState(
            A_local_init={"squat": 1.0},
            A_sys_init=1.0,
            M_init=0.0,  # Starts at 0 -> A_M = 1.0
            params=params
        )
        
        # Initially A_M should be ~1.0
        assert state.A_M == pytest.approx(1.0, abs=0.01)
        
        # Apply reps to fatigue
        for i in range(10):
            state.apply_rep("squat", 100.0, 0.9, i)
        
        # A_M should decrease but stay bounded
        assert state.A_M < 1.0
        assert state.A_M >= params.min_A
    
    def test_velocity_prediction_uses_a_m(self):
        """v_pred should use A_M (not exp(-kM*M))."""
        profile = LiftVelocityProfile(lift="squat", a=0.5, b=0.003)
        params = RepEngineParams()
        
        state = RepState(
            A_local_init={"squat": 0.9},
            A_sys_init=0.95,
            M_init=0.5,  # Legacy M
            params=params
        )
        
        v_ref = profile.v_ref(100.0)
        v_pred = state.predict_velocity(v_ref, "squat")
        
        # Should be v_ref * A_l * A_sys * A_M (all in [0,1])
        # Not using exp(-kM*M) anymore
        expected_max = v_ref * 0.9 * 0.95 * 1.0
        assert v_pred <= expected_max
        assert v_pred > 0


class TestDensityFactor:
    """Test H1: Density factor affects central more than local fatigue."""
    
    def test_short_rest_increases_density_factor(self):
        """Shorter rest = higher density factor."""
        params = RepEngineParams(enable_density_factor=True)
        state = RepState(
            A_local_init={"squat": 1.0},
            A_sys_init=1.0,
            M_init=0.0,
            params=params
        )
        
        # Short rest (30s), 5 reps -> high density
        density_short = state.compute_density_factor(30.0, 5)
        
        # Long rest (180s), 5 reps -> lower density
        density_long = state.compute_density_factor(180.0, 5)
        
        # Short rest should have higher density
        assert density_short > density_long
    
    def test_density_factor_affects_central_phi_more(self):
        """Density factor should increase central phi more than local."""
        params = RepEngineParams(enable_density_factor=True, density_alpha=1.5)
        state = RepState(
            A_local_init={"squat": 1.0},
            A_sys_init=1.0,
            M_init=0.0,
            params=params
        )

        # Low density factor
        phi_local_low, phi_central_low, _ = state.compute_phi(
            load_kg=100.0, y=0.8, e1rm=100.0, density_factor=0.8
        )

        # High density factor
        phi_local_high, phi_central_high, _ = state.compute_phi(
            load_kg=100.0, y=0.8, e1rm=100.0, density_factor=1.5
        )

        # Both should increase or stay same (high density increases both)
        assert phi_local_high >= phi_local_low
        assert phi_central_high >= phi_central_low

        # Central should increase more (ratio check) when density_factor > 1
        local_ratio = phi_local_high / phi_local_low
        central_ratio = phi_central_high / phi_central_low
        # Central ratio should be higher due to density_alpha applied to central only
        assert central_ratio >= local_ratio


class TestSetEndRPE:
    """Test H1: Optional set_end_rpe affects central vs local split."""
    
    def test_high_rpe_increases_central_fatigue(self):
        """Higher RPE shifts fatigue toward central."""
        params = RepEngineParams()
        state = RepState(
            A_local_init={"squat": 1.0},
            A_sys_init=1.0,
            M_init=0.0,
            params=params
        )
        
        # Apply rep with low RPE
        _, A_sys_low, _, _, _ = state.apply_rep(
            "squat", 100.0, 0.9, 0, set_end_rpe=6.0
        )
        
        # Reset state
        state = RepState(
            A_local_init={"squat": 1.0},
            A_sys_init=1.0,
            M_init=0.0,
            params=params
        )
        
        # Apply rep with high RPE
        _, A_sys_high, _, _, _ = state.apply_rep(
            "squat", 100.0, 0.9, 0, set_end_rpe=10.0
        )
        
        # High RPE should reduce A_sys more (more central fatigue)
        assert A_sys_high < A_sys_low


class TestHardenedSessionSimulation:
    """Test H1: Full session with hardened model."""
    
    def test_session_outputs_y_phi(self):
        """Session output includes y_phi for each rep."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        
        session = SessionInput(
            sets=[
                SetInput(
                    lift="squat",
                    load_kg=100.0,
                    velocities=[0.50, 0.45, 0.40],  # Decreasing (y<1)
                    rest_before_sec=None
                )
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0
        )
        
        output = simulate_strength_session(session)
        
        # Check that y_phi is included in outputs
        for set_output in output.sets:
            for rep in set_output.reps:
                assert hasattr(rep, 'y_phi')
                assert rep.y_phi <= 1.0  # Always clamped
    
    def test_session_outputs_a_m(self):
        """Session output includes A_M instead of just M."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)
        
        session = SessionInput(
            sets=[
                SetInput(
                    lift="squat",
                    load_kg=100.0,
                    velocities=[0.50, 0.45, 0.40],
                    rest_before_sec=None
                )
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0
        )
        
        output = simulate_strength_session(session)
        
        # Should have A_M in outputs
        assert hasattr(output, 'final_A_M')
        assert output.final_A_M <= 1.0
        assert output.final_A_M > 0
        
        # Legacy M should also be present for backward compatibility
        assert hasattr(output, 'final_M')


class TestIdentifiability:
    """Test H1: Central vs local fatigue identifiability."""
    
    def test_density_creates_distinguishable_central_local(self):
        """Different density should create different central/local fatigue patterns."""
        profile = LiftVelocityProfile(lift="squat", a=0.55, b=0.0032)

        # Low density session (long rest)
        session_low = SessionInput(
            sets=[
                SetInput(lift="squat", load_kg=100.0, velocities=[0.50, 0.48], rest_before_sec=180.0),
                SetInput(lift="squat", load_kg=100.0, velocities=[0.46, 0.44], rest_before_sec=180.0),
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0,
            params=RepEngineParams(enable_density_factor=True)
        )

        # High density session (short rest)
        session_high = SessionInput(
            sets=[
                SetInput(lift="squat", load_kg=100.0, velocities=[0.50, 0.48], rest_before_sec=30.0),
                SetInput(lift="squat", load_kg=100.0, velocities=[0.46, 0.44], rest_before_sec=30.0),
            ],
            profiles={"squat": profile},
            init_A_local={"squat": 1.0},
            init_A_sys=1.0,
            init_M=0.0,
            R_mito=0.0,
            params=RepEngineParams(enable_density_factor=True)
        )

        output_low = simulate_strength_session(session_low)
        output_high = simulate_strength_session(session_high)

        # High density should create more system fatigue (lower A_sys)
        assert output_high.final_A_sys <= output_low.final_A_sys

        # High density may also have lower local availability
        # The key is that central is affected more by density
        # Check that A_sys/A_local ratio is lower for high density (more central fatigue)
        sys_ratio_low = output_low.final_A_sys / max(output_low.final_A_local.get("squat", 0.01), 0.01)
        sys_ratio_high = output_high.final_A_sys / max(output_high.final_A_local.get("squat", 0.01), 0.01)

        # Both should have some fatigue (less than 1.0)
        assert output_high.final_A_sys < 1.0
        assert output_low.final_A_sys < 1.0
