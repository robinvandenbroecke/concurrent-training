# Research protocol and publication decision

Working protocol, not registered and not approved by an ethics committee.
No recruitment, human data collection, manuscript submission or results fabrication
is implied. Updated 6 September 2026.

## Novelty assessment

A fatigue–fitness model, a load–velocity profile, state-space estimation, RPE-based
autoregulation, and combining strength/endurance inputs already have substantial
precedent. Their combination in an app does not establish methodological novelty.
Existing work includes Banister/Busso modelling, Kalman-filter performance tracking
(Kolossa et al., 2017), critical analyses of parameter estimation (Marchal et al.,
2025), and a 2025 VBT/Kalman tutorial preprint by Swinton. The preprint is a priority
lead whose existence and abstract were found; a complete comparison with its full
text is still required. See [evidence register](evidence_register.md).

The plausible contribution is a parsimonious, transparent, reproducible forecasting
system that uses appropriately timed resistance-exercise measurements and survives
honest comparisons on unseen sessions and unseen athletes. Practical utility must
then be tested separately. Novel terminology or extra compartments are not a
contribution in themselves.

## Primary study: strength forecasting

**Provisional title:** Prospective prediction of standardized resistance-exercise
velocity using a parsimonious load-response model: comparison with simple baselines.

**Primary question:** Does a preregistered model predict the next standardized
submaximal probe velocity more accurately than a prespecified simple comparator?
The primary comparator should be chosen before the final evaluation (for example
last observation or EWMA based on development data), not the weakest convenient
baseline. Prespecify one primary lift/outcome/horizon; other lifts and horizons
are secondary. A within-set velocity predictor and a next-session predictor are
different tasks and should not share an ambiguous endpoint.

**Initial population:** healthy adult recreationally trained lifters performing
regular strength exercise, with concurrent endurance exposure logged from day one.
Do not initially mix youth, postoperative rehabilitation, elite weightlifters and
untrained returners in one undifferentiated calibration. Return from detraining
can be a prespecified subgroup once sample size permits.

**Feasibility phase:** approximately 20–30 participants for 8–12 weeks is a planning
range to estimate measurement error, adherence, variability, recruitment and data
completeness. It is not a powered efficacy sample and may be insufficient for
between-athlete generalization. Determine definitive sample size by simulation
using pilot estimates of within-athlete autocorrelation, inter-athlete variation,
missingness and the smallest useful difference in prediction error. Hundreds of
reps from ten athletes do not create hundreds of independent participants.

**Measurements:** fixed device and velocity definition; prespecified warm-up and
probe loads within a separately calibrated range; same exercise execution and
maximal concentric intent; timestamped reps, loads, rest and set-end RPE; symptoms,
technique deviations, exercise order, sleep/illness flags, session duration,
endurance mode and raw available power/heart-rate data. Record device changes and
calibration dates. A probe induces fatigue and contributes to the exposure log.
Use periodic standardized performance tests when needed to anchor the construct,
without requiring maximal testing at every session.

A personal log such as one athlete's training history is useful for feasibility and
software debugging, but cannot establish population validity or prove the model's
novelty. No unavailable historical velocities should be reconstructed as if measured.

## Data and temporal design

1. Freeze the protocol, primary outcome, exclusions, comparison family, error
   tolerance, model equations, dose definitions and analysis plan before test data.
2. Reserve an initial calibration phase. Store calibration measurements and the
   calibration end time. Initial models must not depend on final athlete profiles.
3. Use a development cohort for feature/parameter design. Nested rolling-origin
   validation operates entirely inside development data. Select model complexity
   and hyperparameters there; report that selection process.
4. Lock a final chronological test period with cutoffs fixed in advance. Save each
   forecast, input cutoff and model version before the outcome is observed.
5. Test transportability on separate athletes, ideally a later cohort/site or
   different device after explicit recalibration. Athlete ID cannot straddle
   development and external validation in a way that leaks individual parameters.
6. Every model sees the same preceding observations and exposure events, including
   training sessions with no valid probe. Outcomes are raw m/s; no clipping of
   difficult measurements to improve apparent error.
7. Label missing measurements and exclusions with reasons. Report coverage by
   athlete, lift, fatigue level and effort; study whether unusable data correlate
   with worse performance. Avoid selecting only the heaviest “good” set after
   observing its RPE/velocity loss as the sole primary endpoint.

The new `research/evaluate.py` supplies a minimal event-based, fixed-parameter
prequential comparison and input hashes. It does **not** implement the full fitted
analysis, confidence intervals, nested optimization, sample-size simulation or
external cohort study described here. The old `run_validation.py` is only runtime
diagnostics and must not be used to claim leakage-free performance.

## Analysis plan

Primary metric: held-out MAE in m/s, with a prespecified clinically/practically useful
difference grounded in device/protocol repeatability. Secondary: RMSE, signed bias,
relative error where denominators remain meaningful, calibration, prediction-interval
coverage/width, coverage/abstention, within-athlete and between-athlete summaries.
Report both athlete-weighted and observation-weighted results. Use paired comparisons
on identical targets. Confidence intervals should resample athletes and respect
within-athlete temporal blocks, or use an appropriate hierarchical model.

A small average improvement alone is insufficient if it lies within measurement
noise or fails in an important subgroup. Report the distribution of improvements,
not just pooled correlation or R². Test M0→M1→M2 ablations and parameter recovery;
report whether a simpler model performs as well. Baseline parameters receive a
comparable tuning budget within training data. Prespecify handling of ties,
multiple secondary analyses and failed convergence.

Trend F1 is secondary and only meaningful with prespecified, independently justified
change thresholds. A threshold such as ±0.015 in a synthetic normalized target is
not automatically a meaningful human performance change.

## Second study: incremental concurrent-training information

Proceed only if the strength measurement system is stable. Collect sufficient
variation in strength/endurance dose, modality and spacing. Compare the frozen
strength-only model with a nested extension using endurance exposure. Distinguish:

- Acute prediction: does yesterday's cycling/running exposure improve prediction
  of today's standardized strength or power performance?
- Chronic adaptation: does concurrent programming alter long-term strength,
  hypertrophy, explosive power or endurance improvement?

Observational logs are vulnerable to self-selection: tired athletes change their
training, and scheduling covaries with work, sleep and baseline fitness. A fitted
coupling coefficient is therefore not automatically causal. A prospective randomized
crossover can investigate acute timing/modality where feasible; chronic adaptations
require a suitable longitudinal controlled design. Check carryover, period effects,
washout feasibility and distinct sample-size requirements. Power/CP/W′ predictions
need separate endurance targets and validations; strength velocity cannot validate
the endurance model.

If this is only an additional analysis of the same limited dataset, include it as
a secondary analysis in the first paper rather than creating a weak separate paper.

## Third stage: does model-guided coaching help?

A forecast can be accurate without producing better decisions. After prediction
validation, compare assisted model guidance with a simple RPE/velocity-based
standard under equivalent time and training opportunities. Prespecify strength and
endurance outcomes, adherence, burden, changes/overrides, missed sessions and adverse
training outcomes. Keep human override and record why recommendations were rejected.
A randomized longitudinal study is needed before claiming superior progression,
recovery, injury prevention or optimal training.

## Manuscript material that can be prepared now

- Introduction: limitations of sparse testing, baseline models and measurement error;
  exact, falsifiable contribution without claiming novelty already proven.
- Methods: equations, event schema, model versions, prespecified inputs, validation
  splits, comparators, uncertainty and reproducibility.
- Software availability: versioned private code during development; choose licensing
  and an archival release if publication requires it. No public release has occurred.
- Results shells: recruitment/coverage table, paired error table, calibration plot,
  individual error distributions, ablations and failure analysis, all left unfilled
  until real observations and analyses exist.
- Discussion: utility conditional on real results, identifiability and causal limits,
  protocol/device dependence, and distinction between forecasts and coaching efficacy.

No abstract claiming superiority, participant count, effect size, p-value, confidence
interval or ethics approval should be generated before it exists. Register the final
protocol and obtain the appropriate approvals/consent before collecting research data.

## Go / no-go criteria

| Decision | Minimum evidence |
|---|---|
| Advance from debugging to pilot | Reproducible logging, nulls/units/time correct, migration and privacy/ownership tests pass |
| Advance to confirmatory forecasting study | Repeatable outcome, usable coverage, stable calibration, identifiable enough model, competitive pilot baselines |
| Claim predictive advantage | Prespecified held-out improvement with uncertainty, robust coverage and external athlete validation |
| Write separate concurrent paper | Distinct question, adequate exposure variation/data, incremental value or informative negative result |
| Claim better training outcomes | Prospectively compared decisions and outcomes under a suitable controlled design |

Failure to beat simple baselines is a valid result. A useful app can still be built
with established programming principles and good data collection; a novel model is
not a prerequisite for a practical product.
