# Mistake Ledger

## 2026-04-11 Day 1 follow-up

- Treating an empty summary as a pyperformance execution failure would have
  sent the sprint down the wrong path; always inspect the raw JSON schema
  before changing runtime or harness behavior.
- Remote helper workdirs are archive-backed. Any metadata field that wants a
  commit id must come from the caller, not from `git rev-parse` on the host.

## 2026-04-11

- 不要把“补齐所有顶级 JIT 特性”当成两天内可交付目标。
- 不要在 harness 不稳定时，把大部分时间花在解释微小 benchmark 摆动上。
- 不要同时推进太多大方向；两天冲刺必须先做排序。
