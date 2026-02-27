# Task Plan: CinderX 3.14 vs CPython 3.14 Interpreter Execution

## Goal
Identify execution-path differences between CinderX 3.14 and upstream CPython 3.14 interpreter, then rank optimization opportunities for CinderX interpreter work.

## Scope
- Interpreter dispatch / eval loop
- Frame evaluation and trampolines
- Opcode specialization / inline cache behavior
- Quickening and deopt interactions
- Supporting runtime hooks that affect interpreter hot path

## Phases
1. Locate relevant source files and baseline versions
2. Diff CinderX against CPython 3.14 for interpreter path
3. Extract behavior/perf-impact differences
4. Produce optimization-priority recommendations

## Status
- [x] Phase 1
- [x] Phase 2
- [x] Phase 3
- [x] Phase 4

## Notes
- Upstream baseline used for comparison: CPython `3.14` branch HEAD `a58ea8c21239a23b03446aecd030995bbe40b7a7` (2026-02-27).
- Local branch analyzed: `bench-cur-7c361dce` at `ed681292cab44e007effb96471999d172a90448d`.
- Comparison focused on `interpreter.c`, `borrowed-ceval.c.template`, `Includes/ceval_macros.h`, `Includes/generated_cases.c.h`, `cinder-bytecodes.c`, and opcode definitions.
