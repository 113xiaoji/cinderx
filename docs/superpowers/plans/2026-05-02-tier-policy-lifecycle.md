# Tier Policy Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the tier-policy MVP by turning compile-failure blocking from a permanent latch into an explainable backoff lifecycle with recovery, reset, and remote functional coverage.

**Architecture:** Keep the policy state in the existing per-function `FunctionTierState` model. Add bounded compile-failure cooldown/backoff counters, expose them through `jit.get_function_tier_state()`, and update policy decisions at the existing `shouldAttemptOptimizedPromotion()`, `recordCompileFailure()`, and successful `finalizeFunc()` boundaries.

**Tech Stack:** C++ JIT runtime (`cinderx/Jit/context.*`, `cinderx/Jit/pyjit.cpp`) plus Python regression coverage in `cinderx/PythonLib/test_cinderx/test_jit_tiering.py`. All authoritative verification must use `/root/work/incoming/remote_update_build_test.sh`.

---

### Task 1: Add RED coverage for compile-failure cooldown recovery

**Files:**
- Modify: `cinderx/PythonLib/test_cinderx/test_jit_tiering.py`

- [x] **Step 1: Write the failing test**

Add a focused script test that:
- causes an optimized compile failure with a tiny code-size limit
- observes `policy_state == "compile_failure_cooldown"`
- performs enough lazy-promotion decisions to exhaust the cooldown
- verifies a later promotion is allowed and the function reaches optimized tier after the code-size limit is restored
- checks that `compile_failure_cooldown_remaining`, `compile_failure_backoff`, and `compile_failure_streak` are exposed

- [x] **Step 2: Run RED remotely**

Run:

```bash
SKIP_PYPERF=1 SKIP_PYPERF_SETUP=1 EXTRA_VERIFY_CMD='PYTHONPATH=cinderx/PythonLib/test_cinderx $PYTHON -m unittest test_jit_tiering.TieringApiTests.test_compile_failure_cooldown_expires_and_allows_repromotion -v' /root/work/incoming/remote_update_build_test.sh
```

Expected: FAIL because the new tier-state fields and cooldown expiry behavior do not exist yet.

### Task 2: Implement bounded cooldown/backoff lifecycle

**Files:**
- Modify: `cinderx/Jit/context.h`
- Modify: `cinderx/Jit/context.cpp`
- Modify: `cinderx/Jit/pyjit.cpp`
- Modify: `cinderx/PythonLib/cinderx/jit.py`
- Modify: `cinderx/cinderjit.pyi` if public type stubs need to stay aligned

- [x] **Step 1: Extend `FunctionTierState`**

Add:
- `compile_failure_streak`
- `compile_failure_backoff`
- `compile_failure_cooldown_remaining`
- `policy_resets`

- [x] **Step 2: Update compile-failure policy**

On `recordCompileFailure()`:
- increment total failures and streak
- set a bounded cooldown derived from the streak
- set `policy_state = compile_failure_cooldown`
- set `promotion_blocked = true`
- keep `last_policy_event/reason` explicit

- [x] **Step 3: Update promotion decisions**

On `shouldAttemptOptimizedPromotion()`:
- decrement compile-failure cooldown for blocked decisions
- keep blocked decisions separate from compile attempts
- clear the block only after the cooldown has expired
- allow the next promotion decision and record `compile_failure_cooldown_expired`

- [x] **Step 4: Reset on successful optimized compile**

On successful `finalizeFunc()`:
- reset compile-failure streak/backoff/cooldown
- clear the promotion block
- increment `policy_resets`
- reset deopt budget to the default

### Task 3: Verify policy lifecycle and preserve existing blocking behavior

**Files:**
- Modify: `findings.md`
- Modify: `progress.md`
- Modify: `task_plan.md`

- [x] **Step 1: Run focused GREEN remotely**

Run the new focused test through the remote entrypoint. Expected: PASS.

- [x] **Step 2: Run the full tiering suite remotely**

Run:

```bash
SKIP_PYPERF=1 SKIP_PYPERF_SETUP=1 EXTRA_VERIFY_CMD='PYTHONPATH=cinderx/PythonLib/test_cinderx $PYTHON -m unittest test_jit_tiering -v' /root/work/incoming/remote_update_build_test.sh
```

Expected: default ARM runtime and `test_jit_tiering` both pass.

- [x] **Step 3: Record evidence**

Append RED/GREEN results and remaining risks to `findings.md`, log the session in `progress.md`, and mark this plan in `task_plan.md`.

### Completion Evidence

- RED remote evidence:
  - cooldown/backoff tests first failed with missing `compile_failure_backoff` telemetry.
  - code-change reset test later failed with stale `compile_failure_cooldown` state after `__code__` replacement.
- Debugging evidence:
  - full remote tiering run exposed a hot-loop OSR regression where one interpreted hot loop consumed the entire compile-failure cooldown and immediately recompiled.
  - review follow-up showed the first conservative OSR fix could become permanent for OSR-only recovery.
  - final fix: age hot-loop OSR cooldown once per interpreted activation, then defer actual OSR promotion until a later activation.
- GREEN remote evidence:
  - focused lifecycle set:
    - `test_function_code_change_resets_policy_backoff`
    - `test_compile_failure_backoff_blocks_hot_loop_osr`
    - `test_compile_failure_cooldown_expires_and_allows_repromotion`
    - `test_repeated_compile_failures_grow_policy_backoff`
    - result: `Ran 4 tests in 0.219s`, `OK`
  - focused review follow-up set:
    - `test_successful_compile_without_failure_does_not_count_policy_reset`
    - `test_compile_failure_cooldown_expires_and_allows_repromotion`
    - `test_hot_loop_osr_cooldown_ages_across_calls`
    - result: `Ran 3 tests in 0.185s`, `OK`
  - full remote entrypoint:
    - default ARM runtime: `Ran 102 tests in 16.401s`, `OK (skipped=3)`
    - full `test_jit_tiering`: `Ran 26 tests in 5.600s`, `OK`
