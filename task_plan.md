# Task Plan: Issue 31 Raytrace Regression Fix

## Goal
Keep the issue31 instance-attr specialization gains while removing the severe raytrace regression introduced by commit `4c14dd10`.

## Current Phase
Pyperformance JIT performance tuning wave: build an extended benchmark scoreboard and then iterate on test-first JIT optimizations until the selected benchmark set reaches at least 30% geometric-mean speedup versus the current JIT baseline, without skipping correctness blockers or failing benchmarks.

## Current Performance Tuning Addendum
- [x] Define the extended JIT-relevant pyperformance set:
  - `richards,go,deltablue,raytrace,nqueens`
  - `generators,coroutines,comprehensions,unpack_sequence,chaos,logging,coverage`
  - `nbody,spectral_norm,scimark,float,fannkuch`
  - `pickle,pickle_dict,pickle_list,json_dumps,json_loads`
- [x] Define the stop metric as candidate-versus-current-JIT-baseline geometric mean speedup.
- [x] Keep no-JIT measurements as an upside/capability map, not as the stop baseline.
- [x] Add scoreboard support for per-benchmark ratios and geomean speedup.
- [x] Add explicit pyperformance subset modes for `autojit` and `nojit`.
- [x] Run the current branch extended unfiltered `autojit50` baseline through `/root/work/incoming/remote_update_build_test.sh`.
- [x] Run the no-JIT capability baseline through `/root/work/incoming/remote_update_build_test.sh`.
- [x] Run the filtered `jitlist` baseline through `/root/work/incoming/remote_update_build_test.sh`.
- [x] Rank the first production optimization candidate from fresh matrix evidence.
- [~] For each production candidate, use RED/GREEN TDD through the remote entrypoint.
- [ ] Stop only when geomean time ratio is `<= 0.70` and functional verification is green.
- Latest active loop:
  - specialized set/dict contains lowering is functionally complete and
    verified through the remote entrypoint.
  - focused gate RED:
    `arm-results/specialized_set_contains_gate_red_20260503_1.log`.
  - focused gate GREEN:
    `arm-results/specialized_set_contains_gate_green_20260503_1.log`.
  - adjacent ARM runtime:
    `arm-results/specialized_set_contains_adjacent_20260503_3.log`,
    `Ran 120 tests`, `OK`; smoke passed.
  - pyperformance runner pytest:
    `arm-results/pyperf_subset_tools_specialized_contains_20260503_1.log`,
    `4 passed`.
  - 8-row matrix:
    `arm-results/specialized_contains_matrix_20260503_1.log`.
  - disabled-vs-enabled result:
    `geomean_time_ratio = 0.9995066378813695`,
    `geomean_speedup_pct = 0.04933621186304915`, no >5% regressions.
  - decision:
    keep gated, but continue optimization because this does not move the
    selected-workload target.
  - KW exact PyFunction vectorcall:
    `arm-results/kw_exact_pyfunc_gate_green_20260503_1.log` focused GREEN;
    `arm-results/kw_exact_pyfunc_adjacent_20260503_2.log` adjacent GREEN;
    `arm-results/kw_pyfunc_vectorcall_matrix_20260503_1.log` selected 8-row
    matrix.
  - KW vectorcall matrix result:
    `geomean_time_ratio = 0.991333621477996`,
    `geomean_speedup_pct = 0.8666378522004026`, no >5% regressions.
  - decision:
    keep default-on as a scoped micro-win; continue, because combined evidence
    is still well short of `geomean_time_ratio <= 0.70`.
  - AutoJIT threshold band:
    `arm-results/autojit_band_matrix_20260503_1.log`, 8 rows, 5 samples,
    policy h512, thresholds 50/75/100/150/200.
  - threshold result versus `AUTOJIT=50`:
    `75 = -0.0927% geomean, go -3.02%`;
    `100 = +0.291% geomean, go -6.15%`;
    `150 = -0.127% geomean, go -10.12%`;
    `200 = -1.01% geomean, go -14.77%`.
  - threshold decision:
    keep `AUTOJIT=50`; global threshold bump is not viable for the target
    object workload mix.
- Latest matrix note:
  - pyperformance expands `logging` and `scimark`, so the selected list becomes
    28 concrete benchmark rows.
  - unfiltered `MODE=autojit AUTOJIT=50` versus `MODE=nojit` produced
    `geomean_time_ratio = 6.7114`, meaning broad unfiltered auto-JIT is much
    slower overall on this suite.
  - filtered `MODE=jitlist` versus unfiltered `autojit50` produced
    `geomean_time_ratio = 0.2828`, a `71.7%` time reduction against the bad
    unfiltered JIT baseline.
  - filtered `MODE=jitlist` versus no-JIT still produced
    `geomean_time_ratio = 1.8979`, so compile selection fixes the worst policy
    damage but does not make the JIT broadly profitable yet.
  - high-threshold `autojit1000` versus unfiltered `autojit50` produced only
    `geomean_time_ratio = 0.9607`, so a global threshold increase is not a
    meaningful fix.
  - filtered delayed `jitlist-autojit50` versus eager `jitlist` produced
    `geomean_time_ratio = 3.3843`, showing delayed compile transition costs are
    bad for this pyperformance single-value harness.
  - immediate implication: keep eager filtered `jitlist` as the policy oracle,
    then pursue a real execution-cost candidate. Current top HIR/LIR candidate:
    exact list/tuple/range `FOR_ITER` lowering.
  - `FOR_ITER_LIST` builder-time HIR specialization was tested and rejected for
    now: during JIT compile, C++ observed the base `FOR_ITER` opcode even when
    Python adaptive disassembly showed `FOR_ITER_LIST`.
  - current implementation path: exact list-iterator fast path inside existing
    `JITRT_InvokeIterNext`, followed by remote functional verification and
    pyperformance comparison.
  - list-iterator helper result:
    - focused remote `Ran 1 test`, `OK`
    - adjacent remote `Ran 8 tests`, `OK`
    - 8-row pyperformance subset `geomean_time_ratio = 0.9849120157035239`
    - no `>=5%` row regressions
    - decision: small safe win, not enough for the 30% stop target.
  - tuple/range iterator helper extension result:
    - focused remote `Ran 2 tests`, `OK`
    - adjacent remote `Ran 9 tests`, `OK`
    - 8-row pyperformance subset `geomean_time_ratio = 0.9855222065914018`
    - no `>=5%` row regressions
    - decision: builtin iterator helper family is clean but still only about
      `1.5%`, so continue to a larger execution-cost candidate.
  - loop-heavy jitlist policy simulation:
    - 8-row pyperformance subset `geomean_time_ratio = 0.7474786908573173`
      versus full eager `jitlist`
    - close to the `<=0.70` stop target, but not enough
    - blocker: `go` regressed `19.1681%`
    - next: refine object-helper admission instead of landing a pure
      loop-heavy policy.
  - refined object-helper policy simulation:
    - 8-row pyperformance subset `geomean_time_ratio = 0.775399315072543`
      versus full eager `jitlist`
    - `go` recovered, but `generators` and `richards` regressed beyond the
      warning gate
    - conclusion: a single positive jitlist profile is not robust enough.
  - credible harness correction after worker venv/wheel fix:
    - the pyperformance wrapper now creates the declared worker venv and
      installs the fresh CinderX wheel into the actual timed worker Python.
    - corrected `AUTOJIT=0` probe compiled benchmark functions such as
      `__main__:Task.qpkt`, proving timed workers now use the built JIT.
  - latest credible 8-row matrix:
    - no-JIT vs autojit0:
      `geomean_time_ratio = 4.135672727365508`
    - no-JIT vs autojit50:
      `geomean_time_ratio = 17.073658059316212`
    - autojit50 vs stateful deferred autojit50:
      `geomean_time_ratio = 0.8721901131266123`
    - no-JIT vs stateful deferred autojit50:
      `geomean_time_ratio = 14.891475754240103`
  - current decision:
    - broad JIT enablement is still far below the 30% speedup target versus
      no-JIT on the selected debug-single-value suite.
    - dynamic deferred helper promotion is a meaningful improvement versus
      broad autojit50, but not sufficient.
    - next phase is a corrected compile-selection benchmark pass: filtered
      `jitlist` and `jitlist-autojit` after the worker venv/wheel fix.
  - corrected `jitlist`/`jitlist-autojit` benchmark pass:
    - remote log: `arm-results/jitlist_matrix_20260503_2.log`
    - same entrypoint run passed 110 ARM runtime tests and JIT effectiveness
      smoke.
    - no-JIT vs eager `jitlist __main__:*`:
      `geomean_time_ratio = 4.11819462384738`
    - no-JIT vs `jitlist-autojit50`:
      `geomean_time_ratio = 17.10706585856534`
    - `jitlist-autojit50` vs stateful deferred `jitlist-autojit50`:
      `geomean_time_ratio = 0.8781559168729067`
    - decision: compile selection by `__main__:*` is not sufficient; next
      production policy should explicitly protect cold/short/generated code
      from optimized compilation until runtime hotness evidence is stronger.
- Generated-code cold filter phase:
  - [x] Add local RED wrapper contract for `PYTHONJITFILTERGENERATED`.
  - [x] Implement default-off `jit-filter-generated` /
    `PYTHONJITFILTERGENERATED`.
  - [x] Keep local wrapper/hook tests green.
  - [x] Run remote ARM RED/GREEN for
    `ArmRuntimeTests.test_generated_code_filter_skips_comprehension_code`.
    - remote log: `arm-results/generated_filter_green_20260503_1.log`
    - default ARM runtime: `Ran 111 tests in 17.005s`, `OK (skipped=3)`
    - focused generated-filter test: `ok`
    - JIT effectiveness smoke: `jit-effective-ok compiled_size 976 interp_calls 10`
  - [x] Run a corrected pyperformance matrix with generated filtering.
  - [x] Write final generated-filter benchmark result to `findings.md`.
  - Matrix result:
    - remote/local log:
      `arm-results/generated_filter_matrix_20260503_1.log`
    - `jitlist` vs `generated_jitlist`:
      `geomean_time_ratio = 0.9917048374233595`
    - `jitlist` vs `generated_stateful_deferred_jitlist`:
      `geomean_time_ratio = 0.8679698298110454`, but `go` regressed
      `20.60%` and `richards` regressed `15.68%`
    - `jitlist-autojit50` vs generated+stateful deferred `jitlist-autojit50`:
      `geomean_time_ratio = 0.8633087797836041` with no >=5% regressions
    - decision: generated filtering alone is not a 30% path; the next
      performance slice must address object/state method-call cost while
      preserving the policy wins on `deltablue`, `nqueens`, and `raytrace`.
- Attr-state deferred helper promotion phase:
  - [x] RED remote focused test for attr-only `self` helper deferral.
  - [x] Extend deferred helper classifier to attribute load/store helper shapes.
  - [x] GREEN remote focused test.
  - [ ] Rerun attr-helper pyperformance matrix after remote SSH recovers.
  - [ ] If `go`/`richards` recover without losing geomean, keep and expand
    verification; otherwise refine or revert this candidate.

- Dynamic object method-call cost phase:
  - [x] Add exact `list.pop()` default-index helper and opt-out coverage.
  - [x] Verify helper through the remote ARM entrypoint.
  - [x] Run same-run list-pop pyperformance matrix.
  - [x] Record that `go` improves by roughly `+1.5%` but selected geomean does
    not improve.
  - [x] Capture post-helper `go`/`richards` code-shape diagnostics.
  - [ ] Pick the next bigger candidate that reduces the remaining
    `LoadMethodCached + CallMethod` cost rather than only changing fallback or
    thresholds.
  - [ ] Prove the candidate with RED/GREEN remote tests before performance
    claims.
  - [ ] Run the selected pyperformance matrix and update `findings.md`.

- Merge-readiness / combined optimization phase:
  - [x] List all default-on, gated/off, rejected, and removed optimization
    attempts in `findings.md`.
  - [x] Run a same-entrypoint combined matrix for current retained switches.
  - [x] Compute distance to the `30%` selected-workload target.
  - [ ] Create a new branch from remote `bench-cur-7c361dce`.
  - [ ] Split commits into benchmark tooling, JIT optimization/policy code, and
    evidence docs.
  - [ ] Verify the commit branch through the remote entrypoint before push.

## Current Quality Pass Addendum
- [x] Debug and fix the `precompile_all(workers=2)` crash in the compile-failure cooldown test.
- [x] Keep the fix functional and narrow: skip nested genexpr HIR inlining only during threaded precompile, where worker threads do not own a Python thread state.
- [x] Verify through the remote ARM entrypoint:
  - focused `precompile_all(workers=2)` tiering regression
  - full `test_jit_tiering`
  - broader OSR / method-with-values / normal genexpr guard set
- [x] Guard the next high-risk optional worker-thread Python-dict queries:
  - known-callable fallback lookup
  - tiny-method candidate scanning
  - math.sqrt module-dict validation helpers
- [x] Continue broader threaded-precompile audit for less obvious Python C-API access before returning to performance tuning.
- [x] Add explicit tier policy state to the unified per-function tier model:
  - `ready`
  - `compile_failure_cooldown`
  - `deopt_budget_exhausted`
- [x] Preserve policy/backoff state across explicit uncompile so blocked functions do not blindly promote again.
- [x] Clean stale type-deopt patchers when compiled runtime owners are removed, closing the invalidation/fallback lifecycle hole found by the deopt-budget test.
- [x] Review submit-readiness for the current dirty worktree, fix shared CodeRuntime uncompile ownership, and record a pushable commit split.
- [x] Add mature tier policy decision telemetry:
  - count promotion policy decisions
  - count blocked promotion attempts separately from real compile attempts
  - expose last promotion decision plus last policy event/reason
  - verify RED/GREEN through the remote ARM entrypoint
- [x] Complete tier policy lifecycle semantics:
  - bounded compile-failure cooldown/backoff instead of a permanent latch
  - explicit cooldown remaining, streak, backoff, and reset telemetry
  - promotion allowed again only after the policy cooldown expires
  - successful optimized compile resets compile-failure policy state
  - RED/GREEN and full functional verification through the remote ARM entrypoint
- [x] Harden tier policy lifecycle review findings:
  - clean successful compile does not count as a policy reset
  - cooldown expiry immediately exposes ready/unblocked state
  - hot-loop OSR cooldown ages once per interpreted activation and resumes on a
    later activation, not within the same hot loop
  - focused review follow-up plus full ARM/tiering verification passed through
    the remote entrypoint
- [x] Expose OSR cooldown resume deferral in tier-state telemetry:
  - add a focused RED test showing the deferred state is not observable today
  - expose a read-only `compile_failure_osr_resume_deferred` field through
    `jit.get_function_tier_state()`
  - keep the field false for clean fallback/no-JIT paths
  - verify focused and full tiering behavior through the remote ARM entrypoint
- [x] Expose pending fallback state after type invalidation:
  - add a focused RED test for the gap between type patching and the first
    runtime fallback
  - expose `fallback_pending` and `fallback_pending_reason` through
    `jit.get_function_tier_state()`
  - clear the pending flag when the runtime fallback is observed or when the
    function is recompiled/uncompiled
  - verify focused and full tiering behavior through the remote ARM entrypoint
- [x] Gate reopt/resume paths through tier policy:
  - add RED coverage showing a deopt-budget-exhausted function can still be
    reoptimized through `reoptFunc()`/enable-resume today
  - route reoptimization through `shouldAttemptOptimizedPromotion()` before
    finalizing optimized code
  - preserve explicit resume behavior for healthy compiled functions
  - verify focused and full tiering behavior through the remote ARM entrypoint
- [x] Classify permanent compile failures separately from transient cooldown:
  - identify a stable unsupported-shape failure that should not blindly enter
    transient cooldown semantics
  - add RED coverage for the new policy state and code-change reset path
  - keep resource/temporary failures on bounded cooldown
  - verify focused and full tiering behavior through the remote ARM entrypoint
- [x] Harden unsupported compile-failure policy across promotion entrypoints:
  - cover `precompile_all` as an unsupported-failure producer, not only
    `force_compile`
  - verify subsequent promotion attempts stay permanently blocked with zero
    transient cooldown/backoff
  - verify focused and full tiering behavior through the remote ARM entrypoint
- [x] Prevent management APIs from bypassing tier policy:
  - add RED coverage showing `jit_unsuppress()` on an already-unsuppressed
    function must not reset compile-failure/deopt policy
  - reset policy only when the suppress flag actually changes
  - verify focused and full tiering behavior through the remote ARM entrypoint
- [x] Gate dependent/static target compilation through tier policy:
  - add RED coverage where a caller compile would otherwise retry an
    unsupported static callee
  - skip policy-blocked dependent targets without incrementing compile failure
    counters again
  - verify focused and full tiering behavior through the remote ARM entrypoint
- [x] Continue tier-policy maturity scan for remaining bypasses:
  - inspect all optimized compile/reopt/preload entrypoints for missing policy
    checks
  - add RED coverage before any new production change
  - keep verification on the unified remote ARM entrypoint
- [x] Address review-minor maturity test gaps:
  - cover non-suppressed unsupported code shapes resetting through
    `__code__` replacement
  - cover shared-runtime pending fallback ownership cleanup
  - verify focused and full tiering behavior through the remote ARM entrypoint
- [x] Close remaining tier-state maturity review findings:
  - count deopt-budget-exhaustion policy resets when `function_modified`
    restores a function to ready state
  - keep shared-runtime runtime-fallback observation per-function so one owner
    does not clear another owner's pending fallback state
  - add maturity tests for unsupported permanent blocks, deopt reset, shared
    disable cleanup, and observed-owner fallback cleanup
  - verify RED/GREEN through the remote ARM entrypoint

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

## Object-heavy follow-up: tiny bool predicate methods

### Goal
- Reduce Python method-call overhead in object-heavy state workloads by directly lowering tiny zero-arg boolean predicate methods that match Richards-style state checks:
  - `self.a and self.b and not self.c`
  - `self.a or (not self.b and self.c)`

### Status
- TDD RED was observed through the remote ARM entrypoint:
  - `test_tiny_bool_predicate_method_eliminates_branch_callmethod` initially failed with `CallMethod = 1` for both predicate callers.
- Production fix currently lives in `cinderx/Jit/hir/simplify.cpp`:
  - classify Python 3.14 bytecode patterns for tiny bool predicates
  - handle `RESUME_CHECK` extended-opcode form
  - replace profiled method fast path (`VectorCall`) and fallback `CallMethod` with guarded direct field reads and boxed bool results
  - attach snapshots to generated fast/miss blocks so guard/refcount passes have valid frame state
- Regression status:
  - remote ARM entrypoint, 13 targeted tests, `Ran 13 tests in 18.357s`, `OK`
- Benchmark status:
  - result file: `/root/work/arm-sync/object_matrix_tiny_bool_predicate_20260501_1.json`
  - compared with `/root/work/arm-sync/object_matrix_storeattr_direct_field_20260501_1.json`:
    - `deltablue`: about `0.18%` faster
    - `go`: about `0.57%` slower
    - `raytrace`: about `0.42%` faster
    - `richards`: about `0.53%` faster
  - compared with `/root/work/arm-sync/object_matrix_listappend_direct_20260501_1.json`:
    - `deltablue`: about `0.33%` faster
    - `go`: about `0.41%` slower
    - `raytrace`: about `0.42%` faster
    - `richards`: about `0.43%` slower
- Decision:
  - keep investigating; this is a real HIR-shape improvement, but not yet a strong standalone throughput win.
  - next phase should focus on remaining hot object method/call shapes in `go` and `richards`.

### Verification notes
- The first benchmark attempt failed before build because the remote entrypoint could not find `/root/work/incoming/cinderx-update.tar`.
- Resolution:
  - re-uploaded `cinderx-update.tar` and `scripts/arm/remote_update_build_test.sh`
  - re-ran the same benchmark command through `/root/work/incoming/remote_update_build_test.sh`

## Object-heavy follow-up: exact list/int STORE_SUBSCR lowering

### Goal
- Remove generic `StoreSubscr` overhead for Python 3.14's specialized `STORE_SUBSCR_LIST_INT` shape in `go`-like object workloads.
- Preserve list assignment semantics for exact builtin lists, including negative integer indexes and `IndexError`.
- Keep list subclasses and non-exact shapes on the existing generic path via guards/deopt.

### Status
- TDD RED was observed through the remote ARM entrypoint:
  - `ArmRuntimeTests.test_list_int_store_subscr_lowers_to_callstatic_helper` initially failed with `StoreSubscr=2`, `CallStatic=0`.
- Production fix currently covers:
  - `BytecodeInstruction::specializedOpcode()` whitelist for `STORE_SUBSCR_LIST_INT`
  - HIR builder exact-list / exact-long guards for both normal and array slow-path store-subscript lowering
  - runtime helper `JITRT_SetListItemExactInt`
  - simplifier rewrite from guarded `StoreSubscr` to `CallStatic + CheckNeg`
- Crash/root-cause found during implementation:
  - after the bytecode whitelist was added, focused force-compile segfaulted in `RefcountInsertion::Run -> DeoptBase::setFrameState -> FrameState copy`
  - HIR diagnostics showed newly allocated array slow-path blocks starting with `GuardType` but no same-block `Snapshot`
  - fix: emit `Snapshot(tc.frame)` at array slow-path block entry before any specialized guard can be inserted there
  - simplifier also now emits snapshots between non-replayable `CallStatic` store helpers and their `CheckNeg` deopt checks
- Focused regression status:
  - remote ARM entrypoint, focused test:
    - `test_list_int_store_subscr_lowers_to_callstatic_helper ... ok`
    - `Ran 1 test in 0.050s`
    - `OK`
- Broader focused regression status:
  - remote ARM entrypoint, object/JIT focused suite:
    - `Ran 14 tests in 18.404s`
    - `OK`
- Matrix status:
  - result file: `/root/work/arm-sync/object_matrix_list_store_int_20260501_1.json`
  - `go` improved about `0.23%` vs the tiny-bool matrix, but the full matrix is still mixed/noisy across the previous same-harness references
  - decision: this is correctness-clean, but not a material standalone performance win
- Next:
  - continue with higher-frequency Python method/function-call overhead, especially `richards` tiny state mutators / `Task.findtcb` and `go` object-call shapes

## Object-heavy follow-up: tiny state-mutator return-self methods

### Design
- Target only zero-arg methods with this shape:
  - one or more `self.<bool_field> = True/False` writes
  - final `return self`
- Primary benchmark target:
  - Richards-style state transitions such as `Task.waitTask`, `TaskState.running`, and `TaskState.packetPending`
- Safety boundary:
  - exact receiver type guard
  - exact method identity guard
  - managed split-dict / inline-values object layout only
  - no method-name instance shadowing in cached split keys
  - bool constants only
  - deopt if a destination field is missing, keys changed, inline values invalid, or method/type identity changed
- Explicitly out of scope for this slice:
  - `Task.findtcb`
  - recursive `go.Square.find`
  - arbitrary setters, descriptors, keyword args, or non-bool assignments

### TDD plan
- Add a focused ARM runtime test with `TaskState.running()` / `TaskState.packetPending()` / `Task.waitTask()`-like methods.
- RED expectation before implementation:
  - caller HIR still contains `CallMethod`
  - no direct field-store lowering for the tiny mutator call itself
- GREEN expectation:
  - target caller HIR has `CallMethod = 0`
  - target caller HIR has direct `StoreField` operations for the bool fields
  - returned object identity and field state transitions remain correct
  - instance method shadowing still changes behavior correctly via deopt/fallback
- Current TDD status:
  - RED observed through remote entrypoint:
    - `CallMethod = 3`
    - `StoreField = 0`
  - focused GREEN observed through remote entrypoint:
    - `Ran 1 test in 0.756s`
    - `OK`

### Verification plan
- All focused RED/GREEN and final benchmark evidence must go through `/root/work/incoming/remote_update_build_test.sh`.
- After GREEN, run:
  - broader object/JIT focused regression suite
  - `richards`-first pyperformance subset with more samples
  - full object-heavy matrix only if `richards` signal is positive or neutral enough to justify broader measurement
- Current regression status:
  - broader focused remote suite:
    - `Ran 15 tests in 19.117s`
    - `OK`
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

## 2026-04-29 Object-Heavy Workload Performance Slice

### Goal
- Find and land one narrow JIT hot-path optimization with measurable benefit on object-heavy pyperformance workloads.
- Primary matrix: `richards`, `go`, `deltablue`, `raytrace`.
- Secondary safety: focused ARM runtime tests for the exact lowering shape.

### Workflow
- Brainstorming:
  - compare current local JIT diff against the object workload symptoms already recorded in `findings.md`
  - rank candidates by expected benchmark impact and correctness risk
- Writing plans:
  - keep this section as the active checklist for the slice
- TDD:
  - prove the candidate shape with a focused test through the remote entrypoint before production changes, or use an existing failing/disabled toggle as RED evidence
- Verification before completion:
  - all tests and benchmark evidence must come from `/root/work/incoming/remote_update_build_test.sh`
  - append key results to `findings.md`

### Current candidate hypotheses
- `LOAD_ATTR_METHOD_WITH_VALUES` for builtin container method descriptors may help list-heavy object workloads, but it must be checked for deopt storms and benchmark regressions.
- `TO_BOOL_BOOL` currently uses a permanent bool guard; a safer fast-bool-with-generic-fallback shape may preserve bool-hot speed without miscompiling non-bool quickening changes.
- Existing MDP-specific min/max and compare rewrites are evidence-positive for `mdp`, but they are benchmark-specific and should not be generalized blindly.

### Checklist
- [x] Capture current remote benchmark baseline for the primary matrix.
- [x] Pick one candidate with code-level evidence and a narrow regression test.
- [x] Run RED through the remote entrypoint.
- [x] Implement the smallest production change.
- [x] Run GREEN focused tests through the remote entrypoint.
- [x] Run benchmark A/B or on/off matrix through the remote entrypoint.
- [x] Record candidate evidence in `findings.md`.
- [ ] Keep only changes whose correctness/stability value is clear or whose throughput evidence is positive enough to justify landing.
- [x] Validate exact list/int subscript read guard-fast-path through focused GREEN, focused regression, and object-heavy matrix.
- [ ] Investigate the next higher-leverage Python-call/method-call shape after the restored list/int read path.

### Current status update
- Stability blocker fixed:
  - pyperformance worker startup no longer segfaults on the new focused regression after gating phase-1 hot-loop OSR to `__main__`.
- Second stability blocker fixed:
  - Richards method/attr-heavy schedule loop no longer segfaults after gating phase-1 OSR to leaf-loop shapes.
- Remaining GREEN scope:
  - retry pyperformance worker and the primary object matrix.
- Positive phase-1 OSR tests passed:
  - `test_phase1_once_call_hot_loop_enters_jit_same_activation`
  - `test_phase1_loop_osr_skips_active_exception_shape`
  - `test_phase1_loop_osr_skips_pyperformance_startup_imports`
  - `test_phase1_loop_osr_richards_method_loop_does_not_crash`
- Low-local instance-value candidate:
  - `PYTHONJITINSTANCEVALUEMINLOCALS=1` initially exposed a method-call stack-shape crash
  - fixed by falling back from `LOAD_ATTR_INSTANCE_VALUE` to the generic method path when the `LOAD_ATTR` method bit is set
  - focused regression now passes through the remote entrypoint
  - matrix result is not throughput-positive overall:
    - `raytrace` improved, but `richards`, `go`, and `deltablue` regressed
  - decision: keep the correctness fix, do not change the default threshold
- Exact method cache split candidate:
  - `PYTHONJITEXACTMETHODCACHESPLIT=1` correctness regression passes through the remote entrypoint
  - object matrix result is not throughput-positive:
    - `raytrace` neutral, `richards`, `go`, and `deltablue` regressed
  - decision: do not enable by default
- Next candidate direction:
  - inspect narrow state-update opportunities, especially safe existing-field `STORE_ATTR`
  - prioritize shapes with targeted benchmark upside and low deopt/regression risk
- `STORE_ATTR_INSTANCE_VALUE` direct-field candidate:
  - helper-call lowering was rejected after matrix regression
  - direct `LoadField` / `CheckField` / `StoreField` lowering now passes focused remote tests
  - same-harness specialized-opcodes-on/off matrix is mixed:
    - small wins for `deltablue`, `go`, and `raytrace`
    - small regression for `richards`
  - decision: keep correctness-clean direct lowering for now, but do not treat it as the final performance win
- Exact list append candidate:
  - `CALL_LIST_APPEND` for exact builtin lists now lowers to `ListAppend` instead of generic `CallMethod`
  - focused RED/GREEN passed through the remote ARM entrypoint
  - direct `go:UCTNode.play` HIR improved from `ListAppend=0`, `CallMethod=7` to `ListAppend=2`, `CallMethod=5`
  - matrix result is mixed:
    - `richards` improved slightly
    - `raytrace` was neutral
    - `go` and `deltablue` were slightly slower
  - decision: keep as a shape/correctness improvement candidate, but do not call it the benchmark win yet
- Next candidate direction:
  - move to hotter method-call / Python-call / loop-body costs
  - prioritize zero-arg/tiny Python method calls and exact PyFunction call overhead
  - avoid more attr-access micro-optimizations unless deopt or opcode-count evidence shows a clear hotspot
- Exact list/int subscript read candidate:
  - restored final two-guard implementation after rejecting the unsigned single-guard refinement
  - remote focused regression after restore:
    - `Ran 16 tests in 14.378s`
    - `OK`
  - restored matrix versus `object_matrix_mutator_disabled_20260501_1.json`:
    - `deltablue`: about `0.43%` faster
    - `go`: about `0.08%` faster
    - `raytrace`: about `0.50%` faster
    - `richards`: about `0.09%` faster
  - decision: keep this as a small safe win, but move up-stack to Python-call/method-call overhead for stronger gains
- HIR inliner switch experiment:
  - global inliner-on matrix is mixed versus the restored baseline:
    - `richards` and `go` improve
    - `deltablue` and `raytrace` regress
  - decision: do not flip global HIR inliner on by default.
- Next selected candidate:
  - selective lookup-free monomorphic Python method call / inline fast path.
  - design intent:
    - prove a `Task.findtcb(self, id)` / `Square.find(update)`-style one-arg method call can eliminate method lookup and expose or produce inlining without globally enabling broad inliner behavior.
    - preserve shadowing, subclass, and polymorphic fallback/deopt semantics.
  - initial TDD target:
    - focused ARM runtime test that shows the caller still has `LoadMethodCached/LoadMethod + CallMethod/VectorCall` before the change and fewer lookup/call ops after the change.
    - negative cases for instance shadowing and receiver polymorphism.
- Selective method-value preload implementation:
  - RED:
    - `ArmRuntimeTests.test_method_with_values_one_arg_method_preloads_for_hir_inliner`
    - remote entrypoint failure showed `num_inlined_functions = 0` while `VectorCall = 1`
  - GREEN:
    - preloader records warmed `LOAD_ATTR_METHOD_WITH_VALUES` cached `PyFunction` descriptors
    - dependent preloading now feeds those functions to the existing HIR inliner
    - focused remote test passed with `Ran 1 test in 0.048s`, `OK`
  - remaining validation:
    - [x] focused object/JIT/OSR regression suite
    - [x] broad refreshed inliner-on object-heavy pyperformance matrix
    - [x] narrow the method-value preload candidate after broad preload regressed `richards`/`deltablue`
    - [x] focused GREEN for the narrowed small one-arg method preload shape
    - [x] focused object/JIT/OSR regression suite after narrowing
    - [x] refreshed inliner-on object-heavy pyperformance matrix after narrowing
    - [x] decide whether this stays as opt-in inliner capability or supports a selective tier policy later
- Next performance direction:
  - default-on object hot-path optimization, because the opt-in HIR-inliner preload slice did not produce broad throughput gains.
  - leading candidate: reduce refcount overhead for branch-only/immediately-consumed instance-field loads, or another similarly narrow state-access shape with focused HIR evidence.
- Baseline-tier state model slice:
  - [x] reproduce `test_jit_tiering` crash through the remote ARM entrypoint
  - [x] identify root cause: pending baseline-auto scheduled functions could fall through to optimized compile after baseline-auto was disabled
  - [x] add separate pending baseline tier state (`baseline_scheduled_funcs_`)
  - [x] keep active baseline tier state separate (`baseline_funcs_`)
  - [x] add focused tests for reset, pending unschedule, forced baseline, and promotion
  - [x] focused remote GREEN: `Ran 5 tests in 0.004s`, `OK`
  - [x] combined remote verification with the diagnostic repro script
  - [x] default object-heavy benchmark regression check
  - outcome: correctness/stability positive; no demonstrated throughput win, continue default hot-path performance work
- Tier-state quality closure:
  - [x] add unified `FunctionTierState` API fields for active tier, baseline scheduling, compile failures, runtime fallbacks, and invalidations
  - [x] connect runtime deopt fallback telemetry from `prepareForDeopt()` into per-function state
  - [x] connect type invalidation patching from type deopt patchers into per-function state
  - [x] distinguish `baseline_to_optimized` from generic optimized compilation
  - [x] make baseline-auto disable clear pending baseline state, installed `jitVectorcall`, and registered compilation units
  - [x] prevent `pause(deopt_all=True)` and paused calls from reactivating pending baseline state
  - [x] prevent `force_compile_baseline()` from silently reattaching already-compiled shared code as optimized
  - [x] remove stale CodeRuntime owner mappings when functions are destroyed, uncompiled, or deopted
  - [x] focused remote GREEN: `test_jit_tiering`, `Ran 14 tests in 2.101s`, `OK`
  - [x] broader remote guard: tiering + OSR + method-with-values suite, `Ran 26 tests in 5.330s`, `OK`
  - [x] maturity follow-up: owner-specific runtime fallback telemetry avoids
    clearing sibling owners when the observed runtime owner can be identified
  - [x] maturity follow-up remote guard:
    - focused adjacent tier-state group `Ran 8 tests in 0.518s`, `OK`
    - default ARM runtime `Ran 102 tests in 16.417s`, `OK (skipped=3)`
    - full `test_jit_tiering` `Ran 40 tests in 11.014s`, `OK`
  - outcome: feature/quality closure for tier-state MVP is materially stronger; no performance claim made in this phase
- Lookup-free tiny bool mutator retry:
  - [x] RED: tightened the state-mutator test to require `CallMethod == 0`, `LoadMethodCached + LoadMethod == 0`, and direct `StoreField` operations
  - [x] identify why the old simplifier-only design regressed: `LoadMethod` remained observable and could not be DCE'd
  - [x] move the narrow shape to builder-level `LOAD_ATTR_METHOD_WITH_VALUES` handling for tiny bool mutator `PyFunction` descriptors
  - [x] focused remote GREEN
  - [x] focused 23-test object/JIT/OSR regression suite
  - [x] object-heavy matrix
  - outcome: correctness-clean, small `go` signal, mixed/noise-sized broader matrix; continue looking for stronger default throughput gain
- State-helper admission retry:
  - [x] RED/GREEN for opt-in subscript-state helper admission
  - [x] reject broad attr-only admission with benchmark evidence
  - [x] run subscript-only matrix through the remote entrypoint
  - outcome: `11.37%` geomean speedup versus full eager `jitlist`, but still
    misses the target because `go` regresses `24.64%` and `richards` regresses
    `6.23%`
- Next selected candidate:
  - dynamic delayed helper promotion instead of static helper admission
  - goal: preserve no-backedge loop-heavy wins while selectively recovering hot
    object helpers after runtime evidence
  - first TDD target: a skipped no-backedge helper remains interpreted before
    its promotion threshold, then becomes compiled after enough calls, while
    compile failures/backoff prevent repeated blind promotion
- Deferred helper promotion status:
  - [x] focused RED/GREEN for stateful subscript-only deferred helper promotion
  - [x] adjacent ARM runtime verification through the remote entrypoint
  - [x] precise full `test_jit_tiering` verification through the remote
    entrypoint
  - [x] pyperformance wrapper TDD fix for explicit worker `CINDERX_DISABLE`
    propagation
  - [x] remote worker probe proving nojit disables JIT and autojit/jitlist can
    compile a probe function
  - [ ] resolve why the selected `--debug-single-value` pyperformance subset
    still shows near-zero JIT/no-JIT separation
  - [ ] only after the benchmark harness shows real JIT sensitivity, continue
    tuning policy thresholds or machine-code optimizations toward the 30%
    selected-workload target

- Attr-state deferred helper promotion refinement:
  - [x] focused RED/GREEN for attr-state helper deferral
  - [x] rerun attr-helper pyperformance matrix after remote recovery
  - [x] record matrix result in `findings.md`
  - [x] narrow attr-helper classification to avoid raytrace-like regressions
  - [x] validate refined classifier through focused remote tests
  - [x] rerun corrected pyperformance matrix with multi-threaded build
  - [x] test promotion-threshold variants for complex attr predicates
  - [x] test tiny-filter threshold variants with helper threshold 512
  - [x] confirm best tiny-filter candidates with higher sample count
  - [x] collect function-level go telemetry for eager baseline vs deferred policy
  - [x] scout lower helper-promotion thresholds for go recovery
  - [x] TDD the warmed method-with-values specialized Python-call lowering gap
  - [x] patch and verify the narrow HIRBuilder fast path if RED confirms it
  - [x] rerun selected pyperformance matrix after call-shape fix
  - [x] TDD remaining `CALL_KW_PY` method-with-values gaps in `go`
  - [x] keep/refine/revert the attr widening based on matrix evidence
  - [x] collect post-KW HIR/compile telemetry for remaining generic method
    calls and non-call costs in `Board.move`, `Square.move`, `Board.useful`,
    and `UCTNode.play`
  - [x] test and reject deopt-only miss fallback for delayed
    method-with-values after benchmark evidence showed a direct slowdown
  - [x] test selective method-value-only HIR inliner as an opt-in candidate and
    reject default enablement after the selected matrix regressed geomean by
    `1.97%`
  - [ ] diagnose why method-value inlining is not throughput-positive
  - [ ] rank the next production optimization candidate from post-KW and
    post-inliner telemetry instead of continuing blind threshold tuning

- Method-descriptor FASTCALL generalization phase:
  - [x] Add a RED LIR regression for inherited exact method descriptors with
    zero explicit arguments, starting with `list.pop()`.
  - [x] Add a gated vectorcall-shaped helper for additional
    `PyMethodDescr_Type` `METH_FASTCALL` / `METH_FASTCALL|METH_KEYWORDS`
    shapes while preserving the existing `list.pop(0)` fast path.
  - [x] Verify focused ARM RED/GREEN through
    `/root/work/incoming/remote_update_build_test.sh` with
    `CINDERX_BUILD_JOBS=8 PARALLEL=8`.
  - [x] Run runner propagation and selected pyperformance matrix; keep
    default-on only if the disabled-vs-enabled matrix is positive with no
    `>=5%` row regressions.
  - [x] Matrix was negative (`geomean_speedup_pct = -0.7497%`), so keep the
    feature gated/off by default.

- Inline list iterator next phase:
  - [x] Add a RED LIR regression proving list iterator loops do not currently
    contain an inline `PyListIter_Type` fast-path check.
  - [x] Implement a gated LIR hot path for exact list iterators while keeping
    `JITRT_InvokeIterNext` for fallback/exhaustion.
  - [x] Verify focused LIR shape and list mutation/clear semantics through the
    ARM entrypoint.
  - [x] Replace the initial `Py_IncRef` helper call with inline `MakeIncref`
    and re-verify focused tests.
  - [x] Run two disabled-vs-enabled matrices; both were negative, and
    `comprehensions` regressed beyond `5%`.
  - [x] Keep `PYTHONJITINLINELISTITERNEXT` gated/off by default.

- Existing instance-value store phase:
  - [x] Add RED coverage proving existing `STORE_ATTR_INSTANCE_VALUE` still
    lowers through cached store machinery before the candidate.
  - [x] Implement a gated direct `StoreField` lowering for non-empty
    split-dict inline-value slots, with empty-slot fallback to preserve
    attribute insertion-order semantics.
  - [x] Verify focused ARM RED/GREEN through the remote entrypoint with
    `CINDERX_BUILD_JOBS=8 PARALLEL=8`.
  - [x] Run runner propagation and selected pyperformance matrix.
  - [x] Matrix was negative (`geomean_speedup_pct = -3.6571%`) with
    `raytrace` and `richards` over the `5%` regression gate, so keep
    `PYTHONJITSTOREATTRINSTANCEVALUEEXISTING` gated/off by default.
  - [x] Run final focused gated/off verification after switching the default.

- Deferred-helper code-shape phase:
  - [x] Add RED/GREEN coverage proving `precompile_all()` must not compile
    deferred helpers before the helper-promotion threshold.
  - [x] Keep early registration, but filter `precompile_all` attempts for
    deferred helpers.
  - [x] Reject the dedicated deferred-helper vectorcall after matrix evidence.
  - [x] Reject removing early registration after matrix evidence.
  - [x] Run current precompile-filter matrix and record the remaining `go`
    regression.
  - [x] Collect `go` function-state diagnostics with and without
    `PYTHONJITADMITSTATEHELPERS`.
  - [x] Test and reject skipping call-containing state helpers after the
    selected matrix made `go` regress by roughly `20%`.
  - [x] Revert the rejected skip classifier.
  - [x] Design selective admission for call-containing state helpers that need
    registration and compilation rather than long deferred interpretation.
  - [x] Add focused RED coverage for that admission rule before
    implementation.
  - [x] Re-run adjacent ARM runtime and selected pyperformance matrix through
    the remote entrypoint.
  - [ ] Inspect compiled HIR/LIR quality for admitted `go` helpers, especially
    recursive method calls and state attribute accesses in `Square.find` and
    dispatch paths in `Board.move`/`UCTNode.select`.
