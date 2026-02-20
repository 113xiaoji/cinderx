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

### Follow-up Validation: Lazy Helper-Stub Emission A/B (392245ed -> 7c361dce)

- Date: 2026-02-19
- Compared commits:
  - prev: `392245ed` (before lazy helper-stub emission)
  - cur: `7c361dce` (lazy helper-stub emission + tighter size guard)
- ARM host: `124.70.162.35` (`ecs-8416-c44a`)
- Pipeline:
  - `scripts/push_to_arm.ps1 -WorkBranch bench-prev-392245ed -SkipPyperformance`
  - `scripts/push_to_arm.ps1 -WorkBranch bench-cur-7c361dce -SkipPyperformance`
  - both runs passed ARM runtime tests (`Ran 4 tests ... OK`)

Artifacts:

- A/B raw summary:
  - `/root/work/arm-sync/ab_prev_392245ed_summary.json`
  - `/root/work/arm-sync/ab_cur_7c361dce_summary.json`
- A/B aggregate comparison:
  - `/root/work/arm-sync/ab_compare_392245ed_vs_7c361dce.json`

Repeated pyperformance (`richards`, debug-single-value, n=6 each):

- `jitlist` from -> to:
  - mean: `0.1015787320 s` -> `0.1015154074 s` (`-0.062%`)
  - median: `0.1013166280 s` -> `0.1017389011 s` (`+0.417%`)
  - 95% bootstrap CI of mean delta: `[-0.955%, +0.791%]`
- `autojit=50` from -> to:
  - mean: `0.1039325395 s` -> `0.1018160134 s` (`-2.036%`)
  - median: `0.1018768270 s` -> `0.1015132890 s` (`-0.357%`)
  - 95% bootstrap CI of mean delta: `[-5.716%, +0.682%]`

Interpretation:

- For `jitlist`, this iteration shows no statistically clear runtime change.
- For `autojit=50`, direction is positive but confidence interval still crosses
  zero, so it is not yet a stable claim.

Code-size check for the call-heavy regression shape:

- prev: `71616` bytes (`/root/work/arm-sync/compiled_size_prev_392245ed.txt`)
- cur: `71600` bytes (`/root/work/arm-sync/compiled_size_cur_7c361dce.txt`)
- delta: `-16` bytes (`-0.022%`)

JIT effectiveness cross-check on current commit (`7c361dce`):

- Artifact:
  - `/root/work/arm-sync/jit_effect_nojit_vs_jitlist_7c361dce_summary.json`
  - `/root/work/arm-sync/jit_effect_nojit_vs_jitlist_7c361dce_robust.json`
- `richards` nojit vs jitlist (n=5 each):
  - mean delta: `-4.961%` (jitlist faster)
  - median delta: `-0.391%`
  - robust trimmed-mean delta: `-0.715%`
  - exclude-first-run delta: `-0.430%`

Interpretation:

- JIT is active and can produce real speedup, but for `richards` at this stage
  the gain is modest and sensitive to run-to-run noise/outliers.

Theory (why this iteration has tiny runtime impact):

- `57c4350e` only changes AArch64 call lowering for `emitCall(..., instr ==
  nullptr)` paths (runtime scaffolding/cold paths), and keeps helper-stub
  dedup on hot instruction-backed callsites.
- Expected effect: remove unnecessary helper stubs for one-off targets,
  reducing generated code slightly.
- Observed effect matches theory: tiny but measurable code-size reduction
  (`71616 -> 71600`) and near-flat runtime on `richards`.

### Extended Benchmark Matrix (nojit vs jitlist, current commit 7c361dce)

- Date: 2026-02-19
- Artifact:
  - `/root/work/arm-sync/multi_bench_nojit_vs_jitlist_7c361dce_summary.json`
- Method:
  - `debug-single-value`
  - n=5 per benchmark/mode
  - modes: `PYTHONJITDISABLE=1` vs jitlist (`__main__:*`)

Results:

- `richards`:
  - mean delta: `-31.26%`
  - median delta: `-49.37%`
  - trimmed-mean delta: `-44.38%`
  - 95% CI: `[-51.57%, +4.01%]` (very wide)
- `nbody`:
  - mean delta: `+1.38%` (jitlist slower)
  - median delta: `-0.24%`
  - trimmed-mean delta: `+0.96%`
  - 95% CI: `[-0.73%, +3.63%]`
- `deltablue`:
  - mean delta: `-1.82%`
  - median delta: `-1.38%`
  - trimmed-mean delta: `-1.41%`
  - 95% CI: `[-4.21%, +0.48%]`

Interpretation:

- The first richards matrix contains strong outliers; it cannot be treated as a
  stable gain signal by itself.
- `nbody` and `deltablue` are closer to noise-level deltas on this sample size.

### Richards Interleaved A/B (noise-controlled)

- Date: 2026-02-19
- Artifact:
  - `/root/work/arm-sync/richards_interleaved_nojit_vs_jitlist_7c361dce_summary.json`
- Method:
  - 10 interleaved pairs (`nojit` then `jitlist` in each pair)
  - same host/session to reduce drift

Results:

- mean delta: `-0.165%`
- median delta: `-0.917%`
- trimmed-mean delta: `-0.592%`
- paired-delta mean: `-0.126%`
- paired-delta median: `-0.328%`
- 95% CI: `[-2.93%, +2.95%]`

Interpretation:

- Under interleaved sampling, current `richards` performance is effectively
  near parity (no statistically clear speedup/slowdown).
- Current branch is therefore best described as:
  - ARM JIT functional and effective
  - call-site code size improved
  - runtime speedup still requires hot-path optimization work.

### Richards Steady-State (in-process, warm benchmark loop)

- Date: 2026-02-19
- Method:
  - Directly run `bm_richards.Richards().run(1)` in one process
  - warmups: `5`
  - samples: `30`
- Artifacts:
  - `/root/work/arm-sync/richards_steady_nojit.txt`
  - `/root/work/arm-sync/richards_steady_autojit50.txt`
  - `/root/work/arm-sync/richards_steady_jitlist_force.txt`

From -> To:

- `nojit` mean: `0.4784831400 s`
- `autojit=50` mean: `0.2633556131 s`
  - delta: `-44.96%` (faster)
- `jitlist_force` mean: `0.3285057888 s`
  - delta vs `nojit`: `-31.34%` (faster)
  - delta vs `autojit=50`: `+19.83%` (slower)

Interpretation:

- In warm steady-state, ARM JIT provides real speedup on richards.
- `autojit=50` outperforms forced-jitlist in this setup, likely because forced
  compilation has higher compile overhead and/or suboptimal compile timing.

### Richards Hot Functions and HIR Shape

- Date: 2026-02-19
- Artifact:
  - `/tmp/inspect_richards_compiled_funcs.py` output
  - `/tmp/inspect_richards_hir_counts.py` output
- Top compiled functions by native size:
  - `HandlerTask.fn` (`3432`)
  - `WorkTask.fn` (`3080`)
  - `IdleTask.fn` (`2680`)
  - `Task.runTask` (`1872`)
  - `DeviceTask.fn` (`1688`)
- Aggregate top-10 HIR mix (high counts):
  - `Decref`/`XDecref`
  - `CondBranch`/`Branch`
  - `LoadAttrCached`/`StoreAttrCached`
  - `CallMethod` + `LoadMethodCached` + `GetSecondOutput`

Interpretation:

- richards hot paths are branchy, attribute-heavy, and refcount-heavy.
- Pure cold-path call-target pooling changes are unlikely to move this benchmark
  strongly; next gains should target hot call/method/refcount paths.

### Toggle Sensitivity (separate-process sanity check)

- Date: 2026-02-19
- Method:
  - separate interpreter process per case
  - `autojit=50`, warmups `5`, samples `25`
- Artifacts:
  - `/root/work/arm-sync/richards_case_baseline.txt`
  - `/root/work/arm-sync/richards_case_inliner_off.txt`
  - `/root/work/arm-sync/richards_case_spec_off.txt`
  - `/root/work/arm-sync/richards_case_type_guard_off.txt`

Means:

- baseline: `0.1307207331 s`
- inliner off: `0.1332647072 s` (`+1.95%`, slower)
- specialized opcodes off: `0.1316843338 s` (`+0.74%`, slower)
- type-annotation guards off: `0.1324508902 s` (`+1.32%`, slower)

Interpretation:

- Current default JIT feature set is already better than these obvious
  toggled-off variants for richards steady-state.

### pyperformance --fast (cold/short-run caution)

- Date: 2026-02-19
- Artifacts:
  - `/root/work/arm-sync/richards_fast_nojit_7c361dce.json`
  - `/root/work/arm-sync/richards_fast_jitlist_7c361dce.json`
  - `/root/work/arm-sync/richards_fast_autojit50_7c361dce.json`
  - `/root/work/arm-sync/richards_fast_compare_7c361dce.txt`
  - `/root/work/arm-sync/richards_fast_compare_nojit_vs_autojit50_7c361dce.txt`

Observed:

- nojit: `103 ms +- 3 ms`
- jitlist: `181 ms +- 36 ms` (reported `1.76x slower`)
- autojit50: `191 ms +- 5 ms` (reported `1.85x slower`)

Interpretation:

- On this host/setup, `pyperformance --fast` is dominated by short-run/cold
  behavior and repeated compile overhead for JIT modes.
- Do not treat this mode as steady-state throughput evidence for optimization
  decisions.

