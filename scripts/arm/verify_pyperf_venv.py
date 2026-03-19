#!/usr/bin/env python3
"""Validate the pyperformance venv setup used by the ARM remote entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def parse_pyvenv_cfg(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def run_worker_probe(
    venv_python: Path,
    argv_tokens: list[str],
    worker_env: list[str],
) -> dict[str, object]:
    code = r"""
import json
import sys

payload = {
    "argv": sys.argv[1:],
    "sitecustomize_file": None,
    "sitecustomize_error": None,
    "cinderx_initialized": False,
    "cinderx_import_error": None,
    "jit_enabled": False,
    "jit_error": None,
}

try:
    import sitecustomize
    payload["sitecustomize_file"] = getattr(sitecustomize, "__file__", None)
except Exception as exc:
    payload["sitecustomize_error"] = f"{type(exc).__name__}:{exc}"

try:
    import cinderx
    payload["cinderx_initialized"] = bool(cinderx.is_initialized())
    payload["cinderx_import_error"] = str(cinderx.get_import_error())
except Exception as exc:
    payload["cinderx_import_error"] = f"{type(exc).__name__}:{exc}"

try:
    import cinderx.jit as jit
    payload["jit_enabled"] = bool(jit.is_enabled())
except Exception as exc:
    payload["jit_error"] = f"{type(exc).__name__}:{exc}"

print(json.dumps(payload))
"""
    env = dict(os.environ)
    for item in worker_env:
        key, value = item.split("=", 1)
        env[key] = value
    proc = subprocess.run(
        [str(venv_python), "-c", code, *argv_tokens],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    payload: dict[str, object] = {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    if proc.returncode == 0:
        try:
            payload["worker"] = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            payload["decode_error"] = str(exc)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--venv", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-system-site-packages", action="store_true")
    parser.add_argument("--probe-worker", action="store_true")
    parser.add_argument("--worker-argv-token", action="append", default=[])
    parser.add_argument("--worker-env", action="append", default=[])
    parser.add_argument("--require-sitecustomize-prefix")
    parser.add_argument("--require-cinderx-initialized", action="store_true")
    parser.add_argument("--require-jit-enabled", action="store_true")
    args = parser.parse_args()

    venv = Path(args.venv)
    pyvenv_cfg = parse_pyvenv_cfg(venv / "pyvenv.cfg")
    payload: dict[str, object] = {
        "venv": str(venv),
        "pyvenv_cfg": pyvenv_cfg,
        "checks": {},
    }
    checks: dict[str, bool] = payload["checks"]  # type: ignore[assignment]

    include_system = (
        pyvenv_cfg.get("include-system-site-packages", "").lower() == "true"
    )
    checks["venv_exists"] = venv.is_dir()
    checks["python_exists"] = (venv / "bin" / "python").exists()
    checks["system_site_packages"] = include_system

    failed = False
    if not checks["venv_exists"] or not checks["python_exists"]:
        failed = True
    if args.require_system_site_packages and not include_system:
        failed = True

    if args.probe_worker:
        probe = run_worker_probe(
            venv / "bin" / "python",
            args.worker_argv_token,
            args.worker_env,
        )
        payload["worker_probe"] = probe
        worker = probe.get("worker", {}) if isinstance(probe.get("worker"), dict) else {}
        sitecustomize_file = worker.get("sitecustomize_file")
        checks["worker_returncode"] = probe.get("returncode", 1) == 0
        checks["worker_sitecustomize_prefix"] = (
            isinstance(sitecustomize_file, str)
            and args.require_sitecustomize_prefix is not None
            and sitecustomize_file.startswith(args.require_sitecustomize_prefix)
        ) if args.require_sitecustomize_prefix is not None else True
        checks["worker_cinderx_initialized"] = bool(worker.get("cinderx_initialized"))
        checks["worker_jit_enabled"] = bool(worker.get("jit_enabled"))
        if not checks["worker_returncode"]:
            failed = True
        if args.require_sitecustomize_prefix and not checks["worker_sitecustomize_prefix"]:
            failed = True
        if args.require_cinderx_initialized and not checks["worker_cinderx_initialized"]:
            failed = True
        if args.require_jit_enabled and not checks["worker_jit_enabled"]:
            failed = True

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
