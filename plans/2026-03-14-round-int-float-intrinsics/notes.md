# Design Notes: issue-35 round/int float intrinsics

## Current State
- `math.sqrt` already has dedicated intrinsification and native lowering.
- `round(x)` and `int(x)` currently stay on builtin-call / `VectorCall` paths.
- There is no existing `DoubleToInt` or generic floating-point rounding opcode in HIR/LIR.

## Implication
- This issue needs new core IR/codegen support, not just a small matcher tweak.
- The smallest coherent implementation is:
  1. add `DoubleToInt<CInt64>` with overflow fallback
  2. use it for `int(float)`
  3. add a rounding step for single-arg `round(float)` and then reuse `DoubleToInt`

## Proposed Phasing
- Phase 1:
  - add `DoubleToInt` HIR opcode
  - lower it in LIR/codegen on AArch64
  - support deopt/fallback when the input cannot be represented as signed int64
  - rewrite `int(float)` builtin calls to `DoubleToInt + PrimitiveBox`
- Phase 2:
  - add a floating-point unary rounding opcode or equivalent LIR/codegen path
  - support banker's rounding semantics for `round(float)` single-arg form
  - rewrite `round(float)` builtin calls to `round-to-nearest + DoubleToInt + PrimitiveBox`

## Risks
- Overflow / NaN / inf handling must deopt cleanly to preserve Python semantics.
- `round(x)` needs banker's rounding, not just “round away from zero”.
- Because this touches new IR/codegen surface area, remote verification is mandatory before any closeout.

## Validation Plan
- Add ARM runtime regressions for:
  - `int_builtin(x)` lowering
  - `round_builtin(x)` lowering
  - negative and tie cases for correctness
- Run targeted remote repros before claiming performance improvement.

## 2026-03-15 Remote Verification Findings
- `124.70.162.35` was used for ARM validation; `124.70.162.32` timed out on port 22 from this environment.
- A major source of confusion was the remote venv initially still loading a wheel installed from `/root/work/cinderx-generators-baseline2/...`; validation only became trustworthy after explicitly reinstalling the wheel from `/root/work/cinderx-main/dist/...`.
- With the correct wheel installed, the new HIR lowering was active:
  - `int(float)` emitted `DoubleToInt`
  - `round(float)` emitted `DoubleRoundToInt`
- First real ARM runs showed a negative-input crash. `gdb` on the remote host showed the failure was in interpreter fallback after deopt:
  - `resumeInInterpreter()` re-entered the call path with a corrupt argument array
  - the new `DoubleToInt` / `DoubleRoundToInt` sites were deopting with a frame state that did not reconstruct the original unary call stack
- Fixes that were required:
  - map `Opcode::kDoubleToInt` and `Opcode::kDoubleRoundToInt` to `DeoptReason::kGuardFailure` in `cinderx/Jit/deopt.cpp`
  - use ordered floating AArch64 conditions for `LessThanUnsigned` / `LessThanEqualUnsigned` in `cinderx/Jit/codegen/autogen.cpp`
  - synthesize a fallback frame state in `simplify.cpp` that reconstructs the original unary builtin call stack (`callable`, `NULL`, `arg`) for `DoubleToInt` / `DoubleRoundToInt`
- After those fixes:
  - negative non-zero values stopped crashing
  - targeted ARM runtime regressions for both new tests passed
  - manual fallback checks confirmed correct behavior for `NaN`, `inf`, `-inf`, and large finite values

## Current Best Technical Read
- This issue did require new IR/backend surface; it was not solvable as a matcher-only tweak.
- The subtle correctness risk was not only numeric comparison but also deopt/frame-state reconstruction for the new fallback path.
- With the fallback-frame fix in place, the new lowering is now functionally correct on the validated ARM host.
