#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from pathlib import Path


def infer_benchmark_name(
    bench: dict[str, object],
    index: int,
    benchmark_filter: list[str],
) -> str:
    metadata = bench.get("metadata", {})
    if isinstance(metadata, dict):
        name = metadata.get("name")
        if isinstance(name, str) and name:
            return name

    name = bench.get("name")
    if isinstance(name, str) and name:
        return name

    if len(benchmark_filter) == 1:
        return benchmark_filter[0]
    if index < len(benchmark_filter):
        return benchmark_filter[index]
    if benchmark_filter:
        return f"{benchmark_filter[0]}#{index + 1}"
    return f"benchmark_{index + 1}"


def resolve_git_commit(workdir: Path, explicit_commit: str) -> str:
    if explicit_commit:
        return explicit_commit
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workdir,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return ""
    return proc.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tmpdir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--benchmarks", required=True)
    parser.add_argument("--samples", type=int, required=True)
    parser.add_argument("--autojit", type=int, required=True)
    parser.add_argument("--run-label", default="")
    parser.add_argument("--baseline-ref", default="")
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--specialized-opcodes", default="")
    parser.add_argument("--jitlist-entries", default="")
    parser.add_argument("--git-commit", default="")
    args = parser.parse_args()

    tmpdir = Path(args.tmpdir)
    output = Path(args.output)
    benchmark_filter = [name for name in args.benchmarks.split(",") if name]
    workdir = Path(args.workdir)

    rows: dict[str, list[float]] = {}
    for path in sorted(tmpdir.glob("run_*.json")):
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        for index, bench in enumerate(data.get("benchmarks", [])):
            name = infer_benchmark_name(bench, index, benchmark_filter)
            runs = bench.get("runs", [])
            if not runs:
                continue
            values = runs[0].get("values", [])
            if not values:
                continue
            rows.setdefault(name, []).append(float(values[0]))

    summary = {
        "benchmarks": [],
        "benchmark_filter": benchmark_filter,
        "samples": args.samples,
        "autojit": args.autojit,
        "run_label": args.run_label,
        "baseline_ref": args.baseline_ref,
        "workdir": str(workdir),
        "git_commit": resolve_git_commit(workdir, args.git_commit),
        "specialized_opcodes": args.specialized_opcodes,
        "jitlist_entries": args.jitlist_entries,
    }

    for name in sorted(rows):
        vals = rows[name]
        summary["benchmarks"].append(
            {
                "name": name,
                "samples": vals,
                "median": statistics.median(vals),
                "min": min(vals),
                "max": max(vals),
            }
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
