# Proposal

## Case

`issue85-object-heavy-osr-profitability`

## Problem

`#76` 的 same-activation hot-loop OSR 在 object-heavy / search-heavy workload 上仍可能出现回退。

## Candidate directions

### A. 在 `pyjit.cpp` 的 hot-loop OSR 入口继续做 profitability gate

- 优点：
  - 改动面最小
  - 直接作用于 same-activation OSR
  - 不会把 `builder.cpp` 的广义 specialization policy 一起带动
- 风险：
  - 仍然是 heuristic
  - 需要持续验证不会误伤正收益 case

### B. 在 `builder.cpp` 中引入更广义的 shape score

- 优点：
  - 从 IR 形状层面更系统
  - 长期可能更容易统一 policy
- 风险：
  - 改动范围大
  - 更容易影响 `#76` 已经稳定的正向路径

### C. 对 benchmark / function 形状做更直接的特判

- 优点：
  - 最快止血
- 风险：
  - 泛化性差
  - 不适合作为长期策略

## Recommended direction

先走 **A**。

原因：

- 当前证据表明问题首先发生在 same-activation OSR profitability，而不是 HIR lowering correctness。
- `go` 这类回退已经能通过 `pyjit.cpp` 的入口策略被部分收住。
- 现在更需要做的是继续把 shape 规则收紧，而不是同时改更大范围的 builder policy。

## Scope

- 分析 object-heavy / search-heavy case 的真实 shape
- 区分 wrapper pollution 与 object-heavy 主问题
- 通过远端统一入口验证每一轮结论
- 在没有 reviewer 明确批准前，不做大范围 runtime 改写

## Non-goals

- 不把 `#85` 和 `#76` 的 correctness 主线重新混在一起
- 不在没有新假设和新验证的前提下重复尝试失败方案
