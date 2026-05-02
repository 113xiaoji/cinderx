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

