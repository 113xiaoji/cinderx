# Phase 1 MVP OSR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Scheme-B OSR into `JUMP_BACKWARD_JIT` so a function that executes only once can still enter compiled loop code in the same activation on CinderX 3.14.

**Architecture:** Reuse the Phase 0 whole-function compiler and loop-header secondary-entry machinery, but replace the synthetic locals payload with a real interpreter-frame driven OSR path. Keep the MVP narrow: only outermost, reducible, object-only loops; no generators/coroutines/active exception regions; instrumentation off. Detect hot backedges in the 3.14 interpreter, compile on demand, cache the real OSR entry by `(function, bc_offset)`, and jump through a dedicated interpreter-frame OSR stub that still deopts through the existing downward path.

**Tech Stack:** C++ interpreter/JIT runtime, CPython 3.14 generated opcode cases, HIR/LIR/codegen, Python `unittest`, ARM remote helper.

---

## File Structure

**Files:**
- Modify: `cinderx/Interpreter/3.14/Includes/generated_cases.c.h`
- Modify: `cinderx/Jit/pyjit.h`
- Modify: `cinderx/Jit/pyjit.cpp`
- Modify: `cinderx/Jit/context.h`
- Modify: `cinderx/Jit/context.cpp`
- Modify: `cinderx/Jit/code_runtime.h`
- Modify: `cinderx/Jit/code_runtime.cpp`
- Modify: `cinderx/Jit/jit_rt.h`
- Modify: `cinderx/Jit/jit_rt.cpp`
- Modify: `cinderx/Jit/codegen/gen_asm.h`
- Modify: `cinderx/Jit/codegen/gen_asm.cpp`
- Modify: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Add: `scripts/arm/issue76_phase1_probe.py`
- Modify: `plans/2026-03-31-issue76-hot-loop-osr/findings.md`
- Modify: `plans/2026-03-31-issue76-hot-loop-osr/progress.md`

**Responsibilities:**
- `generated_cases.c.h`
  - call the CinderX hot-loop OSR probe from `JUMP_BACKWARD_JIT` before CPython tier2 optimization
- `pyjit.h/.cpp`
  - expose the interpreter-facing `tryHotLoopOSR(...)` entrypoint and Python debug/stat plumbing
- `context.h/.cpp`
  - store Phase 1 OSR counters and any lightweight cache/state needed per compiled function
- `code_runtime.h/.cpp`
  - distinguish the real interpreter-frame OSR entry from the Phase 0 test-only entry
- `jit_rt.h/.cpp`
  - helpers that validate the current `_PyInterpreterFrame` shape and prepare object-only live-ins for OSR
- `gen_asm.h/.cpp`
  - emit the real OSR entry stub that adopts the current interpreter frame rather than using a synthetic locals sequence
- `test_arm_runtime.py`
  - once-call hot-loop Python regressions and guard-rail tests for unsupported shapes
- `issue76_phase1_probe.py`
  - remote-targeted MVP proof script used by the standard ARM helper
- `findings.md` / `progress.md`
  - record design-to-runtime decisions and remote evidence

### Task 1: Add a Failing Phase 1 Once-Call Hot-Loop Regression

**Files:**
- Modify: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Add: `scripts/arm/issue76_phase1_probe.py`
- Modify: `cinderx/Jit/context.h`
- Modify: `cinderx/Jit/context.cpp`
- Modify: `cinderx/Jit/pyjit.cpp`

- [ ] **Step 1: Write the failing Python regression**

Add a new ARM runtime test that proves the current activation entered JIT from a hot backedge, not merely that the function became compilable for the future:

```python
def test_phase1_once_call_hot_loop_enters_jit_same_activation(self) -> None:
    code = textwrap.dedent(
        """
        import cinderx
        import cinderx.jit as jit

        jit.enable()
        jit.enable_specialized_opcodes()
        jit.compile_after_n_calls(1000000)

        def hot(n: int, acc: int) -> int:
            while n > 0:
                acc = acc + n
                n = n - 1
            return acc

        jit.get_and_clear_runtime_stats()
        result = hot(50000, 0)
        stats = jit.get_and_clear_runtime_stats()
        osr_entries = [
            entry for entry in stats.get("osr", [])
            if entry["normal"]["func_qualname"] == "hot"
        ]

        print(result)
        print(len(osr_entries))
        print(sum(entry["int"]["count"] for entry in osr_entries))
        print(jit.is_jit_compiled(hot))
        """
    )
```

- [ ] **Step 2: Add a focused remote probe script that mirrors the regression**

Create `scripts/arm/issue76_phase1_probe.py`:

```python
import cinderx.jit as jit


def hot(n: int, acc: int) -> int:
    while n > 0:
        acc = acc + n
        n = n - 1
    return acc


def main() -> None:
    jit.enable()
    jit.enable_specialized_opcodes()
    jit.compile_after_n_calls(1000000)
    jit.get_and_clear_runtime_stats()
    result = hot(50000, 0)
    stats = jit.get_and_clear_runtime_stats()
    osr = [
        entry for entry in stats.get("osr", [])
        if entry["normal"]["func_qualname"] == "hot"
    ]
    print(f"result={result}")
    print(f"osr_entries={osr}")
    if result != (50000 * 50001) // 2:
        raise SystemExit("wrong result")
    if not osr:
        raise SystemExit("no osr stats")
    if sum(entry["int"]["count"] for entry in osr) <= 0:
        raise SystemExit("osr count did not increase")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the regression to verify it fails**

Run the standard ARM helper in targeted mode:

```powershell
$ErrorActionPreference = 'Stop'
$tar = Join-Path $env:TEMP 'issue76_phase1_red.tar'
& 'C:\Program Files\Git\cmd\git.exe' archive --format=tar --prefix=cinderx-src/ -o $tar HEAD
scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 $tar root@124.70.162.35:/root/work/incoming/cinderx-update.tar
scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 scripts/arm/remote_update_build_test.sh root@124.70.162.35:/root/work/incoming/remote_update_build_test.sh
scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 scripts/arm/issue76_phase1_probe.py root@124.70.162.35:/root/work/incoming/issue76_phase1_probe.py
ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 root@124.70.162.35 @'
  tr -d '\r' < /root/work/incoming/remote_update_build_test.sh > /root/work/incoming/remote_update_build_test.sh.lf
  mv /root/work/incoming/remote_update_build_test.sh.lf /root/work/incoming/remote_update_build_test.sh
  chmod +x /root/work/incoming/remote_update_build_test.sh
  INCOMING_DIR=/root/work/incoming \
  WORKDIR=/root/work/cinderx-main \
  PYTHON=/opt/python-3.14/bin/python3.14 \
  DRIVER_VENV=/root/venv-cinderx314 \
  BENCH=richards \
  AUTOJIT=50 \
  PARALLEL=1 \
  SKIP_PYPERF=1 \
  ARM_RUNTIME_SKIP_TESTS=test_ \
  EXTRA_TEST_CMD='python -u /root/work/incoming/issue76_phase1_probe.py' \
  /root/work/incoming/remote_update_build_test.sh
'@
```

Expected:
- the probe exits non-zero with `no osr stats`
- or the Python regression shows `len(osr_entries) == 0`

- [ ] **Step 4: Add minimal OSR runtime stats plumbing**

Extend the existing runtime stats shape with an `osr` list, parallel to `deopt`:

```cpp
struct OSRStat {
  std::size_t count;
  BCOffset bc_offset;
};

using OSRStats =
    jit::UnorderedMap<const CodeRuntime*, jit::UnorderedMap<BCOffset, OSRStat>>;
```

and expose it in `get_and_clear_runtime_stats()` as:

```cpp
{
  "normal": {
    "func_qualname": "...",
    "bc_offset": 2
  },
  "int": {
    "count": 1
  }
}
```

- [ ] **Step 5: Re-run the targeted probe and verify it still fails for the expected reason**

Run the same remote helper command.

Expected:
- build/install succeeds
- the probe still fails because real OSR entry is not wired yet, but stats plumbing is visible and not crashing

- [ ] **Step 6: Commit**

```bash
git add cinderx/Jit/context.h cinderx/Jit/context.cpp cinderx/Jit/pyjit.cpp cinderx/PythonLib/test_cinderx/test_arm_runtime.py scripts/arm/issue76_phase1_probe.py
git commit -m "test: add phase1 once-call hot-loop osr regression"
```

### Task 2: Add a Real Interpreter-Frame OSR Entry Stub

**Files:**
- Modify: `cinderx/Jit/code_runtime.h`
- Modify: `cinderx/Jit/code_runtime.cpp`
- Modify: `cinderx/Jit/jit_rt.h`
- Modify: `cinderx/Jit/jit_rt.cpp`
- Modify: `cinderx/Jit/codegen/gen_asm.h`
- Modify: `cinderx/Jit/codegen/gen_asm.cpp`

- [ ] **Step 1: Write a failing probe-level assertion for the real OSR entry**

Extend `issue76_phase1_probe.py` to verify the compiled function exports a non-zero real OSR entry:

```python
entries = jit.get_osr_entries(hot)
print(f"entries={entries}")
if not entries or entries[0]["entry_address"] <= 0:
    raise SystemExit("missing real osr entry")
```

Expected:
- this still fails because `entry_address` is only the raw loop-header address, not a runnable interpreter-frame OSR entry

- [ ] **Step 2: Add explicit metadata for the real entry**

Split the current metadata into raw loop-header and runnable entry addresses:

```cpp
struct OSREntryMetadata {
  BCOffset bc_offset;
  uintptr_t body_address{0};
  uintptr_t osr_entry_address{0};
  uintptr_t test_entry_address{0};
  std::vector<LocalMapping> local_mappings;
};
```

and keep `test_entry_address` untouched so Phase 0 regression coverage survives.

- [ ] **Step 3: Add a runtime helper that validates the current frame shape**

Add the narrow Phase 1 MVP helper:

```cpp
struct Phase1OSRFrameData {
  _PyInterpreterFrame* frame;
  PyObject** localsplus;
};

Phase1OSRFrameData JITRT_PreparePhase1OSREntry(
    PyThreadState* tstate,
    PyFunctionObject* func,
    BCOffset bc_offset);
```

For the MVP, the helper must:
- assert the top frame belongs to `func`
- reject active exception / generator / inlined-frame cases
- expose `localsplus`
- leave frame ownership unchanged

- [ ] **Step 4: Emit a real OSR secondary entry stub**

Generate a second stub alongside the Phase 0 test entry:

```cpp
void NativeGenerator::generatePhase1OSREntry(const FrameInfo& frame_info) {
  // link nothing new
  // load tstate/current_frame/current localsplus
  // initialize frame-dependent live-ins
  // jump to the loop-header entry block
}
```

For the MVP:
- reuse the current object-only local-mapping export
- use the current interpreter frame already linked in `PyThreadState.current_frame`
- keep the Phase 0 test entry for regression/debug use

- [ ] **Step 5: Re-run the targeted probe and verify the failure moves forward**

Run the same helper command from Task 1, now expecting:
- `entries[0]["entry_address"] > 0`
- but still `no osr stats`, because the interpreter has not called the real entry yet

- [ ] **Step 6: Commit**

```bash
git add cinderx/Jit/code_runtime.h cinderx/Jit/code_runtime.cpp cinderx/Jit/jit_rt.h cinderx/Jit/jit_rt.cpp cinderx/Jit/codegen/gen_asm.h cinderx/Jit/codegen/gen_asm.cpp scripts/arm/issue76_phase1_probe.py
git commit -m "jit: add real interpreter-frame loop osr entry stub"
```

### Task 3: Wire `JUMP_BACKWARD_JIT` to the CinderX OSR Probe

**Files:**
- Modify: `cinderx/Interpreter/3.14/Includes/generated_cases.c.h`
- Modify: `cinderx/Jit/pyjit.h`
- Modify: `cinderx/Jit/pyjit.cpp`

- [ ] **Step 1: Add a failing interpreter-facing entrypoint declaration**

Expose a single narrow hook from `pyjit.h`:

```cpp
namespace jit {
bool tryHotLoopOSR(
    PyThreadState* tstate,
    _PyInterpreterFrame* frame,
    _Py_CODEUNIT* this_instr,
    _Py_CODEUNIT* loop_start);
}
```

Expected failure:
- `generated_cases.c.h` cannot yet compile against the missing declaration/definition

- [ ] **Step 2: Implement the minimal probe in `pyjit.cpp`**

The MVP version should:

```cpp
bool tryHotLoopOSR(
    PyThreadState* tstate,
    _PyInterpreterFrame* frame,
    _Py_CODEUNIT* this_instr,
    _Py_CODEUNIT* loop_start) {
  if (!isJitUsable()) {
    return false;
  }
  BorrowedRef<PyFunctionObject> func = jit::frameFunction(frame);
  if (func == nullptr) {
    return false;
  }
  // compile on demand if needed
  // find OSR metadata by bc offset
  // call the real osr entry
  // record OSR stat
  return entered;
}
```

Keep the first version narrow:
- only handle top-level function frames
- only act when the compiled function already exports the selected `bc_offset`
- return `false` on any unsupported shape

- [ ] **Step 3: Call the probe from `JUMP_BACKWARD_JIT` before tier2 optimize**

Insert the CinderX probe ahead of `_PyOptimizer_Optimize()`:

```cpp
if (backoff_counter_triggers(counter) && this_instr->op.code == JUMP_BACKWARD_JIT) {
    _Py_CODEUNIT *start = this_instr;
    while (oparg > 255) {
        oparg >>= 8;
        start--;
    }
    _PyFrame_SetStackPointer(frame, stack_pointer);
    if (jit::tryHotLoopOSR(tstate, frame, this_instr, start)) {
        stack_pointer = _PyFrame_GetStackPointer(frame);
        DISPATCH();
    }
    int optimized = _PyOptimizer_Optimize(frame, start, &executor, 0);
    stack_pointer = _PyFrame_GetStackPointer(frame);
```

The first version must preserve the existing CPython tier2 path when CinderX declines OSR.

- [ ] **Step 4: Re-run the targeted probe and verify it turns green**

Run the helper command from Task 1.

Expected:
- `result=` is correct
- `osr_entries=` is non-empty
- OSR stats now show at least one entry for `hot`
- helper exits `0`

- [ ] **Step 5: Commit**

```bash
git add cinderx/Interpreter/3.14/Includes/generated_cases.c.h cinderx/Jit/pyjit.h cinderx/Jit/pyjit.cpp scripts/arm/issue76_phase1_probe.py
git commit -m "jit: enter loop osr from jump_backward_jit"
```

### Task 4: Add Guard-Rail Regressions for Unsupported Shapes

**Files:**
- Modify: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Modify: `scripts/arm/issue76_phase1_probe.py`

- [ ] **Step 1: Add a failing unsupported-shape regression**

Add a Python test that proves unsupported cases do not crash and simply stay interpreted:

```python
def test_phase1_loop_osr_skips_active_exception_shape(self) -> None:
    code = textwrap.dedent(
        """
        import cinderx.jit as jit

        jit.enable()
        jit.enable_specialized_opcodes()
        jit.compile_after_n_calls(1000000)

        def hot(n: int) -> int:
            total = 0
            try:
                while n > 0:
                    total += n
                    n -= 1
            finally:
                total += 1
            return total

        jit.get_and_clear_runtime_stats()
        result = hot(5000)
        stats = jit.get_and_clear_runtime_stats()
        osr = [entry for entry in stats.get("osr", []) if entry["normal"]["func_qualname"] == "hot"]
        print(result)
        print(len(osr))
        """
    )
```

- [ ] **Step 2: Verify the test fails for the right reason**

Run only the new case through the helper:

```powershell
ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 root@124.70.162.35 @'
  cd /root/work/cinderx-main &&
  /root/venv-cinderx314/bin/python -m unittest \
    cinderx.PythonLib.test_cinderx.test_arm_runtime.ArmRuntimeTests.test_phase1_loop_osr_skips_active_exception_shape -v
'@
```

Expected:
- the assertion should currently fail because the test is not present yet

- [ ] **Step 3: Implement the minimum guard-rail behavior**

Make the Phase 1 probe return `false` for unsupported shapes:

```cpp
if (frame->owner != FRAME_OWNED_BY_THREAD) {
  return false;
}
if (co->co_flags & kCoFlagsAnyGenerator) {
  return false;
}
if (activeExceptBlock(frame) || !isObjectOnlyLoopOSRShape(...)) {
  return false;
}
```

- [ ] **Step 4: Re-run the targeted unsupported-shape test**

Expected:
- the function returns the correct interpreter result
- no OSR stats are recorded
- helper exits `0`

- [ ] **Step 5: Commit**

```bash
git add cinderx/PythonLib/test_cinderx/test_arm_runtime.py cinderx/Jit/pyjit.cpp scripts/arm/issue76_phase1_probe.py
git commit -m "test: guard unsupported phase1 loop osr shapes"
```

### Task 5: Full Verification and Evidence Capture

**Files:**
- Modify: `plans/2026-03-31-issue76-hot-loop-osr/findings.md`
- Modify: `plans/2026-03-31-issue76-hot-loop-osr/progress.md`

- [ ] **Step 1: Run the focused direct probe on ARM**

```powershell
ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 root@124.70.162.35 @'
  cd /root/work/cinderx-main &&
  ISSUE76_PHASE0_STABILITY_RUNS=8 /root/venv-cinderx314/bin/python -u scripts/arm/issue76_phase1_probe.py
'@
```

Expected:
- exit code `0`
- the probe prints a positive OSR count for `hot`

- [ ] **Step 2: Run the standard helper gate**

```powershell
ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 root@124.70.162.35 @'
  tr -d '\''\r'\'' < /root/work/incoming/remote_update_build_test.sh > /root/work/incoming/remote_update_build_test.sh.lf &&
  mv /root/work/incoming/remote_update_build_test.sh.lf /root/work/incoming/remote_update_build_test.sh &&
  chmod +x /root/work/incoming/remote_update_build_test.sh &&
  INCOMING_DIR=/root/work/incoming \
  WORKDIR=/root/work/cinderx-main \
  PYTHON=/opt/python-3.14/bin/python3.14 \
  DRIVER_VENV=/root/venv-cinderx314 \
  BENCH=richards \
  AUTOJIT=50 \
  PARALLEL=1 \
  SKIP_PYPERF=1 \
  ARM_RUNTIME_SKIP_TESTS=test_ \
  EXTRA_TEST_CMD='\''python -u /root/work/incoming/issue76_phase1_probe.py'\'' \
  /root/work/incoming/remote_update_build_test.sh
'@
```

Expected:
- helper exit code `0`
- probe output confirms the same-activation OSR count is non-zero

- [ ] **Step 3: Run the targeted Python regression file**

```powershell
ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 root@124.70.162.35 @'
  cd /root/work/cinderx-main &&
  /root/venv-cinderx314/bin/python -m unittest discover -s cinderx/PythonLib/test_cinderx -p test_arm_runtime.py -k phase1_loop_osr -v
'@
```

Expected:
- all `phase1_loop_osr` tests pass

- [ ] **Step 4: Record the evidence**

Append to `findings.md`:

```markdown
## 2026-04-01 Phase 1 MVP verification

- direct probe:
  - `result=...`
  - `osr_entries=[...]`
  - `osr_count=...`
- helper gate:
  - `HELPER_RC=0`
- unsupported-shape guard:
  - returned interpreter result
  - no OSR stats recorded
```

and append to `progress.md`:

```markdown
- Completed Phase 1 MVP wiring through `JUMP_BACKWARD_JIT`.
- Verified same-activation loop OSR through the standard ARM helper.
```

- [ ] **Step 5: Commit**

```bash
git add plans/2026-03-31-issue76-hot-loop-osr/findings.md plans/2026-03-31-issue76-hot-loop-osr/progress.md
git commit -m "docs: record phase1 loop osr verification"
```
