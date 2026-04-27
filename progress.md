# Progress Log

## Session: 2026-02-25

### Phase 1: Brainstorming & Requirements
- **Status:** in_progress
- **Started:** 2026-02-25
- Actions taken:
  - Loaded required skills:
    - `using-superpowers`
    - `planning-with-files`
    - `brainstorming`
    - `writing-plans`
    - `test-driven-development`
    - `verification-before-completion`
  - Ran planning session catchup script from installed path.
  - Reviewed current `task_plan.md`, `progress.md`, and latest `findings.md` sections to recover state.
  - Began new task plan for `ENABLE_LIGHTWEIGHT_FRAMES` integration with LTO/PGO/adaptive static.
- Files created/modified:
  - task_plan.md (updated for this task)
  - progress.md (this file)

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| N/A | N/A | N/A | N/A | pending |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-02-25 | `session-catchup.py` missing at default path | 1 | Used installed planning-with-files path under `.codex/planning-with-files/.codex/skills/` |

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Phase 1 (brainstorming) |
| Where am I going? | Plan -> TDD -> implementation -> remote verification |
| What's the goal? | Enable LIGHTWEIGHT_FRAMES on ARM 3.14 with LTO/PGO/adaptive static compatibility |
| What have I learned? | Existing project already has adaptive static + LTO integration; lightweight frames currently not enabled for 3.14 in setup defaults |
| What have I done? | Loaded skills, initialized planning docs, started requirement clarification |

## Decision Update (2026-02-25)
- Priority: `ENABLE_LIGHTWEIGHT_FRAMES` must land and validate on Python 3.14 first.
- Rollout order: 3.14-first; any 3.15 default enablement deferred to next phase after 3.14 verification.

## Session Update: 2026-02-26

### Phase status
- Phase 1 (brainstorming): complete
- Phase 2 (writing plan): complete
- Phase 3 (TDD): complete
- Phase 4 (integration): complete
- Phase 5 (verification): complete
- Phase 6 (delivery): in_progress

### Code changes completed
- Added `should_enable_lightweight_frames()` in `setup.py` with Stage-A policy:
  - default on for OSS `3.14` on `aarch64/arm64`
  - default off for `3.15` (env override still possible)
  - preserve meta `3.12` behavior
- Added `_cinderx.is_lightweight_frames_enabled()` and exported `cinderx.is_lightweight_frames_enabled()`.
- Added/extended tests:
  - `tests/test_setup_lightweight_frames.py`
  - `tests/test_cinderx_lightweight_frames_api.py`
  - `cinderx/PythonLib/test_cinderx/test_oss_quick.py`
- Added 3.14 compatibility guards for missing 3.15-only `PyUnstable_*JITExecutable*` APIs:
  - `cinderx/Common/py-portability.h`
  - `cinderx/Jit/frame.cpp`
  - `cinderx/Jit/lir/generator.cpp`
- Added PGO workload retry helper in `setup.py`:
  - `run_pgo_workload()` retries once on `subprocess.CalledProcessError`
  - used by `BuildCommand._run_with_pgo()`
- Added test for retry behavior:
  - `tests/test_setup_pgo_workload_retries.py`

### Verification run summary (remote only)
- Entry point: `ssh root@124.70.162.35`
- Setup and API unit tests: pass
- `CINDERX_ENABLE_PGO=0 CINDERX_ENABLE_LTO=1 python setup.py install`: pass
- `CINDERX_ENABLE_PGO=1 CINDERX_ENABLE_LTO=1 python setup.py install`: pass
- Runtime probes after installs:
  - `cinderx.is_adaptive_static_python_enabled() -> True`
  - `cinderx.is_lightweight_frames_enabled() -> True`
- Smoke:
  - `python cinderx/PythonLib/test_cinderx/test_oss_quick.py` -> `Ran 3 tests ... OK`

## Session Update: 2026-03-15

### Task status
- Issue31 closeout: completed
- Scope:
  - no new functional code changes
  - ARM staging rebuild + closeout revalidation
  - sync `task_plan.md`, `notes.md`, and `findings.md` to review-ready state

### Remote verification summary
- ARM staging workdir:
  - `/root/work/frame-issue31-closeout-20260315`
- Import path used for staging validation:
  - `PYTHONPATH=scratch/lib.linux-aarch64-cpython-314:cinderx/PythonLib`
- Targeted regressions:
  - `ArmRuntimeTests.test_specialized_numeric_leaf_mixed_types_avoid_deopts`: pass
  - `ArmRuntimeTests.test_plain_instance_other_arg_guard_eliminates_cached_attr_loads`: pass
  - `ArmRuntimeTests.test_other_arg_inference_skips_helper_method_shapes`: pass

### Performance / behavior summary
- Issue31 A/B revalidation:
  - `PointOther.dist`: `0.295552274096s`
  - `PointRhs.dist`: `0.315386445029s`
  - `PointOther` mixed probe: `0.246739777969s`
  - `PointRhs` mixed probe: `0.276117506088s`
- Raytrace direct benchmark:
  - `compile_strategy=all`
  - `prewarm_runs=1`
  - `samples=5`
  - median wall: `0.5452457539504394s`
- Issue31 regression sites remain cleared:
  - `Vector.dot`: `0`
  - `Point.__sub__`: `0`
  - `Sphere.intersectionTime`: `0`
- Known remaining follow-ups:
  - `Vector.scale`
  - `addColours`

### Delivery state
- Issue31 is now documented as review-ready.
- Residual raytrace deopts outside the main issue31 regression are explicitly kept out of scope for this closeout.

## Session Update: 2026-03-15 (raytrace follow-up)

### Task status
- Raytrace follow-up optimization: completed for this round
- Scope:
  - reduce remaining `LOAD_ATTR_METHOD_WITH_VALUES` deopts after issue31 closeout
  - keep issue31 protections intact
  - add a targeted regression and revalidate on ARM staging

### Code changes completed
- Narrowed `LOAD_ATTR_METHOD_WITH_VALUES` lowering in `cinderx/Jit/hir/builder.cpp`:
  - keep the fast path for stable exact receivers
  - also keep it for true `self` receivers when the descriptor owner type has no subclasses
  - fall back to `LoadMethod` for polymorphic unpacked-local receiver sites
- Added ARM runtime regression:
  - `test_polymorphic_method_load_avoids_method_with_values_deopts`

### Remote verification summary
- ARM staging workdir:
  - `/root/work/frame-issue31-closeout-20260315`
- Targeted regressions:
  - `test_polymorphic_method_load_avoids_method_with_values_deopts`: pass
  - `test_specialized_numeric_leaf_mixed_types_avoid_deopts`: pass
  - `test_plain_instance_other_arg_guard_eliminates_cached_attr_loads`: pass
  - `test_other_arg_inference_skips_helper_method_shapes`: pass

### Performance / behavior summary
- Raytrace direct benchmark:
  - previous median: `0.5452457539504394s`
  - current median: `0.5257585040526465s`
  - previous total deopts: `257510`
  - current total deopts: `130005`
- Removed remaining method-load deopt family:
  - `Scene.rayColour`
  - `Scene._lightIsVisible`
  - `SimpleSurface.colourAt` (`LOAD_ATTR_METHOD_WITH_VALUES`)
- Next likely targets:
  - `Canvas.plot`
  - `Vector.scale`
  - `addColours`
  - `SimpleSurface.colourAt` instance-value path

## Session Update: 2026-03-15 (raytrace follow-up 2)

### Task status
- Raytrace follow-up optimization: completed for this round
- Scope:
  - reduce `Canvas.plot`, `Vector.scale`, and `addColours` deopts
  - preserve the earlier method-load fix
  - validate on ARM staging and keep only throughput-positive changes

### Code changes completed
- Narrowed no-backedge float exact guards in `cinderx/Jit/hir/builder.cpp`:
  - keep them only for loop-hot code or methods with inferred exact non-self args
- Narrowed builtin `min/max` float specialization in `cinderx/Jit/hir/simplify.cpp`:
  - skip the float fast path for obvious integral clamp shapes with exact long operands
- Added runtime regressions:
  - `test_self_only_float_leaf_mixed_factor_avoids_deopts`
  - `test_builtin_min_max_int_clamp_shape_avoids_float_guard_deopts`

### Remote verification summary
- ARM staging workdir:
  - `/root/work/frame-issue31-closeout-20260315`
- Targeted regressions:
  - `test_polymorphic_method_load_avoids_method_with_values_deopts`: pass
  - `test_self_only_float_leaf_mixed_factor_avoids_deopts`: pass
  - `test_builtin_min_max_int_clamp_shape_avoids_float_guard_deopts`: pass
  - issue31 guard tests: pass

### Performance / behavior summary
- Raytrace direct benchmark:
  - previous median: `0.5452457539504394s`
  - current median: `0.5367581009631976s`
  - previous total deopts: `257510`
  - current total deopts: `19285`
- Removed deopt families:
  - `Canvas.plot`
  - `Vector.scale`
  - `addColours`
- Remaining dominant deopt:
  - `SimpleSurface.colourAt` `LOAD_ATTR_INSTANCE_VALUE`

### Discarded attempt
- Tried disabling `LOAD_ATTR_INSTANCE_VALUE` for non-leaf `self` receivers.
- That removed the last deopt bucket but regressed raytrace to about `1.92s`, so it was not kept.

## Session Update: 2026-04-27 (tiering fallback telemetry)

### Task status
- Extended the tiering promotion/fallback closure with a deopt-all fallback
  telemetry slice.
- Scope:
  - record why `jit.disable(deopt_all=True)` moves a compiled function back to
    interpreter tier
  - keep `force_uncompile()` fallback telemetry intact
  - thread explicit deopt reasons through the shared deopt implementation

### TDD evidence
- Added `test_disable_deopt_all_records_fallback_transition`.
- ARM red run before implementation:
  - actual output was only `['interp']`
  - expected fallback event was missing

### Verification summary
- ARM staging workdir:
  - `/root/work/cinderx-richards-fresh-20260414`
- ARM build:
  - `CINDERX_DISABLE=1 /root/venv-cinderx314/bin/python -m build --wheel -n`
  - result: wheel built successfully
- ARM targeted tests:
  - `cd cinderx/PythonLib && /root/venv-cinderx314/bin/python -m unittest -v test_cinderx.test_jit_tiering`
  - result: `Ran 11 tests in 0.383s`, `OK`
- Direct probe:
  - final tier: `interp`
  - event: `('baseline', 'interp', 'disable_deopt_all')`
- Multi-function direct probe:
  - final tiers: `interp`, `interp`
  - events recorded for both `helper_a` and `helper_b`

## Session Update: 2026-04-27 (unified tier info state)

### Task status
- Extended the tier-state API so `get_function_tier_info()` reports deopted
  state and the last tier transition.
- Scope:
  - preserve the existing clearable event stream
  - add a stable per-function state surface for active tier, cached tiers,
    deopt state, and last fallback reason

### TDD evidence
- Added `test_function_tier_info_reports_deopt_state`.
- ARM red run before implementation:
  - failed with `KeyError: 'is_deopted'`
  - old tier info only exposed `active_tier`, `has_baseline`, and
    `has_optimized`

### Verification summary
- ARM staging workdir:
  - `/root/work/cinderx-richards-fresh-20260414`
- ARM build:
  - `CINDERX_DISABLE=1 /root/venv-cinderx314/bin/python -m build --wheel -n`
  - result: wheel built successfully
- ARM targeted tests:
  - `cd cinderx/PythonLib && /root/venv-cinderx314/bin/python -m unittest -v test_cinderx.test_jit_tiering`
  - result: `Ran 12 tests in 0.420s`, `OK`
- Direct probes:
  - `disable(deopt_all=True)` reports `is_deopted=True` and
    `last_transition.reason=disable_deopt_all`
  - clearing tiering events before reading tier info still preserves the last
    transition in the state surface
  - replacing `helper.__code__` reports `is_deopted=True` and
    `last_transition.reason=function_modified`

## Session Update: 2026-04-27 (dependency invalidation telemetry)

### Task status
- Extended tiering stats with dependency invalidation/check telemetry.
- Scope:
  - observe type dependency patcher checks from `Context::notifyTypeModified()`
  - expose whether each patcher patched or skipped
  - keep runtime compile/fallback policy unchanged

### TDD evidence
- Added `test_tiering_stats_records_type_dependency_invalidations`.
- ARM red run before implementation:
  - output: `['True', 'False', 'False', 'True']`
  - interpretation: `Point.dist` generated real `DeoptPatchpoint` entries, but
    tiering stats did not yet expose invalidation/check events.

### Verification summary
- ARM staging workdir:
  - `/root/work/cinderx-richards-fresh-20260414`
- ARM build:
  - `CINDERX_DISABLE=1 /root/venv-cinderx314/bin/python -m build --wheel -n`
  - result: wheel built successfully
- ARM targeted test:
  - `test_tiering_stats_records_type_dependency_invalidations`: pass
- ARM targeted suite:
  - `cd cinderx/PythonLib && /root/venv-cinderx314/bin/python -m unittest -v test_cinderx.test_jit_tiering`
  - result: `Ran 13 tests in 0.477s`, `OK`
- Direct probe:
  - `Point.dist` compiled with `DeoptPatchpoint=6`
  - `PyType_Modified(Point)` emitted six `split_dict` invalidation/check events
  - each event reported `action=skip`, `reason=type_modified`

## Session Update: 2026-04-27 (tier state / policy closeout)

### Task status
- Connected dependency invalidation outcomes into stable per-function tier state.
- Consolidated active tier, last transition, dependency state, baseline call
  counts, and promotion policy counters into `TierState`.
- Added optimized compile-failure cooldown/backoff so repeated promotion
  failures stop retrying on every baseline call.
- Fixed a review-found owner identity bug where dependency patch state could be
  assigned by qualname to the wrong function.
- Fixed the pyperformance subset matrix summarizer for pyperformance 1.14
  debug-single-value JSON.

### TDD / review evidence
- Owner identity regression:
  - old behavior attached `action=patch` dependency state to the second
    same-qualname function instead of the compiled owner
  - new regression:
    `test_dependency_invalidation_state_uses_compiled_owner_identity`
- Pyperformance parser regression:
  - old `run_pyperf_subset.sh` produced empty `benchmarks: []`
  - new unit coverage:
    `tests.test_summarize_pyperf_subset`
- Subagent review:
  - checked all type deopt patcher constructor call sites
  - no P0/P1/P2 issues found

### Verification summary
- Local helper tests:
  - `python -m unittest -v tests.test_arm_remote_update_build_test tests.test_summarize_pyperf_subset`
  - result: `Ran 20 tests`, `OK`
- ARM build:
  - `CINDERX_DISABLE=1 /root/venv-cinderx314/bin/python -m build --wheel -n`
  - result: wheel built successfully
- ARM tiering suite with scratch PYTHONPATH:
  - `PYTHONPATH=scratch/lib.linux-aarch64-cpython-314:cinderx/PythonLib /root/venv-cinderx314/bin/python -m unittest -v test_cinderx.test_jit_tiering`
  - result: `Ran 16 tests in 1.769s`, `OK`
- Pyperformance matrix after summarizer fix:
  - `richards`, 9 samples: median `0.12229131999993115s`
  - `go`, 9 samples: median `0.27292389099966385s`
  - `deltablue`, 7 samples: median `0.04078413099887257s`
  - `raytrace`, 7 samples: median `0.5151431289996253s`

### Performance evidence
- Promotion failure policy microbenchmark:
  - baseline `94fb6b8f`: median `0.0002002040000661509s`
  - current ownerfix build: median `0.00004339299994171597s`
  - repeated compile-fail decisions: `553 -> 28`
  - cooldown decisions: `0 -> 525`
- Interpretation:
  - the real speedup is in the tier policy failure path, not claimed as a broad
    pyperformance win
  - pyperformance matrix is the guardrail that the tier-state/policy work did
    not destabilize object-heavy workloads

## Session Update: 2026-04-27 (promotion failure suppression)

### Task status
- Added a failure-budget state to optimized promotion policy.
- Repeated optimized compile failures now enter
  `optimized_compile_suppressed` instead of cycling through cooldown forever.
- `jit_unsuppress(func)` now clears optimized promotion failure/cooldown/
  suppression state so an explicitly unsuppressed function can promote again.

### TDD evidence
- Added `test_repeated_optimized_promotion_failures_are_suppressed`.
- ARM red run before implementation:
  - actual:
    `['4', 'False', 'baseline', '4', 'None', '35', 'optimized_compile_cooldown']`
  - expected:
    `['3', 'True', 'baseline', '3', 'True', '0', 'optimized_compile_suppressed']`
- Added `test_jit_unsuppress_clears_optimized_promotion_suppression`.
- ARM red run before implementation:
  - actual:
    `['None', 'baseline', 'None', '4', '34', 'baseline']`
  - expected:
    `['True', 'baseline', 'False', '0', '0', 'optimized']`

### Verification summary
- ARM build:
  - `CINDERX_DISABLE=1 /root/venv-cinderx314/bin/python -m build --wheel -n`
  - result: wheel built successfully
- ARM targeted tests:
  - `test_repeated_optimized_promotion_failures_are_suppressed`: pass
  - `test_jit_unsuppress_clears_optimized_promotion_suppression`: pass
- ARM full tiering suite:
  - `PYTHONPATH=scratch/lib.linux-aarch64-cpython-314:cinderx/PythonLib /root/venv-cinderx314/bin/python -m unittest -v test_cinderx.test_jit_tiering`
  - result: `Ran 18 tests in 1.843s`, `OK`

### Performance / policy evidence
- Compared against previous ownerfix microbenchmark:
  - previous fail decisions: `28`
  - current fail decisions: `21`
  - previous cooldown decisions: `525`
  - current cooldown decisions: `168`
  - current suppressed decisions: `364`
- Median stayed effectively flat in this tiny micro path:
  - previous: `0.00004339299994171597s`
  - current: `0.000043993000872433186s`
- Interpretation:
  - this slice is a policy correctness / wasted retry avoidance improvement
  - it reduces repeated failed compile attempts but does not claim a new broad
    pyperformance speedup

### Errors / recoveries
- A first remote microbenchmark compare command produced valid JSON but exited
  non-zero because of a malformed heredoc terminator.
- A second one-liner attempt was parsed by local PowerShell.
- Final verification used a PowerShell here-string piped to remote Python and
  exited cleanly.
- Subagent review found a P2 where `forgetCode()`, `clearCache()`, and
  `removeCompiledFunc()` cleared suppressed/cooldown but not failure count.
- The fix now routes all promotion failure-budget resets through
  `resetOptimizedPromotionFailureState(TierState&)`.
- First ARM rebuild after that fix failed because the helper originally shared
  the same name as `Context::clearOptimizedPromotionFailures(func)`, causing
  overload resolution to choose the member function with a `TierState` argument.
- Renamed the helper to `resetOptimizedPromotionFailureState()`; ARM rebuild and
  tiering suite then passed.

