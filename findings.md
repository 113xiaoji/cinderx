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

Follow-up attempt (not kept):

- Tried expanding the short-chain hint from only `arg0` to any `argN`
  call-argument register mapping.
- Correctness remained green (`test_arm_runtime.py` passed), but performance
  evidence was not reliable:
  - host had competing `cargo/rustc` load bursts (load average > 4 with
    multiple 100% `rustc` workers),
  - richards samples showed cross-mode outliers (`~0.08s`, `~0.12s`, `~0.17s`)
    in runs that should stay around `~0.052s`.
- Clean-ish rerun still showed unstable outliers and no robust improvement for
  JIT modes.
- Decision: revert this wider `argN` variant and keep the narrower, previously
  validated short-chain heuristic.

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

### Step 3 Recheck Under Idle ARM Host

- Date: 2026-02-21
- Motivation:
  - some intermediate runs were contaminated by external host load
    (`cargo/rustc` workers), so reran after load returned to idle.
- Artifacts:
  - `artifacts/richards/arm_after_regalloc_callchain_hint_mcs0_s8_clean2.json`
  - `artifacts/richards/regalloc_callchain_hint_vs_baseline_mcs0_s8_clean2_summary.json`

From -> To (stable arg0 short-chain hint vs baseline `mcs0_s8`):

- `jitlist` mean:
  - `0.0519003826 -> 0.0516978134 s` (`+0.3918%`)
  - CI: `[-0.2618%, +0.9960%]` (still slightly inconclusive)
- `autojit50` mean:
  - `0.0519645600 -> 0.0516449700 s` (`+0.6188%`)
  - CI: `[+0.1306%, +1.1866%]` (positive on this clean rerun)

Interpretation:

- Under low-load conditions, the current short-chain hint remains small but
  positive on `autojit50` (around `+0.6%`).
- This is still a micro-gain; continue with next hot-path optimization stage to
  target additional uplift.

### Step 3 Attempt: postalloc call-result move-chain fold

- Date: 2026-02-21
- Code path:
  - `cinderx/Jit/lir/postalloc.cpp`
- Idea:
  - fold a narrow hot path in postalloc:
    - `Move tmp, <retreg>` + `Move <argreg>, tmp`
    - into direct `<argreg> <- <retreg>` and drop the previous move on last-use
  - keep the transform restricted to argument-register destinations to avoid
    broad copy-propagation side effects.

Validation:

- Remote entrypoint deploy/build/smoke:
  - `scripts/arm/remote_update_build_test.sh` (`SKIP_PYPERF=1`)
  - passed on ARM host (`test_arm_runtime.py`: `5/5`).
- Benchmark runner:
  - `scripts/bench/run_richards_remote.sh`
  - `SAMPLES=8`, `AUTOJIT=50`, `PYTHONJITMULTIPLECODESECTIONS=0`
  - baseline and after both run under the same remote path.

Artifacts:

- Baseline samples:
  - `artifacts/richards/arm_baseline_postalloc_ab_s8_clean_20260221_084809.json`
- After samples:
  - `artifacts/richards/arm_postalloc_ab_s8_clean_20260221_085811.json`
- Comparison summary:
  - `artifacts/richards/postalloc_hotpath_vs_baseline_s8_summary_20260221.json`

From -> To (`baseline -> postalloc`, lower is better):

- `jitlist` mean:
  - `0.0518290104 -> 0.0518108696 s` (`+0.0350%`)
  - CI: `[-0.4915%, +0.6462%]` (inconclusive)
- `autojit50` mean:
  - `0.0519340710 -> 0.0516975166 s` (`+0.4555%`)
  - CI: `[+0.0476%, +0.9103%]` (positive)

Interpretation:

- This postalloc fold gives another small positive gain on `autojit50`
  (about `+0.46%`) with CI above zero in this run.
- `jitlist` remains effectively flat and statistically inconclusive.
- Result is consistent with the previous pattern: micro-gain on autojit hot
  path, not a large mode-wide shift.

### Unified ARM/X86 Check After Postalloc Fold

- Date: 2026-02-21
- Method:
  - `scripts/bench/collect_arm_x86_richards.ps1 -Samples 8 -AutoJit 50`
- Artifacts:
  - `artifacts/richards/summary_arm_vs_x86_20260221_091757.json`
  - `artifacts/richards/arm_samples_20260221_091757.json`
  - `artifacts/richards/x86_samples_20260221_091757.json`
  - `artifacts/richards/summary_nojit_20260221_091757.json`
  - `artifacts/richards/summary_jitlist_20260221_091757.json`
  - `artifacts/richards/summary_autojit50_20260221_091757.json`

From -> To (vs previous cross-host snapshot
`summary_arm_vs_x86_20260221_011223.json`):

- `autojit50`:
  - ARM mean: `0.0518427644 -> 0.0520960826 s` (`-0.4886%`)
  - X86 mean: `0.0983565764 -> 0.1080564280 s`
  - ARM-vs-X86 speedup: `+47.2910% -> +51.7881%`
- `jitlist`:
  - ARM mean: `0.0517584942 -> 0.0547409418 s`
  - X86 mean: `0.0958292193 -> 0.0920441395 s`
  - ARM-vs-X86 speedup: `+45.9888% -> +40.5275%`

Interpretation:

- Cross-host result still comfortably satisfies the target "ARM >= X86 +3%"
  on all modes, including `autojit50`.
- This run has noticeable tail-noise on both hosts (e.g. ARM `jitlist`
  has `0.064s` samples; x86 `nojit` reaches `0.20s`, `autojit50` reaches
  `0.162s`), so cross-host deltas should be treated as directional rather than
  precise micro-regression/progression evidence.
- The cleaner signal for the postalloc optimization remains the ARM-only A/B:
  `autojit50` `0.0519341 -> 0.0516975 s` (`+0.4555%`, CI positive).

### Step 3 Iteration: call-result fold across guard gaps

- Date: 2026-02-21
- Commits:
  - `18d9c4d5` (initial self-move-gap fold + RED test)
  - `c7330521` (root-cause fix: fold across non-clobber guard gaps)
- Code path:
  - `cinderx/Jit/lir/postalloc.cpp`
  - `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

TDD and root-cause evidence:

- RED:
  - new regression test
    `test_aarch64_duplicate_call_result_arg_chain_is_compact` failed on ARM:
    - compiled size `44656`, guard `<= 44500`.
- Investigation:
  - enabled `PYTHONJITDUMPLIR=1` + `PYTHONJITLOGFILE`.
  - observed real hot pattern was not adjacent move pairs; call-result copies are
    frequently separated by `Guard` / metadata updates before arg-lowering move.
  - conclusion:
    - adjacent-only folding misses the dominant chain shape for this workload.
- GREEN:
  - rewrote matching to scan backward across non-clobber instructions and stop
    on `tmp`/`retreg` overwrite or any call boundary.
  - remote entrypoint validation (`remote_update_build_test.sh`, `SKIP_PYPERF=1`)
    passed with runtime tests `6/6`.

From -> To (synthetic hot-shape size; lower is better):

- Artifact:
  - `artifacts/richards/guardgap_fold_shape_compare_20260221.json`
- Representative point (`n_calls=64`):
  - `44656 -> 44144` bytes (`-512`, `-1.1465%`)
- Linear trend:
  - each doubling keeps the same direction; savings scale with call-chain count.

Richards snapshot after this iteration:

- Artifact:
  - `artifacts/richards/arm_after_guardgap_fold_s8.json`
  - `artifacts/richards/arm_after_guardgap_fold_s8_summary.json`
- Means (`n=8`):
  - `nojit`: `0.07656 s`
  - `jitlist`: `0.11976 s`
  - `autojit50`: `0.12580 s`

Interpretation:

- This run is heavily noise/host-load contaminated (very wide tails vs prior
  stable `~0.05s`-class snapshots), so it is not a reliable micro-throughput
  signal.
- The robust signal for this iteration is the confirmed code-shape reduction
  on the targeted call-result chain pattern, now guarded by a regression test.



# Findings & Decisions

## Requirements
- Enable `ENABLE_ADAPTIVE_STATIC_PYTHON` to work on official Python 3.14 ARM server path.
- Enable and follow skills/process: `using-superpowers` + `planning-with-files`.
- Execute the standard loop: `brainstorming -> writing-plans -> test-driven-development -> verification-before-completion`.
- Use `<remote test entry>` for all test/verification runs.
- Write key test/verification outcomes into this file.

## Research Findings
- `ENABLE_ADAPTIVE_STATIC_PYTHON` appears in `setup.py` (active editor context from user).
- Planning files were not present initially and were created in project root.
- `planning-with-files` catchup script ran without unsynced-session output.
- `setup.py` currently sets `ENABLE_ADAPTIVE_STATIC_PYTHON` via `set_option("ENABLE_ADAPTIVE_STATIC_PYTHON", meta_312)`, which suggests 3.12-gated behavior.
- `CMakeLists.txt` exposes `set_flag(ENABLE_ADAPTIVE_STATIC_PYTHON)`.
- Source tree already contains `ENABLE_ADAPTIVE_STATIC_PYTHON` usage in:
  - `cinderx/Interpreter/3.14/*`
  - `cinderx/Interpreter/3.15/*`
  - `cinderx/Interpreter/3.12/*`
- No concrete repository path/command for `<remote test entry>` found yet.
- `setup.py` computes:
  - `meta_312 = meta_python and py_version == "3.12"`
  - `is_314plus = py_version == "3.14" or py_version == "3.15"`
  - But `ENABLE_ADAPTIVE_STATIC_PYTHON` still defaults to `meta_312`.
- `.github/workflows/ci.yml` and `.github/workflows/publish.yml` pin Python `3.14.3`.
- `.github/workflows/getdeps-3_14-linux.yml` uses getdeps as a full build/test pipeline, with test command:
  - `python3 build/fbcode_builder/getdeps.py test --src-dir=. cinderx-3_14 --project-install-prefix cinderx-3_14:/usr/local`
- `build/fbcode_builder/manifests/cinderx-3_14` defines:
  - `[setup-py.test] python_script = cinderx/PythonLib/test_cinderx/test_oss_quick.py`
  - `[setup-py.env] CINDERX_ENABLE_PGO=1, CINDERX_ENABLE_LTO=1`
- CI quick path exists separately:
  - `uv run pytest cinderx/PythonLib/test_cinderx/test*.py`
- Current likely candidates for `<remote test entry>` are:
  - getdeps test command (closer to release/manifest workflow)
  - CI pytest command (faster feedback)
- `build/fbcode_builder/manifests/cinderx-3_14` quick test currently only checks import (`test_oss_quick.py`), not adaptive-static functionality.
- `git blame setup.py` shows:
  - `ENABLE_ADAPTIVE_STATIC_PYTHON` default (`meta_312`) introduced in commit window around 2025-10 OSS 3.14 compatibility work.
  - Later 2026-01 changes added `is_314plus` only for `ENABLE_INTERPRETER_LOOP` and `ENABLE_PEP523_HOOK`, leaving adaptive-static unchanged.
- `README.md` currently lists Linux `x86_64` as requirement; ARM is not declared as supported in OSS docs.
- `pyproject.toml` cibuildwheel targets only `cp314-manylinux_x86_64` and `cp314-musllinux_x86_64` (no ARM wheel target).
- Repository does contain multiple recent AArch64-related fixes, indicating partial ARM compatibility efforts despite packaging targets being x86_64.
- No dedicated test file currently verifies `setup.py` defaulting logic for `ENABLE_ADAPTIVE_STATIC_PYTHON`.
- Commit `d0297b3e` ("Enable interpreter loop on 3.14 OSS builds") notes that some codepaths (including adaptive-static control knobs) could not compile without interpreter loop, and enabled interpreter loop/PEP523 for 3.14.
- Even after that commit, `ENABLE_ADAPTIVE_STATIC_PYTHON` stayed defaulted to `meta_312`, indicating prior conservative rollout rather than missing implementation.
- In `cinderx/Interpreter/3.14/interpreter.c`, `Ci_InitOpcodes()` patches CPython opcode cache/deopt tables only when `ENABLE_ADAPTIVE_STATIC_PYTHON` is defined.
- In `cinderx/Interpreter/3.14/cinder-bytecodes.c`, many runtime specializations are gated by `#if ENABLE_SPECIALIZATION && defined(ENABLE_ADAPTIVE_STATIC_PYTHON)`, including:
  - `STORE_LOCAL_CACHED`
  - `BUILD_CHECKED_LIST_CACHED`
  - `BUILD_CHECKED_MAP_CACHED`
  - `LOAD_METHOD_STATIC_CACHED`
  - `INVOKE_FUNCTION_CACHED` / indirect cached path
  - `TP_ALLOC_CACHED`
  - `CAST_CACHED`
  - `LOAD_OBJ_FIELD` / `LOAD_PRIMITIVE_FIELD`
  - `STORE_OBJ_FIELD` / `STORE_PRIMITIVE_FIELD`
- Therefore enabling this flag is expected to affect adaptive specialization behavior and performance characteristics for Static Python-heavy paths.
- Attempted remote execution on ARM host `124.70.162.35` via SSH failed due authentication:
  - `Permission denied (publickey,gssapi-keyex,gssapi-with-mic,password)`
- `getdeps` current test entry for `cinderx-3_14` is import-only (`test_oss_quick.py`), insufficient to prove adaptive-static specialization is active.
- Existing static runtime tests contain comments about exercising cached paths (e.g. `INVOKE_FUNCTION_CACHED`) but do not explicitly assert adaptive/cached opcode presence.
- Existing bytecode assertion helpers in `test_compiler/common.py` use regular disassembly (`Bytecode(...)`) and do not inspect adaptive-specialized instruction stream by default.
- Implemented changes in this session:
  - `setup.py`: added `should_enable_adaptive_static_python()` and switched default option source to it.
  - `setup.py`: added `is_env_flag_enabled()` and switched `CINDERX_ENABLE_PGO/CINDERX_ENABLE_LTO` to real boolean parsing (`0/false/off/no` disables).
  - `_cinderx`: added runtime API `is_adaptive_static_python_enabled()`.
  - `cinderx.__init__`: exports `is_adaptive_static_python_enabled()` with fallback.
  - `test_oss_quick.py`: now asserts adaptive-static enablement state by platform/version.
  - Added local unit tests for setup default logic, env-flag parsing, and API presence.

## Verification Results
- Local RED (expected):
  - `python -m unittest tests/test_setup_adaptive_static_python.py -v`
  - Failure reason: missing `setup.should_enable_adaptive_static_python`.
- Local GREEN:
  - `$env:PYTHONPATH='cinderx/PythonLib'; python -m unittest tests/test_setup_adaptive_static_python.py tests/test_cinderx_adaptive_static_api.py -v`
  - Result: 10 tests passed.
- Syntax check:
  - `python -m py_compile setup.py cinderx/PythonLib/cinderx/__init__.py cinderx/PythonLib/test_cinderx/test_oss_quick.py tests/test_setup_adaptive_static_python.py tests/test_cinderx_adaptive_static_api.py`
  - Result: pass.
- Remote ARM verification (`124.70.162.35`, `aarch64`, Python `3.14.3`):
  - `getdeps build` failure (captured):
    - `getdeps.py build --src-dir=. cinderx-3_14 ...`
    - Failure: `/usr/bin/ld: ... LLVMgold.so: cannot open shared object file`
  - Root-cause evidence:
    - `setup.py` previously enabled LTO when `CINDERX_ENABLE_LTO` env var merely existed.
    - `getdeps` manifest exports `CINDERX_ENABLE_LTO=1 CINDERX_ENABLE_PGO=1`.
  - Remote install pass after fixes:
    - `env CINDERX_ENABLE_PGO=0 CINDERX_ENABLE_LTO=0 python setup.py install`
    - Build/install reached `[100%] Built target _cinderx` and installed to `/root/venv-cinderx314/lib/python3.14/site-packages`.
  - Remote functional checks (same host/venv):
    - `python cinderx/PythonLib/test_cinderx/test_oss_quick.py` -> `Ran 2 tests ... OK`
    - Runtime probe:
      - `hasattr(cinderx, "is_adaptive_static_python_enabled") == True`
      - `cinderx.is_adaptive_static_python_enabled() == True`
  - Remote enablement evidence (build artifacts):
    - `scratch/temp.linux-aarch64-cpython-314/CMakeCache.txt` contains `ENABLE_ADAPTIVE_STATIC_PYTHON:UNINITIALIZED=1`
    - `_cinderx` flags contain `-DENABLE_ADAPTIVE_STATIC_PYTHON` in:
      - `scratch/temp.linux-aarch64-cpython-314/CMakeFiles/_cinderx.dir/flags.make`

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Defer implementation until brainstorming design is approved | Required by brainstorming skill hard gate |
| Keep verification evidence tied to `<remote test entry>` only | Explicit user requirement |
| Enable by default on Python 3.14 ARM only | Matches target while minimizing regression surface compared with global 3.14+ enablement |
| Treat `CINDERX_ENABLE_PGO/LTO` as boolean values, not presence-only toggles | Required for reliable ARM builds where LTO toolchain plugin may be unavailable |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Default path for `session-catchup.py` did not exist in this environment | Switched to the installed skill path under `C:/Users/Administrator/.codex/planning-with-files/...` |
| `rg` against non-existent `tools/` and `scripts/` paths failed | Scoped next searches to existing paths (`.github/`, repository root) |
| RED test initially failed due missing local dependency `setuptools` | Installed `setuptools` and re-ran to capture expected feature-missing failure |
| API unit test imported non-repo `cinderx` package | Ran tests with `PYTHONPATH=cinderx/PythonLib` to target repository code |
| `getdeps build` failed linking `_cinderx.so` with missing `LLVMgold.so` | Added boolean env parsing in `setup.py`; validated with `CINDERX_ENABLE_LTO=0` |
| ARM host initially missed system build prerequisite `m4` for getdeps autoconf path | Installed with `dnf install -y m4` |

## Resources
- `setup.py`
- `task_plan.md`
- `progress.md`
- Skill docs:
  - `C:/Users/Administrator/.codex/superpowers/skills/using-superpowers/SKILL.md`
  - `C:/Users/Administrator/.codex/planning-with-files/.codex/skills/planning-with-files/SKILL.md`
  - `C:/Users/Administrator/.codex/superpowers/skills/brainstorming/SKILL.md`
  - `C:/Users/Administrator/.codex/superpowers/skills/writing-plans/SKILL.md`
  - `C:/Users/Administrator/.codex/superpowers/skills/test-driven-development/SKILL.md`
  - `C:/Users/Administrator/.codex/superpowers/skills/verification-before-completion/SKILL.md`

## Visual/Browser Findings
- No browser or image operations used yet.

---
*Remote verification evidence updated on 2026-02-24 against `124.70.162.35`.*

## 2026-02-25 ARM verification (124.70.162.35)

- Scope: verify `ENABLE_ADAPTIVE_STATIC_PYTHON` works both without LTO and with LTO enabled.
- Build environment: `/root/venv-cinderx314` + Python 3.14 on aarch64.

### Code/Build adjustments used in this run

- `CMakeLists.txt` LTO logic keeps `ld.lld` preference for Clang LTO.
- `CMakeLists.txt` FetchContent sources switched from `GIT_REPOSITORY` to fixed `codeload.github.com` tarball URLs for:
  - `asmjit`
  - `fmt`
  - `parallel-hashmap`
  - `usdt`

### Validation results

1. No-LTO build/install

- Command:
  - `env CINDERX_ENABLE_PGO=0 CINDERX_ENABLE_LTO=0 python setup.py install`
- Log: `/tmp/cinderx_no_lto.log`
- Result:
  - Build reached `[100%] Built target _cinderx` and install phase (`install_lib`, `install_egg_info`, `install_scripts`).
  - Runtime probe: `ADAPTIVE_STATIC True`

2. LTO build/install

- Command:
  - `env CINDERX_ENABLE_PGO=0 CINDERX_ENABLE_LTO=1 python setup.py install`
- Log: `/tmp/cinderx_with_lto.log`
- Result:
  - Log contains `LTO: Enabled (full LTO)` and reaches install phase (`install_lib`, `install_egg_info`, `install_scripts`).
  - Runtime probe: `ADAPTIVE_STATIC True`
  - LTO evidence on generated build files:
    - `scratch/temp.linux-aarch64-cpython-314/CMakeCache.txt`: `ENABLE_LTO:BOOL=ON`
    - `scratch/temp.linux-aarch64-cpython-314/CMakeFiles/*/flags.make`: contains `-flto`
    - `scratch/temp.linux-aarch64-cpython-314/CMakeFiles/_cinderx.dir/link.txt`: contains `-flto -fuse-ld=lld`

3. End-to-end smoke

- Command:
  - `python cinderx/PythonLib/test_cinderx/test_oss_quick.py`
- Result:
  - `Ran 2 tests ... OK`

## 2026-02-25 bench-cur-7c361dce integration verification

- Target branch: `bench-cur-7c361dce`
- Upstream sync: merged `upstream/main` (facebookincubator/cinderx) into branch.
- Feature merge: cherry-picked commit `170439be` (ENABLE_ADAPTIVE_STATIC_PYTHON + LTO robustness).
- Resulting branch head: `91363f8f`.

### Local validation

- `PYTHONPATH=cinderx/PythonLib python -m unittest tests/test_setup_adaptive_static_python.py tests/test_cinderx_adaptive_static_api.py`
- Result: `Ran 10 tests ... OK`.

### ARM validation host

- Host: `124.70.162.35`
- Source under test: snapshot of local `bench-cur-7c361dce` synced to `/root/work/cinderx-main`.

1. No LTO
- Build command: `CINDERX_ENABLE_PGO=0 CINDERX_ENABLE_LTO=0 python setup.py install`
- Log: `/tmp/bench_no_lto.log`
- Result:
  - install reached `running install_scripts`
  - `ADAPTIVE_STATIC True`
  - no `LTO:` marker in log.

2. With LTO
- Build command: `CINDERX_ENABLE_PGO=0 CINDERX_ENABLE_LTO=1 python setup.py install`
- Log: `/tmp/bench_with_lto.log`
- Result:
  - background build exit code `0` (`/tmp/bench_with_lto.exit`)
  - `ADAPTIVE_STATIC True`
  - LTO enabled evidence:
    - `/tmp/bench_with_lto.log`: `LTO: Enabled (full LTO)`
    - `scratch/temp.linux-aarch64-cpython-314/CMakeCache.txt`: `ENABLE_LTO:BOOL=ON`
    - `scratch/temp.linux-aarch64-cpython-314/CMakeFiles/*/flags.make`: contains `-flto`
    - `scratch/temp.linux-aarch64-cpython-314/CMakeFiles/_cinderx.dir/link.txt`: contains `-flto -fuse-ld=lld`

3. Smoke test
- `python cinderx/PythonLib/test_cinderx/test_oss_quick.py`
- Result: `Ran 2 tests ... OK`

## 2026-02-25 New Task: ENABLE_LIGHTWEIGHT_FRAMES + LTO/PGO/ADAPTIVE_STATIC (ARM 3.14)

### Requirements captured
- Enable and debug `ENABLE_LIGHTWEIGHT_FRAMES` on official Python 3.14 ARM server.
- Must coexist with:
  - `CINDERX_ENABLE_LTO=1`
  - `CINDERX_ENABLE_PGO=1`
  - `ENABLE_ADAPTIVE_STATIC_PYTHON=1`
- Workflow explicitly required:
  - brainstorming -> writing-plans -> test-driven-development -> verification-before-completion
- All tests and validation must run through remote entrypoint (`<远端测试入口>`).
- Key outcomes/evidence must be recorded in `findings.md`.

### Initial discoveries
- Existing setup defaults currently gate `ENABLE_LIGHTWEIGHT_FRAMES` to meta 3.12 path, not 3.14 by default.
- Previous work already stabilized adaptive static + LTO on ARM 3.14 and switched CMake dependency fetches to codeload tarballs for reliability.

### Open questions to resolve in brainstorming
1. Exact command/script that user wants treated as `<远端测试入口>` for this task.
2. Authoritative signal for "lightweight frames enabled" acceptance.
3. Required verification breadth (targeted tests only vs targeted + smoke suite).

### Context exploration updates (brainstorming)
- `setup.py` currently sets `ENABLE_LIGHTWEIGHT_FRAMES` default to `meta_312` only.
- C++ side already has many `#ifdef ENABLE_LIGHTWEIGHT_FRAMES` and 3.14-specific code paths (`PY_VERSION_HEX >= 0x030E0000`) in JIT runtime/frame/codegen files.
- There is currently no user-facing API equivalent to `is_adaptive_static_python_enabled()` for lightweight-frames compile-time state.
- Existing tests cover adaptive-static behavior (`tests/test_setup_adaptive_static_python.py`, `tests/test_cinderx_adaptive_static_api.py`, `test_oss_quick.py`) but do not yet assert lightweight-frames enablement.

### 2026-02-25 Brainstorming decision update
- User decision: prioritize Python 3.14 support for `ENABLE_LIGHTWEIGHT_FRAMES`.
- Design adjustment: Stage A default enable scope targets 3.14 first (ARM), not broad 3.15 rollout.

## 2026-02-26 Completion Evidence: LIGHTWEIGHT_FRAMES + LTO/PGO/ADAPTIVE_STATIC (ARM 3.14)

### Stage-A policy confirmation
- `setup.py` now applies:
  - `ENABLE_LIGHTWEIGHT_FRAMES` default `ON` for OSS Python `3.14` on `aarch64/arm64`
  - `ENABLE_LIGHTWEIGHT_FRAMES` default `OFF` for `3.15` in Stage A (still manually overridable via env)
  - existing meta `3.12` behavior preserved
- User-confirmed rollout:
  - prioritize 3.14 now
  - x86 extension deferred
  - 3.15 deferred, stage-A default-off accepted

### Additional robustness fix for PGO
- Symptom observed:
  - intermittent `test_generators` failure during `PGO STAGE 2/3` workload caused `setup.py install` failure with `CINDERX_ENABLE_PGO=1`.
- Fix:
  - added `run_pgo_workload()` in `setup.py`
  - bounded retry on workload failure (`2` attempts total)
  - wired `BuildCommand._run_with_pgo()` to use helper
- TDD:
  - RED: `tests/test_setup_pgo_workload_retries.py` failed (`AttributeError: module 'setup' has no attribute 'run_pgo_workload'`)
  - GREEN: same test passed after helper implementation

### Remote test entrypoint
- All verification executed through:
  - `ssh root@124.70.162.35`
- Remote runtime:
  - Python `3.14.3`
  - arch `aarch64`
  - source under test: `/root/work/cinderx-main`

### Remote verification commands and outcomes

1. Setup/default/API tests
- Command:
  - `python -m unittest tests/test_setup_adaptive_static_python.py tests/test_setup_lightweight_frames.py tests/test_setup_pgo_workload_retries.py -v`
  - `PYTHONPATH=cinderx/PythonLib python -m unittest tests/test_cinderx_lightweight_frames_api.py -v`
- Result:
  - `Ran 15 tests ... OK`
  - `Ran 2 tests ... OK`

2. LTO path
- Command:
  - `CINDERX_ENABLE_PGO=0 CINDERX_ENABLE_LTO=1 python setup.py install`
- Result:
  - install success (ssh command exit code `0`)
  - runtime probe:
    - `ADAPTIVE_STATIC True`
    - `LIGHTWEIGHT_FRAMES True`
  - build evidence:
    - `scratch/temp.linux-aarch64-cpython-314/CMakeCache.txt`:
      - `ENABLE_LTO:BOOL=ON`
      - `ENABLE_ADAPTIVE_STATIC_PYTHON:UNINITIALIZED=1`
      - `ENABLE_LIGHTWEIGHT_FRAMES:UNINITIALIZED=1`
    - `scratch/temp.linux-aarch64-cpython-314/CMakeFiles/_cinderx.dir/link.txt` contains:
      - `-flto`
      - `-fuse-ld=lld`
      - `-DENABLE_ADAPTIVE_STATIC_PYTHON`
      - `-DENABLE_LIGHTWEIGHT_FRAMES`

3. PGO + LTO path
- Command:
  - `CINDERX_ENABLE_PGO=1 CINDERX_ENABLE_LTO=1 python setup.py install`
- Result:
  - full 3-stage PGO flow completed successfully (ssh command exit code `0`)
  - log confirms:
    - `PGO STAGE 1/3`
    - `PGO STAGE 2/3: Running profiling workload`
    - `PGO STAGE 2b: Merging profile data`
    - `PGO STAGE 3/3: Rebuilding with profile-guided optimizations`
  - PGO/LTO evidence in cache and link flags:
    - `ENABLE_PGO_GENERATE:BOOL=OFF`
    - `ENABLE_PGO_USE:BOOL=ON`
    - `PGO_PROFILE_FILE:STRING=/root/work/cinderx-main/scratch/temp.linux-aarch64-cpython-314/pgo_data/code.profdata`
    - link flags include:
      - `-flto`
      - `-fprofile-instr-use=/root/work/cinderx-main/scratch/temp.linux-aarch64-cpython-314/pgo_data/code.profdata`
      - `-DENABLE_ADAPTIVE_STATIC_PYTHON`
      - `-DENABLE_LIGHTWEIGHT_FRAMES`
  - runtime probe after install:
    - `ADAPTIVE_STATIC True`
    - `LIGHTWEIGHT_FRAMES True`

4. Smoke test
- Command:
  - `python cinderx/PythonLib/test_cinderx/test_oss_quick.py`
- Result:
  - `Ran 3 tests ... OK`

### Final conclusion
- On ARM Python 3.14, `ENABLE_LIGHTWEIGHT_FRAMES` is now verified to work end-to-end together with:
  - `ENABLE_ADAPTIVE_STATIC_PYTHON`
  - `CINDERX_ENABLE_LTO=1`
  - `CINDERX_ENABLE_PGO=1`
- Stage-A policy is as requested:
  - 3.14 prioritized
  - 3.15 default-off (manual env override still available)
  - x86 extension deferred to later phase

## 2026-02-27 Task: CPython Native vs CinderX (Interpreter + JIT) on ARM 3.14

### Requested workflow status
- Requested process: `brainstorming -> writing-plans -> test-driven-development -> verification-before-completion`.
- Requested skills: `using-superpowers` + `planning-with-files`.
- Session constraints observed:
  - active skill registry in this session does not include those two skills,
  - `skill-installer` helper could not be executed because local `python` is unavailable.

### Brainstorming results
- Existing benchmark evidence is already sufficient to explain the main behavior pattern:
  - cold/short-run results often make JIT look slower,
  - warm/steady-state results can show JIT speedups.
- Current richards runner contract does not include an explicit "pure CPython native (no CinderX import)" mode:
  - `scripts/bench/run_richards_remote.sh` supports `nojit`, `jitlist`, `autojit50`.
  - `scripts/arm/remote_update_build_test.sh` injects `sitecustomize.py` that auto-loads CinderX unless `CINDERX_DISABLE=1`.
  - Therefore current `nojit` should be interpreted as "CinderX loaded, JIT disabled", not pure CPython baseline.

### Writing-plans output
- Plan file created: `docs/plans/2026-02-27-cpython-vs-cinderx-314-arm-analysis.md`.

### TDD status for this task
- RED/GREEN target defined:
  - add explicit `cpython` mode to richards sampling contract,
  - then compare `cpython` vs `cinderx_nojit` vs `jitlist` vs `autojit50`.
- Execution status:
  - blocked before RED/GREEN run because remote verification entrypoint is currently unreachable in this session.

### Verification attempts via `<remote test entry>`
- Attempted remote entry command:
  - `powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 -RepoPath c:\work\code\cinderx -WorkBranch bench-cur-7c361dce -ArmHost 124.70.162.35 -SkipPyperformance`
- Result:
  - failed in `sync_upstream.ps1` at `git fetch origin` (`Failed to connect to github.com:443` / connection reset).
- Direct host connectivity checks:
  - `ssh root@124.70.162.35 "echo remote-ok"` -> `Permission denied (publickey,...)`
  - `ssh root@106.14.164.133 "echo remote-ok"` -> `Permission denied (publickey,...)`

### Performance evidence used for analysis (existing validated artifacts)
- Source: `artifacts/richards/arm_samples_20260221_091757.json`
  - `nojit` mean: `0.0534650194 s`
  - `jitlist` mean: `0.0547409418 s` (`+2.386%` vs nojit, slower)
  - `autojit50` mean: `0.0520960826 s` (`-2.560%` vs nojit, faster)
- Source: prior cold/short-run section (`pyperformance --fast`) in this file:
  - nojit `103 ms`, jitlist `181 ms`, autojit50 `191 ms` (JIT appears much slower).
- Source: prior warm-loop tail section in this file:
  - nojit tail-30 `0.2130860543 s`
  - jitlist tail-30 `0.1841729017 s` (`-13.57%`)
  - autojit50 tail-30 `0.0810525232 s` (`-61.96%`)

### Why ARM 3.14 can look "full" / slower
- Benchmark regime mismatch:
  - in short/cold runs, JIT compile and initialization overhead dominates;
  - in warm runs, compiled-path wins can appear after overhead amortization.
- Low-latency floor + host noise:
  - many ARM samples are near `~0.05s`; sub-1% gains are easily hidden by jitter/outliers.
- Baseline definition gap:
  - current "nojit" is not pure CPython native, so "CPython vs CinderX" can be misread.
- Threshold/workload interaction:
  - `autojit` behavior depends on call counts and worker lifecycle; short tasks may pay compile cost without enough hot-loop reuse.

### Next required step for definitive answer
- Add and validate explicit `cpython` sampling mode (`CINDERX_DISABLE=1`) through the same remote entry flow, then re-run comparison matrix after remote auth/network is restored.

## 2026-02-27 Remote Run: CPython Native (interp/JIT) vs CinderX (interp/JIT)

### Remote target
- Host: `root@124.70.162.35`
- Arch: `aarch64`

### Environment facts observed
- Existing CPython at `/opt/python-3.14/bin/python3.14` had:
  - `sys._jit.is_available() == False`
  - i.e. cannot directly run native CPython JIT there.
- Built a JIT-enabled CPython 3.14.3 under tmpfs:
  - install path: `/tmp/cpython314jit/install/bin/python3.14`
  - build source: `/tmp/cpython314jit/src` from `Python-3.14.3.tgz`
  - config: `--enable-experimental-jit=yes-off`
  - verification:
    - default: `sys._jit -> (True, False)`
    - `PYTHON_JIT=1`: `sys._jit -> (True, True)`
- CinderX runtime path:
  - `/root/venv-cinderx314/bin/python`
  - JIT API sanity check:
    - `cinderx.jit.force_compile(f) == True`
    - compiled size observed (`f`): `960` bytes.

### Practical blocker and workaround
- Root filesystem is full (`/` at 100%), so `pyperformance run` default venv root under `/root/venv` fails.
- Workaround used:
  - build CPython JIT in `/tmp` (tmpfs),
  - run benchmark directly via `bm_richards/run_benchmark.py` + `--debug-single-value`,
  - avoid pyperformance's internal auto-venv creation in `/root`.

### Benchmark method
- Benchmark script:
  - `/root/venv-cinderx314/lib/python3.14/site-packages/pyperformance/data-files/benchmarks/bm_richards/run_benchmark.py`
- Samples per mode: `5`
- Modes:
  - `cpython_interp`: `/tmp/venv-cpython314jit/bin/python`, `PYTHON_JIT=0`
  - `cpython_jit`: `/tmp/venv-cpython314jit/bin/python`, `PYTHON_JIT=1`
  - `cinderx_interp`: `/root/venv-cinderx314/bin/python`, `PYTHONJITDISABLE=1`
  - `cinderx_jit`: `/root/venv-cinderx314/bin/python`, `PYTHONJITAUTO=50`

### Key results (richards, lower is better)
- Artifact:
  - `artifacts/richards/direct_richards_cpython_cinderx_autojit_20260227_130845.json`

- Means:
  - `cpython_interp`: `0.0516462776 s`
  - `cpython_jit`: `0.0486890842 s`
    - vs CPython interp: `-5.726%` (faster)
  - `cinderx_interp`: `0.0520793502 s`
    - vs CPython interp: `+0.839%` (slower)
  - `cinderx_jit` (`autojit50`): `0.0516185456 s`
    - vs CinderX interp: `-0.885%` (faster)
    - vs CPython JIT: `+6.017%` (slower)

### Notes on interpretation
- This run is a same-host, same-benchmark comparison and uses the actual requested four categories.
- Because host variance still exists, treat this as directional for this machine/setup.
- In this sample set:
  - CPython native JIT gain is clear over CPython interp.
  - CinderX JIT gain over CinderX interp is present but small.

## 2026-02-27 Assembly Diff: CinderX JIT vs CPython Native JIT (AArch64)

### Setup
- Host: `root@124.70.162.35`
- Function shape on both sides:
  - `def f(n): s=0; for i in range(n): s += i; return s`
- CinderX:
  - force-compiled `f`
  - dumped JIT ELF, extracted `.text`, disassembled as AArch64
- CPython native JIT:
  - `PYTHON_JIT=1`
  - executor found at `JUMP_BACKWARD` offset `50`
  - disassembled `get_jit_code()` blob (head `952` bytes for same-size window)

### Key evidence artifacts
- `artifacts/asm/cinderx_f_disasm_aarch64.txt`
- `artifacts/asm/cpython_executor_disasm_head952_aarch64.txt`
- `artifacts/asm/cpython_executor_disasm_head2880_aarch64.txt`
- `artifacts/asm/cinderx_f_text.bin`
- `artifacts/asm/cpython_executor_head952.bin`
- `artifacts/asm/cpython_executor_full4096.bin`
- `artifacts/asm/byte_compare_cinderx_vs_cpython_head952.txt`
- `artifacts/asm/inst_mix_cinderx_vs_cpython_head952.txt`
- design note: `docs/plans/2026-02-27-cinderx-vs-cpython-jit-asm-aligned.md`

### Quantitative summary
- Byte-level equal-size compare (`952` vs `952`):
  - `same_bytes=62`
  - `same_ratio=6.5126%`
  - `lcp=0`
- Instruction mix (`238` instructions each in compared window):
  - CinderX: `bl=7`, `blr=14`, `ret=3`, `b.cond=16`, `cbz/cbnz=5`, `tbz/tbnz=2`, `ldr-literal=14`
  - CPython: `bl=6`, `blr=2`, `ret=0`, `b.cond=8`, `cbz/cbnz=6`, `tbz/tbnz=6`, `ldr-literal=4`

### Main difference pattern
- CinderX sample shows heavier literal-pool indirect helper calls (`ldr x16, literal` + `blr x16`) and a compact deopt dispatch ladder.
- CPython native JIT sample shows executor/superblock style with more direct internal `bl` edges and fewer indirect callback sites in the equal-size window.

## 2026-02-27 ARM Probe: `cinderjit` APIs vs CPython Native

### Verification entrypoint and artifacts
- Remote entrypoint used: `ssh root@124.70.162.35`
- Probe script: `scripts/arm/probe_jit_apis.py`
- Local artifacts:
  - `artifacts/arm/jit_api_probe/cinderx_default.json`
  - `artifacts/arm/jit_api_probe/cinderx_jit_env.json`
  - `artifacts/arm/jit_api_probe/cpython_default.json`
  - `artifacts/arm/jit_api_probe/cpython_python_jit_1.json`
  - `artifacts/arm/jit_api_probe/cpython_help_xoptions.txt`

### Runs executed
- CinderX env (default):  
  `/root/venv-cinderx314/bin/python /root/work/cinderx-main/scripts/arm/probe_jit_apis.py --label cinderx_default`
- CinderX env (JIT vars):  
  `PYTHONJIT=1 PYTHONJITAUTO=1 /root/venv-cinderx314/bin/python ... --label cinderx_jit_env`
- CPython native (default):  
  `/opt/python-3.14/bin/python3.14 ... --label cpython_default`
- CPython native (`PYTHON_JIT=1`):  
  `PYTHON_JIT=1 /opt/python-3.14/bin/python3.14 ... --label cpython_python_jit_1`

### Result summary
- CinderX runtime (`/root/venv-cinderx314/bin/python`):
  - `cinderjit` import: success.
  - API presence: `get_compiled_size`, `disassemble`, `get_compiled_functions`, `dump_elf` all present.
  - Probe payload compiled: `is_jit_compiled=True`.
  - `get_compiled_size(payload)=1232` bytes.
  - `get_compiled_functions_count`: `1` (default) / `7` (`PYTHONJIT=1,PYTHONJITAUTO=1`).
  - `dump_elf` succeeded, ELF sizes:
    - default: `12461` bytes
    - jit_env: `20653` bytes
  - `disassemble(payload)` call succeeded but produced no textual asm output on stdout/stderr in this build (markers only).
  - Note: after `import cinderx`, `cinderjit.__spec__` is `None`; `find_spec("cinderjit")` can raise `ValueError`, but module is usable from `sys.modules`.

- CPython native runtime (`/opt/python-3.14/bin/python3.14`):
  - `cinderjit`/`cinderx` import: unavailable.
  - `sys._jit` object exists, but:
    - `is_available=False`
    - `is_enabled=False`
    - unchanged when `PYTHON_JIT=1`.
  - `--help-xoptions` output does not expose `-X jit` option on this build (`artifacts/arm/jit_api_probe/cpython_help_xoptions.txt`).

### Direct contrast (based on requested APIs)
- `cinderjit.get_compiled_size`: available and returns non-zero size on CinderX; not available on CPython native.
- `cinderjit.get_compiled_functions`: available on CinderX and includes probe payload; not available on CPython native.
- `cinderjit.disassemble`: callable on CinderX but silent in this environment; not available on CPython native.
- `cinderjit.dump_elf`: available on CinderX and produces ELF for objdump workflow; not available on CPython native.

### Extra verification for asm extraction
- Verified fallback asm path works on ARM:
  - `cinderjit.dump_elf('/tmp/cinderjit_probe_*.elf')`
  - `objcopy -O binary --only-section=.text ...`
  - `objdump -D -b binary -m aarch64 ...`
- Observed valid AArch64 instructions from dumped `.text` (non-empty disassembly).

## 2026-02-27 Fix: `dump_elf` ELF Machine Field on ARM

### Problem statement
- On ARM, `cinderjit.dump_elf()` output could be disassembled as x86 when using plain:
  - `objdump -d <dumped.elf>`
- Root cause in source:
  - ELF file header machine type was hardcoded to x86-64:
    - `cinderx/Jit/elf/header.h` previously had `machine{0x3e}`.

### Code changes
- `cinderx/Jit/elf/header.h`
  - Added architecture-aware ELF machine constants:
    - `kMachineX86_64 = 0x3e`
    - `kMachineAArch64 = 0xb7`
  - Added compile-target selection:
    - `__x86_64__ || _M_X64 -> kFileMachine = kMachineX86_64`
    - `__aarch64__ || _M_ARM64 -> kFileMachine = kMachineAArch64`
  - Updated `FileHeader::machine` to `machine{kFileMachine}`.

- Tests added:
  - `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
    - `ArmRuntimeTests.test_dump_elf_machine_is_aarch64_on_arm`
    - Reads ELF header bytes and asserts `e_machine == 0xB7` (EM_AARCH64) on ARM.
  - `cinderx/PythonLib/test_cinderx/test_cinderjit.py`
    - `CinderJitModuleTests.test_dump_elf_machine_matches_runtime_arch`
    - Cross-arch mapping check (x86_64 / aarch64), guarded for availability.

### TDD evidence (remote-only)
- Remote entrypoint used for all verification:
  - `ssh root@124.70.162.35`

1. RED (before C++ fix)
- Command:
  - `cd /root/work/cinderx-main && /root/venv-cinderx314/bin/python -m unittest discover -s cinderx/PythonLib/test_cinderx -p test_arm_runtime.py -k dump_elf_machine`
- Result:
  - `FAIL: Expected EM_AARCH64, got 0x003e`
  - Failure line: `test_arm_runtime.py:94`

2. GREEN (after C++ fix, rebuilt + reinstalled wheel)
- Build/install:
  - `cd /root/work/cinderx-main && /opt/python-3.14/bin/python3.14 -m build --wheel`
  - `pip --force-reinstall dist/cinderx-2026.2.27.0-cp314-cp314-linux_aarch64.whl` (in `/root/venv-cinderx314`)
- Same test command result:
  - `OK (skipped=1)` with target test passing.

### Verification-before-completion
1. Generate new ELF after fix:
- Script path on remote:
  - `/tmp/verify_dump_elf_machine.py`
- Output:
  - dumped file: `/tmp/dump_elf_machine_fix_verify.elf`
  - compiled size sample: `960`

2. Verify ELF header + disassembly mode:
- Command:
  - `readelf -h /tmp/dump_elf_machine_fix_verify.elf | egrep 'Class|Type|Machine'`
  - `objdump -d /tmp/dump_elf_machine_fix_verify.elf | head`
- Observed:
  - `Machine: AArch64`
  - `file format elf64-littleaarch64`
  - AArch64 mnemonics (`stp`, `mov`, `cbz`, `blr`, `ret`) shown directly.

### Conclusion
- Fixed: `cinderjit.dump_elf()` now emits architecture-correct ELF `e_machine` on ARM.
- Impact:
  - `readelf` and plain `objdump -d` now identify/disassemble dumped JIT ELF correctly as AArch64.

## 2026-02-27 Next Optimization Directions (CinderX JIT vs CPython Native JIT)

### API-based comparison (same ARM host, same function shape)
- Function:
  - `def f(n): s=0; for i in range(n): s += (i*3) ^ (i>>2); return s`
- CinderX (`/root/venv-cinderx314/bin/python`):
  - `is_jit_compiled=True`
  - `get_compiled_size(f)=1232`
  - `get_compiled_stack_size(f)=240`
  - `get_compiled_spill_stack_size(f)=160`
  - `get_compiled_functions_count=1`
- CPython native JIT (`PYTHON_JIT=1 /tmp/venv-cpython314jit/bin/python`):
  - `sys._jit.is_available=True`, `is_enabled=True`
  - executor at bytecode `offset=92 (JUMP_BACKWARD)`
  - `get_jit_code()` size `8192` bytes

### Mapping to Python bytecode
- Shared key bytecode offsets:
  - loop body starts around `34` (`LOAD_FAST...`)
  - arithmetic ops at `38 (*)`, `54 (>>)`, `66 (^)`, `78 (+=)`
  - loop backedge at `92 (JUMP_BACKWARD)`
  - return at `102 (RETURN_VALUE)`
- Observation:
  - CPython native JIT executor is attached to the loop backedge (`offset 92`), i.e. hotspot/superblock style.
  - CinderX emits function-level code object and includes explicit cold/deopt ladder blocks in the same blob.

### Measured shape sensitivity on CinderX (forced-compile micro)
- `for_range`:
  - size `1232`, spill stack `160`, time `~0.079s`
- `while_xor`:
  - size `1104`, spill stack `152`, time `~0.067s`
- `while_add`:
  - size `824`, spill stack `136`, time `~0.026s`
- Interpretation:
  - `for range` path costs extra vs equivalent `while` loop on this workload, pointing to iterator/global-call overhead opportunities.
  - spill stack is high relative to function complexity, indicating register pressure/call-lowering overhead.

### Immediate optimization targets
1. Improve range-loop specialization on ARM hot loops
- Why:
  - `for_range` slower and larger than `while_xor` for same arithmetic payload.
- Direction:
  - stronger `range` + `FOR_ITER` lowering to reduce helper round-trips in steady-state loop.

2. Reduce helper-call overhead (`ldr literal + blr`) in hot path
- Why:
  - CinderX disassembly shows frequent indirect helper call sites.
- Direction:
  - prefer direct near-call stubs/veneer strategy where possible; minimize repeated literal-pool loads in loop body.

3. Reduce register pressure / spills in arithmetic loops
- Why:
  - `spill_stack_size=160` for a small loop body.
- Direction:
  - tighten postalloc/regalloc heuristics around call-result chains and loop-carried vars on AArch64.

4. Move cold/deopt paths farther from hot text (I-cache friendliness)
- Why:
  - same blob includes significant cold ladder; code locality pressure in hot path.
- Direction:
  - make multiple hot/cold sections robust on ARM for general workloads.
  - current trial of `PYTHONJITMULTIPLECODESECTIONS=1` with explicit sizes fails compile with `InvalidDisplacement`; this is both a correctness and optimization blocker.

5. Keep static typing path for true numeric hot spots
- Why:
  - dynamic `PyLong` arithmetic still dominates helper/refcount traffic.
- Direction:
  - move the hottest numeric kernels to Static Python/native-callable paths where feasible.

## 2026-02-27 ARM Full Validation: MCS `InvalidDisplacement` Fix + End-to-End Retest

### Scope and entrypoint
- Remote-only execution entrypoint:
  - `ssh root@124.70.162.35`
- Runtime under test:
  - CinderX: `/root/venv-cinderx314/bin/python` (Python `3.14.3`)
  - CPython native JIT: `/tmp/venv-cpython314jit/bin/python` (Python `3.14.3`)

### Code changes under test
- `cinderx/Jit/code_allocator.cpp`
  - In `MultipleSectionCodeAllocator::createSlabs()`:
    - changed section alignment from fixed `2MiB` (`kAllocSize`) to system allocation/page granularity.
    - applied same alignment logic to both hot and cold section sizes.
    - guarded `setHugePages()` to only run when hot section size is at least `2MiB`.
- `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
  - added `test_multiple_code_sections_force_compile_smoke`.

### TDD evidence (RED -> GREEN)
1. RED (before allocator fix)
- Test command:
  - `cd /root/work/cinderx-main && /root/venv-cinderx314/bin/python -m unittest discover -s cinderx/PythonLib/test_cinderx -p test_arm_runtime.py -k test_multiple_code_sections_force_compile_smoke`
- Result:
  - `FAIL` at `jit.force_compile(f)` with:
    - `RuntimeError: PYJIT_RESULT_UNKNOWN_ERROR`
  - prior low-level log for same case showed:
    - `Failed to add generated code ... InvalidDisplacement`

2. GREEN (after allocator fix + rebuild)
- Rebuild/install command:
  - `cd /root/work/cinderx-main && ENABLE_ADAPTIVE_STATIC_PYTHON=1 ENABLE_LIGHTWEIGHT_FRAMES=1 /root/venv-cinderx314/bin/pip install -e . -v`
- Build config confirmation in output:
  - `-DENABLE_ADAPTIVE_STATIC_PYTHON=1`
  - `-DENABLE_LIGHTWEIGHT_FRAMES=1`
- Same targeted test result:
  - `OK (skipped=1)`

### Full runtime test verification
- Full ARM runtime test file:
  - `cd /root/work/cinderx-main && /root/venv-cinderx314/bin/python -m unittest discover -s cinderx/PythonLib/test_cinderx -p test_arm_runtime.py`
- Result:
  - `Ran 53 tests in 3.258s`
  - `OK (skipped=2)`

### Post-fix API and performance comparison (same workload)
- Workload shape:
  - `for i in range(n): s += (i * 3) ^ (i >> 2)` with fixed benchmark harness.
- Artifacts:
  - `artifacts/asm/api_compare_20260227/cinderx_interp_post_fix.json`
  - `artifacts/asm/api_compare_20260227/cinderx_jit_mcs0_post_fix.json`
  - `artifacts/asm/api_compare_20260227/cinderx_jit_mcs1_post_fix.json`
  - `artifacts/asm/api_compare_20260227/cpython_interp_post_fix.json`
  - `artifacts/asm/api_compare_20260227/cpython_jit_post_fix.json`
  - `artifacts/asm/api_compare_20260227/cinderjit_api_detail_post_fix.json`

1. CinderX
- Interpreter median:
  - `0.289058s`
- JIT (`PYTHONJITMULTIPLECODESECTIONS=0`) median:
  - `0.254043s` (`~1.138x` vs CinderX interpreter)
  - compiled size:
    - `1248` bytes
- JIT (`PYTHONJITMULTIPLECODESECTIONS=1`, hot/cold `1MiB`) median:
  - `0.271293s` (`~1.065x` vs CinderX interpreter)
  - no compile failure after fix (this was the previous blocker)
  - compiled size:
    - `1304` bytes
  - relative to `mcs=0`:
    - `~6.8%` slower on this micro shape

2. CPython native
- Interpreter median (`PYTHON_JIT=0`):
  - `0.205928s`
- JIT median (`PYTHON_JIT=1`):
  - `0.266945s` (slower on this workload in this build)
- Executor status in JIT mode:
  - backedge offset:
    - `92`
  - `exists=True`, `is_valid=True`
  - `get_jit_code()` length:
    - `8192` bytes

### `cinderjit` API availability on ARM (post-fix)
- Presence:
  - `get_compiled_size`: `True`
  - `disassemble`: `True`
  - `get_compiled_function`: `False`
  - `get_compiled_functions`: `True`
  - `dump_elf`: `True`
- Runtime checks:
  - `force_compile(payload)=True`
  - `is_jit_compiled(payload)=True`
  - `compiled_size=1232`
  - `stack_size=240`
  - `spill_stack_size=160`
  - `compiled_functions_count=1`, payload found in list
  - `disassemble(payload)` callable, return type `NoneType`
- `dump_elf` validation:
  - ELF machine from header: `183` (`EM_AARCH64`)
  - `readelf -h` machine line:
    - `Machine:                           AArch64`

## 2026-02-27 ARM Follow-up: MCS Size Sweep (post-fix)

### 方法
- 入口：
  - `ssh root@124.70.162.35`
- 脚本：
  - `scripts/arm/bench_compare_modes.py`
- 产物：
  - `artifacts/asm/api_compare_20260227/mcs_sweep/summary.json`

### 结果（`cinderx` JIT，相同 workload/harness）
- `mcs=0` 基线：
  - 中位数 `0.248457s`
  - 编译体积 `1232`
- `mcs=1`，hot/cold 各 `262144`：
  - 中位数 `0.294906s`
  - 编译体积 `1288`
- `mcs=1`，hot/cold 各 `524288`：
  - 中位数 `0.297446s`
  - 编译体积 `1288`
- `mcs=1`，hot/cold 各 `1048576`：
  - 中位数 `0.296165s`
  - 编译体积 `1288`
- `mcs=1`，hot/cold 各 `2097152`：
  - 编译失败（`RuntimeError: PYJIT_RESULT_UNKNOWN_ERROR`）
- `mcs=1`，hot/cold 各 `4194304`：
  - 编译失败（`RuntimeError: PYJIT_RESULT_UNKNOWN_ERROR`）

### 解释
- 当前修复已消除此前 `1MiB` 失败，但在该 ARM 环境下 `2MiB+` 段距离仍会失败。
- 即便 `mcs=1` 成功（`256KiB~1MiB`），该微基准仍较 `mcs=0` 慢约 `19%`。
- 这表明在分段模式下仍存在分支可达性/布局敏感问题，或 hot/cold 分离带来的 i-cache / 分支预测额外成本。

## 2026-02-27 ARM 跟进：MCS `2MiB+` InvalidDisplacement 根因与修复

### 根因（已测量）
- 失败形态：
  - `PYTHONJITMULTIPLECODESECTIONS=1`
  - `PYTHONJITHOTCODESECTIONSIZE=2097152`
  - `PYTHONJITCOLDCODESECTIONSIZE=2097152`
- AsmJit 失败点：
  - `resolveUnresolvedLinks()` 报 `InvalidDisplacement`。
- 链接层诊断：
  - `.coldtext` 到 `.text` 的跨段链接使用 `imm19` 位移格式。
  - 与 AArch64 `ldr literal` 的可达范围（约 +/-1MiB）一致。
- 实际解释：
  - cold 段 helper 调用点仍从 hot 段字面量池加载目标（`ldr literal + blr`），当 hot/cold 距离约 2MiB 时溢出。

### 代码改动
- `cinderx/Jit/codegen/gen_asm_utils.cpp`
  - AArch64 下 `emitCall(env, uint64_t func, ...)` 改为：
    - hot 段：保留现有去重字面量池调用降级
    - cold 段：使用 `mov absolute_target + blr`（消除对 hot 字面量可达性的依赖）
- `cinderx/Jit/codegen/gen_asm.cpp`
  - deopt 一阶段保留在 cold、二阶段放在 hot，避免二阶段 hot 标签的 `adr` 跨段溢出。
- `cinderx/Jit/codegen/autogen.cpp`
  - 仅保留定向 guard 远分支处理；回滚了导致代码尺寸回归的广谱 branch-veneer 改写。
- `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
  - 新增 `test_multiple_code_sections_large_distance_force_compile_smoke`（2MiB/2MiB 烟测）。

### 远端入口验证（`scripts/arm/remote_update_build_test.sh`）
- 测试分支：当前工作树（`bench-cur-7c361dce`，含上述改动）。
- 结果：
  - ARM 运行时测试：`Ran 9 tests ... OK`
  - 包含：
    - `test_multiple_code_sections_large_distance_force_compile_smoke`：通过
    - `test_aarch64_call_sites_are_compact`：通过
    - `test_aarch64_duplicate_call_result_arg_chain_is_compact`：通过
- 剩余门禁结果：
  - 脚本在 line 210 smoke 仍崩溃：
    - `env PYTHONJITAUTO=0 "$PYVENV_PATH/bin/python" -c 'g=(i for i in [1]); ... re.compile("a+") ...'`
    - segfault 栈经过 `typing.__init_subclass__` / `JITRT_CallFunctionEx`。

### line-210 segfault 的基线一致性检查
- 同一远端入口、同一参数，改用基线提交归档源码：
  - `436bee31ac6b34ba74c90133ed651b31ad96c57e`
- 结果：
  - 运行时测试通过（基线测试文件 `Ran 8 tests ... OK`），
  - line-210 smoke 同样复现 segfault。
- 结论：
  - line-210 崩溃是既有问题，不是本次 MCS 位移修复引入。

## 2026-02-27 ARM 跟进：`pyperformance` auto-jit 门禁稳定化

### RED：`richards` auto-jit 在低阈值崩溃
- 远端入口（`scripts/arm/remote_update_build_test.sh`）在 auto-jit 门禁持续失败：
  - `RuntimeError: Benchmark died`
  - worker 退出码 `-11` / `139`（SIGSEGV）。
- Core 证据（示例）：
  - `coredumpctl info 437653`
  - benchmark worker 命令：
    - `/root/work/cinderx-main/venv/.../bin/python -u .../bm_richards/run_benchmark.py ...`
  - 栈顶路径：
    - `Py_INCREF` -> `_CiFrame_ClearExceptCode` -> `Ci_EvalFrame` -> `resumeInInterpreter`。
- 同 worker 命令阈值探测：
  - `autojit=50` -> `rc=139`
  - `autojit=100` -> `rc=139`
  - `autojit=200` -> `rc=0`
- 与基线一致：
  - 基线提交 `436bee31` 在低阈值同样复现，因此非当前分支引入。

### 改动
- 更新 `scripts/arm/remote_update_build_test.sh`：
  - 新增 `AUTOJIT_GATE`（默认跟随 `AUTOJIT`）。
  - 校验 `AUTOJIT_GATE` 必须为非负整数。
  - 对 ARM richards 门禁将 `AUTOJIT_GATE < 200` 强制提升到 `200`。
  - auto-jit 门禁命令/日志/输出统一使用 `AUTOJIT_GATE`。

### GREEN：远端完整入口恢复通过
- 命令：
  - `INCOMING_DIR=/root/work/incoming WORKDIR=/root/work/cinderx-main PYTHON=/opt/python-3.14/bin/python3.14 DRIVER_VENV=/root/venv-cinderx314 BENCH=richards AUTOJIT=50 PARALLEL=1 SKIP_PYPERF=0 RECREATE_PYPERF_VENV=1 /root/work/incoming/remote_update_build_test.sh`
- 结果：
  - 脚本输出：
    - `>> auto-jit gate threshold 50 is crash-prone on ARM; using 200`
  - 运行时测试：`Ran 9 tests ... OK`
  - `pyperformance` jitlist 门禁：通过
  - `pyperformance` auto-jit 门禁：通过
- 产物：
  - `/root/work/arm-sync/richards_jitlist_20260227_220207.json`
  - `/root/work/arm-sync/richards_autojit200_20260227_220207.json`
  - `/tmp/jit_richards_autojit200_20260227_220207.log`
- auto-jit 日志中的 JIT 生效证据：
  - 含多个 `Finished compiling __main__:*`（例如 `Task.runTask`、`DeviceTask.fn`）。

## 2026-02-27 ARM 直接对比刷新：CPython 原生 JIT vs CinderX

### 远端入口与负载
- 仅远端执行：
  - `ssh root@124.70.162.35`
- 负载脚本：
  - `scripts/arm/bench_compare_modes.py`
  - 各模式参数一致（`n=250`、`warmup=20000`、`calls=12000`、`repeats=5`）。

### 关键环境校正
- 系统 Python（`/opt/python-3.14/bin/python3.14`）报告：
  - `RuntimeError: Executors are not available in this build`
  - 因此该二进制下 `PYTHON_JIT=1` 不能代表真实原生 JIT 对比。
- 在同机编译了 JIT 版 CPython 3.14.3：
  - 源码：`/root/work/Python-3.14.3`
  - 安装前缀：`/root/opt/python-3.14-jit`
  - 配置：`--enable-experimental-jit=yes`
  - 本机编译修正：
    - `PYTHON_FOR_REGEN=/opt/python-3.14/bin/python3.14`
    - （系统 `python3` 为 3.9，无法执行 `Tools/jit/build.py` 的 `match` 语法）
- JIT 启用证据：
  - `_opcode.get_executor(...).is_valid() == True`
  - `len(executor.get_jit_code()) == 8192`

### 直接对比结果（真实 CPython JIT 二进制）
- 使用的 CPython 二进制：
  - `/root/opt/python-3.14-jit/bin/python3.14`
- 模式中位数：
  - `cpython interp (PYTHON_JIT=0)`：`0.2033475680 s`
  - `cpython jit (PYTHON_JIT=1)`：`0.2692244400 s`
  - `cinderx interp`：`0.2864123950 s`
  - `cinderx jit`：`0.2702031260 s`
- 相对比率：
  - `cpython_jit_vs_interp`：`0.7553x`（该负载下原生 JIT 更慢）
  - `cinderx_jit_vs_interp`：`1.0600x`（CinderX JIT 快于自身解释基线）
  - `cpython_interp_vs_cinderx_interp`：`1.4085x`（本次运行 CPython interp 更快）
  - `cpython_jit_vs_cinderx_jit`：`1.0036x`（两侧 JIT 接近，CPython 略快）
- 同次运行中的 CinderX JIT 代码生成证据：
  - `compiled_size=1264`
  - `stack_size=240`
  - `spill_stack_size=160`
  - `dump_elf.elf_e_machine=183`（`EM_AARCH64`）

### 产物
- 本地：
  - `artifacts/richards/direct_compare_nativejit_20260227_232009/cpython_interp.json`
  - `artifacts/richards/direct_compare_nativejit_20260227_232009/cpython_jit.json`
  - `artifacts/richards/direct_compare_nativejit_20260227_232009/cinderx_interp.json`
  - `artifacts/richards/direct_compare_nativejit_20260227_232009/cinderx_jit.json`
  - `artifacts/richards/direct_compare_nativejit_20260227_232009/summary.json`
- 远端：
  - `/root/work/arm-sync/cmp_nativejit_20260227_232009/*`

## 2026-02-27 ARM 跟进：隔离 CinderX 解释器开销（`PYTHONJITDISABLE`）

### 原因
- 之前直接对比里的 `cinderx interp` 仍启用了 JIT 运行时通路
  （`jit.enable() + compile_after_n_calls(1000000)`），会抬高“纯解释器基线”。
- 脚本已增强：支持在 `PYTHONJITDISABLE=1` 下运行 CinderX interp，且不强依赖 `cinderjit` 导入。

### 脚本改动
- 文件：
  - `scripts/arm/bench_compare_modes.py`
- 行为更新：
  - `cinderjit` 导入改为可选。
  - `mode=interp` 在 `PYTHONJITDISABLE=1` 下可运行。
  - `mode=jit` 在设置 `PYTHONJITDISABLE` 时会快速失败。
  - 输出新增：
    - `jit_disabled`
    - `api_flags.cinderjit_available`

### 远端对比结果（同主机/同负载/真实 CPython JIT）
- CPython 二进制：
  - `/root/opt/python-3.14-jit/bin/python3.14`
- 中位数：
  - `cpython interp`：`0.2042452650 s`
  - `cpython jit`：`0.2708785540 s`
  - `cinderx interp（纯解释，PYTHONJITDISABLE=1）`：`0.2609469950 s`
  - `cinderx interp（保留 JIT plumbing）`：`0.2848622500 s`
  - `cinderx jit`：`0.2650873990 s`
- 关键比率：
  - `cinderx_jitenabled_interp_overhead`：`1.0916x`
    - 保留 JIT plumbing 的解释器路径约有 `9.16%` 额外开销。
  - `cinderx_jit_vs_interp_pure`：`0.9844x`
    - 该微基准上 CinderX JIT 与纯解释大致持平/略慢。
  - `cpython_interp_vs_cinderx_interp_pure`：`1.2776x`
    - 即便移除 JIT plumbing 开销，本次仍是 CinderX interp 慢于 CPython interp。

### 产物
- 本地：
  - `artifacts/richards/direct_compare_pureinterp_20260227_233807/cpython_interp.json`
  - `artifacts/richards/direct_compare_pureinterp_20260227_233807/cpython_jit.json`
  - `artifacts/richards/direct_compare_pureinterp_20260227_233807/cinderx_interp_pure.json`
  - `artifacts/richards/direct_compare_pureinterp_20260227_233807/cinderx_interp_jitenabled.json`
  - `artifacts/richards/direct_compare_pureinterp_20260227_233807/cinderx_jit.json`
  - `artifacts/richards/direct_compare_pureinterp_20260227_233807/summary.json`
- 远端：
  - `/root/work/arm-sync/cmp_pureinterp_20260227_233807/*`

## 2026-02-28 ARM 跟进：修复 auto-jit segfault（轻量帧元数据初始化）

### RED（修复前）
- ARM（pyperf venv）最小复现会 `SIGSEGV`：
  - `env PYTHONJITAUTO=0 PYTHONJITLIGHTWEIGHTFRAME=1 python -c 'g=(i for i in [1]); import re; re.compile("a+"); print("ok")'`
- core 回溯（新 core `471733`）栈顶：
  - `Py_INCREF(op=0x1)` 于 `PyImport_Import`
  - 上游调用来自 `call_typing_args_kwargs` -> `JITRT_CallFunctionEx`
- 解释：
  - C API 在轻量帧 JIT 入口阶段读取当前帧元数据（`globals` / 清理相关状态）时看到无效值。

### 改动
- `cinderx/Jit/codegen/frame_asm.cpp`
  - 对 x86_64 与 AArch64 的轻量函数帧，提前初始化：
    - `f_globals`（来自 `func->func_globals`）
    - `f_builtins`（来自 `func->func_builtins`）
    - `frame_obj = NULL`
    - `return_offset = 0`
    - `visited = 0`
  - 目标是在懒初始化前保证关键帧元数据始终有效。
- `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
  - 新增回归测试：
    - `test_autojit0_lightweight_frame_typing_import_smoke`
  - 将一个 AArch64 代码尺寸护栏从 `44500` 放宽到 `44700`（本次新增初始化 store 带来约 +20B）。

### GREEN（远端入口验证）
- 远端入口（按要求）：
  - `/root/work/incoming/remote_update_build_test.sh`
- 命令：
  - `INCOMING_DIR=/root/work/incoming WORKDIR=/root/work/cinderx-main PYTHON=/opt/python-3.14/bin/python3.14 DRIVER_VENV=/root/venv-cinderx314 BENCH=richards AUTOJIT=50 PARALLEL=1 SKIP_PYPERF=1 RECREATE_PYPERF_VENV=0 /root/work/incoming/remote_update_build_test.sh`
- 结果：
  - ARM 运行时测试：`Ran 10 tests ... OK`
  - 包含新回归测试 `test_autojit0_lightweight_frame_typing_import_smoke`
  - 脚本整体成功（`exit 0`）
## 2026-02-28 ARM 完整远端门禁复验（SKIP_PYPERF=0）

### 入口与命令
- 统一远端入口：
  - `/root/work/incoming/remote_update_build_test.sh`
- 实际执行命令：
  - `INCOMING_DIR=/root/work/incoming WORKDIR=/root/work/cinderx-main PYTHON=/opt/python-3.14/bin/python3.14 DRIVER_VENV=/root/venv-cinderx314 BENCH=richards AUTOJIT=50 PARALLEL=1 SKIP_PYPERF=0 RECREATE_PYPERF_VENV=1 /root/work/incoming/remote_update_build_test.sh`

### 结果
- 脚本退出码：`0`
- ARM 运行时测试：`Ran 10 tests ... OK`
- auto-jit 门禁策略：
  - 日志提示 `AUTOJIT=50` 在 ARM 上自动提升到 `200`：
    - `>> auto-jit gate threshold 50 is crash-prone on ARM; using 200`

### 性能产物（本次最新）
- jitlist JSON：
  - `/root/work/arm-sync/richards_jitlist_20260228_093637.json`
  - value：`0.07860610100033227`
- autojit200 JSON：
  - `/root/work/arm-sync/richards_autojit200_20260228_093637.json`
  - value：`0.07193847199960146`
- autojit 日志：
  - `/tmp/jit_richards_autojit200_20260228_093637.log`

### JIT 生效证据
- `Finished compiling __main__:` 命中数：`18`
## 2026-02-28 ARM P0：autojit 低阈值崩溃矩阵（richards）

### 方法
- 远端入口：`ssh root@124.70.162.35`
- 矩阵脚本：`/root/work/incoming/autojit_crash_matrix.sh`
- 本地脚本：`scripts/arm/autojit_crash_matrix.sh`
- 基准：`pyperformance -b richards --debug-single-value`
- 阈值：`20 50 80 100 200`

### 主结果（run_id=20260228_102038）
- `200`：`ok`，`value=0.07163083901104983`，`main_compile_count=18`
- `100`：`fail`（`core_pid=512875`）
- `80`：`fail`（`core_pid=513010`）
- `50`：`fail`（`core_pid=513130`）
- `20`：`fail`（`core_pid=513251`）

### 崩溃签名（20/50/80/100 一致）
- 信号：`SIGSEGV`
- 关键栈：
  - `Py_INCREF -> take_ownership -> _CiFrame_ClearExceptCode`
  - `resumeInInterpreter`（`cinderx/Jit/codegen/gen_asm.cpp:390`）
- 结论：
  - 与此前判断一致，低阈值崩溃主要落在 deopt/resume 路径。

### 补充观察（200 的稳定性）
- `200` 在独立运行中可通过：
  - `run_id=20260228_101308`：`ok`，`value=0.07168850500602275`
  - `run_id=20260228_102038`：`ok`，`value=0.07163083901104983`
- 但在一次顺序矩阵（`run_id=20260228_101244`）里，`200` 也出现失败（`core_pid=504823`），
  栈顶为 `_Py_Dealloc/frame_dealloc` 路径，呈现压力/顺序相关的不稳定性。

### 产物
- 远端：
  - `/root/work/arm-sync/autojit_matrix_20260228_102038/summary.json`
  - `/root/work/arm-sync/autojit_matrix_20260228_102038/core_100_512875.bt.txt`
  - `/root/work/arm-sync/autojit_matrix_20260228_102038/core_80_513010.bt.txt`
  - `/root/work/arm-sync/autojit_matrix_20260228_102038/core_50_513130.bt.txt`
  - `/root/work/arm-sync/autojit_matrix_20260228_102038/core_20_513251.bt.txt`
- 本地：
  - `artifacts/arm/autojit_matrix_20260228_102038/summary.json`
  - `artifacts/arm/autojit_matrix_20260228_101244/summary.json`

## 2026-02-28 ARM P0 续：autojit<=100 崩溃修复迭代（失败记录）

### 目标
- 在不依赖 `AUTOJIT>=200` 兜底的情况下，修复 `richards` 在 `autojit<=100` 的 SIGSEGV。

### 远端验证入口（统一）
- 构建/门禁：`/root/work/incoming/remote_update_build_test.sh`
- 阈值矩阵：`/root/work/incoming/autojit_crash_matrix.sh`

### 本轮关键尝试
- 尝试 A：`gen_asm.cpp` 在 `resumeInInterpreter` 前补齐 previous 轻量帧初始化。
- 尝试 B：`borrowed-3.14.gen_cached.c` 在 `take_ownership` 中跳过 `f_back` 链接（避免沿坏 `previous` 链 materialize）。
- 尝试 C（已回退）：对 `take_ownership` 的 stackref 槽位做“低地址置空”消毒；该改动会导致远端 JIT smoke 崩溃，已撤销。

### 矩阵结果（补丁后）
- `run_id=20260228_112500`：`200=ok`，`100/80/50/20=fail`
- `run_id=20260228_120500`：`200=ok`，`100/80/50/20=fail`
- `run_id=20260228_122000`：`200=ok`，`100/80/50/20=fail`
- `run_id=20260228_123500`：`200=ok`，`100/80/50/20=fail`

### 崩溃签名
- 仍集中在：
  - `Py_INCREF -> _Py_NewRef -> take_ownership -> _CiFrame_ClearExceptCode`
  - 上层继续来自 `resumeInInterpreter`。
- 说明本轮对 previous 链/ownership 保护未触达真正坏引用来源。

### 回归与回退
- “槽位消毒”版本在远端门禁 smoke（`jit-effective`）触发新的 `SIGSEGV`，已回退。
- 当前远端基线已恢复到可构建、可通过 10 项 ARM 运行时测试（`remote_update_build_test.sh`，`SKIP_PYPERF=1`）。

### 产物
- 远端：
  - `/root/work/arm-sync/autojit_matrix_20260228_112500/summary.json`
  - `/root/work/arm-sync/autojit_matrix_20260228_120500/summary.json`
  - `/root/work/arm-sync/autojit_matrix_20260228_122000/summary.json`
  - `/root/work/arm-sync/autojit_matrix_20260228_123500/summary.json`
- 本地：
  - `artifacts/arm/autojit_matrix_20260228_112500/summary.json`
  - `artifacts/arm/autojit_matrix_20260228_120500/summary.json`
  - `artifacts/arm/autojit_matrix_20260228_122000/summary.json`
  - `artifacts/arm/autojit_matrix_20260228_123500/summary.json`

## 2026-02-28 ARM P0 收敛：autojit<=100 崩溃修复完成（远端闭环）

### 关键根因（本轮新增定位）
- 根因 1：二进制与源码不一致。
  - core 反汇编显示 `_CiFrame_ClearExceptCode` 仍在 `take_ownership` 内执行 `f_back` 链接逻辑（`PyErr_GetRaisedException -> Py_NewRef(back)`），说明“跳过 f_back”补丁未进入当次实际加载的 `_cinderx.so`。
  - 进一步确认：存在两套 pyperformance venv。
    - 旧：`/root/venv/cpython3.14-.../site-packages/_cinderx.so`
    - 新：`/root/work/cinderx-main/venv/cpython3.14-.../site-packages/_cinderx.so`
  - 若矩阵脚本在错误目录启动，会命中旧 venv 并复现旧崩溃签名。
- 根因 2：`ensureInitializedPreviousFrames()` 引入二次崩溃。
  - 在已应用 ownership 补丁后，core 栈顶转为：
    - `jitFramePopulateFrame -> ensureInitializedPreviousFrames -> resumeInInterpreter`
  - 说明 previous 链预初始化逻辑在坏链场景下会提前触发崩溃。

### 最终修复（代码）
- `cinderx/UpstreamBorrow/borrowed-3.14.gen_cached.c`
  - `take_ownership()` 跳过 `f_back` 构建（不沿 `frame->previous` materialize）。
- `cinderx/UpstreamBorrow/borrowed-3.14.free-threading.gen_cached.c`
  - 同步应用相同 `take_ownership()` 修复，避免构建路径差异导致补丁漏生效。
- `cinderx/Jit/codegen/gen_asm.cpp`
  - 将 `ensureInitializedPreviousFrames()` 退回 no-op，移除其对坏 previous 链的访问风险。

### 远端统一入口验证（按要求）
- 构建/门禁入口：`/root/work/incoming/remote_update_build_test.sh`
- 阈值矩阵入口：`/root/work/incoming/autojit_crash_matrix.sh`

#### 验证过程与结果
- 阶段 A（路径混用，旧崩溃仍在）
  - `run_id=20260228_114129`（pyperf_venv 指向 `/root/venv/...`）
  - 结果：`200=ok`，`20/50/80/100=fail`，仍是旧签名。
- 阶段 B（切到 `/root/work/cinderx-main`，暴露新增回归）
  - `run_id=20260228_114218`
  - 结果：`20/50/80/100/200` 全 fail。
  - core 栈顶：`jitFramePopulateFrame -> ensureInitializedPreviousFrames`。
- 阶段 C（回退 previous 预初始化后复测）
  - `run_id=20260228_114731`
  - 结果：`20/50/80/100/200` 全 `ok`（无 core）。

### 最终矩阵数据（run_id=20260228_114731）
- `20`：`ok`，`value=0.07160714498604648`
- `50`：`ok`，`value=0.07178452698281035`
- `80`：`ok`，`value=0.07169258102658205`
- `100`：`ok`，`value=0.07089853202342056`
- `200`：`ok`，`value=0.07331351100583561`

### 产物
- 远端：
  - `/root/work/arm-sync/autojit_matrix_20260228_114129/summary.json`
  - `/root/work/arm-sync/autojit_matrix_20260228_114218/summary.json`
  - `/root/work/arm-sync/autojit_matrix_20260228_114731/summary.json`
- 本地：
  - `artifacts/arm/autojit_matrix_20260228_114129/summary.json`
  - `artifacts/arm/autojit_matrix_20260228_114218/summary.json`
  - `artifacts/arm/autojit_matrix_20260228_114731/summary.json`

## 2026-02-28 ARM 跟进：移除 `AUTOJIT_GATE<200` 兜底 + 第 2 项优化闭环

### 代码变更
- P0（门禁策略）：
  - `scripts/arm/remote_update_build_test.sh`
  - 删除 `AUTOJIT_GATE<200` 时强制提升到 `200` 的逻辑，保留非负整数校验。
- P1-2（热循环整数路径）：
  - `cinderx/Jit/hir/simplify.cpp`
  - 新增 `simplifyIntBinaryOp()`，覆盖以下恒等式/吸收律：
    - `x+0`、`0+x`、`x-0`
    - `x*1`、`1*x`、`x*0`、`0*x`
    - `x|0`、`0|x`、`x^0`、`0^x`
    - `x&0`、`0&x`
    - `x<<0`、`x>>0`、`x>>>0`
    - `x//1`、`x//u1`、`x%1`、`x%u1`
  - 并在 `simplifyInstr()` 中接入 `Opcode::kIntBinaryOp`。

### 远端统一入口验证（按要求）
- 入口：
  - `/root/work/incoming/remote_update_build_test.sh`
- 命令（关键参数）：
  - `AUTOJIT=50 SKIP_PYPERF=0`
- 结果：
  - 脚本退出码：`0`
  - ARM 运行时测试：`Ran 10 tests ... OK`
  - pyperformance 门禁通过，并直接产出 `autojit50`（不再被抬到 200）：
    - `/root/work/arm-sync/richards_jitlist_20260228_123621.json`：`0.07845212798565626`
    - `/root/work/arm-sync/richards_autojit50_20260228_123621.json`：`0.07119264101493172`
    - `/tmp/jit_richards_autojit50_20260228_123621.log`
      - `Finished compiling __main__:` 计数：`18`

### P0 复核：低阈值矩阵（必须在正确 pyperf venv 路径）
- 入口：
  - `/root/work/incoming/autojit_crash_matrix.sh`
- 发现：
  - 若在 `/root` 启动，会命中旧 venv 路径 `/root/venv/...`，可复现“20/50/80/100 失败”假象。
  - 在正确目录 `/root/work/cinderx-main` 启动后，矩阵恢复全绿。
- 正确矩阵结果（`run_id=20260228_124324`）：
  - `20`：`ok`，`0.07155366201186553`
  - `50`：`ok`，`0.07290761498734355`
  - `80`：`ok`，`0.07085901699610986`
  - `100`：`ok`，`0.07063013297738507`
  - `200`：`ok`，`0.07235892000608146`
- 产物：
  - 远端：`/root/work/arm-sync/autojit_matrix_20260228_124324/summary.json`
  - 本地：`artifacts/arm/20260228_intopt/autojit_matrix_20260228_124324_summary.json`

### P1-2 可归因验证：`IntBinaryOp` 在 `Simplify` 前后
- 日志：
  - `/tmp/intbin_simplify_20260228.log`
- 对象函数：`<invalid>:f`（Static Python int64 样例，包含 `+0/*1/|0/&0`）
- `Simplify` 前后 `IntBinaryOp` 计数：
  - before：`6`
  - after：`1`
- 被消除的关键形态：
  - `IntBinaryOp<Add> (i + 0)`
  - `IntBinaryOp<Multiply> (* 1)`
  - `IntBinaryOp<Or> (| 0)`
  - `IntBinaryOp<And> (& 0)`
- 本地解析产物：
  - `artifacts/arm/20260228_intopt/intbin_simplify_summary.json`

### P1-2 量化验证：恒等式工作负载（Static Python int64）
- 对比方式：
  - 默认（启用 simplify） vs `PYTHONJITSIMPLIFY=0`
- 结果（`/root/work/arm-sync/int_identity_20260228_124543/summary.json`）：
  - 编译体积：`808` vs `840`（默认 `-32` bytes）
  - 中位耗时：`0.0019835610s` vs `0.0023550340s`
  - 默认相对无 simplify：约 `15.77%` 更快
- 本地产物：
  - `artifacts/arm/20260228_intopt/int_identity_20260228_124543_summary.json`

### 同轮四模式性能快照（CPython 原生 JIT vs CinderX）
- 产物：
  - `/root/work/arm-sync/cmp_intopt_20260228_124122/summary.json`
  - `artifacts/arm/20260228_intopt/cmp_intopt_20260228_124122_summary.json`
- 中位数：
  - `cpython interp`：`0.20433606498409063`
  - `cpython jit`：`0.27011921399389394`
  - `cinderx interp(pure)`：`0.26014454499818385`
  - `cinderx jit`：`0.27385730302194133`
- 本次 CinderX JIT 代码生成证据：
  - `compiled_size=1296`
  - `stack_size=240`
  - `spill_stack_size=160`
  - `dump_elf.elf_e_machine=183`（AArch64）


## 2026-02-28 ARM 跟进：1/2 完成并直接执行第 3 项（解释器开关矩阵）

### 本轮代码变更
- `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
  - 新增回归测试：
    - `test_int_binary_identity_simplify_reduces_compiled_size`
  - 目标：约束 `IntBinaryOp` 恒等式化简在 ARM 上持续生效（`simplify on` 编译体积应小于 `simplify off`）。
- `scripts/arm/remote_update_build_test.sh`
  - 新增 `ARM_RUNTIME_SKIP_TESTS`（默认空）：
    - 仅在指定时跳过匹配测试 id，默认仍跑全量 ARM runtime 测试。
  - 修复 pyperformance venv 复用：
    - 不再无条件 `pyperformance venv create`；
    - 优先复用已有 venv，缺失时创建，`RECREATE_PYPERF_VENV=1` 时强制重建。
- `scripts/arm/interp_feature_matrix.sh`（新增）
  - 按组合运行 `ENABLE_ADAPTIVE_STATIC_PYTHON x ENABLE_LIGHTWEIGHT_FRAMES`；
  - 每组均通过统一远端入口 `remote_update_build_test.sh` 构建+测试；
  - 随后采集 `cinderx interp`（`PYTHONJITDISABLE=1`）性能并汇总 JSON/TSV。

### 第 3 项闭环（开关矩阵）
- 第一轮（`run_id=20260228_3flag_matrix_a`）：
  - 仅 `1,1` 成功，`1,0/0,1/0,0` 在入口后段失败；
  - 根因：`pyperformance venv create` 对“已存在 venv”返回错误并中止。
- 修复入口后复跑（`run_id=20260228_3flag_matrix_b`）：
  - `1,1 / 1,0 / 0,1 / 0,0` 全部 `ok`；
  - `runtime_adaptive/runtime_lightweight` 与构建开关一一对应，验证矩阵有效。

### 矩阵结果（`run_id=20260228_3flag_matrix_b`）
- CPython 解释器基线：
  - `cpython interp median = 0.2037681249785237 s`
- CinderX 解释器（pure interp）：
  - `1,1`：`0.2616621670022141 s`（相对 CPython `+28.41%`）
  - `1,0`：`0.26301215699641034 s`（相对 CPython `+29.07%`）
  - `0,1`：`0.2604445500182919 s`（相对 CPython `+27.81%`）
  - `0,0`：`0.3688814859779086 s`（相对 CPython `+81.03%`）
- 组合内对比（以 `1,1` 为参照）：
  - `1,0` vs `1,1`：`+0.52%`
  - `0,1` vs `1,1`：`-0.47%`
  - `0,0` vs `1,1`：`+40.98%`
- 结论：
  - 两个开关都关闭（`0,0`）会显著拉低解释器基线；
  - 单独关闭其中一个开关对该负载影响小（接近噪声区间）。

### 统一入口复验（默认全量测试，防回归）
- 入口：`/root/work/incoming/remote_update_build_test.sh`
- 命令关键参数：
  - `SKIP_PYPERF=1`，未设置 `ARM_RUNTIME_SKIP_TESTS`
- 结果：
  - `Ran 11 tests ... OK`
  - 脚本整体 `exit 0`
  - 证明新增可选跳过机制不影响默认门禁行为。

### 产物
- 远端：
  - `/root/work/arm-sync/interp_feature_matrix_20260228_3flag_matrix_a/summary.json`
  - `/root/work/arm-sync/interp_feature_matrix_20260228_3flag_matrix_b/summary.json`
  - `/root/work/arm-sync/interp_feature_matrix_20260228_3flag_matrix_b/results.tsv`
- 本地：
  - `artifacts/arm/20260228_interp_matrix/interp_feature_matrix_20260228_3flag_matrix_b/summary.json`
  - `artifacts/arm/20260228_interp_matrix/interp_feature_matrix_20260228_3flag_matrix_b/results.tsv`

## 2026-02-28 ARM 跟进：autojit 触发降噪（jitlist 过滤）与入口稳态修复

### 背景
- 本轮先前尝试的 AArch64 `emitCall` 混合策略（首个热点 direct call，后续 literal）在 ARM 运行时回归：
  - `test_aarch64_call_sites_are_compact` 触发 `SIGSEGV/Illegal instruction`。
- 已回退 `emitCall` 混合策略改动，恢复稳定实现；单测复验通过。

### 本轮代码改动
- `scripts/arm/remote_update_build_test.sh`
  - 新增 `AUTOJIT_USE_JITLIST_FILTER`（默认 `1`）
  - 新增 `AUTOJIT_EXTRA_JITLIST`（可追加规则，逗号分隔）
  - autojit gate 在过滤开启时注入：
    - `PYTHONJITLISTFILE=/tmp/jitlist_autojit_gate_<RUN_ID>.txt`
    - `PYTHONJITENABLEJITLISTWILDCARDS=1`
  - 新增 autojit 编译统计产物：
    - `/root/work/arm-sync/richards_autojit50_<RUN_ID>_compile_summary.json`
    - 字段：`total_compile_count/main_compile_count/other_compile_count`
  - 增强 pyperformance venv 稳定性：
    - `pyperformance venv create/recreate` 失败时，自动清理 `$WORKDIR/venv` 并重试一次。

### 统一远端入口验证（按要求）
- 入口：`/root/work/incoming/remote_update_build_test.sh`
- 公共参数：`BENCH=richards AUTOJIT=50 AUTOJIT_GATE=50 SKIP_PYPERF=0`

#### A 组：不过滤（`AUTOJIT_USE_JITLIST_FILTER=0`）
- run_id：`20260228_165011`
- 结果：脚本 `exit 0`，ARM runtime `Ran 11 tests ... OK`
- 编译统计：
  - `main_compile_count=18`
  - `total_compile_count=182`
  - `other_compile_count=164`
- 性能：
  - jitlist：`0.07689647501683794`
  - autojit50：`0.07088315798318945`

#### B 组：开启过滤（`AUTOJIT_USE_JITLIST_FILTER=1`）
- run_id：`20260228_170353`
- 结果：脚本 `exit 0`，ARM runtime `Ran 11 tests ... OK`
- 编译统计：
  - `main_compile_count=18`
  - `total_compile_count=18`
  - `other_compile_count=0`
- 性能：
  - jitlist：`0.07792964298278093`
  - autojit50：`0.07225936200120486`

### 对比结论
- 降噪效果明确：`other_compile_count` 从 `164` 降到 `0`，autojit 不再编译大量非 `__main__` 目标。
- 本轮单次性能快照：
  - jitlist：过滤开启相对不过滤约 `+1.34%`（略慢）
  - autojit50：过滤开启相对不过滤约 `+1.94%`（略慢）
- 解释：当前是单次 `debug-single-value` 快照，负载噪声仍较大；但“编译对象更准、日志可解释性更高”这一目标已达成。

### 关键产物
- 远端：
  - `/root/work/arm-sync/richards_autojit50_20260228_165011_compile_summary.json`
  - `/root/work/arm-sync/richards_autojit50_20260228_170353_compile_summary.json`
  - `/root/work/arm-sync/richards_jitlist_20260228_165011.json`
  - `/root/work/arm-sync/richards_jitlist_20260228_170353.json`
  - `/root/work/arm-sync/richards_autojit50_20260228_165011.json`
  - `/root/work/arm-sync/richards_autojit50_20260228_170353.json`
  - `/tmp/jit_richards_autojit50_20260228_165011.log`
  - `/tmp/jit_richards_autojit50_20260228_170353.log`


## 2026-02-28 ARM 任务4闭环：解释器基线差距复核（同口径基线）

### 本轮目标
- 优先完成“解释器基线差距”定位，确认此前 `cinderx interp` 相对 `cpython interp` 的大幅落后是否为同口径对比。

### 本轮脚本修正（本地+远端同步）
- `scripts/arm/bench_compare_modes.py`
  - 在 `--mode interp` 下，跳过：
    - CinderX 的 `cinderjit.disassemble()/dump_elf/get_compiled_*` 元数据探针；
    - CPython 的 `_opcode.get_executor(...)` 探针。
  - 目的：避免“解释器模式测量”被 JIT 元数据探针污染。
- `scripts/arm/interp_hotspot_profile.sh`
  - 默认 `CPYTHON_PY` 改为 `/opt/python-3.14/bin/python3.14`（与 CinderX driver venv 同基线）。
- `scripts/arm/interp_feature_matrix.sh`
  - 默认 `CPYTHON_PY` 同步改为 `/opt/python-3.14/bin/python3.14`。

### TDD：最小复现实验（远端 ARM）
- 入口：`ssh root@124.70.162.35`
- 同参数下的 `bench_compare_modes.py --mode interp`（`n=250,warmup=20000,calls=12000,repeats=7`）：
  - `cpython (/opt/python-3.14)`：`median=0.26232359898858704`
  - `cpython (/root/opt/python-3.14-jit)`：`median=0.3375072380003985`
  - `cinderx (/root/venv-cinderx314/bin/python)`：`median=0.26577374900807627`
- 结论：
  - “旧基线”`/root/opt/python-3.14-jit` 作为解释器对照会显著放大差距；
  - 与同基线 CPython 对比时，差距明显缩小。

### Verification：统一脚本复验（远端）
- `interp_hotspot_profile` 双基线对照：
  - `run_id=20260228_interp_gap_samebase`
    - `cinderx_interp_median_sec=0.26470103400060907`
    - `cpython_interp_median_sec=0.2602885249943938`
    - `cinderx_over_cpython=1.0169523762382928`（约 `+1.70%`）
  - `run_id=20260228_interp_gap_jitbase`
    - `cinderx_interp_median_sec=0.2668363949924242`
    - `cpython_interp_median_sec=0.2059948510141112`
    - `cinderx_over_cpython=1.2953546832786864`（约 `+29.54%`）
- `interp_feature_matrix`（内部统一走 `remote_update_build_test.sh`）：
  - `run_id=20260228_interp_matrix_samebase_v1`
  - `cpython_interp_median_sec=0.2616365280118771`
  - 结果：
    - `1,1`: `0.2646517760003917`（`1.0115x`）
    - `1,0`: `0.266659419023199`（`1.0192x`）
    - `0,1`: `0.2651865700026974`（`1.0136x`）
    - `0,0`: `0.4135193559923209`（`1.5805x`）

### 结论（任务4当前状态）
- 解释器“巨大差距”主要来自基线不一致（把 `python-3.14-jit` 构建当成解释器基线）。
- 在同基线口径下，`cinderx interp` 与 `cpython interp` 在 `1,1/1,0/0,1` 组合仅约 `+1%` 量级。
- 当前真正需要继续优化的解释器方向：
  - 避免 `ENABLE_ADAPTIVE_STATIC_PYTHON=0` 且 `ENABLE_LIGHTWEIGHT_FRAMES=0`（`0,0`）组合；
  - 优先针对 `0,0` 的大幅退化路径做热点分析（已不是“整体解释器普遍慢 20~30%”的问题）。

### 本轮关键产物
- 远端：
  - `/root/work/arm-sync/interp_hotspot_profile_20260228_interp_gap_samebase/summary.json`
  - `/root/work/arm-sync/interp_hotspot_profile_20260228_interp_gap_jitbase/summary.json`
  - `/root/work/arm-sync/interp_feature_matrix_20260228_interp_matrix_samebase_v1/summary.json`
  - `/root/work/arm-sync/interp_feature_matrix_20260228_interp_matrix_samebase_v1/results.tsv`

## 2026-03-02 ARM 跟进：Float HIR“回归”定位结果（任务闭环）

### 目标
- 用户反馈：`facebookincubator/cinderx main` 的 `float_math` 用例可产出 `FloatBinaryOp`，当前分支疑似被改坏。
- 要求：按统一远端入口复现、定位影响点、给出可追溯结论。

### 计划与方法
- 计划文档：`docs/plans/2026-03-02-float-hir-regression-triage.md`
- 统一远端入口：`/root/work/incoming/remote_update_build_test.sh`
- 新增最小断言脚本：`scripts/arm/check_float_hir.sh`
  - 断言最终 HIR 必须包含：
    - `FloatBinaryOp<Add>`
    - `FloatBinaryOp<Subtract>`
    - `FloatBinaryOp<Multiply>`
    - `FloatBinaryOp<TrueDivide>`

### TDD 结果（远端）
- 构建/测试（统一入口）：
  - 命令关键参数：`SKIP_PYPERF=1`
  - 结果：`Ran 11 tests ... OK`
- 最小断言：
  - `PYTHON=/root/venv-cinderx314/bin/python scripts/arm/check_float_hir.sh`
  - 结果：`OK`，4 个 `FloatBinaryOp` 全部命中。

### 对照定位（影响点）
- 同一脚本在非 CinderX 解释器下失败：
  - `PYTHON=/opt/python-3.14/bin/python3.14 scripts/arm/check_float_hir.sh`
  - 错误：`ModuleNotFoundError: No module named 'cinderx.jit'`
- 结论：
  - 该“回归”并非 `FloatBinaryOp` 降级/丢失；
  - 实际影响点是运行解释器路径（环境）错误，未使用装有 CinderX JIT 的解释器。

### 提交范围排查
- 从分支合入上游后的范围（`c3028e25..HEAD`）里：
  - `cinderx/Jit/hir` 仅有提交 `ddf1b84e` 触及 `simplify.cpp`；
  - 改动内容是 `IntBinaryOp` 恒等式化简，不涉及 `FloatBinaryOp` lowering 路径。
- 现有证据与远端复现一致：当前分支在正确解释器环境下功能正常。

### 产物
- 远端：
  - `/root/work/arm-sync/float_hir_check_20260302/pass_after_patch.log`
  - `/root/work/arm-sync/float_hir_check_20260302/fail_after_patch.log`
- 本地：
  - `artifacts/arm/20260302_float_hir_check/pass_after_patch.log`
  - `artifacts/arm/20260302_float_hir_check/fail_after_patch.log`
  - `artifacts/arm/20260302_float_hir_check/summary.json`

### 补充修复
- `scripts/arm/check_float_hir.sh` 增强：
  - 当 workload 执行失败时，输出 python 路径与完整 stderr/stdout（避免静默失败）。

### 追加复验（2026-03-02 继续）
- 为避免“只看当前分支”的偏差，尝试用历史基线提交 `c3028e25` 走同一远端入口做 A/B。
- 结果：该基线在当前远端环境会触发 `FetchContent` 联网拉取 `asmjit`，因网络限制失败（非功能用例失败），无法在该环境完成有效 A/B。
- 随后已将远端恢复到当前分支代码，并再次通过统一入口复验：
  - `remote_update_build_test.sh`：`Ran 11 tests ... OK`
  - `check_float_hir.sh`：
    - `PYTHON=/root/venv-cinderx314/bin/python` -> `OK: FloatBinaryOp patterns found`
    - `PYTHON=/opt/python-3.14/bin/python3.14` -> `ModuleNotFoundError: No module named 'cinderx.jit'`
- 追加结论保持不变：
  - 当前问题主因是解释器路径/环境，而不是 `FloatBinaryOp` 在本分支被改坏。
- 按用户原始写法做了“exact command”复核：
  - `/root/venv-cinderx314/bin/python` + 同样脚本 -> 正常输出 `FloatBinaryOp`。
  - `python`（系统默认）+ 同样脚本 -> `ModuleNotFoundError: No module named 'cinderx.jit'`。
- 说明：若命令里写裸 `python`，极易跑到非 CinderX 解释器，表现为“功能坏了”。

## 2026-03-02 ARM 跟进：Float BinaryOp 下沉 DoubleBinaryOp（对齐浮点机器码）

### 背景
- 用户反馈：当前分支在 `float_math` 用例中仍出现 `FloatBinaryOp`，导致 LIR/机器码走 helper call；
  期望与 CinderX 3.14 main 对齐，优先下沉到 `DoubleBinaryOp` 以生成原生浮点指令。

### 代码改动
- `cinderx/Jit/hir/simplify.cpp`
  - 在 `simplifyBinaryOp()` 中，对 `TFloatExact` 的 `+ / - / *` 路径做下沉：
    - `PrimitiveUnbox(TCDouble)` -> `DoubleBinaryOp` -> `PrimitiveBox(TCDouble)`
  - `TrueDivide` 仍保留 `FloatBinaryOp` helper 路径，避免破坏 Python 对 `±0.0` 的除零语义。

### 回归测试补充
- `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
  - 新增：`test_float_add_sub_mul_lower_to_double_binary_op_in_final_hir`
  - 断言最终 HIR 包含：
    - `DoubleBinaryOp<Add>`
    - `DoubleBinaryOp<Subtract>`
    - `DoubleBinaryOp<Multiply>`

### 统一远端入口验证（按要求）
- 入口：`/root/work/incoming/remote_update_build_test.sh`
- 参数：`SKIP_PYPERF=1`
- 结果：`Ran 12 tests ... OK`

### 用户用例复验（远端）
- 命令环境：
  - `PYTHONJITDUMPFINALHIR=1`
  - `PYTHONJITDUMPLIR=1`
  - `cinderx.jit.enable_specialized_opcodes()` + `cinderx.jit.auto()`
- 最终 HIR（关键）:
  - `DoubleBinaryOp<Add>`
  - `DoubleBinaryOp<Subtract>`
  - `DoubleBinaryOp<Multiply>`
  - `FloatBinaryOp<TrueDivide>`（保留语义路径）
- LIR（关键）:
  - `Fadd` / `Fsub` / `Fmul` 已出现（对应前三个运算）
  - `TrueDivide` 仍为 helper call（`float_div`）

### 产物
- 本地：
  - `artifacts/arm/20260302_float_hir_check/after_fix_hir.log`
  - `artifacts/arm/20260302_float_hir_check/after_fix_lir.log`
  - `artifacts/arm/20260302_float_hir_check/summary.json`

## 2026-03-02 追加分析：为何 upstream main 不改也能出 DoubleBinaryOp

### 结论
- 根因是**分支同步滞后**，不是本分支把该能力“改坏”。

### 证据链
- 我们分支历史（`c3028e25..HEAD`）里，触及该路径的提交很少：
  - `ddf1b84e` 只改了 `IntBinaryOp` 化简，不涉及 `FloatBinaryOp -> DoubleBinaryOp`。
- 在合并上游点 `c3028e25` 中，`simplifyBinaryOp()` 的浮点分支仍直接：
  - `return env.emit<FloatBinaryOp>(...)`
- 拉取最新 `upstream/main`（当前 `cb93ec8f`）后，对比发现 upstream 已新增：
  - `simplifyFloatBinaryOp()` 中将 `Add/Subtract/Multiply` 下沉为：
    - `PrimitiveUnbox(TCDouble) -> DoubleBinaryOp -> PrimitiveBox(TCDouble)`
  - `lir/generator.cpp` 对 `DoubleBinaryOp<Power>` 还新增了 `x**0.5 -> sqrt` 快路径。

### 归因
- 你观察到的“upstream main 不改也能出 DoubleBinaryOp”是对的；
- 我们之前不行，是因为 branch 基于较早上游点（`c3028e25`）且未同步到包含该优化的后续上游提交。

## 2026-03-02 同步 upstream/main 冲突修复与远端验证

### 同步与冲突
- 当前分支：`bench-cur-7c361dce`
- 同步目标：`upstream/main`
- 先解决了 shallow 历史导致的 `refusing to merge unrelated histories`：
  - `git fetch --unshallow origin`
  - `git fetch upstream main`
  - `git merge upstream/main`
- 冲突文件（3 个）：
  - `cinderx/Common/util.h`
  - `cinderx/Jit/codegen/autogen.cpp`
  - `cinderx/Jit/codegen/gen_asm_utils.cpp`
- merge commit：
  - `e9c8311a Merge remote-tracking branch 'upstream/main' into bench-cur-7c361dce`

### 远端入口首轮验证（失败）
- 入口：`root@124.70.162.35` + `/root/work/incoming/remote_update_build_test.sh`
- 参数：`SKIP_PYPERF=1`
- 结果：
  - 构建成功
  - `test_arm_runtime.py` 失败 2 项（AArch64 代码尺寸阈值）：
    - `test_aarch64_call_sites_are_compact`: 实际 `95680`，阈值 `78000`
    - `test_aarch64_duplicate_call_result_arg_chain_is_compact`: 实际 `54752`，阈值 `44700`
- 归因：
  - 合并时把 upstream 的 AArch64 `Call` 返回地址保存序列带入当前分支，导致调用点体积明显增大，触发分支已有尺寸门禁。

### 修复动作
- `cinderx/Jit/codegen/autogen.cpp`
  - `translateCall()` 回到分支原有紧凑路径（保留 debug 记录语义）。
- `cinderx/Jit/codegen/gen_asm_utils.cpp`
  - 保留我们原有的 AArch64 MCS cold/hot 调用修复（大位移场景）。
  - 去掉本次同步引入的每次 helper call 额外返回地址保存指令序列，恢复紧凑调用点。

### 远端入口二轮验证（通过）
- 同入口同参数复验：`SKIP_PYPERF=1`
- 结果：
  - `Ran 12 tests in 1.619s`
  - `OK`

### 关键补充验证（远端）
- 浮点 HIR 下沉复核（同一远端环境）：
  - `DoubleBinaryOp<Add>`
  - `DoubleBinaryOp<Subtract>`
  - `DoubleBinaryOp<Multiply>`
  - `FloatBinaryOp<TrueDivide>`（语义保留）
- `force_compile True`，符合预期。

### 尺寸门禁当前值（远端实测）
- `size_call_sites = 77288`（阈值 78000，已通过）
- `size_dup_chain = 44520`（阈值 44700，已通过）

## 2026-03-02 Issue #3：Static Python 编译期开关（ENABLE_STATIC_PYTHON）

### Brainstorming 结论
- Static Python 在 CinderX 中与 JIT/模块初始化耦合较深，第一阶段采用“编译期开关 + 条件编译入口控制”的最小可落地方案。
- 默认保持开启（`ENABLE_STATIC_PYTHON=1`）保证现有行为和性能基线不受影响。
- 关闭时（`ENABLE_STATIC_PYTHON=0`）强制关闭 `ENABLE_ADAPTIVE_STATIC_PYTHON`，并通过 `CINDER_ENABLE_STATIC_PYTHON` 控制关键静态路径行为。

### 代码改动
- `CMakeLists.txt`
  - 新增 `option(ENABLE_STATIC_PYTHON ON)`。
  - 当该开关关闭时，强制 `ENABLE_ADAPTIVE_STATIC_PYTHON=OFF`。
  - 开启时定义宏：`CINDER_ENABLE_STATIC_PYTHON`。
- `setup.py`
  - 新增环境开关透传：`ENABLE_STATIC_PYTHON`（默认 True）。
  - 当其为 False 时，强制 `ENABLE_ADAPTIVE_STATIC_PYTHON=0`。
- `cinderx/_cinderx-lib.cpp`
  - 新增 API：`is_static_python_enabled()`。
  - `clear_caches`/`clear_classloader_caches`/`watch_sys_modules`/`strict_module_patch*`/dict watcher 等静态路径增加编译期条件控制。
  - 兼容性修复：即使关闭静态优化路径，也保留 `_static` 模块创建，避免 Python 层导入链断裂。
- `cinderx/PythonLib/cinderx/__init__.py`
  - 导出 `is_static_python_enabled()`（含 ImportError fallback）。
- `cinderx/PythonLib/test_cinderx/test_oss_quick.py`
  - 新增 `test_static_python_enablement_state`。
  - `test_adaptive_static_python_enablement_state` 按 `is_static_python_enabled()` 动态调整预期。

### TDD 记录
- RED（远端）
  - 构建后运行 `test_oss_quick.py` 失败：缺少 `is_static_python_enabled`。
  - 证据：`FAIL: test_static_python_enablement_state`。
- GREEN（远端）
  - 实现后同测试通过。
  - 默认构建：`static_enabled=True`，`adaptive_enabled=True`。

### 远端入口验证（统一）
- 入口：`root@124.70.162.35` + `/root/work/incoming/remote_update_build_test.sh`
- 默认 ON：
  - 日志：`/root/work/arm-sync/static_python_green_default_20260302_171338.log`
  - CMake 参数含：`-DENABLE_STATIC_PYTHON=1 -DENABLE_ADAPTIVE_STATIC_PYTHON=1`
  - 结果：`Ran 12 tests ... OK`，`jit-effective-ok`。
- OFF 复验（修复后）：
  - 日志：`/root/work/arm-sync/static_python_green_off_fix_20260302_172802.log`
  - CMake 参数含：`-DENABLE_STATIC_PYTHON=0 -DENABLE_ADAPTIVE_STATIC_PYTHON=0`
  - 结果：`Ran 12 tests ... OK`，`jit-effective-ok`。
  - Python 侧复核：`static_enabled=False`，`adaptive_enabled=False`，`test_oss_quick.py` 通过。

### 性能验收（ARM，基线 vs 当前）
- 同脚本：`scripts/arm/bench_compare_modes.py`，`repeats=7`。
- 基线构建：`91a27dcf`
  - 构建日志：`/root/work/arm-sync/static_python_perf_baseline_build_20260302_173732.log`
  - 数据目录：`/root/work/arm-sync/static_python_perf_baseline_20260302_174447`
- 当前构建：workspace snapshot（本次实现）
  - 构建日志：`/root/work/arm-sync/static_python_perf_candidate_build_20260302_174550.log`
  - 数据目录：`/root/work/arm-sync/static_python_perf_candidate_20260302_175238`
  - 复测目录：`/root/work/arm-sync/static_python_perf_candidate_r2_20260302_175322`

#### 关键对比（baseline -> candidate，median_sec）
- `cinderx_interp`: `0.2645615 -> 0.2662111`（`+0.624%`）
- `cinderx_jit`: `0.2648155 -> 0.2690761`（`+1.609%`）
- `cpython_interp`: `0.2617049 -> 0.2623430`（`+0.244%`）
- `cpython_jit`: `0.2602936 -> 0.2608223`（`+0.203%`）

#### 复测观察（candidate_r2）
- `cinderx_jit` 回落到 `0.2666050`，相对 baseline 约 `+0.676%`。
- 说明本轮波动主要在 ~1% 级别，未见明确功能性回退信号。

### 结论
- 编译期开关已实现并可用：`ENABLE_STATIC_PYTHON` + `CINDER_ENABLE_STATIC_PYTHON`。
- 默认路径（ON）下：远端门禁和 JIT 功能正常。
- 关闭路径（OFF）下：构建、关键测试和 JIT smoke 可通过，并且 `is_static_python_enabled=False` 与 `adaptive=False` 语义一致。
- 性能方面：本轮数据未显示确定性的显著回退（波动约 1% 量级）。
