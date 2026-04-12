from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SUPERINSTRUCTIONS = (
    "LOAD_FAST__LOAD_FAST",
    "STORE_FAST__LOAD_FAST",
    "LOAD_CONST__LOAD_FAST",
)
VERSIONS = ("3.14", "3.15")


def _interpreter_file(version: str, relative_path: str) -> Path:
    return REPO_ROOT / "cinderx" / "Interpreter" / version / relative_path


def test_bytecode_definitions_exist_for_phase1_superinstructions() -> None:
    for version in VERSIONS:
        content = _interpreter_file(version, "cinder-bytecodes.c").read_text(
            encoding="utf-8"
        )
        for name in SUPERINSTRUCTIONS:
            assert f"super({name})" in content


def test_generated_cases_define_targets_for_phase1_superinstructions() -> None:
    for version in VERSIONS:
        content = _interpreter_file(
            version, "Includes/generated_cases.c.h"
        ).read_text(encoding="utf-8")
        for name in SUPERINSTRUCTIONS:
            assert f"TARGET({name})" in content


def test_opcode_target_headers_reference_phase1_superinstructions() -> None:
    for version in VERSIONS:
        content = _interpreter_file(version, "cinderx_opcode_targets.h").read_text(
            encoding="utf-8"
        )
        for name in SUPERINSTRUCTIONS:
            assert name in content
