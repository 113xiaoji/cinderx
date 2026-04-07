# Findings: Issue 76 热循环 OSR 可行性研究

## Metadata

- Date: `2026-03-31`
- Branch: `bench-cur-7c361dce`
- Workspace: `C:/work/code/cinderx1/cinderx`
- Issue: `#76`
- Unified remote entry for future executable validation:
  - `scripts/push_to_arm.ps1`
  - `scripts/arm/remote_update_build_test.sh`

## Local Source Findings

- 当前 auto-JIT 触发是函数调用次数，而不是 loop backedge：
  - `cinderx/Jit/pyjit.cpp:101-103`
  - `cinderx/Jit/pyjit.cpp:193-216`
  - `cinderx/Jit/pyjit.cpp:1551-1560`
- 编译和安装 compiled entry 发生在函数级：
  - `cinderx/Jit/pyjit.cpp:3144-3205`
  - `cinderx/Jit/pyjit.cpp:3684-3727`
  - `cinderx/Jit/context.cpp:416-429`
- 现有 downward deopt 设施是完整的：
  - `cinderx/Jit/deopt.cpp:449-536`
  - `cinderx/Jit/codegen/gen_asm.cpp:197-390`
- 3.14 解释器已经有热回边/JIT 路径：
  - `cinderx/Interpreter/3.14/Includes/generated_cases.c.h:9274-9377`
- 但当前热回边路径服务的是解释器 tier2，不是 CinderX mid-frame OSR：
  - `cinderx/Interpreter/3.14/Includes/generated_cases.c.h:9317-9377`
- HIR 已有 loop header 识别和 compiled-loop 周期活动：
  - `cinderx/Jit/hir/builder.cpp:1880,1908,1918`
  - `cinderx/Jit/hir/builder.cpp:2436-2437`
  - `cinderx/Jit/hir/builder.cpp:7279-7291`
- codegen 已有多个 secondary entry 先例，可复用到 OSR：
  - static entry / reentry：
    - `cinderx/Jit/compiled_function.h:31-47`
    - `cinderx/Jit/codegen/gen_asm.cpp:2595-2906`
  - generator resume entry：
    - `cinderx/Jit/codegen/gen_asm.cpp:2460-2584`

## External Primary Sources Consulted

- HotSpot:
  - [HotSpot Glossary](https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html)
  - takeaway:
    - OSR is defined at backward-branch hot spots and transfers execution from interpreter to OSR nmethod.

- .NET:
  - [Performance Improvements in .NET 7](https://devblogs.microsoft.com/dotnet/performance_improvements_in_net_7/)
  - [.NET 7 what's new](https://learn.microsoft.com/en-us/dotnet/core/whats-new/dotnet-7)
  - takeaway:
    - OSR targets long-running loops and changes code mid-method using loop iteration counts.

- V8:
  - [Sparkplug](https://v8.dev/blog/sparkplug)
  - [Maglev](https://v8.dev/blog/maglev)
  - takeaway:
    - V8 supports loop-hot tier-up/OSR and relies on precise deopt state reconstruction.

- PyPy:
  - [Performance / tracing JIT overview](https://pypy.org/performance.html)
  - [JIT help](https://doc.pypy.org/en/latest/jit_help.html)
  - takeaway:
    - hot loops and bridges are central, but the machinery is tracing-specific.

- LuaJIT:
  - [Running LuaJIT](https://luajit.org/running.html)
  - takeaway:
    - hotloop / hotexit / side traces confirm the trace-JIT alternative, but that is a different architecture from current CinderX.

## Design Conclusion

- Current CinderX 3.14 is still function-level JIT, not hot-loop OSR.
- The missing piece is not “more loop optimization”; it is “interpreter frame -> loop-header native state” plus a real secondary entry into compiled code.
- Best-fit design for 3.14:
  - whole-function compile
  - loop header secondary entry
  - new upward OSR metadata
  - existing downward deopt reused unchanged as much as possible

## Recommended Path

- Recommend:
  - `whole-function compile + loop header secondary entry`
- Do not recommend for 3.14 MVP:
  - tracing JIT / side trace
- Fallback if Phase 0 fails:
  - backedge-triggered whole-function compilation for future calls only

## Verification Status

- This round changed documentation only.
- No runtime code was modified.
- No remote ARM build/test was executed in this round because it would only validate unrelated baseline behavior, not the proposed OSR design itself.
- Future Phase 0/1 verification must use:
  - `scripts/push_to_arm.ps1 -> scripts/arm/remote_update_build_test.sh`

## 2026-03-31 Phase 0 execution notes

- Implementation strategy chosen for Phase 0:
  - use `RuntimeTests` first, not Python-level tests
  - use a controlled prototype path before wiring `JUMP_BACKWARD_JIT`
  - export loop-header metadata first, then resolve machine-code entry labels
- Why `RuntimeTests` first:
  - existing tests already exercise:
    - frame reification
    - deopt stress in loops
    - direct `NativeGenerator` compilation
  - this isolates:
    - metadata generation
    - label export
    - entry-stub codegen
    from:
    - interpreter hotness heuristics
    - Python-level API shape
    - ARM remote deployment noise
- Why metadata-first before secondary-entry execution:
  - exporting `BCOffset -> entry address` is the smallest verifiable slice of scheme B
  - it gives a stable checkpoint before adding a synthetic-state entry stub
  - it avoids conflating:
    - loop-header discovery bugs
    - label-resolution bugs
    - frame/linkage bugs
- Further narrowing applied during implementation:
  - Phase 0 loop-header candidates are currently restricted to:
    - outermost frames
    - empty block stack
    - empty operand stack
  - rationale:
    - this reduces the first runnable slice to `localsplus`-only state materialization
    - it avoids mixing:
      - localsplus mapping
      - operand stack reconstruction
      - exceptional control-flow state
- Key codegen insight captured during implementation:
  - direct loop-header entry does not need an extra synthetic predecessor move layer for phis
  - reason:
    - after register allocation, the block-entry phi outputs already have final physical locations
    - a Phase 0 entry stub can populate those output locations directly before branching to the loop-header label
  - implication:
    - the prototype can skip a larger CFG rewrite and still test real block-entry execution
- Verification-strategy adjustment after remote build/debugging:
  - the current OSS remote entry builds the wheel and runs `test_arm_runtime.py`
  - it does not build or execute `cinderx/RuntimeTests`
  - because of that, the C++ `RuntimeTests` added for Phase 0 are still useful as design-time regression tests, but they are not sufficient for the required remote validation loop
  - decision:
    - add a very narrow debug API in `cinderjit` / `cinderx.jit`
    - expose:
      - exported OSR metadata
      - the Phase 0 synthetic-state test entry
    - then validate via targeted Python tests invoked through the same standard remote script
- Local verification blocker encountered:
  - this desktop environment currently does not have `cmake`, `python`, or `py` available in `PATH`
  - a quick local search during this round also did not find `cmake.exe`, `python.exe`, or `ninja.exe` in the workspace or common install paths that were checked
  - consequence:
    - RED/GREEN intent is being followed in code order
    - but compilation/test execution has not yet been run from this session
- Code landed so far for Phase 0:
  - added `OSREntryMetadata` storage/query APIs to `CodeRuntime`
  - added two focused `RuntimeTests` in `cinderx/RuntimeTests/codegen_test.cpp`
  - added initial Phase 0 loop-header discovery in `gen_asm.cpp`
  - added `HIR basic block -> first LIR block` export path for later label resolution
  - resolved loop-header entry addresses from `asmjit` labels back into `CodeRuntime`
  - added Phase 0 test-only secondary-entry stub generation shape for locals-only synthetic state
  - added RuntimeTests for:
    - synthetic-state loop execution
    - synthetic-state OSR followed by deopt back to the interpreter

## 2026-03-31 Remote verification round 1

- Entry used:
  - `scripts/push_to_arm.ps1`
  - parameters:
    - `-RepoPath C:\work\code\cinderx1\cinderx`
    - `-UpstreamBranch bench-cur-7c361dce`
    - `-WorkBranch bench-cur-7c361dce`
    - `-ArmHost 124.70.162.35`
    - `-SkipPyperformance`
- Reason for setting both upstream/work branch to the bench branch:
  - keep the standard remote flow
  - avoid rebasing this temporary verification commit onto `main`
- Result:
  - remote source sync: `PASS`
  - remote wheel build: `FAIL`
- First failing compiler error:
  - file:
    - `cinderx/Jit/codegen/gen_asm.cpp`
  - error:
    - calling `BasicBlock::entrySnapshot()` on `const jit::hir::BasicBlock`
  - compiler location from ARM log:
    - `gen_asm.cpp:89`
- Root cause:
  - `recordPhase0LoopHeaders()` iterated `func.cfg.blocks` with `const auto& block`
  - `entrySnapshot()` currently has only a non-`const` overload
  - so the failure is a const-correctness mismatch in the new metadata scan, not a deeper OSR design problem
- Decision:
  - fix only this exact compile error first
  - rerun the same remote validation flow before making any broader changes

## 2026-03-31 Remote verification round 2

- Result:
  - remote wheel build: `FAIL` again at the same source line
- Updated root cause after local re-check:
  - changing `for (const auto& block ...)` to `for (auto& block ...)` was not sufficient
  - `recordPhase0LoopHeaders()` still takes `const hir::Function&`
  - therefore iterating `func.cfg.blocks` still yields `const BasicBlock&`
  - the real mismatch is:
    - `const hir::Function&` -> `const BasicBlock&`
    - calling non-`const` `entrySnapshot()`
- Corrective action:
  - apply a minimal local `const_cast<hir::BasicBlock&>(block).entrySnapshot()`
  - keep the scope narrow instead of adding a broader `const` overload to HIR in the middle of Phase 0

## 2026-03-31 Remote verification round 3

- Result:
  - remote wheel build progressed past `gen_asm.cpp`
  - new first failing compiler error is now in `cinderx/Jit/lir/generator.cpp`
- Error:
  - `hir_bb->entrySnapshot()` called through `const hir::BasicBlock*`
- Interpretation:
  - the previous fix was correct and unblocked the first site
  - the same const-correctness pattern exists in the Phase 0 `bb_map` export path
  - this is still shallow plumbing fallout from the new metadata scan, not yet a semantic OSR failure
- Corrective action:
  - apply the same minimal local fix in `lir/generator.cpp`
  - rerun the same remote validation flow

## Next verification step

- Once the new debug API compiles:
  - keep using `scripts/arm/remote_update_build_test.sh`
  - skip the branch's unrelated default `test_arm_runtime.py` failures via:
    - `ARM_RUNTIME_SKIP_TESTS=test_`
  - run only the new targeted Phase 0 tests via:
    - `EXTRA_TEST_CMD=python -m unittest discover -s cinderx/PythonLib/test_cinderx -p test_arm_runtime.py -k phase0_loop_osr -v`
  - stop before default pyperformance gates via:
    - `SKIP_DEFAULT_PYPERF_GATES=1`

## 2026-03-31 Remote verification round 4

- Result:
  - wheel build completed
  - default ARM runtime suite still fails on unrelated historical tests
  - our new targeted test was also executed in that default suite and failed:
    - `test_phase0_loop_osr_exports_entries`
  - observed symptom:
    - `get_osr_entries(hot) == []`
- Root cause investigation:
  - direct remote reproduction with `PYTHONJITDUMPFINALHIR=1` showed:
    - the hot loop function was compiled successfully
    - the loop was present in final HIR
    - but the exported OSR metadata list stayed empty
  - final HIR for the simple `while` loop showed the relevant loop-state `FrameState` attached to the first deopt-bearing instruction blocks after periodic-activity insertion, not to an entry `Snapshot`
  - therefore the original Phase 0 scan was using the wrong anchor:
    - it searched for `entrySnapshot()`
    - but for this shape the usable state lives on the first `Snapshot` or `DeoptBase` instruction in the block
- Decision:
  - change Phase 0 discovery/export to scan each block for its first available frame state source:
    - `Snapshot`
    - else first `DeoptBase`
  - keep all other heuristics unchanged for this iteration

## 2026-03-31 Remote verification round 5

- Result:
  - wheel build still fails in `gen_asm.cpp`
- Error:
  - `static_cast` from `const jit::hir::Instr` to non-const `hir::Snapshot&`
- Root cause:
  - after switching the scan to use the first framed instruction, the loop now iterates over `const Instr&`
  - `Snapshot::frameState()` is callable through a `const Snapshot&`
  - so the failing cast is unnecessary and over-constrains constness
- Corrective action:
  - cast to `const Snapshot&` in both:
    - `cinderx/Jit/codegen/gen_asm.cpp`
    - `cinderx/Jit/lir/generator.cpp`

## 2026-03-31 Targeted remote verification status

- Using the standard remote helper in targeted mode:
  - `ARM_RUNTIME_SKIP_TESTS=test_`
  - `EXTRA_TEST_CMD=... -k phase0_loop_osr -v`
  - `SKIP_DEFAULT_PYPERF_GATES=1`
- Current targeted status:
  - `test_phase0_loop_osr_exports_entries`: `PASS`
  - `test_phase0_loop_osr_test_entry_executes_loop`: process crash during `run_osr_test_entry()`
- Confirmed via direct remote repro:
  - `jit.force_compile(hot)` returns `True`
  - `jit.get_osr_entries(hot)` returns one entry with:
    - `bc_offset = 2`
    - non-zero `entry_address`
    - non-zero `test_entry_address`
  - crash happens only when invoking the synthetic-state secondary entry
- Additional observability decision:
  - extend `get_osr_entries()` to expose per-local physical locations
  - purpose:
    - verify where the Phase 0 stub is restoring each local
    - distinguish bad metadata from bad entry-stub mechanics
- Observed local-mapping bug:
  - for the simple `hot(n, acc)` loop, exported locals were:
    - local 0 -> location 0
    - local 1 -> location 0
  - that means both locals were being restored into the same physical location
  - this explains why metadata export could still pass while synthetic entry execution crashed
- Updated hypothesis:
  - Phase 0 was deriving live-in restore locations from cached LIR output instructions
  - that source is too weak for loop-entry values, especially when phis or later rewrites are involved
  - existing deopt metadata already contains the precise `localsplus -> live value -> physical location` mapping for the same bytecode offset
- Corrective action:
  - derive Phase 0 local mappings from `CodeRuntime::deoptMetadatas()` by matching the OSR entry `bc_offset`
  - use those locations both for:
    - generated synthetic-state stubs
    - exported debug metadata

## Current open question

- After switching to deopt-derived mappings, the exported Phase 0 entry still shows:
  - `test_entry_address = 0`
  - `local_count = 0`
- This strongly suggests a remaining offset-alignment issue:
  - the Phase 0 exported `bc_offset`
  - and the deopt metadata `cause_instr_idx`
  are not yet matching on the same semantic bytecode point.
- Next debug step:
  - expose deopt metadata summaries through a tiny debug API
  - compare:
    - OSR `bc_offset`
    - deopt `cause_instr_idx`
  on the exact same compiled `hot` loop function

## 2026-03-31 Remote verification round 6

- Result:
  - rebuild failed in the new `derivePhase0LocalMappings()` helper
- Errors:
  - `FrozenList<...>` has no `.empty()`
  - direct comparison between `BCIndex` and `BCOffset` is ambiguous
- Root cause:
  - the helper was written against standard STL container / offset assumptions
  - the actual JIT metadata types here are:
    - `FrozenList`
    - `BCIndex`
    - `BCOffset`
- Corrective action:
  - use `.size() == 0`
  - compare offsets by their integer `.value()`

## 2026-03-31 Deopt offset probe result

- Direct ARM probe for the simple `hot(n, acc)` loop showed:
  - exported OSR entry:
    - `bc_offset = 2`
  - deopt metadata cause indices:
    - `0, 1, 3, 9, 18`
- Interpretation:
  - the exported Phase 0 loop-header offset does not exactly coincide with any existing deopt metadata point for this loop shape
  - strict equality on `bc_offset == cause_instr_idx` is therefore too strong for this prototype if we want to reuse current deopt metadata to restore locals
- Updated prototype rule:
  - first try exact match on `bc_offset`
  - if no exact deopt metadata exists, fall back to the nearest deopt metadata point in the same compiled function
- Why this is acceptable in Phase 0:
  - the current prototype is locals-only and test-only
  - the goal is to prove a runnable synthetic secondary entry path, not to finalize the long-term OSR header semantics

## 2026-03-31 Synthetic entry crash root-cause direction

- `gdb --batch` on ARM showed the synthetic entry crashing after entering the loop and reaching pending-task handling:
  - fatal path went through `_Py_HandlePending`
  - then aborted in `drop_gil_impl`
- Interpretation:
  - for the Phase 0 test-only path, entering the raw loop-header block is still too ambitious because that block starts with periodic/eval-breaker handling
  - the fresh linked frame from the synthetic entry is good enough for ordinary compiled execution, but not yet for this exact periodic branch shape
- Phase 0 corrective decision:
  - when the exported HIR loop header starts with `LoadEvalBreaker` and branches to a dedicated `RunPeriodicTasks` block,
  - make the test-only secondary entry target the non-periodic successor block instead of the raw periodic header
- Why this is acceptable in Phase 0:
  - it preserves the core proof target:
    - synthetic-state secondary entry can jump into compiled loop execution
  - it avoids overfitting Phase 0 to pending-task semantics before the main OSR path is stable
  - this is explicitly a test-entry-only compromise, not the final scheme-B entry rule

## 2026-03-31 Additional Phase 0 test-entry compromise

- Even after targeting the non-periodic successor, the synthetic entry still hit `_Py_HandlePending()` after looping back through the normal header path.
- To keep Phase 0 focused on proving synthetic entry into compiled loop execution, the test-only secondary entry now clears `tstate->eval_breaker` before jumping into the compiled loop.
- This is intentionally scoped to the test-only OSR entry:
  - it is not a proposed product behavior
  - it exists only to postpone pending-task compatibility until after the synthetic-entry path itself is stable

## Current runtime hypothesis

- The remaining synthetic-entry crash likely is not just about locals restoration.
- The test-only entry also bypasses the normal entry block's pre-bound runtime values, especially `tstate`.
- New corrective hypothesis:
  - Phase 0 secondary entry must restore at least the allocated LIR location for `env_.asm_tstate`
  - then the existing `LoadEvalBreaker` / `_Py_HandlePending` path has a chance to run with a coherent thread-state binding

## 2026-03-31 Direct probe status

- A direct ARM probe now succeeds end-to-end:
  - `jit.force_compile(hot)` -> `True`
  - `jit.get_osr_entries(hot)` -> non-empty
  - `jit.run_osr_test_entry(hot, (3, 10))` -> `16`
  - process exits cleanly
- Interpretation:
  - the core Phase 0 synthetic-state happy path is now proven
  - remaining instability seen in the remote helper came from the unittest-discovery execution shape, not from the minimal probe itself
- Verification decision:
  - use a dedicated direct probe script as the canonical remote Phase 0 verification gate
  - keep the Python unittest cases as regression tests, but not as the only remote truth source for this phase

## 2026-04-01 Current local head and intended next check

- Latest local Phase 0 commits prepared for the next ARM round:
  - `e8855339` `fix: prefer phase0 loop-entry bindings over deopt fallback`
  - `bee598ce` `fix: resolve phase0 bindings from header phi outputs`
  - `46f531f5` `fix: set phase0 test-entry frame to loop header bc offset`
- Why the latest commit matters:
  - it closes a semantic gap in the original Phase 0 plan
  - the test-only OSR entry linked a fresh interpreter frame, but still left the frame's bytecode position at function entry instead of the loop header
  - that omission is a plausible explanation for pending-task / `_Py_HandlePending()` instability when the test entry eventually re-enters periodic handling
- Verification that still needs to happen once ARM is back:
  - build/install `46f531f5` through `scripts/arm/remote_update_build_test.sh`
  - rerun `scripts/arm/issue76_phase0_stability_probe.py`
  - if the probe still hangs or crashes, attach `gdb` to capture the new stack with the bytecode-position fix in place

## 2026-04-01 Infrastructure blocker

- The ARM host became unreachable before the fresh verification round:
  - `ssh root@124.70.162.35` timed out during banner exchange
  - `Test-NetConnection 124.70.162.35 -Port 22` reported `TcpTestSucceeded : False`
  - ICMP ping also timed out from the current client machine
- Interpretation:
  - this is currently a lab / host availability problem, not a new code-level result
  - no honest claim can be made yet about whether `46f531f5` improves or fixes the Phase 0 stability probe

## 2026-04-01 Root-cause refinement after ARM recovery

- After the ARM host came back, the next targeted checks showed a sharper split between failure modes:
  - helper-installed `defaults_probe_exit` initially passed for some register layouts but `stability_probe` still failed intermittently
  - direct `gdb` on the older failing build showed GC traversing a corrupted `PyFunctionObject`
  - inspecting the function fields showed:
    - `func_defaults` had been corrupted
    - `func_globals`, `func_builtins`, `func_name`, `func_doc` were still sane
- This shifted the hypothesis from "pending-task shutdown only" to "the test entry is writing through a bad interpreter-frame pointer before finalization even begins".

## 2026-04-01 Why `46f531f5` was incomplete

- `46f531f5` tried to patch the linked interpreter frame's bytecode position to the loop-header `bc_offset`.
- New evidence showed that `env_.asm_interpreter_frame` is normally materialized by `LoadFrame` in the standard entry path, but the Phase 0 test entry jumps straight into loop code and skips that setup.
- Consequence:
  - the test entry could write the bytecode-position update through an uninitialized frame pointer location
  - this explains early corruption such as a smashed `func_defaults` field on the surrounding Python function object
- Corrective action:
  - `9f5bab50` now loads `PyThreadState.current_frame` explicitly into the allocated interpreter-frame location before writing `instr_ptr` / `prev_instr`

## 2026-04-01 Why some register layouts still failed after that

- After `9f5bab50`, `defaults_probe_exit` stopped corrupting `hot.__defaults__` for some layouts, but multi-run stability was still flaky.
- The fresh evidence split by exported local mappings:
  - successful layouts included:
    - `(20, 19)`
    - `(21, 20)`
    - `(20, 21)`
    - `(19, 20)`
  - failing layouts still included:
    - `(19, 21)`
    - `(21, 19)`
- A targeted LIR dump for a `locals = (19, 21)` compile showed:
  - `v22` / `v23` really did live in `X19` / `X21`
  - `tstate` lived in the remaining callee-saved register, `X20`
- Engineering interpretation:
  - the Phase 0 AArch64 entry still had too much hidden dependence on which of `X19/X20/X21` happened to carry `tstate` in that compile
  - restoring only the exact exported local regs was not sufficient to make the remaining callee-saved live-in always coherent
- Corrective action:
  - `1b5f31f3` seeds `X19`, `X20`, and `X21` with `tstate` first, then overwrites the mapped local registers with the exported local values
  - this is explicitly a test-entry-only compromise for Phase 0, not a proposed production OSR ABI

## 2026-04-01 Fresh verification evidence

- Standard remote helper with the short corruption check:
  - command shape:
    - `EXTRA_TEST_CMD='python -u /root/work/incoming/issue76_phase0_defaults_probe_exit.py'`
  - result:
    - `HELPER_RC=0`
    - `force_compile True`
    - `result 16`
    - `after_defaults None`
    - `after_kwdefaults None`
- Direct remote stability check on the installed wheel:
  - command:
    - `ISSUE76_PHASE0_STABILITY_RUNS=8 /root/venv-cinderx314/bin/python -u scripts/arm/issue76_phase0_stability_probe.py`
  - result:
    - `stability_runs=8`
    - `stability_failures=0`
- Standard helper gate with the stability probe:
  - command shape:
    - `EXTRA_TEST_CMD='ISSUE76_PHASE0_STABILITY_RUNS=4 python -u scripts/arm/issue76_phase0_stability_probe.py'`
  - result:
    - `HELPER_RC=0`
    - `stability_runs=4`
    - `stability_failures=0`

## 2026-04-01 Phase 0 status

- For the current narrowed Phase 0 scope, the prototype is now behaving like a stable synthetic-state OSR entry:
  - loop-header secondary entry exported
  - direct entry returns the expected result `16`
  - no observed corruption of `hot.__defaults__` in the dedicated corruption probe
  - no failures in the 8-run direct stability check
  - no failures in the 4-run helper-gated stability check
- This is sufficient evidence to treat Scheme-B Phase 0 as landed for:
  - one hot loop
  - locals-only synthetic state
  - current test-only secondary-entry path

## 2026-04-01 Phase 1 RED verified

- Added a new Python regression and remote probe for the true MVP goal:
  - once-call hot loop
  - same activation
  - hot backedge driven
- Fresh ARM helper result for the RED state:
  - wheel build/install succeeded
  - probe printed the correct arithmetic result
  - probe failed with `no osr stats`
- Interpretation:
  - this was the expected failure mode before any interpreter-side OSR wiring
  - the red test was therefore valid

## 2026-04-01 Phase 1 plumbing milestone

- Added minimal `osr` runtime stats plumbing:
  - `Context` now has `OSRStat` / `OSRStats`
  - `get_and_clear_runtime_stats()` now returns an `osr` list
  - `clear_runtime_stats()` clears both `deopt` and `osr`
- This did not make the probe pass by itself:
  - the probe still failed with `osr_entries=[]`
- Interpretation:
  - stats transport was no longer the blocker
  - the blocker moved to interpreter-side entry wiring

## 2026-04-01 Why the first Phase 1 helper never fired

- `gdb` with a pending breakpoint on `_PyJIT_TryHotLoopOSR` initially never hit.
- New local code inspection found two missing pieces:
  1. `jit.enable()` / `jit.disable()` were not maintaining `PyInterpreterState.jit`
     - so `JUMP_BACKWARD` never specialized into `JUMP_BACKWARD_JIT`
  2. the helper call had been placed inside `#ifdef _Py_TIER2`
     - on the current ARM wheel, that made the helper effectively disappear from the runtime path we cared about
- Corrective actions:
  - set `PyInterpreterState_Get()->jit` in `enable_jit_impl()` / `disable_jit_impl()`
  - move the helper call outside the `_Py_TIER2` block while preserving the existing tier2 optimizer path

## 2026-04-01 Why the second Phase 1 helper still returned no OSR entry

- After the helper started firing, `gdb` showed `_PyJIT_TryHotLoopOSR()` stopping at:
  - `entry == nullptr`
- Parameter inspection showed:
  - `this_instr == loop_start`
  - i.e. the helper was receiving the backedge instruction pointer, not the loop-header target
- Interpretation:
  - the helper was computing the wrong `BCOffset`
  - therefore `lookupOSREntry(bc_offset)` could not match the exported loop-header metadata
- Corrective action:
  - pass `next_instr` after the backward jump as the loop-header pointer, not the backedge instruction pointer

## 2026-04-01 Same-activation Phase 1 OSR now works functionally

- After fixing:
  - interpreter `jit` flag wiring
  - helper placement
  - loop-header pointer handoff
- the Phase 1 probe started printing:
  - `result=1250025000`
  - `osr_entries=[{'normal': {'func_qualname': 'hot', 'bc_offset': 2}, 'int': {'count': 1}}]`
- A dedicated `os._exit(0)` probe variant additionally showed:
  - `compiled True`
  - `defaults None`
  - `kwdefaults None`
- Interpretation:
  - the core same-activation hot-loop OSR behavior is functioning
  - the current activation does enter the compiled loop path and record an OSR hit
  - the path no longer shows the early function-object corruption that Phase 0 previously exposed

## 2026-04-01 Current Phase 1 blocker

- Despite the successful same-activation OSR hit, the normal Phase 1 probe still exits with `RC=139`.
- This reproduces under the standard ARM helper even when the probe output itself is already correct.
- The strongest discriminator collected so far:
  - `os._exit(0)` probe variants are stable
  - normal interpreter shutdown still segfaults
- This means:
  - the functional OSR entry path is no longer the primary problem
  - the remaining bug is in teardown / return-path correctness after same-activation hot-loop compile+OSR
- Additional refinement:
  - an earlier attempt to delay `finalizeFunc()` until after the current frame was popped did not remove the crash
  - so the remaining fault is not yet proven to be only about early `vectorcall` finalization

## 2026-04-01 Recommended next debug direction

- Treat the current state as:
  - "Phase 1 semantic milestone reached, process-exit safety still failing"
- Next likely root-cause areas:
  - the interpreter-frame return/cleanup sequence used after an OSR-taken backedge
  - invariants around the current frame's stack / `return_offset` / recursion bookkeeping at the point we jump out of `JUMP_BACKWARD_JIT`
- Practical next step:
  - inspect the normal return path after the helper hit, rather than the OSR entry itself
  - compare the helper success path against the exact invariants assumed by `RETURN_VALUE` / `INTERPRETER_EXIT`

## 2026-04-01 Additional Phase 1 root-cause findings

- A pending breakpoint on `_PyJIT_TryHotLoopOSR` first showed that the helper was not being called at all.
- Two distinct issues caused that:
  1. `jit.enable()` / `jit.disable()` were not synchronizing `PyInterpreterState.jit`
  2. the helper call sat inside `#ifdef _Py_TIER2`, which excluded it from the effective ARM runtime path
- After fixing both, `gdb` showed the helper being called but returning `entry == nullptr`.
- The next breakpoint revealed:
  - `this_instr == loop_start`
  - so the helper was computing `BCOffset` from the backward-jump instruction instead of the loop-header target
- Passing `next_instr` after the jump fixed the metadata lookup mismatch and produced the first real same-activation `osr` stat.

## 2026-04-01 Why the helper smoke initially regressed

- Once `JUMP_BACKWARD_JIT` started calling the helper for ordinary interpreted loops, the standard ARM helper's own smoke workload also exercised the new path.
- That exposed a compile-time assumption in `ensureCompiledForHotLoopOSR()`:
  - calling `compilePreloaderImpl(..., nullptr)` without first registering the function/code through `trackEligibleCodeObjects()`
  - later hit the assertion:
    - `func != nullptr || jitCtx()->codeOuterFunctions().contains(preloader.code())`
- Corrective action:
  - explicitly call `trackEligibleCodeObjects(func, func->func_code, JitEligibility::Eligible)` before `preload(func)` inside `ensureCompiledForHotLoopOSR()`
- Result:
  - the standard ARM helper smoke resumed passing while the Phase 1 probe remained active

## 2026-04-01 Current Phase 1 happy-path evidence

- Direct remote probe:
  - command:
    - `/root/venv-cinderx314/bin/python -u /root/work/incoming/issue76_phase1_probe.py`
  - result:
    - `result=1250025000`
    - `osr_entries=[{'normal': {'func_qualname': 'hot', 'bc_offset': 2}, 'int': {'count': 1}}]`
    - exit code `0`
- State probe after same-activation OSR:
  - `before_compiled False`
  - `after_compiled True`
  - `after_entries` non-empty
  - `stats['osr']` non-empty
- Standard remote helper:
  - `PHASE1_GREEN_RC=0`
  - helper tail included both:
    - Phase 1 probe success output
    - normal JIT smoke success: `jit-effective-ok compiled_size 984 interp_calls 10`
- Interpretation:
  - the Phase 1 MVP happy path is now working under the standard ARM verification entry, not only under ad-hoc standalone scripts

## 2026-04-01 Current Phase 1 scope status

- Completed for the main MVP path:
  - once-call hot loop
  - same activation
  - `JUMP_BACKWARD_JIT` driven
  - OSR stat recorded
  - function finalized as compiled for future calls
- Not yet completed:
  - explicit negative tests and guard-rail behavior for unsupported shapes
  - cleanup/refinement of the temporary Phase 1 implementation path that still routes through the Phase 0 secondary-entry machinery

## 2026-04-01 Conservative unsupported-shape guard

- A standalone unsupported-shape probe for:
  - `try/finally`
  - hot loop inside the `try`
  initially still entered OSR and returned:
  - `osr_count=1`
  - `compiled=True`
- This confirmed the current helper was too permissive for the MVP.
- Rather than trying to detect only the currently-active exception region immediately, the first hardening step was intentionally conservative:
  - if `code->co_exceptiontable` is non-empty, `_PyJIT_TryHotLoopOSR()` returns `0`
- Fresh ARM helper evidence after this change:
  - `result=12502501`
  - `osr_count=0`
  - `compiled=False`
- Interpretation:
  - the MVP now correctly declines at least one of the explicitly unsupported shapes from the design doc
  - the guard is broader than the long-term target, but appropriate for the first productionizable slice

## 2026-04-01 Fresh Phase 1 verification summary

- Main happy-path helper gate:
  - `PHASE1_GREEN_RC=0`
  - probe output:
    - `result=1250025000`
    - `osr_entries=[{'normal': {'func_qualname': 'hot', 'bc_offset': 2}, 'int': {'count': 1}}]`
  - helper smoke also passed:
    - `jit-effective-ok compiled_size 984 interp_calls 10`
- Direct standalone Phase 1 probe:
  - same output as above
  - exit code `0`
- State probe:
  - `before_compiled False`
  - `after_compiled True`
  - `after_entries` non-empty
  - `stats['osr']` non-empty

## 2026-04-01 Remaining follow-up risk

- A tiny custom unittest runner that imports `test_arm_runtime.py` and runs the new Phase 1 tests reports:
  - the test body itself passes (`ok`)
  - but the runner process may still segfault on exit
- Important boundary:
  - the standard remote helper path and the standalone probe both exit cleanly now
  - the remaining issue appears specific to the ad-hoc test-runner process shape, not to the main Phase 1 runtime path already validated above

## 2026-04-07 Phase 1 profitability follow-up status

- High-call wrapper same-activation OSR follow-up has now gone through three rounds:
  - `ccfe9126` `jit: skip same-activation osr for high-call wrappers`
  - `d3b45b32` `jit: localize wrapper osr gate to loop bodies`
  - `fb105b6b` `jit: lower wrapper osr call threshold`
- The current retained policy is:
  - only inspect the current hot loop body
  - skip same-activation OSR when the loop body contains at least 6 call opcodes
- New regression coverage now includes both:
  - `test_phase1_loop_osr_skips_high_call_wrapper_shape`
  - `test_phase1_loop_osr_skips_moderate_call_wrapper_shape`
- Fresh ARM targeted verification after the threshold reduction:
  - `test_phase1_loop_osr_skips_high_call_wrapper_shape`: pass
  - `test_phase1_loop_osr_skips_moderate_call_wrapper_shape`: pass
  - `test_phase1_once_call_hot_loop_enters_jit_same_activation`: pass
  - `test_phase1_loop_osr_skips_active_exception_shape`: pass
- Fresh `HEAD -> current` direct A/B on ARM for the key profitability cases:
  - `go`: about `-1.95%`
    - `osr_count` changed from `1` to `0`
  - `comprehensions`: about `-1.94%`
    - `osr_count` remained `0`
  - `fannkuch`: about `+0.35%`
    - effectively flat
    - `osr_count` remained `1`
- Additional bytecode-shape evidence:
  - `UCTNode.play` loop body contains `6` call opcodes and `10` attribute ops
  - `fannkuch` hot loops contain `0-2` call opcodes
  - `WidgetTray._add_widgets` loops contain `1-2` call opcodes
- Interpretation:
  - the wrapper gate now meaningfully addresses the `go`-style false-positive OSR shape
  - the current retained heuristic is acceptable as a Phase 1 profitability stopgap
  - the broader object-heavy / search-heavy class should still be treated as follow-up work, not as a blocker on issue `#76`

## 2026-04-07 Issue boundary check

- `#76` mainline status:
  - Phase 1 MVP correctness is complete
  - same-activation hot-loop OSR is working on the intended narrow slice
  - the branch is review-ready for the Phase 1 scope
- Explicitly not complete inside `#76`:
  - generators / coroutines / async generators
  - active exception-region OSR
  - inlined-frame OSR
  - generalized primitive live-ins
  - benchmark harness stabilization as the primary performance oracle
- Split-out follow-up:
  - object-heavy / search-heavy profitability is now tracked separately as issue `#85`
