# Task Plan: DeltaBlue HIR/LIR Analysis

## Goal
Find the highest-value HIR/LIR optimization opportunities in `pyperformance bm_deltablue`, implement the best one(s), and validate real benchmark gains.

## Workflow
- Baseline current benchmark on remote.
- Identify hottest compiled functions in DeltaBlue.
- Dump and inspect HIR/LIR for the hottest paths.
- Implement the smallest high-impact optimization.
- Re-measure on the same remote host against a clean baseline worktree.

## Constraints
- Use `124.70.162.35` for meaningful performance validation.
- Keep the benchmark comparison apples-to-apples.
- Avoid speculative large-surface refactors until a hot bottleneck is proven.

## Status
- [x] Start planning
- [x] Prepare clean remote worktrees for baseline/current
- [x] Measure current DeltaBlue baseline
- [x] Inspect hot-function HIR/LIR
- [ ] Implement optimization
- [ ] Verify correctness and benchmark gain

## Current Direction
- Remote baseline on `c3ac4a6` is built in both `cinderx-deltablue-base` and `cinderx-deltablue-dev`.
- Direct `delta_blue(100)` samples on the base tree show the hottest compiled function is `bm_deltablue_run.BinaryConstraint.choose_method` (compiled size `7576`).
- `choose_method` spends 5 `CallMethod` sites on `Strength.stronger/weaker` classmethod wrappers.
- Those wrappers are tiny (`Strength.stronger` / `Strength.weaker` compile to size `760`) and are good candidates for eliminating type-method cache call overhead, then exposing to the inliner.
- The attempted implementation paths were:
  - extend builtin load-method elimination to handle exact type-receiver method loads coming from `{LoadTypeMethodCacheEntryValue | FillTypeMethodCache}`
  - preserve mutation correctness with runtime identity guards on the resolved callable / bound receiver
  - rerun inlining after builtin load-method elimination
  - narrow inline of trivial `return a.attr < b.attr` / `>` classmethod wrappers

## Result
- [x] Implement optimization candidate
- [x] Verify correctness on remote
- [x] Verify benchmark impact on remote
- [x] Record that the current candidate is not worth landing

## Verdict
- The classmethod-call elimination direction is not a good DeltaBlue optimization in its current form.
- Runtime correctness was achieved, but the verified hot benchmark signal was negative:
  - vectorcall-only reduction removed `CallMethod`, but steady-state `delta_blue(100)` got slower than base
  - directly inlining the wrapper into `choose_method` made the function substantially larger and much slower
- This candidate should not be merged as-is.

## Follow-up
- A second iteration targeted `len()` truthiness in `Planner.remove_propagate_from`.
- This one is promising:
  - very small HIR change
  - targeted regression test passed remotely
  - steady-state DeltaBlue benchmark improved on the remote host
- Current local follow-up findings:
  - attempted:
    - narrow `CallMethod -> VectorCall<..., static>` rewrite for constant
      `PyMethodDescr` receivers in `simplifyCallMethod()`
    - builder/bytecode plumbing to preserve
      `CALL_LIST_APPEND` / `CALL_METHOD_DESCRIPTOR_*`
  - remote ARM result on `/root/work/cinderx-main`:
    - targeted list-subclass repros still compiled to
      `LoadMethodCached + GetSecondOutput + CallMethod`
    - `CallMethod` count stayed at `1` for both `append` and `pop(0)`
  - conclusion:
    - this patch is not worth keeping in code form
    - the real optimization point is earlier than the current HIR simplify hook
      and likely earlier than the current builder call lowering as well
- Follow-up on the follow-up:
  - root cause proved by remote instrumentation:
    - builder already saw specialized call opcodes
      (`CALL_LIST_APPEND`, `CALL_METHOD_DESCRIPTOR_FAST`)
    - but the callable register had no output type yet during HIR construction
  - fix:
    - preserve the specialized call families in `BytecodeInstruction::specializedOpcode()`
    - in `emitAnyCall()`, inspect the callable's defining `LoadConst` instruction
      instead of the register output type
    - rewrite method-descriptor specialized calls to `VectorCall<..., static>`
  - remote ARM result on `/root/work/cinderx-main`:
    - `append_once`: `CallMethod: 0`, `ListAppend: 1`
    - `pop_front`: `CallMethod: 0`, `VectorCall: 1`
    - targeted runtime regressions passed
  - benchmark result:
    - stable positive DeltaBlue signal on remote AArch64
    - direct `delta_blue(100)` samples in isolated base/dev venvs showed about
      `2.0%` to `2.3%` median speedup for `dev`
