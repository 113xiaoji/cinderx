from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from types import SimpleNamespace
from pathlib import Path

import pytest


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_bench(runtime: str, *extra_args: str) -> subprocess.CompletedProcess[str]:
    script = Path("scripts/arm/bench_compare_modes.py")
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--runtime",
            runtime,
            "--mode",
            "interp",
            *extra_args,
            "--workload",
            "load_fast_pair_loop",
            "--n",
            "3",
            "--warmup",
            "0",
            "--calls",
            "1",
            "--repeats",
            "1",
        ],
        capture_output=True,
        text=True,
    )


def test_bench_compare_modes_exposes_producer_choices() -> None:
    script = _load_module(
        Path("scripts/arm/bench_compare_modes.py"),
        "_bench_compare_modes_producer_parser_test",
    )
    parser = script.build_parser()
    producer_action = next(
        action for action in parser._actions if action.dest == "producer"
    )

    assert producer_action.choices == ("default", "cinder")


def test_cpython_default_output_includes_producer_and_emission_fields() -> None:
    result = run_bench("cpython", "--producer", "default")
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout)

    assert payload["workload"] == "load_fast_pair_loop"
    assert payload["runtime"] == "cpython"
    assert payload["mode"] == "interp"
    assert payload["producer"] == "default"
    assert payload["emitted_superinstructions"] == []


def test_cpython_rejects_cinder_producer() -> None:
    result = run_bench("cpython", "--producer", "cinder")

    assert result.returncode != 0
    assert "cinder producer requires --runtime cinderx" in result.stderr


def test_cinderx_interp_named_workload_requires_real_driver_env() -> None:
    result = run_bench("cinderx", "--producer", "cinder")

    assert result.returncode != 0
    assert "ModuleNotFoundError" in result.stderr
    assert "from cinderx.compiler import CinderCodeGenerator, compile_code" in result.stderr


def test_cinder_producer_json_uses_helper_emission_evidence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _load_module(
        Path("scripts/arm/bench_compare_modes.py"),
        "_bench_compare_modes_cinder_evidence_source_test",
    )

    def fake_load_cinder_workload(workload_name: str):
        assert workload_name == "load_fast_pair_loop"
        return (lambda n: n + 1), ["LOAD_FAST__LOAD_FAST"]

    def fake_cinderx_mode(
        mode: str, fn, workload_name: str, n: int, warmup: int, calls: int, repeats: int
    ):
        assert callable(fn)
        assert mode == "interp"
        assert workload_name == "load_fast_pair_loop"
        assert (n, warmup, calls, repeats) == (3, 0, 1, 1)
        return {"runtime": "cinderx", "mode": mode, "workload": workload_name}

    def fail_collect_emitted_superinstructions(_fn):
        raise AssertionError("cinder producer evidence should come from helper")

    monkeypatch.setattr(script, "load_cinder_workload", fake_load_cinder_workload)
    monkeypatch.setattr(script, "cinderx_mode", fake_cinderx_mode)
    monkeypatch.setattr(
        script,
        "collect_emitted_superinstructions",
        fail_collect_emitted_superinstructions,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bench_compare_modes.py",
            "--runtime",
            "cinderx",
            "--mode",
            "interp",
            "--producer",
            "cinder",
            "--workload",
            "load_fast_pair_loop",
            "--n",
            "3",
            "--warmup",
            "0",
            "--calls",
            "1",
            "--repeats",
            "1",
        ],
    )

    assert script.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["producer"] == "cinder"
    assert payload["emitted_superinstructions"] == ["LOAD_FAST__LOAD_FAST"]


def test_load_cinder_workload_uses_cinder_code_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _load_module(
        Path("scripts/arm/bench_compare_modes.py"),
        "_bench_compare_modes_cinder_generator_test",
    )
    helper = _load_module(
        Path("scripts/arm/interp_superinstruction_workloads.py"),
        "_interp_superinstruction_workloads_generator_test",
    )
    spec = helper.get_workload_spec("load_fast_pair_loop")
    calls: list[object] = []

    class FakeFlowGraph:
        captured: dict[str, list[str]] = {}

        def __init__(self, name: str, filename: str, scope) -> None:
            self.name = name
            self.filename = filename
            self.scope = scope
            self.ordered_blocks = []

        def insert_superinstructions(self) -> None:
            return None

    class FakeCinderCodeGenerator:
        flow_graph = FakeFlowGraph

    def fake_compile_code(
        source: str,
        filename: str,
        mode: str,
        *,
        compiler=None,
        modname: str,
    ):
        assert source == spec.source
        assert filename == f"<{spec.name}>"
        assert mode == "exec"
        assert modname == f"pilot::{spec.name}"
        calls.append(compiler)
        flow_graph = compiler.flow_graph("module", filename, None)
        entry_graph = compiler.flow_graph(spec.entry_name, filename, None)
        entry_graph.ordered_blocks = [
            SimpleNamespace(
                insts=[
                    SimpleNamespace(opname="LOAD_FAST__LOAD_FAST"),
                    SimpleNamespace(opname="RETURN_VALUE"),
                ]
            )
        ]
        compiler.flow_graph.captured[spec.entry_name] = []
        entry_graph.insert_superinstructions()
        return compile(source, filename, mode)

    fake_compiler_module = types.ModuleType("cinderx.compiler")
    fake_compiler_module.CinderCodeGenerator = FakeCinderCodeGenerator
    fake_compiler_module.compile_code = fake_compile_code
    monkeypatch.setitem(sys.modules, "cinderx.compiler", fake_compiler_module)
    monkeypatch.setattr(
        script,
        "collect_emitted_superinstructions",
        lambda _code: (_ for _ in ()).throw(
            AssertionError("producer evidence should come from recording flow graph")
        ),
    )

    _, emitted = script.load_cinder_workload("load_fast_pair_loop")

    assert len(calls) == 1
    assert issubclass(calls[0], FakeCinderCodeGenerator)
    assert emitted == ["LOAD_FAST__LOAD_FAST"]


def _fake_static_opnames(storage_shape: str):
    if storage_shape == "dict":
        return {
            17: "LOAD_FAST__LOAD_FAST",
            18: "STORE_FAST",
        }
    if storage_shape == "list":
        opnames = [f"<{index}>" for index in range(32)]
        opnames[17] = "LOAD_FAST__LOAD_FAST"
        opnames[18] = "STORE_FAST"
        return opnames
    raise AssertionError(f"unsupported static opnames shape in test fixture: {storage_shape}")


@pytest.mark.parametrize("storage_shape", ["dict", "list"])
def test_collect_emitted_superinstructions_uses_cinder_static_opnames(
    monkeypatch: pytest.MonkeyPatch, storage_shape: str
) -> None:
    script = _load_module(
        Path("scripts/arm/bench_compare_modes.py"),
        "_bench_compare_modes_opcode_name_resolution_test",
    )

    fake_instructions = [
        SimpleNamespace(opcode=17, opname="<unknown>"),
        SimpleNamespace(opcode=18, opname="<unknown>"),
    ]

    monkeypatch.setattr(script.dis, "get_instructions", lambda _code: fake_instructions)
    monkeypatch.setattr(
        script,
        "get_cinder_static_opnames",
        lambda: _fake_static_opnames(storage_shape),
        raising=False,
    )

    assert script.collect_emitted_superinstructions(object()) == [
        "LOAD_FAST__LOAD_FAST"
    ]


def test_workload_choices_come_from_registry_and_no_repo_path_is_injected() -> None:
    script_path = Path("scripts/arm/bench_compare_modes.py")
    script_text = script_path.read_text(encoding="utf-8")
    assert "cinderx/PythonLib" not in script_text
    assert "sys.path.insert" not in script_text

    script = _load_module(script_path, "_bench_compare_modes_test")
    helper = _load_module(
        Path("scripts/arm/interp_superinstruction_workloads.py"),
        "_interp_superinstruction_workloads_test",
    )
    expected_choices = ("default",) + tuple(spec.name for spec in helper.WORKLOAD_SPECS)
    parser = script.build_parser()
    workload_action = next(action for action in parser._actions if action.dest == "workload")

    assert workload_action.choices == expected_choices
