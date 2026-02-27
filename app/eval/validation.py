"""
Sprint V1: Validation Module - Objective prediction error metrics

Computes falsifiable metrics comparing model predictions to observed outcomes.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from datetime import date, timedelta
import math
import statistics


@dataclass
class RepLevelMetrics:
    """Rep-level velocity prediction errors."""
    rmse: float  # Root mean squared error
    mae: float   # Mean absolute error
    n_samples: int
    errors: List[float] = field(default_factory=list)


@dataclass
class DayLevelMetrics:
    """Day-level performance prediction errors."""
    mae: float           # Mean absolute error
    mape: float          # Mean absolute percentage error
    n_samples: int
    predictions: List[Tuple[float, float]] = field(default_factory=list)  # (predicted, observed)


@dataclass
class TrendClassificationMetrics:
    """Trend classification accuracy."""
    accuracy: float
    precision: float
    recall: float
    f1: float
    confusion_matrix: Dict[str, Dict[str, int]]  # predicted -> actual
    n_samples: int


@dataclass
class ValidationReport:
    """Complete validation report for an athlete."""
    athlete_id: int
    date_range: Tuple[date, date]
    
    # Rep-level (strength, VBT)
    rep_level_rmse: Optional[float] = None
    rep_level_mae: Optional[float] = None
    
    # Day-level (strength)
    day_level_mae_model: Optional[float] = None
    day_level_mae_baseline_a: Optional[float] = None
    day_level_mae_baseline_b: Optional[float] = None
    
    # Day-level (endurance)
    endurance_accuracy_model: Optional[float] = None
    endurance_accuracy_baseline: Optional[float] = None
    
    # Trend-level
    trend_accuracy_model: Optional[float] = None
    trend_accuracy_baseline_a: Optional[float] = None
    trend_accuracy_baseline_b: Optional[float] = None
    
    def to_dict(self) -> Dict:
        return {
            "athlete_id": self.athlete_id,
            "date_from": self.date_range[0].isoformat(),
            "date_to": self.date_range[1].isoformat(),
            "rep_level": {
                "rmse": self.rep_level_rmse,
                "mae": self.rep_level_mae,
            },
            "day_level_strength": {
                "mae_model": self.day_level_mae_model,
                "mae_baseline_a": self.day_level_mae_baseline_a,
                "mae_baseline_b": self.day_level_mae_baseline_b,
            },
            "day_level_endurance": {
                "accuracy_model": self.endurance_accuracy_model,
                "accuracy_baseline": self.endurance_accuracy_baseline,
            },
            "trend_level": {
                "accuracy_model": self.trend_accuracy_model,
                "accuracy_baseline_a": self.trend_accuracy_baseline_a,
                "accuracy_baseline_b": self.trend_accuracy_baseline_b,
            }
        }


def compute_rep_level_metrics(
    predicted_velocities: List[float],
    observed_velocities: List[float]
) -> RepLevelMetrics:
    """
    Compute rep-level velocity prediction errors.
    
    Args:
        predicted_velocities: List of predicted velocities (v_pred before observing)
        observed_velocities: List of observed velocities (v_obs)
    
    Returns:
        RepLevelMetrics with RMSE, MAE
    """
    if len(predicted_velocities) != len(observed_velocities):
        raise ValueError("Predicted and observed must have same length")
    
    n = len(predicted_velocities)
    if n == 0:
        return RepLevelMetrics(rmse=0.0, mae=0.0, n_samples=0, errors=[])
    
    errors = [obs - pred for pred, obs in zip(predicted_velocities, observed_velocities)]
    squared_errors = [e ** 2 for e in errors]
    
    rmse = math.sqrt(sum(squared_errors) / n)
    mae = sum(abs(e) for e in errors) / n
    
    return RepLevelMetrics(
        rmse=round(rmse, 6),
        mae=round(mae, 6),
        n_samples=n,
        errors=errors
    )


def compute_day_level_strength_metrics(
    predicted_perf_y: List[float],
    observed_perf_y: List[float]
) -> DayLevelMetrics:
    """
    Compute day-level performance prediction errors.
    
    Args:
        predicted_perf_y: List of predicted performance ratios (0.6-1.1)
        observed_perf_y: List of observed performance ratios
    
    Returns:
        DayLevelMetrics with MAE, MAPE
    """
    if len(predicted_perf_y) != len(observed_perf_y):
        raise ValueError("Predicted and observed must have same length")
    
    n = len(predicted_perf_y)
    if n == 0:
        return DayLevelMetrics(mae=0.0, mape=0.0, n_samples=0, predictions=[])
    
    abs_errors = [abs(obs - pred) for pred, obs in zip(predicted_perf_y, observed_perf_y)]
    mae = sum(abs_errors) / n
    
    # MAPE with protection against zero
    pct_errors = []
    for pred, obs in zip(predicted_perf_y, observed_perf_y):
        if obs != 0:
            pct_errors.append(abs((obs - pred) / obs))
        else:
            pct_errors.append(0.0)
    mape = sum(pct_errors) / n * 100 if pct_errors else 0.0
    
    return DayLevelMetrics(
        mae=round(mae, 6),
        mape=round(mape, 6),
        n_samples=n,
        predictions=list(zip(predicted_perf_y, observed_perf_y))
    )


def compute_trend_classification_metrics(
    predicted_classes: List[str],  # "progress", "stagnation", "regression"
    observed_classes: List[str]
) -> TrendClassificationMetrics:
    """
    Compute trend classification accuracy metrics.
    
    Args:
        predicted_classes: List of predicted trend classifications
        observed_classes: List of observed trend classifications
    
    Returns:
        TrendClassificationMetrics with accuracy, precision, recall, F1, confusion matrix
    """
    if len(predicted_classes) != len(observed_classes):
        raise ValueError("Predicted and observed must have same length")
    
    n = len(predicted_classes)
    if n == 0:
        return TrendClassificationMetrics(
            accuracy=0.0, precision=0.0, recall=0.0, f1=0.0,
            confusion_matrix={}, n_samples=0
        )
    
    # Accuracy
    correct = sum(1 for p, o in zip(predicted_classes, observed_classes) if p == o)
    accuracy = correct / n
    
    # Confusion matrix: predicted -> actual counts
    classes = ["progress", "stagnation", "regression"]
    confusion = {c: {c2: 0 for c2 in classes} for c in classes}
    for p, o in zip(predicted_classes, observed_classes):
        if p in confusion and o in confusion[p]:
            confusion[p][o] += 1
    
    # Precision, recall, F1 per class (macro-averaged)
    precisions = []
    recalls = []
    
    for c in classes:
        tp = confusion[c][c]
        fp = sum(confusion[p][c] for p in classes if p != c)
        fn = sum(confusion[c][o] for o in classes if o != c)
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        
        precisions.append(precision)
        recalls.append(recall)
    
    avg_precision = sum(precisions) / len(precisions)
    avg_recall = sum(recalls) / len(recalls)
    f1 = 2 * avg_precision * avg_recall / (avg_precision + avg_recall) if (avg_precision + avg_recall) > 0 else 0.0
    
    return TrendClassificationMetrics(
        accuracy=round(accuracy, 6),
        precision=round(avg_precision, 6),
        recall=round(avg_recall, 6),
        f1=round(f1, 6),
        confusion_matrix=confusion,
        n_samples=n
    )


def compute_endurance_classification_metrics(
    predicted_stable: List[bool],  # True = stable/improve, False = decline
    observed_stable: List[bool]
) -> Dict:
    """
    Compute binary classification accuracy for endurance trend prediction.
    
    Returns accuracy and confusion matrix.
    """
    n = len(predicted_stable)
    if n == 0:
        return {"accuracy": 0.0, "n_samples": 0, "confusion": {}}
    
    correct = sum(1 for p, o in zip(predicted_stable, observed_stable) if p == o)
    accuracy = correct / n
    
    # Confusion: predicted -> observed
    confusion = {
        "predicted_stable": {"actual_stable": 0, "actual_decline": 0},
        "predicted_decline": {"actual_stable": 0, "actual_decline": 0}
    }
    
    for p, o in zip(predicted_stable, observed_stable):
        p_key = "predicted_stable" if p else "predicted_decline"
        o_key = "actual_stable" if o else "actual_decline"
        confusion[p_key][o_key] += 1
    
    return {
        "accuracy": round(accuracy, 6),
        "n_samples": n,
        "confusion": confusion
    }


def predict_perf_y_from_readiness(readiness: float) -> float:
    """
    Map readiness score (0-1) to predicted perf_y.
    
    Simple fit-free mapping:
    - readiness 1.0 -> perf_y 1.0
    - readiness 0.0 -> perf_y 0.75
    - clamped to [0.60, 1.10]
    """
    # Linear mapping: perf_y = 0.75 + 0.25 * readiness
    pred = 0.75 + 0.25 * readiness
    return max(0.60, min(1.10, pred))
