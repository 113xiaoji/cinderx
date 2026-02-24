# ARM JIT Perf Iteration Design (2026-02-19)

## Context

Current branch `arm-jit-perf` already includes AArch64 helper-stub call-target dedup and has directional gains on richards. The next iteration must preserve correctness, prove JIT is active, and report clear `from -> to` perf deltas.

## Constraints

- Keep the existing remote validation path as the authority:
  - `scripts/push_to_arm.ps1`
  - `scripts/arm/remote_update_build_test.sh`
- Keep results measurable and comparable:
  - use same benchmark (`richards`) first
  - use repeated sampling where possible
- Avoid broad risky refactors in this iteration.

## Candidate Approaches

### Approach A (Recommended): Hot-path unsupported-op reduction from real benchmark logs

- Capture fresh richards JIT logs on ARM.
- Identify compile misses or unsupported codegen paths actually hit by workload.
- Implement one small AArch64 lowering/fallback improvement that unlocks more compiled regions.
- Re-run same pipeline and compare `from -> to`.

Trade-offs:
- Pros: workload-driven, higher chance of real speed gain.
- Cons: requires log mining and may expose deeper missing pieces.

### Approach B: Further call emission micro-optimization only

- Keep current compilation coverage unchanged.
- Tune helper-call lowering (stub shape/placement/inlining policy) for lower call overhead.

Trade-offs:
- Pros: limited surface area.
- Cons: may be noise-sensitive and already near local optimum.

### Approach C: Stability-first (autojit repeated-run robustness)

- Focus on autojit repeated benchmark stability before speed.
- Add instrumentation/repro harness around worker crashes.

Trade-offs:
- Pros: improves confidence in future perf claims.
- Cons: likely no immediate speedup in this iteration.

## Recommended Design

Use Approach A for this iteration, while still collecting jitlist and autojit results:

1. Establish a fresh baseline using current `arm-jit-perf` head.
2. Mine benchmark JIT logs for missing ARM support in executed paths.
3. Add one minimal targeted change plus a regression test (TDD).
4. Re-run the same pipeline and compare:
   - compiled-size guard
   - richards jitter and autojit values
   - JIT activity proof (`Finished compiling ...` counts/log evidence)
5. Record all results in `findings.md` with explicit `from -> to`.

## Validation Criteria

- JIT runtime unit tests pass on ARM gate run.
- New/updated regression test demonstrates expected behavior.
- JIT active evidence present during benchmark worker run.
- Perf section includes concrete before/after numbers and whether improvement is real (single-sample directional or multi-sample aggregate).
