# Research reference — experimental

This independent standard-library reference exists to make model comparisons
inspectable. It does not validate the application's complex rep/day engines.
Read [model equations](../docs/model_reference.md) and the
[research protocol](../docs/research_protocol.md) before using it on real data.

```bash
python -m unittest discover -s tests -p test_scientific_audit.py -v
python -m research.evaluate \
  --manifest research/example_manifest.json \
  --events research/example_events.csv \
  --output artifacts/audit_2026_09/reference_demo.json
```

The supplied files are explicitly synthetic, contain no participants, and are
frozen test fixtures. Their outcome trajectory uses a sine trend, gradual drift
and noise, not the tested model's state equations. They demonstrate reproducibility
and allow a simple baseline to win. Do not present their errors as human validation.

## Input contract

The JSON manifest labels `data_source` (`synthetic` or `real`), provides a fixed
`test_start` per athlete and separately measured lift-specific calibration profiles:
`a`, `b`, `min_load_kg`, `max_load_kg`, `calibrated_before`. It may provide candidate
parameters. Calibration must predate every event. The caller is responsible for
verifying that declared calibration values and real/synthetic labels are true.

CSV columns:

| Field | Meaning |
|---|---|
| event_id | Unique stable ID; duplicates rejected |
| athlete_id | Pseudonymous ID matching the manifest |
| timestamp | ISO 8601 with UTC offset; chronological within athlete |
| kind | `observation`, `strength`, or `endurance` |
| lift | Calibrated lift for observation/strength; empty for endurance |
| load_kg | Probe load, for observations |
| velocity_m_s | Actual observed velocity, for observations |
| dose | Nonnegative completed exposure, for strength/endurance |

Dose events are not observations. Record the probe's exposure separately at the
appropriate completed timestamp. Endurance dose updates all tracked lifts for the
athlete. Equal-time events use CSV order; make observation-before-dose order explicit.
Every forecast is emitted before its outcome is assimilated. Earlier forecasts
cannot change when later observations are changed, as checked by tests.

The report includes SHA-256 input hashes, fixed parameters, raw m/s forecasts,
train/test labels, paired metrics and limitations. Test cutoffs never change because
additional future rows were appended. No application database, cached day state or
live capacity service is consulted. This is a fixed-parameter exploratory evaluation;
fit/tune baselines and candidate models using the full prespecified protocol before
claiming a fair scientific superiority comparison.
