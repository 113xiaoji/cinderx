#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path


def file_entry(workdir: Path, relpath: str) -> dict[str, object]:
    path = workdir / relpath
    if not path.exists():
        return {
            "path": relpath,
            "exists": False,
        }
    data = path.read_bytes()
    return {
        "path": relpath,
        "exists": True,
        "size": len(data),
        "sha256": sha256(data).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-commit", default="")
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--wheel", default="")
    parser.add_argument("--build-no-isolation", default="0")
    parser.add_argument("--skip-pyperf", default="0")
    parser.add_argument("--path", action="append", default=[])
    args = parser.parse_args()

    workdir = Path(args.workdir)
    output = Path(args.output)

    payload = {
        "source_commit": args.source_commit,
        "workdir": str(workdir),
        "wheel": args.wheel,
        "build_no_isolation": args.build_no_isolation == "1",
        "skip_pyperf": args.skip_pyperf == "1",
        "files": [file_entry(workdir, relpath) for relpath in args.path],
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
