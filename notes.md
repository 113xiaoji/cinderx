# Notes: ARM JIT Perf Iteration 2026-02-19

## Findings

- Working git repo: `d:/code/cinderx-upstream-20260213`, branch `arm-jit-perf`, head `778d01d0`.
- Current AArch64 helper-call dedup path:
  - callsites: `bl helper_stub` (`gen_asm_utils.cpp`)
  - helper stub: `ldr scratch, [literal] ; br scratch` (`gen_asm.cpp`)
- Remaining obvious `mov/blr` direct helper calls are mainly in global trampoline generation code (`gen_asm.cpp`) and not per-instruction codegen.
- There are still many `CINDER_UNSUPPORTED` guard points in ARM paths; benchmark-log-driven selection is needed to avoid blind changes.

## Candidate Next Targets

1. Benchmark-log-driven missing lowering on executed path (recommended).
2. Further helper-stub micro-tuning (risk: noisy gains).
3. autojit stability investigation (confidence work, not immediate speed).

## Scripts / Entry Points

- `scripts/push_to_arm.ps1`
- `scripts/arm/remote_update_build_test.sh`
