#!/usr/bin/env bash
set -euo pipefail

DRIVER_VENV="${DRIVER_VENV:-/root/venv-cinderx314}"
WORKDIR="${WORKDIR:-$(pwd)}"
BENCHMARKS="${BENCHMARKS:-}"
SAMPLES="${SAMPLES:-3}"
AUTOJIT="${AUTOJIT:-50}"
MODE="${MODE:-autojit}"
OUTPUT="${OUTPUT:-/root/work/arm-sync/pyperf_subset.json}"
INSTALL_CINDERX_WHEEL="${INSTALL_CINDERX_WHEEL:-1}"
CINDERX_ENABLE_SPECIALIZED_OPCODES="${CINDERX_ENABLE_SPECIALIZED_OPCODES:-1}"
CINDERX_JITLIST_ENTRIES="${CINDERX_JITLIST_ENTRIES:-}"
PYTHONJITFILTERTINY="${PYTHONJITFILTERTINY:-}"
PYTHONJITSHAPEPROFITFILTER="${PYTHONJITSHAPEPROFITFILTER:-}"
PYTHONJITFILTERGENERATED="${PYTHONJITFILTERGENERATED:-}"
PYTHONJITADMITSTATEHELPERS="${PYTHONJITADMITSTATEHELPERS:-}"
PYTHONJITADMITCALLINGSTATEHELPERS="${PYTHONJITADMITCALLINGSTATEHELPERS:-}"
PYTHONJITDEFERFILTEREDHELPERS="${PYTHONJITDEFERFILTEREDHELPERS:-}"
PYTHONJITDEFERCONTAINSHELPERS="${PYTHONJITDEFERCONTAINSHELPERS:-}"
CINDERX_PYPERF_HOOK_PROBE_FILE="${CINDERX_PYPERF_HOOK_PROBE_FILE:-}"
PYTHONJITDEBUG="${PYTHONJITDEBUG:-}"
PYTHONJITLOGFILE="${PYTHONJITLOGFILE:-}"
PYTHONJITENABLEHIRINLINER="${PYTHONJITENABLEHIRINLINER:-}"
PYTHONJITENABLEMETHODVALUEINLINER="${PYTHONJITENABLEMETHODVALUEINLINER:-}"
PYTHONJITENABLESPECIALIZEDCONTAINS="${PYTHONJITENABLESPECIALIZEDCONTAINS:-}"
PYTHONJITDYNAMICMETHODCACHESPLIT="${PYTHONJITDYNAMICMETHODCACHESPLIT:-}"
PYTHONJITENABLEKWPYFUNCVECTORCALL="${PYTHONJITENABLEKWPYFUNCVECTORCALL:-}"
PYTHONJITZEROARGMWVDELAYEDLOOKUP="${PYTHONJITZEROARGMWVDELAYEDLOOKUP:-}"
PYTHONJITEXACTDICTSUBSCR="${PYTHONJITEXACTDICTSUBSCR:-}"
PYTHONJITMETHODDESCRFASTVECTORCALL="${PYTHONJITMETHODDESCRFASTVECTORCALL:-}"
PYTHONJITINLINELISTITERNEXT="${PYTHONJITINLINELISTITERNEXT:-}"
PYTHONJITLISTPOPLASTHELPER="${PYTHONJITLISTPOPLASTHELPER:-}"
PYTHONJITCACHEDMETHODCALLHELPER="${PYTHONJITCACHEDMETHODCALLHELPER:-}"
PYTHONJITSTOREATTRINSTANCEVALUEEXISTING="${PYTHONJITSTOREATTRINSTANCEVALUEEXISTING:-}"
PYTHONJITINSTANCEVALUEMINLOCALS="${PYTHONJITINSTANCEVALUEMINLOCALS:-}"
PYTHONJITEXACTMETHODCACHESPLIT="${PYTHONJITEXACTMETHODCACHESPLIT:-}"

if [[ -z "$BENCHMARKS" ]]; then
  echo "ERROR: BENCHMARKS must be set"
  exit 2
fi
if [[ "$MODE" != "autojit" && "$MODE" != "nojit" && "$MODE" != "jitlist" && "$MODE" != "jitlist-autojit" ]]; then
  echo "ERROR: MODE must be one of: autojit, nojit, jitlist, jitlist-autojit"
  exit 2
fi

DRIVER_PY="$DRIVER_VENV/bin/python"
if [[ ! -x "$DRIVER_PY" ]]; then
  echo "ERROR: missing driver python: $DRIVER_PY"
  exit 2
fi

HOOK_DIR="$WORKDIR/scripts/arm/pyperf_env_hook"
if [[ ! -f "$HOOK_DIR/sitecustomize.py" ]]; then
  echo "ERROR: missing hook dir: $HOOK_DIR"
  exit 2
fi

TMPDIR="$(mktemp -d /tmp/pyperf_subset.XXXXXX)"
trap 'rm -rf "$TMPDIR"' EXIT

PYVENV_PATH="$(
  PYTHONJIT=0 "$DRIVER_PY" -m pyperformance venv show | \
    sed -n 's/^Virtual environment path: \([^ ]*\).*$/\1/p'
)"
if [[ -z "$PYVENV_PATH" ]]; then
  echo "ERROR: failed to resolve pyperformance venv path"
  exit 2
fi
if [[ ! -x "$PYVENV_PATH/bin/python" ]]; then
  echo "pyperf_subset_venv_create=$PYVENV_PATH"
  if ! PYTHONJIT=0 "$DRIVER_PY" -m pyperformance venv create; then
    echo "pyperf_subset_venv_create=failed"
  fi
fi
if [[ ! -x "$PYVENV_PATH/bin/python" ]]; then
  fallback_path=""
  fallback_path="/root/venv/$(basename "$PYVENV_PATH")"
  if [[ -n "$fallback_path" && -x "$fallback_path/bin/python" ]]; then
    echo "pyperf_subset_venv_fallback=$fallback_path"
    PYVENV_PATH="$fallback_path"
  else
    echo "ERROR: failed to resolve pyperformance venv path"
    exit 2
  fi
fi

if [[ "$INSTALL_CINDERX_WHEEL" != "0" ]]; then
  shopt -s nullglob
  cinderx_wheels=("$WORKDIR"/dist/cinderx-*.whl)
  shopt -u nullglob
  if (( ${#cinderx_wheels[@]} > 0 )); then
    cinderx_wheel="$(ls -t "${cinderx_wheels[@]}" | head -n 1)"
    echo "pyperf_subset_install_wheel=$cinderx_wheel"
    "$PYVENV_PATH/bin/python" -m pip install --force-reinstall --no-deps \
      "$cinderx_wheel" >/dev/null
  else
    echo "pyperf_subset_install_wheel=missing"
  fi
fi

echo "pyperf_subset_benchmarks=$BENCHMARKS"
echo "pyperf_subset_samples=$SAMPLES"
echo "pyperf_subset_mode=$MODE"
echo "pyperf_subset_output=$OUTPUT"

inherit_env="PYTHONPATH,CINDERX_ENABLE_SPECIALIZED_OPCODES,CINDERX_DISABLE"
worker_env=(
  PYTHONPATH="$HOOK_DIR${PYTHONPATH:+:$PYTHONPATH}"
  CINDERX_ENABLE_SPECIALIZED_OPCODES="$CINDERX_ENABLE_SPECIALIZED_OPCODES"
  CINDERX_DISABLE="0"
)

case "$MODE" in
  autojit)
    worker_env+=(CINDERX_WORKER_PYTHONJITAUTO="$AUTOJIT")
    inherit_env+=",CINDERX_WORKER_PYTHONJITAUTO"
    if [[ -n "$CINDERX_JITLIST_ENTRIES" ]]; then
      worker_env+=(CINDERX_JITLIST_ENTRIES="$CINDERX_JITLIST_ENTRIES")
      inherit_env+=",CINDERX_JITLIST_ENTRIES"
    fi
    ;;
  nojit)
    worker_env+=(CINDERX_DISABLE="1")
    ;;
  jitlist)
    jitlist_entries="$CINDERX_JITLIST_ENTRIES"
    if [[ -z "$jitlist_entries" ]]; then
      jitlist_entries="__main__:*"
    fi
    worker_env+=(
      CINDERX_JITLIST_ENTRIES="$jitlist_entries"
      PYTHONJITENABLEJITLISTWILDCARDS="1"
    )
    inherit_env+=",CINDERX_JITLIST_ENTRIES,PYTHONJITENABLEJITLISTWILDCARDS"
    ;;
  jitlist-autojit)
    jitlist_entries="$CINDERX_JITLIST_ENTRIES"
    if [[ -z "$jitlist_entries" ]]; then
      jitlist_entries="__main__:*"
    fi
    worker_env+=(
      CINDERX_JITLIST_ENTRIES="$jitlist_entries"
      CINDERX_JITLIST_AUTOJIT="$AUTOJIT"
      PYTHONJITENABLEJITLISTWILDCARDS="1"
    )
    inherit_env+=",CINDERX_JITLIST_ENTRIES,CINDERX_JITLIST_AUTOJIT,PYTHONJITENABLEJITLISTWILDCARDS"
    ;;
esac

add_optional_env() {
  local name="$1"
  local value="${!name:-}"
  if [[ -n "$value" ]]; then
    worker_env+=("$name=$value")
    inherit_env+=",$name"
  fi
}

add_optional_env PYTHONJITINSTANCEVALUEMINLOCALS
add_optional_env PYTHONJITEXACTMETHODCACHESPLIT
add_optional_env PYTHONJITFILTERTINY
add_optional_env PYTHONJITSHAPEPROFITFILTER
add_optional_env PYTHONJITFILTERGENERATED
add_optional_env PYTHONJITADMITSTATEHELPERS
add_optional_env PYTHONJITADMITCALLINGSTATEHELPERS
add_optional_env PYTHONJITDEFERFILTEREDHELPERS
add_optional_env PYTHONJITDEFERCONTAINSHELPERS
add_optional_env CINDERX_PYPERF_HOOK_PROBE_FILE
add_optional_env PYTHONJITDEBUG
add_optional_env PYTHONJITLOGFILE
add_optional_env PYTHONJITENABLEHIRINLINER
add_optional_env PYTHONJITENABLEMETHODVALUEINLINER
add_optional_env PYTHONJITENABLESPECIALIZEDCONTAINS
add_optional_env PYTHONJITDYNAMICMETHODCACHESPLIT
add_optional_env PYTHONJITENABLEKWPYFUNCVECTORCALL
add_optional_env PYTHONJITZEROARGMWVDELAYEDLOOKUP
add_optional_env PYTHONJITEXACTDICTSUBSCR
add_optional_env PYTHONJITMETHODDESCRFASTVECTORCALL
add_optional_env PYTHONJITINLINELISTITERNEXT
add_optional_env PYTHONJITLISTPOPLASTHELPER
add_optional_env PYTHONJITCACHEDMETHODCALLHELPER
add_optional_env PYTHONJITSTOREATTRINSTANCEVALUEEXISTING

for ((i = 1; i <= SAMPLES; i++)); do
  out="$TMPDIR/run_${i}.json"
  echo ">> pyperformance subset sample $i/$SAMPLES"
  env \
    CINDERX_DISABLE=1 \
    "${worker_env[@]}" \
    "$DRIVER_PY" -m pyperformance run --debug-single-value -b "$BENCHMARKS" \
      --inherit-environ "$inherit_env" \
      -o "$out"
done

"$DRIVER_PY" - <<'PY' "$TMPDIR" "$OUTPUT" "$BENCHMARKS" "$SAMPLES" "$AUTOJIT" "$MODE"
import json
import statistics
import sys
from pathlib import Path

tmpdir = Path(sys.argv[1])
output = Path(sys.argv[2])
benchmarks = sys.argv[3].split(",")
samples = int(sys.argv[4])
autojit = int(sys.argv[5])
mode = sys.argv[6]

rows = {}
for path in sorted(tmpdir.glob("run_*.json")):
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    for idx, bench in enumerate(data.get("benchmarks", [])):
        name = bench.get("metadata", {}).get("name")
        if name is None and len(benchmarks) == 1:
            # pyperformance may omit per-benchmark metadata for a single
            # -b entry, even though the raw value is present.
            name = benchmarks[0]
        if name is None:
            continue
        value = bench["runs"][0]["values"][0]
        rows.setdefault(name, []).append(float(value))

summary = {
    "benchmarks": [],
    "benchmark_filter": benchmarks,
    "samples": samples,
    "autojit": autojit,
    "mode": mode,
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
PY
