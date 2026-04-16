#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from bench_pyperf_direct import load_recipe
except ImportError:
    sibling = Path(__file__).with_name("bench_pyperf_direct.py")
    spec = importlib.util.spec_from_file_location("bench_pyperf_direct", sibling)
    if spec is None or spec.loader is None:
        raise
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    load_recipe = module.load_recipe


def bool_flag(enabled: bool, flag: str) -> list[str]:
    return [flag] if enabled else []


def build_plain_args(recipe: dict[str, object], samples: int, output: Path) -> list[str]:
    args = [
        sys.executable,
        str(Path(__file__).with_name("bench_pyperf_direct.py")),
        "--samples",
        str(samples),
        "--output",
        str(output),
    ]
    benchmark_name = str(recipe.get("benchmark_name", "") or "")
    module_path = str(recipe.get("module_path", "") or "")
    module_name = str(recipe.get("module_name", "") or "")
    bench_func = str(recipe.get("bench_func", "") or "")
    bench_args = recipe.get("bench_args", [])
    prewarm_runs = int(recipe.get("prewarm_runs", 0) or 0)
    specialized_opcodes = bool(recipe.get("specialized_opcodes", False))
    stub_pyperf = bool(recipe.get("stub_pyperf", False))

    if benchmark_name:
        args.extend(["--benchmark-name", benchmark_name])
    elif module_path:
        args.extend(["--module-path", module_path])
    else:
        raise ValueError("recipe must provide benchmark_name or module_path")

    if module_name:
        args.extend(["--module-name", module_name])
    if not bench_func:
        raise ValueError("recipe must provide bench_func")
    args.extend(["--bench-func", bench_func])
    args.extend(["--bench-args-json", json.dumps(bench_args)])
    if prewarm_runs:
        args.extend(["--prewarm-runs", str(prewarm_runs)])
    args.extend(bool_flag(stub_pyperf, "--stub-pyperf"))
    args.extend(bool_flag(specialized_opcodes, "--specialized-opcodes"))
    return args


def build_recipe_args(recipe_path: Path, samples: int, output: Path) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).with_name("bench_pyperf_direct.py")),
        "--recipe-json",
        str(recipe_path),
        "--samples",
        str(samples),
        "--output",
        str(output),
    ]


def load_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_compare_payload(
    recipe_path: Path,
    plain_data: dict[str, object],
    recipe_data: dict[str, object],
) -> dict[str, object]:
    plain_median = float(plain_data["median_wall_sec"])
    recipe_median = float(recipe_data["median_wall_sec"])
    delta_pct = ((recipe_median / plain_median) - 1.0) * 100.0
    return {
        "recipe_name": str(recipe_data.get("recipe_name", "")),
        "recipe_path": str(recipe_path.resolve()),
        "benchmark_name": str(
            recipe_data.get("benchmark_name") or plain_data.get("benchmark_name") or ""
        ),
        "bench_func": str(recipe_data.get("bench_func") or plain_data.get("bench_func") or ""),
        "samples": int(recipe_data.get("samples") and len(recipe_data["samples"]) or 0),
        "plain_median_wall_sec": plain_median,
        "recipe_median_wall_sec": recipe_median,
        "delta_pct": delta_pct,
        "plain": plain_data,
        "recipe": recipe_data,
    }


def run_command(args: list[str]) -> None:
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(args)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe-json", required=True)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    recipe_path = Path(args.recipe_json)
    recipe = load_recipe(recipe_path)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        plain_output = tmpdir / "plain.json"
        recipe_output = tmpdir / "recipe.json"

        run_command(build_plain_args(recipe, args.samples, plain_output))
        run_command(build_recipe_args(recipe_path, args.samples, recipe_output))

        payload = build_compare_payload(
            recipe_path, load_payload(plain_output), load_payload(recipe_output)
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
