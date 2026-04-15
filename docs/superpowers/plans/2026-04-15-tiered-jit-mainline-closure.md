# Tiered JIT Mainline Closure Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-anchor the branch on true tiered-JIT capability closure instead of further helper-only benchmark tuning.

**Architecture:** Freeze helper policy unless it blocks validation, then use `richards` as the primary hot-path sample to close the remaining compiler/tiering gaps: call-shape flattening, preload/inliner/simplify coordination, and eventual baseline->optimized promotion readiness. Treat benchmark numbers as validation outputs, not feature goals.

**Tech Stack:** CinderX JIT HIR passes, preloader/inliner pipeline, ARM runtime regression tests, ARM remote helper verification

---

### Task 1: Freeze helper strategy and protect focus

**Files:**
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/findings.md`

- [ ] Record that helper policy is no longer the mainline target unless a new blocker appears.
- [ ] Keep future benchmark-only A/B probes clearly separated from compiler-mainline work.

### Task 2: Use `richards` to isolate hot call-chain gaps

**Files:**
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/findings.md`

- [ ] Add only root-cause regression tests that explain why `Task.runTask`, `HandlerTask.fn`, or `WorkTask.fn` still retain `CallMethod/LoadMethodCached`.
- [ ] Validate each hypothesis first with targeted ARM repros before touching implementation.
- [ ] Reject any optimization that improves a synthetic test but does not survive `richards` same-workdir or fresh-helper verification.

### Task 3: Close preload / simplify / inliner coordination gaps

**Files:**
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/hir/preload.cpp`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/hir/simplify.cpp`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/compiler.cpp`

- [ ] Prefer the smallest change that converts a real hot callsite into an inline-friendly final shape.
- [ ] Treat `NeedsPreload`, late-emerging `VectorCall`, and post-simplify missed inlining as distinct root causes.
- [ ] Keep fixes scoped so they can be mapped back to tiered-JIT capability gaps, not one-off benchmark heuristics.

### Task 4: Re-map successful fixes to mainline capability closure

**Files:**
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/docs/superpowers/specs/2026-04-15-tiered-jit-mainline-gap-status.md`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/findings.md`

- [ ] For every compiler win, classify whether it closes a baseline-tier gap, a preload/inliner/simplify gap, or a promotion/feedback gap.
- [ ] Recompute the three headline completion estimates only when there is evidence that a real capability closed.
