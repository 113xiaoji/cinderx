# Pyperformance JIT 30 Percent Design

## Goal

Improve the selected pyperformance JIT benchmark set until the candidate branch is at least 30% faster than the current JIT baseline, measured by geometric mean of benchmark median times, while preserving functional correctness.

## Benchmark Set

The initial benchmark set is:

```text
richards,go,deltablue,raytrace,nqueens,generators,coroutines,comprehensions,unpack_sequence,chaos,logging,coverage,nbody,spectral_norm,scimark,float,fannkuch,pickle,pickle_dict,pickle_list,json_dumps,json_loads
```

The set intentionally covers object-heavy workloads, control-flow and OSR workloads, numeric loop workloads, and real Python library workloads.

`logging` and `scimark` are pyperformance benchmark groups. On the ARM harness
they expand to 28 concrete benchmark rows total, so all geomean comparisons must
use the concrete rows present in the JSON summaries rather than the 22 textual
filters above.

## Measurement Model

The stop criterion is candidate-versus-current-JIT-baseline geometric mean speedup:

```text
geomean_speedup = 1 - exp(mean(log(candidate_median / baseline_median)))
```

A 30% improvement means the geomean time ratio is at most `0.70x`. The current branch commit `17f386f8` is the JIT baseline for this tuning wave. No-JIT runs are still useful as a capability map, but they do not count toward the 30% candidate improvement target.

Every performance claim must come from `/root/work/incoming/remote_update_build_test.sh`, with key results copied into `findings.md`.

## Optimization Strategy

The target is too large for a single HIR fast path. The plan is a layered optimization program:

- Tier policy first: avoid optimized-tier work for functions that fail, deopt repeatedly, or show no stable hot path.
- Selective object/call hot paths: recover monomorphic method calls, reduce `LoadMethodCached`/`CallMethod`, and cut field-load/refcount pressure where semantics are provably safe.
- Numeric and loop hot paths: improve boxed primitive, compare, and loop-body lowering for numeric benchmarks.
- Container/library hot paths: add general builtin/container fast paths only when they are benchmark-agnostic and covered by regression tests.

## Correctness Rules

Crashes, deopt storms, empty benchmark summaries, missing worker JIT activation, and large per-benchmark regressions are blockers. They must be reduced to focused reproductions and fixed; benchmarks must not be removed to make the matrix pass.

Each production change must follow RED/GREEN:

1. Add or tighten a focused test that fails for the missing behavior.
2. Run the focused test through the remote entrypoint and record the failure.
3. Implement the smallest production change.
4. Run the focused test, adjacent regression suite, and benchmark matrix through the remote entrypoint.
5. Record correctness and performance evidence in `findings.md`.

## Expected Contribution

The near-term expectation is not that any one slice gives 30%. A realistic contribution model is:

- Tier policy and compile selection: 5-10% by avoiding bad optimized-tier choices.
- Object/call/refcount hot paths: 8-15% by removing distributed dispatch and ownership overhead.
- Numeric/OSR/primitive hot paths: 8-15% by improving loop-body efficiency.
- Container/library paths: 3-8% by reducing common builtin and serialization overhead.

If fresh baseline data contradicts these expectations, the ranking must be updated before code changes.

## Baseline Discovery

The first broad baseline showed that unfiltered worker auto-JIT is itself a
major performance problem on this matrix:

- Remote entrypoint: `/root/work/incoming/remote_update_build_test.sh`
- Current unfiltered JIT baseline:
  `/root/work/arm-sync/pyperf_ext_autojit50_20260503_1.json`
- No-JIT capability baseline:
  `/root/work/arm-sync/pyperf_ext_nojit_20260503_1.json`
- Comparison:
  `/root/work/arm-sync/pyperf_ext_nojit_vs_autojit50_20260503_1.json`
- Result: `geomean_time_ratio = 6.7114` for unfiltered `autojit50` versus
  no-JIT, i.e. the JIT mode is much slower overall.

Only `coverage` was a clear win for unfiltered auto-JIT. The worst regressions
were ultra-short or library-heavy rows such as `unpack_sequence`,
`logging_silent`, `comprehensions`, `pickle_list`, and `deltablue`. This changes
the first production priority from "add one more fast path" to "avoid compiling
bad candidates and establish a filtered tier baseline."

The filtered `MODE=jitlist` baseline validated that diagnosis:

- Remote filtered JIT:
  `/root/work/arm-sync/pyperf_ext_jitlist_20260503_1.json`
- No-JIT versus filtered JIT:
  `/root/work/arm-sync/pyperf_ext_nojit_vs_jitlist_20260503_1.json`
- Unfiltered auto-JIT versus filtered JIT:
  `/root/work/arm-sync/pyperf_ext_autojit50_vs_jitlist_20260503_1.json`
- Filtered JIT versus unfiltered auto-JIT:
  `geomean_time_ratio = 0.2828`, `geomean_speedup_pct = 71.7`.
- Filtered JIT versus no-JIT:
  `geomean_time_ratio = 1.8979`, so filtered JIT is still slower than no-JIT
  overall.

This makes compile selection / tier policy the first production candidate.
Filtered `jitlist` is an oracle showing the size of the policy win; it is not
enough by itself because the remaining filtered JIT still has large execution
costs on rows such as `comprehensions`, `deltablue`, `go`, and `generators`.
