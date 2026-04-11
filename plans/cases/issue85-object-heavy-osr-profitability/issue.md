# Issue

## Title

hot-loop OSR profitability: object-heavy / search-heavy workloads regress under same-activation OSR

## Current state

- 问题草稿已写在：
  - `plans/2026-04-04-hot-loop-osr-object-heavy-issue-draft.md`
- 当前还未确认是否已经在 GitHub 上成功创建 issue
- 当前最新分支下，原始 same-activation false-positive 形状已经没有 clean 的当前 reproducer。
- 因此 `#85` 更适合作为：
  - profitability / shape policy follow-up
  - 而不是当前 blocker 修复

## Goal

把这类 workload 从“已知问题”推进到“有清晰 shape taxonomy、策略边界、验证方法”的状态，并为后续实现提供稳定入口。
