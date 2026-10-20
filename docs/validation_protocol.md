> Historical specification. The September 2026 [audit](audit_2026_09.md) and [model reference](model_reference.md) supersede conflicting scientific/validation claims. `run_validation.py` is retrospective diagnostics, not leakage-free scientific validation. Older thresholds and calibration artifacts are unvalidated.

# Validation Protocol

**Version**: Sprint H1  
**Date**: 2026-05-16

---

## 1. Purpose

Define reproducible metrics, thresholds, and baselines for validating the concurrent-training model. All commands are runnable from the repository root.

---

## 2. Metrics

### 2.1 Rep-level metric

**Target**: Predict next-rep velocity given current state.

**Computation**:
1. For every rep `r` in every set (excluding the last rep of each set):
2. Use state after rep `r` to predict velocity of rep `r+1`.
3. Compare `v_pred` vs `v_obs`.

**Primary scores**:
- **RMSE** = `sqrt(mean((v_pred − v_obs)^2))`
- **MAE** = `mean(|v_pred − v_obs|)`

**Acceptance criterion**:
- RMSE ≤ 0.05 m/s for squat/bench on trained profiles.
- RMSE ≤ 0.08 m/s for deadlift/press (higher natural variance).

### 2.2 Day-level metric

**Target**: Predict next-day first-rep or top-set performance.

**Computation**:
1. For each day `d` with a strength session:
2. Use `day_engine` state at the start of day `d` (carried over from `d−1`) to predict the first-rep velocity of the first work set.
3. Alternative: predict the heaviest quality set’s performance metric `perf_y`.

**Primary score**:
- **Next-day first-rep RMSE** (m/s)
- **Next-day top-set error** (absolute difference in `perf_y`)

**Acceptance criterion**:
- Next-day first-rep RMSE ≤ 0.08 m/s.
- Top-set error ≤ 0.10 in `perf_y` units.

### 2.3 Trend metric

**Target**: Classify microcycle-level progress, stagnation, or regression.

**Computation**:
1. Group sessions into microcycles (7-day blocks).
2. For each lift, compute `performance_engine` signal:
   - `progress` if EWMA slope > +0.015 and `perf_y` increased
   - `stagnation` if |EWMA slope| ≤ 0.015
   - `regression` if EWMA slope < −0.015 and `perf_y` decreased
3. Compare to ground truth (synthetic labels or expert-annotated real data).

**Primary score**:
- **F1 macro** across {progress, stagnation, regression}

**Acceptance criterion**:
- F1 macro ≥ 0.60 on synthetic data.
- F1 macro ≥ 0.50 on real-world data (noisier labels).

---

## 3. Baseline Comparisons

All model evaluations must report side-by-side against:

### 3.1 Simple VBT threshold
- Next-rep velocity = `v_ref * 0.95`
- Stop rule: VL > 20 %
- No fatigue state, no history.

### 3.2 Simple Banister / FFM
- One `F` and `D` per lift.
- `perf_y = F − D`
- Decay: `F_t+1 = F_t * exp(−1/45)`, `D_t+1 = D_t * exp(−1/7)`
- Update: `D += k * tonnage`, `F += k * tonnage / 3`

### 3.3 Rolling e1RM / readiness heuristic
- `readiness = last_e1RM / max_e1RM_last_30d`
- `v_pred = readiness * v_ref`
- No metabolic or system components.

---

## 4. Hold-out Policy

1. **Per-athlete time split**: train on first 70 % of days, test on last 30 %.
2. **No lookahead**: day `d` predictions may only use sessions up to `d−1`.
3. **Lift-stratified**: report metrics per lift; do not aggregate across lifts unless sample sizes justify it.

---

## 5. Minimum Reporting Table

Every validation run must produce an artifact containing at least:

```json
{
  "run_date": "2026-05-16",
  "data_source": "synthetic_v2 | real_db",
  "n_athletes": 10,
  "hold_out_days": 30,
  "metrics": {
    "rep_rmse": {"squat": 0.042, "bench": 0.038, ...},
    "rep_mae": {"squat": 0.031, ...},
    "day_first_rep_rmse": {"squat": 0.065, ...},
    "day_top_set_error": {"squat": 0.08, ...},
    "trend_f1_macro": 0.62
  },
  "baselines": {
    "vbt_threshold": {"rep_rmse": {"squat": 0.089, ...}},
    "banister": {"day_first_rep_rmse": {"squat": 0.12, ...}},
    "rolling_e1rm": {"day_top_set_error": {"squat": 0.15, ...}}
  }
}
```

---

## 6. Running Validation

### 6.1 Quick test (unit tests)
```bash
python3 -m pytest -q
```
Expected: all tests pass.

### 6.2 Full validation on synthetic data
```bash
python3 run_validation.py --source synthetic --athletes 10 --days 90
```
Artifacts written to `artifacts/latest/`.

### 6.3 Validation on real database
```bash
python3 run_validation.py --source db --athlete-id 1 --days 90
```
Requires PostgreSQL running and populated.

### 6.4 Replay evaluation
```bash
python3 run_replay.py
```
Replays all stored sessions and writes `artifacts/eval_strength_YYYY_MM/report.json`.

---

## 7. Reproducibility Checklist

- [ ] `pytest -q` passes with no warnings (except deprecation).
- [ ] All paths in test files use `Path(__file__).resolve().parents[1]`.
- [ ] `docs/model_specification.md` exists and mentions `x_M`, `T_legs`, `bounded R_mito`, `explicit interference`.
- [ ] `run_validation.py` completes without error and writes `artifacts/latest/validation_report.json`.
- [ ] Baseline comparisons are included in the report.
