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
- [in_progress] Round 1 guarded-aggressive follow-up

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

## Round 1 hypothesis
- User-provided external numbers show the helper-backed round is still slower:
  - `deepcopy`: about `1.02x` slower
  - `deepcopy_reduce`: about `1.03x` slower
  - `deepcopy_memo`: about `1.02x` slower
- New target shape:
  - keep the pure HIR object-pointer path when the compile-time audit state is
    empty
  - add a tiny runtime `Guard(canBypassBuiltinIdAudit())` ahead of the HIR path
    so active compiled frames deopt correctly if `sys.addaudithook()` appears
  - keep `sys.addaudithook` invalidation so future calls recompile to the slow
    path instead of repeatedly deopting

## Round 1 checklist
- [x] Re-read the aggressive diff and self-review the audit correctness story
- [x] Identify the active-frame correctness hole in watcher-only invalidation
- [x] Convert the pure HIR path to a guarded fast path
- [x] Add a same-frame `sys.addaudithook()` regression test
- [x] Re-run targeted ARM validation through the standard remote entrypoint
- [x] Re-run `deepcopy` current-vs-base through the standard remote entrypoint
- [x] Update `findings.md` with the Round 1 evidence and decision
- [x] Resolve the residual `coverage` regression signal with a cleaner focused compare if needed
- [x] Decide whether to accept the remaining no-jitlist `coverage` slowdown as out-of-scope for issue62 or continue debugging broader autojit coverage internals

## Round 1 closure note
- The remaining `coverage` signal reproduces in nojit mode and shrinks
  substantially when the current workdir path is shortened on ARM.
- Current judgement:
  - this is more likely an environment or path-length effect in the
    `coverage` benchmark than an issue62 regression in the JIT fast path
- Follow-up status:
  - the remaining `coverage` work is now better treated as a separate
    environment/benchmark-investigation thread rather than a blocker on issue62
