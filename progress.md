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
 
## Session: 2026-04-11 (Remote Space Cleanup)

### Phase 1: Inventory
- **Status:** in_progress
- **Started:** 2026-04-11
- Actions taken:
  - Read current `task_plan.md`, `progress.md`, and `findings.md` for context
  - Ran `planning-with-files` session catchup (no stored Codex session state)
- Files created/modified:
  - task_plan.md (added remote cleanup plan)
  - progress.md (this entry)

### Phase 2-4: Cleanup + Verify
- **Status:** complete
- Actions taken:
  - Measured ARM disk usage (`df -h`) and `/root/work` sizes
  - Removed stale `/root/work` issue/benchmark workdirs
  - Re-checked `df -h` to confirm reclaimed space
- Result:
  - `/dev/vda2` moved from 100% full to 73% used (`21G` available)

## Session: 2026-04-11 (Local Python Env for CinderX)

### Phase 1: Requirements + platform decision
- **Status:** in_progress
- **Started:** 2026-04-11
- Actions taken:
  - Read `README.md` and `pyproject.toml` for platform/version requirements
  - Checked `wsl -l -v` to see if WSL distributions are installed
  - Updated task plan for local environment setup
- Files created/modified:
  - task_plan.md (added local environment plan)
  - progress.md (this entry)
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

## 2026-04-12

- Reproduced a clean regression in the unified ARM helper path after
  `91006d4c`, then bisected it against `4dac6841`.
- Narrowed the regression to no-OSR finalize behavior plus `force_compile()`
  semantics for already-compiled functions.
- Implemented:
  - safe-point finalize path in the interpreter/OSR handshake
  - call-outside-loop gate for no-OSR finalize
  - idempotent `force_compile()`
  - updated smoke/test expectations for already-compiled hot-loop functions
- Verified through the unified remote helper path with `SKIP_PYPERF=1`:
  - `Ran 93 tests in 119.196s`
  - `OK`
- Follow-up compare work found two harness constraints:
  - baseline/current benchmark compare needs isolated `WORKDIR` and isolated
    `DRIVER_VENV` per revision
  - `bench_pyperf_direct.py --compile-strategy none` is not sufficient for
    fresh compare venvs because the benchmark kernels stay uncompiled
- Added a new direct harness mode for explicit kernel compilation:
  - `--compile-strategy exprs`
  - `--compile-exprs-json`
- First isolated explicit-kernel compares:
  - `fannkuch`: about `-6.55%`
  - `unpack_sequence`: about `+4.62%`
  - `scimark_monte_carlo`: about `-9.62%`
  - `go`: about `+10.07%`
- Completed the remaining representative-set compares:
  - `scimark_sor`: about `+0.67%`
  - `scimark_lu`: about `-6.98%`
  - `nbody`: about `+1.36%`
  - `spectral_norm`: about `+9.38%`
  - `chaos`: about `+1.91%`
  - `raytrace`: about `-2.62%`
- Updated conclusion:
  - explicit-kernel compare is the only trustworthy fresh compare mode so far
  - current representative set is mixed, not all-green
- Latest follow-up:
  - `fd2ae6f5` adds a regular auto-JIT gate for attr-heavy object helpers at
    `jitVectorcall`
  - fresh ARM helper verification on a new driver venv is green:
    - `Ran 95 tests in 66.409s`
    - `OK`
  - synthetic semantic A/B is also green:
    - baseline still auto-compiles `useful_fast`
    - current no longer auto-compiles `useful_fast`
    - numeric hot loops still auto-compile
  - the real `bm_go.versus_cpu()` path still crashes whenever CinderX is
    enabled, and succeeds with `CINDERX_DISABLE=1`
  - current understanding:
    - the helper gate itself is working
    - the remaining `go` blocker is a broader CinderX-enabled benchmark crash
- Narrowing follow-up:
  - startup-state checks showed the installed venv starts with the JIT enabled
    by default
  - `fd2ae6f5` was too broad and blocked `Board.useful`-like helpers
  - `6a7e4f9a` now restricts the helper gate to call-free attr-heavy helpers
    that actually contain a backward jump
  - fresh ARM helper run is green again:
    - `Ran 96 tests in 65.857s`
    - `OK`
  - fresh regular auto-JIT benchmark signal:
    - initial 7-sample:
      - `bm_go`: about `+6.79%`
      - `fannkuch`: about `-1.29%`
    - thick 15-sample confirmation:
      - `bm_go`: about `-1.33%`
      - `fannkuch`: about `-0.26%`
  - updated takeaway:
    - the narrowed helper gate no longer shows a stable performance regression
