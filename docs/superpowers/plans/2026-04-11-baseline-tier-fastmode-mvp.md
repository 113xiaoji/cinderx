# Baseline Tier Fast-Mode MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land a first baseline-tier MVP that reuses the current compiler pipeline in a stripped-down fast mode, exposes observable tier state (`interp` / `baseline` / `optimized`), and supports baseline compilation plus explicit optimized promotion without attempting the later dedicated bytecode baseline compiler yet.

**Architecture:** Keep this plan intentionally narrow. Instead of building the long-term standalone baseline compiler, refactor the current compiler and runtime bookkeeping so the JIT can produce two named tiers from the existing pipeline: a low-pass-count baseline tier and the current optimizing tier. The baseline tier gets a separate public API and a separate automatic call-count threshold, while `force_compile()` becomes the explicit promotion path to optimized tier. This establishes tier state, tier-aware entry replacement, and validation scaffolding before a later plan introduces a separate bytecode-only baseline compiler backend.

**Tech Stack:** C++20, CPython 3.14 extension APIs, `cinderx.jit` Python wrappers, `unittest`, ARM remote helper scripts, existing CinderX deopt/runtime infrastructure.

---

## File Structure

- `cinderx/Jit/tier.h`
  - new shared enum/helpers for `CompileTier`
- `cinderx/Jit/compiler.h`
  - add tier-aware compile entrypoints
- `cinderx/Jit/compiler.cpp`
  - define baseline-vs-optimized pass selection
- `cinderx/Jit/compiled_function.h`
  - attach tier metadata to compiled code objects
- `cinderx/Jit/context.h`
  - store active compiled versions per compilation key
- `cinderx/Jit/context.cpp`
  - install baseline or optimized entrypoints and handle promotion replacement
- `cinderx/Jit/pyjit.cpp`
  - add Python APIs and tier-aware `jitVectorcall()` dispatch
- `cinderx/PythonLib/cinderx/jit.py`
  - expose new APIs and fallback stubs
- `cinderx/PythonLib/test_cinderx/test_jit_tiering.py`
  - focused red/green regression tests for tier behavior
- `findings.md`
  - remote evidence and limits of the MVP

### Task 1: Add the public tier API contract with failing Python tests

**Files:**
- Create: `cinderx/PythonLib/test_cinderx/test_jit_tiering.py`
- Modify: `cinderx/PythonLib/cinderx/jit.py`
- Modify: `cinderx/Jit/pyjit.cpp`
- Test: `cinderx/PythonLib/test_cinderx/test_jit_tiering.py`

- [ ] **Step 1: Write the failing focused test file**

```python
import textwrap
import unittest

import cinderx.jit as jit
import cinderx.test_support as cinder_support


@cinder_support.skip_unless_jit
class TieringApiTests(unittest.TestCase):
    def tearDown(self) -> None:
        jit.baseline_compile_after_n_calls(0)
        jit.compile_after_n_calls(0)

    def test_force_compile_baseline_exposes_baseline_tier(self) -> None:
        def helper(x):
            return x + 1

        self.assertEqual(jit.get_function_tier(helper), "interp")
        self.assertTrue(jit.force_compile_baseline(helper))
        self.assertEqual(jit.get_function_tier(helper), "baseline")
        self.assertEqual(helper(3), 4)

    def test_force_compile_promotes_baseline_function_to_optimized(self) -> None:
        def helper(x):
            return x + 1

        self.assertTrue(jit.force_compile_baseline(helper))
        self.assertEqual(jit.get_function_tier(helper), "baseline")
        self.assertTrue(jit.force_compile(helper))
        self.assertEqual(jit.get_function_tier(helper), "optimized")
        self.assertEqual(helper(5), 6)

    def test_low_threshold_autocompiles_baseline_before_optimized(self) -> None:
        def helper(x):
            return x + 1

        jit.baseline_compile_after_n_calls(1)
        jit.compile_after_n_calls(1000000)
        self.assertEqual(jit.get_function_tier(helper), "interp")
        self.assertEqual(helper(7), 8)
        self.assertEqual(jit.get_function_tier(helper), "baseline")
```

- [ ] **Step 2: Run the new tests and verify they fail for the expected API gap**

Run:

```powershell
& 'C:\work\code\deer-flow\backend\.venv\Scripts\python.exe' -m unittest cinderx.PythonLib.test_cinderx.test_jit_tiering -v
```

Expected:

```text
AttributeError: module 'cinderx.jit' has no attribute 'force_compile_baseline'
```

- [ ] **Step 3: Stage and commit only the failing tests**

```powershell
git add cinderx/PythonLib/test_cinderx/test_jit_tiering.py
git -c user.name='Codex' -c user.email='codex@local.invalid' commit -m "test: add baseline tier api regressions"
```

Expected:

```text
git commit exits 0 and prints:
test: add baseline tier api regressions
```

### Task 2: Add shared tier metadata and a baseline-aware fast-mode compile path

**Files:**
- Create: `cinderx/Jit/tier.h`
- Modify: `cinderx/Jit/compiler.h`
- Modify: `cinderx/Jit/compiler.cpp`
- Modify: `cinderx/Jit/compiled_function.h`
- Test: `cinderx/PythonLib/test_cinderx/test_jit_tiering.py`

- [ ] **Step 1: Add the shared tier enum and compiled-function metadata**

Create `cinderx/Jit/tier.h` with:

```cpp
#pragma once

#include <cstdint>

namespace jit {

enum class CompileTier : uint8_t {
  kBaseline,
  kOptimized,
};

inline const char* tierName(CompileTier tier) {
  switch (tier) {
    case CompileTier::kBaseline:
      return "baseline";
    case CompileTier::kOptimized:
      return "optimized";
  }
  return "optimized";
}

} // namespace jit
```

Then extend `CompiledFunctionData` in `cinderx/Jit/compiled_function.h`:

```cpp
#include "cinderx/Jit/tier.h"

struct CompiledFunctionData {
  CompileTier tier{CompileTier::kOptimized};
  std::span<const std::byte> code;
  vectorcallfunc vectorcall_entry{nullptr};
  // existing fields stay unchanged
};

class CompiledFunction {
 public:
  CompileTier tier() const {
    return data_.tier;
  }
```

- [ ] **Step 2: Make `Compiler` explicitly accept a compile tier**

Update `cinderx/Jit/compiler.h`:

```cpp
std::optional<CompiledFunctionData> Compile(
    const hir::Preloader& preloader,
    CompileTier tier);

std::optional<CompiledFunctionData> Compile(
    BorrowedRef<PyFunctionObject> func,
    CompileTier tier);
```

And add a tier-aware config builder in `cinderx/Jit/compiler.cpp`:

```cpp
PassConfig createConfigForTier(CompileTier tier) {
  if (tier == CompileTier::kBaseline) {
    return static_cast<PassConfig>(
        PassConfig::kCleanCFG |
        PassConfig::kDeadCodeElim |
        PassConfig::kInsertUpdatePrevInstr);
  }
  return createConfig();
}
```

When filling `CompiledFunctionData`, set:

```cpp
compiled_func.tier = tier;
```

- [ ] **Step 3: Make the tests fail later for behavior, not missing APIs**

Run:

```powershell
& 'C:\work\code\deer-flow\backend\.venv\Scripts\python.exe' -m unittest cinderx.PythonLib.test_cinderx.test_jit_tiering -v
```

Expected:

```text
AttributeError: module 'cinderx.jit' has no attribute 'get_function_tier'
```

- [ ] **Step 4: Commit the C++ tier metadata scaffolding**

```powershell
git add cinderx/Jit/tier.h cinderx/Jit/compiler.h cinderx/Jit/compiler.cpp cinderx/Jit/compiled_function.h
git -c user.name='Codex' -c user.email='codex@local.invalid' commit -m "jit: add compile tier metadata and fast-mode config"
```

Expected:

```text
git commit exits 0 and prints:
jit: add compile tier metadata and fast-mode config
```

### Task 3: Add tier-aware runtime bookkeeping, public APIs, and automatic baseline entry

**Files:**
- Modify: `cinderx/Jit/context.h`
- Modify: `cinderx/Jit/context.cpp`
- Modify: `cinderx/Jit/pyjit.cpp`
- Modify: `cinderx/PythonLib/cinderx/jit.py`
- Test: `cinderx/PythonLib/test_cinderx/test_jit_tiering.py`

- [ ] **Step 1: Add versioned compiled-code storage in `Context`**

Add a small per-key version holder to `cinderx/Jit/context.h`:

```cpp
enum class FunctionTierState : uint8_t {
  kInterp,
  kBaseline,
  kOptimized,
};

struct CompiledVersions {
  std::unique_ptr<CompiledFunction> baseline;
  std::unique_ptr<CompiledFunction> optimized;

  CompiledFunction* active() const {
    if (optimized != nullptr) {
      return optimized.get();
    }
    return baseline.get();
  }
};
```

Replace the current compiled-code map with:

```cpp
UnorderedMap<CompilationKey, CompiledVersions> compiled_codes_;
```

Adjust `lookupFunc()`, `lookupCode()`, and `lookupCodeRuntime()` to return `active()`, and add:

```cpp
FunctionTierState lookupFuncTier(BorrowedRef<PyFunctionObject> func);
bool hasOptimizedTier(BorrowedRef<PyFunctionObject> func);
```

- [ ] **Step 2: Add the public Python APIs and wrapper stubs**

In `cinderx/Jit/pyjit.cpp`, add:

```cpp
PyObject* force_compile_baseline(PyObject*, PyObject* arg);
PyObject* get_function_tier(PyObject*, PyObject* arg);
PyObject* baseline_compile_after_n_calls(PyObject*, PyObject* arg);
PyObject* get_baseline_compile_after_n_calls(PyObject*, PyObject*);
```

Required semantics:

- `force_compile_baseline(f)`:
  - compile with `CompileTier::kBaseline`
  - install baseline entry if the function is still interpreted
- `force_compile(f)`:
  - compile with `CompileTier::kOptimized`
  - replace active entry with optimized tier
- `get_function_tier(f)`:
  - return `"interp"` when not compiled
  - return `"baseline"` when only baseline exists
  - return `"optimized"` when optimized exists
- `baseline_compile_after_n_calls(n)`:
  - set a new baseline-tier threshold

In `cinderx/PythonLib/cinderx/jit.py`, add imports and fallbacks:

```python
from cinderjit import (
    baseline_compile_after_n_calls,
    force_compile_baseline,
    get_baseline_compile_after_n_calls,
    get_function_tier,
)
```

Fallbacks:

```python
def baseline_compile_after_n_calls(calls: int) -> None:
    return None

def force_compile_baseline(func: FuncAny) -> bool:
    return False

def get_baseline_compile_after_n_calls() -> int | None:
    return None

def get_function_tier(func: FuncAny) -> str:
    return "interp"
```

- [ ] **Step 3: Update `jitVectorcall()` to compile baseline tier first**

In `cinderx/Jit/config.h`, add:

```cpp
std::optional<uint32_t> baseline_compile_after_n_calls;
```

Then update `jitVectorcall()` in `cinderx/Jit/pyjit.cpp` so it behaves like:

```cpp
if (auto baseline_limit = getConfig().baseline_compile_after_n_calls;
    baseline_limit.has_value()) {
  auto const calls = countCalls(code);
  if (calls >= *baseline_limit && jitCtx()->lookupFuncTier(func) == CompileTierState::kInterp) {
    auto result = compileFunction(func, CompileTier::kBaseline);
    if (result == Result::OK) {
      return func->vectorcall(func_obj, stack, nargsf, kwnames);
    }
  }
}

if (auto optimize_limit = getConfig().compile_after_n_calls;
    optimize_limit.has_value()) {
  auto const calls = countCalls(code);
  if (calls < *optimize_limit && !jitCtx()->hasOptimizedTier(func)) {
    incrementShadowcodeCall(code);
    auto entry = getInterpretedVectorcall(func);
    return entry(func_obj, stack, nargsf, kwnames);
  }
}

return forcedJitVectorcall(func_obj, stack, nargsf, kwnames);
```

This MVP keeps promotion simple:

- automatic path can create baseline
- explicit `force_compile()` promotes to optimized
- full automatic baseline->optimized promotion is left for a later plan

- [ ] **Step 4: Re-run the focused tests until they pass**

Run:

```powershell
& 'C:\work\code\deer-flow\backend\.venv\Scripts\python.exe' -m unittest cinderx.PythonLib.test_cinderx.test_jit_tiering -v
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit the tier-aware runtime and API plumbing**

```powershell
git add cinderx/Jit/context.h cinderx/Jit/context.cpp cinderx/Jit/pyjit.cpp cinderx/PythonLib/cinderx/jit.py cinderx/PythonLib/test_cinderx/test_jit_tiering.py
git -c user.name='Codex' -c user.email='codex@local.invalid' commit -m "jit: add baseline tier runtime and api plumbing"
```

Expected:

```text
git commit exits 0 and prints:
jit: add baseline tier runtime and api plumbing
```

### Task 4: Validate locally and through the standard remote entrypoint, then record findings

**Files:**
- Modify: `findings.md`
- Test: `cinderx/PythonLib/test_cinderx/test_jit_tiering.py`

- [ ] **Step 1: Re-run the focused local tier tests**

Run:

```powershell
& 'C:\work\code\deer-flow\backend\.venv\Scripts\python.exe' -m unittest cinderx.PythonLib.test_cinderx.test_jit_tiering -v
```

Expected:

```text
OK
```

- [ ] **Step 2: Run the standard remote helper with only the new tier tests**

Run:

```powershell
$env:ARM_RUNTIME_SKIP_TESTS='test_'
$env:EXTRA_TEST_CMD='python -m unittest cinderx.PythonLib.test_cinderx.test_jit_tiering -v'
$env:SKIP_DEFAULT_PYPERF_GATES='1'
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 -RepoPath C:\work\code\cinderx5 -UpstreamRemote codex-local -UpstreamBranch bench-cur-7c361dce -WorkBranch bench-cur-7c361dce -ArmHost 124.70.162.35 -Benchmark richards
```

Expected:

```text
>> extra test command
OK
SKIP_DEFAULT_PYPERF_GATES=1 set; done after post-pyperf command.
```

- [ ] **Step 3: Run one direct remote tier probe under the same helper worktree**

Run:

```powershell
ssh root@124.70.162.35 "cd /root/work/cinderx-main && PYTHONPATH=scratch/lib.linux-aarch64-cpython-314:cinderx/PythonLib /root/venv-cinderx314/bin/python - <<'PY'
import cinderx.jit as jit

jit.enable()
jit.baseline_compile_after_n_calls(1)
jit.compile_after_n_calls(1000000)

def hot(n):
    s = 0
    for i in range(n):
        s += i
    return s

print(jit.get_function_tier(hot))
hot(10)
print(jit.get_function_tier(hot))
jit.force_compile(hot)
print(jit.get_function_tier(hot))
print(hot(10))
PY"
```

Expected:

```text
interp
baseline
optimized
45
```

- [ ] **Step 4: Append the MVP result to `findings.md`**

Append:

```markdown
## 2026-04-11 baseline tier fast-mode MVP

- Scope:
  - first landing of tier-aware JIT plumbing only
  - baseline tier reuses the current compiler in a stripped fast-mode
  - no standalone bytecode baseline compiler yet
- Public API:
  - `force_compile_baseline()`
  - `get_function_tier()`
  - `baseline_compile_after_n_calls()`
- Validation:
  - local `test_jit_tiering.py`: `OK`
  - remote `test_jit_tiering.py` via standard helper: `OK`
  - direct remote tier probe:
    - `interp`
    - `baseline`
    - `optimized`
    - `45`
- Limitation:
  - automatic baseline -> optimized promotion is not in this MVP
  - the optimized tier is still the existing HIR/LIR compiler
  - the dedicated standalone baseline compiler remains a follow-up project
```

- [ ] **Step 5: Commit the findings update**

```powershell
git add findings.md
git -c user.name='Codex' -c user.email='codex@local.invalid' commit -m "docs: record baseline tier fast-mode mvp findings"
```

Expected:

```text
git commit exits 0 and prints:
docs: record baseline tier fast-mode mvp findings
```
