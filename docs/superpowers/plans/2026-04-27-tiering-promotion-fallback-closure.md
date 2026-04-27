# Tiering Promotion and Fallback Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the next mainline tiered-JIT gap by making baseline-to-optimized promotion, skipped promotion decisions, and fallback-to-interpreter transitions observable through one tier state surface.

**Architecture:** Keep this slice narrow. Baseline-compiled functions remain tier-managed through a lightweight vectorcall wrapper so they can still reach optimized tier after the optimized threshold. `Context` remains the owner of per-function active tier and transition telemetry, while `pyjit.cpp` records runtime promotion decisions and explicit fallback events.

**Tech Stack:** C++20, CPython vectorcall APIs, CinderX JIT `Context`, `cinderx.jit` Python wrappers, `unittest`, ARM targeted validation

---

### Task 1: Add failing tiering tests

**Files:**
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/PythonLib/test_cinderx/test_jit_tiering.py`

- [x] Add a test showing that a function can auto-compile to baseline first, then auto-promote to optimized after the optimized threshold.
- [x] Add a test showing that tiering stats include promotion decision records for both skipped and promoted baseline calls.
- [x] Add a test showing that `force_uncompile()` records a fallback transition to `interp`.
- [x] Run the targeted test on an ARM build before implementation and confirm the new expectations fail.

### Task 2: Extend tier telemetry data

**Files:**
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/context.h`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/context.cpp`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/pyjit.cpp`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/PythonLib/cinderx/jit.py`

- [x] Add transition reasons for auto-threshold activations, force activations, and explicit fallback.
- [x] Add promotion decision telemetry with function name, current tier, target tier, action, and reason.
- [x] Return both `events` and `decisions` from `jit.get_and_clear_tiering_stats()`.

### Task 3: Add baseline-to-optimized promotion loop

**Files:**
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/pyjit.cpp`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/context.cpp`

- [x] Keep baseline functions behind a tiering vectorcall entry instead of permanently replacing their Python vectorcall with the raw baseline entry.
- [x] On each baseline-tier call, record why optimized promotion is skipped when the optimized threshold is absent or not reached.
- [x] When the optimized threshold is reached, compile or attach optimized code and record the promotion decision and tier transition.
- [x] Leave optimized functions on the raw optimized entry once promotion succeeds.

### Task 4: Verify and record evidence

**Files:**
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/findings.md`

- [x] Run the targeted tiering tests locally and record whether they skip cleanly without a local JIT extension.
- [x] Run the targeted tiering tests on ARM and record the passing tests.
- [x] Run a small direct ARM probe for baseline-to-optimized automatic promotion and capture the event/decision shape.
- [x] Update `findings.md` with the exact commands and results.

### Task 5: Extend fallback reasons to deopt-all paths

**Files:**
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/context.h`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/pyjit.cpp`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/PythonLib/test_cinderx/test_jit_tiering.py`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/findings.md`

- [x] Add a failing test showing that `jit.disable(deopt_all=True)` records a fallback transition for a baseline-tier function.
- [x] Thread explicit deopt reasons through `deoptFuncImpl()` and the deopt-all path.
- [x] Preserve existing `force_uncompile()` fallback telemetry.
- [x] Rebuild on ARM and run the full targeted tiering API suite.
- [x] Run a direct ARM probe for the public event shape and update `findings.md`.

### Task 6: Fold deopt state into unified tier info

**Files:**
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/context.h`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/context.cpp`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/Jit/pyjit.cpp`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/PythonLib/cinderx/jit.py`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/cinderx/PythonLib/test_cinderx/test_jit_tiering.py`
- Modify: `C:/work/code/cinderx5/.worktrees/baseline-tier-fastmode-mvp/findings.md`

- [x] Add a failing test showing that `get_function_tier_info()` exposes deopted state and the last fallback reason.
- [x] Store the last tier transition in `Context` independently of the clearable event stream.
- [x] Expose `is_deopted` and `last_transition` through the public tier info dictionary.
- [x] Verify both `disable_deopt_all` and `function_modified` paths on ARM.
