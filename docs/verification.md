# Audit verification — 6 September 2026

This record distinguishes software checks from scientific validation. Passing tests
does not validate training effects, physiological compartment interpretations,
parameter values, injury prevention or Android usability.

## Checks performed

- The exact latest development snapshot, PR #2 at
  `71f6e2147687bd89d684400bb506c553a6af31a1`, was used as the audit base.
- The standard-library audit suite has 28 passing tests, covering rest partitioning,
  causal prefixes, missing measurements, endurance integration, day decay,
  priority constraints and independent reference-model evaluation.
- Python compilation succeeds for the application, research reference and legacy
  diagnostic entry point.
- The synthetic event fixture and manifest reproduce
  `artifacts/audit_2026_09/reference_demo.json`. Input hashes, per-target predictions,
  parameters and limitations are included. Sixty held-out observations are entirely
  synthetic. Last-observation MAE is 0.01579 m/s; M2 MAE is 0.01909 m/s.
- First full GitHub test run at audit commit
  `f764fbb6d1de7341b89fcf86a8cdb50db5553fad`: 762 passed, 7 failed, 8 skipped.
  The failures exposed old expectations for missing readiness, priority frequency,
  explanatory strings and one arithmetic-equality difference. They were reviewed
  and corrected; the successful final rerun is recorded below.
- PostgreSQL migration CI passed on that run, including upgrade and the
  revision 006 → 005 → 006 round trip. This is a schema-cycle check, not proof of
  safe downgrade for every existing production dataset.

## Final CI status

The complete application/test changes were verified at commit
[`0fe673d86fa1f994a8878d34d128c687d6cd0ba8`](https://github.com/robinvandenbroecke/concurrent-training/commit/0fe673d86fa1f994a8878d34d128c687d6cd0ba8).
Both jobs succeeded in [GitHub Actions run 34020247430](https://github.com/robinvandenbroecke/concurrent-training/actions/runs/34020247430):

| Check | Result |
|---|---|
| Python 3.11 full pytest suite | **776 passed, 8 skipped**, one dependency deprecation warning |
| Validation diagnostic smoke run | Passed; output explicitly reports `scientific_validation: false` and `no_lookahead: false` |
| PostgreSQL 16 migration job | Passed, all upgrades and revision 006 → 005 → 006 |
| Independent fixture reproduction | Exact report equality, including input hashes and all forecasts |
| New audit coverage | 28 numerical/research invariants plus 7 runtime/data-contract regression tests |

The eight skipped tests did not execute and are not counted as verified. The warning
concerns Starlette's deprecated AnyIO alias; no dependency upgrade is claimed.
Application code is unchanged since the cited validated commit. Follow-up changes
record verification and enforce LF line endings for research fixtures, with a CI
check that regenerates and compares the report including its input hashes. The
upload check caught and corrected a CSV CRLF/LF hash discrepancy; all predictions
and metrics were identical. The test and migration logs are available in the linked
workflow and its diagnostic artifacts.

## Remaining verification and release conditions

- No Android project, emulator/device test, installable APK or public deployment
  was delivered or tested.
- No penetration test, complete dependency vulnerability scan, account-isolation
  certification or external OAuth round-trip verification was performed.
- No human dataset, prospective experiment, complete parameter-identifiability
  study or scientific superiority/efficacy test was performed.
- No external manuscript or preregistration submission was made.
- Runtime recovery and load semantics changed. Existing fitted parameters and
  persisted day states are not automatically compatible. Before deploying this
  branch, retain a backup, version the configuration, decide on deterministic replay
  or an explicit state reset, and recalibrate with appropriately timed observations.
  A production state conversion is not implemented by this PR.
- API readiness and predicted velocity may now be null. Consumers must honor
  `assessment_status` and not substitute 100 or a fabricated measurement.
- The PR is stacked above open PR #2 (which is above #1). Review and integrate in
  dependency order; do not treat this branch as an independent patch against main.
