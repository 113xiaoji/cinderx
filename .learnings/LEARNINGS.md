# LEARNINGS

## 2026-04-07 issue85 kickoff

- `#76` 的 Phase 1 主线已经不再是主要问题，新的重点是 profitability，而不是 correctness。
- object-heavy / search-heavy workload 需要单独看 shape，不要和 wrapper pollution 混为一谈。
- `go` 这类 case 的关键是：
  - 回边循环里调用密集
  - 属性访问和状态迁移密集
  - 即使只有一个函数 same-activation OSR，也可能带来明显回退
- `comprehensions` 这类 case 要谨慎下结论：
  - 端到端 timing 需要多轮重复验证
  - 如果 `osr_count` 始终是 `0`，就不要把它归因为 hot-loop OSR
