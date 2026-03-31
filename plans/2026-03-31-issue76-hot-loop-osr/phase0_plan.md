# Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land a controlled prototype for scheme B that proves loop-header secondary entry generation and synthetic-state OSR execution for CinderX 3.14.

**Architecture:** Keep Phase 0 intentionally narrower than the final design. Instead of wiring directly into `JUMP_BACKWARD_JIT`, generate test-oriented OSR metadata and a secondary entry stub that can enter compiled loop code from a synthetic state payload. Narrow the first working slice to loop headers whose entry snapshot has an empty operand stack and block stack, so the prototype only has to materialize localsplus values. Reuse the existing whole-function compiler, block-label codegen, and deopt/runtime frame linkage as much as possible.

**Tech Stack:** C++ runtime/codegen, HIR/LIR/codegen pipeline, GoogleTest `RuntimeTests`, CPython 3.14 interpreter frames.

---

### File Structure

**Files:**
- Modify: `cinderx/Jit/code_runtime.h`
- Modify: `cinderx/Jit/code_runtime.cpp`
- Modify: `cinderx/Jit/codegen/environ.h`
- Modify: `cinderx/Jit/lir/generator.h`
- Modify: `cinderx/Jit/lir/generator.cpp`
- Modify: `cinderx/Jit/codegen/gen_asm.h`
- Modify: `cinderx/Jit/codegen/gen_asm.cpp`
- Modify: `cinderx/Jit/jit_rt.h`
- Modify: `cinderx/Jit/jit_rt.cpp`
- Modify: `cinderx/RuntimeTests/codegen_test.cpp`
- Modify: `plans/2026-03-31-issue76-hot-loop-osr/findings.md`

**Responsibilities:**
- `code_runtime.*`
  - hold OSR entry metadata and test-entry addresses
- `environ.h`
  - carry HIR-to-LIR/LIR-to-label mappings needed to export loop-header labels
- `lir/generator.*`
  - identify Phase 0-eligible loop headers and map them to first LIR blocks
- `gen_asm.*`
  - emit test-oriented secondary entry stubs and resolve final label offsets
- `jit_rt.*`
  - helper(s) for linking a fresh frame and initializing it for synthetic-state OSR
- `RuntimeTests/codegen_test.cpp`
  - failing tests first, then green-path validation
- `findings.md`
  - capture test-analysis decisions and verification results for each iteration

### Task 1: Add Failing RuntimeTests for Phase 0 Metadata

**Files:**
- Modify: `cinderx/RuntimeTests/codegen_test.cpp`

- [ ] **Step 1: Write the failing test**

Add a new `CodegenTest` case that:
- compiles a small loop-bearing function such as:

```python
def hot(n, acc):
  while n > 0:
    acc = acc + n
    n = n - 1
  return acc
```

- creates a `NativeGenerator`
- forces code generation via `getVectorcallEntry()`
- asserts that `codeRuntime()` reports at least one exported OSR entry
- asserts that the exported entry is associated with a bytecode offset inside the loop header

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cmake --build build --target RuntimeTests --config Release
.\build\RuntimeTests\RuntimeTests.exe --gtest_filter=CodegenTest.Phase0ExportsLoopHeaderOsrEntry
```

Expected:
- compile or link failure because OSR metadata/query APIs do not exist yet
- or runtime assertion failure because there are no exported OSR entries

- [ ] **Step 3: Write minimal implementation**

Implement:
- `OSREntryMetadata` in `CodeRuntime`
- storage/query helpers such as:
  - `addOSREntry(...)`
  - `lookupOSREntryByBCOffset(...)`
  - `osrEntries()`

- [ ] **Step 4: Run test to verify it passes**

Run the same `RuntimeTests` command and expect:
- `PASS`

- [ ] **Step 5: Commit**

```bash
git add cinderx/Jit/code_runtime.h cinderx/Jit/code_runtime.cpp cinderx/RuntimeTests/codegen_test.cpp
git commit -m "jit: record phase0 loop header osr metadata"
```

### Task 2: Add Failing Test for Loop-Header Label Export

**Files:**
- Modify: `cinderx/Jit/codegen/environ.h`
- Modify: `cinderx/Jit/lir/generator.h`
- Modify: `cinderx/Jit/lir/generator.cpp`
- Modify: `cinderx/Jit/codegen/gen_asm.cpp`
- Modify: `cinderx/RuntimeTests/codegen_test.cpp`

- [ ] **Step 1: Write the failing test**

Add a second `CodegenTest` that:
- compiles the same `hot(n, acc)` function
- asks for the OSR entry metadata
- asserts the stored code offset / entry address is non-zero and distinct from the top-level vectorcall entry

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\build\RuntimeTests\RuntimeTests.exe --gtest_filter=CodegenTest.Phase0ResolvesLoopHeaderLabel
```

Expected:
- fail because the metadata exists but entry address/offset is still unset

- [ ] **Step 3: Write minimal implementation**

Implement:
- a Phase 0 eligibility scan in `LIRGenerator`:
  - outermost loop headers only
  - empty block stack only
  - object-only entry snapshot live-ins only
- export mapping from HIR loop header to first LIR block
- in `generateAssemblyBody()` / post-finalization:
  - resolve the first LIR block label offset
  - store the final code address into `CodeRuntime`

- [ ] **Step 4: Run test to verify it passes**

Run the same `RuntimeTests` command and expect:
- `PASS`

- [ ] **Step 5: Commit**

```bash
git add cinderx/Jit/codegen/environ.h cinderx/Jit/lir/generator.h cinderx/Jit/lir/generator.cpp cinderx/Jit/codegen/gen_asm.cpp cinderx/RuntimeTests/codegen_test.cpp
git commit -m "jit: export phase0 loop header osr entry labels"
```

### Task 3: Add Failing Test for Synthetic-State OSR Execution

**Files:**
- Modify: `cinderx/Jit/jit_rt.h`
- Modify: `cinderx/Jit/jit_rt.cpp`
- Modify: `cinderx/Jit/codegen/gen_asm.h`
- Modify: `cinderx/Jit/codegen/gen_asm.cpp`
- Modify: `cinderx/RuntimeTests/codegen_test.cpp`

- [ ] **Step 1: Write the failing test**

Add a `CodegenTest` that:
- compiles `hot(n, acc)`
- looks up the loop-header OSR entry
- constructs a synthetic localsplus payload representing entry into the loop with:
  - `n = 3`
  - `acc = 10`
- invokes a test-only OSR entry function
- expects the result `16`

Minimal intended payload shape for the first slice:

```cpp
PyObject* localsplus[] = {n, acc};
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\build\RuntimeTests\RuntimeTests.exe --gtest_filter=CodegenTest.Phase0SyntheticStateOsrExecutesLoop
```

Expected:
- fail because the test-entry stub/runtime helper does not exist yet

- [ ] **Step 3: Write minimal implementation**

Implement a test-oriented OSR entry path:
- generate a custom secondary-entry stub for each Phase 0 OSR entry
- helper links a fresh interpreter/JIT frame for the function
- helper initializes frame bytecode position to the loop header
- stub loads locals-only object live-ins from the synthetic payload into their assigned native locations
- stub jumps to the loop-header block label

Explicit non-goals in this task:
- no automatic `JUMP_BACKWARD_JIT` wiring
- no live interpreter-frame adoption
- no generator/coroutine support
- no operand-stack reconstruction

- [ ] **Step 4: Run test to verify it passes**

Run the same `RuntimeTests` command and expect:
- `PASS`

- [ ] **Step 5: Commit**

```bash
git add cinderx/Jit/jit_rt.h cinderx/Jit/jit_rt.cpp cinderx/Jit/codegen/gen_asm.h cinderx/Jit/codegen/gen_asm.cpp cinderx/RuntimeTests/codegen_test.cpp
git commit -m "jit: add phase0 synthetic-state loop osr entry"
```

### Task 4: Add Failing Test for Deopt Compatibility from OSR Entry

**Files:**
- Modify: `cinderx/RuntimeTests/codegen_test.cpp`
- Modify: `cinderx/Jit/codegen/gen_asm.cpp`
- Modify: `cinderx/Jit/jit_rt.cpp`

- [ ] **Step 1: Write the failing test**

Add a `CodegenTest` that:
- compiles a simple loop-bearing function whose body contains a guaranteed deopt/slow-path trigger after OSR entry
- enters via the Phase 0 OSR stub
- expects execution to complete correctly after dropping back to the interpreter

One acceptable strategy:
- insert a test-only forced deopt guard in the selected loop-header path
- verify the final Python result still matches the interpreter baseline

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\build\RuntimeTests\RuntimeTests.exe --gtest_filter=CodegenTest.Phase0OsrThenDeoptResumesCorrectly
```

Expected:
- fail because OSR-entered execution cannot yet deopt/finish correctly

- [ ] **Step 3: Write minimal implementation**

Implement only the missing compatibility needed to make the test pass:
- ensure the Phase 0 secondary entry creates a frame/layout acceptable to existing deopt paths
- if needed, initialize frame metadata fields that current deopt/resume logic assumes

- [ ] **Step 4: Run test to verify it passes**

Run the same `RuntimeTests` command and expect:
- `PASS`

- [ ] **Step 5: Commit**

```bash
git add cinderx/RuntimeTests/codegen_test.cpp cinderx/Jit/codegen/gen_asm.cpp cinderx/Jit/jit_rt.cpp
git commit -m "jit: make phase0 loop osr entry compatible with deopt"
```

### Task 5: Verification and Evidence Capture

**Files:**
- Modify: `plans/2026-03-31-issue76-hot-loop-osr/findings.md`

- [ ] **Step 1: Run focused local verification**

Run:

```powershell
cmake --build build --target RuntimeTests --config Release
.\build\RuntimeTests\RuntimeTests.exe --gtest_filter=CodegenTest.Phase0*
```

Expected:
- all new Phase 0 tests pass

- [ ] **Step 2: Record detailed testing analysis**

Write into `findings.md`:
- why RuntimeTests was chosen over Python-level first
- why synthetic-state entry was chosen over immediate `JUMP_BACKWARD_JIT` wiring
- exact failure modes observed in each red step
- why each narrowing decision reduced risk

- [ ] **Step 3: Optional remote smoke gate**

If the Phase 0 changes affect shared runtime behavior enough to justify it, run the standard remote entry:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 -RepoPath C:\work\code\cinderx1\cinderx -WorkBranch bench-cur-7c361dce -SkipPyperformance
```

Expected:
- only if needed after local RuntimeTests are green

- [ ] **Step 4: Commit evidence**

```bash
git add plans/2026-03-31-issue76-hot-loop-osr/findings.md
git commit -m "docs: record phase0 loop osr prototype verification"
```
