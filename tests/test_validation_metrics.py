"""
Sprint V1: Tests for validation metrics
"""
import pytest
from app.eval.validation import (
    compute_rep_level_metrics,
    compute_day_level_strength_metrics,
    compute_trend_classification_metrics,
    compute_endurance_classification_metrics,
    predict_perf_y_from_readiness,
    ValidationReport,
)


class TestRepLevelMetrics:
    """Test rep-level velocity prediction metrics."""
    
    def test_perfect_predictions_zero_error(self):
        """Perfect predictions should have zero RMSE and MAE."""
        predicted = [0.45, 0.43, 0.40, 0.38, 0.35]
        observed = [0.45, 0.43, 0.40, 0.38, 0.35]
        
        metrics = compute_rep_level_metrics(predicted, observed)
        
        assert metrics.rmse == pytest.approx(0.0, abs=1e-9)
        assert metrics.mae == pytest.approx(0.0, abs=1e-9)
        assert metrics.n_samples == 5
    
    def test_constant_error(self):
        """Constant error should give correct RMSE and MAE."""
        predicted = [0.40, 0.40, 0.40]
        observed = [0.45, 0.45, 0.45]
        
        metrics = compute_rep_level_metrics(predicted, observed)
        
        # Constant error of 0.05
        assert metrics.rmse == pytest.approx(0.05, abs=1e-9)
        assert metrics.mae == pytest.approx(0.05, abs=1e-9)
    
    def test_mixed_errors(self):
        """Mixed positive/negative errors."""
        predicted = [0.40, 0.40, 0.40, 0.40]
        observed = [0.42, 0.38, 0.41, 0.39]  # Errors: +0.02, -0.02, +0.01, -0.01
        
        metrics = compute_rep_level_metrics(predicted, observed)
        
        # MAE = (0.02 + 0.02 + 0.01 + 0.01) / 4 = 0.015
        assert metrics.mae == pytest.approx(0.015, abs=1e-6)
        
        # RMSE = sqrt((0.0004 + 0.0004 + 0.0001 + 0.0001) / 4) = sqrt(0.001/4) = 0.0158...
        expected_rmse = ((0.02**2 + 0.02**2 + 0.01**2 + 0.01**2) / 4) ** 0.5
        assert metrics.rmse == pytest.approx(expected_rmse, rel=1e-3)
    
    def test_empty_lists(self):
        """Empty lists should return zero metrics."""
        metrics = compute_rep_level_metrics([], [])
        
        assert metrics.rmse == 0.0
        assert metrics.mae == 0.0
        assert metrics.n_samples == 0
    
    def test_mismatched_lengths_raises(self):
        """Mismatched lengths should raise ValueError."""
        with pytest.raises(ValueError):
            compute_rep_level_metrics([0.4, 0.4], [0.45])


class TestDayLevelMetrics:
    """Test day-level performance prediction metrics."""
    
    def test_perfect_predictions(self):
        """Perfect predictions should have zero MAE."""
        predicted = [0.85, 0.90, 0.95]
        observed = [0.85, 0.90, 0.95]
        
        metrics = compute_day_level_strength_metrics(predicted, observed)
        
        assert metrics.mae == pytest.approx(0.0, abs=1e-9)
        assert metrics.n_samples == 3
    
    def test_known_errors(self):
        """Known error pattern."""
        predicted = [0.80, 0.85, 0.90]  # Slightly pessimistic
        observed = [0.85, 0.90, 0.95]   # Actually better
        
        metrics = compute_day_level_strength_metrics(predicted, observed)
        
        # MAE = (0.05 + 0.05 + 0.05) / 3 = 0.05
        assert metrics.mae == pytest.approx(0.05, abs=1e-9)
    
    def test_empty_lists(self):
        """Empty lists should return zero metrics."""
        metrics = compute_day_level_strength_metrics([], [])
        
        assert metrics.mae == 0.0
        assert metrics.n_samples == 0


class TestTrendClassificationMetrics:
    """Test trend classification metrics."""
    
    def test_perfect_classification(self):
        """100% accuracy when all predictions match."""
        predicted = ["progress", "stagnation", "regression", "progress"]
        observed = ["progress", "stagnation", "regression", "progress"]
        
        metrics = compute_trend_classification_metrics(predicted, observed)
        
        assert metrics.accuracy == pytest.approx(1.0, abs=1e-9)
        assert metrics.n_samples == 4
    
    def test_random_classification_50_percent(self):
        """50% accuracy when half match."""
        predicted = ["progress", "progress", "stagnation", "stagnation"]
        observed = ["progress", "regression", "stagnation", "progress"]
        
        metrics = compute_trend_classification_metrics(predicted, observed)
        
        # 2 out of 4 correct
        assert metrics.accuracy == pytest.approx(0.5, abs=1e-9)
    
    def test_confusion_matrix(self):
        """Confusion matrix should count correctly."""
        predicted = ["progress", "progress", "stagnation"]
        observed = ["progress", "stagnation", "stagnation"]
        
        metrics = compute_trend_classification_metrics(predicted, observed)
        
        # progress predicted as progress: 1
        assert metrics.confusion_matrix["progress"]["progress"] == 1
        # progress predicted as stagnation: 1 (error)
        assert metrics.confusion_matrix["progress"]["stagnation"] == 1
        # stagnation predicted as stagnation: 1
        assert metrics.confusion_matrix["stagnation"]["stagnation"] == 1


class TestEnduranceClassification:
    """Test endurance binary classification."""
    
    def test_perfect_binary_classification(self):
        """100% accuracy for binary case."""
        predicted = [True, True, False, False]
        observed = [True, True, False, False]
        
        result = compute_endurance_classification_metrics(predicted, observed)
        
        assert result["accuracy"] == pytest.approx(1.0, abs=1e-9)
        assert result["n_samples"] == 4
    
    def test_all_false_predicted(self):
        """Case with all predictions False."""
        predicted = [False, False, False]
        observed = [False, True, False]
        
        result = compute_endurance_classification_metrics(predicted, observed)
        
        # 2 out of 3 correct
        assert result["accuracy"] == pytest.approx(2/3, abs=1e-6)


class TestReadinessToPerfY:
    """Test readiness to perf_y mapping."""
    
    def test_readiness_1_0(self):
        """Maximum readiness gives max perf_y."""
        pred = predict_perf_y_from_readiness(1.0)
        assert pred == pytest.approx(1.0, abs=1e-9)
    
    def test_readiness_0_0(self):
        """Zero readiness gives baseline perf_y."""
        pred = predict_perf_y_from_readiness(0.0)
        assert pred == pytest.approx(0.75, abs=1e-9)
    
    def test_readiness_0_5(self):
        """Mid readiness gives mid perf_y."""
        pred = predict_perf_y_from_readiness(0.5)
        assert pred == pytest.approx(0.875, abs=1e-9)
    
    def test_clamping_high(self):
        """High values are clamped."""
        pred = predict_perf_y_from_readiness(2.0)
        assert pred == 1.10  # Max clamp
    
    def test_clamping_low(self):
        """Low values are clamped."""
        pred = predict_perf_y_from_readiness(-1.0)
        assert pred == 0.60  # Min clamp


class TestValidationReport:
    """Test validation report structure."""
    
    def test_report_to_dict(self):
        """Report should serialize to dict correctly."""
        from datetime import date
        
        report = ValidationReport(
            athlete_id=1,
            date_range=(date(2024, 1, 1), date(2024, 3, 1)),
            rep_level_rmse=0.05,
            rep_level_mae=0.04,
            day_level_mae_model=0.06,
            day_level_mae_baseline_a=0.08,
            day_level_mae_baseline_b=0.07,
        )
        
        d = report.to_dict()
        
        assert d["athlete_id"] == 1
        assert d["date_from"] == "2024-01-01"
        assert d["date_to"] == "2024-03-01"
        assert d["rep_level"]["rmse"] == 0.05
        assert d["rep_level"]["mae"] == 0.04
        assert d["day_level_strength"]["mae_model"] == 0.06
