# Task Plan: Issue 31 Raytrace Regression Fix

## Goal
Keep the issue31 instance-attr specialization gains while removing the severe raytrace regression introduced by commit `4c14dd10`.

## Current Phase
Closeout complete: revalidated on ARM staging and ready for review.

## Phases

### Phase 1: Reproduction and root cause
- [x] Reproduce the regression on the provided raytrace script on remote ARM
- [x] Confirm whether the regression is caused by exact `other` arg guards, downstream float specialization, or both
- [x] Capture current HIR/deopt evidence for the hottest failing methods
- Status: completed

### Phase 2: Minimal safe fix
- [x] Narrow or remove the unsafe exact-arg inference that causes the regression
- [x] Preserve the stable issue31 gains on the safe Point.dist / linear_combination-style shape
- [x] Add a regression test for the raytrace shape
- Status: completed

### Phase 3: Verification
- [x] Remote rebuild on ARM staging
- [x] Verify the new raytrace regression test
- [x] Re-run the issue31 targeted test to ensure no regression on the intended optimization
- [x] Check raytrace deopt counts and timing after the fix
- Status: completed

### Phase 4: Evidence
- [x] Append the root cause and fix results to findings.md
- [x] Update task status for review/commit readiness
- Status: completed

## Issue 31 Closeout Summary
- Closeout revalidation used ARM staging workdir `/root/work/frame-issue31-closeout-20260315`.
- Import path for staging verification:
  - `PYTHONPATH=scratch/lib.linux-aarch64-cpython-314:cinderx/PythonLib`
- Retained strategy:
  - exact `other` arg inference only on plain attr-read methods
  - specialized float-op guards disabled on helper-heavy no-backedge methods
- Verified balance:
  - issue31 plain attr gains still remain (`PointOther.dist` and the mixed probe both remain faster with `other` than with `rhs`)
  - raytrace's worst deopt offenders (`Vector.dot`, `Point.__sub__`, `Sphere.intersectionTime`) are no longer present in runtime deopt stats for the provided repro
- Deliberately out of scope for this closeout:
  - smaller residual deopts in `Vector.scale` and `addColours`
- Status:
  - issue31 is ready for review / merge as a closed fix

## Session: 2026-04-05 performance-go JIT analysis

### Goal
- Explain why CinderX JIT underperforms on pyperformance `go`.
- Converge on the safest repair direction before making code changes.
- Keep all verification aligned with the unified remote entrypoint when connectivity allows.

### Current Phase
- Phase 4 completed with fresh remote evidence.
- Root-cause analysis, design review, and future TDD shape are complete.

### Phases

#### Phase 1: Context recovery
- [x] Read repo guidance and prior issue60 artifacts.
- [x] Read the current builder/inliner/test code paths.
- [x] Confirm the unified remote validation path.
- Status: completed

#### Phase 2: Brainstorming
- [x] Compare static-heuristic, hybrid, and profile-driven repair directions.
- [x] Decide which direction is technically safe enough to recommend.
- Status: completed

#### Phase 3: TDD and planning
- [x] Identify the existing regression tests that define the safe envelope.
- [x] Identify the next regression shapes needed before any broader change.
- [x] Write design and implementation-plan docs under `docs/plans/`.
- Status: completed

#### Phase 4: Fresh remote verification
- [x] Re-run the current branch through the unified remote entrypoint for `go`.
- [x] Capture fresh `go` benchmark numbers and targeted method-load regression results.
- Status: completed

### Key Current Conclusion
- The historical issue60 evidence still points to the same core bottleneck:
  attr-derived but runtime-monomorphic receivers in `go` lose the
  `LOAD_ATTR_METHOD_WITH_VALUES -> VectorCall -> inline` chain when the JIT
  only trusts exact HIR receiver types.
- The safest proven repair direction is the profile-driven call-site split
  already captured in the issue60 artifacts, not another broader static
  heuristic.
- The most plausible residual gap is that the current implementation only
  recovers the outer attr-derived recursive call and intentionally leaves the
  nested inlined recursive call on the generic `CallMethod` path for safety.
- Fresh ARM reruns now show:
  - the unified `go` benchmark gate completes with JIT enabled and
    `main_compile_count = 34`
  - a focused `attr_derived_polymorphic` issue60 regression still segfaults
    after the test body reports `ok`, with the native stack pointing into
    `outputTypeWithRecursiveCoroHint -> reflowTypes -> SSAify::Run`
- Additional narrowing:
  - the crash is reproducible via direct
    `force_compile(_colorize.can_colorize.__annotate__)`
  - `PYTHONJITAUTO=1000000` avoids the outer unittest crash, which shows the
    harness is auto-jitting unrelated code paths
  - the most likely immediate bug is in `pass.cpp`, where a shared opcode case
    block treats non-`Send` instructions as `Send`
- That means the next change round should first lock down compiler stability on
  the issue60 safety path, then revisit any deeper nested-call recovery.
- Current local fix set:
  - `cinderx/Jit/hir/pass.cpp`
  - `cinderx/Jit/hir/annotation_index.cpp`
  - `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Fresh targeted remote results after the fix set:
  - `test_attr_derived_polymorphic_method_load_avoids_method_with_values_deopts`
    passes
  - `test_specialized_opcodes_do_not_eagerly_execute_annotation_thunks`
    passes
- Fresh benchmark remote result after the harness fix:
  - `go_jitlist_20260405_181404.json`: `0.5156086859933566 s`
  - `go_autojit50_20260405_181404.json`: `0.5089590209972812 s`
  - compile summary:
    - `main_compile_count = 34`
- Same-host A/B follow-up completed:
  - baseline `HEAD`:
    - jitlist: `0.24918644900026266 s`
    - autojit50: `0.4742307880005683 s`
  - fixed working tree:
    - jitlist: `0.25993193100293865 s`
    - autojit50: `0.25297167700045975 s`
- Same-host direct issue-specific follow-up completed:
  - baseline `bm_go.versus_cpu()` median:
    - `0.5150911270000051 s`
  - fixed `bm_go.versus_cpu()` median:
    - `0.17598324100003992 s`
  - delta:
    - about `-65.83%`
- Remaining work:
  - if we want a commit-ready performance claim, capture a multi-sample rerun
    under tighter host-load control
  - otherwise, the remaining `go` work is no longer “find the crash”, but
    “decide whether the residual perf signal justifies deeper optimization”
  - if ARM connectivity returns, add a direct `bm_go.versus_cpu()`-style probe
    for a cleaner issue-specific measurement
- Requested broad regression sweep status:
  - baseline vs fixed subset run completed for:
    - `generators,coroutines,comprehensions,richards,richards_super,float,go,deltablue,raytrace,nqueens,nbody,unpack_sequence,fannkuch,coverage,scimark,spectral_norm,chaos,logging`
  - only initial candidate above `5%` was `fannkuch`
  - focused `fannkuch` rerun cleared that signal
  - current conclusion:
    - no confirmed large regression remains in the requested set

### Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `ssh root@124.70.162.35` timed out on port 22 during fresh remote verification | 1 | Retried later after connectivity returned |
| PowerShell quoting broke the first manual remote-entry invocation | 1 | Re-ran with format-string based shell command construction |
| Focused remote `attr_derived_polymorphic` regression exits with `SIGSEGV` after reporting `ok` | 1 | Captured a `PYTHONFAULTHANDLER=1` stack trace showing `outputTypeWithRecursiveCoroHint -> reflowTypes -> SSAify::Run` and treated it as the current blocker |
| Direct `force_compile(_colorize.can_colorize.__annotate__)` also exits with `SIGSEGV` | 1 | Used it to prove the crash is broader than the issue60 benchmark shape and likely rooted in `pass.cpp` send-case handling |
| Combined multi-test remote suites showed outer-harness contamination after the first test | 1 | Switched authoritative verification to one-targeted-test-per-run through the same unified remote entrypoint |

## Raytrace Follow-up: polymorphic method loads

### Goal
- Reduce the remaining raytrace deopts caused by over-eager `LOAD_ATTR_METHOD_WITH_VALUES` lowering on polymorphic method call sites after issue31 was closed.

### Result
- Current retained policy in `builder.cpp`:
  - keep the `LOAD_ATTR_METHOD_WITH_VALUES` fast path for:
    - receivers already known to have a stable exact type
    - true `self` receivers whose descriptor owner type has no subclasses
  - fall back to normal `LoadMethod` lowering for polymorphic unpacked locals such as raytrace's `o.intersectionTime(...)` and `s.colourAt(...)`
- New regression coverage:
  - `test_polymorphic_method_load_avoids_method_with_values_deopts`
- Remote ARM staging validation:
  - targeted tests:
    - `test_polymorphic_method_load_avoids_method_with_values_deopts`
    - `test_specialized_numeric_leaf_mixed_types_avoid_deopts`
    - `test_plain_instance_other_arg_guard_eliminates_cached_attr_loads`
    - `test_other_arg_inference_skips_helper_method_shapes`
  - result: `OK`
- Raytrace `compile_strategy=all` update:
  - previous median: `0.5452457539504394s`
  - current median: `0.5257585040526465s`
  - improvement: about `3.6%`
  - previous total deopts: `257510`
  - current total deopts: `130005`
  - removed deopt family:
    - `Scene.rayColour` `LOAD_ATTR_METHOD_WITH_VALUES`
    - `Scene._lightIsVisible` `LOAD_ATTR_METHOD_WITH_VALUES`
    - `SimpleSurface.colourAt` `LOAD_ATTR_METHOD_WITH_VALUES`
- Remaining follow-up after this round:
  - `Canvas.plot`
  - `Vector.scale`
  - `addColours`
  - `SimpleSurface.colourAt` instance-value path

## Raytrace Follow-up: mixed float guards and int clamp min/max

### Goal
- Reduce the next remaining raytrace deopt buckets after the polymorphic method-load fix:
  - `Vector.scale`
  - `addColours`
  - `Canvas.plot`

### Result
- Current retained policy:
  - for specialized numeric float guards on no-backedge code, keep them only for loop-hot code or issue31-style leaf methods with inferred exact non-self args
  - leave self-only helpers such as `Vector.scale()` and generic helpers such as `addColours()` on the generic path
  - leave obvious integer clamp shapes like `max(0, min(255, int(...)))` on the generic min/max path instead of forcing the float-specialized builtin lowering
- New regression coverage:
  - `test_self_only_float_leaf_mixed_factor_avoids_deopts`
  - `test_builtin_min_max_int_clamp_shape_avoids_float_guard_deopts`
- Remote ARM staging validation:
  - targeted tests:
    - `test_polymorphic_method_load_avoids_method_with_values_deopts`
    - `test_self_only_float_leaf_mixed_factor_avoids_deopts`
    - `test_builtin_min_max_int_clamp_shape_avoids_float_guard_deopts`
    - `test_specialized_numeric_leaf_mixed_types_avoid_deopts`
    - `test_plain_instance_other_arg_guard_eliminates_cached_attr_loads`
    - `test_other_arg_inference_skips_helper_method_shapes`
  - result: `OK`
- Raytrace `compile_strategy=all` update:
  - previous median: `0.5452457539504394s`
  - current median: `0.5367581009631976s`
  - previous total deopts: `257510`
  - current total deopts: `19285`
  - removed deopt families:
    - `Vector.scale`
    - `addColours`
    - `Canvas.plot`
- Remaining follow-up after this round:
  - `SimpleSurface.colourAt` `LOAD_ATTR_INSTANCE_VALUE`

### Discarded attempt
- A narrower `LOAD_ATTR_INSTANCE_VALUE` fallback for non-leaf `self` receivers was prototyped.
- It removed the remaining deopts but regressed raytrace wall time to about `1.92s`, so it was not kept.

## Issue 34: builtin `min/max` on two floats

### Goal
- Remove the generic `VectorCall` path for `min(a, b)` / `max(a, b)` when both arguments are exact floats.
- Preserve Python semantics for NaN handling, signed-zero ties, and result object identity.

### Analysis
- Direct lowering to `DoubleBinaryOp<Min/Max>` is not semantically safe for Python builtins:
  - `min/max` return one of the original operand objects, not a freshly boxed float.
  - NaN behavior is order-sensitive (`min(nan, 1.0)` differs from `min(1.0, nan)`).
  - Ties such as `0.0` vs `-0.0` preserve the first argument object.
- Safe specialization strategy:
  - keep the builtin `GuardIs`
  - guard both args to `FloatExact`
  - unbox to `CDouble`
  - compare `rhs < lhs` for `min` and `rhs > lhs` for `max`
  - branch/select between the original operand objects

### Verification
- Remote ARM editable rebuild on `/root/work/frame-stage-local`: completed
- Targeted tests:
  - `test_builtin_min_max_two_float_args_eliminate_vectorcall`: passed
  - `test_builtin_min_max_two_float_args_preserve_order_nan_and_identity`: passed
- Probe results (`N=2_000_000`):
  - `min_builtin`: `0.1626069820486009s`
  - `min_ternary`: `0.2111730769975111s`
  - `min_ratio`: `0.7700175815997482x`
  - `max_builtin`: `0.16318202891852707s`
  - `max_ternary`: `0.21114284498617053s`
  - `max_ratio`: `0.7728513316622934x`
- Optimized HIR evidence:
  - `VectorCall = 0`
  - `GuardType = 2`
  - `PrimitiveUnbox = 2`
  - `PrimitiveCompare = 1`
  - `CondBranch = 2`
  - `Phi = 1`

### Status
- Current local code for issue34 is ready for review/commit.

## Issue 33: builtin `abs` on float

### Goal
- Remove the generic `VectorCall` path for `abs(x)` when `x` is an exact float.
- Lower the hot path to a dedicated double abs opcode that can become ARM64 `FABS`.

### Analysis
- Unlike builtin `min/max`, `abs(float)` does not need to preserve operand object identity.
- The safe specialization strategy is:
  - keep the builtin `GuardIs`
  - guard the argument to `FloatExact`
  - `PrimitiveUnbox<CDouble>`
  - `DoubleAbs`
  - `PrimitiveBox<CDouble>`
- The repo does not have a generic `DoubleUnaryOp` hierarchy, so the minimal fit is a dedicated `DoubleAbs`, mirroring existing `DoubleSqrt`.

### Verification
- Remote ARM editable rebuild on `/root/work/frame-stage-local`: completed
- Targeted tests:
  - `test_builtin_abs_float_lowers_to_double_abs`: passed
  - `test_builtin_abs_float_preserves_nan_and_negative_zero`: passed
- Probe results (`N=2_000_000`):
  - `abs_builtin`: `0.7133366869529709s`
  - `abs_manual`: `0.649760145926848s`
  - `abs_ratio`: `1.0978461689666028x`
- Optimized HIR evidence:
  - `GuardIs = 1`
  - `GuardType = 1`
  - `PrimitiveUnbox = 1`
  - `DoubleAbs = 1`
  - `PrimitiveBox = 1`
  - `VectorCall = 0`

### Status
- Current local code for issue33 is ready for review/commit.

## Nqueens Optimization

### Goal
- Analyze current `pyperformance bm_nqueens` HIR/LIR bottlenecks on ARM.
- Identify the next highest-value optimization beyond the existing `set(genexpr)` work.

## 2026-04-05 post-fix update

- Minimal targeted fix implemented:
  - `cinderx/Jit/hir/pass.cpp`
  - `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Remote targeted verification on the fixed working-tree snapshot:
  - `test_force_compile_annotation_thunk_does_not_crash`: pass
  - `test_attr_derived_polymorphic_method_load_avoids_method_with_values_deopts`: pass
- Remaining blocker:
  - fresh same-build `go` pyperformance validation is still blocked by a
    harness-layer shell error in `remote_update_build_test.sh` during the
    pyperformance setup phase
- Land the smallest safe improvement with remote-only verification and record the result in `findings.md`.

### Workflow
- Brainstorming:
  - capture current benchmark timing, compiled functions, deopts, and opcode mix
  - compare hotspot HIR/LIR against already optimized `set(genexpr)`-style shapes
- Writing plans:
  - keep the active checklist and decisions in this file
- TDD:
  - add a targeted runtime regression that proves the new lowering/optimization fires
- Verification before completion:
  - rebuild and benchmark only through the remote ARM entrypoint
  - record key HIR/LIR evidence and timing deltas in `findings.md`

### Current status
- [x] Capture current remote `bm_nqueens` baseline and hotspot functions
- [x] Inspect hotspot HIR/LIR and rank optimization opportunities
- [~] Implement the best narrow optimization
- [ ] Add a targeted regression test
- [ ] Rebuild and validate remotely
- [x] Record current evidence in `findings.md`

### Current findings
- Stable latest-code remote baseline (`/root/work/cinderx-nqueens-head`):
  - `compile_strategy=all`: median `1.1747283110162243s`
  - `compile_strategy=none`: median `1.389004991040565s`
  - no runtime deopts
- Current optimized `n_queens` already benefits from the earlier `set(genexpr)` work:
  - `MakeSet = 2`
  - `SetSetItem = 2`
  - no generator-object call chain on the two `set(...)` diagonals
- The remaining dominant hotspot is `bm_nqueens_run:permutations`:
  - `VectorCall = 7`
  - `CallMethod = 2`
  - `MakeFunction = 2`
  - `BuildSlice = 2`
  - `ListSlice = 4`
- Most important residual shape:
  - the two `tuple(pool[i] for i in indices[:r])` sites
  - on Python 3.14 these are already bytecode-optimized into:
    - `BUILD_LIST`
    - `MAKE_FUNCTION`
    - `CALL 0` to create the genexpr generator object
    - outer `FOR_ITER + LIST_APPEND`
    - `CALL_INTRINSIC_1(INTRINSIC_LIST_TO_TUPLE)`
  - so the remaining waste is generator-object creation, not the outer tuple call itself

### Prototype result
- Tried a builder-time rewrite to inline the compiler-optimized `tuple(genexpr)` path.
- Conclusion:
  - this is still the best expected next optimization for `nqueens`
  - but the straightforward prototype is not yet safe enough to land because it needs a cross-basic-block rewrite of the `CALL 0 -> FOR_ITER -> LIST_APPEND -> LIST_TO_TUPLE` pattern
  - on Python 3.14, the compiler emits both:
    - an exact-builtin fast path for `tuple`
    - a fallback generic call path if builtin identity does not hold
  - current HIR counts therefore mix executed fast-path ops with dormant fallback-path ops
  - more importantly, the `CALL 0` that creates the genexpr object and the following `FOR_ITER` live in different bytecode blocks, so the old `set(genexpr)` same-block rewrite structure does not apply
  - current local worktree has been restored to stable `HEAD`; no unverified nqueens optimization code is kept

## Session: 2026-05-12 AArch64 new optimization search

### Goal
- Start from the clean merged AArch64 base after:
  - `27142c72 perf(jit): use nearby aarch64 guard stubs`
  - `57846e36 perf(jit): emit aarch64 cbz/cbnz`
  - `95f8ac63 perf(jit): add aarch64 loadattr lir stub`
- Continue from latest remote after:
  - `6a330ecc perf(jit): fold aarch64 fp compare branches`
- Identify new ARM/micro-architecture-friendly optimization points.
- Do not stack on already-tested local candidates.
- Stop only if one benchmark row improves by `30%+`, or overall/geomean improves by `10%+`.
- Do not push or merge candidate code to remote.

### Branch
- Current search branch: `codex/aarch64-new-optimizations-20260512`
- Starting commit: `95f8ac63`
- Current local base: fast-forwarded to `6a330ecc`

### Phases

#### Phase 1: Clean base and evidence setup
- [x] Switch to a clean branch from `95f8ac63`.
- [x] Collect current merged-base LIR/benchmark evidence.
- [x] Refresh local branch after remote added AArch64 FP compare branch folding.
- Status: completed

#### Phase 2: Candidate discovery
- [x] Sweep existing hot LIR families after the three merged optimizations.
- [x] Rank ARM-specific candidates by likely upside and implementation risk.
- [ ] Continue discovering candidates because no stop condition has been met.
- Status: in_progress

#### Phase 3: Prototype and test
- [x] Test StoreAttr cached stub threshold/default-enable candidate.
- [x] Test Test+BranchZ/NZ to cbz/cbnz postalloc candidate.
- [x] Test shared call-stub threshold candidate.
- [x] Test LoadAttr stub threshold candidate.
- [x] Test vectorcall arg-array StorePair/stp candidate.
- [x] Run exact LoadMethod cache split diagnostic.
- [x] Test AArch64 MemImm literal-pool address candidate.
- [x] Inspect AArch64 FMA peephole candidate; reject before build because
  `fmadd` single-rounding is not equivalent to Python `a * b + c`.
- [x] Test AArch64 `BitTest+BranchNC/C` to `tbz/tbnz` candidate.
- [x] Test AArch64 `GuardNotNegative` direct `tbnz` to near-deopt candidate.
- [x] Test materialized compare-bool branch to direct `Cmp + BranchCC` candidate.
- [x] Test AArch64 subword `NotZero/Zero` guard to direct `cbz/cbnz` candidate.
- [x] Test AArch64 `PrimitiveBox<CInt64>` rematerialization candidate.
- [x] Test AArch64 subword `CondBranch` to direct `cbz/cbnz` candidate.
- [x] Test multiple-code-sections layout candidate on current 3-opt base.
- [x] Prototype/test AArch64 `LoadMethodCache::lookupHelper` fast-path stub.
- [x] Run perf follow-up on LoadMethod stub and test multi-entry variant.
- [x] Run enabled perf follow-up for the multi-entry LoadMethod stub.
- [x] Test compile-time `ENABLE_LIGHTWEIGHT_FRAMES=1` candidate.
- [x] Test `PYTHONJITATTRCACHESIZE=8/16` candidate.
- [x] Test `PYTHONJITHUGEPAGES=0` candidate.
- [x] Prototype/test AArch64 `JITRT_UnlinkFrameFromTstate` epilogue helper.
- [x] Prototype/test AArch64 known-frame unlink refinement.
- [x] Prototype/test AArch64 multi-entry StoreAttr cached stub refinement.
- [x] Prototype/test AArch64 generator inline-decref candidate.
- [x] Prototype/test AArch64 broad float-guard specialization candidate.
- [x] Prototype/test AArch64 BatchDecref threshold sweep.
- [x] Prototype/test AArch64 inline `CheckSequenceBounds` fast path.
- [x] Prototype/test AArch64 `isValidKeysVersion` force-inline candidate.
- [x] Prototype/test AArch64 direct `tp_iternext` fast path for `InvokeIterNext`.
- [x] Prototype/test AArch64 fast non-generator `FrameHeader` lookup in frame clear.
- [x] Prototype/test AArch64 unchecked tstate in `JITRT_UnlinkFrame`.
- [x] Prototype/test AArch64 `FOR_ITER_LIST` list-iterator helper specialization.
- [x] Prototype/test AArch64 compact-long `CompareBool` helper specialization.
- [x] Prototype/test AArch64 managed-dict fast path in `isValidKeysVersion`.
- [x] Prototype/test AArch64 LoadMethod entry-local dict-offset validation.
- [x] Prototype/test AArch64 exact-`TFunc` vectorcall direct helper.
- [x] Prototype/test AArch64 exact-float nonzero-constant true-divide lowering.
- [x] Re-test AArch64 `JITRT_UnlinkFrameFromTstate` on current 4-opt base.
- [x] Prototype/test AArch64 unchecked tstate in generator send and frame clear.
- [x] Prototype/test AArch64 generic `JITRT_RichCompareBool` compact-long fast path.
- [x] Prototype/test AArch64 `LOAD_ATTR_METHOD_WITH_VALUES` guard-only variants.
- [x] Prototype/test AArch64 tiny method-with-values bypass and exact-arg inference variants.
- [x] Prototype/test AArch64 list suffix-rotate helper.
- [x] Prototype/test AArch64 callable-instance one-arg vectorcall helper variants.
- [x] Capture current4 `go` perf and prototype/test AArch64 compact-long `LongInPlaceOp` helper variants.
- [x] Prototype/test AArch64 immortal-bool type propagation variants.
- [x] Prototype/test AArch64 unused tiny return-self call elimination.
- [x] Prototype/test AArch64 compact-long `IndexUnbox` helper fast path.
- [x] Prototype/test AArch64 exact-float generic `BinaryOp` helper fast path.
- [x] Prototype/test AArch64 compact-long bitwise helper fast path.
- [x] Prototype/test AArch64 exact-container `GetLengthInt64` helper fast path.
- [x] Prototype/test AArch64 exact-list `StoreSubscr` helper fast path.
- [x] Prototype/test AArch64 exact-list + slice subscript helper fast path.
- [x] Prototype/test AArch64 tstate-aware frame unlink and clear refinement.
- [x] Prototype/test AArch64 exact-list `MakeTupleFromList` helper.
- [x] Prototype/test AArch64 fixed-arity small `MakeTuple<1/2/3>` helpers.
- [x] Prototype/test AArch64 direct double `StoreArrayItem` lowering on scimark.
- [x] Prototype/test AArch64 direct primitive `StoreArrayItem` lowering on scimark.
- [x] Prototype/test AArch64 direct all-type `StoreArrayItem` lowering.
- [x] Prototype/test AArch64 direct CPython API calls for selected `PrimitiveBox` helpers.
- [x] Prototype/test AArch64 compact-long `PrimitiveUnbox` helper fast path on scimark.
- [x] Prototype/test AArch64 compact-long `LongBinaryOp<Add/Subtract>` helper fast path.
- [x] Prototype/test AArch64 `FOR_ITER_TUPLE` tuple-iterator helper fast path.
- [x] Test configuration candidate `PYTHONJITENABLEHIRINLINER=1`.
- [x] Test configuration candidate `PYTHONJITENABLEHIRINLINER=1 PYTHONJITHIRINLINERCOSTLIMIT=10000`.
- [x] Prototype/test AArch64 `FOR_ITER_RANGE` range-iterator helper fast path.
- [x] Prototype/test AArch64 duplicate `CheckField` / `CheckVar` elimination.
- [x] Prototype/test AArch64 `LoadFieldAddress + LoadArrayItem[0]` addressing fold.
- [x] Prototype/test AArch64 HIR checked exact-float `BinaryOp<Add/Subtract/Multiply>` fast path.
- [x] Prototype/test narrower AArch64 HIR checked exact-float `BinaryOp<Multiply>` fast path.
- [x] Prototype/test AArch64 delayed `_PyThreadState_GET()` in vectorcall helpers.
- [x] Prototype/test AArch64 no-incref return for immortal `JITRT_IterDoneSentinel`.
- [x] Re-test AArch64 exact `LoadMethod` split with trusted type guard.
- [x] Prototype/test AArch64 exact list/tuple nonnegative-int subscript helper.
- [x] Prototype/test AArch64 exact list/tuple nonnegative-int subscript helper that skips slice subscripts.
- [x] Prototype/test AArch64 combined exact dict/list/tuple subscript helper.
- [x] Prototype/test AArch64 `STORE_ATTR_INSTANCE_VALUE` direct helper variants.
- [x] Prototype/test AArch64 owner-based `jitFrameGetHeader` generator check.
- [x] Prototype/test AArch64 compact-long helper for `LongCompare` object result.
- [x] Test HIR inliner on scimark.
- [x] Prototype/test AArch64 branchless `CheckSequenceBounds` with `csel`.
- [x] Prototype/test AArch64 no-promotion `LoadMethodCache::lookup`.
- [x] Prototype/test AArch64 direct `LoadMethodCache` cached-result construction.
- [x] Prototype/test AArch64 generator `XDecref`-only inline refinement.
- [x] Prototype/test AArch64 `JITRT_InvokeIterNext` skip-null-check fast path.
- [x] Prototype/test AArch64 direct CPython API calls for selected `PrimitiveBox` helpers on object subset.
- [x] Prototype/test AArch64 direct `PyFloat_FromDouble` for `PrimitiveBox<TCDouble>` only.
- [x] Prototype/test AArch64 Decref immortal-bit `tbnz/tbz` branch form.
- [x] Prototype/test AArch64 zero-immediate memory stores with `wzr/xzr`.
- [x] Prototype/test AArch64 StoreAttr interpreter-state threading variants.
- [x] Prototype/test AArch64 inline `AttributeMutator` kind/empty checks.
- [x] Prototype/test AArch64 inline StoreAttr cache entry scan.
- [x] Prototype/test AArch64 consecutive duplicate Guard removal.
- [x] Prototype/test AArch64 keep zero-immediate register moves instead of self-`Xor`.
- [x] Prototype/test AArch64 `PrimitiveBoxBool` shifted pointer arithmetic.
- [x] Prototype/test AArch64 `LoadMethodCache::lookup` slot0 likely branch hints.
- [x] Prototype/test AArch64 offset-zero indexed memory operands.
- [x] Prototype/test AArch64 GuardType/GuardIs target materialization fold.
- [x] Prototype/test AArch64 `AttributeMutator::setAttr` hot-case ordering.
- [x] Prototype/test AArch64 forced inline `AttributeMutator::setAttr`.
- [x] Prototype/test AArch64 `GuardNotNegative` direct `tbnz` to near-deopt.
- [x] Prototype/test AArch64 `GuardNotNegative` direct `tbnz` to near-deopt, 64-bit-only.
- [x] Prototype/test AArch64 `GuardNotNegative` direct `tbnz` to near-deopt, 32-bit-only.
- [x] Test AArch64 shared call-stub high-threshold / effectively-disabled runtime candidate.
- [x] Re-test AArch64 `GuardNotNegative` direct `tbnz` to near-deopt on the 223 ARM host.
- [x] Prototype/test AArch64 `IntToBool + BranchZ/NZ` postalloc fold on the 223 ARM host focused subset.
- [x] Run full JIT28 S3/S12 for AArch64 `IntToBool + BranchZ/NZ` postalloc fold.
- [ ] Because the benefit is determined, collect lightweight real-workload hit evidence, counter data, or LIR/ASM census for AArch64 `IntToBool + BranchZ/NZ` postalloc fold before review/reporting.
- [ ] Inspect/prototype the next independent candidate from clean base only if causality/review rejects the current stop-condition candidate.
- Status: stop_condition_hit; pause broad discovery and immediately finish causality evidence for `IntToBool + BranchZ/NZ`; review/reporting comes after that gate.

#### Phase 4: Stop-condition gate
- [x] Check each tested candidate against `30%` single-row or `10%` geomean.
- [x] If not met, record and continue discovery.
- [ ] Complete causality evidence for the stop-condition candidate.
- [ ] Run final review only after causality/workload hit evidence is complete.
- Status: performance stop condition hit by `IntToBool + BranchZ/NZ`; full JIT28 S12 speedup geomean is `+10.065%`, with `comprehensions +30.070%`, `coroutines +41.736%`, and `nqueens +32.102%`.
