# Task Plan: ARM JIT Performance Iteration 2026-02-19

## Goal

Deliver one additional ARM64 JIT optimization iteration with verified `from -> to` performance results (richards), and confirm JIT is actually active during benchmark runs.

## Phases

- [x] Phase 1: Session recovery and constraints check
- [x] Phase 2: Current state inspection (code + benchmarks + logs)
- [x] Phase 3: Design and implementation plan for next optimization
- [x] Phase 4: TDD (add/update failing regression/perf guard test)
- [x] Phase 5: Implement minimal code change
- [x] Phase 6: Verify locally + remote unified ARM pipeline
- [x] Phase 7: Record findings (`from -> to`) and summarize

## Key Questions

1. Which remaining AArch64 codegen pattern is both low-risk and likely to improve richards?
2. Can we demonstrate "real improvement" with repeated samples instead of single-sample noise?
3. Are there unsupported ARM codegen paths still causing deopt/fallback in benchmark workers?

## Decisions Made

- Continue from branch `arm-jit-perf` at `778d01d0`.
- Use the existing remote entrypoint (`scripts/push_to_arm.ps1`) for all authoritative validation.
- Keep benchmark focus on `pyperformance richards` first, then extend after stable gain is proven.
- Rebase onto latest `origin/main` first (user chose conflict-resolution path) before next ARM perf iteration.
- Optimize AArch64 call emission by lazily creating helper stubs and routing `instr == nullptr` calls directly via literals.
- Use compactness guard TDD cycle (`RED` fail threshold below baseline, then `GREEN` after code change).

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| `python.exe` cannot execute `session-catchup.py` on this Windows host | 1 | Switched to manual recovery using git status + existing `findings.md` + explicit plan/progress files. |
| `sync_upstream.ps1` blocked due dirty tree | 1 | Committed planning/work-in-progress files before remote runs. |
| Rebase conflict on `cinderx/Jit/pyjit.cpp` while syncing to latest main | 1 | Resolved conflict and continued rebase to completion. |
| PowerShell interpolation broke remote loop timestamp command | 1 | Switched to explicit output names for manual benchmark samples. |

## Status

Currently: All planned phases complete for this iteration; runtime perf signal remains mixed and needs controlled multi-sample A/B before claiming speedup.
