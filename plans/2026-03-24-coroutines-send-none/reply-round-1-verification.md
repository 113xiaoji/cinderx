# Issue Reply Draft: #65 coroutines send(None) builder rewrite

Implemented the fix in `cinderx/Jit/hir/builder.cpp` / `builder.h` as a very narrow Python 3.14 bytecode-shape rewrite for the `coro.send(None)` loop. The rewrite now lowers the normal completion path to explicit compiled control flow instead of generic `CallMethod` + exception exit.

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

Additional follow-up validation:

- current-build steady-state `coroutines`
  - `nojit` median: `0.02804468712565722s`
  - `autojit50` median: `0.028144777875240834s`
  - delta: `+0.3569%` (effectively flat)
- small regression screen (`coroutines,generators,comprehensions`, `--fast`)
  - regressions above `10%`: `0`
  - `comprehensions`: `+0.2864%`
  - `coroutines`: `-0.0292%`
  - `generators`: `+0.0484%`

Bottom line: the old normal-completion `UnhandledException / CallMethod` path is gone, and the benchmark now stays in compiled control flow via `Send + GetSecondOutput<CInt64> + CondBranch`.
