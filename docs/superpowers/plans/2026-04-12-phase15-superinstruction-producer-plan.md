# Phase 1.5 Superinstruction Producer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real producer for the new double-underscore Phase 1 superinstructions, make the pilot workloads run through that producer on `3.14`, and upgrade verification from static contracts to “emitted + executed + evidenced”.

**Architecture:** Keep the existing interpreter consumer wiring from Phase 1, but add a new explicit producer lane through the Cinder Python compiler. Use a source-backed workload registry so the same workload definition can feed both the default producer and the Cinder producer, then teach the benchmark/pilot scripts to record emitted superinstruction evidence. Runtime closure is required only for `3.14`; `3.15` remains static-wiring-only in this phase.

**Tech Stack:** Cinder Python compiler (`pyassem.py`, `opcodes.py`, `pycodegen.py`), ARM benchmark scripts, pytest, existing `test_compiler` helpers, unified ARM entrypoint (`scripts/push_to_arm.ps1` / `scripts/arm/remote_update_build_test.sh`).

---

### File structure

- `C:\work\code\cinderx4\scripts\arm\interp_superinstruction_workloads.py`
  - Source-backed workload registry and helpers for default producer vs. Cinder producer.
- `C:\work\code\cinderx4\tests\test_interp_superinstruction_workloads.py`
  - Registry/source contract tests.
- `C:\work\code\cinderx4\cinderx\PythonLib\cinderx\compiler\pyassem.py`
  - Superinstruction producer logic.
- `C:\work\code\cinderx4\cinderx\PythonLib\cinderx\compiler\opcodes.py`
  - Stack-effect / producer metadata for the new double-underscore opcodes.
- `C:\work\code\cinderx4\tests\test_cinder_compiler_superinstructions.py`
  - Local producer-oriented unit tests using a minimal `cinderx.opcode` stub.
- `C:\work\code\cinderx4\scripts\arm\bench_compare_modes.py`
  - Producer selection and emitted-evidence JSON.
- `C:\work\code\cinderx4\tests\test_bench_compare_modes_workloads.py`
  - Producer CLI / JSON contract tests.
- `C:\work\code\cinderx4\scripts\arm\interp_superinstruction_pilot.sh`
  - `3.14` pilot driver using the new `cinder` producer path.
- `C:\work\code\cinderx4\tests\test_interp_superinstruction_pilot_contract.py`
  - Pilot driver contract tests.
- `C:\work\code\cinderx4\findings.md`
  - Final emitted/runtime evidence and unified-entrypoint result.

### Task 1: Upgrade the workload registry to source-backed specs

**Files:**
- Modify: `C:\work\code\cinderx4\scripts\arm\interp_superinstruction_workloads.py`
- Modify: `C:\work\code\cinderx4\tests\test_interp_superinstruction_workloads.py`

- [ ] **Step 1: Write the failing registry/source tests**

```python
from scripts.arm import interp_superinstruction_workloads as workloads


def test_workload_specs_include_entry_name_and_source() -> None:
    spec = workloads.get_workload_spec("load_fast_pair_loop")
    assert spec.entry_name == "load_fast_pair_loop"
    assert "def load_fast_pair_loop" in spec.source
    assert spec.target_pair == "LOAD_FAST->LOAD_FAST"


def test_get_workload_names_is_stable() -> None:
    assert workloads.get_workload_names() == (
        "load_fast_pair_loop",
        "store_fast_load_fast_loop",
        "load_const_load_fast_loop",
    )


def test_default_workload_builder_executes_source() -> None:
    fn = workloads.get_workload("load_const_load_fast_loop")
    assert isinstance(fn(8), int)
    assert fn(8) == fn(8)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interp_superinstruction_workloads.py -q
```

Expected: FAIL because the registry does not yet expose `entry_name`, `source`, or a stable `get_workload_names()` API.

- [ ] **Step 3: Implement source-backed workload specs**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class WorkloadSpec:
    name: str
    target_pair: str
    entry_name: str
    source: str
```

```python
WORKLOAD_SPECS: tuple[WorkloadSpec, ...] = (
    WorkloadSpec(
        name="load_fast_pair_loop",
        target_pair="LOAD_FAST->LOAD_FAST",
        entry_name="load_fast_pair_loop",
        source="""\
def load_fast_pair_loop(n):
    total = 0
    for i in range(n):
        left = i
        right = i + 1
        total += left + right
    return total
""",
    ),
    WorkloadSpec(
        name="store_fast_load_fast_loop",
        target_pair="STORE_FAST->LOAD_FAST",
        entry_name="store_fast_load_fast_loop",
        source="""\
def store_fast_load_fast_loop(n):
    total = 0
    current = 1
    for i in range(n):
        current = i ^ current
        total += current
    return total
""",
    ),
    WorkloadSpec(
        name="load_const_load_fast_loop",
        target_pair="LOAD_CONST->LOAD_FAST",
        entry_name="load_const_load_fast_loop",
        source="""\
def load_const_load_fast_loop(n):
    total = 0
    factor = 7
    for i in range(n):
        total += factor * i
    return total
""",
    ),
)


def get_workload_spec(name: str) -> WorkloadSpec:
    for spec in WORKLOAD_SPECS:
        if spec.name == name:
            return spec
    raise KeyError(f"unknown superinstruction pilot workload: {name}")


def get_workload_names() -> tuple[str, ...]:
    return tuple(spec.name for spec in WORKLOAD_SPECS)


def build_default_workload(spec: WorkloadSpec) -> Callable[[int], int]:
    namespace: dict[str, object] = {}
    exec(compile(spec.source, f"<{spec.name}>", "exec"), namespace, namespace)
    fn = namespace[spec.entry_name]
    assert callable(fn)
    return fn  # type: ignore[return-value]


def get_workload(name: str) -> Callable[[int], int]:
    return build_default_workload(get_workload_spec(name))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interp_superinstruction_workloads.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/arm/interp_superinstruction_workloads.py tests/test_interp_superinstruction_workloads.py
git commit -m "refactor: make superinstruction workloads source-backed"
```

### Task 2: Teach the compiler producer to emit the new double-underscore opcodes

**Files:**
- Modify: `C:\work\code\cinderx4\cinderx\PythonLib\cinderx\compiler\pyassem.py`
- Modify: `C:\work\code\cinderx4\cinderx\PythonLib\cinderx\compiler\opcodes.py`
- Create: `C:\work\code\cinderx4\tests\test_cinder_compiler_superinstructions.py`

- [ ] **Step 1: Write the failing producer tests**

```python
import dis
import importlib
import sys
import types
from pathlib import Path
from types import CodeType


PYLIB = Path(__file__).resolve().parents[1] / "cinderx" / "PythonLib"
SUPER_OPS = {
    "LOAD_CONST__LOAD_FAST": 122,
    "LOAD_FAST__LOAD_FAST": 123,
    "STORE_FAST__LOAD_FAST": 124,
}


def install_fake_cinderx_opcode() -> None:
    fake = types.ModuleType("cinderx.opcode")

    def init(all_opnames, all_opmap, *_args):
        for name, op in SUPER_OPS.items():
            all_opnames[op] = name
            all_opmap[name] = op

    fake.init = init  # type: ignore[attr-defined]
    sys.modules["cinderx.opcode"] = fake


def compile_function(source: str, fn_name: str) -> CodeType:
    install_fake_cinderx_opcode()
    sys.path.insert(0, str(PYLIB))
    for mod in (
        "cinderx.compiler.opcodes",
        "cinderx.compiler.pyassem",
        "cinderx.compiler.pycodegen",
    ):
        sys.modules.pop(mod, None)
    from cinderx.compiler.pycodegen import compile_code

    module_code = compile_code(source, "<producer-test>", "exec")
    for const in module_code.co_consts:
        if isinstance(const, CodeType) and const.co_name == fn_name:
            return const
    raise AssertionError(f"missing function code object: {fn_name}")


def test_load_fast_pair_emits_new_dunder_superinstruction() -> None:
    code = compile_function(
        '''
def f(n):
    total = 0
    for i in range(n):
        left = i
        right = i + 1
        total += left + right
    return total
''',
        "f",
    )
    opnames = [instr.opname for instr in dis.get_instructions(code)]
    assert "LOAD_FAST__LOAD_FAST" in opnames
    assert "LOAD_FAST_LOAD_FAST" not in opnames


def test_store_fast_load_fast_emits_new_dunder_superinstruction() -> None:
    code = compile_function(
        '''
def f(n):
    total = 0
    current = 1
    for i in range(n):
        current = i ^ current
        total += current
    return total
''',
        "f",
    )
    opnames = [instr.opname for instr in dis.get_instructions(code)]
    assert "STORE_FAST__LOAD_FAST" in opnames
    assert "STORE_FAST_LOAD_FAST" not in opnames


def test_load_const_load_fast_emits_new_dunder_superinstruction() -> None:
    code = compile_function(
        '''
def f(n):
    total = 0
    factor = 7
    for i in range(n):
        total += factor * i
    return total
''',
        "f",
    )
    opnames = [instr.opname for instr in dis.get_instructions(code)]
    assert "LOAD_CONST__LOAD_FAST" in opnames
```

- [ ] **Step 2: Run the producer tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_cinder_compiler_superinstructions.py -q
```

Expected: FAIL because `pyassem.py` still emits the old single-underscore forms and does not handle `LOAD_CONST + LOAD_FAST`.

- [ ] **Step 3: Implement the new producer and metadata**

```python
# cinderx/PythonLib/cinderx/compiler/pyassem.py
elif opcode == "LOAD_FAST__LOAD_FAST":
    local1 = ioparg >> 4
    local2 = ioparg & 0xF
    refs.append(Ref(i, local1))
    refs.append(Ref(i, local2))

elif opcode == "LOAD_CONST__LOAD_FAST":
    refs.append(Ref(i, NOT_LOCAL))
    local = ioparg & 0xF
    refs.append(Ref(i, local))

elif opcode == "STORE_FAST__LOAD_FAST":
    r = refs.pop()
    local1 = ioparg >> 4
    local2 = ioparg & 0xF
    self.store_local(instr_flags, refs, local1, r)
    refs.append(Ref(i, local2))
```

```python
# cinderx/PythonLib/cinderx/compiler/pyassem.py
def insert_superinstructions(self) -> None:
    for block in self.ordered_blocks:
        for i, instr in enumerate(block.insts):
            if i + 1 == len(block.insts):
                break
            next_instr = block.insts[i + 1]
            if instr.opname == "LOAD_CONST" and next_instr.opname == "LOAD_FAST":
                self.make_super_instruction(instr, next_instr, "LOAD_CONST__LOAD_FAST")
            elif instr.opname == "LOAD_FAST" and next_instr.opname == "LOAD_FAST":
                self.make_super_instruction(instr, next_instr, "LOAD_FAST__LOAD_FAST")
            elif instr.opname == "STORE_FAST" and next_instr.opname == "LOAD_FAST":
                self.make_super_instruction(instr, next_instr, "STORE_FAST__LOAD_FAST")
            elif instr.opname == "STORE_FAST" and next_instr.opname == "STORE_FAST":
                self.make_super_instruction(instr, next_instr, "STORE_FAST_STORE_FAST")
```

```python
# cinderx/PythonLib/cinderx/compiler/opcodes.py
opcode.popped.update(
    LOAD_CONST__LOAD_FAST=0,
    LOAD_FAST__LOAD_FAST=0,
    STORE_FAST__LOAD_FAST=1,
)

opcode.pushed.update(
    LOAD_CONST__LOAD_FAST=2,
    LOAD_FAST__LOAD_FAST=2,
    STORE_FAST__LOAD_FAST=1,
)
```

- [ ] **Step 4: Run the producer tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_cinder_compiler_superinstructions.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cinderx/PythonLib/cinderx/compiler/pyassem.py cinderx/PythonLib/cinderx/compiler/opcodes.py tests/test_cinder_compiler_superinstructions.py
git commit -m "feat: emit phase15 double-underscore superinstructions"
```

### Task 3: Add producer-aware benchmark output and emitted-superinstruction evidence

**Files:**
- Modify: `C:\work\code\cinderx4\scripts\arm\bench_compare_modes.py`
- Modify: `C:\work\code\cinderx4\tests\test_bench_compare_modes_workloads.py`
- Modify: `C:\work\code\cinderx4\scripts\arm\interp_superinstruction_pilot.sh`
- Modify: `C:\work\code\cinderx4\tests\test_interp_superinstruction_pilot_contract.py`

- [ ] **Step 1: Write the failing benchmark/pilot contract tests**

```python
from pathlib import Path

from scripts.arm import interp_superinstruction_workloads as workloads


def test_bench_compare_modes_exposes_producer_choices() -> None:
    import scripts.arm.bench_compare_modes as bench

    parser = bench.build_parser()
    producer_action = next(action for action in parser._actions if action.dest == "producer")
    assert producer_action.choices == ("default", "cinder")


def test_cpython_default_output_includes_producer_and_emission_fields(tmp_path: Path) -> None:
    import json
    import subprocess
    import sys

    output = tmp_path / "out.json"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/arm/bench_compare_modes.py",
            "--runtime",
            "cpython",
            "--mode",
            "interp",
            "--producer",
            "default",
            "--workload",
            "load_fast_pair_loop",
            "--warmup",
            "0",
            "--calls",
            "1",
            "--repeats",
            "1",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["producer"] == "default"
    assert payload["emitted_superinstructions"] == []


def test_cpython_rejects_cinder_producer() -> None:
    import subprocess
    import sys

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/arm/bench_compare_modes.py",
            "--runtime",
            "cpython",
            "--mode",
            "interp",
            "--producer",
            "cinder",
            "--workload",
            "load_fast_pair_loop",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "cinder producer requires --runtime cinderx" in proc.stderr
```

```python
def test_pilot_script_runs_cinder_producer() -> None:
    text = Path("scripts/arm/interp_superinstruction_pilot.sh").read_text(encoding="utf-8")
    assert "--producer cinder" in text
    assert ".cinderx.cinder.json" in text
```

- [ ] **Step 2: Run the contract tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_bench_compare_modes_workloads.py tests/test_interp_superinstruction_pilot_contract.py -q
```

Expected: FAIL because there is no `--producer` option yet and the pilot script does not run the Cinder producer.

- [ ] **Step 3: Implement producer selection and emitted evidence**

```python
# scripts/arm/bench_compare_modes.py
parser.add_argument("--producer", choices=["default", "cinder"], default="default")
```

```python
def load_cinder_workload(workload_name: str):
    from cinderx.compiler import exec_cinder
    from scripts.arm.interp_superinstruction_workloads import get_workload_spec

    spec = get_workload_spec(workload_name)
    namespace: dict[str, object] = {}
    exec_cinder(spec.source, namespace, namespace, modname=f"pilot::{spec.name}")
    fn = namespace[spec.entry_name]
    assert callable(fn)
    return fn
```

```python
def collect_emitted_superinstructions(fn) -> list[str]:
    names = [instr.opname for instr in dis.get_instructions(fn)]
    return [
        name
        for name in (
            "LOAD_CONST__LOAD_FAST",
            "LOAD_FAST__LOAD_FAST",
            "STORE_FAST__LOAD_FAST",
        )
        if name in names
    ]
```

```python
if args.producer == "cinder":
    if args.runtime != "cinderx":
        raise SystemExit("cinder producer requires --runtime cinderx")
    if args.workload == "default":
        raise SystemExit("cinder producer requires a named pilot workload")
    fn = load_cinder_workload(args.workload)
else:
    fn = workload if args.workload == "default" else get_workload(args.workload)
```

```python
result["producer"] = args.producer
result["emitted_superinstructions"] = collect_emitted_superinstructions(fn)
```

```bash
# scripts/arm/interp_superinstruction_pilot.sh
env PYTHONJITDISABLE=1 "$DRIVER_PY" "$BENCH_SCRIPT" \
  --runtime cinderx \
  --mode interp \
  --producer cinder \
  --workload "$workload" \
  --n "$N" \
  --warmup "$WARMUP" \
  --calls "$CALLS" \
  --repeats "$REPEATS" \
  --output "$OUT_DIR/${workload}.cinderx.cinder.json"
```

- [ ] **Step 4: Run the contract tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_bench_compare_modes_workloads.py tests/test_interp_superinstruction_pilot_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/arm/bench_compare_modes.py tests/test_bench_compare_modes_workloads.py scripts/arm/interp_superinstruction_pilot.sh tests/test_interp_superinstruction_pilot_contract.py
git commit -m "feat: add producer-aware superinstruction benchmark evidence"
```

### Task 4: Validate 3.14 runtime emission through the unified ARM entrypoint

**Files:**
- Modify: `C:\work\code\cinderx4\findings.md`

- [ ] **Step 1: Add the failing acceptance note to `findings.md`**

Add this temporary acceptance target near the current Phase 1 section:

```markdown
- Phase 1.5 pending closure:
  - need one `3.14` unified-entrypoint run where:
    - `producer == "cinder"`
    - emitted evidence contains at least one of:
      - `LOAD_FAST__LOAD_FAST`
      - `STORE_FAST__LOAD_FAST`
      - `LOAD_CONST__LOAD_FAST`
```

- [ ] **Step 2: Run the local producer-focused regression suite**

Run:

```powershell
$env:PYTHONPATH='.'
uv run --python 3.12 --no-project --with pytest python -m pytest tests/test_interp_superinstruction_workloads.py tests/test_cinder_compiler_superinstructions.py tests/test_bench_compare_modes_workloads.py tests/test_interp_superinstruction_pilot_contract.py -q
```

Expected: PASS.

- [ ] **Step 3: Run one unified ARM verification for the `3.14` producer path**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_to_arm.ps1 `
  -RepoPath C:\work\code\cinderx4 `
  -UpstreamRemote localorigin `
  -UpstreamBranch bench-cur-7c361dce `
  -WorkBranch codex/phase15-producer-verify `
  -ArmHost 124.70.162.35 `
  -RemoteDriverVenv /root/venv-cinderx314-pilot `
  -SkipPyperformance `
  -SkipArmRuntimeValidation `
  -ExtraVerifyCmd "OUT_DIR=/root/work/arm-sync/interp_superinstruction_pilot bash scripts/arm/interp_superinstruction_pilot.sh && python - <<'PY'\nimport json\nfrom pathlib import Path\nroot = Path('/root/work/arm-sync/interp_superinstruction_pilot')\nfor path in sorted(root.glob('*.cinderx.cinder.json')):\n    data = json.loads(path.read_text(encoding='utf-8'))\n    print(path.name, data['producer'], data['emitted_superinstructions'])\nPY"
```

Expected:

- unified entrypoint succeeds end-to-end
- for at least one `*.cinderx.cinder.json` artifact:
  - `producer == "cinder"`
  - `emitted_superinstructions` contains one of:
    - `LOAD_FAST__LOAD_FAST`
    - `STORE_FAST__LOAD_FAST`
    - `LOAD_CONST__LOAD_FAST`

- [ ] **Step 4: Record the producer evidence in `findings.md`**

Replace the temporary pending note with:

```markdown
- 2026-04-12 phase1.5: superinstruction producer closure
  - runtime family closed in this phase:
    - `3.14`
  - producer mode:
    - `cinder`
  - emitted evidence:
    - `load_fast_pair_loop.cinderx.cinder.json -> emitted_superinstructions contains LOAD_FAST__LOAD_FAST`
    - `store_fast_load_fast_loop.cinderx.cinder.json -> emitted_superinstructions contains STORE_FAST__LOAD_FAST`
    - `load_const_load_fast_loop.cinderx.cinder.json -> emitted_superinstructions contains LOAD_CONST__LOAD_FAST`
  - acceptance:
    - at least one Phase 1 pilot workload emitted a new double-underscore superinstruction
  - `3.15` remains:
    - static wiring + contract only in this phase
```

- [ ] **Step 5: Commit**

```bash
git add findings.md
git commit -m "docs: record phase15 producer verification evidence"
```
