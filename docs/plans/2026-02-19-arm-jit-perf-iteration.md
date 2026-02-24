# ARM JIT Performance Iteration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver one additional measurable ARM64 JIT optimization iteration with verified `from -> to` gains (or explicit no-gain conclusion) using the existing remote gate flow.

**Architecture:** Keep the current AArch64 JIT pipeline intact, identify one benchmark-relevant ARM codegen gap from real logs, and apply a minimal codegen/test change. Validate via local targeted tests and remote unified benchmark flow.

**Tech Stack:** C++ (CinderX JIT codegen), Python test harness, PowerShell deploy script, ARM remote benchmark host.

---

### Task 1: Re-establish baseline evidence

**Files:**
- Modify: `progress.md`
- Modify: `findings.md`

**Step 1: Run baseline remote pipeline**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath d:\code\cinderx-upstream-20260213 `
  -WorkBranch arm-jit-perf `
  -ArmHost 124.70.162.35 `
  -Benchmark richards
```

**Step 2: Verify baseline artifacts exist**

Expected:
- ARM test gate passes
- richards jitlist/autojit artifact paths printed
- JIT log path printed

**Step 3: Write baseline notes**

Update `findings.md` and `progress.md` with baseline values and artifact paths.

### Task 2: Identify one optimization target from workload evidence

**Files:**
- Modify: `notes.md` (create if missing)
- Modify: `task_plan.md`

**Step 1: Mine benchmark log**

Run command(s) to extract compile failures, unsupported op traces, and compilation counts from remote log files.

**Step 2: Choose one low-risk target**

Document:
- exact file/line area
- expected impact
- why low-risk

**Step 3: Record decision**

Update `task_plan.md` decisions and `notes.md` findings.

### Task 3: TDD regression/perf guard setup

**Files:**
- Modify or create: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

**Step 1: Add a failing test for target behavior**

Test should fail at baseline for the selected gap and pass after implementation.

**Step 2: Run targeted test and capture failing output**

Run:

```powershell
python -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k <new_test_name> -q
```

Expected:
- FAIL for expected reason.

### Task 4: Implement minimal code change

**Files:**
- Modify: one of
  - `cinderx/Jit/codegen/autogen.cpp`
  - `cinderx/Jit/codegen/gen_asm.cpp`
  - `cinderx/Jit/codegen/gen_asm_utils.cpp`
  - related headers

**Step 1: Implement minimal fix/optimization**

- Keep changes small and local.
- Avoid unrelated refactors.

**Step 2: Run targeted test**

Expected:
- New test now PASS.

### Task 5: Full verification and perf comparison

**Files:**
- Modify: `findings.md`
- Modify: `progress.md`
- Modify: `task_plan.md`

**Step 1: Run local targeted checks**

Run required local unit tests for touched behavior.

**Step 2: Run remote unified flow again**

Use same command as baseline to keep comparison fair.

**Step 3: Compare and document**

Must include:
- `from -> to` numbers for richards jitlist/autojit
- compiled-size guard result if relevant
- JIT activity proof
- explicit statement: real improvement / no clear improvement

### Task 6: Branch hygiene and handoff

**Files:**
- Modify: `progress.md`

**Step 1: Summarize changed files and test evidence**

**Step 2: Commit**

```bash
git add <touched files>
git commit -m "AArch64: <specific optimization summary>"
```

**Step 3: Push**

```bash
git push xiaoji arm-jit-perf
```
