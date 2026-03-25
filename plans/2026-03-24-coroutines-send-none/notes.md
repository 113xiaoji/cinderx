# Notes: coroutines send(None) builder rewrite

## User-provided target behavior

- Benchmark: `pyperformance coroutines`
- Current bad shape:
  - `LOAD_ATTR send`
  - `LOAD_CONST None`
  - `CALL 1`
  - `POP_TOP`
  - `StopIteration` handler
- Current lowering:
  - `LoadMethod("send")`
  - `GetSecondOutput`
  - `CallMethod`
- Desired lowering:
  - `LoadMethodCached<"send">`
  - `GetSecondOutput<OptObject>`
  - `Send`
  - `GetSecondOutput<CInt64>`
  - `CondBranch(done, outer_resume, inner_loop)`

## Constraints

- Match by bytecode shape, not by broad semantic guesswork.
- Only rewrite `send(None)`.
- Only rewrite when the call result is immediately discarded and control loops back.
- Any mismatch must fall back to the existing generic `CallMethod` path.

## Environment / process notes

- Skill-required scheduler helper script is absent from this repo.
- Standard remote closed-loop entrypoint available:
  - `scripts/arm/remote_update_build_test.sh`
- Need to append key verified results to repo-root `findings.md`.

## Local implementation notes

- First matcher attempt depended on `tc.frame.block_stack.top().handler_off`.
- That did not work on Python 3.14 zero-cost exception shape for this case.
- The working matcher now uses:
  - current `CALL 1`
  - previous `LOAD_CONST None`
  - previous `LOAD_ATTR send` with method bit set
  - next `POP_TOP`
  - next `JUMP_BACKWARD`
  - forward scan to `PUSH_EXC_INFO`
  - narrow match-path scan for:
    - `LOAD_GLOBAL StopIteration`
    - `CHECK_EXC_MATCH`
    - `POP_JUMP_IF_FALSE`
    - optional `NOT_TAKEN/NOP`
    - `POP_TOP`
    - `POP_EXCEPT`
    - `JUMP_BACKWARD`

## Verification summary

- Targeted ARM runtime regression:
  - `test_cinderx.test_arm_runtime.ArmRuntimeTests.test_coroutines_send_none_loop_lowers_to_send`
  - passes under remote driver venv
- Manual verification on the real benchmark function:
  - benchmark path:
    - `/root/venv-cinderx314/lib/python3.14/site-packages/pyperformance/data-files/benchmarks/bm_coroutines/run_benchmark.py`
  - compiled function:
    - `bm_coroutines_run_benchmark:bench_coroutines`
  - rewrite hit logged at bytecode offset `126`
- Unified remote entrypoint run:
  - build/install via `scripts/arm/remote_update_build_test.sh`
  - targeted runtime regression via `EXTRA_TEST_CMD`
  - benchmark smoke:
    - `coroutines_jitlist_20260324_191926.json`
    - `coroutines_autojit50_20260324_191926.json`
  - actual benchmark-function verify via `EXTRA_VERIFY_CMD`

## Follow-up benchmark validation

- Used the standard remote entrypoint again with:
  - `SKIP_BUILD=1`
  - `SKIP_ARM_RUNTIME_TESTS=1`
  - `SKIP_PYPERF=1`
  - `EXTRA_VERIFY_CMD` calling:
    - `scripts/arm/run_pyperf_selection.py`
    - `scripts/arm/compare_pyperf_json.py`

### coroutines steady-state

- Current-build `nojit` summary:
  - median: `0.02804468712565722s`
- Current-build `autojit50` summary:
  - median: `0.028144777875240834s`
- Delta:
  - `+0.3569%` (`autojit50` slightly slower, effectively flat)

### small regression screen

Benchmarks:

- `coroutines`
- `generators`
- `comprehensions`

Method:

- compare current-build `autojit50` against current-build `nojit`
- `--fast`
- regression threshold: `10%`

Results:

- `comprehensions`: `+0.2864%`
- `coroutines`: `-0.0292%`
- `generators`: `+0.0484%`
- regressions above threshold: `0`

## Added local regression anchor

- Added a 3.14 HIR fixture in:
  - `cinderx/RuntimeTests/hir_tests/all_passes_test.txt`
- Fixture goal:
  - assert the minimal `bench_coroutines` shape lowers to:
    - `Send`
    - `GetSecondOutput<CInt64>`
    - `CondBranch`
  - and not back to generic `CallMethod`
- Remote execution status:
  - the current remote build produced the library/wheel targets only
  - no `RuntimeTests`/HIR test binary target was present in the existing CMake build tree
  - so the fixture was added but not executed in this round
