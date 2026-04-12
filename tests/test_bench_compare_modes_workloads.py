from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_cpython_interp_named_workload_is_reported_in_json() -> None:
    script = Path("scripts/arm/bench_compare_modes.py")
    env = os.environ.copy()
    env["PYTHONPATH"] = "."

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--runtime",
            "cpython",
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
        env=env,
    )

    payload = json.loads(result.stdout)
    assert payload["workload"] == "load_fast_pair_loop"
    assert payload["runtime"] == "cpython"
    assert payload["mode"] == "interp"
