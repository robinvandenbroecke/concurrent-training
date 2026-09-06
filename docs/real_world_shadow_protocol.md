> Historical specification. The September 2026 [audit](audit_2026_09.md) and [model reference](model_reference.md) supersede conflicting scientific/validation claims. `run_validation.py` is retrospective diagnostics, not leakage-free scientific validation. Older thresholds and calibration artifacts are unvalidated.

# Real-world shadow validation protocol

## Purpose

Run the coach against real training data without allowing it to autonomously alter training. The first objective is data integrity and falsification, not performance claims.

## Required inputs

### Strength

- real session timestamp and performed exercise order
- load and repetitions for every set
- first-rep velocity where available
- full velocity series where available
- rest before each set
- set-end RPE
- initialized lift capacity profile

### Endurance

Signal priority is explicit:

1. cycling or reliable running power relative to athlete threshold power
2. pace plus heart rate
3. duration and declared intensity as a low-confidence fallback

Every endurance session stores `signal_source` in `raw_data` as `power`, `power_unscaled`, or `summary`.

## Shadow period

Use at least four weeks and preferably eight weeks. The model may generate readiness and recommendations, but the athlete or coach retains final control. Store whether each suggestion was accepted and why.

## Evaluation

Run:

```bash
python run_validation.py --source db --athlete-id <id> --days 90
```

The report uses a per-athlete temporal split: the first 70% of target-bearing dates establish baseline history; the final 30% are held out. Predictions are computed before the current session is added.

Required comparisons:

- hardened state model
- rolling velocity threshold
- Banister fitness-fatigue model
- rolling 30-day performance heuristic

Report aggregate and per-lift MAE/RMSE, rep-level error, target availability, and trend F1. A synthetic advantage is not evidence of real-world validity.

## Promotion criteria

Assisted coaching may begin only when:

- ingestion is idempotent and timestamps are correct;
- no repeated same-day decay occurs;
- the model is not materially worse than the strongest baseline on held-out real data;
- no unsafe load or volume recommendations occur during manual review;
- missing-data fallbacks are visible to the user.

Autonomous coaching is outside the current validation stage.

