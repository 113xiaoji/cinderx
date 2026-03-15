# Task Plan: issue-35 round/int float intrinsics

## Goal
Lower `int(float)` and single-argument `round(float)` away from generic `VectorCall` and onto native ARM64-friendly conversion paths.

## Scope
- Builtin-call recognition for:
  - `int(x)` where `x` is float-like
  - `round(x)` single-argument form where `x` is float-like
- New HIR/LIR/codegen support for float-to-int conversion with overflow fallback
- Regression coverage and remote ARM verification

## Workflow
1. Brainstorming: inspect existing builtin-call and float fast-path infrastructure
2. Writing-Plans: record a phased design and implementation order
3. Test-Driven-Development: add lowering/behavior regressions first
4. Verification-Before-Completion: run remote build/tests and collect evidence

## Status
- [x] Brainstorming
- [x] Writing-Plans
- [x] Test-Driven-Development
- [x] Verification-Before-Completion

## Remote Test Entry
- `scripts/arm/remote_update_build_test.sh`

## Current Verification State
- Remote host `124.70.162.35` is reachable and usable for ARM validation.
- Remote host `124.70.162.32` timed out on port 22 from this environment.
- Remote validation is now closed on `124.70.162.35`.
- `int(float)` and single-arg `round(float)` both lower away from `VectorCall` and onto the new ARM path.
- Negative non-zero values now execute correctly after fixing the fallback frame state used by `DoubleToInt` / `DoubleRoundToInt`.
- Manual ARM checks also confirmed fallback behavior for `NaN`, `inf`, `-inf`, and large finite values.
