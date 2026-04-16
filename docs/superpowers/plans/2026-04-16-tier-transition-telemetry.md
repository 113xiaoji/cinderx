# Tier Transition Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class observability for JIT tier transitions so we can inspect both per-function tier state and global tier transition events without changing promotion policy yet.

**Architecture:** Keep this slice intentionally small. Extend `Context` with a tiny transition event buffer that records active-tier changes when a function is finalized or deoptimized, then expose that through a new Python telemetry API. Add a per-function inspection API that reports the active tier and which compiled tiers currently exist. Tests stay in `test_jit_tiering.py` and exercise only the public Python surface.

**Tech Stack:** C++20, CPython 3.14 extension APIs, `cinderx.jit` Python wrappers, `unittest`

---

### Task 1: Add failing Python tests for tier observability

**Files:**
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/PythonLib/test_cinderx/test_jit_tiering.py`

- [ ] Add a red test for `get_function_tier_info()`.
- [ ] Add a red test for `get_and_clear_tiering_stats()`.
- [ ] Run the targeted test file and confirm it fails for missing API surface.

### Task 2: Add context-side telemetry and Python API exposure

**Files:**
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/context.h`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/context.cpp`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/pyjit.cpp`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/PythonLib/cinderx/jit.py`

- [ ] Add a minimal tier-transition event struct and storage in `Context`.
- [ ] Record transitions when the active tier changes and when a compiled function falls back to interp.
- [ ] Expose Python APIs for per-function tier info and global tier transition stats.

### Task 3: Verify and record

**Files:**
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/findings.md`

- [ ] Re-run `test_jit_tiering.py` and confirm all new tests pass.
- [ ] Record the new telemetry surface and example event shapes in `findings.md`.
