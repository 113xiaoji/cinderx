# Task Plan: deepcopy builtin id inline

## Goal
Fix issue `#62`: inline builtin `id()` in JIT-compiled `copy.deepcopy` hot paths
so they avoid the generic `VectorCall -> builtin_id -> PySys_Audit ->
PyLong_FromVoidPtr` chain when it is safe to do so.

Primary case:
- `deepcopy`

Required optimization order:
1. `HIR`
2. `LIR`
3. `codegen`

Required workflow:
1. brainstorming
2. writing-plans
3. test-driven-development
4. verification-before-completion

All remote tests and verification must use:
- `scripts/arm/remote_update_build_test.sh`

Remote hosts:
- ARM: `124.70.162.35`
- x86: `106.14.164.133`

## User constraints
- use `using-superpowers` and `planning-with-files`
- prefer the smallest safe fix
- keep commit message linked to:
  - `https://github.com/113xiaoji/cinderx/issues/62`
- write key results to `findings.md`
- regress the requested subset:
  - `generators`
  - `coroutines`
  - `comprehensions`
  - `richards`
  - `richards_super`
  - `float`
  - `go`
  - `deltablue`
  - `raytrace`
  - `nqueens`
  - `nbody`
  - `unpack_sequence`
  - `fannkuch`
  - `coverage`
  - `scimark`
  - `spectral_norm`
  - `chaos`
  - `logging`

## Brainstorming
- User-supplied hotspot:
  - `copy.deepcopy` calls `id()` on each object node
  - current JIT keeps the call on a guarded builtin `VectorCall` path
- Current likely control point:
  - builtin-call simplification after `GuardIs<builtin_id>`
- Smallest expected safe shape:
  - lower to a helper-backed integer fast path plus boxing
  - preserve audit semantics inside the helper
- Biggest risk:
  - silently dropping `PySys_Audit("builtins.id", ...)` in cases where audit
    hooks are live

## Round 0 checklist
- [x] Create case-local proposal / issue / notes / mistake ledger
- [x] Confirm current current-tip `id()` lowering on this branch
- [x] Find the narrowest HIR control point for builtin `id()`
- [x] Add a targeted regression test
- [x] Decide whether a pure-HIR fix is enough or whether backend support is needed
- [x] Validate remotely through the standard ARM entrypoint under scheduler lease

## Current phase
- [completed] Round 0 verification complete

## Round 0 findings
- likely control point:
  - `cinderx/Jit/hir/simplify.cpp:simplifyVectorCall(...)`
- likely first-round implementation:
  - runtime-helper-backed builtin `id()` simplification using:
    - `CallStatic(builtinIdAsInt64)`
    - `CheckNeg`
    - `PrimitiveBox(TCInt64)`
- likely test anchors:
  - generic builtin `id()` HIR regression
  - audit-hook semantic verification script
- active ARM lease:
  - benchmark: `36`
- active remote workspace:
  - `/root/work/cinderx-issue62-deepcopy-id-inline`

## Round 0 result
- Retained code changes:
  - `cinderx/Common/audit.h`
  - `cinderx/Common/audit.cpp`
  - `cinderx/Jit/hir/simplify.cpp`
  - `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Validation-only remote-entry support changes used in this round:
  - `scripts/arm/remote_update_build_test.sh`
  - `scripts/arm/run_pyperf_subset.sh`
- Scheduler closeout:
  - lease `36` released with reason:
    - `issue62 round complete`
- Targeted verification:
  - `ArmRuntimeTests.test_builtin_id_eliminates_vectorcall`: `OK`
  - `ArmRuntimeTests.test_deepcopy_keyerror_helpers_avoid_unhandledexception_deopts`: `OK`
  - direct audit output included:
    - `builtins.id (<__main__.Box object at ...>,)`
    - final truth line `True`
- Current branch `deepcopy`:
  - jitlist:
    - `deepcopy`: `0.0006456110131694004 s`
  - autojit2:
    - `deepcopy`: `0.0006735479910275899 s`
- Base branch `deepcopy`:
  - jitlist:
    - `deepcopy`: `0.0006558750101248734 s`
  - autojit2:
    - `deepcopy`: `0.0006610549971810542 s`
- Requested subset compare:
  - compare artifact:
    - `/root/work/arm-sync/issue62_regress_compare.json`
  - only >5% signal in the 2-sample pass:
    - `comprehensions`: `+8.70%`
- Current decision:
  - issue62 is functionally fixed for the main guarded builtin `id()` shape
  - primary `deepcopy` timing does not show a material regression vs base
  - one residual `comprehensions` signal and one `deepcopy_memo` sub-benchmark
    signal are recorded for follow-up
