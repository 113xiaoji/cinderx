#!/usr/bin/env python3
"""Verify the narrow send(None) coroutine-loop rewrite for issue #65."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import cinderjit
import cinderx
import cinderx.jit as jit

def load_benchmark_function():
    import pyperformance

    root = Path(pyperformance.__file__).resolve().parent
    path = root / "data-files" / "benchmarks" / "bm_coroutines" / "run_benchmark.py"
    spec = importlib.util.spec_from_file_location("bm_coroutines_run_benchmark", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load benchmark module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return path, module.bench_coroutines


def main() -> int:
    cinderx.init()
    jit.enable()
    jit.enable_specialized_opcodes()
    jit.compile_after_n_calls(1_000_000)

    benchmark_path, bench_coroutines = load_benchmark_function()

    for _ in range(3):
        bench_coroutines(1)

    forced = bool(jit.force_compile(bench_coroutines))
    if not forced:
        raise SystemExit("force_compile(bench_coroutines) returned False")

    counts = cinderjit.get_function_hir_opcode_counts(bench_coroutines) or {}

    jit.get_and_clear_runtime_stats()
    bench_coroutines(8)
    stats = jit.get_and_clear_runtime_stats()

    relevant = [
        entry
        for entry in stats.get("deopt", [])
        if entry["normal"]["func_qualname"] == "bench_coroutines"
    ]
    callmethod_unhandled = sum(
        int(entry["int"]["count"])
        for entry in relevant
        if entry["normal"]["reason"] == "UnhandledException"
        and entry["normal"]["description"] == "CallMethod"
    )

    payload = {
        "benchmark_path": str(benchmark_path),
        "forced": forced,
        "send_count": int(counts.get("Send", 0)),
        "callmethod_count": int(counts.get("CallMethod", 0)),
        "getsecondoutput_count": int(counts.get("GetSecondOutput", 0)),
        "condbranch_count": int(counts.get("CondBranch", 0)),
        "callmethod_unhandled_deopt_count": callmethod_unhandled,
        "deopt_count": len(relevant),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
