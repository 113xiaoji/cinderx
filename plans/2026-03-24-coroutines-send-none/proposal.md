# Proposal: coroutines send(None) builder rewrite

## Problem

On Python 3.14, `run.bench_coroutines` drives coroutines via `coro.send(None)` in a loop. The normal completion path still leaves compiled code through `StopIteration`, surfacing as `UnhandledException / CallMethod` instead of explicit compiled control flow.

## Hypothesis

The bytecode sequence for this benchmark is narrow enough that the builder can recognize it before generic `CallMethod` lowering and emit the same `Send`-based control flow used for real `SEND` bytecode.

## Planned implementation

- Add a narrow matcher in `builder.cpp` for:
  - method name `send`
  - one positional argument
  - argument value `None`
  - immediate `POP_TOP`
  - loop/backedge and handler shape consistent with the benchmark
- Add a helper in `builder.h`
- Invoke the helper before generic `CallMethod` lowering in `emitAnyCall()`

## Success criteria

- build/install passes
- benchmark smoke succeeds
- runtime stats API works
- patched HIR shows `Send + GetSecondOutput<CInt64> + CondBranch`
- patched runtime stats no longer show `UnhandledException / CallMethod`
