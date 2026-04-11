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
