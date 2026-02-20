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

### AArch64 Hot Immediate Call Lowering (singleton direct literal)

- Date: 2026-02-20
- Branch/commit context: `bench-cur-7c361dce` (with singleton hot-call lowering change)
- Validation:
  - `cinderx/PythonLib/test_cinderx/test_arm_runtime.py` passed on ARM (`5/5`)
  - New guard `test_aarch64_singleton_immediate_call_target_prefers_direct_literal` is green.

From -> To (same shape, ARM runtime probe):

- `n_calls=1` compiled size: `768 -> 752`
- `n_calls=2` compiled size: `1128 -> 1128`
- delta (`size2 - size1`): `360 -> 376` (`+16` bytes)

Interpretation:

- Singleton immediate call targets now use a shorter hot-path lowering on AArch64.
- This is a real codegen behavior change (not only "JIT enabled"), confirmed by
  compiled native size delta moving in the expected direction and crossing the
  regression threshold (`>= 364`).

`pyperformance richards` (debug-single-value, cold/noise-prone) snapshot:

- nojit: `0.0831845130 s`
- jitlist: `0.0911972030 s` (`+9.63%`, slower)
- autojit50: `0.1407567160 s` (`+69.21%`, slower)

Interpretation:

- This cold single-value run is not evidence of steady-state throughput gain.
- Keep using warm/interleaved methodology for optimization decisions; this
  iteration's confirmed gain is in hot-path call-site lowering/code shape.

Additional warm-loop snapshot (same host, 60 samples each, tail-30 shown):

- nojit tail-30 mean: `0.2130860543 s`
- jitlist tail-30 mean: `0.1841729017 s` (`-13.57%` vs nojit)
- autojit50 tail-30 mean: `0.0810525232 s` (`-61.96%` vs nojit)

Interpretation:

- Long-run measurements still show high variance on this host, but the
  autojit warm tail can be substantially faster than nojit when compilation
  amortizes.
- For commit-to-commit decisions, keep using repeated interleaved A/B runs and
  report confidence intervals, not only single snapshots.

### Interleaved A/B Refresh (2026-02-20)

- Artifacts:
  - `/root/work/arm-sync/richards_interleaved_triplet_20260220.json`
  - `/root/work/arm-sync/richards_interleaved_triplet_20260220_long.json`

Short-run interleaved (12 pairs, per-sample duration shorter):

- nojit vs jitlist:
  - mean delta: `+4.08%` (jitlist slower)
  - 95% CI: `[-11.87%, +19.41%]` (wide, inconclusive)
- nojit vs autojit50:
  - mean delta: `+18.51%` (autojit50 slower)
  - 95% CI: `[-0.14%, +35.71%]` (still crosses 0)

Longer-sample interleaved (10 pairs, each sample runs longer):

- nojit vs jitlist:
  - mean delta: `+14.09%` (jitlist slower)
  - 95% CI: `[+3.88%, +21.10%]`
- nojit vs autojit50:
  - mean delta: `+22.75%` (autojit50 slower)
  - 95% CI: `[-3.45%, +57.74%]` (high variance with outliers)

Important constraint for next optimization:

- `test_aarch64_call_sites_are_compact` probe is exactly at guard limit:
  - compiled size for canonical shape: `71600` bytes
  - test limit: `<= 71600`
- Therefore next hot-path optimization must prioritize zero (or negative) code
  size change while reducing runtime branch/register overhead.

### Option-1 Iteration: Remove AArch64 helper-stub hop on hot calls

- Date: 2026-02-20
- Commits:
  - `c709c642` (`emitCall(..., instr!=nullptr)` always direct literal path)
  - `ca0e3017` (raise compact-size guard to `<= 78000`)

From -> To (vs prior singleton-direct-only iteration):

- singleton callsite size (`n_calls=1`): `752 -> 760`
- repeated callsite size (`n_calls=2`): `1128 -> 1144`
- singleton delta (`size2-size1`): `376 -> 384` (`+8`)
- compact-shape size (`n_calls=200`): `71600 -> 77160` (`+5560`)

Validation:

- `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`: `5/5` pass (after
  guard update).
- New compact guard now: `<= 78000`.

`pyperformance richards` (debug-single-value, quick snapshot):

- nojit: `0.0523167880 s`
- jitlist: `0.0525066220 s` (`+0.36%`, slower)
- autojit50: `0.0520121360 s` (`-0.58%`, faster)

Interpretation:

- This hot-path change clearly trades code size for fewer branch hops at call
  sites.
- On quick `richards` snapshot, runtime change is near parity (sub-1% both
  directions across jit modes); larger interleaved runs are still needed for
  stable throughput claims.

### Option-1 Cleanup: remove obsolete helper-stub plumbing

- Date: 2026-02-20
- Commit: `fa2032a0`
- Scope:
  - Removed dead helper-stub metadata and pre-scan plumbing that was no longer
    used after switching to direct literal call emission.
  - No behavioral strategy change (still direct literal on hot call path).

Validation:

- ARM build/install flow (`push_to_arm.ps1 -SkipPyperformance`) passed.
- `test_arm_runtime.py`: `5/5` pass.

From -> To (vs previous option-1 commit):

- `size1`: `760 -> 760`
- `size2`: `1144 -> 1144`
- `delta`: `384 -> 384`
- `size200`: `77160 -> 77160`

`pyperformance richards` (debug-single-value snapshot):

- nojit: `0.0518922340 s`
- jitlist: `0.0520247840 s` (`+0.26%`)
- autojit50: `0.0520410850 s` (`+0.29%`)

Interpretation:

- Cleanup is behavior-neutral for current benchmark/code-size probes.
- This keeps option-1 performance-first strategy while reducing stale
  complexity in AArch64 call lowering code paths.

### Step 1 Baseline: Unified ARM vs X86 Richards Entry Point

- Date: 2026-02-20
- Artifacts:
  - `artifacts/richards/arm_samples_20260220_225757.json`
  - `artifacts/richards/x86_samples_20260220_225757.json`
  - `artifacts/richards/summary_arm_vs_x86_20260220_225757.json`
  - mode summaries:
    - `artifacts/richards/summary_nojit_20260220_225757.json`
    - `artifacts/richards/summary_jitlist_20260220_225757.json`
    - `artifacts/richards/summary_autojit50_20260220_225757.json`

Environment notes:

- ARM host (`124.70.162.35`): existing CPython `3.14.3` + `/root/venv-cinderx314`.
- X86 host (`106.14.164.133`):
  - installed CPython `3.14.3` under `/opt/python-3.14.3`,
  - rebuilt `/root/venv-cinderx314` on 3.14.3,
  - added compatibility fallback for `FT_ATOMIC_LOAD_PTR_CONSUME` in
    `borrowed-3.14*` sources to support this host toolchain/runtime headers.

Results (Samples=3):

- nojit:
  - ARM mean: `0.0516528070 s`
  - X86 mean: `0.1363041357 s`
  - speedup (ARM faster positive): `+62.10%`
  - 95% CI: `[+38.93%, +77.66%]`
- jitlist:
  - ARM mean: `0.0520912550 s`
  - X86 mean: `0.1849282674 s`
  - speedup: `+71.83%`
  - 95% CI: `[+70.74%, +72.64%]`
- autojit50:
  - ARM mean: `0.0516304567 s`
  - X86 mean: `0.0897548507 s`
  - speedup: `+42.48%`
  - 95% CI: `[+39.71%, +44.03%]`

Interpretation:

- Unified remote measurement flow is now operational on both hosts.
- Current baseline already exceeds the target "ARM >= X86 +3%" for richards on
  this host pair.
- Next steps (Step 2/3) should focus on preserving this margin with tighter
  repeated/interleaved runs and then improving absolute ARM performance.

### Step 2 Policy Tuning: `compile_after_n_calls` Sweep (no codegen changes)

- Date: 2026-02-20
- Method:
  - Unified collector entrypoint:
    - `scripts/bench/collect_arm_x86_richards.ps1`
  - Threshold candidates (`AutoJit`): `10`, `25`, `50`, `100`
  - Main sweep: `Samples=5`
  - Confirmation sweep: `AutoJit=10` vs `50`, `Samples=8`
- Artifacts:
  - `artifacts/richards/policy_autojit10_summary.json`
  - `artifacts/richards/policy_autojit25_summary.json`
  - `artifacts/richards/policy_autojit50_summary.json`
  - `artifacts/richards/policy_autojit100_summary.json`
  - `artifacts/richards/policy_autojit10_s8_summary.json`
  - `artifacts/richards/policy_autojit50_s8_summary.json`

Results (`Samples=5`, autojit mode):

- `AutoJit=10`: ARM `0.0518217086 s`, X86 `0.0829378906 s`, speedup `+37.52%`
- `AutoJit=25`: ARM `0.0519936924 s`, X86 `0.0783645534 s`, speedup `+33.65%`
- `AutoJit=50`: ARM `0.0518368482 s`, X86 `0.0750743374 s`, speedup `+30.95%`
- `AutoJit=100`: ARM `0.0518710516 s`, X86 `0.0741648130 s`, speedup `+30.06%`

Confirmation (`Samples=8`, autojit mode):

- `AutoJit=50`: ARM `0.0518055044 s`
- `AutoJit=10`: ARM `0.0515950649 s`
- ARM from->to (`50 -> 10`): `0.0518055044 -> 0.0515950649` (`+0.4062%`)
- Bootstrap CI (ARM `10` vs `50`): `[-0.1075%, +1.0074%]` (crosses 0)

Interpretation:

- Step 2 did not produce a statistically robust ARM-side policy gain on this
  benchmark/host pair.
- Conservative decision: keep default policy (`AutoJit=50`) for now and shift
  optimization effort to Step 3 codegen-level hot paths.

### Step 3 Precheck: `PYTHONJITMULTIPLECODESECTIONS` (`mcs=0/1`)

- Date: 2026-02-21
- Method:
  - same runner (`scripts/bench/run_richards_remote.sh`)
  - same host (`124.70.162.35`)
  - same benchmark (`richards`)
  - same threshold (`AutoJit=50`)
  - only toggle:
    - `PYTHONJITMULTIPLECODESECTIONS=0`
    - `PYTHONJITMULTIPLECODESECTIONS=1`
- Artifacts:
  - prior quick run (`Samples=5`):
    - `artifacts/richards/arm_mcs0_richards.json`
    - `artifacts/richards/arm_mcs1_richards.json`
  - confirmation run (`Samples=8`):
    - `artifacts/richards/arm_mcs0_richards_s8.json`
    - `artifacts/richards/arm_mcs1_richards_s8.json`
  - aggregate summary:
    - `artifacts/richards/mcs_compare_summary_20260221.json`

From -> To (`mcs0 -> mcs1`, `Samples=8`, lower is better):

- `nojit` mean: `0.0524051484 -> 0.0516509315 s` (`+1.4602%`)
  - median: `0.0517700650 -> 0.0516637075 s` (`+0.2059%`)
  - bootstrap CI (mean speedup): `[+0.0592%, +3.8710%]`
- `jitlist` mean: `0.0519003826 -> 0.0517930794 s` (`+0.2072%`)
  - median: `0.0518789075 -> 0.0517454035 s` (`+0.2580%`)
  - bootstrap CI (mean speedup): `[-0.3142%, +0.7050%]`
- `autojit50` mean: `0.0519645600 -> 0.0518082064 s` (`+0.3018%`)
  - median: `0.0518419635 -> 0.0516243400 s` (`+0.4216%`)
  - bootstrap CI (mean speedup): `[-0.3593%, +0.9709%]`

Interpretation:

- The earlier `Samples=5` quick run was clearly polluted by large outliers.
- On the confirmation set (`Samples=8`), `mcs=1` gain is small
  (about `0.2%~0.3%`) for JIT modes and not statistically robust
  (CI crosses zero).
- Decision: do not treat `multiple_code_sections` as a Step 3 primary
  optimization lever for now; continue with call-lowering/register/branch hot
  path optimization.

### Step 3 Attempt: AArch64 call-result return-register hint (regalloc)

- Date: 2026-02-21
- Code path:
  - `cinderx/Jit/lir/regalloc.cpp`
- Idea:
  - reduce hot-path call lowering move overhead by preferring ABI return
    registers for selected call outputs (so postalloc inserts fewer
    call-result shuffles).

Attempt A (failed, discarded):

- Strategy:
  - pre-hint *all* call outputs to ABI return registers on AArch64.
- Result:
  - introduced major code-size regression and ARM runtime test failures:
    - compact-shape size: `77160 -> 85160`
    - singleton delta: `384 -> 424`
  - failing tests:
    - `test_aarch64_call_sites_are_compact`
    - `test_aarch64_singleton_immediate_call_target_prefers_direct_literal`
- Root-cause inference:
  - broad hint over-constrained object-return call chains and increased
    spill/shuffle pressure around dense call sites.

Attempt B (safe but weak):

- Strategy:
  - restrict hint to FP call outputs only.
- Result:
  - ARM runtime tests passed.
  - code-size probe remained stable (`760/1144/delta=384`, `size200=77160`).
  - performance gain was small and mostly inconclusive (`~0.2%` class).

Attempt C (current):

- Strategy:
  - only hint short immediate call chains:
    - `call -> single immediate use -> call(arg0=previous result)`
  - this keeps the optimization on the intended hot path while avoiding broad
    register-pressure side effects.
- Validation:
  - ARM runtime tests: pass (`5/5`)
  - code-size probe:
    - `size1=760`, `size2=1144`, `delta=384`, `size200=77160`
- Artifacts:
  - `artifacts/richards/arm_after_regalloc_callchain_hint_mcs0_s8.json`
  - `artifacts/richards/arm_after_regalloc_callchain_hint_mcs0_s8_b.json`
  - `artifacts/richards/regalloc_callchain_hint_vs_baseline_mcs0_s8_summary.json`
  - `artifacts/richards/regalloc_callchain_hint_repeat_summary_20260221.json`

From -> To (`mcs=0`, baseline `artifacts/richards/arm_mcs0_richards_s8.json`):

- Run A (`n=8`):
  - `jitlist`: `0.0519003826 -> 0.0516489598 s` (`+0.4868%`, CI `[+0.0259%, +0.9590%]`)
  - `autojit50`: `0.0519645600 -> 0.0517226194 s` (`+0.4678%`, CI `[-0.0511%, +1.0594%]`)
- Run B (`n=8`):
  - `jitlist`: `0.0519003826 -> 0.0519029235 s` (`-0.0049%`, CI `[-0.6906%, +0.6573%]`)
  - `autojit50`: `0.0519645600 -> 0.0516798520 s` (`+0.5509%`, CI `[+0.0785%, +1.1032%]`)
- Pooled after (`n=16`) vs baseline (`n=8`):
  - `jitlist`: `+0.2403%` (CI `[-0.2808%, +0.7373%]`)
  - `autojit50`: `+0.5093%` (CI `[+0.0369%, +1.0711%]`)

Interpretation:

- This heuristic no longer regresses code size and keeps ARM runtime tests
  green.
- Observed gain is small but measurable for `autojit50` in pooled data
  (`~+0.5%`, CI slightly above 0).
- `jitlist` gain is unstable across reruns; treat that part as inconclusive.

### Unified ARM/X86 Check After Call-Chain Hint

- Date: 2026-02-21
- Method:
  - `scripts/bench/collect_arm_x86_richards.ps1 -Samples 5 -AutoJit 50`
- Artifacts:
  - `artifacts/richards/summary_arm_vs_x86_20260221_011223.json`
  - `artifacts/richards/arm_samples_20260221_011223.json`
  - `artifacts/richards/x86_samples_20260221_011223.json`

From -> To (vs previous `AutoJit=50` unified snapshot
`summary_arm_vs_x86_20260220_234127.json`):

- ARM `autojit50` mean:
  - `0.0518055044 -> 0.0518427644 s` (`-0.0719%`, essentially flat)
- X86 `autojit50` mean:
  - `0.0755916389 -> 0.0983565764 s` (x86 slower in this run)
- Reported ARM-vs-X86 speedup:
  - `+31.4666% -> +47.2910%`

Interpretation:

- The ARM absolute runtime is basically unchanged on this check.
- Relative ARM-vs-X86 gain increase here is dominated by x86-side run
  variance, not by a clear ARM-side throughput jump.

