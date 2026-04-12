# Interpreter Optimization Phase 1 Superinstruction Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first interpreter-only superinstruction pilot for CinderX by adding a tiny, explicitly-selected set of fused opcode pairs to the `3.14` / `3.15` interpreter families, validating them with repeatable interpreter-only workloads and ARM remote evidence.

**Architecture:** Keep Phase 1 deliberately small. Start with three low-risk pair superinstructions that already have prior art in CPython `3.12` (`LOAD_FAST__LOAD_FAST`, `STORE_FAST__LOAD_FAST`, `LOAD_CONST__LOAD_FAST`), wire them into both CinderX interpreter families via `cinder-bytecodes.c`, regenerate committed interpreter outputs, and validate only on interpreter-only micro workloads. Do not combine this pilot with PIC or tier2 policy work yet; the only objective is to prove that a narrow, selective superinstruction lane can be added and measured cleanly.

**Tech Stack:** CinderX interpreter bytecode DSL (`cinder-bytecodes.c`), generated interpreter case tables, CPython cases generator entry scripts, Python microbench harnesses, pytest contract tests, PowerShell + bash ARM validation entrypoints.

---

### Scope decomposition

This total design covers multiple independent subsystems:

- Phase 0: observability and target selection
- Phase 1: superinstruction / macro-op pilot
- Phase 2: small PIC pilot
- Phase 3: tier2 / executor admission policy

This plan intentionally implements **Phase 1 only**. It assumes the repository either already has Phase 0 outputs available, or the engineer is willing to use the fixed Phase 1 candidate shortlist below as the pilot seed set.

### Task 1: Add dedicated interpreter-only pilot workloads

**Files:**
- Create: `C:\work\code\cinderx4\scripts\arm\interp_superinstruction_workloads.py`
- Create: `C:\work\code\cinderx4\tests\test_interp_superinstruction_workloads.py`

- [ ] **Step 1: Write the failing workload contract tests**

```python
import dis

from scripts.arm import interp_superinstruction_workloads as workloads


def opcode_pairs(fn) -> set[str]:
    names = [instr.opname for instr in dis.get_instructions(fn)]
    return {f"{a}->{b}" for a, b in zip(names, names[1:])}


def test_load_fast_pair_loop_contains_adjacent_load_fast() -> None:
    fn = workloads.get_workload("load_fast_pair_loop")
    assert "LOAD_FAST->LOAD_FAST" in opcode_pairs(fn)


def test_store_fast_load_fast_loop_contains_store_then_load_fast() -> None:
    fn = workloads.get_workload("store_fast_load_fast_loop")
    assert "STORE_FAST->LOAD_FAST" in opcode_pairs(fn)


def test_load_const_load_fast_loop_contains_const_then_local() -> None:
    fn = workloads.get_workload("load_const_load_fast_loop")
    assert "LOAD_CONST->LOAD_FAST" in opcode_pairs(fn)


def test_unknown_workload_raises_key_error() -> None:
    try:
        workloads.get_workload("missing")
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("expected KeyError for unknown workload")
```

- [ ] **Step 2: Run the workload tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interp_superinstruction_workloads.py -q
```

Expected: FAIL because `scripts.arm.interp_superinstruction_workloads` does not exist yet.

- [ ] **Step 3: Add the workload module**

```python
from __future__ import annotations

from typing import Callable


def load_fast_pair_loop(n: int) -> int:
    total = 0
    for i in range(n):
        left = i
        right = i + 1
        total += left + right
    return total


def store_fast_load_fast_loop(n: int) -> int:
    total = 0
    current = 1
    for i in range(n):
        current = i ^ current
        total += current
    return total


def load_const_load_fast_loop(n: int) -> int:
    total = 0
    factor = 7
    for i in range(n):
        total += factor * i
    return total


WORKLOADS: dict[str, Callable[[int], int]] = {
    "load_fast_pair_loop": load_fast_pair_loop,
    "store_fast_load_fast_loop": store_fast_load_fast_loop,
    "load_const_load_fast_loop": load_const_load_fast_loop,
}


def get_workload(name: str) -> Callable[[int], int]:
    try:
        return WORKLOADS[name]
    except KeyError as exc:
        raise KeyError(f"unknown superinstruction pilot workload: {name}") from exc
```

- [ ] **Step 4: Run the workload tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interp_superinstruction_workloads.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/arm/interp_superinstruction_workloads.py tests/test_interp_superinstruction_workloads.py
git commit -m "feat: add interpreter superinstruction pilot workloads"
```

### Task 2: Teach the benchmark harness to run named pilot workloads

**Files:**
- Modify: `C:\work\code\cinderx4\scripts\arm\bench_compare_modes.py`
- Create: `C:\work\code\cinderx4\tests\test_bench_compare_modes_workloads.py`

- [ ] **Step 1: Write the failing benchmark workload-selection test**

```python
import json
import subprocess
import sys
from pathlib import Path


def test_bench_compare_modes_supports_named_superinstruction_workloads(tmp_path: Path) -> None:
    output = tmp_path / "pilot.json"
    cmd = [
        sys.executable,
        "scripts/arm/bench_compare_modes.py",
        "--runtime",
        "cpython",
        "--mode",
        "interp",
        "--workload",
        "load_fast_pair_loop",
        "--repeats",
        "1",
        "--calls",
        "1",
        "--warmup",
        "0",
        "--output",
        str(output),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["workload"] == "load_fast_pair_loop"
    assert payload["runtime"] == "cpython"
    assert payload["mode"] == "interp"
```

- [ ] **Step 2: Run the benchmark test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_bench_compare_modes_workloads.py -q
```

Expected: FAIL because `bench_compare_modes.py` does not accept `--workload` yet.

- [ ] **Step 3: Update the benchmark script to use the workload registry**

```python
from scripts.arm.interp_superinstruction_workloads import get_workload


def time_calls(fn, n: int, calls: int, repeats: int):
    times = []
    check = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        x = 0
        for _ in range(calls):
            x ^= fn(n)
        t1 = time.perf_counter()
        times.append(t1 - t0)
        check = x
    return times, check
```

```python
import statistics


def cinderx_mode(mode: str, fn, workload_name: str, n: int, warmup: int, calls: int, repeats: int):
    import cinderx.jit as jit

    jit.enable()
    jit.compile_after_n_calls(1000000)
    jit.force_uncompile(fn)

    for _ in range(warmup):
        fn(n)

    forced = bool(jit.force_compile(fn)) if mode == "jit" else False
    compiled = bool(jit.is_jit_compiled(fn)) if mode == "jit" else False
    compiled_size = int(jit.get_compiled_size(fn)) if compiled else 0
    times, check = time_calls(fn, n=n, calls=calls, repeats=repeats)
    return {
        "runtime": "cinderx",
        "mode": mode,
        "workload": workload_name,
        "forced_compile": forced,
        "is_jit_compiled": compiled,
        "compiled_size": compiled_size,
        "times_sec": times,
        "median_sec": statistics.median(times),
        "min_sec": min(times),
        "check": check,
    }


def cpython_mode(mode: str, fn, workload_name: str, n: int, warmup: int, calls: int, repeats: int):
    for _ in range(warmup):
        fn(n)
    times, check = time_calls(fn, n=n, calls=calls, repeats=repeats)
    return {
        "runtime": "cpython",
        "mode": mode,
        "workload": workload_name,
        "times_sec": times,
        "median_sec": statistics.median(times),
        "min_sec": min(times),
        "check": check,
    }


parser.add_argument(
    "--workload",
    choices=[
        "default",
        "load_fast_pair_loop",
        "store_fast_load_fast_loop",
        "load_const_load_fast_loop",
    ],
    default="default",
)
selected_workload = workload if args.workload == "default" else get_workload(args.workload)

if args.runtime == "cinderx":
    result = cinderx_mode(
        args.mode,
        selected_workload,
        args.workload,
        args.n,
        args.warmup,
        args.calls,
        args.repeats,
    )
else:
    result = cpython_mode(
        args.mode,
        selected_workload,
        args.workload,
        args.n,
        args.warmup,
        args.calls,
        args.repeats,
    )
```

- [ ] **Step 4: Run the benchmark test to verify it passes**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_bench_compare_modes_workloads.py tests/test_interp_superinstruction_workloads.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/arm/bench_compare_modes.py tests/test_bench_compare_modes_workloads.py
git commit -m "feat: add named workloads to bench_compare_modes"
```

### Task 3: Freeze the Phase 1 superinstruction candidate shortlist

**Files:**
- Create: `C:\work\code\cinderx4\scripts\arm\interpreter_superinstruction_candidates.py`
- Create: `C:\work\code\cinderx4\tests\test_interpreter_superinstruction_candidates.py`

- [ ] **Step 1: Write the failing candidate shortlist tests**

```python
from scripts.arm import interpreter_superinstruction_candidates as candidates


def test_phase1_candidate_names_are_explicit() -> None:
    names = [candidate.name for candidate in candidates.PHASE1_CANDIDATES]
    assert names == [
        "LOAD_FAST__LOAD_FAST",
        "STORE_FAST__LOAD_FAST",
        "LOAD_CONST__LOAD_FAST",
    ]


def test_phase1_candidates_are_shared_across_314_and_315() -> None:
    for candidate in candidates.PHASE1_CANDIDATES:
        assert candidate.versions == ("3.14", "3.15")
        assert len(candidate.workloads) >= 1


def test_phase1_candidates_keep_their_source_pairs() -> None:
    mapping = {
        candidate.name: candidate.source_pair
        for candidate in candidates.PHASE1_CANDIDATES
    }
    assert mapping["LOAD_FAST__LOAD_FAST"] == ("LOAD_FAST", "LOAD_FAST")
    assert mapping["STORE_FAST__LOAD_FAST"] == ("STORE_FAST", "LOAD_FAST")
    assert mapping["LOAD_CONST__LOAD_FAST"] == ("LOAD_CONST", "LOAD_FAST")
```

- [ ] **Step 2: Run the candidate tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interpreter_superinstruction_candidates.py -q
```

Expected: FAIL because the candidate module does not exist yet.

- [ ] **Step 3: Add the Phase 1 shortlist module**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SuperinstructionCandidate:
    name: str
    source_pair: tuple[str, str]
    workloads: tuple[str, ...]
    versions: tuple[str, ...]
    rationale: str


PHASE1_CANDIDATES = (
    SuperinstructionCandidate(
        name="LOAD_FAST__LOAD_FAST",
        source_pair=("LOAD_FAST", "LOAD_FAST"),
        workloads=("load_fast_pair_loop",),
        versions=("3.14", "3.15"),
        rationale="Cheap local-local pair with direct 3.12 prior art and no cache semantics.",
    ),
    SuperinstructionCandidate(
        name="STORE_FAST__LOAD_FAST",
        source_pair=("STORE_FAST", "LOAD_FAST"),
        workloads=("store_fast_load_fast_loop",),
        versions=("3.14", "3.15"),
        rationale="Common store-then-reload pattern in tiny loop bodies.",
    ),
    SuperinstructionCandidate(
        name="LOAD_CONST__LOAD_FAST",
        source_pair=("LOAD_CONST", "LOAD_FAST"),
        workloads=("load_const_load_fast_loop",),
        versions=("3.14", "3.15"),
        rationale="Const-local pair mirrors the existing 3.12 fused case and stays stack-simple.",
    ),
)
```

- [ ] **Step 4: Run the candidate tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interpreter_superinstruction_candidates.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/arm/interpreter_superinstruction_candidates.py tests/test_interpreter_superinstruction_candidates.py
git commit -m "docs: freeze phase1 superinstruction shortlist"
```

### Task 4: Add the fused opcode pairs to the 3.14 and 3.15 interpreter families

**Files:**
- Modify: `C:\work\code\cinderx4\cinderx\Interpreter\3.14\cinder-bytecodes.c`
- Modify: `C:\work\code\cinderx4\cinderx\Interpreter\3.15\cinder-bytecodes.c`
- Modify: `C:\work\code\cinderx4\cinderx\Interpreter\3.14\Includes\generated_cases.c.h`
- Modify: `C:\work\code\cinderx4\cinderx\Interpreter\3.15\Includes\generated_cases.c.h`
- Modify: `C:\work\code\cinderx4\cinderx\Interpreter\3.14\cinderx_opcode_targets.h`
- Modify: `C:\work\code\cinderx4\cinderx\Interpreter\3.15\cinderx_opcode_targets.h`
- Create: `C:\work\code\cinderx4\tests\test_interpreter_superinstruction_contract.py`

- [ ] **Step 1: Write the failing source/generated contract tests**

```python
from pathlib import Path


VERSIONS = ("3.14", "3.15")
NAMES = (
    "LOAD_FAST__LOAD_FAST",
    "STORE_FAST__LOAD_FAST",
    "LOAD_CONST__LOAD_FAST",
)


def test_superinstruction_names_are_declared_in_cinder_bytecodes() -> None:
    for version in VERSIONS:
        text = Path(f"cinderx/Interpreter/{version}/cinder-bytecodes.c").read_text(encoding="utf-8")
        for name in NAMES:
            assert f"super({name})" in text


def test_generated_cases_contain_superinstruction_targets() -> None:
    for version in VERSIONS:
        text = Path(f"cinderx/Interpreter/{version}/Includes/generated_cases.c.h").read_text(encoding="utf-8")
        for name in NAMES:
            assert f"TARGET({name})" in text


def test_opcode_target_tables_know_about_superinstructions() -> None:
    for version in VERSIONS:
        text = Path(f"cinderx/Interpreter/{version}/cinderx_opcode_targets.h").read_text(encoding="utf-8")
        for name in NAMES:
            assert name in text
```

- [ ] **Step 2: Run the contract tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interpreter_superinstruction_contract.py -q
```

Expected: FAIL because the Phase 1 names do not exist in `3.14` / `3.15` yet.

- [ ] **Step 3: Add the fused definitions to both interpreter families**

Insert the same three `super(...)` definitions immediately after `// BEGIN BYTECODES //` in both `cinderx/Interpreter/3.14/cinder-bytecodes.c` and `cinderx/Interpreter/3.15/cinder-bytecodes.c`:

```c
        // Phase 1 pilot: keep the first fused pairs tiny, stack-simple, and
        // aligned with the proven 3.12 superinstruction naming scheme.
        super(LOAD_FAST__LOAD_FAST) = LOAD_FAST + LOAD_FAST;
        super(STORE_FAST__LOAD_FAST) = STORE_FAST + LOAD_FAST;
        super(LOAD_CONST__LOAD_FAST) = LOAD_CONST + LOAD_FAST;
```

Then regenerate the committed interpreter outputs:

```bash
bash cinderx/Interpreter/regen-cases-314.sh
bash cinderx/Interpreter/regen-cases-315.sh
```

If the local OSS workspace does not contain the internal generator trees referenced by the existing regen scripts (`third-party/python/3.14/patched/Tools/cases_generator` for `3.14` and `third-party/python/main/patched/Tools/cases_generator` for `3.15`), run those commands in the standard internal environment that already regenerates `generated_cases.c.h` and `cinderx_opcode_targets.h`, then copy the regenerated outputs back into this checkout before testing.

- [ ] **Step 4: Run the contract tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interpreter_superinstruction_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cinderx/Interpreter/3.14/cinder-bytecodes.c cinderx/Interpreter/3.15/cinder-bytecodes.c cinderx/Interpreter/3.14/Includes/generated_cases.c.h cinderx/Interpreter/3.15/Includes/generated_cases.c.h cinderx/Interpreter/3.14/cinderx_opcode_targets.h cinderx/Interpreter/3.15/cinderx_opcode_targets.h tests/test_interpreter_superinstruction_contract.py
git commit -m "feat: add phase1 interpreter superinstruction pilot"
```

### Task 5: Add a dedicated ARM pilot driver and record interpreter-only evidence

**Files:**
- Create: `C:\work\code\cinderx4\scripts\arm\interp_superinstruction_pilot.sh`
- Create: `C:\work\code\cinderx4\tests\test_interp_superinstruction_pilot_contract.py`
- Modify: `C:\work\code\cinderx4\findings.md`

- [ ] **Step 1: Write the failing pilot-driver contract tests**

```python
from pathlib import Path


def test_pilot_driver_runs_all_three_phase1_workloads() -> None:
    text = Path("scripts/arm/interp_superinstruction_pilot.sh").read_text(encoding="utf-8")
    assert "load_fast_pair_loop" in text
    assert "store_fast_load_fast_loop" in text
    assert "load_const_load_fast_loop" in text
    assert "bench_compare_modes.py" in text
```

- [ ] **Step 2: Run the pilot-driver contract test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interp_superinstruction_pilot_contract.py -q
```

Expected: FAIL because the pilot driver does not exist yet.

- [ ] **Step 3: Add the pilot driver script**

```bash
#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${WORKDIR:-/root/work/cinderx-main}"
DRIVER_VENV="${DRIVER_VENV:-/root/venv-cinderx314}"
CPYTHON_PY="${CPYTHON_PY:-/opt/python-3.14/bin/python3.14}"
N="${N:-250}"
WARMUP="${WARMUP:-20000}"
CALLS="${CALLS:-12000}"
REPEATS="${REPEATS:-5}"
OUT_DIR="${OUT_DIR:-/root/work/arm-sync/interp_superinstruction_pilot}"
mkdir -p "$OUT_DIR"

DRIVER_PY="$DRIVER_VENV/bin/python"
WORKLOADS=(
  load_fast_pair_loop
  store_fast_load_fast_loop
  load_const_load_fast_loop
)

for workload in "${WORKLOADS[@]}"; do
  env PYTHON_JIT=0 "$CPYTHON_PY" "$WORKDIR/scripts/arm/bench_compare_modes.py" \
    --runtime cpython --mode interp --workload "$workload" \
    --n "$N" --warmup "$WARMUP" --calls "$CALLS" --repeats "$REPEATS" \
    --output "$OUT_DIR/${workload}.cpython.json"

  env PYTHONJITDISABLE=1 "$DRIVER_PY" "$WORKDIR/scripts/arm/bench_compare_modes.py" \
    --runtime cinderx --mode interp --workload "$workload" \
    --n "$N" --warmup "$WARMUP" --calls "$CALLS" --repeats "$REPEATS" \
    --output "$OUT_DIR/${workload}.cinderx.json"
done
```

- [ ] **Step 4: Run the local contract tests and one ARM remote pilot**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interp_superinstruction_workloads.py tests/test_bench_compare_modes_workloads.py tests/test_interpreter_superinstruction_candidates.py tests/test_interpreter_superinstruction_contract.py tests/test_interp_superinstruction_pilot_contract.py -q
```

Expected: PASS.

Remote verification command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx4 `
  -SkipPyperformance `
  -SkipArmRuntimeValidation `
  -ExtraVerifyCmd "bash scripts/arm/interp_superinstruction_pilot.sh && ls -1 /root/work/arm-sync/interp_superinstruction_pilot"
```

Expected: the remote command prints six JSON artifacts:
- `load_fast_pair_loop.cpython.json`
- `load_fast_pair_loop.cinderx.json`
- `store_fast_load_fast_loop.cpython.json`
- `store_fast_load_fast_loop.cinderx.json`
- `load_const_load_fast_loop.cpython.json`
- `load_const_load_fast_loop.cinderx.json`

- [ ] **Step 5: Record the Phase 1 pilot evidence**

Add to `findings.md`:

```markdown
- 2026-04-12 phase1: interpreter superinstruction pilot
  - pilot names:
    - `LOAD_FAST__LOAD_FAST`
    - `STORE_FAST__LOAD_FAST`
    - `LOAD_CONST__LOAD_FAST`
  - interpreter families updated:
    - `3.14`
    - `3.15`
  - pilot workloads:
    - `load_fast_pair_loop`
    - `store_fast_load_fast_loop`
    - `load_const_load_fast_loop`
  - remote artifact root:
    - `/root/work/arm-sync/interp_superinstruction_pilot`
  - note:
    - this phase validates only selective pair superinstructions
    - PIC and tier2 remain out of scope for this pilot
```

- [ ] **Step 6: Commit**

```bash
git add scripts/arm/interp_superinstruction_pilot.sh tests/test_interp_superinstruction_pilot_contract.py findings.md
git commit -m "docs: record phase1 superinstruction pilot evidence"
```
