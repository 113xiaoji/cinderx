from __future__ import annotations

import importlib
import opcode
import re
import sys
import types
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHONLIB = ROOT / "cinderx" / "PythonLib"
OPCODE_STUBS_HEADER = ROOT / "cinderx" / "Common" / "opcode_stubs.h"
REQUIRED_OPCODE_NAMES = (
    "LOAD_FAST__LOAD_FAST",
    "STORE_FAST__LOAD_FAST",
    "LOAD_CONST__LOAD_FAST",
)


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


def compile_function_instructions(source: str, func_name: str) -> list[tuple[int, str]]:
    with compiler_import_context() as (compiler, pycodegen, pyassem):
        class RecordingFlowGraph(pyassem.PyFlowGraph315):
            captured: dict[str, list[tuple[int, str]]] = {}

            def insert_superinstructions(self) -> None:
                super().insert_superinstructions()
                RecordingFlowGraph.captured[self.name] = [
                    (index, instr.opname)
                    for block in self.ordered_blocks
                    for index, instr in enumerate(block.insts)
                ]

        class RecordingGenerator(pycodegen.CinderCodeGenerator315):
            flow_graph = RecordingFlowGraph

        compiler.compile_code(source, f"<{func_name}>", "exec", compiler=RecordingGenerator)
        return RecordingFlowGraph.captured[func_name]


def test_emits_double_underscore_load_fast_pair() -> None:
    instructions = compile_function_instructions(
        """
def load_fast_pair_loop(n):
    total = 0
    for i in range(n):
        left = i
        right = i + 1
        total += left + right
    return total
""",
        "load_fast_pair_loop",
    )
    names = [name for _, name in instructions]

    assert "LOAD_FAST__LOAD_FAST" in names
    assert "LOAD_FAST_LOAD_FAST" not in names


def test_emits_double_underscore_store_fast_load_fast_pair() -> None:
    instructions = compile_function_instructions(
        """
def store_fast_load_fast_loop(n):
    total = 0
    current = 0
    for i in range(n):
        current = i; other = current
        total += other
    return total
""",
        "store_fast_load_fast_loop",
    )
    names = [name for _, name in instructions]

    assert "STORE_FAST__LOAD_FAST" in names
    assert "STORE_FAST_LOAD_FAST" not in names


def test_emits_load_const_load_fast_pair() -> None:
    instructions = compile_function_instructions(
        """
def load_const_load_fast_loop(n):
    total = 0
    for i in range(n):
        total += 257 * i
    return total
""",
        "load_const_load_fast_loop",
    )
    names = [name for _, name in instructions]
    fused_indices = [
        index for index, name in enumerate(names) if name == "LOAD_CONST__LOAD_FAST"
    ]

    assert names.count("LOAD_CONST__LOAD_FAST") == 1
    assert not any(
        first == "LOAD_CONST" and second == "LOAD_FAST"
        for first, second in zip(names, names[1:])
    )
    assert len(fused_indices) == 1
    fused_index = fused_indices[0]
    assert names[fused_index - 2 : fused_index + 5] == [
        "STORE_FAST",
        "LOAD_FAST",
        "LOAD_CONST__LOAD_FAST",
        "NOP",
        "BINARY_OP",
        "BINARY_OP",
        "STORE_FAST",
    ]
