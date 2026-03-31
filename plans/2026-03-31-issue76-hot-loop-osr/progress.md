# Progress Log: Issue 76 Hot-Loop OSR

## 2026-03-31

- Resumed Phase 0 debugging from the existing prototype branch.
- Re-read `task_plan.md` and `findings.md`; confirmed `progress.md` was missing and created it.
- Reproduced the current state on ARM from `HEAD` (`ed5f8d17`) using the standard remote helper inputs.
- Confirmed the core synthetic-state OSR path is not helper-only fragile:
  - direct `issue76_phase0_probe.py` can return `16`
  - repeated direct runs also show intermittent aborts / segfaults
- Collected a 15-run sample and observed a strong correlation:
  - `local 0 -> X19`, `local 1 -> X21` failed repeatedly
  - other mappings often succeeded
- Formed the current root-cause hypothesis:
  - the Phase 0 stub is still using an approximation of loop-header live-in locations
  - jumping directly to the loop header likely bypasses predecessor/phi materialization
- Added `scripts/arm/issue76_phase0_stability_probe.py` as a repeat-run regression probe so the instability has a concrete RED gate before the next implementation change.
