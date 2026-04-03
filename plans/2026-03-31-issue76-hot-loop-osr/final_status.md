# Issue 76 Final Status

## Scope

This note records the current implementation status for issue `#76` after the
Phase 1 bring-up work and the follow-up correctness debugging.

The issue asked for a structured design around hot-loop OSR on CinderX 3.14,
including:

- current-state analysis
- problem definition
- industry comparison
- candidate options
- recommended design
- module-level implementation plan
- validation and risk discussion

Those design requirements are covered by the existing files in this directory:

- [deliverable.md](./deliverable.md)
- [phase0_plan.md](./phase0_plan.md)
- [phase1_plan.md](./phase1_plan.md)
- [findings.md](./findings.md)
- [progress.md](./progress.md)

This file adds the final implementation summary and a check against the
original design goals.

## What Landed

The implemented work is the Phase 1 MVP path for Scheme B:

- whole-function compilation remains the unit of compilation
- hot-loop entry is through a secondary loop-header entry, not a tracing JIT
- same-activation interpreter-to-JIT transfer is supported for a narrow class of
  loops
- downward deopt continues to use the existing deopt machinery

The key code paths are:

- [generated_cases.c.h](C:/work/code/cinderx1/cinderx/cinderx/Interpreter/3.14/Includes/generated_cases.c.h)
  - same-activation hot-loop OSR return path now closes `localsplus` ownership
    correctly before returning through the interpreter
- [pyjit.cpp](C:/work/code/cinderx1/cinderx/cinderx/Jit/pyjit.cpp)
  - `run_osr_test_entry()` and hot-loop OSR now hand object ownership to the
    compiled entry correctly
- [gen_asm.cpp](C:/work/code/cinderx1/cinderx/cinderx/Jit/codegen/gen_asm.cpp)
  - Phase 0/1 OSR local mappings are now derived from the actual entry LIR
    live-reg inputs, not guessed from a nearby deopt point
- [test_arm_runtime.py](C:/work/code/cinderx1/cinderx/cinderx/PythonLib/test_cinderx/test_arm_runtime.py)
  - regression coverage now includes the synthetic OSR refcount case and the
    Phase 1 same-activation loop case
- [remote_update_build_test.sh](C:/work/code/cinderx1/cinderx/scripts/arm/remote_update_build_test.sh)
  - the ad-hoc filtered runner keeps the parent interpreted so unrelated
    parent-process auto-JIT does not hide the real runtime result

## Why This Is General, Not Case-Specific

The final fix is not a `fannkuch`-only special case.

The central bug was structural:

- the fallback Phase 0 local mapping path used a nearby deopt snapshot
- that snapshot could describe an older predecessor state
- loop-header entry then restored locals into the wrong physical locations

The fix is structural too:

- local mappings are extracted from the real deopt-capable instruction at the
  actual OSR entry block
- the mapping is derived by matching HIR live regs to the entry LIR inputs
- the resulting OSR entry uses the same live-in convention the compiled block
  itself expects

That applies to any loop shape that satisfies the current MVP restrictions. It
does not depend on benchmark names or handwritten case logic.

The ownership fix is also general:

- OSR entry values are borrowed from the interpreter frame or synthetic payload
- compiled code consumes owned references
- both the test-entry path and the same-activation path now transfer ownership
  consistently

Again, this is a generic runtime contract fix, not a benchmark-specific tweak.

## Original Design Check

The original recommended direction was:

- do not introduce a tracing JIT
- reuse whole-function compilation
- add loop-header secondary entry support
- support "function executes once, loop gets hot in the same activation"
- keep Phase 1 narrow and object-focused

Current status against that design:

- current-state analysis: done
- problem definition: done
- industry comparison: done
- candidate-option comparison: done
- recommended design: done
- Phase 0 synthetic entry prototype: done
- Phase 1 same-activation MVP: done
- real same-activation loop entry on ARM: done
- downward deopt compatibility for the MVP path: done
- object-only outermost-loop narrowness: done
- tracing JIT alternative: intentionally not implemented

## What Is Still Out Of Scope

The following are still Phase 2 or later work:

- generators, coroutines, async generators
- inlined-frame OSR entry
- active exception-region OSR
- generalized primitive live-in reconstruction
- richer operand-stack reconstruction beyond the current supported shapes
- broader benchmark-harness stabilization so end-to-end pyperformance can be
  used as the primary comparison signal

## Validation Summary

Fresh ARM evidence collected for this branch:

- filtered ARM runtime runner:
  - `Ran 86 tests in 60.736s`
  - `OK`
- standard ARM helper:
  - passes end-to-end with `SKIP_PYPERF=1`
- same-activation `v5` probe:
  - `10/10` successful exits
- synthetic OSR probe:
  - `10/10` successful exits

Benchmark status is improved but not fully finished:

- truthful current JIT workers can now run the requested benchmark set
- truthful baseline workers at `187e483f` still crash
- this means current benchmark work is useful validation tooling, but not yet a
  clean before/after performance comparison harness

## Recommendation

The core OSR/runtime fix is ready to submit now.

The benchmark worker harness changes are useful and should stay on the branch,
but they are better treated as follow-up tooling work than as the definition of
issue `#76` being "done".
