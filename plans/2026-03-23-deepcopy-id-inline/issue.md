# [arm-opt][pyperformance] deepcopy: inline builtin id() on guarded hot paths

## Problem description

- Workload:
  - `deepcopy`
- Symptom:
  - guarded builtin `id()` calls still lower to generic `VectorCall`
- Why it matters:
  - `copy.deepcopy` repeatedly calls `id()` for memo bookkeeping, so extra call
    dispatch and object boxing cost is visible in aggregate

## Current IR

- To be refreshed on current tip for this round.

## Target HIR

- Preferred target:
  - `GuardIs<builtin_id>` + direct object-pointer-to-integer conversion + box

## Optimization suggestions

- First try a pure-HIR builtin-call simplification.
- Only widen the change if audit-hook correctness or backend support demands it.

## Minimal reproducer

- `copy.deepcopy` on a shared-reference object graph
- and a smaller `id(obj)`-heavy helper when needed for exact HIR inspection
