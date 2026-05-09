# ARM LIR/CODEGEN Indexed Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and verify an ARM/AArch64 LIR/CODEGEN optimization loop
until the requested JIT28 stop condition is confirmed.

**Architecture:** Start with a narrow CODEGEN change that lowers eligible
`MemoryIndirect` loads/stores to AArch64 indexed memory operands. Keep the
fallback path unchanged for unsupported addressing forms. Benchmark each
candidate independently on the ARM host before moving to the next ranked
candidate.

**Tech Stack:** C++ LIR/CODEGEN, AsmJit AArch64 backend, PowerShell/SSH remote
runner, pyperformance JSON summaries.

---

### Task 1: Remove Rejected Guard Candidate From HEAD

**Files:**
- Modify: `cinderx/Jit/codegen/autogen.cpp`
- Modify: `cinderx/Jit/codegen/environ.h`
- Modify: `cinderx/Jit/codegen/gen_asm.cpp`
- Modify: `cinderx/Jit/codegen/gen_asm.h`

- [ ] **Step 1: Revert the rejected trial without touching notes**

Run:

```powershell
git revert --no-commit dc3cb6ca
git diff -- cinderx/Jit/codegen/autogen.cpp cinderx/Jit/codegen/environ.h cinderx/Jit/codegen/gen_asm.cpp cinderx/Jit/codegen/gen_asm.h
```

Expected: the near-deopt branch helper and `aarch64_near_deopt_branches`
plumbing are removed. `progress.md` and `task_plan.md` remain unstaged.

- [ ] **Step 2: Commit the revert**

Run the commit-validator workflow and commit only the four CODEGEN files with
message:

```text
revert(jit): drop arm guard branch trial
```

Expected: HEAD code no longer contains the rejected trial.

### Task 2: Add Access-Size-Aware Indexed Memory Lowering

**Files:**
- Modify: `cinderx/Jit/codegen/autogen.cpp`
- Test: `cinderx/RuntimeTests/lir_abi_test.cpp`

- [ ] **Step 1: Add a focused codegen test case**

Add AArch64-only move translations that exercise offset-free indexed load and
store forms with 64-bit/object operands:

```cpp
#if defined(CINDER_AARCH64)
  translateInstr(Instruction::kMove, makeOutPhyReg(), makeIndScale(1, 2, 3, 0));
  translateInstr(
      Instruction::kMove, makeOutIndScale(1, 2, 3, 0), makePhyReg(3));
#endif
```

Expected: current code still compiles because this test is a characterization
that protects the new direct lowering once implemented.

- [ ] **Step 2: Implement direct indexed memory helper**

In `autogen.cpp`, add helpers near `ptrIndirect()`:

```cpp
uint8_t accessSizeShift(const OperandBase* operand);
std::optional<arch::Mem> ptrIndirectIndexed(
    const MemoryIndirect* indirect,
    uint8_t access_shift);
```

The helper returns a direct AArch64 `a64::ptr(base, index)` when the multiplier
is 0, or `a64::ptr(base, index, a64::lsl(access_shift))` when the multiplier
matches `access_shift`. It returns `std::nullopt` for nonzero offsets,
unsupported scales, or missing index registers.

- [ ] **Step 3: Thread access size through loads and stores**

Replace indirect move load/store calls with access-size-aware calls:

```cpp
auto ptr = ptrIndirect(
    as,
    arch::reg_scratch_0,
    arch::reg_scratch_1,
    input->getMemoryIndirect(),
    accessSizeShift(output));
```

Do the analogous replacement for register and immediate stores using the
stored operand or output type. Keep `translateLea()` on the existing
`leaIndirect()` path.

- [ ] **Step 4: Run focused local/remote correctness**

Run:

```powershell
git diff --check
```

Then run the ARM remote entrypoint build with default smoke validation.

Expected: build and smoke pass on `root@124.70.162.35`.

### Task 3: Benchmark Candidate 1

**Files:**
- Read: `scripts/arm/remote_update_build_test.sh`
- Read: `scripts/arm/run_pyperf_subset.sh`
- Read: `docs/pyperformance-cinderx-integration.md`

- [ ] **Step 1: Build baseline and candidate with method parity**

Use the same host, Python, driver venv, worker hook, `AUTOJIT=50`,
`CINDERX_ENABLE_SPECIALIZED_OPCODES=1`, and `SAMPLES=5`.

High-signal subset:

```text
richards,deltablue,nqueens,comprehensions,unpack_sequence,go,raytrace,generators
```

Expected: two JSON files under `/root/work/arm-sync/`, one for baseline and one
for candidate.

- [ ] **Step 2: Classify result**

Compute row medians and geomean over common rows. Classify as:

```text
confirmed / candidate / inconclusive / noise / regression
```

Expected: only `confirmed` can satisfy the stop condition. Below 1% geomean is
noise by default; 1-3% requires repeat/A-B evidence.

- [ ] **Step 3: Continue or expand**

If a single row is near or above 30%, rerun that row/subset and then run full
JIT28. If not, continue to Task 4.

### Task 4: Next Candidates If Needed

**Files:**
- Modify: `cinderx/Jit/lir/postalloc.cpp`
- Modify: `cinderx/Jit/lir/postgen.cpp`
- Modify: `cinderx/Jit/codegen/autogen.cpp`

- [ ] **Step 1: Consider compare-result branch fusion**

Collect LIR pattern counts for single-use `Equal/Compare -> CondBranch`.
Implement only if the pattern is common in high-signal rows.

- [ ] **Step 2: Consider negative immediate canonicalization**

Implement only for AArch64 add/sub/compare forms where the opposite immediate
is encodable and semantics are unchanged.

- [ ] **Step 3: Repeat benchmark loop**

Each candidate gets its own correctness test, remote build, high-signal subset
A/B, and full JIT28 run only when it appears to meet the stop condition.

