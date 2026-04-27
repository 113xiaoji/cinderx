#!/usr/bin/env python3
import json
import statistics
import sys
from pathlib import Path


def _benchmark_name(data, bench, benchmark_filter):
    name = bench.get("metadata", {}).get("name")
    if name:
        return name

    # pyperformance 1.14 debug-single-value stores the benchmark name at the
    # top level instead of duplicating it in each benchmark entry.
    name = data.get("metadata", {}).get("name")
    if name:
        return name

    if len(benchmark_filter) == 1:
        return benchmark_filter[0]

    return None


def _first_value(bench):
    for run in bench.get("runs", []):
        values = run.get("values", [])
        if values:
            return float(values[0])
    return None


def summarize(tmpdir, output, benchmark_filter, samples, autojit):
    rows = {}
    for path in sorted(Path(tmpdir).glob("run_*.json")):
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

        for bench in data.get("benchmarks", []):
            name = _benchmark_name(data, bench, benchmark_filter)
            value = _first_value(bench)
            if name is None or value is None:
                continue
            rows.setdefault(name, []).append(value)

    summary = {
        "benchmarks": [],
        "benchmark_filter": benchmark_filter,
        "samples": samples,
        "autojit": autojit,
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

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main(argv):
    if len(argv) != 6:
        print(
            "usage: summarize_pyperf_subset.py TMPDIR OUTPUT BENCHMARKS SAMPLES AUTOJIT",
            file=sys.stderr,
        )
        return 2

    _, tmpdir, output, benchmarks, samples, autojit = argv
    summarize(
        Path(tmpdir),
        Path(output),
        benchmarks.split(","),
        int(samples),
        int(autojit),
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
