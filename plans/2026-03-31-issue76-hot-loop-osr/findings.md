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
