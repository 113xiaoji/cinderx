# AGENTS.md

## 2026-04-11 Day 1 sprint status

- Active case:
  - `plans/cases/jit-capability-two-day-sprint/`
- Current Day 1 focus:
  - Track A: stable remote A/B harness and summary artifacts
  - Track B: profitability / skip-reason observability
- Verified on ARM today:
  - full `test_arm_runtime.py` via remote helper: `Ran 91 tests ... OK`
  - `scripts/arm/test_pyperf_subset_tools.py`: `OK`
  - `bench_pyperf_direct.py` now reports `top_hot_loop_skips`
  - `run_pyperf_subset.sh` summary now retains benchmark rows even when raw
    pyperformance JSON omits benchmark names in `--debug-single-value` mode

## 2026-04-11 Day 2 sprint status

- Remote helper:
  - `SKIP_PYPERF=1` now exits after runtime smoke instead of entering
    pyperformance setup.
  - `BUILD_NO_ISOLATION=1` is now the preferred ARM helper mode on this host.
- Runtime direction in progress:
  - attr-heavy loop profitability gate in `cinderx/Jit/pyjit.cpp`
  - skip reason: `attr_heavy_loop`
- Latest ARM verification:
  - full remote helper path in skip mode:
    - `Ran 92 tests ... OK`
    - helper terminates at `SKIP_PYPERF=1 set; done after smoke.`
  - current direct benchmark runs now show skip reasons inside benchmark code
    for:
    - `go`
    - `chaos`
    - `raytrace`
  - clean direct baseline/current compare is now available for:
    - `fannkuch`
    - `go`
    - `chaos`
    - `raytrace`
- Current performance priority:
  - `go` improved strongly after skip caching and NO_JIT backedge rewriting
  - thicker samples now show:
    - `fannkuch` is effectively flat/slightly positive
    - `chaos` is modestly positive
    - `raytrace` median is slightly positive but still has warmup variance
  - broader direct coverage now exists for another 16 benchmarks
  - follow-up coverage fix for “compiled but no OSR entry” has now turned the
    previously confirmed regressions positive:
    - `unpack_sequence`
    - `spectral_norm`
    - `nbody`
    - `scimark_lu`
  - rerunning the broader direct matrix after that fix now shows no stable
    median regression in the currently measured broad set
  - 2026-04-12 follow-up:
    - clean helper verification initially exposed a real regression introduced
      after `91006d4c`
    - final current worktree now re-stabilizes the clean helper path:
      - `Ran 93 tests in 119.196s`
      - `OK`
      - `jit-effective-ok compiled_size 984 interp_calls 10`
    - key runtime adjustments:
      - defer no-OSR finalize to interpreter safe point
      - only no-OSR finalize loop-dominant shapes (no calls outside loop)
      - make `force_compile()` idempotent for already-compiled functions

本仓库当前有一个正在进行中的专项 case：`issue85-object-heavy-osr-profitability`。

工作约定：

- `#76` 的 Phase 1 MVP 主线已经完成，新的运行时代码工作默认视为 `#85` follow-up。
- `#85` 的事实源优先级：
  - `plans/cases/issue85-object-heavy-osr-profitability/`
  - `plans/2026-03-31-issue76-hot-loop-osr/`
  - 根目录 `findings.md`
- 远端验证入口统一使用：
  - `scripts/push_to_arm.ps1`
  - `scripts/arm/remote_update_build_test.sh`
- 不要把 pyperformance 端到端噪音直接当成 correctness 结论。
- 先做分析和计划，再做实现；先做定向验证，再宣称收益或回退。
- 对 `go` / `chaos` 这类 object-heavy / search-heavy case，优先按 shape/profitability 处理，不做 benchmark 名称特判。

如果修改 `cinderx/` 下代码，仍需遵守 [cinderx/AGENTS.md](C:/work/code/cinderx1/cinderx/cinderx/AGENTS.md) 中已有约束。
