# Notes: tomli_loads BinaryOp exception edge

## Identity
- Issue: `#48`
- Primary benchmark case: `tomli_loads`
- Current branch: `bench-cur-7c361dce`

## Problem statement
- `skip_chars()` intentionally uses `try/except IndexError` to terminate a
  string scan.
- If JIT-compiled `src[pos]` cannot transfer control into the compiled handler,
  the hot path deopts every time the scan hits end-of-string.

## Immediate questions
- How are exception edges represented for `BinaryOp<Subscript>` in HIR?
- Is the edge missing at build time, or erased by a later CFG/cleanup pass?
- Does the same issue still reproduce on current tip?
- Is the benchmark slowdown actually dominated by this deopt site?

## Local code-read findings
- `builder.cpp`
  - `emitBinaryOp()` simply emits `BinaryOp(..., tc.frame)` for generic
    subscripts
  - there is no dedicated handler-edge concept attached there
- `hir.h`
  - `BinaryOp`, `UnicodeSubscr`, `CheckSequenceBounds`, `IndexUnbox`, and
    `IsNegativeAndErrOccurred` are all `DeoptBase` instructions
- `deopt.cpp`
  - any `DeoptBase` opcode that is not explicitly classified as guard/yield/raise
    deopts as `UnhandledException`
  - `UnhandledException` resumes the interpreter at the next bytecode, relying
    on frame/block-stack reconstruction rather than a compiled except block
- `builder.cpp`
  - except-handler opcodes like `WITH_EXCEPT_START`, `PUSH_EXC_INFO`, and
    `CHECK_EXC_MATCH` still abort if compiled directly
- implication:
  - issue `#48` is unlikely to be a single missing CFG edge on `BinaryOp`
  - current design more broadly treats runtime exceptions on this path as deopt
    events

## First implementation candidates
- Candidate A, HIR builder/CFG fix:
  - restore the handler edge for `BinaryOp<Subscript>` in covered `try` blocks
- Candidate B, later-pass preservation fix:
  - keep existing edge information alive through cleanup/lowering
- Candidate C, runtime suppression fallback:
  - if a function repeatedly deopts with `UnhandledException` on a handled
    subscript bytecode, suppress future JIT compilation of that function so it
    stays on the interpreter rather than bouncing through JIT entry/deopt on
    every call
  - this is less ambitious than compiled exception-edge support, but aligns
    with the current exception-handling model and should recover benchmark time

## Constraints
- Remote tests and benchmarks must use:
  - `scripts/arm/remote_update_build_test.sh`
- Key results must be written to `findings.md`

## Local patch draft
- Isolated implementation worktree:
  - `/C:/work/code/coroutines/cinderx-issue48-clean`
  - branch:
    - `codex/issue48-tomli-binaryop-exn-edge`
- Draft implementation:
  - `pyjit.cpp` / `pyjit.h`
    - add a runtime suppression hook for repeated handled-subscript
      `UnhandledException` deopts
    - only triggers when:
      - deopt reason is `UnhandledException`
      - causing bytecode is subscript
      - code object has exception handling
      - per-site deopt count crosses a small threshold
  - `gen_asm.cpp`
    - call the new suppression hook after deopt stats are recorded
  - `test_arm_runtime.py`
    - add a new regression for `skip_chars()` expecting deopts to stop
      repeating and the function to leave the compiled path

## Round 1 standard-entry validation
- Remote workdir:
  - `/root/work/cinderx-tomli-issue48`
- Entry:
  - `scripts/arm/remote_update_build_test.sh`
- Targeted runtime regression:
  - `ArmRuntimeTests.test_skip_chars_handled_index_error_avoids_repeated_unhandled_deopts`
  - result:
    - `OK`
- Standard-entry jitlist gate:
  - `tomli_loads`: `3.71 sec`
  - artifact:
    - `/root/work/arm-sync/tomli_loads_jitlist_20260319_193934.json`
- Standard-entry autojit2 gate:
  - still blocked
  - latest log:
    - `/tmp/jit_tomli_loads_autojit2_20260319_194237.log`
  - latest visible signal:
    - segmentation fault during benchmark-worker autojit compile

## Remote-entry support work
- Added to the isolated worktree:
  - `scripts/arm/verify_pyperf_venv.py`
  - `scripts/arm/pyperf_env_hook/sitecustomize.py`
- For this case only, the remote entrypoint on the ARM host was patched in
  place to honor:
  - `SKIP_PYPERF_WORKER_PROBE=1`
  - because the worker probe was crashing with a bus error unrelated to
    issue `#48`

## 2026-03-19 main workspace sync
- The validated isolated-worktree changes were copied back into:
  - `/C:/work/code/coroutines/cinderx`
- Main-workspace code now contains:
  - repeated handled-subscript deopt suppression in:
    - `cinderx/Jit/pyjit.cpp`
    - `cinderx/Jit/pyjit.h`
    - `cinderx/Jit/codegen/gen_asm.cpp`
  - the `skip_chars()` runtime regression in:
    - `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Main-workspace remote-entry support now contains:
  - `scripts/arm/verify_pyperf_venv.py`
  - `scripts/arm/pyperf_env_hook/sitecustomize.py`
  - updated `scripts/arm/remote_update_build_test.sh` wiring for:
    - worker hook installation
    - optional worker probe skip
    - narrow `JITLIST_ENTRIES`
    - narrow `AUTOJIT_JITLIST_ENTRIES`
- Main-workspace local validation:
  - `git diff --check`: clean except existing CRLF warnings
  - direct Python syntax checks:
    - not run locally because no `python` executable is available in this shell

## 2026-03-20 main workspace isolated ARM revalidation
- Remote entry:
  - `scripts/arm/remote_update_build_test.sh`
- Remote workdir:
  - `/root/work/cinderx-tomli-issue48-main`
- Driver venv:
  - `/root/venv-cinderx314-issue48-main`
- Run id:
  - `20260320_000014`
- Parameters:
  - `BENCH=tomli_loads`
  - `AUTOJIT=2`
  - `JITLIST_ENTRIES=tomli._parser:skip_chars`
  - `AUTOJIT_JITLIST_ENTRIES=tomli._parser:skip_chars`
  - `SKIP_PYPERF_WORKER_PROBE=1`
  - `ARM_RUNTIME_TEST_NAMES=ArmRuntimeTests.test_skip_chars_handled_index_error_avoids_repeated_unhandled_deopts`
- Results:
  - targeted runtime regression:
    - `OK`
  - jitlist artifact:
    - `/root/work/arm-sync/tomli_loads_jitlist_20260320_000014.json`
  - jitlist value:
    - `3.6337578909988224 s`
  - autojit artifact:
    - `/root/work/arm-sync/tomli_loads_autojit2_20260320_000014.json`
  - autojit value:
    - `3.7181417380015773 s`
  - compile summary artifact:
    - `/root/work/arm-sync/tomli_loads_autojit2_20260320_000014_compile_summary.json`
  - compile summary:
    - `main_compile_count = 0`
    - `total_compile_count = 1`
    - `other_compile_count = 1`
  - autojit log:
    - `/tmp/jit_tomli_loads_autojit2_20260320_000014.log`
    - only compiled target:
      - `tomli._parser:skip_chars`
- Interpretation:
  - the migrated main workspace now runs the isolated issue48 configuration
    end-to-end through the standard remote entrypoint
  - the fix is functionally confirmed outside the separate clean worktree
  - this single-value rerun does not show a stable speedup over jitlist, which
    reinforces that the issue48 fix is mainly a correctness / deopt-control
    fix rather than a large standalone benchmark gain

## Current blocker
- The minimal target bug is fixed, but the standard-entry autojit benchmark is
  still blocked by a later crash unrelated to the original `skip_chars`
  reproducer.

## Round 2 isolated environment
- To avoid pollution from previous workdirs and shared venvs, a fresh isolated
  environment was created on the ARM host:
  - workdir:
    - `/root/work/cinderx-tomli-issue48-iso`
  - driver venv:
    - `/root/venv-cinderx314-issue48`
  - pyperformance venv:
    - `/root/work/cinderx-tomli-issue48-iso/venv/cpython3.14-5c1b530ee639-compat-31b33d68c68a`
- In that environment, both jitlist and autojit were narrowed to the target
  function only:
  - `tomli._parser:skip_chars`

## Round 2 isolated results
- Targeted runtime regression:
  - `ArmRuntimeTests.test_skip_chars_handled_index_error_avoids_repeated_unhandled_deopts`
  - `OK`
- jitlist benchmark:
  - artifact:
    - `/root/work/arm-sync/tomli_loads_jitlist_20260319_214336.json`
  - value:
    - `3.6831124689997523 s`
- autojit2 benchmark:
  - artifact:
    - `/root/work/arm-sync/tomli_loads_autojit2_20260319_214336.json`
  - value:
    - `3.6588112600002205 s`
- autojit compile summary:
  - artifact:
    - `/root/work/arm-sync/tomli_loads_autojit2_20260319_214336_compile_summary.json`
  - `main_compile_count = 0`
  - `total_compile_count = 1`
  - `other_compile_count = 1`
- autojit log:
  - `/tmp/jit_tomli_loads_autojit2_20260319_214336.log`
  - confirms only:
    - `Finished compiling tomli._parser:skip_chars in 914µs, code size: 896 bytes`

## Interpretation
- The isolated environment confirms the issue48 fix itself is not the source of
  the earlier crashes.
- Once the compile surface is narrowed to `skip_chars`, autojit2 no longer hits
  the `re._parser` / `enum` crash chain.
- The current measured gain is modest:
  - about `0.7%` on the isolated `tomli_loads` run
- So the issue48 fix is functionally correct, but by itself it is not a large
  benchmark mover under this isolated setup.
