> Historical specification. The September 2026 [audit](audit_2026_09.md) and [model reference](model_reference.md) supersede conflicting scientific/validation claims. `run_validation.py` is retrospective diagnostics, not leakage-free scientific validation. Older thresholds and calibration artifacts are unvalidated.

# Concurrent-Training Model Specification

**Version**: Sprint H1 (Hardened)  
**Date**: 2026-05-16  
**Status**: Production  
**Official path**: `rep_engine` → `day_engine` → `performance_engine` (via `EngineOrchestrator`)

---

## 1. Architecture Overview

The model is a hierarchical state-space system with three time resolutions:

| Layer | Time Scale | Module | Key Outputs |
|-------|-----------|--------|-------------|
| Rep | seconds | `rep_engine` | `v_pred`, `A_l`, `A_sys`, `A_M`, limiting factor |
| Day | days | `day_engine` | `D_l`, `F_l`, `C_l`, `D_sys`, `R_mito`, `E_fat`, `T_legs` |
| Trend | weeks | `performance_engine` | Trend direction, EWMA, e1RM estimate |

The deprecated `ConcurrentTrainingModel` (`app/domain/legacy_model.py`) is retained **only** for backward-comparison; production ingestion must use `EngineOrchestrator`.

---

## 2. Variables

### 2.1 Observed (inputs)

| Symbol | Description | Unit |
|--------|-------------|------|
| `v_obs` | Observed bar velocity | m/s |
| `load_kg` | External load | kg |
| `rest_sec` | Rest before set/rep | s |
| `duration_min` | Endurance session duration | min |
| `intensity_type` | Endurance intensity label | {z2, hiit, mixed} |
| `set_end_rpe` | Optional RPE at set end | 1–10 |

### 2.2 Latent (state)

#### Rep-level (`rep_engine`)

| Symbol | Definition | Domain |
|--------|-----------|--------|
| `x_l` | `ln(A_l)` — local log-availability | `(−∞, 0]` |
| `x_sys` | `ln(A_sys)` — system log-availability | `(−∞, 0]` |
| `x_M` | `ln(A_M)` — metabolic log-availability | `(−∞, 0]` |

Availability is recovered by exponentiation:
```
A_l = exp(x_l),   A_sys = exp(x_sys),   A_M = exp(x_M)
```

#### Day-level (`day_engine`)

| Symbol | Definition | Domain |
|--------|-----------|--------|
| `D_l` | Per-lift fatigue | `[0, ∞)` |
| `F_l` | Per-lift fitness/adaptation | `[0, ∞)` |
| `C_l` | Capacity (e1RM-like) | `[C_min, C_max]` |
| `D_sys` | System fatigue | `[0, ∞)` |
| `R_mito` | Recovery capacity | `[0, 1]` |
| `E_fat` | Endurance fatigue | `[0, ∞)` |
| `T_legs` | Structural/connective-tissue fatigue | `[0, 1]` |

---

## 3. Equations by Layer

### 3.1 Rep Engine

**Velocity prediction**
```
v_pred = v_ref(load) * exp(x_l + x_sys + x_M)
```
where `v_ref(load) = a − b*load` (clamped to `[v_min, v_max]`).

**Fatigue driver**
```
y       = v_ref / v_obs          # freshness signal (>1 = faster than ref)
y_phi   = min(y, 1.0)            # clamped driver (prevents anti-fatigue)
I       = load / e1rm            # intensity (1.0 if e1rm unknown)
phi_base = I^alpha * (1/y_phi)^delta
```

**Catastrophe nonlinearity** (high-velocity-loss region)
```
if VL > VL_threshold:
    excess = (VL − VL_threshold) / (1 − VL_threshold)
    catastrophe_mult = 1 + excess^catastrophe_exponent
else:
    catastrophe_mult = 1
```

**Central density factor**
```
density_factor = sqrt( (reps_in_set / (rest_min + 0.5)) / 5 )
```
clamped to `[0.5, 2.0]`.

**Per-rep updates**
```
phi_local   = phi_base * catastrophe_mult
phi_central = phi_base * catastrophe_mult * density_factor^density_alpha

# Optional RPE split
if set_end_rpe > 7:
    rpe_factor = (set_end_rpe − 7) / 3
    phi_local   *= (1 − 0.3*rpe_factor)
    phi_central *= (1 + 0.3*rpe_factor)

# State decrements
Delta_x_l   = −a_local   * phi_local   * (1 + eta_M * (1 − A_M))
Delta_x_sys = −a_sys     * phi_central
Delta_x_M   = −a_M * chi(rep_index)   # chi = 1 + 0.05*rep_index
```

**Recovery during rest** (`delta_t` seconds)
```
R = clamp(R_mito, 0, 1)
boost = 1 + beta_rest * R

recovery_l = r_local * (1 − exp(−delta_t / tau_rest_local)) * boost
recovery_sys = r_sys * (1 − exp(−delta_t / tau_rest_sys)) * boost

x_l   ← min(0, x_l   + recovery_l   − eta_Mrest * (1 − A_M))
x_sys ← min(0, x_sys + recovery_sys − eta_Mrest * (1 − A_M))

# Metabolic clearance
tau_M_eff = tau_M / (1 + beta_M * R)
x_M ← x_M * exp(−delta_t / tau_M_eff)   # A_M recovers toward 1
```

### 3.2 Day Engine

**Impulses** (computed from `rep_engine` output and set metadata)
```
tonnage      = load_kg * reps
intensity    = clamp(load_kg / C_l, 0.20, 1.20)
velocity_term = mean(v_ref / v_obs)
vl_term      = 1 + p_VL * VL
set_impulse  = tonnage * intensity^alpha_I * velocity_term * vl_term
```

**R_mito update** (bounded)
```
R_new = R * exp(−k_mito_decay)
      + k_mito_z2 * u_E_Z2
      + k_mito_hiit * u_E_HIIT
      − k_mito_overload * overload_indicator
R_new = clamp(R_new, 0, 1)
```

**Capacity update** (with saturation)
```
saturation = (1 − C / C_max)^alpha
dC = g_l * F_l * saturation − h_l * D_l − lambda_l
C_new = clamp(C + dC, C_min, C_max)
```

**T_legs update**
```
T_new = T * exp(−1 / tau_T_legs)
      + k_T_legs * u_legs
      + k_T_high_intensity * u_legs_high_intensity
T_new = clamp(T_new, 0, 1)
```

**Per-lift fatigue**
```
tau_eff = tau_Dl[lift] / (1 + beta_l[lift] * R)
D_new = D_l * exp(−1 / tau_eff)
      + k_Dl * u_l
      + interf_per_lift[lift]
```

**System fatigue**
```
tau_sys_eff = tau_sys / (1 + beta_sys * R)
D_sys_new = D_sys * exp(−1 / tau_sys_eff)
          + k_sys * u_sys
          + interf_sys
```

**Endurance fatigue**
```
E_fat_new = E_fat * exp(−1 / tau_Efat)
          + k_EHIIT * u_E_HIIT
          + k_SE * u_legs
```

**Interference** (all explicit — no placeholder coefficients)
```
if u_E_HIIT == 0:
    interf = 0
else:
    base = u_E_HIIT * mode_factor(mode) * timing_factor
    interf_per_lift[lift] = k_ES[lift] * base
    interf_sys = k_ES_sys * base
```

---

## 4. Fixed Parameters vs Fit Candidates

### 4.1 Fixed (physically anchored, do not fit)

| Parameter | Rationale |
|-----------|-----------|
| `C_min = 20` | Biological floor (empty bar ~20 kg for most adults) |
| `C_max = 200` | Practical squat/bench ceiling for non-elite populations |
| `R_mito_max = 1` | Bounded recovery capacity |
| `v_min = 0.05` | Bar cannot move slower than ~5 cm/s and still complete a rep |
| `y_phi = min(y, 1.0)` | Anti-fatigue clamp is a structural invariant |

### 4.2 Fit candidates (population or individual)

| Parameter | Typical range | Notes |
|-----------|---------------|-------|
| `a_local`, `a_sys` | 0.01–0.03 | Fatigue susceptibility per lift |
| `tau_Dl[lift]` | 2–5 days | Fatigue decay time constant |
| `tau_T_legs` | 14–28 days | Connective-tissue recovery |
| `g_l` | 0.01–0.02 | Fitness-to-capacity gain |
| `h_l` | 0.005–0.015 | Fatigue-to-capacity loss |
| `k_mito_z2` | 0.0008–0.0012 | Z2 → recovery buildup |
| `alpha_I` | 1.0–1.5 | Intensity exponent in impulse |

### 4.3 Individual calibration target

Primary calibration targets per athlete:
1. **Load-velocity profile** `(a, b)` per lift — from submaximal warm-up sets.
2. **Capacity `C_l`** — from heaviest quality set or confirmed breakthrough protocol.
3. **Fatigue decay `tau_Dl`** — from repeated same-lift sessions with varying rest days.

---

## 5. Known Limitations

1. **No formal identifiability proof** for `x_sys` vs `x_M` separation on sparse data.
2. **Catastrophe threshold** (`VL = 0.40`) is heuristic; may need sport-specific tuning.
3. **Endurance power model** is duration-based; no formal W′/CP or MAP integration yet.
4. **T_legs** is unobserved; validation relies on predictive improvement when included.
5. **Female/masters/adolescent** parameter ranges are extrapolated from general adult male literature.

---

## 6. Falsification / Validation Plan

### 6.1 Required claims to test

| Claim | Falsification criterion |
|-------|------------------------|
| Log-space `x_M` improves numeric stability over `M` | `x_M` engine converges on datasets where `M` engine diverges |
| `y_phi = min(y, 1.0)` improves predictions | RMSE lower with clamp than without on held-out reps |
| Catastrophe term matters | Significant reduction in high-VL rep prediction error |
| `T_legs` improves next-day leg-lift readiness | Lower next-day first-rep error when `T_legs` is included |
| Explicit interference terms | All HIIT→strength coefficients are explicit functions (no placeholders) |

### 6.2 Baseline comparisons

The model must beat or match three baselines on all primary metrics:

**a) Simple VBT threshold**
- Predict next-rep velocity as `v_ref * 0.95` (naive freshness assumption).
- Stop when observed VL > 20 %.

**b) Simple Banister / FFM**
- Single fitness `F` and fatigue `D` per lift.
- `perf_y = F − D`.
- Updated with exponential decay after each session.

**c) Rolling e1RM / readiness heuristic**
- `readiness = last_e1RM / best_e1RM_last_30d`.
- `predicted_velocity = readiness * v_ref`.

---

## 7. Minimum Reporting Table

When reporting validation results, include:

| Metric | Value | Baseline A | Baseline B | Baseline C |
|--------|-------|-----------|-----------|-----------|
| Rep-level RMSE (m/s) | | | | |
| Rep-level MAE (m/s) | | | | |
| Next-day first-rep RMSE | | | | |
| Next-day top-set error | | | | |
| Progress/stagnation F1 | | | | |
| Calibration N (athletes) | | — | — | — |
| Hold-out days | | — | — | — |
