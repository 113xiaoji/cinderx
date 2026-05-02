# Tier Policy Decision Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tiered-JIT promotion policy explainable by recording why promotion was attempted, blocked, or skipped.

**Architecture:** Extend the existing per-function `FunctionTierState` rather than adding another side map. Keep policy telemetry read-only from Python through `jit.get_function_tier_state()`, and update it only at the existing policy decision boundaries: `shouldAttemptOptimizedPromotion()`, `recordPromotionAttempt()`, compile-failure backoff, runtime fallback, and type invalidation.

**Tech Stack:** C++ JIT runtime (`cinderx/Jit/context.*`, `cinderx/Jit/pyjit.cpp`), Python API fallback (`cinderx/PythonLib/cinderx/jit.py`), unittest regression coverage (`cinderx/PythonLib/test_cinderx/test_jit_tiering.py`), remote ARM entrypoint (`/root/work/incoming/remote_update_build_test.sh`).

---

### Task 1: Add RED Coverage For Decision Telemetry

**Files:**
- Modify: `cinderx/PythonLib/test_cinderx/test_jit_tiering.py`

- [ ] **Step 1: Write a failing test for allowed promotion decisions**

Add a test that compiles baseline first, promotes with `force_compile()`, then checks:

```python
state["promotion_decisions"] == 1
state["promotion_blocked_attempts"] == 0
state["last_promotion_decision"] == "attempt"
state["last_policy_event"] == "promotion_attempt"
state["last_policy_reason"] == "force_compile"
```

- [ ] **Step 2: Write a failing test for blocked promotion decisions**

Extend the compile-failure cooldown precompile-all regression so that after `precompile_all()` is blocked it checks:

```python
state["promotion_decisions"] == 2
state["promotion_attempts"] == 1
state["promotion_blocked_attempts"] == 1
state["last_promotion_decision"] == "blocked"
state["last_policy_event"] == "promotion_blocked"
state["last_policy_reason"] == "compile_failure_cooldown"
```

- [ ] **Step 3: Verify RED through the remote entrypoint**

Run the focused tiering test through `/root/work/incoming/remote_update_build_test.sh`.

Expected result: fail with missing keys such as `KeyError: 'promotion_decisions'`.

### Task 2: Extend FunctionTierState

**Files:**
- Modify: `cinderx/Jit/context.h`
- Modify: `cinderx/Jit/context.cpp`
- Modify: `cinderx/Jit/pyjit.cpp`
- Modify: `cinderx/PythonLib/cinderx/jit.py`

- [ ] **Step 1: Add state fields**

Add these fields to `FunctionTierState`:

```cpp
std::size_t promotion_decisions{0};
std::size_t promotion_blocked_attempts{0};
std::string last_promotion_decision{"none"};
std::string last_policy_event{"none"};
std::string last_policy_reason{"none"};
```

- [ ] **Step 2: Update promotion policy checks**

In `Context::shouldAttemptOptimizedPromotion()`:

```cpp
state.promotion_decisions++;
state.last_promotion_reason = reason;
if (state.promotion_blocked) {
  state.promotion_blocked_attempts++;
  state.last_promotion_decision = "blocked";
  state.last_policy_event = "promotion_blocked";
  state.last_policy_reason = state.promotion_blocked_reason;
  state.last_transition = "promotion_blocked";
  return false;
}
state.last_promotion_decision = "attempt";
state.last_policy_event = "promotion_allowed";
state.last_policy_reason = reason;
return true;
```

- [ ] **Step 3: Update attempt and blocker events**

In `recordPromotionAttempt()`, set `last_policy_event` to `promotion_attempt` and `last_policy_reason` to the promotion reason. In blocker paths, set `last_policy_event` and `last_policy_reason` to the policy reason that explains the block.

- [ ] **Step 4: Expose fields through Python**

Add dictionary entries in `get_function_tier_state()` and matching fallback defaults in `cinderx/PythonLib/cinderx/jit.py`.

### Task 3: GREEN Verification And Evidence

**Files:**
- Modify: `findings.md`
- Modify: `progress.md`
- Modify: `task_plan.md`

- [ ] **Step 1: Run focused remote tiering verification**

Run `test_jit_tiering` through the remote entrypoint with pyperformance setup skipped.

Expected result: `OK`.

- [ ] **Step 2: Run default ARM runtime guard**

Use the same remote entrypoint. The default ARM runtime suite must still pass before completion.

- [ ] **Step 3: Record evidence**

Append RED/GREEN results and any root-cause notes to `findings.md`, and update `progress.md` plus `task_plan.md`.
