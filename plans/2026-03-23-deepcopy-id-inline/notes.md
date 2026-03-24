# Notes: deepcopy builtin id inline

## Identity
- Issue: `#62`
- Primary benchmark case: `deepcopy`
- Current branch: `codex/issue62-deepcopy-id-inline`

## Problem statement
- Current JIT knows some `id()` call sites are calling the real builtin via
  `GuardIs`, but still leaves the call on a generic `VectorCall` path.
- In `copy.deepcopy`, `id()` is on a hot path for memo dictionary access and
  memo keep-alive management.

## Initial questions
- Where is builtin-call specialization for exact guarded builtins implemented?
- Is there already an HIR instruction for object-pointer-to-integer conversion?
- Does deopt / frame-state support already know how to re-box such a primitive?
- What is the narrowest safe audit-hook policy for builtin `id()`?

## Current code-read findings
- `cinderx/Jit/hir/simplify.cpp`
  - builtin guarded `VectorCall` simplifications already exist for:
    - `abs`
    - `min`
    - `max`
  - the natural insertion point for `id()` is therefore `simplifyVectorCall(...)`
- Existing HIR pieces needed for a pure-HIR fast path already exist:
  - `LoadFieldAddress(object, offset)` yields `TCPtr`
  - `IntConvert(TCPtr -> TCInt64)` is already lowered in LIR
  - `PrimitiveBox(TCInt64)` already boxes back to `LongExact`
- Important type constraint:
  - `TCPtr` does not have a direct boxed equivalent
  - so the fast path must go through:
    - `LoadFieldAddress`
    - `IntConvert(..., TCInt64)`
    - `PrimitiveBox(TCInt64)`
- Audit semantics:
  - `cinderx/Common/audit.cpp` already inspects `_PyRuntime.audit_hooks`
  - the smallest safe first round is a runtime guard helper rather than a new
    watcher scheme
- Current test strategy:
  - keep one stable committed unittest for the `VectorCall -> fast path` HIR
    change
  - verify audit-hook semantics through a direct remote script under the
    standard entrypoint, because the first unittest wrapper interacted badly
    with the remote unittest driver process

## Remote policy
- All remote validation uses:
  - `scripts/arm/remote_update_build_test.sh`
- Shared scheduler DB:
  - `C:/work/code/coroutines/cinderx/plans/remote-scheduler.sqlite3`
- Current ARM lease:
  - benchmark: `36`
- Current remote workspace:
  - `/root/work/cinderx-issue62-deepcopy-id-inline`
- Lease closeout:
  - lease `36` released after the round

## Round 0 ARM results
- Targeted checks through the standard remote entrypoint:
  - `ArmRuntimeTests.test_builtin_id_eliminates_vectorcall`
    - `OK`
  - `ArmRuntimeTests.test_deepcopy_keyerror_helpers_avoid_unhandledexception_deopts`
    - `OK`
- Direct audit verification through the same entrypoint:
  - observed output:
    - `builtins.id (<__main__.Box object at ...>,)`
    - final line:
      - `True`
- Current branch `deepcopy` artifacts:
  - `/root/work/arm-sync/deepcopy_jitlist_20260324_015651.json`
  - `/root/work/arm-sync/deepcopy_autojit2_20260324_015651.json`
  - `/root/work/arm-sync/deepcopy_autojit2_20260324_015651_compile_summary.json`
- Base branch `deepcopy` artifacts:
  - `/root/work/arm-sync/deepcopy_jitlist_20260324_020918.json`
  - `/root/work/arm-sync/deepcopy_autojit2_20260324_020918.json`
  - `/root/work/arm-sync/deepcopy_autojit2_20260324_020918_compile_summary.json`
- Current branch main timings:
  - jitlist:
    - `deepcopy`: `0.0006456110131694004 s`
    - `deepcopy_reduce`: `0.0010173909977311268 s`
    - `deepcopy_memo`: `0.00010101800580741838 s`
  - autojit2:
    - `deepcopy`: `0.0006735479910275899 s`
    - `deepcopy_reduce`: `0.0010271520004607737 s`
    - `deepcopy_memo`: `8.409600559389219e-05 s`
- Base branch main timings:
  - jitlist:
    - `deepcopy`: `0.0006558750101248734 s`
    - `deepcopy_reduce`: `0.0010282009970978834 s`
    - `deepcopy_memo`: `8.90259980224073e-05 s`
  - autojit2:
    - `deepcopy`: `0.0006610549971810542 s`
    - `deepcopy_reduce`: `0.0010072500008391216 s`
    - `deepcopy_memo`: `8.31259967526421e-05 s`
- Requested subset artifacts:
  - current:
    - `/root/work/arm-sync/issue62_regress_subset.json`
  - base:
    - `/root/work/arm-sync/issue62_regress_subset_base.json`
  - compare:
    - `/root/work/arm-sync/issue62_regress_compare.json`
- Requested-name mismatch in pyperformance 1.14:
  - no leaf benchmark named:
    - `scimark_fft`
    - `scimark_lu`
    - `scimark_monte_carlo`
    - `scimark_sor`
    - `scimark_sparse_mat_mult`
    - `logging_format`
    - `logging_silent`
    - `logging_simple`
- Compare summary:
  - only >5% signal:
    - `comprehensions`: `+8.70%`
  - all other collected leaf benchmarks stayed within `5%`
