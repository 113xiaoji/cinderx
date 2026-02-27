# Branch Optimizations vs Upstream Main (Design)

Date: 2026-02-27
Target branch: `bench-cur-7c361dce`
Upstream baseline: `facebookincubator/cinderx` `main` at `9e6a3cc92794de3cb8caaa698cb0861fc02a11d2`

## Objective
Document the optimization ideas currently carried by this branch, clarify why they improve ARM behavior on Python 3.14, and define a stable path to keep these gains while syncing with upstream.

## Scope
- In scope:
  - AArch64 JIT codegen and call lowering optimizations.
  - AArch64 call-result move chain optimizations in register allocation and post-alloc passes.
  - Python 3.14 ARM default feature enablement (`ENABLE_ADAPTIVE_STATIC_PYTHON`, `ENABLE_LIGHTWEIGHT_FRAMES`).
  - Build/toolchain robustness impacting realized performance (`LTO`, `PGO` flow).
- Out of scope:
  - Feature work unrelated to ARM JIT/runtime performance.
  - Replacing upstream benchmark methodology.

## Baseline and Gap
- Merge-base between branch and upstream main: `17c27b6c09f968437b73385b641b4c3de5174048`.
- Divergence at analysis time:
  - branch-only commits: 42
  - upstream-only commits: 27
- Implication:
  - This branch includes optimization work not yet in upstream main.
  - Upstream contains bug/security/runtime fixes not yet in this branch.

## Design Summary

### 1. AArch64 Call Target Lowering Strategy
Problem:
- Repeated helper/runtime calls on ARM can inflate native code size and add branch hops, reducing JIT throughput and i-cache efficiency.

Design:
- Introduce call-target literal pooling keyed by absolute target address.
- Route AArch64 `emitCall` through pooled literal entries (`ldr literal -> blr`).
- Add selective direct literal lowering for singleton/hot immediate call targets.
- Emit literal pool once per function epilogue/codegen finalization.

Primary implementation points:
- `cinderx/Jit/codegen/environ.h`
- `cinderx/Jit/codegen/gen_asm_utils.cpp`
- `cinderx/Jit/codegen/gen_asm.cpp`
- `cinderx/Jit/codegen/frame_asm.cpp`

Expected effect:
- Lower generated code size for repeated targets.
- Lower dynamic branch overhead for singleton hot targets.
- Better instruction-cache locality under call-heavy kernels.

### 2. AArch64 Call-Result Register Chain Optimization
Problem:
- ARM call lowering frequently produces move chains like `retreg -> tmp -> argreg`, increasing instruction count and pressure.

Design:
- Regalloc soft-hint:
  - Prefer return registers for short call chains where call result is immediately consumed as `arg0` of a following call.
- Postalloc rewrite:
  - Fold specific call-result move chains.
  - Permit fold across non-clobber guard/metadata instructions.
  - Stop at call boundaries or clobbers to preserve correctness.

Primary implementation points:
- `cinderx/Jit/lir/regalloc.cpp`
- `cinderx/Jit/lir/postalloc.cpp`

Expected effect:
- Fewer redundant move instructions in hot call paths.
- Better realized IPC and smaller compiled function bodies.

### 3. Python 3.14 ARM Feature Enablement Policy
Problem:
- ARM builds may underperform if high-impact runtime features are disabled by default.

Design:
- Default-enable on OSS CPython 3.14 ARM (`aarch64`/`arm64`):
  - `ENABLE_ADAPTIVE_STATIC_PYTHON`
  - `ENABLE_LIGHTWEIGHT_FRAMES`
- Preserve Meta 3.12 behavior and environment override semantics.
- Expose runtime introspection APIs for deterministic validation:
  - `cinderx.is_adaptive_static_python_enabled()`
  - `cinderx.is_lightweight_frames_enabled()`

Primary implementation points:
- `setup.py`
- `cinderx/_cinderx-lib.cpp`
- `cinderx/PythonLib/cinderx/__init__.py`
- `cinderx/PythonLib/test_cinderx/test_oss_quick.py`

Expected effect:
- Better default runtime specialization behavior on 3.14 ARM.
- Lower frame overhead on supported lightweight-frame paths.

### 4. Build/Toolchain Realization (LTO/PGO)
Problem:
- Performance intent is lost when LTO/PGO setup is fragile across toolchains and hosts.

Design:
- Improve clang LTO linking robustness (`lld` preference, `LLVMgold` fallback validation).
- Use strict but predictable env-flag parsing for `CINDERX_ENABLE_LTO` and `CINDERX_ENABLE_PGO`.
- Add retry wrapper for flaky PGO workload stage.

Primary implementation points:
- `CMakeLists.txt`
- `setup.py`
- `tests/test_setup_adaptive_static_python.py`
- `tests/test_setup_lightweight_frames.py`
- `tests/test_setup_pgo_workload_retries.py`

Expected effect:
- Higher probability that ARM builds actually run with intended optimization profile.

## Verification Strategy
- Runtime correctness and JIT availability:
  - `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Feature-state correctness:
  - `test_oss_quick.py` plus API-level tests under `tests/`.
- Performance evidence:
  - Use remote ARM runner and richards collection scripts.
  - Record key deltas and command evidence in `findings.md`.

## Risks and Mitigations
- Risk: branch drift from upstream security/runtime fixes.
  - Mitigation: schedule regular upstream sync and re-validate ARM perf gates.
- Risk: architecture-specific tuning regresses x86 or other Python versions.
  - Mitigation: keep ARM gating explicit in setup logic and ARM-specific tests.
- Risk: code-size optimizations trade off latency in some patterns.
  - Mitigation: retain compactness guard tests and maintain A/B benchmark artifacts.

## Integration Plan
1. Keep branch-only ARM optimization commits grouped by theme (call lowering, regalloc/postalloc, feature defaults, build robustness).
2. Rebase/cherry-pick onto latest upstream main.
3. Re-run remote ARM full validation (`interp/JIT`, autojit, and benchmark snapshot).
4. Update `findings.md` and keep this design doc as architectural reference.

