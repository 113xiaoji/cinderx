# Task Plan: tomli_loads BinaryOp exception edge

## Goal
Fix issue `#48`: `BinaryOp<Subscript>` inside `try/except IndexError` does not
keep a JIT exception edge, so the hot `skip_chars()` path in `tomli_loads`
falls back to interpreter with `UnhandledException` deopts.

Primary case:
- `tomli_loads`

Required optimization order:
1. `HIR`
2. `LIR`
3. `codegen`

Required workflow:
1. `brainstorming`
2. `writing-plans`
3. `test-driven-development`
4. `verification-before-completion`

All remote tests and verification must use:
- the standard remote entrypoint
  - `scripts/arm/remote_update_build_test.sh`

Remote hosts:
- ARM: `124.70.162.35`
- x86: `106.14.164.133`

## User constraints
- use `using-superpowers` and `planning-with-files`
- keep case-local notes, issue, and proposal current
- write key results to `findings.md`
- do not repeat failed remote attempts without a new hypothesis
- broad regression matrix before closure:
  - `generators`
  - `coroutines`
  - `comprehensions`
  - `richards`
  - `richards_super`
  - `float`
  - `go`
  - `deltablue`
  - `raytrace`
  - `nqueens`
  - `nbody`
  - `unpack_sequence`
  - `fannkuch`
  - `coverage`
  - `scimark`
  - `spectral_norm`
  - `chaos`
  - `logging`

## Round 0 plan
- [completed] Create proposal, issue, notes, and mistake ledger for issue `#48`
- [completed] Read the current `BinaryOp/Subscript` lowering and exception
  handling path in HIR
- [completed] Reproduce the minimal `skip_chars` shape on current tip
- [completed] Capture a fresh `tomli_loads` baseline on ARM through the remote
  entrypoint
- [completed] Decide whether the first patch belongs in HIR CFG/building or later

## Round 0 success criteria
- a fresh current-tip minimal reproducer exists
- a fresh `tomli_loads` baseline exists
- one concrete first-round implementation hypothesis is written down
- one mistake-prevention entry is added before the first patch

## Current local hypothesis
- current JIT behavior suggests exceptions on `BinaryOp<Subscript>` are
  generally modelled as deopt-to-interpreter, not as compiled handler edges
- therefore the first practical patch is likely:
  - runtime suppression after repeated handled-subscript `UnhandledException`
    deopts
- this remains provisional until the failing remote test and benchmark baseline
  are collected

## Current implementation status
- isolated implementation worktree:
  - `/C:/work/code/coroutines/cinderx-issue48-clean`
  - branch:
    - `codex/issue48-tomli-binaryop-exn-edge`
- main workspace sync:
  - validated runtime/codegen/test changes have now been copied into:
    - `/C:/work/code/coroutines/cinderx`
  - remote-entry support files now also exist in the main workspace:
    - `scripts/arm/verify_pyperf_venv.py`
    - `scripts/arm/pyperf_env_hook/sitecustomize.py`
  - `scripts/arm/remote_update_build_test.sh` now wires:
    - worker-sitecustomize installation
    - optional pyperf worker probing via `SKIP_PYPERF_WORKER_PROBE`
    - overridable `JITLIST_ENTRIES`
    - overridable `AUTOJIT_JITLIST_ENTRIES`
- failing regression test:
  - implemented and now green on ARM
- first patch round:
  - implemented in the isolated worktree and migrated back to the main workspace
- remote validation:
  - partially complete
  - main-workspace revalidation still pending

## Round 1 results
- targeted runtime regression:
  - `ArmRuntimeTests.test_skip_chars_handled_index_error_avoids_repeated_unhandled_deopts`
  - `OK`
- standard-entry jitlist gate:
  - `tomli_loads`: `3.71 sec`
- standard-entry autojit2 gate:
  - still blocked
  - latest failure mode:
    - benchmark-worker segmentation fault after a large stdlib compile surface

## Current decision
- The first patch is validated for the minimal `skip_chars()` shape.
- The benchmark remains blocked by a later autojit crash, so issue `#48` is
  still in progress.

## Round 2 isolated environment
- Remote lease:
  - benchmark: `34`
- Isolated environment:
  - `WORKDIR`:
    - `/root/work/cinderx-tomli-issue48-iso`
  - `DRIVER_VENV`:
    - `/root/venv-cinderx314-issue48`
  - `pyperformance venv`:
    - `/root/work/cinderx-tomli-issue48-iso/venv/cpython3.14-5c1b530ee639-compat-31b33d68c68a`
- Narrow benchmark configuration:
  - `JITLIST_ENTRIES=tomli._parser:skip_chars`
  - `AUTOJIT_JITLIST_ENTRIES=tomli._parser:skip_chars`
- Results:
  - targeted runtime regression:
    - `OK`
  - `tomli_loads` jitlist:
    - `3.6831124689997523 s`
  - `tomli_loads` autojit2:
    - `3.6588112600002205 s`
  - autojit compile summary:
    - `main_compile_count = 0`
    - `total_compile_count = 1`
    - `other_compile_count = 1`
  - autojit log confirms only:
    - `Finished compiling tomli._parser:skip_chars in 914µs, code size: 896 bytes`

## Updated decision
- The isolated environment removes the unrelated stdlib/enum compile crashes.
- With only `skip_chars` compiled, the patch no longer crashes under `autojit2`.
- Current isolated performance delta is small:
  - `3.6831 s` -> `3.6588 s`
  - about `0.7%` faster

## Round 3 main-workspace revalidation
- Remote workdir:
  - `/root/work/cinderx-tomli-issue48-main`
- Driver venv:
  - `/root/venv-cinderx314-issue48-main`
- Run id:
  - `20260320_000014`
- Standard remote entrypoint:
  - `scripts/arm/remote_update_build_test.sh`
- Parameters:
  - `BENCH=tomli_loads`
  - `AUTOJIT=2`
  - `JITLIST_ENTRIES=tomli._parser:skip_chars`
  - `AUTOJIT_JITLIST_ENTRIES=tomli._parser:skip_chars`
  - `SKIP_PYPERF_WORKER_PROBE=1`
  - targeted ARM runtime test only
- Results:
  - targeted runtime regression:
    - `OK`
  - jitlist:
    - `3.6337578909988224 s`
  - autojit2:
    - `3.7181417380015773 s`
  - compile summary:
    - `main_compile_count = 0`
    - `total_compile_count = 1`
    - `other_compile_count = 1`
  - compiled target from the autojit log:
    - `tomli._parser:skip_chars`
- Updated decision:
  - the main workspace now reproduces the isolated issue48 setup through the
    standard entrypoint without relying on the separate clean worktree
  - the functional fix is revalidated
  - the narrow benchmark effect remains small and noisy, so broader follow-up
    optimization work is still needed before calling this a performance win
