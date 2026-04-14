# Notes

## 2026-04-11 Day 1 progress

- Track B:
  - added `hot_loop_skip` runtime stats plumbing
  - added ARM regression `test_phase1_loop_osr_reports_skip_reason_for_high_call_wrapper`
  - remote helper run passed full ARM runtime suite (`Ran 91 tests ... OK`)
- Track A:
  - discovered that pyperformance raw JSON in `--debug-single-value` mode may
    omit benchmark names
  - extracted summary logic into `scripts/arm/summarize_pyperf_subset.py`
  - added local/remote unit tests in `scripts/arm/test_pyperf_subset_tools.py`
  - compare script now rejects mismatched `benchmark_filter`, `samples`, and
    `autojit`
- Remaining Day 1 concern:
  - `remote_update_build_test.sh` still performs pyperformance venv setup even
    when `SKIP_PYPERF=1`, so external package/network issues can still fail the
    helper after runtime tests have already passed
  - `hot_loop_skip` stats are currently always-on and record every skip event;
    Day 2 should decide whether to keep that shape, sample it, or move to a
    lower-overhead keyed representation

## 2026-04-11 Day 2 progress

- Remote helper fast-path:
  - moved `pip -U pip` and `pyperformance` installation behind the pyperf path
  - `SKIP_PYPERF=1` now exits after runtime smoke
  - remote helper verification succeeded and printed:
    - `SKIP_PYPERF=1 set; done after smoke.`
- Runtime direction chosen:
  - attr/stateful density gate in `_PyJIT_TryHotLoopOSR()`
- Measured loop-body shapes:
  - object-stateful synthetic:
    - `attr_count = 4`
    - `call_count = 2`
  - search/state-transition synthetic:
    - `attr_count = 7`
    - `call_count = 0`
- Current gate shape:
  - skip with reason `attr_heavy_loop` when:
    - `attr_ops >= 4`
    - and `attr_ops >= call_ops + 2`
- Verification:
  - red before change:
    - `attr_heavy_loop` skip count for object-stateful synthetic = `0`
  - green after change:
    - remote full ARM runtime suite:
      - `Ran 92 tests in 62.480s`
      - `OK`
- Additional Day 2 follow-up:
  - helper build path now defaults to `BUILD_NO_ISOLATION=1`
  - verified current restore on ARM succeeds with:
    - `BUILD_NO_ISOLATION=1`
    - `SKIP_PYPERF=1`
- Current direct benchmark observations:
  - `fannkuch` still OSRs in benchmark code
  - `go` / `chaos` / `raytrace` now show benchmark-code skip reasons instead of
    only imported helper noise
- Invalid data point:
  - one attempted `fb105b6b` direct comparison is discarded because the remote
    source file still contained `attr_heavy_loop`, so the install state was not
    a clean baseline

## 2026-04-11 Day 2 compare update

- Deploy marker plumbing is now in place and verified:
  - baseline marker: `source_commit = fb105b6b`
  - current marker: `source_commit = 06a262ff`
- Skip-cache effect:
  - high-call and object-stateful skip-reason probes now both report `1/1`
    instead of `5000/20000`
- Clean direct compare results:
  - `fannkuch`: about `+3.9%`
  - `go`: about `-34.4%`
  - `chaos`: about `+0.6%`
  - `raytrace`: about `+29.7%`
- Immediate conclusion:
  - skip caching is a real win for `go`
  - `raytrace` remains the biggest unresolved regression

## 2026-04-11 Day 2 skip-nojit refinement

- Root-cause refinement:
  - caching/reporting skip reasons was not enough for `raytrace`
  - loops that keep executing `JUMP_BACKWARD_JIT` still re-enter
    `_PyJIT_TryHotLoopOSR()` on every backedge
- Change:
  - after caching a skip decision, rewrite the backedge to `JUMP_BACKWARD_NO_JIT`
- Results:
  - `go`: improved further to about `-41.5%`
  - `raytrace`: improved from about `+29.7%` down to about `+1.5%`
  - `chaos`: now about `+3.8%`
  - `fannkuch`: now about `+6.5%`

## 2026-04-11 Day 2 thick-sample confirmation

- Focused 15-repeat compares were run for the residual signals:
  - `fannkuch`
  - `chaos`
  - `raytrace`
- Updated result:
  - `fannkuch`: about `-0.19%`
  - `chaos`: about `-3.29%`
  - `raytrace`: about `-1.60%`
- Current conclusion:
  - the representative direct benchmark set is now net positive or neutral
  - the remaining issue in `raytrace` is warmup variance, not a stable median
    regression

## 2026-04-11 Day 2 broader coverage pass

- Ran a broader direct benchmark matrix on clean baseline/current install states
  with 3 repeats for:
  - `unpack_sequence`
  - `scimark_monte_carlo`
  - `scimark_sor`
  - `scimark_lu`
  - `nbody`
  - `spectral_norm`
  - `meteor_contest`
  - `hexiom`
  - `pyflate`
  - `decimal_pi`
  - `telco`
  - `float`
  - `deltablue`
  - `mdp`
  - `barnes_hut`
  - `bpe_tokeniser`
- Broad signal summary:
  - strongest positives:
    - `meteor_contest`
    - `pyflate`
    - `mdp`
    - `go`
  - mostly flat:
    - `scimark_monte_carlo`
    - `scimark_sor`
    - `bpe_tokeniser`
    - `barnes_hut`
  - likely regressions needing thicker confirmation:
    - `nbody`
    - `spectral_norm`
    - `scimark_lu`
    - `unpack_sequence`
- Important caution:
  - `unpack_sequence`, `hexiom`, and `deltablue` all showed very large first-run
    outliers, so their 3-repeat medians are not good final evidence

## 2026-04-11 Day 2 thick-sample broad-regression pass

- Ran 15-repeat direct confirms for:
  - `unpack_sequence`
  - `scimark_lu`
  - `nbody`
  - `spectral_norm`
- Result:
  - `unpack_sequence`: about `+12.9%`
  - `spectral_norm`: about `+12.7%`
  - `nbody`: about `+6.9%`
  - `scimark_lu`: about `+3.0%`
- Updated priority among remaining regressions:
  1. `unpack_sequence`
  2. `spectral_norm`
  3. `nbody`
  4. `scimark_lu`

## 2026-04-11 Day 2 finalize-without-OSR-entry

- Root cause:
  - a function could be compiled by the hot-loop path yet remain unusable for
    future calls if the current activation had no usable OSR entry
- Fix:
  - finalize the compiled function immediately for future calls when:
    - compilation succeeded
    - current activation cannot OSR into it
- Results:
  - `unpack_sequence`: about `-97.4%`
  - `nbody`: about `-72.5%`
  - `scimark_lu`: about `-52.9%`
  - `spectral_norm`: about `-43.2%`
- Current conclusion:
  - this is a broad coverage improvement, not a benchmark-specific tweak

## 2026-04-11 Day 2 broad matrix refresh after finalize fix

- Reran the 16-benchmark broad direct matrix on a clean current install state
  after the finalize-without-OSR-entry fix.
- Result:
  - the broad matrix is now overwhelmingly positive
  - strongest wins include:
    - `unpack_sequence`
    - `nbody`
    - `meteor_contest`
    - `scimark_lu`
    - `hexiom`
    - `pyflate`
    - `spectral_norm`
  - remaining entries are modestly positive or effectively flat
- Updated conclusion:
  - no stable median regression remains in the currently measured broad set

## 2026-04-12 stabilization follow-up

- Clean helper verification exposed a real regression after `91006d4c` that had
  been masked by earlier stale-helper / noisy-runner paths.
- Clean split:
  - `4dac6841`: `Ran 92 tests ... OK`
  - current after `91006d4c`: multiple ARM runtime failures plus helper smoke
    breakage
- Root cause evolved in three steps:
  1. immediate finalize inside `_PyJIT_TryHotLoopOSR()` was too aggressive
  2. even deferred finalize needed a shape gate for functions with calls
     outside the active loop
  3. `force_compile()` returning `False` for already-hot-loop-compiled
     functions broke remaining force-compile regression guards
- Final behavior now in the worktree:
  - safe-point finalize path via `osr_entered == 2`
  - no-OSR finalize only when there are no call opcodes outside the active hot
    loop
  - `force_compile()` is idempotent and returns success when a function is
    already compiled
  - helper smoke and `test_jit_force_compile_smoke` accept already-compiled
    functions and still verify compiled execution
- Final clean ARM verification through the unified helper path:
  - `Ran 93 tests in 119.196s`
  - `OK`
  - `jit-effective-ok compiled_size 984 interp_calls 10`
  - helper exits cleanly at `SKIP_PYPERF=1 set; done after smoke.`

## 2026-04-12 compare harness follow-up

- Representative benchmark compare was resumed after the stability fix.
- New engineering fact:
  - cross-revision compare must use separate `WORKDIR` and separate
    `DRIVER_VENV`
  - keeping `scratch/` across revision swaps produces fake build breakage
  - reusing one driver venv produces reinstall crashes
- Clean helper deploys are reproducible again when both are isolated per
  revision.
- New measurement caveat:
  - in fresh compare venvs, `bench_pyperf_direct.py --compile-strategy none`
    does not JIT-compile the benchmark kernels we care about
  - verified false for:
    - `fannkuch`
    - `bench_all`
    - `bench_nbody`
    - `advance`
    - `bench_spectral_norm`
    - `part_A_times_u`
    - `part_At_times_u`
- Conclusion:
  - the first clean representative direct numbers gathered in that mode cannot
    be used as hot-loop JIT performance evidence
  - next compare step should explicitly force-compile or jitlist the intended
    kernels before timing

## 2026-04-12 explicit compile-expression compare

- Added a new harness mode in `scripts/arm/bench_pyperf_direct.py`:
  - `--compile-strategy exprs`
  - `--compile-exprs-json`
- This mode is specifically for wrapper modules that import benchmark kernels
  from pyperformance benchmark files.
- Local test coverage added:
  - `scripts/arm/test_bench_pyperf_direct.py`
  - `Ran 2 tests ... OK`
- First isolated baseline/current compare with explicit kernel compilation:
  - `fannkuch` with `_fannkuch.fannkuch`: about `-6.55%`
  - `unpack_sequence` with `_unpack.do_unpacking`: about `+4.62%`
  - `scimark_monte_carlo` with `_scimark.MonteCarlo`: about `-9.62%`
  - `go` with `Board.useful + UCTNode.play + UCTNode.random_playout`: about `+10.07%`
- Remaining representative-set results with the same explicit-kernel mode:
  - `scimark_sor` with `_scimark.SOR_execute`: about `+0.67%`
  - `scimark_lu` with `_scimark.LU_factor`: about `-6.98%`
  - `nbody` with `bench_nbody + advance`: about `+1.36%`
  - `spectral_norm` with `bench_spectral_norm + eval_AtA_times_u + part_A_times_u + part_At_times_u`: about `+9.38%`
  - `chaos` with `create_image_chaos + transform_point + get_random_trafo`: about `+1.91%`
  - `raytrace` with `Scene.render + Scene.rayColour + firstIntersection`: about `-2.62%`
- Immediate conclusion:
  - the explicit-kernel compare path is the first trustworthy fresh compare
    mode after the harness cleanup
  - it also shows that some earlier “all-green” conclusions from the
    `compile_strategy none` path were overstated
- current representative-set picture is mixed rather than uniformly positive
- the clearest remaining regression signals in kernel-targeted mode are now:
  - `go`
  - `spectral_norm`

## 2026-04-12 auto-JIT helper gate

- Added a regular auto-JIT gate in `jitVectorcall` for attr-heavy object helper
  shapes.
- Added two ARM regression tests:
  - `test_attr_heavy_object_helper_skips_autojit_compile`
  - `test_numeric_hot_loop_still_autojit_compiles`
- Fresh ARM helper verification with a new driver venv passed:
  - `Ran 95 tests in 66.409s`
  - `OK`
- Fresh semantic A/B on ARM:
  - base `fc1bf253` still auto-compiles the synthetic `useful_fast`
  - current `fd2ae6f5` no longer auto-compiles `useful_fast`
  - both revisions still auto-compile the numeric hot loop
- A real `bm_go.versus_cpu()` probe on the fresh current driver venv still
  segfaults when CinderX is enabled, and succeeds with `CINDERX_DISABLE=1`.
- Current interpretation:
  - the new gate is working as intended on the regular auto-JIT scheduling path
  - but it is not sufficient to make the full `bm_go` benchmark path stable
  - the remaining `go` problem should be treated as a broader CinderX-enabled
    benchmark crash, not as proof that the new gate regressed performance

## 2026-04-12 narrowed helper gate

- Startup-state correction:
  - installed current venv comes up as:
    - `cinderx_initialized = true`
    - `jit_enabled = true`
    - `compile_after = null`
  - `PYTHONJITDISABLE=1` keeps CinderX loaded but disables the JIT
  - `CINDERX_DISABLE=1` disables `_cinderx` entirely
- The earlier \"any CinderX-enabled bm_go crashes\" statement was too broad.
  A plain `bm_go` probe with a stubbed `pyperf` import succeeds in the default
  current startup state.
- The real regression introduced by `fd2ae6f5` was narrower:
  - it blocked `Board.useful`-like helpers from regular auto-JIT
  - that behavior is now covered by
    `test_attr_heavy_helper_with_internal_calls_still_autojit_compiles`
- `6a7e4f9a` refines the gate so it only suppresses helpers that are:
  - call-free
  - attr-heavy
  - loop-backed (have a backward jump)
- Fresh ARM helper run on `/root/venv-cinderx314-autojit-gate3`:
  - `Ran 96 tests in 65.857s`
  - `OK`
- Fresh regular auto-JIT `bm_go` compare with stubbed `pyperf`:
  - baseline `fc1bf253`: `0.09656633200029319`
  - current `6a7e4f9a`: `0.1031204009996145`
  - delta: about `+6.79%`
  - both sides now compile:
    - `Board.useful_fast`
    - `Board.useful`
    - `UCTNode.random_playout`
- Fresh regular auto-JIT `fannkuch` guardrail:
  - baseline: `2.3607938189998094`
  - current: `2.3303426259990374`
  - delta: about `-1.29%`
- Updated conclusion:
  - the narrowed gate is acceptable on correctness and preserves a hot-loop
    winner
  - the initial small `go` gap needed thicker confirmation before treating it
    as actionable
- 15-sample recheck:
  - `bm_go` regular auto-JIT compare:
    - baseline: `0.09528918399882969`
    - current: `0.09401855399846681`
    - delta: about `-1.33%`
  - `fannkuch` regular auto-JIT compare:
    - baseline: `2.3779402840009425`
    - current: `2.3718443339985242`
    - delta: about `-0.26%`
- Current conclusion:
  - `go` is no longer a stable regression after thick-sample confirmation
  - the narrowed helper gate now looks acceptable on both correctness and
    performance

## 2026-04-12 next profitability direction

- Current `bm_go` compiled set still includes many object-heavy methods, and
  they are not obviously a mistake:
  - suppressing constructors regresses badly
  - suppressing broad logic methods regresses even more
- So the next direction should not be \"compile less\".
- Inline cache stats do not show obvious benchmark-specific `load_method`
  misses, so the next likely win is not a simple cache-miss bugfix.
- Focused suppression showed two especially valuable compiled methods:
  - `Square.find`
  - `Board.useful_fast`
- That points to a more promising next generalized opportunity:
  - keep improving exact/self/attr-derived object call chains
  - especially issue60-style profile-driven method-call fast paths that make
    hot calls easier for the inliner to see

## 2026-04-14 passnull validation

- The current local fix under test is a one-line null guard in
  [pass.cpp](C:/work/code/cinderx1/cinderx/cinderx/Jit/hir/pass.cpp):
  - `while (value != nullptr && value->instr()->IsAssign())`
- Added a smaller regression guard in
  [test_arm_runtime.py](C:/work/code/cinderx1/cinderx/cinderx/PythonLib/test_cinderx/test_arm_runtime.py):
  - `test_recursive_coroutine_hir_inliner_force_compile_does_not_crash`
- Clean isolated ARM helper validation:
  - workdir: `/root/work/cinderx-passnull`
  - venv: `/root/venv-cinderx314-passnull`
  - helper flags:
    - `SKIP_PYPERF=1`
    - `BUILD_NO_ISOLATION=1`
    - `ARM_RUNTIME_SKIP_TESTS=collection_derived_monomorphic_method_load_restores_inlining`
  - result:
    - `Ran 98 tests in 64.585s`
    - `OK`
- Real benchmark-source probes with HIR inliner enabled:
  - `bm_go.versus_cpu()`:
    - 3/3 runs returned `5`
    - no crash
  - `bm_fannkuch.fannkuch(DEFAULT_ARG)`:
    - 3/3 runs returned `30`
    - no crash
- Current conclusion:
  - the `Send` null-guard should be treated as an independent correctness fix
    and can be landed without waiting for the collection-derived MWV work.

## 2026-04-14 collection-derived test-path correction

- The collection-derived red test was re-examined on the stable `passnull`
  install.
- Important finding:
  - `Board.useful()` is already JIT-compiled after the warmup loop even with
    `compile_after_n_calls(1000000)`
  - this happens because the loop can still enter JIT through the hot-loop
    path during warmup
- That means the old test shape:
  - warmup
  - `force_compile(Board.useful)`
  did not reliably exercise the explicit compile path.
- Corrected force-compile probe:
  - warmup
  - `force_uncompile(Board.useful)` if already compiled
  - `force_compile(Board.useful)`
- Observed ARM result on the stable install:
  - `compiled_before = True`
  - `compiled_after_uncompile = False`
  - `compiled_after_compile = True`
  - `num_inlined_functions = 1`
  - `result = 36`
- Immediate implication:
  - the collection-derived unit test needs to clear warmup state first
  - otherwise it is not a trustworthy signal for explicit compile-path
    regressions
- Additional clarification:
  - after explicit uncompile/recompile, collection-derived success is visible
    as `num_inlined_functions >= 1`
  - the final optimized HIR does not need to retain a `VectorCall`, because a
    successful inline can consume that intermediate call shape

## Initial prioritization

当前最可能在两天内打出“本质飞跃”的，不是去补全所有大能力，而是：

1. 验证 / benchmark 基础设施稳定化
2. profitability / feedback 决策面增强
3. 对象模型 / method/attr 高价值点的窄优化

## Locked assumptions

### Baseline policy

- 默认 A/B 基线不使用浮动的 `origin/main`
- 默认使用“冲刺开始时固定的已知良好基线 commit”
- 当前建议固定为：
  - `fb105b6b`
  - 原因：
    - 这是最近一轮 runtime-affecting profitability gate 收敛后的稳定点
    - 后续文档提交不会污染性能基线

### Priority policy

- 优先级顺序：
  1. 保住 current hot-loop winners 的已得收益
  2. 在不伤前者的前提下，收 object-heavy/search-heavy regressions
  3. 再考虑更广泛的优化扩张

- 解释：
  - 两天冲刺不适合用“大幅收紧策略换局部 regressions 消失”的方式制造新的净损失
  - 所有针对 object-heavy regressions 的策略，都必须经过 hot-loop winners guardrail

### Guardrail set

- 热循环正向收益保护集：
  - `fannkuch`
  - `unpack_sequence`
  - `comprehensions`
  - `scimark_monte_carlo`
  - `scimark_sor`

- object-heavy / search-heavy 风险集：
  - `go`
  - `chaos`
  - `raytrace`
  - 其他确认属于该类的 case

## Why this ordering

- 如果 harness 不稳，所有后续性能结论都会反复推翻
- 如果 profitability 还只靠 ad-hoc gate，运行时优化很难持续扩展
- 如果对象模型优化还是大量靠手工 heuristic，真实动态 workload 的上限会一直被卡住

## Explicit defer list

- 完整 tiering
- 广覆盖 OSR
- 完整 escape analysis
- 完整 scalar replacement
- 完整 profile-guided recompilation loop
