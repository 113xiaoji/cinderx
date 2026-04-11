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
