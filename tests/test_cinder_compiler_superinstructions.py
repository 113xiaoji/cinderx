from __future__ import annotations

import importlib
import opcode
import re
import sys
import types
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.arm import interp_superinstruction_workloads as workloads


ROOT = Path(__file__).resolve().parents[1]
PYTHONLIB = ROOT / "cinderx" / "PythonLib"
OPCODE_STUBS_HEADER = ROOT / "cinderx" / "Common" / "opcode_stubs.h"
REQUIRED_OPCODE_NAMES = (
    "LOAD_FAST__LOAD_FAST",
    "STORE_FAST__LOAD_FAST",
    "LOAD_CONST__LOAD_FAST",
)
InstructionRecord = tuple[int, str, int]


@dataclass(frozen=True)
class FunctionInstructionCapture:
    before_superinstructions: list[InstructionRecord]
    after_superinstructions: list[InstructionRecord]


class FakeVersionInfo(tuple):
    major = property(lambda self: self[0])
    minor = property(lambda self: self[1])
    micro = property(lambda self: self[2])
    releaselevel = property(lambda self: self[3])
    serial = property(lambda self: self[4])


def normalize_inline_cache_entries(entries: object) -> dict[str, int]:
    if isinstance(entries, dict):
        return {
            str(name): int(value)
            for name, value in entries.items()
        }
    return {
        opcode.opname[index]: int(value)
        for index, value in enumerate(entries)
    }


def get_custom_opcode_names() -> tuple[str, ...]:
    matches: list[str] = []
    current_section: str | None = None
    for line in OPCODE_STUBS_HEADER.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#elif PY_VERSION_HEX < 0x030E0000"):
            current_section = "lt_30e"
            continue
        if stripped == "#else":
            current_section = "else"
            continue
        if stripped == "#endif":
            current_section = None
        if current_section in {"lt_30e", "else"}:
            match = re.search(r"X\(([^)]+)\)", stripped)
            if match:
                matches.append(match.group(1))

    names = [name for name in matches if name not in opcode.opmap]
    return tuple(dict.fromkeys(names))


def test_opcode_stub_header_exposes_double_underscore_superinstructions() -> None:
    names = get_custom_opcode_names()

    for name in REQUIRED_OPCODE_NAMES:
        assert name in names


@contextmanager
def compiler_import_context():
    if str(PYTHONLIB) not in sys.path:
        sys.path.insert(0, str(PYTHONLIB))

    original_version = sys.version_info
    original_inline_cache_entries = opcode._inline_cache_entries
    original_cinderx_opcode = sys.modules.get("cinderx.opcode")

    for name in list(sys.modules):
        if name == "cinderx" or name.startswith("cinderx.compiler"):
            del sys.modules[name]

    sys.version_info = FakeVersionInfo((3, 15, 0, "final", 0))
    opcode._inline_cache_entries = normalize_inline_cache_entries(
        original_inline_cache_entries
    )

    module = types.ModuleType("cinderx.opcode")

    def init(
        opnames: list[str],
        opmap: dict[str, int],
        hasname: list[int],
        hasjrel: list[int],
        hasjabs: list[int],
        hasconst: list[int],
        hasarg: list[int],
        cache_format: dict[object, object],
        specializations: dict[object, object],
        inline_cache_entries: dict[object, object],
    ) -> None:
        used = set(opcode.opmap.values()) | set(opmap.values())
        available = [value for value in range(len(opnames)) if value not in used]
        for name, opcode_value in zip(get_custom_opcode_names(), available, strict=False):
            opmap[name] = opcode_value
            opnames[opcode_value] = name

    module.init = init
    sys.modules["cinderx.opcode"] = module

    try:
        compiler = importlib.import_module("cinderx.compiler")
        pycodegen = importlib.import_module("cinderx.compiler.pycodegen")
        pyassem = importlib.import_module("cinderx.compiler.pyassem")
        yield compiler, pycodegen, pyassem
    finally:
        sys.version_info = original_version
        opcode._inline_cache_entries = original_inline_cache_entries
        if original_cinderx_opcode is None:
            sys.modules.pop("cinderx.opcode", None)
        else:
            sys.modules["cinderx.opcode"] = original_cinderx_opcode


def snapshot_instructions(flow_graph) -> list[InstructionRecord]:
    instructions: list[InstructionRecord] = []
    index = 0
    for block in flow_graph.ordered_blocks:
        for instr in block.insts:
            instructions.append((index, instr.opname, instr.ioparg))
            index += 1
    return instructions


def compile_function_instructions(
    source: str, func_name: str
) -> FunctionInstructionCapture:
    with compiler_import_context() as (compiler, pycodegen, pyassem):
        class RecordingFlowGraph(pyassem.PyFlowGraph314):
            captured: dict[str, FunctionInstructionCapture] = {}

            def push_block(self, worklist, block, depth) -> None:
                if block is None:
                    return
                super().push_block(worklist, block, depth)

            def insert_superinstructions(self) -> None:
                before = snapshot_instructions(self)
                super().insert_superinstructions()
                RecordingFlowGraph.captured[self.name] = FunctionInstructionCapture(
                    before_superinstructions=before,
                    after_superinstructions=snapshot_instructions(self),
                )

        class RecordingGenerator(pycodegen.CinderCodeGenerator314):
            flow_graph = RecordingFlowGraph

        compiler.compile_code(
            source,
            f"<{func_name}>",
            "exec",
            compiler=RecordingGenerator,
            modname=f"pilot::{func_name}",
        )
        return RecordingFlowGraph.captured[func_name]


def find_instruction(
    instructions: list[InstructionRecord], opname: str
) -> InstructionRecord:
    for instruction in instructions:
        if instruction[1] == opname:
            return instruction
    raise AssertionError(f"expected to find {opname!r} in instruction stream")


def test_compiler_opcodes_fall_back_to_runtime_superinstructions() -> None:
    if str(PYTHONLIB) not in sys.path:
        sys.path.insert(0, str(PYTHONLIB))

    original_version = sys.version_info
    original_inline_cache_entries = opcode._inline_cache_entries
    original_cinderx_opcode = sys.modules.get("cinderx.opcode")

    for name in list(sys.modules):
        if name == "cinderx" or name.startswith("cinderx.compiler"):
            del sys.modules[name]

    sys.version_info = FakeVersionInfo((3, 14, 0, "final", 0))
    opcode._inline_cache_entries = normalize_inline_cache_entries(
        original_inline_cache_entries
    )

    module = types.ModuleType("cinderx.opcode")

    def init(
        opnames: list[str],
        opmap: dict[str, int],
        hasname: list[int],
        hasjrel: list[int],
        hasjabs: list[int],
        hasconst: list[int],
        hasarg: list[int],
        cache_format: dict[object, object],
        specializations: dict[object, object],
        inline_cache_entries: dict[object, object],
    ) -> None:
        return None

    module.init = init
    sys.modules["cinderx.opcode"] = module

    try:
        opcodes_module = importlib.import_module("cinderx.compiler.opcodes")
        compiler_opcode = opcodes_module.opcode
        for name in REQUIRED_OPCODE_NAMES:
            assert name in compiler_opcode.opmap
        assert "LOAD_CONST__LOAD_FAST" in compiler_opcode.hasconst
    finally:
        sys.version_info = original_version
        opcode._inline_cache_entries = original_inline_cache_entries
        if original_cinderx_opcode is None:
            sys.modules.pop("cinderx.opcode", None)
        else:
            sys.modules["cinderx.opcode"] = original_cinderx_opcode
        for name in list(sys.modules):
            if name == "cinderx" or name.startswith("cinderx.compiler"):
                del sys.modules[name]


def test_emits_double_underscore_load_fast_pair() -> None:
    spec = workloads.get_workload_spec("load_fast_pair_loop")
    capture = compile_function_instructions(
        spec.source,
        "load_fast_pair_loop",
    )
    names = [name for _, name, _ in capture.after_superinstructions]

    assert "LOAD_FAST__LOAD_FAST" in names
    assert "LOAD_FAST_LOAD_FAST" not in names


def test_emits_double_underscore_store_fast_load_fast_pair() -> None:
    spec = workloads.get_workload_spec("store_fast_load_fast_loop")
    capture = compile_function_instructions(
        spec.source,
        "store_fast_load_fast_loop",
    )
    names = [name for _, name, _ in capture.after_superinstructions]

    assert "STORE_FAST__LOAD_FAST" in names
    assert "STORE_FAST_LOAD_FAST" not in names


def test_emits_load_const_load_fast_pair() -> None:
    spec = workloads.get_workload_spec("load_const_load_fast_loop")
    capture = compile_function_instructions(
        spec.source,
        "load_const_load_fast_loop",
    )
    names = [name for _, name, _ in capture.after_superinstructions]

    assert "LOAD_CONST__LOAD_FAST" in names
    assert not any(
        first == "LOAD_CONST" and second == "LOAD_FAST"
        for first, second in zip(names, names[1:])
    )


@pytest.mark.parametrize(
    ("workload_name", "entry_name", "first_opname", "second_opname", "super_opname"),
    [
        (
            "load_fast_pair_loop",
            "load_fast_pair_loop",
            "LOAD_FAST",
            "LOAD_FAST",
            "LOAD_FAST__LOAD_FAST",
        ),
        (
            "store_fast_load_fast_loop",
            "store_fast_load_fast_loop",
            "STORE_FAST",
            "LOAD_FAST",
            "STORE_FAST__LOAD_FAST",
        ),
        (
            "load_const_load_fast_loop",
            "load_const_load_fast_loop",
            "LOAD_CONST",
            "LOAD_FAST",
            "LOAD_CONST__LOAD_FAST",
        ),
    ],
)
def test_dunder_superinstructions_preserve_split_operands(
    workload_name: str,
    entry_name: str,
    first_opname: str,
    second_opname: str,
    super_opname: str,
) -> None:
    spec = workloads.get_workload_spec(workload_name)
    capture = compile_function_instructions(spec.source, entry_name)

    super_instruction = find_instruction(capture.after_superinstructions, super_opname)
    first_before = capture.before_superinstructions[super_instruction[0]]
    second_before = capture.before_superinstructions[super_instruction[0] + 1]
    nop_instruction = capture.after_superinstructions[super_instruction[0] + 1]

    assert first_before[1] == first_opname
    assert second_before[1] == second_opname
    assert super_instruction[2] == first_before[2]
    assert super_instruction[2] != ((first_before[2] << 4) | second_before[2])
    assert nop_instruction[1] == "NOP"
    assert nop_instruction[2] == second_before[2]
