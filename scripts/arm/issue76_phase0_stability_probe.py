import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    runs = int(os.environ.get("ISSUE76_PHASE0_STABILITY_RUNS", "10"))
    probe = Path(__file__).with_name("issue76_phase0_probe.py")
    failures = 0

    for idx in range(1, runs + 1):
        print(f"==== stability:{idx} ====")
        proc = subprocess.run(
            [sys.executable, "-u", str(probe)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        print(proc.stdout, end="")
        print(f"rc={proc.returncode}")
        if proc.returncode != 0:
            failures += 1

    print(f"stability_runs={runs}")
    print(f"stability_failures={failures}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
