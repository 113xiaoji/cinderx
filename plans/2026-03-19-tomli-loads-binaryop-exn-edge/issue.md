# [arm-opt][pyperformance] tomli_loads: BinaryOp<Subscript> misses exception edge and deopts on expected IndexError

## Problem description

- Workload:
  - `tomli_loads`
- User-visible symptom:
  - `skip_chars()` deopts with `UnhandledException` whenever `src[pos]` runs off
    the end of the string, even though Python code expects that `IndexError`
    and handles it in the surrounding `try/except`
- Why it matters:
  - `tomli_loads` depends on this pattern as part of normal lexer termination,
    so a deterministic deopt at the string boundary can dominate runtime

## Current IR

- Current HIR/LIR/codegen evidence:
  - pending fresh current-tip confirmation
- Hot blocks / hot ops:
  - expected:
    - `BinaryOp<Subscript>`
    - handler transfer on `IndexError`
    - deopt if exception edges are missing
- Known blockers:
  - not yet refreshed on current tip

## Current implementation observations

- Candidate control points:
  - HIR builder bytecode-to-CFG exception wiring
  - CFG cleanup / terminator logic for exceptional blocks
  - lowering of `BinaryOp<Subscript>` if later passes erase exception metadata
- Current local read suggests a broader limitation:
  - except-handler bytecodes are not fully compiled as normal HIR blocks on the
    current path
  - generic exception-producing deopt sites resume in the interpreter instead
    of branching to compiled handlers

## Target HIR

- Desired first-round HIR shape:
  - `BinaryOp<Subscript>` inside `try` should keep an exception path into the
    compiled handler block
- Why this shape should help:
  - the common `IndexError -> except IndexError: pass` path can stay inside JIT
    code without bouncing to the interpreter

## Optimization suggestions

- HIR ideas:
  - restore/retain exception edges for `BinaryOp<Subscript>` in handler-covered
    blocks
- LIR ideas:
  - only if HIR already models the handler edge correctly and the bug appears
    later
- codegen ideas:
  - only if earlier layers are semantically correct and runtime still fails to
    branch into the handler
- pragmatic fallback:
  - suppress repeated `UnhandledException` recompilation for handled-subscript
    sites so the function stays interpreted after a small number of failures
- Main risks:
  - introducing incorrect exception routing for other binary ops
  - perturbing cold exception paths in unrelated benchmarks

## Minimal reproducer

- Source:
  - `skip_chars(src, pos, chars)` with `while src[pos] in chars`
  - trailing-space input to force `IndexError`
- Expected behavior:
  - correctness preserved
  - no `UnhandledException` deopt for the handled `IndexError`

## Baseline and environment

- ARM host: `124.70.162.35`
- x86 host: `106.14.164.133`
- Remote entrypoint:
  - `scripts/arm/remote_update_build_test.sh`
- Current status:
  - local code read in progress
  - remote reproduction pending

## Repeat-error prevention

- Do not patch from the issue description alone; refresh current-tip evidence
- Do not spend remote build time before a local hypothesis is written down
- Do not rerun the same remote command without a changed hypothesis

## Round plan

- Round 0:
  - local code read
  - minimal reproducer
  - remote `tomli_loads` baseline
- Round 1:
  - first HIR-side patch if exception-edge loss is clearly a builder/CFG issue
- Later rounds:
  - only move to LIR/codegen if HIR does not explain the bug

## Round 1 result so far

- The first implemented fix is a pragmatic runtime fallback:
  - after a small number of repeated handled-subscript `UnhandledException`
    deopts, suppress future JIT compilation of that function
- This fix is validated on the minimal `skip_chars()` runtime shape through the
  standard ARM entrypoint.
- `tomli_loads` jitlist benchmark now runs and reports:
  - `3.71 sec`
- `tomli_loads` autojit2 is still blocked by a later benchmark-worker crash, so
  the benchmark-side win is not closed yet.

## Round 2 isolated result

- In a fully isolated ARM environment with only `tomli._parser:skip_chars`
  whitelisted:
  - jitlist:
    - `3.6831124689997523 s`
  - autojit2:
    - `3.6588112600002205 s`
- The isolated autojit2 run compiled exactly one function:
  - `tomli._parser:skip_chars`
- Interpretation:
  - issue48 fix is validated without the unrelated shared-environment crashes
  - current benchmark gain is small, about `0.7%`
