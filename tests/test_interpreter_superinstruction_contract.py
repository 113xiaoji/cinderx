import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SUPERINSTRUCTIONS = (
    "LOAD_FAST__LOAD_FAST",
    "STORE_FAST__LOAD_FAST",
    "LOAD_CONST__LOAD_FAST",
)
VERSION_FILES = {
    "3.14": {
        "bytecodes": "cinder-bytecodes.c",
        "generated_cases": "Includes/generated_cases.c.h",
        "opcode_definitions": "opcode.h",
        "opcode_targets": "cinderx_opcode_targets.h",
    },
    "3.15": {
        "bytecodes": "cinder-bytecodes.c",
        "generated_cases": "Includes/generated_cases.c.h",
        "opcode_definitions": "cinder_opcode.h",
        "opcode_targets": "cinderx_opcode_targets.h",
    },
}


def _interpreter_file(version: str, relative_path: str) -> Path:
    return REPO_ROOT / "cinderx" / "Interpreter" / version / relative_path


def _read(version: str, key: str) -> str:
    return _interpreter_file(version, VERSION_FILES[version][key]).read_text(
        encoding="utf-8"
    )


def _opcode_numbers(version: str) -> dict[str, int]:
    definitions = _read(version, "opcode_definitions")
    result: dict[str, int] = {}
    for name in SUPERINSTRUCTIONS:
        match = re.search(rf"^#define\s+{re.escape(name)}\s+(\d+)\b", definitions, re.M)
        assert match is not None, f"{version} is missing opcode definition for {name}"
        result[name] = int(match.group(1))
    return result


def _opcode_target_entries(version: str) -> list[str]:
    targets = _read(version, "opcode_targets")
    match = re.search(
        r"static void \*.*?\[256\] = \{\n(?P<body>.*?)\n\};",
        targets,
        re.S,
    )
    assert match is not None, f"{version} is missing the primary opcode target table"
    return re.findall(r"&&([A-Za-z0-9_]+)", match.group("body"))


def test_bytecode_definitions_exist_for_phase1_superinstructions() -> None:
    for version in VERSION_FILES:
        content = _read(version, "bytecodes")
        for name in SUPERINSTRUCTIONS:
            assert f"super({name})" in content


def test_generated_cases_define_targets_without_preprocessor_guards() -> None:
    for version in VERSION_FILES:
        content = _read(version, "generated_cases")
        for name in SUPERINSTRUCTIONS:
            assert f"TARGET({name})" in content
            assert f"#ifdef {name}" not in content
            assert f"#ifndef {name}" not in content


def test_opcode_definition_layer_contains_phase1_superinstructions() -> None:
    for version in VERSION_FILES:
        opcode_numbers = _opcode_numbers(version)
        assert len(set(opcode_numbers.values())) == len(SUPERINSTRUCTIONS)


def test_opcode_target_headers_align_with_phase1_opcode_numbers() -> None:
    for version in VERSION_FILES:
        targets = _opcode_target_entries(version)
        assert len(targets) == 256
        opcode_numbers = _opcode_numbers(version)
        for name, opcode_number in opcode_numbers.items():
            assert targets[opcode_number] == f"TARGET_{name}"
