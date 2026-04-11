#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_summary(path: Path) -> dict[str, float]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data


def ensure_matching_shape(
    base_data: dict[str, object],
    current_data: dict[str, object],
) -> None:
    for key in ("benchmark_filter", "samples", "autojit"):
        base_val = base_data.get(key)
        current_val = current_data.get(key)
        if base_val != current_val:
            raise SystemExit(
                f"mismatched {key}: base={base_val!r} current={current_val!r}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--current", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--warn-threshold-pct", type=float, default=5.0)
    args = parser.parse_args()

    base_data = load_summary(Path(args.base))
    current_data = load_summary(Path(args.current))
    ensure_matching_shape(base_data, current_data)
    base = {
        row["name"]: float(row["median"])
        for row in base_data.get("benchmarks", [])
    }
    current = {
        row["name"]: float(row["median"])
        for row in current_data.get("benchmarks", [])
    }
    names = sorted(set(base) | set(current))

    rows = []
    regressions = []
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
                }
            )
            continue
        delta_pct = ((current_val / base_val) - 1.0) * 100.0
        row = {
            "name": name,
            "base_median": base_val,
            "current_median": current_val,
            "delta_pct": delta_pct,
        }
        rows.append(row)
        if delta_pct >= args.warn_threshold_pct:
            regressions.append(row)

    payload = {
        "rows": rows,
        "warn_threshold_pct": args.warn_threshold_pct,
        "regressions": regressions,
        "base_metadata": {
            "run_label": base_data.get("run_label", ""),
            "baseline_ref": base_data.get("baseline_ref", ""),
            "git_commit": base_data.get("git_commit", ""),
        },
        "current_metadata": {
            "run_label": current_data.get("run_label", ""),
            "baseline_ref": current_data.get("baseline_ref", ""),
            "git_commit": current_data.get("git_commit", ""),
        },
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
