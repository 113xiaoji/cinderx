#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    pass


class Contract:
    def __init__(
        self,
        *,
        root: Path,
        contract_path: Path,
        contract_id: str,
        runner: str,
        samples: int,
        autojit: int,
        expected_case_count: int,
        selectors: list[str],
        resolved_cases: list[str],
        suite_id: str,
        suite_manifest_sha256: str,
    ) -> None:
        self.root = root
        self.contract_path = contract_path
        self.contract_id = contract_id
        self.runner = runner
        self.samples = samples
        self.autojit = autojit
        self.expected_case_count = expected_case_count
        self.selectors = selectors
        self.resolved_cases = resolved_cases
        self.suite_id = suite_id
        self.suite_manifest_sha256 = suite_manifest_sha256


def canonical_json_sha256(payload: Any) -> str:
    data = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ContractError(f"{key} must be a non-empty string")
    return value


def require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ContractError(f"{key} must be an integer")
    return value


def require_str_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ContractError(f"{key} must be a non-empty string list")
    if len(set(value)) != len(value):
        raise ContractError(f"{key} must not contain duplicates")
    return list(value)


def repo_root_for_contract(contract_path: Path) -> Path:
    resolved = contract_path.resolve()
    if resolved.parent.name == "benchmark-contract":
        return resolved.parent.parent
    return resolved.parent


def resolve_contract_path(root: Path, path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return root / path


def load_contract(contract_path: Path | str) -> Contract:
    contract_path = Path(contract_path).resolve()
    root = repo_root_for_contract(contract_path)
    raw = read_json(contract_path)
    if not isinstance(raw, dict):
        raise ContractError("contract must be a JSON object")

    contract_id = require_str(raw, "contract_id")
    schema_version = require_int(raw, "schema_version")
    if schema_version != 1:
        raise ContractError(f"unsupported schema_version: {schema_version}")
    runner = require_str(raw, "runner")
    if runner != "pyperformance":
        raise ContractError(f"unsupported runner: {runner}")
    samples = require_int(raw, "samples")
    autojit = require_int(raw, "autojit")
    expected_case_count = require_int(raw, "expected_case_count")
    if samples <= 0:
        raise ContractError("samples must be positive")
    if autojit < 0:
        raise ContractError("autojit must be non-negative")
    if expected_case_count <= 0:
        raise ContractError("expected_case_count must be positive")

    suite_path = resolve_contract_path(root, require_str(raw, "suite_manifest"))
    lock_path = resolve_contract_path(root, require_str(raw, "suite_lock"))
    suite = read_json(suite_path)
    lock = read_json(lock_path)
    if not isinstance(suite, dict) or not isinstance(lock, dict):
        raise ContractError("suite manifest and lock must be JSON objects")

    suite_id = require_str(suite, "suite_id")
    if require_str(suite, "runner") != runner:
        raise ContractError("suite runner must match contract runner")
    selection = suite.get("selection")
    if not isinstance(selection, dict):
        raise ContractError("suite selection must be a JSON object")
    mode = require_str(selection, "mode")
    if mode != "pyperformance_filter":
        raise ContractError(f"unsupported suite selection mode: {mode}")
    selectors = require_str_list(selection, "selectors")

    if require_str(lock, "suite_id") != suite_id:
        raise ContractError("suite lock suite_id must match manifest")
    if require_str(lock, "runner") != runner:
        raise ContractError("suite lock runner must match contract runner")
    digest = canonical_json_sha256(suite)
    if require_str(lock, "manifest_sha256") != digest:
        raise ContractError("suite lock manifest_sha256 does not match manifest")
    resolved_cases = require_str_list(lock, "resolved_cases")
    lock_count = require_int(lock, "case_count")
    if lock_count != len(resolved_cases):
        raise ContractError("suite lock resolved case count does not match case_count")
    if expected_case_count != len(resolved_cases):
        raise ContractError("contract expected_case_count does not match suite lock")

    return Contract(
        root=root,
        contract_path=contract_path,
        contract_id=contract_id,
        runner=runner,
        samples=samples,
        autojit=autojit,
        expected_case_count=expected_case_count,
        selectors=selectors,
        resolved_cases=resolved_cases,
        suite_id=suite_id,
        suite_manifest_sha256=digest,
    )


def rows_by_name(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = summary.get("benchmarks")
    if not isinstance(rows, list):
        raise ContractError("summary benchmarks must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ContractError("summary benchmark row must be an object")
        name = row.get("name")
        if not isinstance(name, str) or not name:
            raise ContractError("summary benchmark name must be a non-empty string")
        if name in result:
            raise ContractError(f"duplicate benchmark row: {name}")
        result[name] = row
    return result


def validate_summary(contract: Contract, summary: dict[str, Any]) -> None:
    for key in ("contract_id", "suite_id", "suite_manifest_sha256"):
        if key not in summary:
            raise ContractError(f"summary missing required metadata: {key}")
    if summary.get("contract_id") != contract.contract_id:
        raise ContractError("summary contract_id does not match contract")
    if summary.get("suite_id") != contract.suite_id:
        raise ContractError("summary suite_id does not match contract")
    if summary.get("suite_manifest_sha256") != contract.suite_manifest_sha256:
        raise ContractError("summary suite_manifest_sha256 does not match contract")
    if summary.get("benchmark_filter") != contract.selectors:
        raise ContractError("summary benchmark_filter does not match contract selectors")
    if summary.get("samples") != contract.samples:
        raise ContractError("summary samples does not match contract")
    if summary.get("autojit") != contract.autojit:
        raise ContractError("summary autojit does not match contract")

    rows = rows_by_name(summary)
    expected = set(contract.resolved_cases)
    actual = set(rows)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ContractError(
            f"summary benchmark cases mismatch: missing={missing} extra={extra}"
        )

    for name in contract.resolved_cases:
        row = rows[name]
        samples = row.get("samples")
        if (
            not isinstance(samples, list)
            or len(samples) != contract.samples
            or any(not isinstance(value, (int, float)) for value in samples)
        ):
            raise ContractError(f"{name} sample count does not match contract")
        median = row.get("median")
        if not isinstance(median, (int, float)):
            raise ContractError(f"{name} median must be numeric")
        actual_median = statistics.median(float(value) for value in samples)
        if not math.isclose(float(median), actual_median, rel_tol=1e-12, abs_tol=1e-18):
            raise ContractError(f"{name} median does not match samples")


def stamp_summary(
    contract: Contract,
    summary: dict[str, Any],
    *,
    variant: str,
    workdir: str,
) -> dict[str, Any]:
    stamped = dict(summary)
    stamped["contract_id"] = contract.contract_id
    stamped["suite_id"] = contract.suite_id
    stamped["suite_manifest_sha256"] = contract.suite_manifest_sha256
    stamped["resolved_case_count"] = len(contract.resolved_cases)
    stamped["resolved_cases"] = list(contract.resolved_cases)
    stamped["variant"] = variant
    stamped["workdir"] = workdir
    validate_summary(contract, stamped)
    return stamped


def median_by_name(summary: dict[str, Any]) -> dict[str, float]:
    return {
        name: float(row["median"])
        for name, row in rows_by_name(summary).items()
    }


def samples_by_name(summary: dict[str, Any]) -> dict[str, list[float]]:
    return {
        name: [float(value) for value in row["samples"]]
        for name, row in rows_by_name(summary).items()
    }


def percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        raise ContractError("cannot compute percentile of empty values")
    idx = int(pct * (len(sorted_values) - 1))
    return sorted_values[idx]


def compare_summaries(
    contract: Contract,
    base: dict[str, Any],
    candidate: dict[str, Any],
    *,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    validate_summary(contract, base)
    validate_summary(contract, candidate)
    base_medians = median_by_name(base)
    candidate_medians = median_by_name(candidate)

    rows = []
    log_ratios = []
    wins = 0
    losses = 0
    for name in contract.resolved_cases:
        base_value = base_medians[name]
        candidate_value = candidate_medians[name]
        if base_value <= 0 or candidate_value <= 0:
            raise ContractError(f"{name} median must be positive")
        delta_pct = ((candidate_value / base_value) - 1.0) * 100.0
        log_ratios.append(math.log(candidate_value / base_value))
        if delta_pct < 0:
            wins += 1
        elif delta_pct > 0:
            losses += 1
        rows.append(
            {
                "name": name,
                "delta_pct": delta_pct,
                "base_median": base_value,
                "candidate_median": candidate_value,
            }
        )

    geomean_pct = (math.exp(sum(log_ratios) / len(log_ratios)) - 1.0) * 100.0

    rng = random.Random(seed)
    base_samples = samples_by_name(base)
    candidate_samples = samples_by_name(candidate)
    boot = []
    for _ in range(bootstrap_samples):
        sample_logs = []
        for name in contract.resolved_cases:
            bvals = base_samples[name]
            cvals = candidate_samples[name]
            bmedian = statistics.median(rng.choice(bvals) for _ in bvals)
            cmedian = statistics.median(rng.choice(cvals) for _ in cvals)
            if bmedian <= 0 or cmedian <= 0:
                raise ContractError(f"{name} bootstrap median must be positive")
            sample_logs.append(math.log(cmedian / bmedian))
        boot.append((math.exp(sum(sample_logs) / len(sample_logs)) - 1.0) * 100.0)
    boot.sort()
    ci = [percentile(boot, 0.025), percentile(boot, 0.975)]
    if geomean_pct < 0 and ci[1] < 0:
        conclusion = "real_gain"
    elif geomean_pct > 0 and ci[0] > 0:
        conclusion = "real_regression"
    else:
        conclusion = "noise"

    return {
        "contract_id": contract.contract_id,
        "suite_id": contract.suite_id,
        "suite_manifest_sha256": contract.suite_manifest_sha256,
        "case_count": len(contract.resolved_cases),
        "samples": contract.samples,
        "autojit": contract.autojit,
        "geomean_pct": geomean_pct,
        "geomean_bootstrap_95ci_pct": ci,
        "wins": wins,
        "losses": losses,
        "conclusion": conclusion,
        "rows": sorted(rows, key=lambda row: row["delta_pct"]),
    }


def report_metadata(report: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "contract_id",
        "suite_id",
        "suite_manifest_sha256",
        "case_count",
        "samples",
        "autojit",
    )
    result: dict[str, Any] = {}
    for key in keys:
        if key not in report:
            raise ContractError(f"report missing required metadata: {key}")
        result[key] = report[key]
    return result


def compare_reports(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    max_geomean_diff_pct: float,
) -> dict[str, Any]:
    left_meta = report_metadata(left)
    right_meta = report_metadata(right)
    if left_meta != right_meta:
        raise ContractError(
            f"report metadata mismatch: left={left_meta} right={right_meta}"
        )

    left_conclusion = left.get("conclusion")
    right_conclusion = right.get("conclusion")
    if not isinstance(left_conclusion, str) or not isinstance(right_conclusion, str):
        raise ContractError("report conclusion must be a string")
    left_geo = left.get("geomean_pct")
    right_geo = right.get("geomean_pct")
    if not isinstance(left_geo, (int, float)) or not isinstance(right_geo, (int, float)):
        raise ContractError("report geomean_pct must be numeric")
    geomean_diff = abs(float(right_geo) - float(left_geo))

    if left_conclusion != right_conclusion:
        consistent = False
        reason = "different_conclusion"
    elif geomean_diff > max_geomean_diff_pct:
        consistent = False
        reason = "geomean_diff_exceeds_threshold"
    else:
        consistent = True
        reason = "same_contract_same_conclusion"

    return {
        "consistent": consistent,
        "reason": reason,
        "max_geomean_diff_pct": max_geomean_diff_pct,
        "geomean_diff_pct": geomean_diff,
        "left": {
            "geomean_pct": float(left_geo),
            "ci": left.get("geomean_bootstrap_95ci_pct"),
            "conclusion": left_conclusion,
        },
        "right": {
            "geomean_pct": float(right_geo),
            "ci": right.get("geomean_bootstrap_95ci_pct"),
            "conclusion": right_conclusion,
        },
        "metadata": left_meta,
    }


def load_summary(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ContractError("summary must be a JSON object")
    return payload


def cmd_validate_suite(args: argparse.Namespace) -> int:
    contract = load_contract(args.contract)
    payload = {
        "ok": True,
        "contract_id": contract.contract_id,
        "suite_id": contract.suite_id,
        "suite_manifest_sha256": contract.suite_manifest_sha256,
        "selectors": contract.selectors,
        "resolved_cases": contract.resolved_cases,
        "case_count": len(contract.resolved_cases),
        "samples": contract.samples,
        "autojit": contract.autojit,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_emit_benchmarks(args: argparse.Namespace) -> int:
    contract = load_contract(args.contract)
    values = contract.resolved_cases if args.resolved else contract.selectors
    print(",".join(values))
    return 0


def cmd_emit_field(args: argparse.Namespace) -> int:
    contract = load_contract(args.contract)
    fields = {
        "contract_id": contract.contract_id,
        "suite_id": contract.suite_id,
        "suite_manifest_sha256": contract.suite_manifest_sha256,
        "samples": str(contract.samples),
        "autojit": str(contract.autojit),
        "case_count": str(len(contract.resolved_cases)),
    }
    try:
        print(fields[args.field])
    except KeyError:
        raise ContractError(f"unsupported field: {args.field}") from None
    return 0


def cmd_stamp_summary(args: argparse.Namespace) -> int:
    contract = load_contract(args.contract)
    summary = load_summary(Path(args.summary))
    stamped = stamp_summary(
        contract,
        summary,
        variant=args.variant,
        workdir=args.workdir,
    )
    write_json(Path(args.output), stamped)
    print(args.output)
    return 0


def cmd_validate_summary(args: argparse.Namespace) -> int:
    contract = load_contract(args.contract)
    summary = load_summary(Path(args.summary))
    validate_summary(contract, summary)
    print(json.dumps({"ok": True, "summary": args.summary}, indent=2))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    contract = load_contract(args.contract)
    base = load_summary(Path(args.base))
    candidate = load_summary(Path(args.candidate))
    report = compare_summaries(
        contract,
        base,
        candidate,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    write_json(Path(args.output), report)
    print(args.output)
    return 0


def cmd_compare_reports(args: argparse.Namespace) -> int:
    left = load_summary(Path(args.left))
    right = load_summary(Path(args.right))
    report = compare_reports(
        left,
        right,
        max_geomean_diff_pct=args.max_geomean_diff_pct,
    )
    write_json(Path(args.output), report)
    print(args.output)
    return 0 if report["consistent"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    validate_suite = sub.add_parser("validate-suite")
    validate_suite.add_argument("--contract", required=True)
    validate_suite.set_defaults(func=cmd_validate_suite)

    emit = sub.add_parser("emit-benchmarks")
    emit.add_argument("--contract", required=True)
    emit.add_argument("--resolved", action="store_true")
    emit.set_defaults(func=cmd_emit_benchmarks)

    field = sub.add_parser("emit-field")
    field.add_argument("--contract", required=True)
    field.add_argument("--field", required=True)
    field.set_defaults(func=cmd_emit_field)

    stamp = sub.add_parser("stamp-summary")
    stamp.add_argument("--contract", required=True)
    stamp.add_argument("--summary", required=True)
    stamp.add_argument("--output", required=True)
    stamp.add_argument("--variant", required=True)
    stamp.add_argument("--workdir", required=True)
    stamp.set_defaults(func=cmd_stamp_summary)

    validate_summary_cmd = sub.add_parser("validate-summary")
    validate_summary_cmd.add_argument("--contract", required=True)
    validate_summary_cmd.add_argument("--summary", required=True)
    validate_summary_cmd.set_defaults(func=cmd_validate_summary)

    compare = sub.add_parser("compare")
    compare.add_argument("--contract", required=True)
    compare.add_argument("--base", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--output", required=True)
    compare.add_argument("--bootstrap-samples", type=int, default=12000)
    compare.add_argument("--seed", type=int, default=20260515)
    compare.set_defaults(func=cmd_compare)

    compare_reports_cmd = sub.add_parser("compare-reports")
    compare_reports_cmd.add_argument("--left", required=True)
    compare_reports_cmd.add_argument("--right", required=True)
    compare_reports_cmd.add_argument("--output", required=True)
    compare_reports_cmd.add_argument("--max-geomean-diff-pct", type=float, default=1.0)
    compare_reports_cmd.set_defaults(func=cmd_compare_reports)

    args = parser.parse_args()
    try:
        return args.func(args)
    except ContractError as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
