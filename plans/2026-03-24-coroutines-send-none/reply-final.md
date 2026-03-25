# Final Issue Comment: #65 coroutines send(None) loop rewrite

Implemented the fix in `cinderx/Jit/hir/builder.cpp` / `builder.h` as a narrow Python 3.14 bytecode-shape rewrite for the `coro.send(None)` loop.

What changed:

- Match the benchmark shape before generic `CallMethod` lowering:
  - `LOAD_ATTR send`
  - `LOAD_CONST None`
  - `CALL 1`
  - `POP_TOP`
  - `JUMP_BACKWARD`
  - `StopIteration` handler returning to the outer loop
- Rewrite the normal completion path to compiled control flow:
  - `Send`
  - `GetSecondOutput<CInt64>`
  - `CondBranch`

Verified through the standard remote entrypoint `scripts/arm/remote_update_build_test.sh`:

- build/install: PASS
- targeted ARM runtime regression: PASS
  - `test_cinderx.test_arm_runtime.ArmRuntimeTests.test_coroutines_send_none_loop_lowers_to_send`
- real benchmark-function verify: PASS
  - benchmark file:
    - `/root/venv-cinderx314/lib/python3.14/site-packages/pyperformance/data-files/benchmarks/bm_coroutines/run_benchmark.py`
  - function:
    - `bm_coroutines_run_benchmark:bench_coroutines`
  - verify JSON:
    - `send_count = 1`
    - `callmethod_count = 0`
    - `callmethod_unhandled_deopt_count = 0`
    - `deopt_count = 0`
  - JIT log confirms:
    - `send-none rewrite hit in bm_coroutines_run_benchmark:bench_coroutines`
  - final HIR/log confirms:
    - `Send`
    - `GetSecondOutput<CInt64>`
    - `CondBranch`

Follow-up timing / regression validation:

- steady-state `coroutines` on the current build is effectively flat
  - current `nojit` median: `0.02804468712565722s`
  - current `autojit50` median: `0.028144777875240834s`
  - delta: `+0.3569%`
- small regression screen (`coroutines,generators,comprehensions`, `--fast`)
  - regressions above `10%`: `0`
  - `comprehensions`: `+0.2864%`
  - `coroutines`: `-0.0292%`
  - `generators`: `+0.0484%`

Additional guardrail:

- added a 3.14 HIR text fixture in `cinderx/RuntimeTests/hir_tests/all_passes_test.txt`
  to keep a cheap regression anchor for `Send + GetSecondOutput<CInt64> + CondBranch`
  (not executed in this round because the current remote build tree did not expose a `RuntimeTests`/HIR fixture binary target).

Bottom line:

- the old normal-completion `UnhandledException / CallMethod` path is gone
- the benchmark now stays in compiled control flow via `Send + GetSecondOutput<CInt64> + CondBranch`
- current measurements show this is a correctness/control-flow fix, not a clear steady-state speedup
