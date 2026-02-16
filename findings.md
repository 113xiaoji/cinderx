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

### Iteration: Expand Literal-Pool Emission to Runtime Helper Calls

- Date: 2026-02-16
- Branch/commit: `arm-jit-perf` @ `a6fc9b54`
- Change:
  - route additional AArch64 runtime-helper call sites in
    `gen_asm.cpp` and `frame_asm.cpp` through `emitCall(env, func, nullptr)`
  - update debug-site recorder to tolerate `instr == nullptr`
    (`gen_asm_utils.cpp`)

Functional verification:

- Remote gate (`scripts/push_to_arm.ps1`, `richards`, full pipeline): pass
- ARM runtime unittest: `Ran 4 tests ... OK`
- `test_aarch64_call_sites_are_compact` spot-check:
  - compiled size remains `77160` bytes (still passing threshold)

pyperformance artifacts (single-sample, debug-single-value):

- jitlist: `/root/work/arm-sync/richards_jitlist_20260216_161952.json`
  - value: `0.1785639740 s`
- autojit=50: `/root/work/arm-sync/richards_autojit50_20260216_161952.json`
  - value: `0.1715511510 s`

JIT effectiveness during benchmark workers:

- log: `/tmp/jit_richards_autojit_20260216_161952.log`
- `Finished compiling __main__:` occurrences: `18`

### Iteration: Helper-Stub Call Targets (BL to Shared Stub)

- Date: 2026-02-16
- Branch/commit: `arm-jit-perf` @ `eaa7ba3b`
- Change:
  - upgrade AArch64 call-target dedup from `ldr literal + blr` at each
    callsite to `bl helper_stub` at each callsite, with shared helper stub +
    shared literal per target
  - files: `environ.h`, `gen_asm_utils.cpp`, `gen_asm.cpp`

From -> To (against previous iteration `a6fc9b54`):

- Call-heavy compiled size guard (`test_aarch64_call_sites_are_compact` shape):
  - `77160` -> `71616` bytes (`-7.19%`)
- pyperformance `richards` jitlist (single-sample):
  - `0.1785639740 s` -> `0.1692628450 s` (`-5.21%`, lower is better)
- pyperformance `richards` autojit=50 (single-sample):
  - `0.1715511510 s` -> `0.1619962710 s` (`-5.57%`, lower is better)

Current artifact paths:

- jitlist: `/root/work/arm-sync/richards_jitlist_20260216_190942.json`
- autojit=50: `/root/work/arm-sync/richards_autojit50_20260216_190942.json`
- JIT log: `/tmp/jit_richards_autojit_20260216_190942.log`
  - `Finished compiling __main__:` occurrences: `18`

Assessment:

- This iteration shows an actual positive delta in both code size and runtime
  in the same remote pipeline.
- Runtime values are still `debug-single-value` single-sample; treat as
  directional gain and validate with multi-run aggregates before claiming final
  speedup.

