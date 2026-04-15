# Tiered JIT Mainline Gap Status

## Mainline Goal

当前真正的主线不是继续堆 benchmark-specific helper 策略，而是补齐下面这条能力链：

- `Tier 0`: 解释器
- `Tier 1`: baseline-tier fast-mode
- `Tier 2`: 现有 optimizing JIT

最终目标不是“某几个用例跑快了”，而是：

1. 代码可以先以很低成本脱离解释器
2. 热点能够再自然升到 optimizing tier
3. tier state / promotion / fallback / 验证口径清晰
4. `go / richards / deltablue / raytrace` 这类 workload 只是用来验证这套能力，而不是替代这套能力

## Progress Estimate

基于当前分支状态，主线完成度这样看最接近事实：

- `验证链路 / ARM 闭环 / benchmark 降噪`
  - 大约 `75-85%`
  - 这一层已经做了很多，足以让我们看清真正的 compiler/tiering 问题

- `baseline-tier fast-mode MVP 骨架`
  - 大约 `45-55%`
  - 已经有实现、测试、远端闭环和基本 tier 状态，但还不算完整 tiering 能力

- `真正的分层 JIT 能力闭环`
  - 大约 `30-40%`
  - 这是当前真正的差距，也是后续工作的主线

## What Is Already Solid

### 1. ARM Verification Loop Exists

当前已经有稳定的远端闭环：

- Windows workspace -> ARM build/update helper
- ARM smoke / runtime tests
- pyperformance single-value gate
- artifact + `findings.md` 记录

这意味着后续不再需要把“怎么验证”当成主问题。

### 2. Helper/Worker Noise Was Reduced

最近几轮实际拿到的收益，主要集中在 worker/helper 层：

- `go`
  - 通过 worker JIT 启动时机、threshold 保留、gate tuning 拿到了明显收益
- `richards`
  - `eager worker JIT` 已经有 same-workdir A/B 和 fresh helper artifact 支撑
- `deltablue`
  - `AUTOJIT_GATE=20` 有 repeatable signal
- `richards_super`
  - 适合 `broad __main__:* + defer=0`
- `raytrace`
  - helper gate 有信号，但不如 `go / richards` 那样强

这些工作是有价值的，但它们解决的是“先把冷态和 worker 噪音降下去”，不是主线闭环本身。

### 3. Baseline-Tier MVP Shell Exists

当前分支已经具备 baseline-tier fast-mode MVP 的关键壳层：

- tier-aware API / runtime 路径
- baseline/optimized 的基本区分
- ARM 回归与 benchmark 口径

这让我们已经不在“完全没有分层”的阶段了。

## What Is Still Missing

### 1. Tier 1 -> Tier 2 Promotion Is Not a Mature System Yet

虽然 baseline fast-mode 已经有雏形，但下面这些能力还没有真正闭环：

- 正式 tier state 管理
- baseline -> optimized promotion 策略
- deopt / fallback 回落策略
- 稳定 feedback 如何喂给 optimizing tier

现在更像“有 tier-aware MVP”，还不是“完整分层 JIT”。

### 2. Hot Call Chains Still Do Not Collapse Reliably

对 `richards` 真实热点的观测表明，最终 HIR 里仍残留明显的方法调用链成本：

- `Task.runTask`
  - `CallMethod=4`
  - `LoadMethodCached=4`
- `HandlerTask.fn`
  - `CallMethod=6`
  - `LoadMethodCached=6`
- `WorkTask.fn`
  - `CallMethod=2`
  - `LoadMethodCached=2`

这意味着：

- helper 层已经把冷态噪音降下来了
- 但真正热点还没进入“optimizing tier 最擅长吃掉”的形状

### 3. Inliner / Preload / Simplify Still Do Not Form a Closed Loop

最近几轮调查已经确认两个重要现象：

1. 有些 inherited Python method path 最终确实能在 late simplify 里变成 `VectorCall`
2. 但真实 richards 热函数的 `num_inlined_functions` 仍然可能是 `0`

也就是说，当前并不是“做不出 VectorCall”，而是：

- 有些 `VectorCall` 暴露得太晚
- 或者看到了 `VectorCall` 也因为 `NeedsPreload` 等原因吃不进去

这正是 compiler/tiering 闭环还没打通的证据。

### 4. We Still Do Not Have a Benchmark-Validated Richards Hot-Path Win Inside the Compiler

目前 `richards` 的收益主要还来自 helper/worker 层，而不是 compiler hot path 本体。

也就是说：

- 冷态路径比之前更干净了
- 但真正的“richards 热点在 compiler 内核里被系统性吃掉”还没发生

这正是为什么整体主线完成度仍然只有 `30-40%` 左右。

## Why Recent Benchmark Work Still Mattered

虽然最近不少工作看起来像 benchmark 战术优化，但它们并没有偏离主线到完全无关：

- 它们帮我们把启动噪音降下去
- 让我们第一次能清楚看到真正的 compiler/tiering 缺口
- 也暴露出当前最真实的主线 gap：
  - hot call chain 还不够平
  - late `VectorCall` 还不能稳定被 tier 2 吃掉
  - preload / simplify / inliner 之间还缺闭环

所以最近这些工作更像“主线前置清障”，而不是主线本身。

## Current Mainline Priority

从现在开始，主线优先级应当重新收紧成下面三件事：

### Priority 1: Stop Chasing More Helper-Only Wins

除非出现新的 benchmark blocker，否则不再把 benchmark-specific helper 规则当成主目标。

原因：

- 低垂果子已经基本摘完
- 再做下去容易掩盖真正的 compiler gap

### Priority 2: Make Richards Hot Call Chains Inline-Friendly

接下来最值得只盯一件事：

- `Task.runTask`
- `HandlerTask.fn`
- `WorkTask.fn`

目标不是“再加一个 heuristic”，而是：

- 让这些热路径更稳定地进入可 inline、可继续优化的最终形状

### Priority 3: Turn the Result Back Into Tiering Capability

每一轮 hot-path 优化都必须回到主线问题上回答：

- 这是 baseline tier 缺口吗？
- 这是 preload / inliner / simplify 的协同缺口吗？
- 这是 promotion / feedback 缺口吗？
- 还是只是一次 isolated peephole？

只有这样，工作才是在补齐分层 JIT，而不是只在“刷 benchmark 分数”。

## Recommended Next Phase

建议下一阶段按这个顺序推进：

1. 以 `richards` 为主样本，继续只调查 hot call chain 的 root cause
2. 只接受能解释为“tiering/compiler 能力补齐”的优化
3. benchmark 只作为验证，不再作为选题本身
4. 等 hot-path 这层更平以后，再重新回看 baseline -> optimized promotion 的正式闭环

## Bottom Line

一句话总结当前状态：

- `ARM 验证链路` 和 `benchmark 降噪` 已经做得比较多
- `baseline-tier fast-mode` 也已经有壳层
- 但距离“真正的分层 JIT 能力闭环”还差一层最关键的东西：
  - 让热点调用链稳定进入 optimizing tier 能真正吃掉的形状

这才是当前主线剩余工作的核心。
