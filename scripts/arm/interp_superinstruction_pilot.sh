#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${WORKDIR:-/root/work/cinderx-main}"
DRIVER_VENV="${DRIVER_VENV:-/root/venv-cinderx314}"
CPYTHON_PY="${CPYTHON_PY:-/opt/python-3.14/bin/python3.14}"
OUT_DIR="${OUT_DIR:-/root/work/arm-sync/interp_superinstruction_pilot}"
N="${N:-250}"
WARMUP="${WARMUP:-20000}"
CALLS="${CALLS:-12000}"
REPEATS="${REPEATS:-5}"
WORKLOADS=(
  load_fast_pair_loop
  store_fast_load_fast_loop
  load_const_load_fast_loop
)

DRIVER_PY="$DRIVER_VENV/bin/python"
BENCH_SCRIPT="$WORKDIR/scripts/arm/bench_compare_modes.py"

if [[ ! -x "$CPYTHON_PY" ]]; then
  echo "ERROR: missing CPython interpreter: $CPYTHON_PY"
  exit 1
fi
if [[ ! -x "$DRIVER_PY" ]]; then
  echo "ERROR: missing driver interpreter: $DRIVER_PY"
  exit 1
fi
if [[ ! -f "$BENCH_SCRIPT" ]]; then
  echo "ERROR: missing benchmark driver: $BENCH_SCRIPT"
  exit 1
fi

mkdir -p "$OUT_DIR"

echo "== interp superinstruction pilot =="
echo "workdir=$WORKDIR"
echo "out_dir=$OUT_DIR"

for workload in "${WORKLOADS[@]}"; do
  cpython_json="$OUT_DIR/${workload}.cpython.json"
  cinderx_json="$OUT_DIR/${workload}.cinderx.cinder.json"

  echo ">> workload=$workload runtime=cpython mode=interp"
  env PYTHON_JIT=0 "$CPYTHON_PY" "$BENCH_SCRIPT" \
    --runtime cpython \
    --mode interp \
    --workload "$workload" \
    --n "$N" \
    --warmup "$WARMUP" \
    --calls "$CALLS" \
    --repeats "$REPEATS" \
    --output "$cpython_json"

  echo ">> workload=$workload runtime=cinderx mode=interp"
  env PYTHONJITDISABLE=1 "$DRIVER_PY" "$BENCH_SCRIPT" \
    --runtime cinderx \
    --mode interp \
    --producer cinder \
    --workload "$workload" \
    --n "$N" \
    --warmup "$WARMUP" \
    --calls "$CALLS" \
    --repeats "$REPEATS" \
    --output "$cinderx_json"
done

echo "== pilot artifacts =="
find "$OUT_DIR" -maxdepth 1 -type f -name '*.json' | sort
