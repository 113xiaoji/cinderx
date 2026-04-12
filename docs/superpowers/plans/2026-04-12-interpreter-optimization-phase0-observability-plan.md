# Interpreter Optimization Phase 0 Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first explainable observability layer for interpreter-only optimization work by adding stable opcode-shape profiling outputs and candidate-selection reporting, without changing interpreter execution behavior.

**Architecture:** Keep Phase 0 narrow and data-oriented. Add Python-level opcode-shape profiling and reporting to the existing benchmark harness first, using current workloads to identify stable hot sequences and cache-sensitive families. Delay any bytecode or interpreter behavior changes until the repository has a repeatable evidence loop for `3.14` / `3.15`.

**Tech Stack:** Python benchmark scripts, `dis`-based opcode analysis, JSON reporting, pytest/unittest contract tests, existing ARM benchmark entry scripts.

---

### Scope decomposition

This total design covers multiple independent subsystems:

- Phase 0: observability and target selection
- Phase 1: superinstruction / macro-op pilot
- Phase 2: small PIC pilot
- Phase 3: tier2 / executor admission policy

This plan intentionally implements **Phase 0 only**. Follow-up plans should be written separately for superinstructions, PIC, and tier2 once Phase 0 produces stable evidence.

### Task 1: Add reusable opcode-shape profiling helpers

**Files:**
- Create: `C:\work\code\cinderx4\scripts\arm\interp_opcode_profile.py`
- Create: `C:\work\code\cinderx4\tests\test_interp_opcode_profile.py`

- [ ] **Step 1: Write the failing contract tests**

```python
from scripts.arm import interp_opcode_profile as profile


def sample_loop(xs):
    total = 0
    for x in xs:
        total += x
    return total


def test_collect_opcode_names_returns_instruction_sequence() -> None:
    names = profile.collect_opcode_names(sample_loop)
    assert "FOR_ITER" in names
    assert "BINARY_OP" in names or "BINARY_ADD" in names


def test_collect_opcode_pairs_counts_adjacent_pairs() -> None:
    pairs = profile.collect_opcode_pairs(sample_loop)
    assert isinstance(pairs, dict)
    assert all(isinstance(k, str) for k in pairs)
    assert all(isinstance(v, int) for v in pairs.values())


def test_collect_backedge_offsets_finds_loop_backedges() -> None:
    offsets = profile.collect_backedge_offsets(sample_loop)
    assert isinstance(offsets, list)
    assert all(isinstance(off, int) for off in offsets)
    assert len(offsets) >= 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interp_opcode_profile.py -q
```

Expected: FAIL because `scripts.arm.interp_opcode_profile` does not exist yet.

- [ ] **Step 3: Implement the profiling helper module**

```python
import dis
from collections import Counter


def collect_opcode_names(fn) -> list[str]:
    return [instr.opname for instr in dis.get_instructions(fn)]


def collect_opcode_pairs(fn) -> dict[str, int]:
    names = collect_opcode_names(fn)
    counts = Counter(f"{a}->{b}" for a, b in zip(names, names[1:]))
    return dict(sorted(counts.items()))


def collect_backedge_offsets(fn) -> list[int]:
    return [instr.offset for instr in dis.get_instructions(fn) if instr.opname == "JUMP_BACKWARD"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interp_opcode_profile.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/arm/interp_opcode_profile.py tests/test_interp_opcode_profile.py
git commit -m "feat: add interpreter opcode profiling helpers"
```

### Task 2: Extend `bench_compare_modes.py` with interpreter-shape reporting

**Files:**
- Modify: `C:\work\code\cinderx4\scripts\arm\bench_compare_modes.py`
- Create: `C:\work\code\cinderx4\tests\test_bench_compare_modes_contract.py`

- [ ] **Step 1: Write the failing JSON contract tests**

```python
import json
import subprocess
import sys


def test_bench_compare_modes_emits_opcode_shape_metadata(tmp_path) -> None:
    output = tmp_path / "result.json"
    cmd = [
        sys.executable,
        "scripts/arm/bench_compare_modes.py",
        "--runtime",
        "cpython",
        "--mode",
        "interp",
        "--repeats",
        "1",
        "--calls",
        "1",
        "--warmup",
        "0",
        "--output",
        str(output),
    ]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(output.read_text(encoding="utf-8"))
    assert "opcode_profile" in data
    assert "opcode_names" in data["opcode_profile"]
    assert "opcode_pairs" in data["opcode_profile"]
    assert "backedge_offsets" in data["opcode_profile"]
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_bench_compare_modes_contract.py -q
```

Expected: FAIL because the script does not yet emit `opcode_profile`.

- [ ] **Step 3: Update the benchmark script to include opcode-shape metadata**

```python
from scripts.arm.interp_opcode_profile import (
    collect_backedge_offsets,
    collect_opcode_names,
    collect_opcode_pairs,
)


def opcode_profile(fn) -> dict[str, object]:
    return {
        "opcode_names": collect_opcode_names(fn),
        "opcode_pairs": collect_opcode_pairs(fn),
        "backedge_offsets": collect_backedge_offsets(fn),
    }
```

```python
result["opcode_profile"] = opcode_profile(workload)
```

- [ ] **Step 4: Run the contract test to verify it passes**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_bench_compare_modes_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/arm/bench_compare_modes.py tests/test_bench_compare_modes_contract.py
git commit -m "feat: emit interpreter opcode shape metadata"
```

### Task 3: Add a candidate-summary report for first-phase workloads

**Files:**
- Create: `C:\work\code\cinderx4\scripts\arm\interpreter_candidate_report.py`
- Create: `C:\work\code\cinderx4\tests\test_interpreter_candidate_report.py`

- [ ] **Step 1: Write the failing report tests**

```python
import json
from pathlib import Path

from scripts.arm import interpreter_candidate_report as report


def test_report_summarizes_top_opcode_pairs(tmp_path: Path) -> None:
    payload = {
        "runtime": "cpython",
        "mode": "interp",
        "opcode_profile": {
            "opcode_names": ["LOAD_FAST", "LOAD_FAST", "BINARY_OP"],
            "opcode_pairs": {
                "LOAD_FAST->LOAD_FAST": 2,
                "LOAD_FAST->BINARY_OP": 1,
            },
            "backedge_offsets": [10],
        },
    }
    sample = tmp_path / "sample.json"
    sample.write_text(json.dumps(payload), encoding="utf-8")
    summary = report.summarize_payloads([sample])
    assert "top_opcode_pairs" in summary
    assert summary["top_opcode_pairs"][0]["pair"] == "LOAD_FAST->LOAD_FAST"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interpreter_candidate_report.py -q
```

Expected: FAIL because `scripts.arm.interpreter_candidate_report` does not exist yet.

- [ ] **Step 3: Implement the candidate summary script**

```python
import json
from collections import Counter
from pathlib import Path


def summarize_payloads(paths: list[Path]) -> dict[str, object]:
    pair_counter = Counter()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        pair_counter.update(payload["opcode_profile"]["opcode_pairs"])
    top_pairs = [
        {"pair": pair, "count": count}
        for pair, count in pair_counter.most_common(20)
    ]
    return {"top_opcode_pairs": top_pairs}
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interpreter_candidate_report.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/arm/interpreter_candidate_report.py tests/test_interpreter_candidate_report.py
git commit -m "feat: add interpreter candidate summary report"
```

### Task 4: Wire first-phase workload selection into the ARM validation flow

**Files:**
- Modify: `C:\work\code\cinderx4\scripts\arm\interp_feature_matrix.sh`
- Modify: `C:\work\code\cinderx4\findings.md`

- [ ] **Step 1: Add a failing contract check for candidate workload output**

```python
from pathlib import Path


def test_feature_matrix_mentions_candidate_summary() -> None:
    text = Path("scripts/arm/interp_feature_matrix.sh").read_text(encoding="utf-8")
    assert "interpreter_candidate_report.py" in text
```

- [ ] **Step 2: Run the contract check to verify it fails**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interpreter_candidate_report.py -q
```

Expected: FAIL after extending the test because the matrix script does not yet invoke the report.

- [ ] **Step 3: Update the ARM script to emit a candidate summary artifact**

```bash
python scripts/arm/interpreter_candidate_report.py \
  --inputs "$OUT_DIR"/*.json \
  --output "$OUT_DIR/interpreter_candidate_summary.json"
```

- [ ] **Step 4: Run the local report tests and one remote dry-run verification**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interp_opcode_profile.py tests/test_bench_compare_modes_contract.py tests/test_interpreter_candidate_report.py -q
```

Expected: PASS.

Remote verification command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx4 `
  -SkipPyperformance `
  -SkipArmRuntimeValidation `
  -ExtraTestCmd "python scripts/arm/bench_compare_modes.py --runtime cpython --mode interp --repeats 1 --calls 1 --warmup 0 --output /tmp/interp_one.json && python scripts/arm/interpreter_candidate_report.py --inputs /tmp/interp_one.json --output /tmp/interp_summary.json && cat /tmp/interp_summary.json"
```

Expected: remote command prints a valid `top_opcode_pairs` summary JSON object.

- [ ] **Step 5: Record Phase 0 evidence**

Add to `findings.md`:

```markdown
- 2026-04-12 phase0: interpreter observability
  - benchmark payloads now include:
    - `opcode_names`
    - `opcode_pairs`
    - `backedge_offsets`
  - candidate summary artifact:
    - `interpreter_candidate_summary.json`
  - first-phase target workloads:
    - `richards`
    - `richards_super`
    - `go`
    - `deltablue`
    - `unpickle_pure_python`
```

- [ ] **Step 6: Commit**

```bash
git add scripts/arm/interp_feature_matrix.sh findings.md
git commit -m "docs: record interpreter phase0 observability evidence"
```
