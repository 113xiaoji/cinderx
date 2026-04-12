from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_bench(runtime: str) -> subprocess.CompletedProcess[str]:
    script = Path("scripts/arm/bench_compare_modes.py")
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--runtime",
            runtime,
            "--mode",
            "interp",
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


def test_cpython_interp_named_workload_is_reported_in_json() -> None:
    result = run_bench("cpython")
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout)

    assert payload["workload"] == "load_fast_pair_loop"
    assert payload["runtime"] == "cpython"
    assert payload["mode"] == "interp"


def test_cinderx_interp_named_workload_requires_real_driver_env() -> None:
    result = run_bench("cinderx")

    assert result.returncode != 0
    assert "ModuleNotFoundError" in result.stderr
    assert "import cinderx.jit as jit" in result.stderr


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
