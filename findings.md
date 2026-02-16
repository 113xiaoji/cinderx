## ARM64 JIT Findings (CinderX)

This file tracks key performance/behavior results for the ARM64 (aarch64) JIT
bring-up and optimization work. All numbers below are produced via the remote
entrypoint:

`scripts/push_to_arm.ps1` -> `scripts/arm/remote_update_build_test.sh`

### Baseline (ARM JIT Functional + Gate Passing)

- Date: 2026-02-16
- Host: `ecs-8416-c44a` (aarch64)
- Python: CPython 3.14.3 (`/opt/python-3.14/bin/python3.14`)
- Branch/commit: `arm-jit-unified` @ `35d5103a`

pyperformance (debug-single-value):

- `richards` (jitlist): `0.1655383380 s`
  - JSON: `/root/work/arm-sync/richards_jitlist_20260216_085629.json`
- `richards` (autojit=50): `0.1595566060 s`
  - JSON: `/root/work/arm-sync/richards_autojit50_20260216_085629.json`

JIT activity proof:

- JIT log contains compilation of `__main__` functions for `richards`
  (e.g. `Finished compiling __main__:Task.runTask ...`).

### Iteration: AArch64 Immediate Call Lowering via Literal Pool

- Date: 2026-02-16
- Branch/commit: `arm-jit-perf` @ `49426fd5`
- Change: route AArch64 `translateCall()` immediate targets through
  `emitCall(env, func, instr)` so helper-call sites use deduplicated literal
  pool loads instead of repeated direct materialization.

Targeted size regression test:

- `cinderx/PythonLib/test_cinderx/test_arm_runtime.py::test_aarch64_call_sites_are_compact`
  - before: `84320` bytes (failing threshold `<= 84000`)
  - after: `77160` bytes (passing)

Verification via unified remote entrypoint:

- Command:
  `powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 -RepoPath d:\code\cinderx-upstream-20260213 -WorkBranch arm-jit-perf -ArmHost 124.70.162.35 -Benchmark richards`
- ARM runtime unittest: `Ran 4 tests ... OK`
- pyperformance artifacts:
  - jitlist: `/root/work/arm-sync/richards_jitlist_20260216_141450.json`
    - value: `0.2937913140 s` (single sample)
  - autojit=50: `/root/work/arm-sync/richards_autojit50_20260216_141450.json`
    - value: `0.2545295180 s` (single sample)
- JIT effectiveness during benchmark workers:
  - log: `/tmp/jit_richards_autojit_20260216_141450.log`
  - `Finished compiling __main__:` occurrences: `18`

