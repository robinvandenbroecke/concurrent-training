# Mathematical reference and model boundaries

Status: proposed research reference, implemented in `research/reference_model.py`.
This is not the full application model and not a validated physiology model.
Version: `research-reference-v1`, 6 September 2026.

## Observation and estimand

Primary observation: first concentric mean velocity (m/s) at a prespecified load,
with the same lift, range of motion, device, velocity definition, warm-up and
maximal intended concentric effort. Peak velocity, mean propulsive velocity and
mean concentric velocity must not be pooled as interchangeable measurements.

A frozen, previously measured load–velocity calibration defines

\[
v_{ref,i\ell}(w)=a_{i\ell}-b_{i\ell}w,\quad b_{i\ell}>0.
\]

`a` has units m/s, `b` has units (m/s)/kg. Predictions outside the calibrated
load range or with nonpositive reference velocity are rejected. This deliberately
avoids interpreting the positive floor in the legacy model as real performance.
A current capacity estimate must not redefine the historical test target.

Normalized log-performance is

\[
z_t=\log(v_t/v_{ref}(w_t))=c_t-d^S_t-d^E_t+\epsilon_t.
\]

`c` is a slowly updated **performance offset**, not muscle mass, fitness in
physical units, or 1RM in kg. `dS` and `dE` are phenomenological load-response
terms, not measured local or central fatigue. The velocity prediction is
`v_ref * exp(c − dS − dE)`.

## Nested models

| Model | State/term | Question |
|---|---|---|
| Fixed profile | `c=dS=dE=0` | Is recent history useful at all? |
| Last observation | Previous measured `v/v_ref` | Does a dynamic model beat persistence? |
| M0 | Adaptive `c`; `dS=dE=0` | Does smoothing beat persistence? |
| M1 | `c` and strength response `dS` | Does logged strength exposure add information? |
| M2 | M1 plus endurance response `dE` | Does endurance exposure add incremental predictive value? |

The exact M2→M1 nesting condition is `kE=0`, with the same initial conditions,
observation update and other parameters. M1→M0 uses `kS=0`. These reductions are
covered by an invariant test. Positive `kE` represents an acute decrement; this
reference cannot estimate beneficial coupling or chronic adaptation interference.
A separate signed or adaptation-interaction extension must be prespecified to
study those questions. Do not interpret a fitted acute term as proof of chronic
concurrent-training interference.

## Event timing

Every observation and dose has a UTC-offset-aware timestamp and unique event ID.
For elapsed time `Δt` in days:

\[
d^S_{t^-}=d^S_{prev}\exp(-\Delta t/\tau_S),\qquad
 d^E_{t^-}=d^E_{prev}\exp(-\Delta t/\tau_E).
\]

At a strength exposure: `dS += kS * uS`. At an endurance exposure:
`dE += kE * uE`. A dose is applied when performed, not before its preceding
observation. A dose event without an associated velocity observation is still
included. Endurance exposure is propagated to every tracked lift in the same
athlete; lift-specific coupling is future work.

After a measured observation, and only after saving the forecast:

\[
e_t=\log(v_t/v_{ref}(w_t))-(c_{t^-}-d^S_{t^-}-d^E_{t^-}),\qquad
c_t=c_{t^-}+\alpha e_t.
\]

This is a fixed-gain observer. It is **not** a Bayesian/Kalman model and does not
supply calibrated uncertainty. A fixed alpha also makes the smoothing depend on
measurement frequency; standardized probe frequency is required for the first
experiment. Alternatives with time-aware process noise belong in a prespecified
comparison, not post-hoc changes after seeing the test set.

## Doses and parameter units

For an empirical study, freeze the strength dose definition, for example
`sum(performed reps × (load / fixed calibration capacity)^2)`. The reference CSV
contains already computed doses; the evaluator does not infer their correctness.
Record and independently verify the underlying sets, calibration and dose code.
The reference capacity is fixed during an evaluation fold; recalculating all past
doses with today's capacity would create a moving target.

The endurance dose used in the corrected application is

\[
u_E=\sum_j(P_j/P_{threshold})^2\Delta t_j/60
\]

with `Δt` in seconds. This is an external load proxy with units of equivalent
minutes. It is not TSS and does not use CP/W′. `kS` has units inverse strength-dose,
`kE` inverse endurance-dose; `tauS`, `tauE` are days; `alpha`, `c`, `dS`, `dE` are
dimensionless. Different dose scaling changes coefficient values; comparing
coefficients across studies requires the same units.

The fixed reference settings (`alpha=.1`, `tauS=3 d`, `tauE=2 d`, `kS=.005`,
`kE=.001`) are candidates for software demonstration. They are not fitted,
physiologically established, optimal, or recommended training thresholds.

## Corrected application equations

These corrections apply to the existing application, independently of the new
reference. Prior numerical results must be recalculated.

1. Rep rest: `x_l(t+Δ)=x_l(t) exp(−Δ(1+beta_rest R)/tau_l)`; analogous system and
   metabolic terms. Each rep output reports all compartments after the rep.
2. Day rest: `R(t)=R0 exp(−k_decay t)`. Local fatigue decays with exponent
   `−[Δ + beta_l ∫R(t)dt]/tau_l`, where
   `∫R=R0*(1−exp(−k_decay Δ))/k_decay`, with the continuous zero-rate limit.
3. Same-day new endurance cannot accelerate prior decay retroactively. Endurance
   fatigue receives total external dose, including easy work.
4. No-input days preserve capacity unless an explicitly nonzero `lambda_l` is
   configured. New training can still affect legacy `F_l/C_l`; their empirical
   interpretation remains unresolved.
5. A missing velocity is an unobserved rep. A neutral nominal driver is used for
   load accounting, with `observation_available=False`; no VBT measurement is
   fabricated. Partial arrays preserve positions.
6. Final set RPE and eventual rep count are excluded from forecasts for earlier
   reps. RPE remains available as retrospective training information.

Recovery-rate modulation by `R` remains a legacy hypothesis. Exact integration
makes the numerical calculation coherent, not the hypothesis scientifically true.

## What is still required mathematically

- Compare against a conventionally fitted Banister/Busso model, persistence,
  rolling means, fixed load–velocity profile, and simple effort-based approaches
  under identical information, calibration budgets and prediction horizons.
- Establish structural observability for a precisely specified model with fixed
  known inputs; then assess practical identifiability with profile likelihoods,
  simulation recovery, sensitivity/conditioning and uncertainty.
- Do not fit all time constants, gains, profile parameters and capacities freely
  to sparse personal data. Start with shared/regularized parameters and estimate
  individual deviations only when informative data support them.
- Add measurement error, device effects, fatigue effects of the probe, missingness
  and relevant context. Test innovations, interval coverage, calibration drift
  and within-athlete correlation.
- Evaluate sensitivity to load scale, temporal binning, excluded observations,
  changing exercise technique, exercise order and return from detraining.
- Publish negative ablations and parameter instability. More latent states must
  earn their place through out-of-sample information, not attractive labels.
