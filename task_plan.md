# Task Plan: ARM vs X86 Richards Optimization Iteration 2026-02-20

## Goal

Execute optimization in strict order:
1) measurement stabilization,
2) JIT policy tuning,
3) ARM codegen hot-path tuning,
with ARM-vs-X86 richards evidence and testing at each stage.

## Phases

- [x] Phase 1: Brainstorming design confirmed by user
- [x] Phase 2: Writing-plans docs created
- [x] Phase 3: Step 1 implementation (ARM/X86 unified measurement entrypoint)
- [x] Phase 4: Step 2 implementation (policy tuning, no codegen)
- [ ] Phase 5: Step 3 implementation (ARM codegen micro-optimization) (in progress)
- [ ] Phase 6: Final verification-before-completion + findings update

## Key Questions

1. Can the x86 host be normalized to the same benchmark toolchain (`venv-cinderx314`)?
2. Which policy knobs show measurable gain before touching codegen?
3. Can ARM codegen changes preserve correctness while improving ARM-vs-X86 gap?

## Decisions Made

- Primary benchmark remains `pyperformance richards`.
- Comparison target: ARM should be >= 3% faster than X86 under unified method.
- X86 host for baseline: `106.14.164.133` (`root` user).
- Default benchmark venv path on both hosts: `/root/venv-cinderx314`.
- Work sequence must remain 1 -> 2 -> 3.
- `PYTHONJITMULTIPLECODESECTIONS` precheck (`mcs=0/1`) is not a robust Step 3
  gain source for JIT modes on current host; keep focus on codegen hot paths.

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| x86 host missing `/root/venv-cinderx314` | 1 | Add setup/bootstrap support as part of Step 1 runner pipeline. |

## Status

Currently: Step 3 codegen hot-path optimization in progress on branch
`bench-cur-7c361dce`; first low-risk regalloc heuristic for AArch64 short
call-chains has been implemented and validated.
Next: run a wider ARM/X86 unified comparison with this change, then decide
whether to keep/iterate/revert based on confidence intervals.
