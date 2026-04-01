# Progress Log: Issue 76 Hot-Loop OSR

## 2026-03-31

- Resumed Phase 0 debugging from the existing prototype branch.
- Re-read `task_plan.md` and `findings.md`; confirmed `progress.md` was missing and created it.
- Reproduced the current state on ARM from `HEAD` (`ed5f8d17`) using the standard remote helper inputs.
- Confirmed the core synthetic-state OSR path is not helper-only fragile:
  - direct `issue76_phase0_probe.py` can return `16`
  - repeated direct runs also show intermittent aborts / segfaults
- Collected a 15-run sample and observed a strong correlation:
  - `local 0 -> X19`, `local 1 -> X21` failed repeatedly
  - other mappings often succeeded
- Formed the current root-cause hypothesis:
  - the Phase 0 stub is still using an approximation of loop-header live-in locations
  - jumping directly to the loop header likely bypasses predecessor/phi materialization
- Added `scripts/arm/issue76_phase0_stability_probe.py` as a repeat-run regression probe so the instability has a concrete RED gate before the next implementation change.

## 2026-04-01

- Restored context and confirmed the latest local Phase 0 commits are:
  - `e8855339` prefer loop-entry bindings over deopt fallback
  - `bee598ce` resolve bindings from header phi outputs
  - `46f531f5` set test-entry frame bytecode position to the loop-header `bc_offset`
- Reconstructed the next verification plan:
  - rebuild/install on ARM through `remote_update_build_test.sh`
  - rerun the dedicated stability probe against the fresh wheel
- Hit an infrastructure blocker before fresh verification:
  - `124.70.162.35:22` timed out for both TCP connect and ICMP ping
  - even a minimal `ssh ... hostname` failed during banner exchange
- Decision:
  - stop short of further unverified runtime changes
  - preserve the current investigation state in planning files and resume once the ARM host is reachable again

- After the ARM host came back, continued Phase 0 debugging and landed four more test-entry-only fixes:
  - `aa94d04f` canonicalize Phase 0 bindings through `copy_propagation_map`
  - `9f5bab50` initialize the Phase 0 interpreter-frame register before writing the loop-header bytecode position
  - `1b5f31f3` seed AArch64 `X19/X20/X21` with `tstate` before overlaying local mappings
- Remote evidence collected in this round:
  - standard helper + `defaults_probe_exit` passed with:
    - `force_compile True`
    - `result 16`
    - `after_defaults None`
    - `after_kwdefaults None`
  - direct ARM stability probe:
    - `ISSUE76_PHASE0_STABILITY_RUNS=8`
    - `stability_failures=0`
  - standard helper gate:
    - `EXTRA_TEST_CMD='ISSUE76_PHASE0_STABILITY_RUNS=4 python -u scripts/arm/issue76_phase0_stability_probe.py'`
    - `HELPER_RC=0`
    - `stability_failures=0`
- Current working conclusion:
  - the Phase 0 synthetic-state OSR prototype is now stable enough to call the phase landed for the current test scope
  - remaining dirty files are the planning documents only

- Began Phase 1 planning after Phase 0 verification closed.
- Locked the MVP slice to:
  - `JUMP_BACKWARD_JIT` driven
  - same-activation once-call hot-loop entry
  - outermost / object-only / unsupported shapes return `false`
- Wrote `phase1_plan.md` in the same issue directory so execution can start without re-deriving file boundaries or remote commands.

- Started Phase 1 execution inline.
- Added the first RED assets:
  - `test_phase1_once_call_hot_loop_enters_jit_same_activation`
  - `scripts/arm/issue76_phase1_probe.py`
- Verified the initial RED on ARM:
  - helper built and installed the wheel
  - probe failed with `no osr stats`
- Added minimal `osr` runtime stats plumbing in `Context`/`pyjit.cpp`.
- Found and fixed two interpreter-side wiring gaps:
  - `jit.enable()/disable()` was not maintaining `PyInterpreterState.jit`
  - the OSR helper was initially handed the backedge instruction pointer instead of the loop-header target pointer
- After those fixes, the Phase 1 probe reached the intended semantic milestone:
  - `result=1250025000`
  - `osr_entries=[{'normal': {'func_qualname': 'hot', 'bc_offset': 2}, 'int': {'count': 1}}]`
- Current blocker:
  - the process still exits with `RC=139` on normal interpreter shutdown
  - `os._exit(0)` variants prove the same-activation OSR path itself works and does not corrupt `hot.__defaults__`
  - the remaining instability is tied to normal process teardown after same-activation hot-loop compile/OSR

- Continued Phase 1 debugging and found three more interpreter-side/root-cause issues:
  - `JUMP_BACKWARD_JIT` helper was originally using the backedge instruction pointer instead of the loop-header target pointer
  - the helper path had to be moved outside `_Py_TIER2` so it also runs on the current ARM build configuration
  - `ensureCompiledForHotLoopOSR()` needed proper registration via `trackEligibleCodeObjects()` so the standard helper smoke path still works
- Confirmed the real semantic milestone with fresh evidence:
  - direct ARM probe:
    - `result=1250025000`
    - `osr_entries=[{'normal': {'func_qualname': 'hot', 'bc_offset': 2}, 'int': {'count': 1}}]`
    - `REMOTE_RC=0`
  - standard remote helper:
    - `PHASE1_GREEN_RC=0`
    - `jit-effective-ok compiled_size 984 interp_calls 10`
    - `result=1250025000`
    - `osr_entries=[...]`
- Also verified the Python regression body now passes:
  - `ArmRuntimeTests.test_phase1_once_call_hot_loop_enters_jit_same_activation` reported `ok`
- Current state:
  - the main Phase 1 happy path is working end-to-end
  - remaining work is Phase 1 hardening, especially explicit unsupported-shape guard rails and narrower cleanup of the temporary implementation path

- Added a conservative Phase 1 unsupported-shape guard:
  - any code object with a non-empty `co_exceptiontable` now skips hot-loop OSR entirely
- Verified the unsupported-shape standalone probe on ARM through the standard helper:
  - `result=12502501`
  - `osr_count=0`
  - `compiled=False`
- Verified the main Phase 1 happy path again after the hardening work:
  - standard helper: `PHASE1_GREEN_RC=0`
  - direct probe: `REMOTE_RC=0`
  - state probe: `after_compiled True`, non-empty `after_entries`, non-empty `stats['osr']`
- Observed an additional follow-up issue:
  - when the new unittest cases are run through a tiny custom runner process, the test bodies report `ok`, but the runner process can still segfault on exit
  - this appears narrower than the main runtime path because the standalone probe and standard helper both exit cleanly
