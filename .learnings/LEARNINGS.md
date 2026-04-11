# LEARNINGS

## 2026-04-11 Day 1 sprint

- In pyperformance `--debug-single-value` output, benchmark entries may contain
  only `runs[].values[]` and omit `metadata.name`. Summary tooling must infer
  names from the requested benchmark filter or explicit row names.
- The remote ARM workdir populated by `remote_update_build_test.sh` is not a
  git checkout. Any summary artifact that needs a commit id must accept an
  explicit commit string instead of relying on `git rev-parse`.
- `bench_pyperf_direct.py` is a good low-noise place to validate new runtime
  stats schema before trusting full pyperformance summaries.

## 2026-04-11 Day 2 sprint

- For `remote_update_build_test.sh`, `PIP_NO_INDEX=1` is too blunt as a helper
  verification trick because it also breaks the isolated `python -m build`
  step. Verify skip-fast paths by watching the helper exit point, not by
  globally disabling package resolution.
- Object-heavy hot loops can be characterized well enough for a first
  profitability gate using bytecode counts from the loop body itself:
  `attr_ops` and `call_ops` gave a fast way to separate object/stateful loops
  from the current hot-loop winners.
- On the ARM host used here, `python -m build --no-isolation` is the more
  reliable default for rapid iteration because the outer interpreter already has
  compatible `build`, `wheel`, and `setuptools`.
- The current direct benchmark path is useful for seeing whether benchmark code
  itself is being skipped or OSR'd, even when pyperformance venv creation is
  unstable.
- Deploy markers are worth the extra plumbing. They turned an ambiguous
  baseline/current story into a verifiable one and exposed exactly when a
  “baseline” run was not actually on the intended source revision.
- Caching skip decisions by `(code, bc_offset)` plus once-per-window reporting
  can have a first-order performance effect on object-heavy workloads; `go`
  improved dramatically once repeated skip accounting was removed.
- Small direct-benchmark regressions can flip sign under thicker samples. The
  15-repeat recheck turned `fannkuch`, `chaos`, and `raytrace` from apparent
  regressions into flat-to-positive results.
- The same thicker-sample process also identified which broad-pass regressions
  are real enough to pursue: `unpack_sequence`, `spectral_norm`, `nbody`, and
  `scimark_lu` stayed negative on 15-repeat medians.
- Some hot loops do compile successfully under the hot-loop trigger but have no
  usable OSR entry for the current activation. Finalizing those compiled
  functions for future calls is a high-leverage coverage fix.
- For loops that should never OSR, caching the decision is not enough if the
  interpreter still re-enters `_PyJIT_TryHotLoopOSR()` on every backward jump.
  Rewriting the backedge to `JUMP_BACKWARD_NO_JIT` removes that residual tax.

## 2026-04-07 issue85 kickoff

- `#76` 的 Phase 1 主线已经不再是主要问题，新的重点是 profitability，而不是 correctness。
- object-heavy / search-heavy workload 需要单独看 shape，不要和 wrapper pollution 混为一谈。
- `go` 这类 case 的关键是：
  - 回边循环里调用密集
  - 属性访问和状态迁移密集
  - 即使只有一个函数 same-activation OSR，也可能带来明显回退
- `comprehensions` 这类 case 要谨慎下结论：
  - 端到端 timing 需要多轮重复验证
  - 如果 `osr_count` 始终是 `0`，就不要把它归因为 hot-loop OSR
