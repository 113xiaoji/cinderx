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

## Session Update: 2026-04-29 object-heavy performance slice

### Starting state
- User asked to continue with full performance optimization.
- Active branch: `bench-cur-7c361dce`.
- Local status at slice start:
  - branch is ahead of `origin/bench-cur-7c361dce`
  - existing uncommitted diff in `cinderx/PythonLib/test_cinderx/test_jit_tiering.py`
- Planning files were re-read before making changes.
- Added the active performance-slice checklist to `task_plan.md`.

### Current approach
- Use only the remote ARM entrypoint for validation:
  - `/root/work/incoming/remote_update_build_test.sh`
- Primary benchmark matrix:
  - `richards`
  - `go`
  - `deltablue`
  - `raytrace`
- First local observations:
  - `LOAD_ATTR_METHOD_WITH_VALUES` has a builtin-list descriptor relaxation in `builder.cpp`.
  - `TO_BOOL_BOOL` still lowers to a permanent bool guard in this branch.
  - Existing MDP-specific rewrites are guarded by env toggles and already have focused experiment tests.

### Remote blocker found
- First remote matrix attempt failed before benchmark during `_cinderx` import.
- Error:
  - `undefined symbol: _ZN3jit16TypeDeoptPatcherC1E11BorrowedRefI11_typeobjectE`
- Root cause:
  - stale remote incremental object for `type_deopt_patchers.cpp`
  - source and build metadata were present, but `libjit.a` still contained a stale constructor signature
- Action:
  - added `CLEAN_BUILD=1` support to `scripts/arm/remote_update_build_test.sh`
  - next run will use the same standard entrypoint with clean build artifacts

### 2026-04-29 update: pyperformance worker startup OSR crash
- RED proof through the standard remote ARM entrypoint:
  - test:
    - `ArmRuntimeTests.test_phase1_loop_osr_skips_pyperformance_startup_imports`
  - result before the production fix:
    - failed with subprocess return code `-11`
  - failure shape:
    - pyperformance-style startup hook enabled JIT while importing stdlib modules
    - same-activation hot-loop OSR attempted to compile an import-time `typing.py` loop
    - crash stack reached `_PyJIT_TryHotLoopOSR` via `compilePreloaderImpl`
- Production fix:
  - phase-1 same-activation hot-loop OSR now only attempts top-level `__main__` functions
  - import-time library/module loops are skipped for this MVP surface
- GREEN proof through the same remote ARM entrypoint:
  - command used `EXTRA_TEST_CMD='PYTHONPATH=scratch/lib.linux-aarch64-cpython-314:cinderx/PythonLib /root/venv-cinderx314/bin/python cinderx/PythonLib/test_cinderx/test_arm_runtime.py ArmRuntimeTests.test_phase1_loop_osr_skips_pyperformance_startup_imports -v'`
  - result:
    - `Ran 1 test`
    - `OK`
- Next:
  - re-run the existing positive OSR tests to ensure the `__main__` gate did not disable the intended benchmark/user-code OSR path
  - then retry the pyperformance worker and object-workload matrix

### 2026-04-29 update: positive OSR regression check
- Repackaged and reran focused OSR regressions through the same remote ARM entrypoint.
- Tests:
  - `ArmRuntimeTests.test_phase1_once_call_hot_loop_enters_jit_same_activation`
  - `ArmRuntimeTests.test_phase1_loop_osr_skips_active_exception_shape`
- Result:
  - `Ran 2 tests`
  - `OK`
- Interpretation:
  - the new `__main__` gate preserves the intended same-activation OSR path for top-level benchmark/user code
  - active-exception-shape protection still holds
- Next:
  - rerun pyperformance worker setup and the `richards,go,deltablue,raytrace` object matrix

### 2026-04-29 update: Richards method-loop OSR crash
- Matrix retry reached true pyperformance worker execution and then crashed in `bm_richards`.
- Diagnostic stack:
  - Python stack:
    - `run_benchmark.py:364 in schedule`
    - `run_benchmark.py:369 in schedule`
    - `run_benchmark.py:408 in run`
  - C stack:
    - `_Py_HandlePending`
    - generated code `<unknown>`
- Root-cause evidence:
  - `schedule()` OSR metadata mapped live local `t` to ARM64 `X20`.
  - phase-0/test-entry OSR adapter only restores Python locals and uses a best-effort `X19/X20/X21` tstate seed.
  - method/attr-heavy loops can need internal pinned state such as `tstate` around periodic-task checks; overwriting that register with a Python local can crash in generated code.
- RED proof:
  - added `ArmRuntimeTests.test_phase1_loop_osr_richards_method_loop_does_not_crash`
  - pre-fix remote result:
    - failed with subprocess return code `-11`
    - same `schedule()` / `_Py_HandlePending` stack
- Production fix:
  - added `supportsPhase1HotLoopOSR()`
  - phase-1 same-activation OSR now only enters leaf-loop shapes
  - call/method/attr/deopt-patchpoint shapes fall back instead of using the fragile adapter
- GREEN proof:
  - focused Richards regression:
    - `Ran 1 test`
    - `OK`
  - combined phase-1 OSR suite:
    - `test_phase1_once_call_hot_loop_enters_jit_same_activation`: ok
    - `test_phase1_loop_osr_skips_active_exception_shape`: ok
    - `test_phase1_loop_osr_skips_pyperformance_startup_imports`: ok
    - `test_phase1_loop_osr_richards_method_loop_does_not_crash`: ok
    - `Ran 4 tests`
    - `OK`
- Next:
  - rerun the `richards,go,deltablue,raytrace` matrix after both OSR stability gates

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

## Session Update: 2026-04-05 (performance-go analysis)

### Task status
- Scope:
  - read-only analysis of pyperformance `go`
  - prioritize root-cause clarity and repair design over immediate code changes
  - keep unified remote verification as the target validation surface
- Status:
  - analysis complete
  - fresh remote benchmark rerun completed
  - focused issue60 safety regression reproduced a deterministic compiler crash

### Actions completed
- Loaded and followed the requested workflow skills:
  - `using-superpowers`
  - `planning-with-files`
  - `brainstorming`
  - `writing-plans`
  - `test-driven-development`
  - `verification-before-completion`
- Read current planning files and recovered prior branch context.
- Read:
  - `cinderx/AGENTS.md`
  - `plans/2026-03-23-issue60-go-method-values-fastpath/*`
  - `cinderx/Jit/hir/builder.cpp`
  - `cinderx/Jit/hir/builder.h`
  - `cinderx/Jit/hir/inliner.cpp`
  - `cinderx/Jit/hir/guarded_load_elimination.cpp`
  - `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
  - `scripts/push_to_arm.ps1`
  - `scripts/arm/remote_update_build_test.sh`
  - `scripts/arm/run_pyperf_subset.sh`
- Dispatched child-agent exploration lanes for:
  - issue60/history + remote-entry context
  - JIT/builder/inliner code-path context

### Conclusions captured
- The main `go` regression shape is still the attr-derived monomorphic receiver
  path (`self.reference.find(update)`-style), where losing the
  method-with-values fast path removes the only inliner-visible `VectorCall`.
- Broad static heuristic reopenings were already shown to be unsafe.
- The best next-step fix remains profile-driven, with any further widening
  needing new regression tests first.
- Fresh ARM data now also shows:
  - benchmark gate for `go` completes successfully with JIT active
  - the focused `attr_derived_polymorphic` regression process segfaults after
    the test itself reports `ok`
  - the crash stack points into `outputTypeWithRecursiveCoroHint ->
    reflowTypes -> SSAify::Run`, so compiler stability is currently a more
    immediate blocker than raw benchmark throughput
  - a follow-up rerun with `PYTHONJITDEBUG=1` identifies the final compile
    target before the crash as `_colorize:__annotate__`, not `Holder.run`
  - current strongest root-cause hypothesis is a `pass.cpp` case-grouping bug
    that routes ordinary opcodes like `LoadGlobal` through send-specific
    `static_cast<const Send&>(instr)` logic
  - direct `force_compile(_colorize.can_colorize.__annotate__)` reproduces the
    same crash
  - the most likely immediate bug is a `pass.cpp` opcode-case grouping bug that
    reinterprets non-`Send` instructions as `Send`
  - the most plausible timing trigger is the outer unittest process:
    - `ArmRuntimeTests.tearDown()` restores `compile_after_n_calls`
    - on this remote setup the saved value is `None`
    - `tearDown()` therefore calls `compile_after_n_calls(0)`
    - `pyjit.cpp` responds by scheduling all pre-existing functions for future
      compilation
    - the crash then lands during unittest summary/shutdown when one of those
      scheduled functions next executes

### Verification attempt
- Fresh remote connectivity check:
  - `ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 root@124.70.162.35 "echo arm-ok && uname -m && test -x /opt/python-3.14/bin/python3.14 && echo py314-ok || echo py314-missing && command -v rsync || echo rsync-missing"`
  - result: reachable, `aarch64`, `py314-ok`, `/usr/bin/rsync`
- Unified remote benchmark rerun:
  - entrypoint:
    - manual archive upload + `scripts/arm/remote_update_build_test.sh`
  - workdir:
    - `/root/work/cinderx-go-analysis-20260405`
  - driver venv:
    - `/root/venv-cinderx314-go-analysis-20260405`
  - settings:
    - `BENCH=go`
    - `SKIP_ARM_RUNTIME_VALIDATION=1`
    - `CINDERX_ENABLE_SPECIALIZED_OPCODES=1`
  - result:
    - `go_jitlist_20260405_084805.json`: `0.24736241299990525 s`
    - `go_autojit50_20260405_084805.json`: `0.2466943160000028 s`
    - compile summary: `main_compile_count=34`, `total_compile_count=34`
    - worker probe: `jit_enabled=true`
- Unified remote focused safety rerun:
  - settings:
    - `SKIP_PYPERF=1`
    - `EXTRA_TEST_CMD='PYTHONFAULTHANDLER=1 python -m unittest ... -k attr_derived_polymorphic -v'`
  - test status:
    - `test_attr_derived_polymorphic_method_load_avoids_method_with_values_deopts`: `ok`
  - process result:
    - immediate post-test `SIGSEGV`
    - stack includes:
      - `_cinderx.so`
      - `outputTypeWithRecursiveCoroHint`
      - `reflowTypes`
      - `SSAify::Run`
- Additional direct repros:
  - default outer harness state:
    - `jit_enabled = True`
    - `compile_after = None`
  - outer harness with `PYTHONJITAUTO=1000000`:
    - focused unittest passes cleanly
  - direct repro:
    - `force_compile(_colorize.can_colorize.__annotate__)`
    - same native crash in `outputTypeWithRecursiveCoroHint`
- Isolation follow-up on the same remote workspace:
  - custom one-test harness with outer `compile_after_n_calls(1000000)`:
    - `Ran 1 test ... OK`
    - no segfault
  - direct failing `unittest discover` rerun with JIT log:
    - still segfaults after the unittest summary
    - JIT log shows incidental harness compiles in `unittest.*`
    - last compile started before the crash:
      - `_colorize:__annotate__`
  - updated read:
    - the crash depends on incidental outer-harness auto-jit work
    - not just on the attr-derived polymorphic regression body itself

### Files created/modified
- `docs/plans/2026-04-05-go-jit-analysis-design.md`
- `docs/plans/2026-04-05-go-jit-analysis-plan.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

## Session Update: 2026-04-05 (post-fix targeted verification)

### Code changes completed
- `cinderx/Jit/hir/pass.cpp`
  - split `Opcode::kSend` out of the mixed object-returning opcode cluster
  - restore the non-`Send` neighbors to `return TObject`
  - add `JIT_DCHECK(instr.IsSend(), ...)`
- `cinderx/Jit/hir/annotation_index.cpp`
  - stop eager `PyFunction_GetAnnotations()` when only
    `specialized_opcodes` is enabled
- `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
  - add `test_force_compile_annotation_thunk_does_not_crash`
  - add `test_specialized_opcodes_do_not_eagerly_execute_annotation_thunks`

### Remote verification summary
- Source sync:
  - switched from `git archive HEAD` to a working-tree snapshot tar so the
    remote build includes the uncommitted local fix and regression
- Unified remote entrypoint:
  - `scripts/arm/remote_update_build_test.sh`
- Targeted custom runner results:
  - `test_force_compile_annotation_thunk_does_not_crash`: pass
  - `test_attr_derived_polymorphic_method_load_avoids_method_with_values_deopts`: pass
  - summary:
    - `Ran 2 tests in 0.131s`
    - `OK`
- Additional isolated remote checks:
  - `test_attr_derived_polymorphic_method_load_avoids_method_with_values_deopts`
    - `Ran 1 test in 0.206s`
    - `OK`
  - `test_specialized_opcodes_do_not_eagerly_execute_annotation_thunks`
    - `Ran 1 test in 0.315s`
    - `OK`

### Remaining blocker
- The pyperformance harness syntax issue in
  `scripts/arm/remote_update_build_test.sh` was fixed locally and the
  benchmark-only rerun now completes.
- Fresh benchmark summary on the fixed working-tree snapshot:
  - `go_jitlist_20260405_181404.json`: `0.5156086859933566 s`
  - `go_autojit50_20260405_181404.json`: `0.5089590209972812 s`
  - compile summary:
    - `main_compile_count = 34`
    - `total_compile_count = 34`
  - worker probe:
    - `jit_enabled = true`
- Residual caution:
  - this benchmark run happened under higher host load than the earlier
  single-benchmark sample, so it is valid as a fresh gate result but not yet
  a clean A/B measurement for claiming a performance win or loss.

## Session Update: 2026-04-05 (same-host go A/B)

### Benchmark comparison
- Method:
  - same ARM host
  - same unified remote entrypoint
  - separate baseline/fixed workdirs
  - same benchmark and flags
- Baseline `HEAD`:
  - `go_jitlist_20260405_193137.json`: `0.24918644900026266 s`
  - `go_autojit50_20260405_193137.json`: `0.4742307880005683 s`
  - `main_compile_count = 34`
- Fixed working tree:
  - `go_jitlist_20260405_194714.json`: `0.25993193100293865 s`
  - `go_autojit50_20260405_194714.json`: `0.25297167700045975 s`
  - `main_compile_count = 34`

### Readout
- jitlist moved slightly slower in this single-sample A/B
- autojit50 moved much faster in this single-sample A/B
- because the baseline autojit run reported higher runnable-thread pressure,
  this is strong directional evidence, not yet a publishable precise speedup
- follow-up direct `bm_go` probing was planned but paused when the ARM host
  started timing out on SSH again

## Session Update: 2026-04-06 (requested subset sweep)

### Subset result
- Ran baseline vs fixed on the requested subset with `SAMPLES=3`
- First-pass result:
  - only `fannkuch` crossed the `5%` regression threshold
  - observed signal: about `+7.59%`
- Focused `fannkuch` rerun:
  - baseline jitlist: `0.4893510160000005 s`
  - fixed jitlist: `0.4717694239998309 s`
  - baseline autojit50: `0.4726716300001499 s`
  - fixed autojit50: `0.4497695210002348 s`

### Current conclusion
- The requested benchmark set does not show a confirmed large regression after
  focused follow-up.
- The earlier `fannkuch` regression signal was not stable.

## Session Update: 2026-04-06 (direct bm_go probe)

### Direct issue-specific comparison
- Harness:
  - `scripts/arm/bench_pyperf_direct.py`
  - `PYTHONJITENABLEHIRINLINER=1`
  - `compile_strategy=all`
  - `specialized_opcodes=true`
  - `samples=5`
  - `prewarm_runs=1`
- Baseline:
  - `median_wall_sec = 0.5150911270000051`
- Fixed:
  - `median_wall_sec = 0.17598324100003992`
- Delta:
  - about `-65.83%`

### Readout
- The direct `bm_go.versus_cpu()` path shows a much larger positive move than
  the coarse pyperformance gate.
- This is consistent with the earlier diagnosis that the repaired hot path is
  very benchmark-shape-specific, while broad pyperformance gate numbers can be
  diluted by other costs and host noise.

## Session Update: 2026-04-29 (object-heavy performance slice)

### Task status
- Continued object-heavy pyperformance optimization on the standard ARM entrypoint.
- Fixed a correctness blocker exposed by the `PYTHONJITINSTANCEVALUEMINLOCALS=1` candidate.
- Rejected the broad low-local instance-value threshold change because the benchmark matrix regressed overall.

### Code changes completed
- Added a method-call-shape fallback for `LOAD_ATTR_INSTANCE_VALUE` in `cinderx/Jit/hir/builder.cpp`.
- Added focused ARM regression coverage:
  - `test_instance_value_method_attr_shape_falls_back`
- Added benchmark-script pass-through for:
  - `PYTHONJITINSTANCEVALUEMINLOCALS`

### Remote verification summary
- Focused RED before the fix:
  - `test_instance_value_method_attr_shape_falls_back` failed with return code `-6`
  - stderr contained `Can't pop from empty stack`
- Focused GREEN after the fix through `/root/work/incoming/remote_update_build_test.sh`:
  - `test_instance_value_method_attr_shape_falls_back ... ok`
  - `Ran 1 test in 0.358s`
  - `OK`
- Object matrix after the fix:
  - command used `PYTHONJITINSTANCEVALUEMINLOCALS=1`
  - `AUTOJIT=50`, `SAMPLES=3`
  - result file: `/root/work/arm-sync/object_matrix_iv_minlocals1_after_method_fallback_20260429_1.json`

### Performance / behavior summary
- Compared to `/root/work/arm-sync/object_matrix_current_after_osr_leaf_gate_20260429_1.json`:
  - `deltablue`: `0.09192227599851321s` -> `0.10004417100572027s`, slower
  - `go`: `0.18278077200011467s` -> `0.18882352900254773s`, slower
  - `raytrace`: `0.5886780619985075s` -> `0.5699919469989254s`, faster
  - `richards`: `0.11665852400255972s` -> `0.22533620600006543s`, much slower
- Decision:
  - keep the stack-shape bug fix
  - do not keep a default threshold change
  - continue with narrower object-workload candidates instead of broad low-local specialization

### Exact method cache split follow-up
- Extended `scripts/arm/run_pyperf_subset.sh` so optional worker env vars can be inherited by pyperformance workers.
- Focused correctness test through `/root/work/incoming/remote_update_build_test.sh`:
  - `test_exact_method_cache_split_respects_instance_shadowing ... ok`
  - `Ran 1 test in 3.271s`
  - `OK`
- Matrix with `PYTHONJITEXACTMETHODCACHESPLIT=1`:
  - result file: `/root/work/arm-sync/object_matrix_exactmethodsplit_20260429_1.json`
  - `deltablue`: `0.09192227599851321s` -> `0.09500566499627894s`, slower
  - `go`: `0.18278077200011467s` -> `0.19336685499729356s`, slower
  - `raytrace`: `0.5886780619985075s` -> `0.5885913480015006s`, neutral
  - `richards`: `0.11665852400255972s` -> `0.11878468000213616s`, slower
- Decision:
  - do not enable exact method cache split by default
  - move on to narrower object state-update candidates

## Session Update: 2026-05-01 (object-heavy STORE_ATTR direct-field slice)

### Task status
- Continued object-heavy pyperformance optimization using only the standard ARM remote entrypoint.
- Rejected the runtime-helper lowering for `STORE_ATTR_INSTANCE_VALUE` after matrix evidence showed it was not throughput-positive.
- Replaced it with direct `LoadField` / `CheckField` / `StoreField` lowering for existing split-dict instance values.

### TDD evidence
- RED:
  - `test_instance_value_specialized_opcodes_lower_to_field_ops` was tightened to expect direct `StoreField` lowering and no `StoreAttrInstanceValue` helper opcode.
  - remote result failed as expected with `StoreField=0` and `StoreAttrInstanceValue=1`.
- GREEN:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - `test_slot_specialized_opcodes_lower_to_field_ops ... ok`
  - `test_instance_value_specialized_opcodes_lower_to_field_ops ... ok`
  - `Ran 2 tests in 9.854s`
  - `OK`

### Benchmark evidence
- Helper candidate:
  - result file: `/root/work/arm-sync/object_matrix_storeattr_instance_value_20260501_1.json`
  - improved `raytrace`, but regressed `deltablue`, `go`, and `richards`
  - decision: not kept as the default path
- Direct-field current-code matrix:
  - specialized-opcodes on: `/root/work/arm-sync/object_matrix_storeattr_direct_field_20260501_1.json`
  - specialized-opcodes off: `/root/work/arm-sync/object_matrix_storeattr_direct_field_nospec_20260501_1.json`
  - same-harness comparison:
    - `deltablue`: about `0.47%` faster with specialized opcodes
    - `go`: about `0.19%` faster with specialized opcodes
    - `raytrace`: about `0.13%` faster with specialized opcodes
    - `richards`: about `1.26%` slower with specialized opcodes

### Notes
- Added a pyperformance venv fallback in `scripts/arm/run_pyperf_subset.sh` so `SKIP_PYPERF_SETUP=1` matrix runs can still resolve the reusable `/root/venv/<name>` worker environment.
- Removed an unused `builder.cpp` lambda after the remote build exposed the warning.
- Performance conclusion is deliberately conservative:
  - the direct-field lowering is correctness-clean and better than the helper attempt
  - the same-run matrix is only a small mixed signal, so the next slice needs a hotter path with more headroom

## Session Update: 2026-05-01 (object-heavy exact list append slice)

### Task status
- Continued from the STORE_ATTR direct-field slice into method-call overhead.
- Tested a narrow Python 3.14 exact-list `CALL_LIST_APPEND` lowering.
- The focused HIR shape improved, but matrix timing remains mixed/noisy.

### TDD evidence
- RED through `/root/work/incoming/remote_update_build_test.sh`:
  - `ArmRuntimeTests.test_exact_list_append_eliminates_callmethod`
  - failed as expected with `CallMethod=1`, `ListAppend=0`, result `10001`
- GREEN through `/root/work/incoming/remote_update_build_test.sh`:
  - `test_exact_list_append_eliminates_callmethod ... ok`
  - `test_list_subclass_append_eliminates_callmethod ... ok`
  - `Ran 2 tests in 0.476s`
  - `OK`

### Benchmark evidence
- Result file:
  - `/root/work/arm-sync/object_matrix_listappend_direct_20260501_1.json`
- Compared to the prior same-code STORE_ATTR direct-field matrix:
  - `deltablue`: about `0.16%` slower
  - `go`: about `0.16%` slower
  - `raytrace`: effectively neutral
  - `richards`: about `0.95%` faster

### Notes
- Direct `go:UCTNode.play` HIR evidence improved from `ListAppend=0`, `CallMethod=7` to `ListAppend=2`, `CallMethod=5`.
- This is a real lowering/shape improvement, but not yet the performance breakthrough for the object-heavy matrix.
- Next direction remains hotter Python method-call / zero-arg tiny-method / call overhead paths.

## Session Update: 2026-05-01 18:29 +08:00 (tiny bool predicate matrix)

### Remote regression evidence
- Re-uploaded the current worktree tarball and remote entrypoint before the regression run.
- Remote command used `/root/work/incoming/remote_update_build_test.sh`.
- Targeted ARM runtime suite:
  - `test_tiny_bool_predicate_method_eliminates_branch_callmethod`
  - `test_tiny_bool_getter_method_eliminates_callmethod`
  - `test_tiny_bool_getter_method_respects_instance_shadowing`
  - `test_tiny_return_self_method_refines_receiver_after_guard`
  - `test_tiny_bool_method_refines_branch_receiver_fields`
  - `test_exact_list_append_eliminates_callmethod`
  - `test_list_subclass_append_eliminates_callmethod`
  - `test_slot_specialized_opcodes_lower_to_field_ops`
  - `test_instance_value_specialized_opcodes_lower_to_field_ops`
  - `test_phase1_once_call_hot_loop_enters_jit_same_activation`
  - `test_phase1_loop_osr_skips_active_exception_shape`
  - `test_phase1_loop_osr_skips_pyperformance_startup_imports`
  - `test_phase1_loop_osr_richards_method_loop_does_not_crash`
- Result:
  - `Ran 13 tests in 18.357s`
  - `OK`

### Benchmark evidence
- First matrix attempt failed before build:
  - remote entrypoint could not open `/root/work/incoming/cinderx-update.tar`
  - resolution was to re-upload the tarball and entrypoint, then rerun the same command.
- Successful matrix result:
  - file: `/root/work/arm-sync/object_matrix_tiny_bool_predicate_20260501_1.json`
  - `AUTOJIT=50`, `SAMPLES=3`
  - `deltablue`: median `0.0037095240004418883s`
  - `go`: median `0.12683104900133912s`
  - `raytrace`: median `0.3541596559989557s`
  - `richards`: median `0.052140922998660244s`
- Compared to `/root/work/arm-sync/object_matrix_storeattr_direct_field_20260501_1.json`:
  - `deltablue`: about `0.18%` faster
  - `go`: about `0.57%` slower
  - `raytrace`: about `0.42%` faster
  - `richards`: about `0.53%` faster
- Compared to `/root/work/arm-sync/object_matrix_listappend_direct_20260501_1.json`:
  - `deltablue`: about `0.33%` faster
  - `go`: about `0.41%` slower
  - `raytrace`: about `0.42%` faster
  - `richards`: about `0.43%` slower

### Current decision
- Do not claim a material performance win from tiny bool predicates alone.
- Continue into higher-leverage remaining method/call hotspots, starting with `go` and `richards`.

## Session Update: 2026-05-01 (STORE_SUBSCR_LIST_INT focused fix)

### Task status
- Continued object-heavy `go`-like workload optimization after tiny bool predicates produced only a small/mixed matrix signal.
- Picked the `go` candidate from hotspot analysis:
  - exact list assignment with exact integer indexes, represented by Python 3.14 `STORE_SUBSCR_LIST_INT`.

### TDD evidence
- RED through `/root/work/incoming/remote_update_build_test.sh`:
  - `ArmRuntimeTests.test_list_int_store_subscr_lowers_to_callstatic_helper`
  - failed before the lowering with `StoreSubscr=2`, `CallStatic=0`.
- GREEN through `/root/work/incoming/remote_update_build_test.sh` after the root-cause fix:
  - `test_list_int_store_subscr_lowers_to_callstatic_helper ... ok`
  - `Ran 1 test in 0.050s`
  - `OK`
- Broader focused regression through `/root/work/incoming/remote_update_build_test.sh`:
  - object/JIT focused suite including list-store, list-append, direct-field, tiny-method, and OSR safety tests
  - `Ran 14 tests in 18.404s`
  - `OK`

### Debugging evidence
- First implementation exposed a compile-time segfault at `jit.force_compile(set_pair)`.
- C-stack pointed into refcount/deopt frame-state binding:
  - `RefcountInsertion::Run`
  - `DeoptBase::setFrameState`
  - `FrameState copy`
- HIR dump showed array slow-path blocks with `GuardType` and no same-block `Snapshot`.
- Root fix:
  - add `Snapshot(tc.frame)` at the store-subscript array slow-path block entry
  - add snapshots between non-replayable `CallStatic` store helpers and `CheckNeg` deopt checks

### Next
- Object-heavy pyperformance matrix through `/root/work/incoming/remote_update_build_test.sh`:
  - result file: `/root/work/arm-sync/object_matrix_list_store_int_20260501_1.json`
  - `AUTOJIT=50`, `SAMPLES=3`
  - `deltablue`: median `0.0037232350005069748s`
  - `go`: median `0.12654143699910492s`
  - `raytrace`: median `0.3543507650028914s`
  - `richards`: median `0.05217049199927715s`
- Matrix comparison:
  - vs tiny-bool matrix:
    - `go` improved about `0.23%`, but `deltablue`, `raytrace`, and `richards` were slightly slower
  - vs listappend matrix:
    - `raytrace` improved about `0.37%`, but `go` and `richards` were slower
  - vs storeattr matrix:
    - `raytrace` improved about `0.37%` and `richards` about `0.47%`, but `deltablue` and `go` were slower
- Decision:
  - keep the correctness-clean list/int store lowering candidate, but do not treat it as the performance breakthrough
  - continue into higher-frequency Python method/function-call overhead

## Session Update: 2026-05-01 (tiny bool state-mutator slice)

### Task status
- Continued after list/int store-subscript produced only a mixed matrix signal.
- Chose the next higher-frequency Richards candidate:
  - tiny zero-arg methods that set bool state fields and return `self`.

### TDD evidence
- RED through `/root/work/incoming/remote_update_build_test.sh`:
  - `ArmRuntimeTests.test_tiny_bool_state_mutator_eliminates_callmethod`
  - failed as expected with:
    - `CallMethod = 3`
    - `StoreField = 0`
- GREEN through `/root/work/incoming/remote_update_build_test.sh`:
  - `test_tiny_bool_state_mutator_eliminates_callmethod ... ok`
  - `Ran 1 test in 0.756s`
  - `OK`

### Implementation notes
- Extended the tiny-method classifier/lowering for exact bool field stores plus `return self`.
- Lowering guards method identity, receiver type dispatch, split-dict keys, inline-values validity, and existing field presence before direct stores.
- First GREEN attempt exposed a compile-time `std::string` vs `const char*` mismatch; fixed and reran the same focused remote test.

### Next
- Broader object/JIT focused regression through `/root/work/incoming/remote_update_build_test.sh`:
  - included the new mutator test plus list-store, list-append, direct-field, tiny predicate/getter/return-self, and OSR safety tests
  - `Ran 15 tests in 19.117s`
  - `OK`
- Next:
  - first Richards-only benchmark produced an empty summary because single-benchmark pyperformance JSON omitted `metadata.name`
  - fixed `scripts/arm/run_pyperf_subset.sh` to name a single unnamed benchmark from `BENCHMARKS`
  - valid Richards-first benchmark:
    - file: `/root/work/arm-sync/richards_tiny_bool_mutator_20260501_2.json`
    - `AUTOJIT=50`, `SAMPLES=5`
    - median `0.05213113099671318s`
  - comparison:
    - about `0.08%` faster than list-store matrix
    - about `0.02%` faster than tiny-bool matrix
    - about `0.41%` slower than listappend matrix
    - about `0.54%` faster than storeattr matrix
- Decision:
  - timing signal is still noise-sized
  - run full object matrix to check combined signal and side effects

## Session Update: 2026-05-01 (tiny bool mutator full matrix parsed)

### Benchmark evidence
- Parsed the completed remote full matrix:
  - `/root/work/arm-sync/object_matrix_tiny_bool_mutator_20260501_1.json`
- Medians:
  - `deltablue`: `0.0037431960008689202s`
  - `go`: `0.12771624699962558s`
  - `raytrace`: `0.3545897559997684s`
  - `richards`: `0.05264104700108874s`
- Relative result:
  - slower than the previous list-store matrix on all four object-heavy benchmarks
  - slower than the tiny-bool predicate matrix on all four object-heavy benchmarks
  - only `raytrace` shows a small win versus the older listappend/storeattr matrices

### Decision
- Do not claim a material performance win from the current tiny bool mutator lowering.
- Continue performance work, but bias toward candidates with fewer guards per saved Python operation.

### Probe attempt note
- Attempted a remote-entrypoint HIR probe with:
  - `EXTRA_VERIFY_CMD='python scripts/arm/probe_object_hir.py go richards'`
- Result:
  - the remote entrypoint completed staging, build, install, filtered ARM runtime run, and JIT smoke
  - the extra probe failed with `ModuleNotFoundError: No module named 'cinderjit'`
- Root cause:
  - `run_extra_cmd` sets `PYTHON=$DRIVER_VENV/bin/python`, but the command used bare `python`, so it ran outside the driver venv
- Next action:
  - re-upload the tarball because the entrypoint consumes it
  - rerun the same probe through the entrypoint with `EXTRA_VERIFY_CMD='$PYTHON scripts/arm/probe_object_hir.py go richards'`

## Session Update: 2026-05-01 (disable negative tiny mutator lowering)

### Root-cause evidence
- Subagent review and focused test output both showed the same issue:
  - the mutator lowering eliminated `CallMethod`
  - but it preserved `LoadMethodCached/LoadMethod` for the method-target guard
  - it then added direct field stores and guard-heavy CFG
- Focused pre-fix output:
  - `CallMethod = 0`
  - `LoadMethodCached + LoadMethod = 3`
  - `StoreField = 7`

### TDD evidence
- RED:
  - `ArmRuntimeTests.test_tiny_bool_state_mutator_keeps_callmethod_until_lookup_is_removed`
  - remote entrypoint failed as expected with `AssertionError: 0 not greater than 0`
- GREEN:
  - disabled the default `simplifyCallMethodTinyBoolMutator()` hook
  - remote entrypoint focused result:
    - `Ran 1 test in 0.812s`
    - `OK`

### Next
- Run focused object/JIT regression with the renamed test.
- Run the object matrix again to confirm the previously observed mutator slowdown is removed.

### Focused regression evidence
- Remote command used `/root/work/incoming/remote_update_build_test.sh`.
- Focused object/JIT suite result:
  - `Ran 15 tests in 19.170s`
  - `OK`
- Next:
  - run object-heavy pyperformance matrix with the mutator hook disabled.

### Matrix evidence
- Remote command used `/root/work/incoming/remote_update_build_test.sh`.
- Result file:
  - `/root/work/arm-sync/object_matrix_mutator_disabled_20260501_1.json`
- Medians:
  - `deltablue`: `0.0037334650041884743s`
  - `go`: `0.12676655300310813s`
  - `raytrace`: `0.35641779599973233s`
  - `richards`: `0.05190802599827293s`
- Versus the negative mutator matrix:
  - `deltablue`: about `0.26%` faster
  - `go`: about `0.74%` faster
  - `raytrace`: about `0.52%` slower
  - `richards`: about `1.39%` faster
- Decision:
  - the rollback/disable is justified for the mutator shape
  - this still is not a material overall win
  - move to `Task.findtcb`-style one-arg tiny method calls

## 2026-05-01 exact list/int subscript read slice

- Chose the next low-risk object-heavy candidate:
  - exact list/tuple + exact int subscript reads used by `Task.findtcb()`-style code and `bm_go`.
- RED evidence through `/root/work/incoming/remote_update_build_test.sh`:
  - `ArmRuntimeTests.test_exact_list_int_subscr_uses_guarded_array_fast_path`
  - failed as expected before production code with:
    - `AssertionError: 2 != 0`
    - `CheckSequenceBounds = 2`
    - `LoadArrayItem = 2`
    - semantic fallback outputs remained correct.
- Implemented minimal GREEN candidate:
  - in `simplifyLoadSubscr()`, exact list/tuple int reads now use guard deopts for `index >= 0` and `index < Py_SIZE(sequence)` before direct `LoadArrayItem`.
  - negative and out-of-range cases should deopt to interpreter rather than call `JITRT_CheckSequenceBounds` on the hot path.
- Focused GREEN evidence:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - build/install/JIT smoke completed.
  - `ArmRuntimeTests.test_exact_list_int_subscr_uses_guarded_array_fast_path`:
    - `Ran 1 test in 0.045s`
    - `OK`
- Next:
  - re-upload because the remote entrypoint consumed the tarball.
  - run the focused object/JIT regression suite.
  - if green, run the object-heavy pyperformance matrix.
- Focused regression evidence:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - object/JIT/OSR focused suite result:
    - `Ran 16 tests in 14.446s`
    - `OK`
- Next:
  - re-upload because the remote entrypoint consumed the tarball again.
  - run `richards,go,deltablue,raytrace` pyperformance matrix through the remote entrypoint.
- Matrix evidence:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - result file: `/root/work/arm-sync/object_matrix_list_read_bounds_20260501_1.json`.
  - medians:
    - `deltablue`: `0.0037166830006754026s`
    - `go`: `0.12654863199713873s`
    - `raytrace`: `0.3568251210017479s`
    - `richards`: `0.05177505699975882s`
  - compared with `/root/work/arm-sync/object_matrix_mutator_disabled_20260501_1.json`:
    - `deltablue`: about `0.45%` faster
    - `go`: about `0.17%` faster
    - `raytrace`: about `0.11%` slower
    - `richards`: about `0.26%` faster
- Decision:
  - the shape is safe and slightly positive on three primary object workloads, but still not a strong throughput win.
  - continue refining this path by reducing guard count before moving to another feature.
- Guard-count RED:
  - tightened the exact list/int subscript test to assert no more than two ordinary `Guard` ops.
  - remote entrypoint failed before the production refinement:
    - `AssertionError: 4 not less than or equal to 2`
    - stdout: `0`, `4`, `2`, `40`, `50`, `index-error`, `30`
- Implemented next minimal candidate:
  - combine `index >= 0` and `index < Py_SIZE(sequence)` into one unsigned less-than guard.
  - negative and out-of-range indexes should deopt through that single guard.
- Next:
  - re-upload and run the tightened focused test through the remote entrypoint.
- Guard-count GREEN:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - tightened focused test:
    - `Ran 1 test in 0.047s`
    - `OK`
- Next:
  - re-upload because the remote entrypoint consumed the tarball.
  - rerun the 16-test object/JIT/OSR focused suite.
  - run a refreshed object-heavy matrix for the unsigned-bounds refinement.
- Focused regression after unsigned-bounds refinement:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - `Ran 16 tests in 14.408s`
  - `OK`
- Unsigned-bounds matrix:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - result file: `/root/work/arm-sync/object_matrix_list_read_unsigned_bounds_20260501_1.json`.
  - medians:
    - `deltablue`: `0.0037338530019042082s`
    - `go`: `0.12772780600062106s`
    - `raytrace`: `0.35630999699787935s`
    - `richards`: `0.052564787001756486s`
  - compared with the two-guard exact-list/int read fast path:
    - `deltablue`: about `0.46%` slower
    - `go`: about `0.93%` slower
    - `raytrace`: about `0.14%` faster
    - `richards`: about `1.53%` slower
- Decision:
  - reject the unsigned single-guard refinement.
  - restored the previous two-guard implementation and original shape test.
- Next:
  - re-upload and revalidate the restored two-guard final state through the remote entrypoint.
- Restored two-guard focused regression:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - object/JIT/OSR focused suite result:
    - `Ran 16 tests in 14.378s`
    - `OK`
- Next:
  - run a fresh restored two-guard object-heavy matrix before choosing the next optimization.
- Restored two-guard object matrix:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - result file: `/root/work/arm-sync/object_matrix_list_read_restored_20260501_1.json`
  - medians:
    - `deltablue`: `0.0037174040044192225s`
    - `go`: `0.12667208800121443s`
    - `raytrace`: `0.3546217519979109s`
    - `richards`: `0.05186034399957862s`
  - versus `object_matrix_mutator_disabled_20260501_1.json`:
    - `deltablue`: about `0.43%` faster
    - `go`: about `0.08%` faster
    - `raytrace`: about `0.50%` faster
    - `richards`: about `0.09%` faster
- Decision:
  - keep the restored two-guard exact list/int read path.
  - do not spend more time on unsigned/single-guard variants for this slice.
- Next:
  - inspect higher-level Python-call/method-call costs, especially one-arg tiny method shapes used by `Task.findtcb`-style code.
- HIR inliner switch experiment:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - result file: `/root/work/arm-sync/object_matrix_hir_inliner_on_20260501_1.json`
  - medians:
    - `deltablue`: `0.0037331460043787956s`
    - `go`: `0.12648785300552845s`
    - `raytrace`: `0.3559034479985712s`
    - `richards`: `0.051703182005439885s`
  - versus restored two-guard baseline:
    - `deltablue`: about `0.42%` slower
    - `go`: about `0.15%` faster
    - `raytrace`: about `0.36%` slower
    - `richards`: about `0.30%` faster
- Decision:
  - global HIR inliner remains too mixed to flip on by default.
  - pursue selective/narrow Python-call or method-call shapes.
- Selective method-value preload TDD:
  - RED through `/root/work/incoming/remote_update_build_test.sh`:
    - `ArmRuntimeTests.test_method_with_values_one_arg_method_preloads_for_hir_inliner`
    - failed before production code with `num_inlined_functions = 0`
    - stdout shape: `CallMethod = 1`, `VectorCall = 1`, semantic outputs correct
  - GREEN through the same remote entrypoint after production change:
    - `Ran 1 test in 0.048s`
    - `OK`
  - implementation:
    - `Preloader` records warmed `LOAD_ATTR_METHOD_WITH_VALUES` cached `PyFunction` descriptors
    - `preloadFuncAndDeps()` queues those functions as dependent preload candidates
- Next:
  - run focused regression suite.
  - run refreshed inliner-on object matrix to see if this improves `richards/go` enough without hurting `deltablue/raytrace` further.
- Focused regression:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - result:
    - `Ran 20 tests in 15.646s`
    - `OK`
- Broad method-value preload matrix:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - result file: `/root/work/arm-sync/object_matrix_hir_inliner_method_preload_20260501_1.json`
  - medians:
    - `deltablue`: `0.0037402169982669875s`
    - `go`: `0.1263926179963164s`
    - `raytrace`: `0.3542254209969542s`
    - `richards`: `0.052375790997757576s`
  - decision:
    - too broad: `go` and `raytrace` improve, but `deltablue` and especially `richards` regress versus the restored baseline.
    - narrowed the production shape to only preload small one-arg `self` methods for the HIR inliner.
- Narrowed preload focused verification:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - focused test:
    - `Ran 1 test in 0.049s`
    - `OK`
- Narrowed preload focused regression:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - object/JIT/OSR focused suite:
    - `Ran 20 tests in 15.739s`
    - `OK`
- Next:
  - re-upload because the remote entrypoint consumes the tarball.
  - run refreshed inliner-on object-heavy matrix for the narrowed shape.
- Narrowed method-value preload matrix:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - result file: `/root/work/arm-sync/object_matrix_hir_inliner_small_method_preload_20260501_1.json`
  - medians:
    - `deltablue`: `0.0037349900012486614s`
    - `go`: `0.12648953100142535s`
    - `raytrace`: `0.35573463599575916s`
    - `richards`: `0.052032849001989234s`
  - versus restored two-guard baseline:
    - `deltablue`: about `0.47%` slower
    - `go`: about `0.14%` faster
    - `raytrace`: about `0.31%` slower
    - `richards`: about `0.33%` slower
- Decision:
  - narrowed preload is useful as an opt-in HIR-inliner capability proof, but it is not the default performance win.
  - continue with default-on object hot paths rather than globally enabling HIR inliner.
- Refcount diagnostic attempt:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - result:
    - failed before probe execution because the command used an old hashed pyperformance venv path.
    - error: `/root/work/cinderx-main/venv/cpython3.14-596c65cb0333-compat-31b33d68c68a/bin/python: No such file or directory`
  - next:
    - rerun the same probe through the stable `/root/venv-cinderx314/bin/python` entrypoint, or let the remote script prepare the pyperformance venv if that Python lacks `pyperformance`.
- Refcount diagnostic:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - output file: `/root/work/arm-sync/object_probe_refcounts_20260501_2.txt`
  - top refcount-heavy targets include:
    - `richards.Richards.run`: 102 refcount ops, 4 `LoadField`, 34 call ops
    - `go.Board.useful`: 100 refcount ops, 91 `LoadField`, 9 call ops
    - `go.Square.move`: 78 refcount ops, 66 `LoadField`, 7 call ops
    - `richards.Task.runTask`: 52 refcount ops, 97 `LoadField`, 6 call ops
    - `richards.schedule`: 41 refcount ops, 85 `LoadField`, 2 call ops
  - interpretation:
    - refcount traffic is real in object-heavy HIR, but the first minimal bool-branch test did not hit field lowering because the function had too few locals for the current `LOAD_ATTR_INSTANCE_VALUE` default gate.
- Bool-field refcount TDD RED attempt 1:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - result:
    - failed before reaching the intended production gap because the test shape did not trigger `LoadField`.
    - stdout shape: `LoadField=0`, `GuardType=0`, `ref_ops=1`, semantic outputs `1`, `0`.
  - next:
    - mutate the test shape to use enough locals to pass the existing instance-value lowering threshold, then rerun RED.
- Bool-field refcount TDD RED attempt 2:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - result:
    - the mutated test did hit field lowering, but the target gap was already absent.
    - stdout shape: `LoadField=4`, `GuardType=0`, `ref_ops=0`, semantic outputs `1`, `0`.
  - decision:
    - abandon this minimal bool-field refcount candidate; no production change is justified.
    - removed the temporary test to keep the suite focused on actual behavior changes.
- Next candidate triage:
  - `list.pop(0)` / queue-pop already has existing protection:
    - HIR test eliminates `CallMethod` for inherited list subclass `pop(0)`.
    - LIR test checks the remaining method-descriptor path avoids generic `VectorCall`.
  - decision:
    - do not duplicate the existing list-pop work in this slice.
    - switch to tier-policy / AUTOJIT threshold exploration, because current code-level micro-optimizations are mostly noise-sized.
- AUTOJIT threshold probe:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - result file: `/root/work/arm-sync/object_matrix_autojit100_20260501_1.json`
  - versus current restored `AUTOJIT=50` baseline:
    - `deltablue`: about `0.38%` slower
    - `go`: about `0.03%` faster
    - `raytrace`: about `0.40%` slower
    - `richards`: about `0.17%` faster
  - interpretation:
    - higher promotion threshold has visible but mixed effect.
    - continue with a threshold band probe (`75`, `150`, `200`) before considering any policy/default change.
- AUTOJIT threshold band:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - compared with current restored `AUTOJIT=50` baseline:
    - `AUTOJIT=75`: `deltablue` `0.16%` slower, `go` `0.33%` faster, `raytrace` `0.08%` faster, `richards` `0.57%` slower
    - `AUTOJIT=150`: `deltablue` `0.14%` slower, `go` `0.31%` faster, `raytrace` `0.24%` faster, `richards` `0.14%` slower
    - `AUTOJIT=200`: `deltablue` `0.06%` slower, `go` `0.10%` faster, `raytrace` `0.69%` slower, `richards` `0.19%` slower
  - decision:
    - do not change the global threshold from this evidence.
    - use the result as policy evidence: a mature tiering strategy needs per-function promotion/backoff/fallback, not one workload-wide gate.
- Baseline-tier MVP state fix:
  - reproduced focused `test_jit_tiering` crash through `/root/work/incoming/remote_update_build_test.sh`.
  - direct faulthandler diagnostics showed pending baseline-auto scheduling could fall through to optimized compilation after baseline-auto was disabled.
  - implemented separate pending baseline state:
    - `baseline_scheduled_funcs_` tracks functions scheduled only for future baseline activation.
    - active baseline state remains in `baseline_funcs_`.
    - disabled baseline-auto now unschedules pending functions on next call and keeps them interpreted.
  - added/updated tiering tests for:
    - `baseline_compile_after_n_calls(None)` reset
    - disabling baseline-auto with pending functions
    - forced baseline
    - forced baseline -> optimized promotion
    - low-threshold auto-baseline
  - focused remote GREEN:
    - `Ran 5 tests in 0.004s`
    - `OK`
  - next:
    - run combined focused test plus `scripts/arm/baseline_tier_repro.py` through the remote entrypoint.
    - then run a default object-heavy matrix to verify no throughput regression from the tier-state checks.
- Baseline-tier combined verification:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - extra command:
    - `PYTHONPATH=cinderx/PythonLib/test_cinderx python -m unittest test_jit_tiering -v && python scripts/arm/baseline_tier_repro.py`
  - result:
    - `test_jit_tiering`: `Ran 5 tests in 0.004s`, `OK`
    - remote entrypoint exited `0`
  - next:
    - run object-heavy default matrix to check performance/regression impact.
- Default object-heavy matrix after baseline-tier state fix:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - result file:
    - `/root/work/arm-sync/object_matrix_after_baseline_tier_state_20260501_1.json`
  - compared with restored `AUTOJIT=50` baseline:
    - `deltablue`: `0.63%` slower
    - `go`: `0.42%` slower
    - `raytrace`: `0.21%` slower
    - `richards`: `0.01%` slower
  - interpretation:
    - stability/tier-state work is green, but there is no throughput win from this change.
    - continue performance work on a default hot path; do not claim this as a benchmark improvement.

## Session Update: 2026-05-01 (lookup-free tiny bool mutator retry)

### TDD evidence
- RED through `/root/work/incoming/remote_update_build_test.sh`:
  - tightened `ArmRuntimeTests.test_tiny_bool_state_mutator_removes_lookup_and_callmethod`.
  - pre-fix HIR shape:
    - `CallMethod = 3`
    - `LoadMethodCached + LoadMethod = 3`
    - `StoreField = 0`
  - semantic outputs remained correct.
- First GREEN attempt:
  - removed the `GuardIs(load_method_result)` dependency in the simplifier.
  - result still had `LoadMethodCached + LoadMethod = 3` and exposed a shadowing semantic failure.
  - conclusion: the optimization must happen before `LoadMethod` emission in the builder, not as post-hoc DCE.
- Final focused GREEN:
  - builder now recognizes warmed `LOAD_ATTR_METHOD_WITH_VALUES` whose descriptor is a tiny bool mutator `PyFunction`.
  - it emits deopt-only method-value guards and pushes `LoadConst(func), receiver`, avoiding `LoadMethod`.
  - simplifier only applies tiny mutator lowering to that constant-function shape.
  - remote focused result:
    - `test_tiny_bool_state_mutator_removes_lookup_and_callmethod ... ok`
    - remote entrypoint exit code `0`.
- Debugging fix:
  - `ArmRuntimeTests.tearDown()` no longer restores missing auto-JIT threshold with `compile_after_n_calls(0)`, because that enables compile-all and can crash unittest exit paths.

### Regression evidence
- Remote object/JIT/OSR focused suite:
  - command used `/root/work/incoming/remote_update_build_test.sh`.
  - `Ran 23 tests in 21.732s`
  - `OK`

### Benchmark evidence
- Object-heavy matrix:
  - result file: `/root/work/arm-sync/object_matrix_tiny_bool_mutator_lookup_free_20260501_1.json`
  - `AUTOJIT=50`, `SAMPLES=3`
  - medians:
    - `deltablue`: `0.003733324003405869s`
    - `go`: `0.12625505700270878s`
    - `raytrace`: `0.3546679770006449s`
    - `richards`: `0.05186529200000223s`
  - compared with restored list-read baseline:
    - `deltablue`: about `0.43%` slower
    - `go`: about `0.33%` faster
    - `raytrace`: about `0.01%` slower
    - `richards`: about `0.01%` slower
  - compared with mutator-disabled baseline:
    - `deltablue`: about neutral
    - `go`: about `0.40%` faster
    - `raytrace`: about `0.49%` faster
    - `richards`: about `0.08%` faster
- Decision:
  - the shape is now correctness-clean and fixes the old negative mutator design.
  - throughput signal is still small and mixed against the latest restored baseline, so continue optimizing before calling this a final performance win.

## Session Update: 2026-05-01 (default one-arg method-value fast path)

### TDD evidence
- RED through `/root/work/incoming/remote_update_build_test.sh`:
  - new test:
    - `ArmRuntimeTests.test_method_with_values_one_arg_method_removes_lookup_by_default`
  - pre-fix HIR shape:
    - `CallMethod = 1`
    - `LoadMethodCached + LoadMethod = 1`
    - `VectorCall = 1`
  - semantic outputs already matched:
    - normal call: `21`
    - instance shadowing: `100`
    - class method replacement: `42`
- First GREEN:
  - builder recognizes warmed `LOAD_ATTR_METHOD_WITH_VALUES` descriptors that are small `self + 1 arg` Python functions.
  - for cache entries with nonzero type/key versions, outer-frame builder emits deopt-only guards and pushes `LoadConst(func), receiver`.
  - generic `simplifyCallMethod()` then converts the constant-function `CallMethod` into `VectorCall`, removing both `LoadMethod` and `CallMethod`.
  - focused remote result:
    - `test_method_with_values_one_arg_method_removes_lookup_by_default ... ok`
- Regression failure and root cause:
  - 24-test focused regression initially failed:
    - `test_polymorphic_virtual_method_avoids_method_with_values_guard_deopts`
    - deopt entries for `Task.runTask` / `LOAD_ATTR_METHOD_WITH_VALUES`: `2`
  - root cause:
    - the new deopt-only path was too broad for non-exact `self.fn(x)` virtual calls inside base-class methods.
    - this reopened the polymorphic shape that prior raytrace/richards work intentionally routed through normal `LoadMethod`.
- Fix:
  - restored the non-exact `self` receiver guard in `emitLoadAttr`.
  - deopt-only tiny/one-arg method-value fast path now skips non-exact current-method `self` receivers, while still allowing ordinary external object parameters like `hot(table, index)`.
- Focused GREEN after the fix:
  - remote command used `/root/work/incoming/remote_update_build_test.sh`.
  - tests:
    - `test_polymorphic_virtual_method_avoids_method_with_values_guard_deopts`
    - `test_method_with_values_one_arg_method_removes_lookup_by_default`
  - result:
    - `Ran 2 tests in 0.788s`
    - `OK`

### Regression evidence
- Remote object/JIT/OSR focused suite:
  - command used `/root/work/incoming/remote_update_build_test.sh`.
  - `Ran 24 tests in 22.477s`
  - `OK`

### Benchmark evidence
- Object-heavy matrix:
  - result file:
    - `/root/work/arm-sync/object_matrix_one_arg_method_value_default_20260501_1.json`
    - local copy: `arm-results/object_matrix_one_arg_method_value_default_20260501_1.json`
  - `AUTOJIT=50`, `SAMPLES=3`
  - medians:
    - `deltablue`: `0.0037186230038059871s`
    - `go`: `0.12664924700220581s`
    - `raytrace`: `0.355018147994997s`
    - `richards`: `0.052285240999481175s`
  - compared with restored list-read baseline:
    - `deltablue`: about `0.03%` slower
    - `go`: about `0.02%` faster
    - `raytrace`: about `0.11%` slower
    - `richards`: about `0.82%` slower
  - compared with mutator-disabled baseline:
    - `deltablue`: about `0.40%` faster
    - `go`: about `0.09%` faster
    - `raytrace`: about `0.39%` faster
    - `richards`: about `0.73%` slower
- Decision:
  - keep the correctness/regression work as a useful call-path capability, but do not claim a performance win.
  - the next step is hotspot-guided HIR probing to find a shape with stronger object-heavy matrix impact.

## Session Update: 2026-05-02 (delayed method-value lookup fallback)

### TDD evidence
- Added `ArmRuntimeTests.test_method_with_values_nonexact_self_delays_lookup_to_fallback`.
- RED through `/root/work/incoming/remote_update_build_test.sh` showed final HIR still placed `LoadMethodCached` before the fast `VectorCall`.
- GREEN through `/root/work/incoming/remote_update_build_test.sh`:
  - focused delayed lookup test: `OK`.

### Implementation
- Builder now enables delayed fallback lookup for a narrow safe shape:
  - warmed `LOAD_ATTR_METHOD_WITH_VALUES`
  - descriptor is a small `self + 1 arg` Python function
  - receiver is non-exact current-method `self`
  - the only intervening arg load is side-effect-free
  - type/key versions are nonzero and the builder is in the outer frame.
- The fast path pushes `LoadConst(func), receiver` immediately.
- The generic fallback emits `LoadMethod` inside the fallback `CALL` block, preserving lookup semantics for the enabled side-effect-free shape.

### Verification
- Remote focused three-test guard:
  - `test_method_with_values_nonexact_self_delays_lookup_to_fallback`
  - `test_polymorphic_virtual_method_avoids_method_with_values_guard_deopts`
  - `test_method_with_values_one_arg_method_removes_lookup_by_default`
  - result: `Ran 3 tests in 1.266s`, `OK`
- Remote object/JIT/OSR focused suite:
  - result: `Ran 25 tests in 23.240s`, `OK`

### Benchmark evidence
- Remote entrypoint:
  - `/root/work/incoming/remote_update_build_test.sh`
- Result file:
  - `arm-results/object_matrix_delayed_method_value_lookup_20260501_1.json`
- `AUTOJIT=50`, `SAMPLES=3`
- Medians:
  - `deltablue`: `0.0037092950005899183s`
  - `go`: `0.12652551700011827s`
  - `raytrace`: `0.35530350799672306s`
  - `richards`: `0.05188201300188666s`
- Compared with restored list-read baseline:
  - `deltablue`: about `0.22%` faster
  - `go`: about `0.12%` faster
  - `raytrace`: about `0.19%` slower
  - `richards`: about `0.04%` slower
- Compared with the default one-arg method-value run:
  - `deltablue`: about `0.25%` faster
  - `go`: about `0.10%` faster
  - `raytrace`: about `0.08%` slower
  - `richards`: about `0.77%` faster
- Decision:
  - do not claim a final performance win.
  - keep investigating because delayed lookup mostly removes the richards slowdown from the previous one-arg change, but the matrix is still mixed and raytrace remains slightly worse.

## Session Update: 2026-05-02 (tier-state quality closure)

### Task status
- Shifted from performance tuning back to feature completeness and code quality for the tiered-JIT MVP.
- Used subagent review to stress-check the current design; addressed the high-priority findings in the same loop.

### TDD / RED evidence
- Added tier-state tests for:
  - baseline -> optimized transition reason
  - compile failure reason
  - runtime fallback reason
  - type invalidation reason
  - pending baseline cleanup on disable and pause
  - shared-code `force_compile_baseline()` behavior
- Initial remote focused run failed on the expected missing semantics:
  - promotion transition still `optimized`
  - compile failure transition still `none`
  - runtime fallback transition still `optimized`
  - invalidation counter did not advance for the initial trigger

### Implementation
- Added/filled unified per-function tier state in `Context`.
- Connected runtime deopt fallback and type invalidation patch telemetry into that state.
- Cleaned pending baseline state when disabling baseline-auto or deopting all.
- Made paused `jitVectorcall()` interpret immediately instead of reactivating baseline.
- Prevented baseline force-compile from reopting shared compiled code.
- Removed stale CodeRuntime owner mappings on destroy/uncompile/deopt and tracked multiple owners per runtime.
- Added Python API fallback stubs for the expanded tier-state API.

### Verification
- Remote focused tiering suite:
  - entrypoint: `/root/work/incoming/remote_update_build_test.sh`
  - command: `PYTHONPATH=cinderx/PythonLib/test_cinderx $PYTHON -m unittest test_jit_tiering -v`
  - result: `Ran 14 tests in 2.101s`, `OK`
- Remote broader guard suite:
  - entrypoint: `/root/work/incoming/remote_update_build_test.sh`
  - coverage: `test_jit_tiering`, phase-1 OSR guards, type-guard deopt guard, and method-with-values polymorphism guards
  - result: `Ran 26 tests in 5.330s`, `OK`
- Local hygiene:
  - `git diff --check` on the touched tiering files reported no whitespace errors.

### Decision
- Tier-state MVP is now substantially more complete functionally.
- No performance claim is made from this round; performance tuning should resume only after the policy state machine is layered on top of the now-observable transitions.

## Session Update: 2026-05-02 (threaded precompile quality pass)

- Continued feature-completeness work for tiered JIT before returning to performance tuning.
- Focused failing case:
  - `test_jit_tiering.TieringApiTests.test_compile_failure_backoff_blocks_precompile_all_repromotion`
  - remote symptom: subprocess exit `-11` during `jit.precompile_all(workers=2)`.
- Latest gdb evidence after the earlier `pass.cpp` null-guard fix:
  - worker thread crashed in `_PyErr_GetRaisedException(tstate=0)`.
  - direct caller was `PyDict_GetItem()` from `Preloader::preload()` while building nested genexpr HIR from `HIRBuilder::inlineGenexprHIR()`.
- Minimal fix in progress:
  - punt nested genexpr HIR inlining during threaded precompile with `RETURN_MULTITHREADED_COMPILE({})`.
  - normal non-threaded compilation still keeps the genexpr inlining path.
  - rationale: worker threads intentionally do not own a `PyThreadState`, so code paths that warm Python dict/global state must not run there.
- GREEN evidence:
  - focused remote entrypoint run:
    - `test_jit_tiering.TieringApiTests.test_compile_failure_backoff_blocks_precompile_all_repromotion`
    - result: `Ran 1 test in 1.699s`, `OK`
  - full tiering remote entrypoint run:
    - `PYTHONPATH=cinderx/PythonLib/test_cinderx $PYTHON -m unittest test_jit_tiering -v`
    - result: `Ran 18 tests in 2.003s`, `OK`
  - broader remote guard:
    - `test_jit_tiering`
    - phase1 OSR guard tests
    - method-with-values polymorphism/delayed-fallback tests
    - normal set/any/tuple genexpr inlining tests
    - result: `Ran 28 tests in 2.748s`, `OK`
- Follow-up threaded-compile hardening:
  - guarded additional optional worker-thread queries that can read Python dict/error state:
    - known callable fallback dict lookup in `resolveKnownCallableObject()`
    - tiny method candidate scanning over globals/type dicts
    - math.sqrt module-dict validation in DCE/refcount/simplify helpers
  - normal non-threaded optimization behavior is still covered by remote tests.
- Final guard after the audit hardening:
  - remote entrypoint command covered full `test_jit_tiering`, phase1 OSR guards, method-with-values guards, tiny bool method optimizations, normal genexpr inlining, and math.sqrt specialization.
  - result: `Ran 34 tests in 3.122s`, `OK`

## Session Update: 2026-05-02 (tier policy state machine and worker audit closure)

- Continued the tiered-JIT functionality quality pass; performance tuning remains paused.
- TDD RED:
  - Added `test_deopt_budget_exhaustion_blocks_repromotion`.
  - Remote focused RED through `/root/work/incoming/remote_update_build_test.sh` failed with `KeyError: 'policy_state'`, proving the per-function API did not yet expose a real policy state.
- Implementation:
  - Added `TierPolicyState` with `ready`, `compile_failure_cooldown`, and `deopt_budget_exhausted`.
  - Exposed `policy_state` through `jit.get_function_tier_state()`.
  - Connected compile-failure backoff and deopt-budget exhaustion to the policy state instead of relying only on free-form reason strings.
  - Preserved policy/backoff telemetry across explicit `force_uncompile()`.
  - Removed stale type-deopt patchers when a compiled runtime owner is removed, fixing a shutdown SIGBUS from `notifyTypeModified()` after explicit uncompile.
  - Added threaded-precompile worker guards for builtin load-method elimination, `checkTranslate()` banned-name checks, split-dict/member-descr field names, tiny helper key-version preparation, and inline-cache stats filename/name initialization.
- Debugging evidence:
  - Repro script printed the expected deopt-budget policy state and then crashed at shutdown.
  - gdb backtrace showed stale `TypeDeoptPatcher*` at `Context::notifyTypeModified()`, with the bad pointer reached from shutdown GC `PyType_Modified()`.
- Remote verification:
  - focused policy/worker guard: `Ran 3 tests in 1.765s`, `OK`
  - full tiering suite: `Ran 20 tests in 3.730s`, `OK`
  - broader ARM guard: `Ran 38 tests in 4.904s`, `OK`

## Session Update: 2026-05-02 (submit-readiness cleanup and review)

- Reviewed the current dirty worktree for a pushable split.
- Fixed a shared `CodeRuntime` lifecycle bug found during review:
  - `force_uncompile()` now preserves shared compiled code while other owners remain active.
  - type-deopt patcher cleanup now happens only when a runtime becomes ownerless.
- Added regression coverage for shared-code invalidation after one owner is explicitly uncompiled.
- Remote verification through `/root/work/incoming/remote_update_build_test.sh`:
  - focused shared-runtime regression: default ARM runtime `Ran 99 tests`, focused test `Ran 1 test`, both `OK`.
  - full tiering suite: default ARM runtime `Ran 99 tests`, `test_jit_tiering` `Ran 21 tests`, both `OK`.
  - submit hygiene: default ARM runtime `Ran 99 tests`, `submit-hygiene-ok files=43`.
- Cleanup:
  - removed stale conflict marker and trailing whitespace from `findings.md`.
  - removed generated `cinderx-update.tar`.
- Review outcome:
  - Main tier-state / worker-safety functionality is now suitable for commit splitting.
  - Object-workload optimization changes should stay as a separate commit or draft slice because performance evidence is mixed.
  - `arm-results/` should remain untracked evidence, not source.

## Session Update: 2026-05-02 (tier policy maturity slice)

- Goal:
  - move tier policy from observable result fields toward explainable decision
    telemetry.
- Selected narrow slice:
  - add promotion decision count
  - add blocked promotion attempt count
  - add last promotion decision
  - add last policy event/reason
- Plan file:
  - `docs/superpowers/plans/2026-05-02-tier-policy-decision-telemetry.md`
- Verification rule:
  - RED and GREEN evidence must use `/root/work/incoming/remote_update_build_test.sh`.
- RED evidence:
  - focused remote entrypoint run covered:
    - `test_function_tier_state_reports_lifecycle`
    - `test_compile_failure_backoff_blocks_precompile_all_repromotion`
  - result failed as expected with:
    - `KeyError: 'promotion_decisions'`
  - this proves the new tests require telemetry not present in the current API.
- Implementation:
  - extended `FunctionTierState` with decision-level policy telemetry.
  - exposed new fields through `jit.get_function_tier_state()`.
  - counted blocked promotion decisions separately from real compile attempts.
- GREEN evidence:
  - focused remote entrypoint:
    - same two tests
    - `Ran 2 tests in 2.392s`
    - `OK`
  - full remote entrypoint:
    - default ARM runtime `Ran 102 tests in 16.246s`, `OK (skipped=3)`
    - full `test_jit_tiering` `Ran 21 tests in 5.309s`, `OK`

## Session Update: 2026-05-02 (tier policy lifecycle completion)

- Goal:
  - complete the tier policy MVP by adding a real compile-failure cooldown
    lifecycle instead of a permanent promotion block.
- Plan file:
  - `docs/superpowers/plans/2026-05-02-tier-policy-lifecycle.md`
- TDD target:
  - add RED coverage for cooldown expiry, allowed re-promotion, and successful
    policy reset before changing production code.
- Implementation completed:
  - added bounded compile-failure cooldown/backoff telemetry to the unified
    per-function tier state.
  - added policy reset on successful optimized compile and on function code
    modification.
  - preserved hot-loop OSR blocking while preventing a single interpreted hot
    loop from consuming the entire compile-failure cooldown.
- Debugging note:
  - focused remote validation initially exposed a test assertion slice bug in
    `test_repeated_compile_failures_grow_policy_backoff`; corrected the test
    to assert the full 12-line lifecycle output.
  - one full-run attempt failed before tests because the remote update tar had
    already been consumed; re-uploaded the current snapshot and reran.
- Verification:
  - focused remote lifecycle set:
    - `test_function_code_change_resets_policy_backoff`
    - `test_compile_failure_backoff_blocks_hot_loop_osr`
    - `test_compile_failure_cooldown_expires_and_allows_repromotion`
    - `test_repeated_compile_failures_grow_policy_backoff`
    - result: `Ran 4 tests in 0.219s`, `OK`
  - full remote entrypoint:
    - default ARM runtime `Ran 102 tests in 16.808s`, `OK (skipped=3)`
    - full `test_jit_tiering` `Ran 24 tests in 5.500s`, `OK`

## Session Update: 2026-05-02 (tier policy lifecycle review hardening)

- Addressed review findings on the lifecycle slice before commit readiness:
  - successful clean optimized compile no longer increments `policy_resets`.
  - cooldown expiry now exposes ready/unblocked state immediately.
  - OSR-only workloads now age cooldown across interpreted activations without
    letting one hot loop burn through cooldown and promote in the same
    activation.
- Debugging sequence:
  - remote RED focused tests caught all three review issues.
  - ARM build rejected direct `code->co_mutable->ncalls` access for Py3.14.
  - `countCalls(code)` built but did not advance reliably for this OSR policy
    path.
  - remote diagnostic showed one `hot(50000)` call performs `50000` OSR policy
    checks, requiring a real per-activation latch.
- Implementation:
  - added a JIT-owned OSR policy epoch and a frame-activation latch in
    `pyjit.cpp`.
  - added internal `compile_failure_osr_resume_deferred` tier state so the
    activation that expires cooldown remains interpreted, and the next
    activation can promote.
- Verification through `/root/work/incoming/remote_update_build_test.sh`:
  - focused review follow-up: `Ran 3 tests in 0.185s`, `OK`
  - full remote entrypoint:
    - default ARM runtime `Ran 102 tests in 16.401s`, `OK (skipped=3)`
    - full `test_jit_tiering` `Ran 26 tests in 5.600s`, `OK`

## Session Update: 2026-05-02 (OSR deferred telemetry maturity)

- Goal:
  - close the remaining observability gap where OSR cooldown expiry defers
    promotion until the next activation, but the deferred state is only
    inferable from behavior.
- Selected slice:
  - expose `compile_failure_osr_resume_deferred` through
    `jit.get_function_tier_state()`.
  - keep semantics unchanged; this is telemetry/API maturity, not performance
    tuning.
- TDD target:
  - add a focused test that observes the second hot-loop activation after
    compile-failure cooldown expiry:
    - `policy_state == "ready"`
    - `promotion_blocked == False`
    - `jit.is_jit_compiled(hot) == False`
    - `compile_failure_osr_resume_deferred == True`
- Implementation:
  - exposed read-only `compile_failure_osr_resume_deferred` from the native
    `jit.get_function_tier_state()` API.
  - kept Python fallback/no-JIT behavior stable by returning
    `compile_failure_osr_resume_deferred == False`.
- Verification through `/root/work/incoming/remote_update_build_test.sh`:
  - RED focused run failed as intended with
    `KeyError: 'compile_failure_osr_resume_deferred'`.
  - first GREEN attempt exposed a test-slice bug (`lines[-11:]` for a
    12-line expected lifecycle); corrected the test to assert the full output.
  - focused GREEN rerun:
    - `test_hot_loop_osr_resume_deferral_is_observable`
    - result: `Ran 1 test in 0.082s`, `OK`
  - full remote entrypoint:
    - default ARM runtime `Ran 102 tests in 16.569s`, `OK (skipped=3)`
    - full `test_jit_tiering` `Ran 27 tests in 5.660s`, `OK`

## Session Update: 2026-05-02 (pending fallback tier-state maturity)

- Goal:
  - close the invalidation/fallback observability gap where type-deopt patching
    had happened but the following runtime fallback had not yet been observed.
- TDD target:
  - extend type invalidation coverage to assert:
    - `fallback_pending == True` immediately after the type patch.
    - `fallback_pending_reason == "type_modified"`.
    - the pending state clears after the first runtime fallback.
- RED evidence:
  - focused remote run failed as intended with:
    - `KeyError: 'fallback_pending'`
- Implementation:
  - added `fallback_pending` and `fallback_pending_reason` to
    `FunctionTierState`.
  - type invalidation now marks pending fallback state.
  - runtime fallback, optimized recompile, and uncompile clear the pending
    fallback state.
  - Python fallback/no-JIT API returns the new fields as `False`/`"none"`.
- Hardening:
  - added `test_uncompile_clears_pending_type_fallback_state` so pending
    fallback telemetry cannot survive explicit uncompile.
  - first hardening run corrected the expected existing transition label from
    `force_uncompile` to `uncompile`.
- Verification through `/root/work/incoming/remote_update_build_test.sh`:
  - focused pair:
    - `test_type_invalidation_updates_tier_state`
    - `test_uncompile_clears_pending_type_fallback_state`
    - result: `Ran 2 tests in 0.145s`, `OK`
  - full remote entrypoint:
    - default ARM runtime `Ran 102 tests in 17.166s`, `OK (skipped=3)`
    - full `test_jit_tiering` `Ran 28 tests in 5.736s`, `OK`

## Session Update: 2026-05-02 (reopt policy gate maturity)

- Goal:
  - close the policy bypass where `reoptFunc()` could reattach existing
    optimized code during enable/resume without consulting deopt budget or
    compile-failure policy.
- TDD target:
  - add a focused RED test that exhausts `Point.getx` deopt budget, runs
    `jit.disable(deopt_all=True)`, then `jit.enable()`, and expects the reopt
    attempt to remain interpreted/deopted and blocked by policy.
- RED evidence:
  - focused remote run failed as intended because `enable()` reoptimized the
    exhausted function:
    - observed `active_tier == "optimized"`
    - observed `compiled == True`
    - observed `last_transition == "optimized"`
- Implementation:
  - `reoptFunc()` now calls
    `shouldAttemptOptimizedPromotion(func, "reopt")` before `finalizeFunc()`.
  - successful reopt records a promotion attempt with reason `reopt`.
  - blocked reopt leaves the function in the deopted/interpreted state.
  - the old stale-deopt cleanup behavior is preserved when no compiled code is
    available to reattach.
- Hardening:
  - added `test_enable_resume_reopts_healthy_deopted_function` to preserve the
    healthy enable/resume path.
- Verification through `/root/work/incoming/remote_update_build_test.sh`:
  - focused blocked reopt:
    - `test_reopt_respects_deopt_budget_exhaustion_on_enable_resume`
    - result: `Ran 1 test in 0.064s`, `OK`
  - focused blocked + healthy pair:
    - `test_reopt_respects_deopt_budget_exhaustion_on_enable_resume`
    - `test_enable_resume_reopts_healthy_deopted_function`
    - result: `Ran 2 tests in 0.114s`, `OK`
  - full remote entrypoint:
    - default ARM runtime `Ran 102 tests in 16.999s`, `OK (skipped=3)`
    - full `test_jit_tiering` `Ran 30 tests in 5.901s`, `OK`

## Session Update: 2026-05-02 (compile-failure taxonomy maturity)

- Goal:
  - distinguish permanent/unsupported JIT compile failures from transient
    resource-style failures in tier policy state.
- TDD target:
  - `jit_suppress()` should produce an unsupported compile failure that blocks
    promotion without aging a transient cooldown/backoff budget.
  - `jit_unsuppress()` should reset that unsupported policy state and allow a
    later optimized compile.
  - max-code-size compile failures must remain on bounded transient cooldown.
- RED evidence through `/root/work/incoming/remote_update_build_test.sh`:
  - focused unsupported-policy test failed as intended under old behavior:
    `cannot_specialize` entered `compile_failure_cooldown` with non-zero
    backoff/cooldown and did not reset through `jit_unsuppress()`.
- Implementation:
  - added `compile_failure_unsupported` as a `TierPolicyState`.
  - classified `cannot_specialize` compile failures as unsupported/permanent
    until code-change style reset.
  - kept max-code-size failures on existing transient cooldown/backoff.
  - made `jit_unsuppress()` call the tier-policy reset hook for the function.
- Focused verification:
  - first compile-failure group rerun found a test assertion slice bug in the
    existing transient cooldown test (`lines[-18:]` for a 20-line lifecycle).
  - after fixing the assertion to `lines[-20:]`, focused compile-failure group
    passed:
    - `test_unsupported_compile_failure_blocks_until_unsuppress`
    - `test_compile_failure_cooldown_expires_and_allows_repromotion`
    - `test_repeated_compile_failures_grow_policy_backoff`
    - result: `Ran 3 tests in 0.153s`, `OK`
- Full verification through `/root/work/incoming/remote_update_build_test.sh`:
  - default ARM runtime `Ran 102 tests in 16.578s`, `OK (skipped=3)`
  - full `test_jit_tiering` `Ran 31 tests in 5.919s`, `OK`

## Session Update: 2026-05-02 (unsupported policy entrypoint hardening)

- Goal:
  - ensure unsupported compile-failure policy is entrypoint-consistent, not
    only correct for direct `force_compile()`.
- Added coverage:
  - `test_precompile_all_unsupported_failure_blocks_later_promotions`.
  - The test makes `precompile_all()` produce the unsupported failure through a
    lazy-registered, `jit_suppress()`ed function.
  - It then verifies later `force_compile()` is policy-blocked without changing
    `compile_failures`, `compile_failure_backoff`, or
    `compile_failure_cooldown_remaining`.
- Verification through `/root/work/incoming/remote_update_build_test.sh`:
  - focused hardening test:
    - `Ran 1 test in 4.488s`, `OK`
  - full remote entrypoint:
    - default ARM runtime `Ran 102 tests in 16.736s`, `OK (skipped=3)`
    - full `test_jit_tiering` `Ran 32 tests in 10.405s`, `OK`

## Session Update: 2026-05-02 (management API policy bypass hardening)

- Gap found during maturity scan:
  - `jit_unsuppress(func)` was resetting tier policy unconditionally.
  - For a function that was never suppressed, this let a management API clear
    compile-failure cooldown/backoff and increment `policy_resets`, effectively
    bypassing policy.
- RED evidence through `/root/work/incoming/remote_update_build_test.sh`:
  - `test_unsuppress_without_suppression_does_not_reset_policy`
  - observed after unsuppress on an unsuppressed cooldown-blocked function:
    - `policy_state == "ready"`
    - `promotion_blocked == False`
    - `compile_failure_backoff == 0`
    - `policy_resets == 1`
    - `last_policy_event == "policy_reset"`
- Implementation:
  - `jit_unsuppress()` now snapshots whether `CI_CO_SUPPRESS_JIT` was set
    before clearing it.
  - tier policy reset is only called when the suppress flag actually changed.
- Verification through `/root/work/incoming/remote_update_build_test.sh`:
  - focused GREEN:
    - `test_unsuppress_without_suppression_does_not_reset_policy`
    - `Ran 1 test in 0.051s`, `OK`
  - suppress/unsupported group:
    - `test_unsupported_compile_failure_blocks_until_unsuppress`
    - `test_precompile_all_unsupported_failure_blocks_later_promotions`
    - `test_unsuppress_without_suppression_does_not_reset_policy`
    - `Ran 3 tests in 4.605s`, `OK`
  - full remote entrypoint:
    - default ARM runtime `Ran 102 tests in 16.580s`, `OK (skipped=3)`
    - full `test_jit_tiering` `Ran 33 tests in 10.504s`, `OK`

## Session Update: 2026-05-02 (dependent static compile policy hardening)

- Gap addressed:
  - compiling a caller could still retry a policy-blocked static dependency
    through the dependent-target loop in `compile_func()`.
  - this bypassed the explainable policy state: the callee's failure counter
    increased again and telemetry reported another compile attempt instead of
    a blocked dependent promotion decision.
- TDD RED:
  - added `test_dependent_compile_respects_unsupported_policy`.
  - first remote run exposed a test-shape issue: bare `exec_static()` globals
    did not register module `m`, so the preloader could not resolve `callee`.
  - after switching the test to a real `types.ModuleType("m")` in
    `sys.modules`, RED failed as intended:
    - `compile_failures` became `2` instead of remaining `1`.
    - telemetry showed `force_compile` / `attempt` instead of
      `dependent_compile` / `blocked`.
- Implementation:
  - gated only `target != func` static dependencies through
    `shouldAttemptPreloadedUnit(target, "dependent_compile")` before
    `compilePreloader()`.
  - primary compile targets still rely on their existing entrypoint policy
    gates, avoiding double-counting.
- Verification through `/root/work/incoming/remote_update_build_test.sh`:
  - focused GREEN:
    - `test_dependent_compile_respects_unsupported_policy`
    - `Ran 1 test in 0.158s`
    - `OK`
  - adjacent policy group:
    - dependent compile, unsupported reset, `precompile_all` unsupported, and
      unsuppress bypass tests
    - `Ran 4 tests in 4.774s`
    - `OK`
  - full remote entrypoint:
    - default ARM runtime:
      - `Ran 102 tests in 16.677s`
      - `OK (skipped=3)`
    - full `test_jit_tiering`:
      - `Ran 34 tests in 10.685s`
      - `OK`

## Session Update: 2026-05-02 (review-minor maturity test closure)

- Reviewer result:
  - no Critical issues.
  - no Important issues.
  - two Minor test gaps identified:
    - unsupported taxonomy reset was mostly covered through `jit_suppress`.
    - shared-runtime pending fallback cleanup needed owner-specific coverage.
- Added coverage:
  - `test_unsupported_code_shape_resets_after_code_change`
    - uses a non-suppressed async-generator function to produce
      `cannot_specialize`.
    - replaces `__code__` with a normal function body.
    - verifies policy reset and later optimized compile.
  - `test_shared_runtime_uncompile_clears_only_that_owner_pending_fallback`
    - compiles two function owners sharing one code runtime.
    - records pending fallback for both after type invalidation.
    - uncompile of one owner clears only that owner's pending state while the
      other remains pending.
- Verification through `/root/work/incoming/remote_update_build_test.sh`:
  - focused shared-runtime pending owner cleanup:
    - `Ran 1 test in 0.072s`
    - `OK`
  - focused reviewer-minor pair:
    - `Ran 2 tests in 0.125s`
    - `OK`
  - full remote entrypoint:
    - default ARM runtime:
      - `Ran 102 tests in 16.890s`
      - `OK (skipped=3)`
    - full `test_jit_tiering`:
      - `Ran 36 tests in 11.422s`
      - `OK`

## Session Update: 2026-05-02 (tier-state maturity closure)

- Goal:
  - close the next tier-state maturity gaps found by independent review.
  - keep the focus on correctness and telemetry quality, not performance.
- Added TDD/coverage:
  - `test_unsupported_failure_does_not_age_with_repeated_attempts`
    - unsupported `cannot_specialize` remains permanent until reset.
    - repeated force attempts increase blocked-attempt telemetry but never
      age into transient cooldown readiness.
  - `test_function_code_change_resets_deopt_budget_exhaustion`
    - RED showed `function_modified` restored deopt-budget policy to ready
      but did not increment `policy_resets`.
  - `test_disable_deopt_all_clears_shared_runtime_pending_fallbacks`
    - shared-runtime owners with pending fallback are both cleaned by explicit
      `disable(deopt_all=True)`.
  - `test_shared_runtime_fallback_clears_only_observed_owner_pending`
    - RED showed one owner observing runtime fallback also cleared the sibling
      owner's pending fallback and incremented sibling fallback stats.
- Implementation:
  - `Context::resetFunctionTierPolicy()` now counts deopt-budget policy reset
    events when no compile-failure policy was present.
  - `recordRuntimeFallback()` now accepts the observed function owner and
    updates only that owner when it belongs to the runtime owner set.
  - the deopt trampoline passes the current frame function to
    `recordRuntimeFallback()`, with the old broadcast behavior retained as a
    fallback when no concrete owner can be identified.
- Remote RED/GREEN through `/root/work/incoming/remote_update_build_test.sh`:
  - first maturity group RED:
    - unsupported permanent block: `ok`
    - deopt-budget code-change reset: `FAIL`
    - disable shared pending cleanup: `ok`
    - failure reason: `policy_resets > 0` expected `True`, observed `False`
  - after deopt-policy reset fix:
    - same 3-test group `Ran 3 tests in 0.186s`, `OK`
  - shared-runtime observed-owner RED:
    - expected sibling owner to remain pending with `runtime_fallbacks == 0`.
    - observed sibling `runtime_fallbacks == 1` and pending cleared.
  - after observed-owner fallback fix:
    - `test_shared_runtime_fallback_clears_only_observed_owner_pending`
    - `Ran 1 test in 0.072s`, `OK`
  - adjacent tier-state regression group after all fixes:
    - new maturity tests plus runtime fallback, deopt-budget exhaustion,
      type invalidation, and shared-runtime pending cleanup
    - `Ran 8 tests in 0.517s`, `OK`
  - final full remote entrypoint:
    - default ARM runtime `Ran 102 tests in 16.235s`, `OK (skipped=3)`
    - full `test_jit_tiering` `Ran 40 tests in 10.999s`, `OK`
  - diff hygiene:
    - `git diff --check` exit code 0
    - only CRLF conversion warnings were reported by Git

## Session Update: 2026-05-02 (runtime fallback owner review follow-up)

- Review follow-up:
  - independent review pointed out that `frameFunction(frame)` can identify an
    inlined callee rather than the root runtime owner, which could still fall
    back to broadcast updates for shared runtimes.
  - added runtime-owner discovery in the deopt trampoline by matching frame
    functions against `CodeRuntime::frameState()` code/builtins/globals.
  - retained owner-set fallback behavior:
    - exact owner match updates one owner.
    - single-owner runtime updates that owner even if the frame match is not
      available.
    - multi-owner runtime without a safe owner match still broadcasts.
- Errors encountered:
  - first remote rebuild failed in `gen_asm.cpp` because Python 3.14 function
    fields are `PyObject*` while runtime frame-state helpers return
    `PyCodeObject*` / `PyDictObject*`; fixed by explicit `PyObject*` casts.
  - first focused rerun used stale class selector `TierPolicyTests`; corrected
    to `TieringApiTests`.
  - second rerun without re-upload failed because the remote entrypoint consumes
    `/root/work/incoming/cinderx-update.tar`; fixed by re-uploading the current
    workspace before invoking the entrypoint.
- Remote focused verification through `/root/work/incoming/remote_update_build_test.sh`:
  - adjacent tier-state regression group after owner-discovery fix:
    - `Ran 8 tests in 0.518s`
    - `OK`
- Full remote verification through `/root/work/incoming/remote_update_build_test.sh`:
  - default ARM runtime:
    - `Ran 102 tests in 16.417s`
    - `OK (skipped=3)`
  - full `test_jit_tiering`:
    - `Ran 40 tests in 11.014s`
    - `OK`
- Diff hygiene:
  - `git diff --check` exit code 0.
  - Git reported CRLF conversion warnings only.
- Review:
  - Sagan final review found no actionable Critical, Important, or Minor
    issues.

## Session Update: 2026-05-03 (pre-commit verification)

- Scope:
  - preparing the tier-state maturity closure for commit and remote push.
  - `arm-results/` remains an untracked evidence directory and was not staged.
- Fresh pre-commit verification:
  - `git diff --check` exit code 0.
  - remote entrypoint `/root/work/incoming/remote_update_build_test.sh`:
    - default ARM runtime `Ran 102 tests in 16.610s`, `OK (skipped=3)`.
    - full `test_jit_tiering` `Ran 40 tests in 11.068s`, `OK`.

## Session Update: 2026-05-03 (pyperformance 30 percent tuning wave)

- Entered performance tuning planning after tier-state maturity closure.
- Defined the expanded JIT-relevant pyperformance benchmark set:
  - `richards,go,deltablue,raytrace,nqueens,generators,coroutines,comprehensions,unpack_sequence,chaos,logging,coverage,nbody,spectral_norm,scimark,float,fannkuch,pickle,pickle_dict,pickle_list,json_dumps,json_loads`
- Defined the stop criterion as candidate-versus-current-JIT-baseline geometric
  mean speedup of at least 30%.
- Added design and implementation-plan docs:
  - `docs/superpowers/specs/2026-05-03-pyperformance-jit-30pct-design.md`
  - `docs/superpowers/plans/2026-05-03-pyperformance-jit-30pct-plan.md`
- Next action:
  - implement benchmark scoreboard/geomean support with TDD-style dry-run
    evidence, then run the current branch extended baseline through the remote
    ARM entrypoint.

## Session Update: 2026-05-03 (scoreboard harness)

- Added RED tests for pyperformance subset tooling:
  - ratio/geomean output in `scripts/arm/compare_pyperf_subset.py`
  - explicit `MODE=nojit` worker support in `scripts/arm/run_pyperf_subset.sh`
- Confirmed local RED with `2 failed`.
- Implemented:
  - per-benchmark time ratio and speedup output
  - geometric mean time ratio and speedup output
  - `MODE=autojit|nojit|jitlist` in the subset runner
- Confirmed local GREEN with `python -m pytest tests/test_pyperf_subset_tools.py -q`:
  - `2 passed in 0.08s`
- Remote entrypoint verification:
  - uploaded working-tree snapshot, excluding `arm-results/`
  - ran `/root/work/incoming/remote_update_build_test.sh`
  - extra command: `python -m pytest tests/test_pyperf_subset_tools.py -q && bash -n scripts/arm/run_pyperf_subset.sh`
  - exit code: `0`
- Next action:
  - run extended current-JIT and no-JIT baseline matrices through the same
    remote entrypoint.

## Session Update: 2026-05-03 (extended baseline matrix)

- Ran the expanded pyperformance matrix through the remote entrypoint:
  - `/root/work/incoming/remote_update_build_test.sh`
  - exit code: `0`
- Produced remote evidence:
  - `/root/work/arm-sync/pyperf_ext_autojit50_20260503_1.json`
  - `/root/work/arm-sync/pyperf_ext_nojit_20260503_1.json`
  - `/root/work/arm-sync/pyperf_ext_nojit_vs_autojit50_20260503_1.json`
- Copied the JSON evidence locally under `arm-results/`; the directory remains
  untracked.
- Important discovery:
  - selected filters expand to 28 concrete pyperformance rows.
  - unfiltered `MODE=autojit AUTOJIT=50` versus no-JIT produced
    `geomean_time_ratio = 6.711393718511059`.
  - only `coverage` was a clear auto-JIT win.
  - broad unfiltered auto-JIT is therefore not the right first optimization
    target; the next step is a filtered `MODE=jitlist` baseline, followed by
    compile-selection / tier-policy ranking.

## Session Update: 2026-05-03 (filtered jitlist baseline)

- First attempt at the filtered matrix failed before benchmarking:
  - archive lacked the expected `cinderx-src/` prefix.
  - inline `POST_PYPERF_CMD` quoting was split by the remote shell.
  - fixed by repackaging the working tree with a `cinderx-src/` prefix and
    using a short remote wrapper script to call the entrypoint.
- Successful remote entrypoint run:
  - `/root/work/incoming/remote_update_build_test.sh`
  - exit code: `0`
- Produced and copied evidence:
  - `/root/work/arm-sync/pyperf_ext_jitlist_20260503_1.json`
  - `/root/work/arm-sync/pyperf_ext_nojit_vs_jitlist_20260503_1.json`
  - `/root/work/arm-sync/pyperf_ext_autojit50_vs_jitlist_20260503_1.json`
- Result:
  - filtered `jitlist` versus unfiltered `autojit50`:
    `geomean_time_ratio = 0.2827850192670735`, about `71.7%` faster.
  - filtered `jitlist` versus no-JIT:
    `geomean_time_ratio = 1.8978816019980658`, still about `89.8%` slower.
- Next action:
  - inspect current pyperformance worker hook and JIT activation policy, then
    rank a production compile-selection / tier-policy candidate before changing
    HIR/LIR internals.

## Session Update: 2026-05-03 (policy probes and ranking)

- Ran `MODE=autojit AUTOJIT=1000` through the remote entrypoint.
  - exit code: `0`
  - versus unfiltered `autojit50`: `geomean_time_ratio = 0.9607331061251834`
  - versus no-JIT: `geomean_time_ratio = 6.447858133614176`
  - conclusion: high threshold alone is not enough.
- Added TDD coverage for filtered delayed jitlist mode:
  - RED: hook ignored `CINDERX_JITLIST_AUTOJIT=50` and still called
    `compile_after_n_calls(0)`.
  - GREEN: added `CINDERX_JITLIST_AUTOJIT` support and
    `MODE=jitlist-autojit`.
  - local verification: `3 passed in 0.06s`.
- Ran `MODE=jitlist-autojit AUTOJIT=50 CINDERX_JITLIST_ENTRIES=__main__:*`
  through the remote entrypoint with the tool tests and shell syntax check.
  - exit code: `0`
  - versus eager `jitlist`: `geomean_time_ratio = 3.3842760938756755`
  - versus unfiltered `autojit50`: `geomean_time_ratio = 0.9570225804117289`
  - versus no-JIT: `geomean_time_ratio = 6.422955334648523`
  - conclusion: delayed jitlist is not useful for this single-value
    pyperformance harness.
- Subagent synthesis:
  - compile-selection/filtering is a real first-order lever.
  - simple global threshold and delayed filtered threshold are not enough.
  - next high-value execution-cost candidate is exact list/tuple/range
    `FOR_ITER` lowering, because filtered JIT still pays generic iterator
    helper costs where the interpreter has specialized opcodes.

## Session Update: 2026-05-03 (FOR_ITER list helper pivot)

- Continued the first execution-cost candidate after remote failures.
- Root-cause from the failed HIR-specialized attempt:
  - remote build succeeded, but the focused GREEN test still reported
    `InvokeIterNext=1`, `InvokeListIterNext=0`, result `10`.
  - diagnostic `PYTHONJITDEBUG=1` showed C++ saw base `FOR_ITER` during
    compilation even when Python adaptive disassembly showed `FOR_ITER_LIST`.
- Decision:
  - stop pursuing a builder-time `FOR_ITER_LIST -> InvokeListIterNext` path for
    now.
  - move the exact list-iterator fast path into existing `JITRT_InvokeIterNext`.
- Code changes in progress:
  - removed the temporary `InvokeListIterNext` HIR/LIR/runtime surface.
  - added an exact `PyListIter_Type` fast path inside `JITRT_InvokeIterNext`.
  - converted the focused ARM runtime test into a semantic guard for list
    iterator mutation behavior under compiled `FOR_ITER`.
- Next action:
  - package the working tree and run focused ARM verification through
    `/root/work/incoming/remote_update_build_test.sh`.
  - if functional verification is green, run a same-harness pyperformance
    comparison to see whether the runtime helper branch is net-positive.

### Error log

- First focused remote validation attempt was invalid before test execution:
  - packaging used a PowerShell binary pipeline, `git archive HEAD | tar -xf -`,
    which corrupted the tar stream and produced repeated
    `tar.exe: Damaged tar archive` messages.
  - local harness sanity still passed after the failed package attempt:
    `python -m pytest tests/test_pyperf_subset_tools.py -q` -> `3 passed`.
  - next attempt must use `git archive -o <file>.tar HEAD` and extract from the
    file, not through a PowerShell pipeline.

## Session Update: 2026-05-03 (list iterator fast path verification)

- Fixed local packaging workflow for remote tests:
  - replaced the bad PowerShell binary pipeline with
    `git archive --format=tar -o <file>.tar HEAD` followed by file extraction.
  - used remote wrapper scripts and `cmd.exe` redirection for long ssh runs so
    normal remote stderr does not abort local PowerShell.
- Remote focused verification through `/root/work/incoming/remote_update_build_test.sh`:
  - `arm-results/list_iter_fastpath_green_20260503_4.log`
  - `Ran 1 test in 0.058s`
  - `OK`
- Remote adjacent verification through the same entrypoint:
  - `arm-results/list_iter_adjacent_green_20260503_2.log`
  - `Ran 8 tests in 0.754s`
  - `OK`
- Remote pyperformance subset through the same entrypoint:
  - `arm-results/list_iter_pyperf_20260503_1.log`
  - output: `arm-results/pyperf_iter_fastpath_jitlist_20260503_1.json`
  - comparison:
    `arm-results/pyperf_ext_jitlist_vs_iter_fastpath_20260503_1.json`
  - `MODE=jitlist`, `SAMPLES=3`
  - subset:
    `comprehensions,generators,nqueens,unpack_sequence,go,deltablue,richards,raytrace`
  - geomean time ratio: `0.9849120157035239`
  - geomean speedup: `1.5087984296476065%`
  - no row exceeded the `5%` regression warning threshold.
- Decision:
  - keep the list iterator helper as a small safe win.
  - continue performance tuning; this is not the 30% target.

## Session Update: 2026-05-03 (tuple/range iterator extension)

- Extended `JITRT_InvokeIterNext` to exact tuple and range iterators:
  - tuple: direct `_PyTupleIterObject` field path plus `PyTuple_GET_ITEM`
  - range: direct `_PyRangeIterObject` field path plus `PyLong_FromLong`
  - all builtin iterator fast paths stay disabled for `Py_GIL_DISABLED`
- Local sanity:
  - `git diff --check`: exit code `0`
  - `python -m pytest tests/test_pyperf_subset_tools.py -q`: `3 passed`
- Remote focused verification:
  - `arm-results/tuple_range_iter_green_20260503_1.log`
  - `Ran 2 tests in 0.119s`
  - `OK`
- Remote adjacent verification:
  - `arm-results/tuple_range_iter_adjacent_green_20260503_1.log`
  - `Ran 9 tests in 0.817s`
  - `OK`
- Remote pyperformance subset:
  - `arm-results/tuple_range_iter_pyperf_20260503_1.log`
  - comparison:
    `arm-results/pyperf_ext_jitlist_vs_iter_all_fastpath_20260503_1.json`
  - `geomean_time_ratio = 0.9855222065914018`
  - `geomean_speedup_pct = 1.4477793408598227%`
  - no row exceeded the `5%` regression warning threshold.
- Decision:
  - keep the builtin iterator helper family as a small safe improvement.
  - next candidate must target a larger cost center than generic iterator
    helper internals.

## Session Update: 2026-05-03 (loop-heavy policy simulation)

- Built a loop-heavy jitlist simulation using the existing pyperformance hook,
  saved at `arm-results/loop_heavy_jitlist_entries.txt`.
- Remote pyperformance subset through `/root/work/incoming/remote_update_build_test.sh`:
  - log: `arm-results/loop_heavy_pyperf_20260503_1.log`
  - result: `arm-results/pyperf_loop_heavy_jitlist_20260503_1.json`
  - comparisons:
    - `arm-results/pyperf_ext_jitlist_vs_loop_heavy_20260503_1.json`
    - `arm-results/pyperf_ext_nojit_vs_loop_heavy_20260503_1.json`
- Result versus full eager `jitlist`:
  - `geomean_time_ratio = 0.7474786908573173`
  - `geomean_speedup_pct = 25.252130914268268%`
  - big wins:
    - `comprehensions`: `80.8348%`
    - `deltablue`: `50.6325%`
  - blocker:
    - `go`: `-19.1681%` regression
- Decision:
  - compile-selection policy is the main lever.
  - continue with a refined policy simulation that keeps loop-heavy wins but
    restores go/object helper coverage.

## Session Update: 2026-05-03 (refined policy simulation)

- Built a refined jitlist simulation:
  - start from loop-heavy entries
  - add all `go` tiny/object helper methods
  - omit `generators` and `richards` entries
  - saved at `arm-results/refined_policy_jitlist_entries.txt`
- Remote pyperformance subset through `/root/work/incoming/remote_update_build_test.sh`:
  - log: `arm-results/refined_policy_pyperf_20260503_1.log`
  - result: `arm-results/pyperf_refined_policy_jitlist_20260503_1.json`
  - comparisons:
    - `arm-results/pyperf_ext_jitlist_vs_refined_policy_20260503_1.json`
    - `arm-results/pyperf_ext_nojit_vs_refined_policy_20260503_1.json`
- Result versus full eager `jitlist`:
  - `geomean_time_ratio = 0.775399315072543`
  - `geomean_speedup_pct = 22.460068492745698%`
  - `go` recovered to `0.6173%` speedup versus full eager `jitlist`
  - blockers:
    - `generators`: `-14.4289%`
    - `richards`: `-30.4581%`
- Decision:
  - do not pursue a single positive-entry profile.
  - next code-level candidate should be a generated-code/tiny-shape negative
    policy with telemetry, then validate whether it keeps the clean
    comprehension/deltablue wins without broad regressions.

## Session Update: 2026-05-03 (tiny helper filter TDD)

- Replaced the weak generated-`<listcomp>` characterization with a focused
  opt-in tiny-helper scheduling test:
  - `ArmRuntimeTests.test_tiny_helper_filter_skips_small_no_backedge_code`
  - shape: wildcard `__main__:*` JIT list plus `PYTHONJITFILTERTINY=1`
  - expected: loop-bearing `outer` compiles, tiny no-backedge
    `tiny_predicate` remains interpreted.
- RED verification through `/root/work/incoming/remote_update_build_test.sh`:
  - log: `arm-results/tiny_filter_red_20260503_1.log`
  - result: failed as expected with stdout `True` / `True`
  - reason: current scheduler ignores `PYTHONJITFILTERTINY`, so the tiny
    helper is still compiled.
- Implementation direction:
  - add a default-off scheduler filter in `scheduleJitCompile()`
  - count instructions with `BytecodeInstructionBlock`
  - skip only tiny functions with no backward jump
  - keep explicit `force_compile()` unaffected because it bypasses the
    scheduler.
- GREEN verification through the same remote entrypoint:
  - focused log: `arm-results/tiny_filter_green_20260503_1.log`
  - result: `Ran 1 test in 0.059s`, `OK`
  - adjacent log: `arm-results/tiny_filter_adjacent_green_20260503_1.log`
  - result: `Ran 11 tests in 0.946s`, `OK`
  - adjacent set covered the tiny filter, explicit force-compile escape hatch,
    builtin iterator helper fast paths, and generator-expression HIR guards.

### Error log

- First pyperformance attempt for the tiny filter did not reach the remote
  entrypoint:
  - failure: `bash: -c: line 1: unexpected EOF while looking for matching "\""`
  - cause: nested SSH quoting around a long `POST_PYPERF_CMD`
  - next attempt must upload a remote wrapper script and execute that wrapper,
    rather than embedding the whole post command in one SSH string.
- Retried pyperformance with a remote wrapper script:
  - log: `arm-results/tiny_filter_pyperf_20260503_2.log`
  - comparison:
    `arm-results/pyperf_ext_jitlist_vs_tiny_filter_20260503_2.json`
  - result versus full eager `jitlist`:
    `geomean_time_ratio = 0.9904433303920432`
  - `raytrace` regressed `8.7154%`
  - conclusion: blanket tiny/no-backedge filtering is not the main performance
    lever; continue with threshold and loop-heavy/object-helper policy probes.
- Threshold scout through the remote entrypoint:
  - log: `arm-results/tiny_filter_threshold_scout_20260503_1.log`
  - `PYTHONJITFILTERTINY=16`: geomean ratio `0.98243798561696`
  - `PYTHONJITFILTERTINY=32`: geomean ratio `0.9836673858208844`
  - `PYTHONJITFILTERTINY=64`: geomean ratio `0.9202948497851511`
  - conclusion: higher no-backedge filtering is still far from 30% and creates
    object-workload regressions.
- Loop-heavy plus go-helper policy simulation:
  - log: `arm-results/loop_go_policy_pyperf_20260503_1.log`
  - comparison:
    `arm-results/pyperf_ext_jitlist_vs_loop_go_policy_20260503_1.json`
  - geomean ratio `1.0277203637549255`
  - conclusion: static global positive jitlists are fragile because benchmark
    helpers all run under `__main__`, so names collide across workloads.

## Session Update: 2026-05-03 (shape profitability scheduler filter)

- Implemented default-off opt-in scheduler policy flags:
  - `PYTHONJITFILTERTINY` / `jit-filter-tiny`
  - `PYTHONJITSHAPEPROFITFILTER` / `jit-shape-profit-filter`
- Added bytecode-shape scanning in `scheduleJitCompile()`:
  - tiny/no-backedge filter
  - call/method/make_function/no-backedge shape filter
  - explicit unpack-shape admission
- Addressed subagent review finding:
  - moved policy filters after `trackEligibleCodeObjects()`, `isJitCompiled()`,
    and `reoptFunc()`
  - added `test_shape_profit_filter_does_not_block_reopt_attachment`
- Local sanity:
  - `git diff --check`: exit code `0`
  - `python -m pytest tests/test_pyperf_subset_tools.py -q`: `3 passed`
- Remote RED/GREEN through `/root/work/incoming/remote_update_build_test.sh`:
  - RED shape policy:
    `arm-results/shape_profit_filter_red_20260503_1.log`
  - RED reopt regression:
    `arm-results/shape_profit_reopt_red_20260503_1.log`
  - focused GREEN:
    `arm-results/shape_profit_focused_green_20260503_1.log`,
    `Ran 2 tests in 0.116s`, `OK`
  - adjacent GREEN:
    `arm-results/shape_profit_adjacent_green_20260503_2.log`,
    `Ran 13 tests in 1.035s`, `OK`
- Remote pyperformance:
  - log: `arm-results/shape_profit_pyperf_20260503_2.log`
  - comparison:
    `arm-results/pyperf_ext_jitlist_vs_shape_profit_20260503_1.json`
  - result versus full eager `jitlist`:
    `geomean_time_ratio = 0.9653445942580665`
  - wins: `comprehensions`, `deltablue`, `unpack_sequence`, `raytrace`
  - regressions: `nqueens`, `richards`, `go`, `generators`
- Decision:
  - keep the opt-in mechanics/tests as useful scaffolding.
  - do not treat the current shape policy as the 30% answer; the next round
    needs per-workload/function-shape evidence for nqueens/go/richards recovery
    while preserving comprehension/deltablue/unpack wins.
- Error log:
  - `shape_profit_adjacent_green_20260503_1.log`: remote tar already consumed.
  - `shape_profit_pyperf_20260503_1.log`: wrapper tried to execute a
    non-executable script directly; fixed by invoking it through `bash`.
- State-helper admission retry:
  - [x] added opt-in `PYTHONJITADMITSTATEHELPERS` / `jit-admit-state-helpers`
  - [x] verified RED/GREEN for subscript-state helper admission under `PYTHONJITFILTERTINY=9999`
  - [x] rejected broad attr+subscript admission after matrix regression
  - [x] tightened to subscript-only and reran focused/adjacent remote GREEN
  - [x] reran object-heavy pyperformance matrix through the remote entrypoint
  - result versus full eager `jitlist`:
    - `geomean_time_ratio = 0.886298242152134`
    - `geomean_speedup_pct = 11.370175784786596`
    - blockers: `go -24.64%`, `richards -6.23%`
  - decision: keep only as opt-in experimental scaffolding for now; move to
    dynamic delayed helper promotion because static admission is not recovering
    object-helper workloads.

## Session Update: 2026-05-03 (deferred helper promotion + harness correction)

- Dynamic delayed helper promotion:
  - [x] focused remote GREEN:
    `arm-results/stateful_deferred_shape_green_20260503_2.log`,
    `Ran 1 test in 0.056s`, `OK`
  - [x] corrected adjacent verification invocation after a bad `unittest`
    module path attempt
  - [x] full tiering verification with precise module:
    `arm-results/stateful_deferred_tiering_green_20260503_1.log`,
    `Ran 40 tests in 11.035s`, `OK`
- Benchmark harness:
  - [x] detected suspect matrix where `nojit`, `jitlist`, and `autojit` were
    nearly identical
  - [x] TDD RED for missing explicit `CINDERX_DISABLE=0` worker override
  - [x] fixed `scripts/arm/run_pyperf_subset.sh` to inherit
    `CINDERX_DISABLE` and default worker JIT modes to `0`
  - [x] local GREEN: `python -m pytest tests/test_pyperf_subset_tools.py -q`,
    `3 passed in 0.07s`
  - [x] remote worker probe:
    `arm-results/worker_probe_20260503_2.log`
    proves nojit disables JIT and autojit/jitlist compile a probe function
- Latest pyperformance evidence:
  - fixed `nojit` vs `autojit0`:
    `arm-results/pyperf_fixed_nojit_vs_autojit0_20260503_1.json`,
    geomean speedup `-0.123%`
  - fixed `nojit` vs `autojit50`:
    `arm-results/pyperf_fixed_nojit_vs_autojit50_20260503_1.json`,
    geomean speedup `-0.854%`
  - fixed `autojit50` vs `stateful_deferred_global50`:
    `arm-results/pyperf_fixed_autojit50_vs_stateful_deferred_global50_20260503_1.json`,
    geomean speedup `0.444%`
  - interpretation: current selected `--debug-single-value` subset is not yet a
    reliable optimization target because it does not show measurable JIT/no-JIT
    separation despite the worker probe compiling functions.
- Next action:
  - collect per-benchmark compile evidence or run a hotter pyperformance mode
    before claiming benchmark speedups.

## Session Update: 2026-05-03 (credible matrix after worker venv fix)

- Fixed the remaining pyperformance worker mismatch:
  - the wrapper now creates the declared pyperformance venv when absent.
  - the wrapper installs the freshly built CinderX wheel into the actual worker
    Python before timing.
  - probe/debug envs are forwarded only when requested.
- Remote evidence through `/root/work/incoming/remote_update_build_test.sh`:
  - `arm-results/richards_probe_pyperf_20260503_3.log`
  - `arm-results/richards_autojit0_probe_20260503_3.jsonl`
  - `arm-results/credible_matrix_20260503_1.log`
- Key result:
  - no-JIT vs autojit0: `geomean_speedup_pct = -313.567%`.
  - no-JIT vs autojit50: `geomean_speedup_pct = -1607.366%`.
  - autojit50 vs stateful deferred autojit50:
    `geomean_speedup_pct = 12.781%`, no >=5% row regressions.
  - no-JIT vs stateful deferred autojit50:
    `geomean_speedup_pct = -1389.148%`.
- Decision:
  - do not claim pyperformance improvement yet.
  - current code proves a useful direction only relative to broad autojit50.
  - next run: filtered `jitlist` / `jitlist-autojit` after the venv fix to
    isolate compile-selection value from general JIT overhead.

## Session Update: 2026-05-03 (corrected jitlist matrix)

- Ran a fresh corrected compile-selection matrix through
  `/root/work/incoming/remote_update_build_test.sh`.
- Same run passed functional gates:
  - `Ran 110 tests in 17.480s`, `OK (skipped=3)`.
  - `jit-effective-ok compiled_size 976 interp_calls 10`.
- Remote generated JSON files under `/root/work/arm-sync`, but local `scp`
  failed afterward because SSH returned `Connection refused`; results below
  were parsed from the complete local remote-entrypoint log.
- Key parsed results:
  - no-JIT vs eager `jitlist __main__:*`:
    `geomean_speedup_pct = -311.819%`.
  - no-JIT vs `jitlist-autojit50`:
    `geomean_speedup_pct = -1610.707%`.
  - `jitlist-autojit50` vs stateful deferred `jitlist-autojit50`:
    `geomean_speedup_pct = 12.184%`.
- Decision:
  - compile-selection via plain `__main__:*` is not enough.
  - next optimization target is a mature cold-workload/tier policy gate:
    avoid compiling generated/short-lived code inside the timed window unless
    runtime evidence shows compile cost can be amortized.

## Session Update: 2026-05-03 (generated-code cold filter TDD started)

- Added RED coverage for the next cold-workload policy slice:
  - wrapper contract now expects `PYTHONJITFILTERGENERATED` to be forwarded to
    pyperformance workers.
  - ARM runtime behavior test expects `outer` to compile while `<listcomp>`
    stays interpreted under the generated-code filter.
- Local RED/GREEN:
  - RED:
    `python -m pytest tests/test_pyperf_subset_tools.py::test_run_pyperf_subset_supports_explicit_nojit_worker_mode -q`
    failed on missing `PYTHONJITFILTERGENERATED`.
  - GREEN:
    `python -m pytest tests/test_pyperf_subset_tools.py -q`
    showed `4 passed`.
  - `git diff --check` returned exit code `0`.
- Implemented default-off generated-code filter:
  - `PYTHONJITFILTERGENERATED` / `jit-filter-generated`.
  - scheduler skips `<listcomp>`, `<dictcomp>`, `<setcomp>`, and `<genexpr>`
    code objects before tiny/shape filters.
  - explicit force-compile remains outside this scheduler filter.
- Blocker:
  - remote SSH to `124.70.162.35` is currently timing out after the corrected
    jitlist matrix completed.
  - generated-code filter still needs remote ARM RED/GREEN and benchmark
    validation before it can be considered complete.

## Session Update: 2026-05-03 (generated-code cold filter remote GREEN)

- Remote recovered and the generated-code filter was validated through the
  unified ARM entrypoint.
- Evidence:
  - `arm-results/generated_filter_green_20260503_1.log`
  - default ARM runtime: `Ran 111 tests in 17.005s`, `OK (skipped=3)`
  - focused generated-code filter test:
    `test_generated_code_filter_skips_comprehension_code ... ok`
  - JIT effectiveness smoke:
    `jit-effective-ok compiled_size 976 interp_calls 10`
- Next action:
  - run the corrected pyperformance matrix with `PYTHONJITFILTERGENERATED=1`
    and compare against unfiltered `jitlist` / `jitlist-autojit50`.

## Session Update: 2026-05-03 (generated-code cold filter matrix)

- Ran the generated-filter matrix through the unified remote entrypoint.
- Local pre-matrix checks:
  - `python -m pytest tests/test_pyperf_subset_tools.py -q`: `4 passed`
  - `python -m py_compile scripts/arm/pyperf_env_hook/sitecustomize.py scripts/arm/compare_pyperf_subset.py`: exit `0`
  - `git diff --check`: exit `0` with only LF/CRLF warnings
- Remote evidence:
  - log: `arm-results/generated_filter_matrix_20260503_1.log`
  - JSONs: `arm-results/generated_filter_matrix_20260503_1_*.json`
  - worker probe: CinderX initialized and JIT enabled
- Result:
  - `jitlist` vs `generated_jitlist`:
    `geomean_speedup_pct = 0.830%`
  - `jitlist` vs generated+stateful deferred `jitlist`:
    `geomean_speedup_pct = 13.203%`, but `go` and `richards` regressed beyond
    the 5% gate
  - `jitlist-autojit50` vs generated+stateful deferred `jitlist-autojit50`:
    `geomean_speedup_pct = 13.669%`, no >=5% regressions
- Decision:
  - generated filtering is safe and measurable but too small.
  - the next optimization should focus on object/state method-call execution
    cost or a more selective object policy, because the current policy wins are
    blocked mainly by `go` and `richards`.

## Session Update: 2026-05-03 (attr-state deferred helper promotion)

- Chose the next TDD slice from matrix evidence:
  - broaden dynamic deferred helper promotion to attr-state `self` methods.
  - intended to recover `go`/`richards` from the tiny/no-backedge policy while
    preserving wins on `deltablue`, `nqueens`, and `raytrace`.
- RED:
  - `arm-results/attr_helper_deferred_red_20260503_1.log`
  - focused test failed as expected at `Worker.set_waiting`, which was not
    marked `helper_promotion_deferred`.
- GREEN:
  - implemented attribute load/store opcode detection for simple `self`
    methods in the deferred-helper classifier.
  - `arm-results/attr_helper_deferred_green_20260503_1.log`
  - focused result: `Ran 1 test in 0.057s`, `OK`.
- Performance validation:
  - `arm-results/attr_helper_matrix_20260503_1.log` started, but the remote
    host closed the SSH connection during build and now refuses SSH.
  - next action after remote recovery: rerun the attr-helper matrix before
    making any performance claim.

## Session Update: 2026-05-03 (attr-state matrix after remote recovery)

- Remote recovered; reran the attr-state matrix through
  `/root/work/incoming/remote_update_build_test.sh`.
- Evidence:
  - log: `arm-results/attr_helper_matrix_20260503_2.log`
  - JSONs: `arm-results/attr_helper_matrix_20260503_1_*.json`
- Result:
  - `jitlist` vs generated+stateful deferred `jitlist`:
    `geomean_speedup_pct = 12.747%`.
  - `go` improved to only `-2.90%` and `richards` to `-4.29%`,
    but `raytrace` regressed `-18.51%`.
  - `jitlist-autojit50` vs generated+stateful deferred:
    `geomean_speedup_pct = 7.422%`; `raytrace` still regressed `-11.39%`.
- Decision:
  - do not treat the broad attr-state classifier as complete.
  - next step: narrow deferred attr-helper promotion so it still recovers
    object-state helpers in `go`/`richards` but avoids raytrace-like
    attr-heavy numeric/geometric helpers.

## Session Update: 2026-05-03 (attr classifier refinement)

- Implemented and validated progressively narrower attr-helper classifiers:
  - store-only attr helpers: fixes raytrace but misses richards predicates.
  - simple state predicates: still missed richards 3.14 boolean scaffold.
  - complex state predicates: includes `COPY`, `POP_TOP`, and `NOT_TAKEN`.
- Remote focused evidence:
  - `attr_helper_refined_red_20260503_1.log` / `attr_helper_refined_green_20260503_1.log`
  - `attr_predicate_helper_red_20260503_1.log` / `attr_predicate_helper_green_20260503_2.log`
  - `attr_complex_predicate_red_20260503_1.log` / `attr_complex_predicate_green_20260503_1.log`
- Remote matrix evidence:
  - `attr_store_helper_matrix_20260503_1.log`
  - `attr_predicate_helper_matrix_20260503_1.log`
  - `attr_complex_predicate_matrix_20260503_1.log`
- Current best attr refinement:
  - complex predicate classifier.
  - `jitlist-autojit50` comparison: `11.32%` geomean speedup, no >5%
    regressions.
  - eager `jitlist` still has `go -7.15%` and `richards -6.05%`.
- Next action:
  - run a promotion-threshold matrix for the complex classifier. Hypothesis:
    threshold `1024` is too late for eager `jitlist` go/richards.

## Session Update: 2026-05-03 (promotion threshold sweep)

- Ran threshold sweep through the unified remote entrypoint:
  - log: `arm-results/attr_threshold_matrix_20260503_1.log`
  - JSONs: `arm-results/attr_threshold_matrix_20260503_1_*.json`
- Best setting found:
  - `PYTHONJITDEFERFILTEREDHELPERS=512`
  - eager `jitlist`: `12.59%` geomean speedup, no >5% regressions.
  - `jitlist-autojit50`: `11.59%` geomean speedup, no >5% regressions.
- Interpretation:
  - the complex attr classifier is now stable enough for the opt-in policy
    experiment.
  - performance is still well short of the 30% target.
  - next axis: sweep `PYTHONJITFILTERTINY` with helper threshold fixed at 512.

## Session Update: 2026-05-03 (tiny-filter threshold sweep)

- Created `arm-results/run_tiny_threshold_matrix_20260503_1.sh` to sweep
  `PYTHONJITFILTERTINY` independently while fixing
  `PYTHONJITDEFERFILTEREDHELPERS=512`.
- Local validation before remote:
  - `python -m pytest tests/test_pyperf_subset_tools.py -q`: `4 passed`
  - `python -m py_compile scripts/arm/pyperf_env_hook/sitecustomize.py scripts/arm/compare_pyperf_subset.py`: exit `0`
  - `git diff --check`: exit `0`, only CRLF warnings
  - local `bash -n` could not be used because WSL has no installed distro;
    remote `bash -n /root/work/incoming/run_tiny_threshold_matrix_20260503_1.sh`
    passed instead.
- Remote validation:
  - entrypoint: `/root/work/incoming/remote_update_build_test.sh`
  - build env: `CINDERX_BUILD_JOBS=8 PARALLEL=8`
  - log: `arm-results/tiny_threshold_matrix_20260503_1.log`
  - JSONs: `arm-results/tiny_threshold_matrix_20260503_1_*.json`
- Result:
  - eager `jitlist` best 3-sample candidates:
    - `PYTHONJITFILTERTINY=9999`: `15.80%` geomean, `go -5.32%`
    - `PYTHONJITFILTERTINY=256`: `15.73%` geomean, `go -5.93%`
    - `PYTHONJITFILTERTINY=64`: `14.32%` geomean, `go -5.54%`
  - `jitlist-autojit50` best safe candidate:
    - `PYTHONJITFILTERTINY=9999`: `11.37%` geomean, no >5% regressions.
- Decision:
  - tiny-filter threshold tuning improves eager geomean versus the previous
    threshold sweep, but still does not approach the 30% target.
  - run a higher-sample confirmation for `64/128/256/9999` before treating the
    `go` regression as real or noise.

## Session Update: 2026-05-03 (tiny-filter confirmation)

- Ran higher-sample confirmation through the unified remote entrypoint:
  - log: `arm-results/tiny_threshold_confirm_20260503_1.log`
  - JSONs: `arm-results/tiny_threshold_confirm_20260503_1_*.json`
  - env: `CINDERX_BUILD_JOBS=8 PARALLEL=8`
  - samples: `5`
  - candidate tiny limits: `64`, `128`, `256`, `9999`
- Result:
  - eager `jitlist` still has stable `go` regressions:
    - limit `64`: `12.28%` geomean, `go -7.27%`
    - limit `128`: `14.32%` geomean, `go -7.50%`
    - limit `256`: `14.39%` geomean, `go -7.06%`
    - limit `9999`: `14.65%` geomean, `go -7.92%`
  - `jitlist-autojit50` remains safe but tops out near `11.11%` geomean.
- Decision:
  - policy threshold tuning alone is not enough for the 30% target.
  - next action: collect function-level telemetry for `go` under eager baseline
    versus generated/stateful-deferred policy to identify missing recovery or
    slower compiled call shapes.

## Session Update: 2026-05-03 (go policy telemetry)

- Added and ran `arm-results/run_go_policy_probe_20260503_1.sh` through the
  unified remote entrypoint.
- Remote evidence:
  - log: `arm-results/go_policy_probe_20260503_1.log`
  - JSONs: `arm-results/go_policy_probe_20260503_1_*.json`
  - env: `CINDERX_BUILD_JOBS=8 PARALLEL=8`
- Result:
  - eager `jitlist`: `compiled_count=83`, `not_compiled=4`.
  - deferred policy with helper threshold `512`: `compiled_count=23-25`,
    `not_compiled=18`, `deferred=8`, `ready=0`.
  - affected helpers include `Board.move`, `EmptySet.add/remove/set`, and
    `Square.find`, all stuck in `helper_promotion_deferred`.
- Decision:
  - the next slice should test lower helper-promotion thresholds for `go`
    telemetry before changing policy code.

## Session Update: 2026-05-03 (go helper-threshold telemetry)

- Extended the go policy probe with helper thresholds `256` and `128` while
  keeping `PYTHONJITFILTERTINY=9999`.
- Remote evidence:
  - log: `arm-results/go_policy_probe_20260503_2.log`
  - JSONs: `arm-results/go_policy_probe_20260503_2_*.json`
- Result:
  - `policy_h256_l9999`: `compiled_count=23`, `deferred=8`, `ready=0`.
  - `policy_h128_l9999`: `compiled_count=23`, `deferred=8`, `ready=0`.
  - the same `go` helpers remain stuck in deferred state:
    `Board.move`, `Square.find`, `EmptySet.add/remove/set`,
    `ZobristHash.update`.
- Decision:
  - helper thresholds `128+` are still too late for pyperformance `go`.
  - next action: run a go-only pyperformance scout over lower helper thresholds
    `4/8/16/32/64`.

## Session Update: 2026-05-03 (go lower-threshold scout)

- Ran the go-only lower helper-threshold scout through the unified remote
  entrypoint with exclusive remote build parallelism:
  - log: `arm-results/go_helper_threshold_scout_20260503_1.log`
  - JSONs: `arm-results/go_helper_threshold_scout_20260503_1_*.json`
  - env: `CINDERX_BUILD_JOBS=8 PARALLEL=8`
- Result:
  - eager `jitlist` remains negative for every tested threshold `4-512`; best
    point is still `go -6.46%` at threshold `512`.
  - `jitlist-autojit50` is closer to neutral but still negative; best point is
    `go -1.83%` at threshold `16`.
- Follow-up diagnostic:
  - warmed `go` bytecode shows many
    `LOAD_ATTR_METHOD_WITH_VALUES + CALL_PY_EXACT_ARGS/CALL_KW_PY` sites.
  - current eager HIR still has generic `LoadMethodCached/CallMethod` in hot
    functions such as `Board.move`, `Square.move`, `Board.useful`, and
    `UCTNode.play`.
- Decision:
  - stop spending cycles on helper threshold tuning for now.
  - next action: TDD a focused method-with-values specialized-call fast-path
    test, then patch `HIRBuilder` if the RED confirms the missing lowering.

## Session Update: 2026-05-03 (attr-derived MWV delayed lookup)

- Added RED coverage for attr-derived method-with-values calls with simple
  positional args.
  - RED log: `arm-results/mwv_attr_derived_red_20260503_2.log`
  - failure: `VectorCall<3>` was after `LoadMethodCached`.
- Implemented a narrow HIRBuilder change:
  - delay lookup for PyFunction method-with-values calls with `1-3`
    side-effect-free positional args.
  - recognize `LOAD_FAST_LOAD_FAST` and
    `LOAD_FAST_BORROW_LOAD_FAST_BORROW`.
  - keep zero-arg calls on the old path after a Richards crash proved they can
    expose unsafe fallback FrameStates with uninitialized locals.
- Verification:
  - `arm-results/mwv_richards_crash_fix_20260503_2.log`:
    focused tests passed and direct Richards repro printed
    `direct-richards-ok`.
  - `arm-results/mwv_adjacent_green_20260503_2.log`:
    adjacent method-with-values regression suite `Ran 8 tests`, `OK`.
- Matrix:
  - `arm-results/candidate_mwv_delayed_matrix_20260503_2.log`
  - selected 8 benchmarks, `3` samples.
  - policy versus `jitlist-autojit50`: `+10.93%` geomean, no >5%
    regressions, with `go -1.81%`.
- Decision:
  - keep the fix as a safe call-shape quality improvement.
  - continue performance work; next likely slice is keyword
    method-with-values calls (`CALL_KW_PY`) that still remain generic in `go`.

## Session Update: 2026-05-03 (keyword MWV delayed lookup)

- Used the exclusive ARM host with multi-threaded remote builds:
  - env: `CINDERX_BUILD_JOBS=8 PARALLEL=8`
  - entrypoint: `/root/work/incoming/remote_update_build_test.sh`
- Implemented keyword method-with-values lowering:
  - `CALL_KW` is accepted by the delayed lookup classifier for simple
    side-effect-free argument shapes.
  - the keyword-name tuple is preserved as the final vectorcall operand.
  - zero-arg method calls remain excluded after the Richards crash found in the
    positional broadening pass.
- Verification:
  - `arm-results/mwv_kw_green_20260503_4.log`:
    default ARM runtime `Ran 114 tests`, `OK`; focused KW test `Ran 1 test`,
    `OK`.
  - `arm-results/mwv_adjacent_green_20260503_3.log`:
    default ARM runtime `Ran 114 tests`, `OK`; adjacent MWV suite
    `Ran 10 tests`, `OK`.
  - `arm-results/mwv_richards_direct_green_20260503_1.log`:
    default ARM runtime `Ran 114 tests`, `OK`; direct repro printed
    `direct-richards-ok`.
- Matrix:
  - `arm-results/candidate_mwv_kw_matrix_20260503_1.log`
  - selected 8 benchmarks, `3` samples.
  - policy versus eager `jitlist`: `+15.38%` geomean, but `go -8.86%`.
  - policy versus `jitlist-autojit50`: `+10.87%` geomean, no >5%
    regressions, `go -0.76%`.
- Decision:
  - keep the KW lowering on correctness/quality grounds.
  - the 30% selected-workload performance target is still not met.
  - next action: collect post-KW HIR telemetry for remaining generic method
    calls and non-call overhead in the hot `go` functions before choosing the
    next implementation slice.

## Session Update: 2026-05-03 (deopt miss candidate rejected)

- Tested a follow-up candidate: replace delayed method-with-values generic
  miss fallback with a direct deopt path.
- TDD/diagnostics:
  - RED: `arm-results/mwv_deopt_miss_red_20260503_3.log`.
  - first GREEN attempt exposed a real polymorphic-self regression.
  - refined version kept non-exact `self` on generic fallback and only used
    deopt-on-miss for attr-derived delayed lookup.
  - focused remote GREEN:
    `arm-results/mwv_deopt_miss_focused_green_20260503_1.log`,
    default ARM runtime `Ran 115 tests`, `OK`; focused set `Ran 5 tests`,
    `OK`.
- HIR signal:
  - `arm-results/go_hir_post_deopt_miss_probe_20260503_1.log`
  - static fallback counts dropped in several `go` functions, for example
    `Square.move CallMethod 4 -> 1` and `UCTNode.play 5 -> 3`.
- Benchmark result:
  - `arm-results/candidate_mwv_deopt_miss_matrix_20260503_1.log`
  - direct comparison to the prior KW candidate was negative:
    policy `jitlist` geomean `-3.85%`; policy `jitlist-autojit50` geomean
    `-3.97%`.
- Decision:
  - reverted this candidate.
  - post-revert remote guard:
    `arm-results/mwv_final_adjacent_green_20260503_1.log`,
    default ARM runtime `Ran 114 tests`, `OK`; adjacent MWV suite
    `Ran 10 tests`, `OK`.
  - continue from the KW delayed lookup baseline, not the deopt-only miss path.

## Session Update: 2026-05-03 (selective method-value inliner rejected as default)

- Used the exclusive ARM host with multi-threaded remote builds:
  - env: `CINDERX_BUILD_JOBS=8 PARALLEL=8`
  - entrypoint: `/root/work/incoming/remote_update_build_test.sh`
- Implemented and verified an opt-in selective method-value HIR inliner:
  - only `VectorCall` sites marked as profiled method-with-values are eligible
    when `PYTHONJITENABLEMETHODVALUEINLINER=1` and global HIR inliner is off.
  - generic static-function inlining remains disabled in this mode.
- Correctness:
  - a raytrace-like polymorphic receiver bug was reproduced and fixed by not
    rewriting the direct exact-receiver fast path into the inlinable shape.
  - `arm-results/method_value_selective_safe_green_20260503_2.log`:
    default ARM runtime `Ran 118 tests`, `OK`; focused method-value suite
    `Ran 4 tests`, `OK`; JIT smoke passed.
- Matrix:
  - `arm-results/method_value_selective_safe_matrix_20260503_1.log`
  - policy baseline versus policy +
    `PYTHONJITENABLEMETHODVALUEINLINER=1`.
  - selected workload geomean: `-1.97%`.
  - wins: `generators +5.59%`, `raytrace +0.37%`.
  - regressions: `richards -7.26%`, `unpack_sequence -3.96%`,
    `nqueens -3.19%`, `deltablue -3.05%`, `go -2.36%`,
    `comprehensions -2.41%`.
- Decision:
  - reject default enablement.
  - preserve it as opt-in infrastructure/regression coverage.
  - next work is diagnosis and a new candidate; do not keep broadening inliner
    blindly.

## Session Update: 2026-05-03 (contains helper and specialized contains)

- Continued on the exclusive ARM host with multi-threaded remote builds:
  - env: `CINDERX_BUILD_JOBS=8 PARALLEL=8`
  - entrypoint: `/root/work/incoming/remote_update_build_test.sh`
- Contains-state helper deferral:
  - added gated `PYTHONJITDEFERCONTAINSHELPERS`.
  - focused RED:
    `arm-results/contains_state_helper_red_20260503_2.log`.
  - focused GREEN:
    `arm-results/contains_state_helper_green_20260503_1.log`,
    `Ran 1 test`, `OK`.
  - adjacent:
    `arm-results/contains_state_helper_adjacent_20260503_1.log`,
    default ARM runtime `Ran 119 tests`, `OK`; JIT smoke passed.
  - matrix:
    `arm-results/contains_state_helper_matrix_20260503_1.log`,
    8 benchmarks, 5 samples, policy h512 baseline versus contains helper gate.
  - result:
    geomean `-0.74%`; repeat on `go,nqueens` with 9 samples was neutral/small
    positive (`+1.42%` geomean).
  - decision:
    keep gated, not a throughput lever.
- Specialized set/dict contains:
  - added `CONTAINS_OP_SET/DICT` specialized-bytecode admission.
  - lowered exact set/dict membership to direct `JITRT_SetContains` /
    `JITRT_DictContains` helpers with exact type guards.
  - added default-on gate `PYTHONJITENABLESPECIALIZEDCONTAINS` for A/B testing
    and pyperformance runner propagation.
  - gate RED:
    `arm-results/specialized_set_contains_gate_red_20260503_1.log`, env `0`
    still used `JITRT_SetContains`.
  - focused GREEN:
    `arm-results/specialized_set_contains_gate_green_20260503_1.log`,
    `Ran 1 test`, `OK`.
  - adjacent:
    `arm-results/specialized_set_contains_adjacent_20260503_3.log`,
    default ARM runtime `Ran 120 tests`, `OK`; JIT smoke passed.
  - runner pytest:
    `arm-results/pyperf_subset_tools_specialized_contains_20260503_1.log`,
    `4 passed in 0.10s`.
  - matrix:
    `arm-results/specialized_contains_matrix_20260503_1.log`,
    8 benchmarks, 5 samples, policy h512, disabled versus enabled.
  - result:
    geomean `+0.049%`, no >5% regressions; `go +0.66%`,
    `richards +0.75%`, `deltablue +0.48%`, noise elsewhere.
  - decision:
    keep as a gated micro-optimization; continue looking for a larger
    execution-cost or policy candidate.

## Session Update: 2026-05-03 (KW exact PyFunction vectorcall)

- Implemented a narrow LIR lowering for `CALL_KW` exact `PyFunction` calls:
  - previously `TranslateSpecializedCall()` rejected all `KwArgs`, so
    `VectorCall<..., kwnames>` sites used the generic vectorcall entrypoint.
  - now exact `PyFunction` kwargs calls can use
    `JITRT_VectorcallExactPyFunc`; method descriptors/C functions with kwargs
    still stay generic.
- Added default-on gate:
  - `PYTHONJITENABLEKWPYFUNCVECTORCALL`
  - propagated through `scripts/arm/run_pyperf_subset.sh`.
- Remote TDD:
  - RED:
    `arm-results/kw_exact_pyfunc_red_20260503_1.log`.
  - gate RED:
    `arm-results/kw_exact_pyfunc_gate_red_20260503_1.log`.
  - focused GREEN:
    `arm-results/kw_exact_pyfunc_gate_green_20260503_1.log`,
    `Ran 1 test`, `OK`.
- Adjacent verification:
  - `arm-results/kw_exact_pyfunc_adjacent_20260503_2.log`
  - default ARM runtime `Ran 121 tests`, `OK`; method-with-values suite
    `Ran 11 tests`, `OK`; JIT smoke passed.
- Runner verification:
  - `arm-results/pyperf_subset_tools_kw_pyfunc_20260503_1.log`
  - `4 passed in 0.10s`.
- Matrix:
  - `arm-results/kw_pyfunc_vectorcall_matrix_20260503_1.log`
  - 8 selected benchmarks, 5 samples, policy h512, disabled versus enabled.
  - geomean `+0.8666%`, no >5% regressions.
  - main rows: `go +1.56%`, `generators +4.27%`,
    `richards +0.44%`, `raytrace -0.48%`.
- Decision:
  - keep as default-on micro-win.
  - continue with policy/autojit band and/or another hot-path lowering because
    this does not close the 30% target.
- Scout rejected:
  - exact-list truthiness was checked, but existing simplification already
    removes `PyObject_IsTrue`; no code change needed there.

## Session Update: 2026-05-03 (AutoJIT threshold band)

- Ran the threshold band on the exclusive ARM host with multi-threaded builds:
  - env: `CINDERX_BUILD_JOBS=8 PARALLEL=8`
  - entrypoint: `/root/work/incoming/remote_update_build_test.sh`
- Matrix:
  - `arm-results/autojit_band_matrix_20260503_1.log`
  - 8 selected benchmarks, 5 samples each.
  - Compared `AUTOJIT=75/100/150/200` against the current production
    comparison point `AUTOJIT=50`.
- Result:
  - `AUTOJIT=75`: geomean `-0.0927%`, `go -3.02%`.
  - `AUTOJIT=100`: geomean `+0.291%`, but `go -6.15%`.
  - `AUTOJIT=150`: geomean `-0.127%`, `go -10.12%`.
  - `AUTOJIT=200`: geomean `-1.01%`, `go -14.77%`.
- Decision:
  - keep `AUTOJIT=50`; threshold-only policy tuning is not the next lever.

## Session Update: 2026-05-04 (dynamic method-cache split focused repair)

- Remote focused green `arm-results/dynamic_method_cache_split_green_20260503_2.log`
  failed under the exclusive ARM entrypoint with
  `CINDERX_BUILD_JOBS=8 PARALLEL=8`.
- Failure shape:
  - subprocess semantic outputs were still correct: `5`, `14`, `24`.
  - HIR counts were `LoadMethodCacheEntryValue=0`,
    `FillMethodCache=0`, `LoadMethodCached=0`.
- Interpretation:
  - the original focused test warmed a single receiver type, so Python 3.14
    method-with-values lowering kept the call on an exact/direct path and did
    not leave a residual `LoadMethod` for the dynamic cache split to transform.
- Repair:
  - changed the focused test warmup to alternate `Box` and `Other` receivers
    before `jit.force_compile(hot)`, forcing a dynamic receiver shape.
- Follow-up:
  - `arm-results/dynamic_method_cache_split_green_20260504_1.log` still showed
    `0/0/0` method-cache counts, so the receiver remained on
    `LOAD_ATTR_METHOD_WITH_VALUES` / `VectorCall`.
  - shape probe `arm-results/dynamic_method_shape_probe_20260504_3.log`
    found stable residual-cache producers:
    `slots-poly` and `getattribute-poly` both produced
    `LoadMethodCacheEntryType=1`, `LoadMethodCacheEntryValue=1`,
    `FillMethodCache=1`, `LoadMethodCached=0`.
  - updated the focused regression to use a `__getattribute__` polymorphic
    receiver and to check gate-off `LoadMethodCached` versus gate-on split.
  - focused GREEN after the shape fix:
    `arm-results/dynamic_method_cache_split_green_20260504_2.log`.
    Default ARM runtime passed `Ran 122 tests in 18.569s`, `OK`; focused
    extra test passed `Ran 1 test in 0.563s`, `OK`; JIT effectiveness smoke
    passed with `jit-effective-ok compiled_size 976 interp_calls 10`.
  - pyperformance runner propagation:
    `arm-results/pyperf_subset_tools_dynamic_method_20260504_1.log`,
    `tests/test_pyperf_subset_tools.py` passed `4 passed in 0.11s`.
  - A/B matrix:
    `arm-results/dynamic_method_cache_split_matrix_20260504_1.log`.
    Disabled-vs-enabled geomean speedup was `-1.9787%` with a `deltablue`
    warning regression of `-5.94%`.
  - Decision:
    keep the dynamic split gated/off by default; continue to the next
    execution-cost candidate.

## Session Update: 2026-05-04 (exact method-cache split default-on rejected)

- Tried changing exact managed-dict method-cache split to default-on while
  preserving `PYTHONJITEXACTMETHODCACHESPLIT=0` as the explicit off switch.
- Strengthened the exact split regression:
  - compiles a `Box.call(self, x)` method using a custom `__getattribute__`
    shape that survives method-with-values lowering.
  - enabled run must contain `LoadMethodCacheEntryValue` and
    `FillMethodCache` with no `LoadMethodCached`.
  - env `PYTHONJITEXACTMETHODCACHESPLIT=0` must fall back to
    `LoadMethodCached`.
  - both paths verify instance shadowing after `box.foo = lambda ...`.
- Remote functional validation:
  `arm-results/exact_default_dynamic_guard_green_20260504_2.log`.
  Default ARM runtime passed `Ran 122 tests in 19.486s`, `OK`; dynamic focused
  extra passed `Ran 1 test in 0.578s`, `OK`; JIT smoke passed with
  `jit-effective-ok compiled_size 984 interp_calls 10`.
- Performance validation:
  - `arm-results/exact_method_cache_split_default_matrix_20260504_1.log`
    compared env-disabled against default-on.
  - disabled-vs-default geomean speedup was `-0.9831%`; no >5% row
    regressions, but the direction does not support default enablement.
- Decision:
  - reverted exact split default back to off.
  - kept the stronger env-gated regression coverage.
  - continue with a real execution-cost optimization candidate.
- Revert validation:
  - `arm-results/method_cache_gated_after_revert_green_20260504_1.log`
    passed through the remote entrypoint with
    `CINDERX_BUILD_JOBS=8 PARALLEL=8`.
  - default ARM runtime passed `Ran 122 tests in 19.047s`, `OK`;
    dynamic focused extra passed `Ran 1 test in 0.599s`, `OK`;
    JIT effectiveness smoke passed.

## Session Update: 2026-05-04 (zero-arg method-with-values delayed lookup)

- Added an attr-derived zero-arg method-with-values delayed lookup candidate.
- RED:
  - `arm-results/zero_arg_mwv_red_20260504_1.log` failed as expected because
    final HIR still had `LoadMethod` before `VectorCall<1>`.
- Implemented a narrow safe rule:
  - zero-arg delayed lookup only when all caller localsplus entries are
    initialized arguments.
  - `PYTHONJITZEROARGMWVDELAYEDLOOKUP=0` disables the new path.
  - zero-arg delayed lookup is restricted to attr-derived receivers and does
    not take over direct argument receiver calls, preserving tiny bool
    `CallMethod` optimizations.
- Debug/fix:
  - first full ARM matrix attempt
    `arm-results/zero_arg_mwv_matrix_20260504_1.log` crashed three tiny bool
    tests with subprocess return `-11`.
  - repair focused run
    `arm-results/zero_arg_mwv_crash_repair_20260504_1.log` passed `Ran 5
    tests`, `OK`.
- Verification:
  - `arm-results/zero_arg_mwv_green_20260504_2.log`: focused/adjacent `Ran 4
    tests`, `OK`.
  - `arm-results/pyperf_subset_tools_zero_arg_mwv_20260504_1.log`: runner
    propagation `4 passed`.
  - `arm-results/zero_arg_mwv_matrix_20260504_2.log`: default ARM runtime
    `Ran 123 tests in 19.843s`, `OK (skipped=3)`; JIT smoke passed.
- Matrix:
  - disabled-vs-enabled geomean speedup `+1.1655%`.
  - no `>=5%` regressions.
  - rows: `richards +3.86%`, `generators +3.68%`, `go +2.59%`,
    `deltablue +0.02%`, `nqueens +0.10%`, `raytrace -0.38%`,
    `comprehensions -0.51%`.
- Decision:
  - keep default-on as a scoped method-call micro-win, but continue because it
    is still far short of the 30% target.

## Session Update: 2026-05-04 (exact dict subscript helper)

- Added a gated exact dict subscript helper candidate.
- RED:
  - `arm-results/exact_dict_subscr_red_20260504_1.log` failed as expected:
    `JITRT_DictSubscrExact` was undefined and `DictSubscr` still called the
    mapping slot.
- Implementation:
  - added `JITRT_DictSubscrExact` using `PyDict_GetItemRef`.
  - preserves miss semantics by raising `KeyError(key)`.
  - added `PYTHONJITEXACTDICTSUBSCR` and runner propagation.
- Debug/fix:
  - `arm-results/exact_dict_subscr_green_20260504_1.log` failed to compile
    because a ternary erased the helper function pointer type.
  - fixed by emitting explicit typed if/else `appendCallInstruction` calls.
- Verification:
  - `arm-results/exact_dict_subscr_green_20260504_2.log`: focused GREEN
    `Ran 1 test`, `OK`.
  - `arm-results/pyperf_subset_tools_exact_dict_20260504_1.log`: runner
    propagation `4 passed`.
  - `arm-results/exact_dict_subscr_matrix_20260504_1.log`: default ARM
    runtime `Ran 124 tests in 19.677s`, `OK (skipped=3)`; JIT smoke passed.
  - after switching the feature to default-off:
    `arm-results/exact_dict_subscr_gated_20260504_1.log` passed `Ran 1 test`,
    `OK`.
- Matrix:
  - disabled-vs-enabled geomean speedup `-0.4578%`.
  - no `>=5%` regressions, but direction is negative.
- Decision:
  - keep gated/off by default; do not count it as a production performance
    win.

## Session Update: 2026-05-04 (method descriptor FASTCALL candidate)

- New hypothesis:
  - The existing LIR specialization only covers exact method descriptors with
    `METH_FASTCALL`, no keywords, and exactly one explicit argument
    (`list.pop(0)` style).
  - Object workloads and container-heavy helper code also use inherited
    descriptor calls with zero explicit args (`list.pop()`) and keyword-capable
    descriptors; those currently fall back to the generic vectorcall helper.
- Plan:
  - add RED coverage for `list.pop()` on a heap list subclass;
  - implement a gated generalized method-descriptor fastcall helper;
  - use the exclusive ARM host with `CINDERX_BUILD_JOBS=8 PARALLEL=8` for all
    RED/GREEN/matrix validation.
- RED:
  - `arm-results/method_descr_fastcall_red_20260504_1.log` failed as expected:
    LIR still showed `VectorCall<1, static>` for `pop_last`, and the new helper
    symbol was undefined.
- GREEN:
  - `arm-results/method_descr_fastcall_green_20260504_1.log` passed focused
    ARM validation: `Ran 1 test`, `OK`.
  - `arm-results/pyperf_subset_tools_method_descr_fastcall_20260504_1.log`
    passed runner propagation: `4 passed`.
- Matrix:
  - `arm-results/method_descr_fastcall_matrix_20260504_1.log` completed default
    ARM runtime, JIT smoke, and the 8-row matrix.
  - disabled-vs-enabled geomean speedup was `-0.7497%`; no `>=5%` row
    regressions.
  - main rows: `generators +0.70%`, `unpack_sequence +0.34%`,
    `go -0.97%`, `richards -1.16%`, `nqueens -3.48%`.
- Decision:
  - keep the generalized method descriptor helper gated/off by default. It is
    functionally useful coverage, but not a production performance win.
- Final gated verification:
  - after switching `method_descr_fast_vectorcall` to default-off,
    `arm-results/method_descr_fastcall_gated_20260504_1.log` passed the
    focused opt-in/opt-out regression: `Ran 1 test`, `OK`.

## Session Update: 2026-05-04 (inline list iterator next candidate)

- RED:
  - `arm-results/inline_list_iternext_red_20260504_1.log` failed as expected:
    the focused LIR test found no `PyListIter_Type` direct check and still saw
    `InvokeIterNext` helper lowering.
- Implementation:
  - added gated `PYTHONJITINLINELISTITERNEXT`.
  - added LIR fast path for exact `PyListIter_Type` hot iterations:
    type check, non-null `it_seq`, in-bounds `it_index < Py_SIZE(seq)`,
    direct `ob_item[index]` load, index increment, and fallback to
    `JITRT_InvokeIterNext` for non-list/exhausted/cleared cases.
- Functional verification:
  - `arm-results/inline_list_iternext_green_20260504_1.log`: focused LIR shape
    plus list mutation/clear semantics passed, `Ran 2 tests`, `OK`.
  - `arm-results/pyperf_subset_tools_inline_list_iternext_20260504_1.log`:
    runner propagation passed, `4 passed`.
- Refinement:
  - the first implementation used a hot-path `Py_IncRef` call. Replaced it with
    inline `MakeIncref` and added `BasicBlockBuilder::currentBlock()` so the
    fast-path phi predecessor is accurate after the inline refcount blocks.
  - `arm-results/inline_list_iternext_green_20260504_2.log`: focused
    re-verification passed, `Ran 2 tests`, `OK`.
- Matrix:
  - first matrix:
    `arm-results/inline_list_iternext_matrix_20260504_1_disabled_vs_enabled.json`
    geomean speedup `-1.0093%`, `comprehensions -5.88%`.
  - inline-refcount matrix:
    `arm-results/inline_list_iternext_matrix_20260504_2_disabled_vs_enabled.json`
    geomean speedup `-0.8079%`, `comprehensions -6.12%`.
- Decision:
  - keep the inline list iterator path gated/off by default. It helps
    `nqueens/richards/raytrace` slightly in the second matrix but hurts
    `comprehensions` enough to fail the production gate.
- Final gated verification:
  - after switching `inline_list_iter_next` to default-off,
    `arm-results/inline_list_iternext_gated_20260504_1.log` passed the
    focused opt-in/opt-out and mutation/clear tests: `Ran 2 tests`, `OK`.

## Session Update: 2026-05-04 (existing instance-value store candidate)

- RED/GREEN:
  - `arm-results/store_instance_value_red_20260504_2.log` failed as expected
    before the lowering existed.
  - `arm-results/store_instance_value_green_20260504_2.log` passed focused ARM
    validation: `Ran 2 tests`, `OK`.
  - `arm-results/pyperf_subset_tools_store_instance_value_20260504_1.log`
    passed runner propagation: `4 passed`.
- Matrix:
  - `arm-results/store_instance_value_matrix_20260504_1.log` completed through
    the remote ARM entrypoint with `CINDERX_BUILD_JOBS=8 PARALLEL=8`.
  - default ARM runtime passed: `Ran 127 tests in 19.911s`, `OK (skipped=3)`.
  - JIT smoke passed: `jit-effective-ok compiled_size 984 interp_calls 10`.
  - pyperformance smoke passed: `smoke-ok`.
  - disabled-vs-enabled geomean speedup:
    `arm-results/store_instance_value_matrix_20260504_1_disabled_vs_enabled.json`
    reported `-3.6571%`.
  - regressions over the `5%` gate: `raytrace -11.03%`,
    `richards -12.22%`.
- Decision:
  - keep `PYTHONJITSTOREATTRINSTANCEVALUEEXISTING` gated/off by default. The
    existing-slot semantics are correct, but the code-size/guard cost is too
    high for the selected matrix.
- Final gated verification:
  - `arm-results/store_instance_value_gated_20260504_1.log` passed after the
    default was switched off: `Ran 2 tests`, `OK`.

## Session Update: 2026-05-04 (deferred-helper code-shape pass)

- `precompile_all` regression:
  - added focused coverage for deferred helpers that must not be compiled by a
    global `jit.precompile_all()` sweep before their helper-promotion hotness
    threshold.
  - RED: `arm-results/deferred_helper_precompile_red_20260504_1.log` failed
    because `precompile_all()` bypassed the deferred-helper threshold.
  - GREEN: `arm-results/deferred_helper_precompile_green_20260504_1.log`
    passed after filtering deferred helpers in `shouldAttemptPreloadedUnit()`.
- Rejected code-level alternatives:
  - dedicated deferred-helper vectorcall passed after manual call counting, but
    the matrix stayed weak and regressed `go`/`unpack_sequence`, so it was
    removed.
  - removing early helper registration kept focused tests green, but dropped
    the broader matrix to `+9.8140%` for the best `l256_h512` policy and made
    `go` roughly `-9.25%`, so early registration was restored.
- Current retained implementation:
  - keep deferred helpers registered.
  - prevent only `precompile_all` from forcing them past their threshold.
  - use a one-query deferred-helper threshold lookup from `jitVectorcall()`.
- Current matrix:
  - `arm-results/deferred_helper_precompile_filter_matrix_20260504_1.log`
    completed remote ARM runtime, focused tests, JIT smoke, and pyperformance
    smoke.
  - best candidate in this pass: `policy_l256_h512 +12.6712%`, but
    `go -6.9174%`.
- Next active hypothesis:
  - stop pure threshold tuning and inspect code-shape classification. With
    `PYTHONJITADMITSTATEHELPERS=1`, the `go` diagnostic compiles
    `Board.move`, `UCTNode.select`, `ZobristHash.update`, and `EmptySet`
    mutators, leaving `Square.find` and `EmptySet.__init__` as the main
    deferred suspects.

## Session Update: 2026-05-04 (call-containing helper skip rejected)

- Added RED coverage for a recursive/call-containing state helper under the
  tiny/no-backedge filter:
  - RED: `arm-results/calling_state_helper_red_20260504_1.log`.
  - GREEN after classifier change:
    `arm-results/calling_state_helper_green_20260504_1.log`.
  - Adjacent deferred-helper tests:
    `arm-results/calling_state_helper_adjacent_20260504_2.log`, `Ran 5 tests`,
    `OK`.
- `go` diagnostics proved the classifier changed the intended state:
  - `arm-results/go_deferred_diag_callskip_l256_h512_20260504_2.log` showed
    `Square.find`, `Board.move`, and `UCTNode.select` no longer deferred.
- Matrix rejected the idea:
  - `arm-results/deferred_helper_callskip_matrix_20260504_1.log`.
  - best geomean in this pass was only `+10.1926%`, while `go` regressed
    `-20.3457%`.
- Decision:
  - revert the call-containing-helper skip classifier. The next code-level
    path is selective admission/compilation of the problematic call-containing
    state helpers, not removing them from the registered/deferred lifecycle.

## Session Update: 2026-05-04 (calling state helper admission)

- Added a new opt-in policy knob:
  - `PYTHONJITADMITCALLINGSTATEHELPERS`.
  - It admits simple self methods with no policy backedge when they contain a
    call opcode and also have state mutation/subscript/predicate shape.
- TDD:
  - RED: `arm-results/calling_state_helper_admit_red_20260504_1.log`.
  - GREEN: `arm-results/calling_state_helper_admit_green_20260504_1.log`.
  - Adjacent: `arm-results/calling_state_helper_admit_adjacent_20260504_1.log`,
    `Ran 5 tests`, `OK`.
- Diagnostics:
  - `arm-results/go_deferred_diag_calladmit_l256_h512_20260504_1.log` showed
    `Square.find`, `EmptySet.__init__`, `Board.move`, and `UCTNode.select`
    compiling under the opt-in.
- Matrix:
  - `arm-results/deferred_helper_calladmit_matrix_20260504_1.log`.
  - `policy_calladmit_l256_h512` improved over same-run `policy_l256_h512`
    from `+9.0405% / go -7.9204%` to `+9.2745% / go -6.7558%`.
- Decision:
  - keep the knob as research/opt-in only. It is the right direction, but not a
    large enough win. Continue into compiled-code quality for the admitted
    helpers.
## Session Update: 2026-05-05 (continue performance tuning beyond fallback)

- Restored the active optimization context from `task_plan.md`,
  `progress.md`, and `findings.md`.
- Recorded the exact `list.pop()` default-index helper evidence:
  - RED, correctness failure, Simplify assertion failure, final GREEN, opt-out
    RED/GREEN, and the same-run pyperformance matrix.
- Important conclusion:
  - `list.pop()` is a real `go` micro-win (`~+1.5%`) but does not move the
    selected geomean; do not spend the next round on more isolated built-in
    helper micro-optimizations unless they attack a broad call shape.
- Current next step:
  - inspect the remaining `LoadMethodCached + CallMethod` chain in
    `go`/`richards` and design a bigger code-quality optimization for hot
    object helpers.

## Session Update: 2026-05-05 (fused cached method-call RED)

- Added focused RED coverage for an opt-in fused cached method-call helper.
- Remote evidence:
  - `arm-results/cached_method_call_helper_red_20260505_1.log`
  - the current compiler still emits `LoadMethodCached=1` and `CallMethod=1`
    for `obj.foo(x)`, while the expected `CallMethodCached` node is absent.
- Decision:
  - implement the narrow fused helper path next, preserving instance
    shadowing and class method replacement through the existing
    `LoadMethodCache` lookup.

## Session Update: 2026-05-05 (fused cached method-call GREEN)

- Implemented opt-in `PYTHONJITCACHEDMETHODCALLHELPER` /
  `-X jit-cached-method-call-helper`.
- Added `CallMethodCached` HIR plus LIR lowering to a vectorcall-shaped helper
  that reuses `LoadMethodCache` and then calls `JITRT_CallMethod`.
- Correctness verification:
  - `arm-results/cached_method_call_helper_green_20260505_4.log`
  - default ARM runtime: `Ran 135 tests`, `OK (skipped=3)`.
  - focused test: `Ran 1 test`, `OK`.
- Current next step:
  - run selected pyperformance disabled-vs-enabled matrix and keep the knob
    research-only unless there is a clear same-run win.

## Session Update: 2026-05-05 (fused cached method-call first matrix)

- Matrix:
  - `arm-results/cached_method_call_matrix_20260505_1.log`
  - `jitlist` helper enabled vs disabled: `+3.8163%` geomean, no `>=5%`
    regressions; strongest rows were `deltablue +15.9878%` and
    `comprehensions +6.0068%`.
  - policy/call-admit helper enabled vs disabled: `+2.2927%` geomean, but
    `unpack_sequence -9.7842%`.
- Decision:
  - do not stop here. The signal is real but not enough, and `go` is still
    slightly negative.
  - next change is to lower `CallMethodCached` to fixed-arity helpers for the
    currently admitted 0-3 explicit-argument shapes instead of the
    vectorcall-shaped wrapper.

## Session Update: 2026-05-05 (fused cached method-call fixed-arity GREEN)

- Lowered `CallMethodCached` arity-0..3/no-keyword sites to fixed runtime
  helpers instead of the vectorcall-shaped wrapper.
- Correctness verification:
  - `arm-results/cached_method_call_fixed_green_20260505_1.log`
  - default ARM runtime: `Ran 135 tests`, `OK (skipped=3)`.
  - focused fused-call test: `Ran 1 test`, `OK`.
- Current next step:
  - run the same selected pyperformance matrix with a fresh result prefix to
    measure whether fixed-arity lowering grows the first matrix's `+3.8163%`
    `jitlist` helper signal.

## Session Update: 2026-05-05 (fused cached method-call fixed-arity matrix)

- Matrix:
  - `arm-results/cached_method_call_fixed_matrix_20260505_1.log`
- Result:
  - `jitlist` helper enabled vs disabled: `+2.4868%` geomean, with
    `go +1.3641%`, `richards +6.3018%`, but `nqueens -5.8863%` and
    `raytrace -7.6494%`.
  - policy/call-admit helper enabled vs disabled: `+3.0238%` geomean, with
    `go +1.8841%`, `richards +2.5408%`, and no `>=5%` regressions.
- Decision:
  - the fixed helper does improve the policy/object-heavy mode and turns `go`
    positive, but pure `jitlist` stability is not good enough.
  - continue with a larger code-level reduction in cached method-call runtime
    overhead instead of stopping at wrapper removal.

## Session Update: 2026-05-05 (small-int cached method-call fusion)

- Added a focused test for `obj.foo(1)` in the dynamic method lookup shape.
- Debugging note:
  - first RED attempt was invalid because the test hit a 3.14 specialized
    method path with `LoadMethod=0` and `CallMethod=0`.
  - corrected RED forced the dynamic path via `__getattribute__` and failed
    with `CallMethodCached=0`, `LoadMethod=1`, `CallMethod=1`.
- Correctness verification:
  - RED: `arm-results/cached_method_call_small_int_red_20260505_2.log`
  - GREEN: `arm-results/cached_method_call_small_int_green_20260505_2.log`
  - default ARM runtime: `Ran 136 tests`, `OK (skipped=3)`.
  - focused test: `Ran 1 test`, `OK`.
- Current next step:
  - run the same pyperformance matrix again with a new prefix to see whether
    admitting `LOAD_SMALL_INT` grows the fixed-arity helper's real benchmark
    signal.

## Session Update: 2026-05-05 (small-int fusion rejected by matrix)

- Matrix:
  - `arm-results/cached_method_call_smallint_matrix_20260505_1.log`
- Result:
  - `jitlist` helper enabled vs disabled fell to `+1.6418%` geomean and still
    had regressions (`raytrace`, `unpack_sequence`).
  - policy/call-admit helper enabled vs disabled fell to `+0.7195%` geomean
    and regressed `unpack_sequence -29.0282%`.
- Decision:
  - remove `LOAD_SMALL_INT` expansion from the active patch. It increases HIR
    coverage but makes benchmark quality worse.
  - next code-level optimization should reduce per-call cached-hit overhead for
    already-profitable fused method calls instead of admitting more low-profit
    call shapes.

## Session Update: 2026-05-05 (borrowed-self cached hit)

- Removed the rejected `LOAD_SMALL_INT` expansion from the active patch.
- Added `LoadMethodCache::lookupForCall()` for immediate fused-call use:
  cached hits return a strong callable but borrow receiver/self.
- Correctness verification:
  - `arm-results/cached_method_call_borrowed_self_green_20260505_1.log`
  - default ARM runtime: `Ran 135 tests`, `OK (skipped=3)`.
  - focused fused-call test: `Ran 1 test`, `OK`.
- Current next step:
  - run the fixed helper matrix again to measure whether avoiding self
    refcount churn increases the `policy_calladmit` and `jitlist` helper
    signals without reintroducing small-int row instability.

## Session Update: 2026-05-05 (borrowed-self matrix)

- Matrix:
  - `arm-results/cached_method_call_borrowed_self_matrix_20260505_1.log`
- Result:
  - `jitlist` helper enabled vs disabled: `+1.9028%` geomean,
    `go +0.6270%`, `richards +5.3833%`, but `unpack_sequence -17.4759%`.
  - policy/call-admit helper enabled vs disabled: `+5.0020%` geomean, no
    `>=5%` regressions, but `go -2.1536%`.
- Decision:
  - this is the best policy-mode helper result so far, but not sufficient.
  - continue reducing direct user-method call overhead before attempting a
    broader enablement decision.

## Session Update: 2026-05-05 (resolved direct method-call GREEN)

- Added a direct resolved-call path inside the fused cached method-call helper:
  after cache lookup, no-keyword resolved Python functions call their vectorcall
  slot directly instead of bouncing through `JITRT_CallMethod()`.
- Correctness verification:
  - `arm-results/cached_method_call_resolved_direct_green_20260505_1.log`
  - default ARM runtime: `Ran 135 tests`, `OK (skipped=3)`.
  - focused fused-call test: `Ran 1 test`, `OK`.
- Current next step:
  - run the same selected pyperformance matrix with a new prefix and compare
    against the borrowed-self and fixed-arity helper results. If this does not
    increase the policy-mode signal, move on to call-site coverage or a deeper
    cached-call fast path rather than tuning thresholds.

## Session Update: 2026-05-05 (resolved direct method-call rejected)

- Matrix:
  - `arm-results/cached_method_call_resolved_direct_matrix_20260505_1.log`
- Result:
  - `jitlist` helper enabled vs disabled: only `+0.0931%` geomean, with
    `raytrace -6.0157%` and `unpack_sequence -31.7946%`.
  - policy/call-admit helper enabled vs disabled: `+4.5065%` geomean, below
    the borrowed-self `+5.0020%`, with `nqueens -5.7163%`.
- Decision:
  - removed the direct resolved-call helper from the active implementation.
  - keep moving toward larger收益 through call-site coverage and lookup-path
    reduction, not more wrapper bypasses that the matrix does not support.

## Session Update: 2026-05-05 (method-with-values fallback cached-call matrix)

- Added and verified a narrow `LOAD_ATTR_METHOD_WITH_VALUES` fallback coverage
  path for opt-in fused cached method calls.
- Correctness verification:
  - RED: `arm-results/cached_method_call_mwv_fallback_red_20260505_1.log`
  - GREEN: `arm-results/cached_method_call_mwv_fallback_green_20260505_1.log`
  - default ARM runtime: `Ran 136 tests`, `OK (skipped=3)`.
  - focused cached-call tests: `Ran 2 tests`, `OK`.
- Coverage diagnostic:
  - `arm-results/cached_method_call_mwv_fallback_coverage_diag_20260505_1.log`
  - helper enabled converted the 88-row diagnostic from
    `CallMethodCached=21`, `LoadMethodCached=121`, `CallMethod=144`,
    `VectorCall=238` to `CallMethodCached=90`, `LoadMethodCached=52`,
    `CallMethod=77`, `VectorCall=172`.
- Matrix:
  - `arm-results/cached_method_call_mwv_fallback_matrix_20260505_1.log`
  - `jitlist` helper enabled vs disabled: `+2.9331%` geomean with
    `richards +5.0806%`, `deltablue +15.7638%`, but `raytrace -8.1068%`.
  - policy/call-admit helper enabled vs disabled: `+8.0560%` geomean,
    no `>=5%` regressions, with `richards +8.1090%`,
    `deltablue +19.8515%`, `unpack_sequence +25.5224%`, but `go -0.2467%`.
- Decision:
  - keep this expansion as the best current policy-mode cached-call result.
  - continue with `go` residual HIR/LIR analysis because ordinary method-call
    coverage is no longer the main missing piece for that benchmark.

## Session Update: 2026-05-05 (combo scout and residual split rejected)

- Recorded the post-cached-call combo scout in `findings.md`.
- Result:
  - method-value inliner combinations are negative (`-4.2215%` alone and
    `-3.5168%` with dynamic split), with row regressions.
  - dynamic method-cache split on top of policy cached-call is a small positive
    scout result: `+2.0651%` geomean, no `>=5%` regressions, but `go -0.4702%`.
- Residual split full matrix:
  - RED: `arm-results/cached_method_call_residual_split_red_20260505_1.log`.
  - GREEN: `arm-results/cached_method_call_residual_split_green_20260505_1.log`,
    default ARM runtime `Ran 138 tests`, focused test `Ran 1 test`, smoke OK.
  - Matrix: `arm-results/cached_method_call_residual_split_matrix_20260505_1.log`.
  - `jitlist` disabled-vs-enabled: `+0.0976%` geomean, `go -3.2924%`,
    regressions in `raytrace` and `unpack_sequence`.
  - `policy_calladmit_l256_h512` disabled-vs-enabled: `+4.1746%` geomean,
    `go -0.7870%`, no `>=5%` regressions.
- Decision:
  - reject auto-enabling residual dynamic split for the cached-call helper path.
  - keep the method-with-values fallback cached-call result as the current best
    policy-mode helper signal (`+8.0560%`).
- Next step:
  - stop expanding low-profit call shapes and inspect remaining `go`/`richards`
    code shapes for a larger code-level optimization, especially object state
    accesses and exact-container operations that current type propagation may
    fail to expose.

## Session Update: 2026-05-05 (calling-state passthrough fixed)

- Found a benchmark harness correctness gap:
  - `scripts/arm/run_pyperf_subset.sh` passed
    `PYTHONJITADMITSTATEHELPERS` but not
    `PYTHONJITADMITCALLINGSTATEHELPERS`.
  - older `policy_calladmit_l256_h512` labels therefore may not mean the
    worker actually saw calling-state admission.
- TDD through the remote entrypoint:
  - RED:
    `arm-results/pyperf_subset_admit_calling_passthrough_red_20260505_2.log`
    failed the new passthrough/probe assertions.
  - GREEN:
    `arm-results/pyperf_subset_admit_calling_passthrough_green_20260505_1.log`
    passed the same pytest slice with `2 passed`.
- Corrected 5-sample matrix:
  - `arm-results/cached_method_call_mwv_calladmit_passthrough_matrix_20260505_1.log`.
  - `--inherit-environ` now includes `PYTHONJITADMITCALLINGSTATEHELPERS`.
  - helper enabled vs disabled under real calling-state admission:
    `+2.4564%` geomean, `go +0.3638%`, `richards +4.9580%`,
    no `>=5%` regressions.
- Decision:
  - keep the harness fix as measurement-chain repair.
  - do not treat this as the larger收益 path; proceed to JIT code work.
  - next candidate: fixed-arity keyword cached-call helpers for already-fused
    `CALL_KW` method calls.

## Session Update: 2026-05-05 (CALL_KW fixed cached-call helper)

- Added focused LIR coverage for already-fused `CALL_KW` cached method calls.
- Remote TDD:
  - RED:
    `arm-results/cached_method_call_kw_fixed_lir_red_20260505_1.log`.
  - GREEN:
    `arm-results/cached_method_call_kw_fixed_lir_green_20260505_1.log`.
  - adjacent:
    `arm-results/cached_method_call_kw_fixed_adjacent_20260505_2.log`,
    default ARM runtime `Ran 138 tests`, `OK (skipped=3)`, focused cached-call
    tests `Ran 4 tests`, `OK`.
- Performance:
  - corrected 8-row policy/call-admit matrix:
    `arm-results/cached_method_call_kw_fixed_matrix_20260505_2.log`,
    geomean speedup `+2.8114%`, no `>=5%` regressions, but `go -3.9115%`.
  - focused 7-sample repeat:
    `arm-results/cached_method_call_kw_fixed_go_repeat_20260505_1.log`,
    geomean speedup `-0.4516%`, `go -2.4291%`,
    `richards +3.9263%`, `raytrace -3.0014%`.
- Decision:
  - this is correct but not the big收益 path.
  - next: TDD a more direct `go` residual shape, starting with
    `obj.foo(arg.value)` cached-call coverage while protecting method-lookup
    versus argument-attribute exception ordering.

## Session Update: 2026-05-05 (CALL_METHOD fixed helper matrix)

- Added and verified focused coverage for the `obj.foo(arg.value)`-style
  residual method-call shape.
- Remote evidence:
  - coverage RED:
    `arm-results/cached_method_call_attr_arg_red_20260505_1.log`.
  - LIR RED/GREEN:
    `arm-results/call_method_attr_arg_fixed_lir_red_20260505_1.log`,
    `arm-results/call_method_attr_arg_fixed_lir_green_20260505_1.log`.
  - adjacent:
    `arm-results/call_method_fixed_adjacent_20260505_2.log`,
    `arm-results/call_method_fixed_focused_adjacent_20260505_1.log`.
- Matrix:
  - `arm-results/call_method_fixed_matrix_20260505_1.log`.
  - policy/call-admit method-helper enabled vs disabled:
    `+4.0625%` geomean, no `>=5%` regressions, but `go -3.0040%`.
- Decision:
  - not a mainline performance breakthrough; it is weaker than the current
    best method-with-values fallback cached-call result (`+8.0560%`) and still
    moves `go` the wrong way.
  - next active RED is
    `arm-results/call_method_fixed_plain_function_red_20260505_1.log`, checking
    a plain-function safety/coverage gap before any broader admission.

## Session Update: 2026-05-05 (merge readiness and combined matrix)

- User asked to list all optimizations, run them together, compute distance to
  the `30%` target, and split mergeable work into commits on a new branch from
  remote `bench-cur-7c361dce`.
- Added a merge-readiness table to `findings.md` covering:
  default-on micro wins, gated/off policy tools, rejected experiments, and
  next high-leverage candidates.
- Ran combined matrix through the standard remote entrypoint:
  - first attempt failed because the remote tarball had already been consumed.
  - second attempt reached post-pyperf but failed because the temporary matrix
    script tried to execute non-executable `run_pyperf_subset.sh` directly.
  - third attempt succeeded after switching to `bash run_pyperf_subset.sh`.
- Final combined result:
  - log: `arm-results/combined_optimization_matrix_20260505_3.log`.
  - `baseline_disabled` vs `combo_all_retained`:
    geomean speedup `+7.3867%`, still `22.6133` percentage points short of
    `30%`; `go` regressed `-10.1161%`.
  - `baseline_disabled` vs `combo_all_plus_generated`:
    geomean speedup `+9.9362%`, still `20.0638` percentage points short of
    `30%`; `go` regressed `-11.1533%` and `raytrace` regressed `-5.4563%`.
- Decision:
  - do not default-enable the full policy/cached-call combo.
  - split commits so runner/measurement fixes, default-safe micro wins, and
    gated/off research knobs are distinguishable.

## Session Update: 2026-05-05 (final branch verification)

- Re-uploaded the committed branch state to the remote test host because the
  standard entrypoint consumes `/root/work/incoming/cinderx-update.tar`.
- Ran final verification through `/root/work/incoming/remote_update_build_test.sh`
  with pyperformance skipped, using the same remote build/test path.
- Evidence:
  `arm-results/final_branch_arm_runtime_20260505_1.log`.
- Result:
  build completed; ARM runtime verification reported `Ran 141 tests`,
  `OK (skipped=3)`.
- Next:
  commit this evidence-only update and push
  `codex/perf-jit-retained-20260505` to the SSH remote.

## Session Update: 2026-05-05 (full default pyperformance probe)

- User asked whether the earlier 8-row matrix misses the broader
  pyperformance picture.
- Ran a full default pyperformance coverage probe through
  `/root/work/incoming/remote_update_build_test.sh` using a post-pyperf
  command.
- Scope:
  - `python -m pyperformance list` reported 97 default benchmark entries.
  - the run expanded to 124 concrete result rows.
  - `SAMPLES=1`, `MODE=jitlist`, chunk size 8.
  - cases:
    `baseline_disabled`, `combo_all_retained`,
    `combo_all_plus_generated`.
- Evidence:
  - entry log:
    `arm-results/full_pyperf_20260505_1_entry.log`.
  - result directory:
    `arm-results/full_pyperf_20260505_1/`.
- Completion:
  all three cases completed with 124 concrete rows and 0 benchmark execution
  failures.
- Result:
  - retained combo:
    geomean speedup `+5.7678%`, gap to 30% target `24.2322` pct points,
    `go -10.3733%`.
  - plus-generated combo:
    geomean speedup `+5.7499%`, gap to 30% target `24.2501` pct points,
    `go -9.297%`.
- Decision:
  full default pyperformance does not rescue the current optimization set.
  It weakens the 8-row signal and reinforces keeping the aggressive policy
  combo gated/off until the `go` object-state regression is addressed.

## Session Update: 2026-05-05 (expanded 28-row JIT set rerun)

- User asked to use the "about 20 JIT cases" suite to compare this version's
  performance.
- Reran the 2026-05-03 expanded JIT-relevant pyperformance set through the
  remote entrypoint:
  `/root/work/incoming/remote_update_build_test.sh`.
- Scope:
  22 pyperformance entries expanded to 28 concrete rows.
- Method:
  `MODE=jitlist`, `SAMPLES=5`.
- Cases:
  `baseline_disabled`, `combo_all_retained`,
  `combo_all_plus_generated`.
- Evidence:
  `arm-results/ext28_pyperf_20260505_1_entry.log` and
  `arm-results/ext28_pyperf_20260505_1/`.
- Completion:
  all three cases completed with 28 rows and 5 samples per row.
- Same-branch results:
  - retained combo:
    geomean speedup `-4.6058%`, gap to 30% target `34.6058` pct points,
    `go -8.5093%`.
  - plus-generated combo:
    geomean speedup `-3.0969%`, gap to 30% target `33.0969` pct points,
    `go -8.6523%`.
- Cross-version sanity check:
  current `baseline_disabled` vs old
  `pyperf_ext_jitlist_20260503_1.json` is nearly flat at `-0.3855%`
  geomean, so the rerun is comparable to the original expanded baseline.
- Outlier-adjusted read:
  excluding `coverage` and `scimark_sor`, retained is `+5.2394%` and
  plus-generated is `+6.5401%`, still far below 30%.
- Decision:
  do not default-enable the aggressive combo for the 28-row JIT suite.
  It has strong localized wins, but `coverage`, `scimark_sor`, and `go`
  dominate the overall regression.
