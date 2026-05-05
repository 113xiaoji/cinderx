#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def load_summary(path: Path) -> dict[str, float]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {
        row["name"]: float(row["median"])
        for row in data.get("benchmarks", [])
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--current", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--warn-threshold-pct", type=float, default=5.0)
    args = parser.parse_args()

    base = load_summary(Path(args.base))
    current = load_summary(Path(args.current))
    names = sorted(set(base) | set(current))

    rows = []
    regressions = []
    ratios = []
    for name in names:
        base_val = base.get(name)
        current_val = current.get(name)
        if base_val is None or current_val is None:
            rows.append(
                {
                    "name": name,
                    "base_median": base_val,
                    "current_median": current_val,
                    "delta_pct": None,
                    "time_ratio": None,
                    "speedup_pct": None,
                }
            )
            continue
        delta_pct = ((current_val / base_val) - 1.0) * 100.0
        time_ratio = current_val / base_val
        speedup_pct = (1.0 - time_ratio) * 100.0
        row = {
            "name": name,
            "base_median": base_val,
            "current_median": current_val,
            "delta_pct": delta_pct,
            "time_ratio": time_ratio,
            "speedup_pct": speedup_pct,
        }
        rows.append(row)
        if base_val > 0.0 and current_val > 0.0:
            ratios.append(time_ratio)
        if delta_pct >= args.warn_threshold_pct:
            regressions.append(row)

    geomean_time_ratio = None
    geomean_speedup_pct = None
    if ratios:
        geomean_time_ratio = math.exp(
            sum(math.log(ratio) for ratio in ratios) / len(ratios)
        )
        geomean_speedup_pct = (1.0 - geomean_time_ratio) * 100.0

    payload = {
        "rows": rows,
        "warn_threshold_pct": args.warn_threshold_pct,
        "regressions": regressions,
        "geomean_time_ratio": geomean_time_ratio,
        "geomean_speedup_pct": geomean_speedup_pct,
        "geomean_benchmark_count": len(ratios),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
