from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_bench(runtime: str) -> dict[str, object]:
    script = Path("scripts/arm/bench_compare_modes.py")
    result = subprocess.run(
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
        check=True,
    )
    return json.loads(result.stdout)


def test_cpython_interp_named_workload_is_reported_in_json() -> None:
    payload = run_bench("cpython")

    assert payload["workload"] == "load_fast_pair_loop"
    assert payload["runtime"] == "cpython"
    assert payload["mode"] == "interp"


def test_cinderx_interp_named_workload_is_reported_in_json() -> None:
    payload = run_bench("cinderx")

    assert payload["workload"] == "load_fast_pair_loop"
    assert payload["runtime"] == "cinderx"
    assert payload["mode"] == "interp"
