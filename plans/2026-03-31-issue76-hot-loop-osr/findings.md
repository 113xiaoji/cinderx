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
