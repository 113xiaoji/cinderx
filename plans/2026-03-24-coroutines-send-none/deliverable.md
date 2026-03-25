# Deliverable: coroutines send(None) builder rewrite

## What changed

- Added a narrow builder-layer rewrite in:
  - `cinderx/Jit/hir/builder.cpp`
  - `cinderx/Jit/hir/builder.h`
- Added a 3.14 HIR fixture in:
  - `cinderx/RuntimeTests/hir_tests/all_passes_test.txt`
- The rewrite triggers only on the Python 3.14 `coro.send(None)` loop shape:
  - `LOAD_ATTR send`
  - `LOAD_CONST None`
  - `CALL 1`
  - `POP_TOP`
  - `JUMP_BACKWARD`
  - `StopIteration` handler that returns to the outer loop
- Added ARM runtime regression coverage in:
  - `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Added a remote verification helper:
  - `scripts/arm/verify_coroutines_send_none.py`

## Verified behavior

- Targeted regression now reports:
  - `Send >= 1`
  - `CallMethod = 0`
  - `UnhandledException / CallMethod` deopt count = `0`
- Manual verification on the real benchmark function reports:
  - `benchmark_path = /root/venv-cinderx314/lib/python3.14/site-packages/pyperformance/data-files/benchmarks/bm_coroutines/run_benchmark.py`
  - `send_count = 1`
  - `callmethod_count = 0`
  - `callmethod_unhandled_deopt_count = 0`
  - `deopt_count = 0`
- HIR/log evidence for `bm_coroutines_run_benchmark:bench_coroutines` shows:
  - rewrite hit
  - `Send`
  - `GetSecondOutput<CInt64>`
  - `CondBranch`

## Unified remote entrypoint result

- Entrypoint:
  - `scripts/arm/remote_update_build_test.sh`
- Outcome:
  - build/install succeeded
  - targeted ARM runtime regression succeeded
  - pyperformance `coroutines` smoke succeeded in both jitlist and autojit modes

Smoke artifacts:

- `coroutines_jitlist_20260324_191926.json`
  - value: `0.06542330799857154`
- `coroutines_autojit50_20260324_191926.json`
  - value: `0.06333435199485393`
- `coroutines_autojit50_20260324_191926_compile_summary.json`
  - `main_compile_count = 1`
  - `total_compile_count = 112`

## Bottom line

The normal `coro.send(None)` completion path is now represented in compiled control flow instead of surfacing as `UnhandledException / CallMethod` for the benchmark shape.

## Follow-up timing / regression results

- Steady-state `coroutines` on the current build is effectively flat:
  - current `nojit` median: `0.02804468712565722s`
  - current `autojit50` median: `0.028144777875240834s`
  - delta: `+0.3569%`
- Small regression screen (`coroutines,generators,comprehensions`, `--fast`) found:
  - regressions above `10%`: `0`
  - `comprehensions`: `+0.2864%`
  - `coroutines`: `-0.0292%`
  - `generators`: `+0.0484%`

## Interpretation

- The builder rewrite definitively fixes the control-flow modeling bug.
- It removes the old `UnhandledException / CallMethod` behavior on the benchmark function.
- On current measurements, the fix is correctness/control-flow-oriented rather than a clear steady-state speedup.
- A cheaper local regression anchor now exists in the HIR text fixtures, although the current remote build configuration did not expose a `RuntimeTests` binary to execute that fixture in this round.
