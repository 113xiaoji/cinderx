## Summary

- finalize the Phase 1 hot-loop OSR MVP for issue #76 on CinderX 3.14
- fix same-activation OSR ownership and loop-entry local mapping so loop-header secondary entry uses the real live-in locations the compiled block expects
- document final status, current scope limits, and benchmark-harness follow-up work

## What Changed

### Core OSR/runtime fix

- [generated_cases.c.h](C:/work/code/cinderx1/cinderx/cinderx/Interpreter/3.14/Includes/generated_cases.c.h)
  - close interpreter-frame `localsplus` references correctly after same-activation OSR returns through the interpreter
- [pyjit.cpp](C:/work/code/cinderx1/cinderx/cinderx/Jit/pyjit.cpp)
  - make synthetic OSR entry and same-activation OSR transfer object ownership consistently to compiled code
- [gen_asm.cpp](C:/work/code/cinderx1/cinderx/cinderx/Jit/codegen/gen_asm.cpp)
  - derive Phase 0/1 OSR local mappings from the real entry LIR live-ins instead of guessing from a nearby deopt point
- [test_arm_runtime.py](C:/work/code/cinderx1/cinderx/cinderx/PythonLib/test_cinderx/test_arm_runtime.py)
  - add/refine ARM runtime regressions for:
    - Phase 0 synthetic OSR refcount preservation
    - Phase 1 same-activation hot-loop OSR entry
    - current branch expectations for the retained runtime heuristics

### Helper / tooling

- [remote_update_build_test.sh](C:/work/code/cinderx1/cinderx/scripts/arm/remote_update_build_test.sh)
  - keep the filtered ARM unittest parent process interpreted to avoid unrelated parent-process auto-JIT exit crashes
- [sitecustomize.py](C:/work/code/cinderx1/cinderx/scripts/arm/pyperf_env_hook/sitecustomize.py)
  - narrow ARM pyperformance worker JIT activation
  - prefer raw `cinderjit` in workers
  - support jitlist-only worker mode
- [run_pyperf_subset.sh](C:/work/code/cinderx1/cinderx/scripts/arm/run_pyperf_subset.sh)
  - align the subset runner with the worker-only JIT environment contract

### Design / status docs

- [final_status.md](C:/work/code/cinderx1/cinderx/plans/2026-03-31-issue76-hot-loop-osr/final_status.md)
  - records what issue #76 asked for, what landed, what remains out of scope, and why the final fix is structural rather than benchmark-specific

## Original Design Check

The original design for issue #76 recommended:

- do not introduce a tracing JIT
- keep whole-function compilation as the unit of compilation
- add loop-header secondary entry support
- support "function runs once, loop gets hot in the same activation"
- keep the MVP narrow and object-focused

That is what this change implements.

The final landed behavior is still the recommended Scheme B:

- whole-function compile
- loop-header secondary entry
- same-activation interpreter-to-JIT transfer
- reuse of the existing downward deopt path

This does **not** introduce tracing, side traces, or benchmark-specific special cases.

## Why This Is General

The key bug fixed here was structural:

- the previous fallback local mapping path could describe the wrong predecessor state
- OSR entry then restored locals into physical locations that did not match the actual compiled entry block live-ins

The fix is also structural:

- local mappings are extracted from the actual entry LIR live-reg inputs
- ownership transfer is fixed at the runtime contract level for OSR entry values

So this is not a `fannkuch`-only or `v5`-only optimization. Those shapes were just the clearest reproducers.

## Validation

Fresh ARM verification used during this branch:

- filtered ARM runtime runner:
  - `Ran 86 tests in 60.736s`
  - `OK`
- standard ARM helper:
  - end-to-end passes with `SKIP_PYPERF=1`
- focused probes:
  - synthetic OSR probe `10/10` successful exits
  - same-activation `v5` probe `10/10` successful exits

## Remaining Gaps

This PR intentionally does **not** claim to complete Phase 2+ work. Still out of scope:

- generators / coroutines / async generators
- active exception-region OSR
- generalized primitive live-in support
- inlined-frame OSR
- fully stable before/after pyperformance harness for every benchmark configuration

## Benchmark Note

Current-side truthful JIT workers now run the requested benchmark set, but the
old baseline branch still crashes under the same truthful worker setup. So the
benchmark-harness changes in this branch are useful follow-up tooling, not the
definition of issue #76 being finished.

Refs #76
