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

## Round 1 follow-up
- User-provided benchmark table for committed helper-backed commit `0421a5f7`
  showed consistent regressions:
  - `deepcopy`: about `1.02x` slower
  - `deepcopy_reduce`: about `1.03x` slower
  - `deepcopy_memo`: about `1.02x` slower
- First aggressive attempt:
  - compile-time no-hook decision plus pure HIR pointer path
  - runtime fallback helper when hooks already exist at compile time
- Review finding before the next remote round:
  - watcher-style invalidation alone is not enough for correctness
  - if a compiled function itself calls `sys.addaudithook()` and later reaches
    `id()` in the same frame, a pure watcher solution can still bypass the new
    audit hook
- Updated Round 1 shape:
  - if compile-time audit state is empty:
    - emit `CallStatic(canBypassBuiltinIdAudit)`
    - emit `Guard`
    - emit `LoadFieldAddress -> IntConvert(TCInt64) -> PrimitiveBox`
  - if compile-time audit state is not empty:
    - keep the helper-backed slow path
  - retain the patched `sys.addaudithook` invalidation so later calls
    recompile away from the guarded fast path once hooks exist
- New targeted regression added:
  - compile a function with no hooks
  - inside the compiled frame call `sys.addaudithook()`
  - verify the subsequent `id()` in the same frame still emits the
    `builtins.id` audit event

## Round 1 results
- The first guarded-aggressive implementation still failed to take the fast
  path in practice because `canBypassBuiltinIdAudit()` counted CinderX's own
  internal audit hooks as blockers.
- Round 1 fix:
  - add `registerBuiltinIdIgnorableAuditHook(...)`
  - mark the JIT audit hook and Static Python audit hook as ignorable for
    `builtins.id`
  - retain `sys.addaudithook` invalidation for later user-installed hooks
- Additional implementation gotchas that were fixed in this round:
  - stale `scratch/` objects on ARM could hide new audit-symbol changes, so a
    clean rebuild was needed at least once
  - the simplifier-inserted `Guard` needed a dominating `Snapshot`, otherwise
    `RefcountInsertion.bindGuards()` crashed during `force_compile()`
- Standard-entry targeted verification after the final Round 1 fixes:
  - `ArmRuntimeTests.test_builtin_id_eliminates_vectorcall`: `OK`
  - `ArmRuntimeTests.test_builtin_id_addaudithook_deopts_active_frame`: `OK`
  - `ArmRuntimeTests.test_deepcopy_keyerror_helpers_avoid_unhandledexception_deopts`: `OK`
- Final Round 1 HIR probe shape for `builtin_id`:
  - contains:
    - `CallStatic = 1`
    - `Guard = 1`
    - `LoadFieldAddress = 1`
    - `IntConvert = 1`
    - `PrimitiveBox = 1`
  - still no guarded builtin `VectorCall`
- Round 1 main benchmark vs base:
  - jitlist:
    - `deepcopy`: `-0.24%`
    - `deepcopy_reduce`: `-1.35%`
    - `deepcopy_memo`: `-9.17%`
  - autojit2:
    - `deepcopy`: `+0.60%`
    - `deepcopy_reduce`: `-0.86%`
    - `deepcopy_memo`: `-3.52%`
- Round 1 subset compare:
  - compare artifact:
    - `/root/work/arm-sync/issue62_regress_compare_round1.json`
  - only >5% comparable regression signal:
    - `coverage`: `+7.69%`
  - all other comparable leaves stayed within `5%`
- Focused follow-up note:
  - a standard-entry single-benchmark rerun for `coverage` wrote an empty
    summary JSON, so this residual signal is still open rather than resolved

## Coverage follow-up
- A focused 5-sample rerun with the same current harness still showed a
  repeatable `coverage` slowdown:
  - current run 1 median:
    - `0.12437327799852937 s`
  - current run 2 median:
    - `0.12515388199972222 s`
  - base median with the same current subset harness:
    - `0.11694090899982257 s`
  - delta:
    - about `+6.36%` to `+7.02%`
- `coroutines` in the same focused reruns stayed near parity, which suggests
  the `coverage` signal is not just a whole-host shift.
- Standard-entry `BENCH=coverage` main gates are much closer to parity:
  - current:
    - jitlist `0.011404810000385623 s`
    - autojit2 `0.011399618997529615 s`
  - base:
    - jitlist `0.011335966999467928 s`
    - autojit2 `0.011404590000893222 s`
- Interpretation:
  - the large residual signal appears specifically in the broader no-jitlist
    subset methodology rather than in the standard benchmark gate with the
    `__main__:*` autojit filter
- Additional diagnosis:
  - `benchmarks/bm_coverage/run_benchmark.py` only benchmarks:
    - `bench_coverage`
    - recursive `fibonacci`
  - HIR opcode counts for `bench_coverage` and `fibonacci` were identical on
    current and base
  - standard `coverage` autojit logs compiled the same four `__main__`
    functions on current and base with near-identical compile times and code
    sizes
  - the `coverage` package itself contains many `id()` call sites, especially
    in debug/tracer code, so the residual signal may be coming from broader
    autojit of coverage internals rather than the benchmark's two `__main__`
    functions
- No-jit follow-up:
  - the same `coverage` slowdown reproduces even with JIT fully disabled in the
    benchmark workers
  - medians with the same nojit helper:
    - current long-path workdir:
      - `0.12099459899764042 s`
    - base:
      - `0.1147898629969859 s`
      - delta about `+5.41%`
  - this points away from JIT-generated machine code as the root cause
- Path-length follow-up:
  - re-running the same current nojit measurement from a much shorter workdir:
    - current short-path:
      - `0.11752671499925782 s`
      - delta vs base about `+2.38%`
  - `coroutines` stayed near parity in all three runs
  - this strongly suggests the residual `coverage` signal is largely a path or
    environment artifact rather than an issue62 codegen/runtime regression
- Standard no-jitlist autojit follow-up:
  - current:
    - `coverage` autojit2 no-jitlist single sample:
      - `0.12347048399897176 s`
    - compile summary:
      - `main_compile_count = 0`
      - `total_compile_count = 0`
  - base:
    - `coverage` autojit2 no-jitlist single sample:
      - `0.11728518700329005 s`
    - compile summary:
      - `main_compile_count = 0`
      - `total_compile_count = 0`
  - implication:
    - the wider no-jitlist `coverage` slowdown happens even when the JIT never
      compiles anything during the run
    - that further points away from the issue62 `id()` fast path itself
