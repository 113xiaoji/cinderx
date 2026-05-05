# Pyperformance JIT 30 Percent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a remote-verified performance tuning loop that drives the selected pyperformance JIT benchmark set to at least 30% geomean speedup versus the current JIT baseline.

**Architecture:** Keep benchmark orchestration in `scripts/arm/*`, keep planning evidence in `task_plan.md`, `findings.md`, and `progress.md`, and keep production JIT changes small and test-first. The loop separates measurement infrastructure from HIR/LIR/tier-policy changes so benchmark failures and correctness failures are diagnosable.

**Tech Stack:** PowerShell orchestration, remote ARM shell, Python 3.14, pyperformance, CinderX JIT, HIR/LIR runtime tests, `unittest`, JSON benchmark summaries.

---

## Files

- Modify: `scripts/arm/run_pyperf_subset.sh`
- Modify: `scripts/arm/compare_pyperf_subset.py`
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`
- Test: `tests` or a new focused script test if the repository has a suitable harness for ARM helper scripts
- Production candidates later: `cinderx/Jit/hir/builder.cpp`, `cinderx/Jit/hir/simplify.cpp`, `cinderx/Jit/hir/refcount_insertion.cpp`, `cinderx/Jit/lir/generator.cpp`, `cinderx/Jit/context.cpp`, `cinderx/Jit/pyjit.cpp`, `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`, `cinderx/PythonLib/test_cinderx/test_jit_tiering.py`

## Task 1: Benchmark Scoreboard Harness

- [x] **Step 1: Add a failing test or direct dry-run check for geomean comparison**

Create a small JSON pair where one benchmark improves by 50% and one is neutral. The compare tool should output ratios and a geometric mean ratio.

Expected behavior:

```json
{
  "geomean_time_ratio": 0.7071067811865476,
  "geomean_speedup_pct": 29.28932188134524
}
```

- [x] **Step 2: Run the check and confirm it fails before implementation**

Run:

```powershell
python scripts/arm/compare_pyperf_subset.py --base <base.json> --current <current.json> --output <out.json>
```

Expected: output lacks `geomean_time_ratio` and `geomean_speedup_pct`.

- [x] **Step 3: Implement geomean output**

Update `scripts/arm/compare_pyperf_subset.py` to compute per-benchmark `time_ratio`, `speedup_pct`, `geomean_time_ratio`, and `geomean_speedup_pct` over benchmarks present in both summaries.

- [x] **Step 4: Add or document no-JIT/JIT mode support**

Extend `scripts/arm/run_pyperf_subset.sh` with an explicit mode variable such as `MODE=autojit|nojit|jitlist`. `nojit` must inherit `CINDERX_DISABLE=1` into workers. `autojit` must preserve the current worker auto-JIT behavior.

- [x] **Step 5: Verify the scoreboard locally**

Run the JSON dry-run again. Expected: the output includes per-benchmark ratios and geomean fields.

## Task 2: Current Baseline Matrix

- [x] **Step 1: Upload and run the current branch through the remote entrypoint**

Use `/root/work/incoming/remote_update_build_test.sh` only. The extended matrix must run through `POST_PYPERF_CMD` or `EXTRA_VERIFY_CMD` with `scripts/arm/run_pyperf_subset.sh`.

Benchmark list:

```text
richards,go,deltablue,raytrace,nqueens,generators,coroutines,comprehensions,unpack_sequence,chaos,logging,coverage,nbody,spectral_norm,scimark,float,fannkuch,pickle,pickle_dict,pickle_list,json_dumps,json_loads
```

- [x] **Step 2: Capture current JIT baseline**

Use `MODE=autojit`, `AUTOJIT=50`, `SAMPLES=5` unless remote runtime makes this too slow. If the run fails, record the failing benchmark and fix the harness or runtime issue rather than dropping the benchmark.

- [x] **Step 3: Capture no-JIT capability baseline**

Use `MODE=nojit`, `SAMPLES=5`. This is not the 30% stop baseline, but it shows whether each benchmark has enough JIT upside to justify deeper work.

- [x] **Step 4: Store and summarize evidence**

Copy or reference the remote JSON paths in `findings.md`. Generate a comparison JSON with geomean fields.

Evidence:

```text
/root/work/arm-sync/pyperf_ext_autojit50_20260503_1.json
/root/work/arm-sync/pyperf_ext_nojit_20260503_1.json
/root/work/arm-sync/pyperf_ext_nojit_vs_autojit50_20260503_1.json
```

Baseline discovery:

- pyperformance expands `logging` and `scimark`; the selected list produced 28 concrete benchmark rows.
- unfiltered `MODE=autojit AUTOJIT=50` is `6.7114x` slower than `MODE=nojit` on geomean.
- only `coverage` is a clear unfiltered auto-JIT win.
- the next required baseline is filtered `MODE=jitlist`, because the first production problem appears to be compile selection / tier policy.

## Task 2B: Filtered Tier Baseline

- [x] **Step 1: Run filtered `jitlist` baseline**

Use `MODE=jitlist`, `SAMPLES=5`, and the same benchmark list through
`/root/work/incoming/remote_update_build_test.sh`.

- [x] **Step 2: Compare filtered baseline against no-JIT and unfiltered auto-JIT**

Generate:

```text
/root/work/arm-sync/pyperf_ext_jitlist_20260503_1.json
/root/work/arm-sync/pyperf_ext_nojit_vs_jitlist_20260503_1.json
```

- [ ] **Step 3: Decide the first production policy candidate**

If filtered `jitlist` is substantially better than unfiltered `autojit50`, rank
compile-selection and backoff policy first. If it is still broadly slower, use
the per-benchmark rows to choose the smallest HIR/LIR candidate with enough
upside.

Evidence:

```text
/root/work/arm-sync/pyperf_ext_jitlist_20260503_1.json
/root/work/arm-sync/pyperf_ext_nojit_vs_jitlist_20260503_1.json
/root/work/arm-sync/pyperf_ext_autojit50_vs_jitlist_20260503_1.json
```

Filtered result:

- filtered `jitlist` versus unfiltered `autojit50`: `geomean_time_ratio = 0.2827850192670735`, `geomean_speedup_pct = 71.72149807329265`.
- filtered `jitlist` versus no-JIT: `geomean_time_ratio = 1.8978816019980658`, `geomean_speedup_pct = -89.78816019980658`.
- decision direction: compile-selection / tier-policy comes first; remaining filtered-JIT overhead still needs HIR/LIR work after policy stops the largest damage.

## Task 3: Triage and Ranking

- [ ] **Step 1: Categorize benchmark deltas**

Group benchmarks into object/call, control-flow/OSR, numeric/primitive, and container/library buckets.

- [ ] **Step 2: Select one minimal hypothesis**

Pick exactly one candidate based on baseline evidence. The first likely candidates are:

```text
field-load/refcount pressure
profile-driven nested method-value VectorCall recovery
numeric primitive loop-body refcount/boxing
container builtin fast path
```

- [ ] **Step 3: Define RED test**

Choose the smallest focused `unittest` or HIR opcode-count test that proves the missing optimization.

## Task 4: Candidate RED/GREEN Loop

- [ ] **Step 1: Write the RED test**

Add a focused test to `cinderx/PythonLib/test_cinderx/test_arm_runtime.py` or `cinderx/PythonLib/test_cinderx/test_jit_tiering.py`, depending on the candidate.

- [ ] **Step 2: Run RED through the remote entrypoint**

Expected: the test fails because the target HIR/LIR/tier behavior is missing.

- [ ] **Step 3: Implement the smallest production change**

Modify only the files required by the candidate. Do not combine unrelated optimizations in the same diff.

- [ ] **Step 4: Run GREEN and adjacent regression tests**

Expected: focused test passes, adjacent object/JIT/tiering tests pass, and no crash/deopt storm appears.

- [ ] **Step 5: Run candidate benchmark matrix**

Run the same extended matrix and compare candidate JSON against the current JIT baseline JSON. Keep the change only if the geomean improves or the correctness/stability value is explicitly worth carrying.

## Task 5: Stop Gate

- [ ] **Step 1: Recompute geomean versus current JIT baseline**

Stop only if `geomean_time_ratio <= 0.70`.

- [ ] **Step 2: Verify correctness**

Run the default ARM runtime tests, full `test_jit_tiering`, and the focused suites touched by all landed candidates through `/root/work/incoming/remote_update_build_test.sh`.

- [ ] **Step 3: Record final evidence**

Write benchmark JSON paths, geomean ratio, per-benchmark regressions, focused test results, and unresolved risks into `findings.md`.
