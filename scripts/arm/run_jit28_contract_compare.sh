#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CONTRACT="$REPO_ROOT/benchmark-contract/jit28.contract.json"
BASE_WORKDIR=""
CANDIDATE_WORKDIR=""
DRIVER_VENV=""
OUTPUT_DIR="/root/work/arm-sync/jit28-contract"
BOOTSTRAP_SAMPLES="12000"
SEED="20260515"
RUNNER_HOOK_DIR="$REPO_ROOT/scripts/arm/pyperf_env_hook"

usage() {
  cat <<'USAGE'
Usage:
  scripts/arm/run_jit28_contract_compare.sh \
    --base-workdir /path/to/base/source \
    --candidate-workdir /path/to/candidate/source \
    --driver-venv /path/to/driver/venv \
    [--contract /path/to/jit28.contract.json] \
    [--output-dir /root/work/arm-sync/jit28-contract] \
    [--bootstrap-samples 12000] \
    [--seed 20260515]

The benchmark case candidates are read only from the contract suite manifest.
This script must not contain benchmark names.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --contract)
      CONTRACT="$2"
      shift 2
      ;;
    --base-workdir)
      BASE_WORKDIR="$2"
      shift 2
      ;;
    --candidate-workdir)
      CANDIDATE_WORKDIR="$2"
      shift 2
      ;;
    --driver-venv)
      DRIVER_VENV="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --bootstrap-samples)
      BOOTSTRAP_SAMPLES="$2"
      shift 2
      ;;
    --seed)
      SEED="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$BASE_WORKDIR" || -z "$CANDIDATE_WORKDIR" || -z "$DRIVER_VENV" ]]; then
  echo "ERROR: --base-workdir, --candidate-workdir, and --driver-venv are required" >&2
  usage >&2
  exit 2
fi

DRIVER_PY="$DRIVER_VENV/bin/python"
CONTRACT_TOOL="$REPO_ROOT/scripts/arm/jit28_contract.py"
SUBSET_RUNNER="$REPO_ROOT/scripts/arm/run_pyperf_subset.sh"

if [[ ! -x "$DRIVER_PY" ]]; then
  echo "ERROR: missing driver python: $DRIVER_PY" >&2
  exit 2
fi
if [[ ! -f "$CONTRACT" ]]; then
  echo "ERROR: missing contract: $CONTRACT" >&2
  exit 2
fi
if [[ ! -f "$CONTRACT_TOOL" ]]; then
  echo "ERROR: missing contract tool: $CONTRACT_TOOL" >&2
  exit 2
fi
if [[ ! -f "$SUBSET_RUNNER" ]]; then
  echo "ERROR: missing subset runner: $SUBSET_RUNNER" >&2
  exit 2
fi
if [[ ! -f "$RUNNER_HOOK_DIR/sitecustomize.py" ]]; then
  echo "ERROR: missing runner hook: $RUNNER_HOOK_DIR/sitecustomize.py" >&2
  exit 2
fi

BASE_WORKDIR="$(cd "$BASE_WORKDIR" && pwd)"
CANDIDATE_WORKDIR="$(cd "$CANDIDATE_WORKDIR" && pwd)"
OUTPUT_DIR="$(mkdir -p "$OUTPUT_DIR" && cd "$OUTPUT_DIR" && pwd)"

"$DRIVER_PY" "$CONTRACT_TOOL" validate-suite --contract "$CONTRACT" >/dev/null
BENCHMARKS="$("$DRIVER_PY" "$CONTRACT_TOOL" emit-benchmarks --contract "$CONTRACT")"
SAMPLES="$("$DRIVER_PY" "$CONTRACT_TOOL" emit-field --contract "$CONTRACT" --field samples)"
AUTOJIT="$("$DRIVER_PY" "$CONTRACT_TOOL" emit-field --contract "$CONTRACT" --field autojit)"
CONTRACT_ID="$("$DRIVER_PY" "$CONTRACT_TOOL" emit-field --contract "$CONTRACT" --field contract_id)"
SUITE_ID="$("$DRIVER_PY" "$CONTRACT_TOOL" emit-field --contract "$CONTRACT" --field suite_id)"
SUITE_SHA="$("$DRIVER_PY" "$CONTRACT_TOOL" emit-field --contract "$CONTRACT" --field suite_manifest_sha256)"
CASE_COUNT="$("$DRIVER_PY" "$CONTRACT_TOOL" emit-field --contract "$CONTRACT" --field case_count)"

echo "contract_id=$CONTRACT_ID"
echo "suite_id=$SUITE_ID"
echo "suite_manifest_sha256=$SUITE_SHA"
echo "case_count=$CASE_COUNT"
echo "samples=$SAMPLES"
echo "autojit=$AUTOJIT"
echo "base_workdir=$BASE_WORKDIR"
echo "candidate_workdir=$CANDIDATE_WORKDIR"
echo "output_dir=$OUTPUT_DIR"

resolve_pyperf_venv() {
  local workdir="$1"
  (
    cd "$workdir"
    PYTHONJIT=0 "$DRIVER_PY" -m pyperformance venv show
  ) | sed -n 's/^Virtual environment path: \([^ ]*\).*$/\1/p'
}

check_variant_import_path() {
  local variant="$1"
  local workdir="$2"
  local pyvenv
  pyvenv="$(resolve_pyperf_venv "$workdir")"
  if [[ -z "$pyvenv" || ! -x "$pyvenv/bin/python" ]]; then
    echo "ERROR: failed to resolve pyperformance venv for $variant in $workdir" >&2
    exit 2
  fi
  local cinderx_file
  cinderx_file="$(
    PYTHONJIT=0 "$pyvenv/bin/python" - <<'PY'
import pathlib
import cinderx
print(pathlib.Path(cinderx.__file__).resolve())
PY
  )"
  case "$cinderx_file" in
    "$workdir"/*)
      ;;
    *)
      echo "ERROR: $variant cinderx import path is outside workdir" >&2
      echo "variant=$variant" >&2
      echo "workdir=$workdir" >&2
      echo "cinderx_file=$cinderx_file" >&2
      exit 2
      ;;
  esac
  echo "${variant}_pyperf_venv=$pyvenv"
  echo "${variant}_cinderx_file=$cinderx_file"
}

run_variant() {
  local variant="$1"
  local workdir="$2"
  local raw="$OUTPUT_DIR/${variant}_raw.json"
  local stamped="$OUTPUT_DIR/${variant}_${CONTRACT_ID}.json"

  check_variant_import_path "$variant" "$workdir"

  env \
    DRIVER_VENV="$DRIVER_VENV" \
    WORKDIR="$workdir" \
    HOOK_DIR="$RUNNER_HOOK_DIR" \
    BENCHMARKS="$BENCHMARKS" \
    SAMPLES="$SAMPLES" \
    AUTOJIT="$AUTOJIT" \
    OUTPUT="$raw" \
    bash "$SUBSET_RUNNER"

  "$DRIVER_PY" "$CONTRACT_TOOL" stamp-summary \
    --contract "$CONTRACT" \
    --summary "$raw" \
    --output "$stamped" \
    --variant "$variant" \
    --workdir "$workdir"
}

run_variant base "$BASE_WORKDIR"
run_variant candidate "$CANDIDATE_WORKDIR"

"$DRIVER_PY" "$CONTRACT_TOOL" compare \
  --contract "$CONTRACT" \
  --base "$OUTPUT_DIR/base_${CONTRACT_ID}.json" \
  --candidate "$OUTPUT_DIR/candidate_${CONTRACT_ID}.json" \
  --output "$OUTPUT_DIR/report_${CONTRACT_ID}.json" \
  --bootstrap-samples "$BOOTSTRAP_SAMPLES" \
  --seed "$SEED"

echo "report=$OUTPUT_DIR/report_${CONTRACT_ID}.json"
