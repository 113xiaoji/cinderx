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

### Follow-up: Multi-sample A/B Check (Same ARM Host)

- Date: 2026-02-16
- Compared commits:
  - prev: `a6fc9b54` (runtime-helper literal-pool expansion)
  - cur: `eaa7ba3b` (helper-stub call targets)

Method:

- Re-deploy each commit via unified remote flow.
- Collect 5 successful `richards` jitlist single-value samples each.
- For autojit (`PYTHONJITAUTO=50`), record success/failure across 15 attempts.

jitlist samples:

- prev values:
  - `0.3524485870`, `0.2699251230`, `0.3607075310`, `0.3716714900`,
    `0.2455384730`
- cur values:
  - `0.3618649420`, `0.1772761080`, `0.1805733180`, `0.1779869640`,
    `0.1852192320`

jitlist aggregate from -> to:

- mean: `0.3200582408 s` -> `0.2165841128 s` (`-32.33%`)
- median: `0.3524485870 s` -> `0.1805733180 s` (`-48.77%`)

autojit stability (15 attempts each):

- prev (`a6fc9b54`): `0/15` successful (all benchmark-worker crashes)
- cur (`eaa7ba3b`): `0/15` successful (all benchmark-worker crashes)

Interpretation:

- There is a strong directional speedup signal on jitlist multi-samples.
- Auto-jit benchmark-worker stability remains a separate blocker and must be
  fixed before treating autojit performance numbers as reliable.

### Iteration: Lazy Helper Stubs for Runtime-Only AArch64 Call Targets

- Date: 2026-02-19
- Branch/commits:
  - code change: `57c4350e` (`AArch64: lazily emit helper stubs for runtime-only call targets`)
  - test guard update: `7c361dce` (`tests: tighten aarch64 call-site compactness guard`)
- Change:
  - AArch64 `emitCall(env, func, instr)` now emits direct literal-based indirect
    calls for `instr == nullptr` scaffolding calls (no per-target helper stub).
  - Helper stubs are now created lazily only for targets that are emitted via
    normal instruction-originated callsites.
  - Files: `environ.h`, `gen_asm_utils.cpp`, `gen_asm.cpp`.

TDD red -> green evidence:

- RED (before code change): tightened guard to `<= 71500` and observed failure:
  - measured size: `71616`
  - assertion: `71616 > 71500`
- GREEN (after code change): compiled size dropped to `71600`, then guard set to
  `<= 71600` and ARM runtime tests passed in unified gate.

From -> To (against pre-change baseline on same branch flow):

- `test_aarch64_call_sites_are_compact` compiled size:
  - `71616` -> `71600` bytes (`-16`, `-0.02%`)

- pyperformance `richards` jitlist (single-sample, unified pipeline):
  - `0.1720421510 s` -> `0.2568877210 s` (`+49.32%`, worse)
  - baseline JSON: `/root/work/arm-sync/richards_jitlist_20260219_163732.json`
  - current JSON: `/root/work/arm-sync/richards_jitlist_20260219_175234.json`

- pyperformance `richards` autojit=50 (single-sample, unified pipeline):
  - `0.1799317821 s` -> `0.1754568410 s` (`-2.49%`, better)
  - baseline JSON: `/root/work/arm-sync/richards_autojit50_20260219_163732.json`
  - current JSON: `/root/work/arm-sync/richards_autojit50_20260219_175234.json`

JIT effectiveness proof:

- Log: `/tmp/jit_richards_autojit_20260219_175234.log`
- `Finished compiling __main__:` occurrences: `18`

Additional spot samples (same host, manual pyperformance invocations):

- jitlist: `/root/work/arm-sync/richards_jitlist_manual_.json` = `0.2018173400 s`
- jitlist: `/root/work/arm-sync/richards_jitlist_manual_b1.json` = `0.2040209400 s`
- autojit=50: `/root/work/arm-sync/richards_autojit50_manual_b1.json` =
  `0.2093519480 s`

Assessment:

- Code size has a small but real improvement (`71616 -> 71600`).
- Runtime impact is not a clear real speedup signal yet: jitlist regressed in
  the official single-sample gate while autojit improved slightly; additional
  spot samples also show high variance.
- Next step for a reliable performance claim is controlled multi-sample A/B on
  this exact commit pair with identical harness conditions.

