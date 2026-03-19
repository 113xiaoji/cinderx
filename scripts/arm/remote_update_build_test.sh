#!/usr/bin/env bash
set -euo pipefail

# This script runs on the ARM host. It expects:
# - ${INCOMING_DIR}/cinderx-update.tar uploaded from Windows (git archive output)
# - It will rsync the extracted sources into $WORKDIR (preserving scratch/, dist/)
# - It will build a wheel, install it into the driver venv, set up pyperformance venv
# - It will run smoke tests + pyperformance gates to catch crashes early

INCOMING_DIR="${INCOMING_DIR:-/root/work/incoming}"
WORKDIR="${WORKDIR:-/root/work/cinderx-main}"
PY="${PYTHON:-/opt/python-3.14/bin/python3.14}"
DRIVER_VENV="${DRIVER_VENV:-/root/venv-cinderx314}"
BENCH="${BENCH:-richards}"
AUTOJIT="${AUTOJIT:-50}"
SMOKE_AUTOJIT="${SMOKE_AUTOJIT:-10}"
PARALLEL="${PARALLEL:-1}"
SKIP_PYPERF="${SKIP_PYPERF:-0}"
RECREATE_PYPERF_VENV="${RECREATE_PYPERF_VENV:-0}"
AUTOJIT_GATE="${AUTOJIT_GATE:-$AUTOJIT}"
AUTOJIT_USE_JITLIST_FILTER="${AUTOJIT_USE_JITLIST_FILTER:-1}"
AUTOJIT_EXTRA_JITLIST="${AUTOJIT_EXTRA_JITLIST:-}"
JITLIST_ENTRIES="${JITLIST_ENTRIES:-__main__:*}"
AUTOJIT_JITLIST_ENTRIES="${AUTOJIT_JITLIST_ENTRIES:-}"
ARM_RUNTIME_SKIP_TESTS="${ARM_RUNTIME_SKIP_TESTS:-}"
ARM_RUNTIME_ONLY_TESTS="${ARM_RUNTIME_ONLY_TESTS:-}"
ARM_RUNTIME_TEST_NAMES="${ARM_RUNTIME_TEST_NAMES:-}"
FORCE_CLEAN_BUILD="${FORCE_CLEAN_BUILD:-0}"
SKIP_PYPERF_WORKER_PROBE="${SKIP_PYPERF_WORKER_PROBE:-0}"

if ! [[ "$AUTOJIT_GATE" =~ ^[0-9]+$ ]]; then
  echo "ERROR: AUTOJIT_GATE must be a non-negative integer, got '$AUTOJIT_GATE'"
  exit 1
fi
if [[ "$AUTOJIT_USE_JITLIST_FILTER" != "0" && "$AUTOJIT_USE_JITLIST_FILTER" != "1" ]]; then
  echo "ERROR: AUTOJIT_USE_JITLIST_FILTER must be 0 or 1, got '$AUTOJIT_USE_JITLIST_FILTER'"
  exit 1
fi

mkdir -p "$WORKDIR" "$INCOMING_DIR" /root/work/arm-sync

RUN_ID="$(date +%Y%m%d_%H%M%S)"

deactivate_if_active() {
  if declare -F deactivate >/dev/null 2>&1; then
    deactivate
  fi
}

echo ">> staging extract"
stage="$(mktemp -d /root/work/cinderx-stage.XXXXXX)"
tar -xf "$INCOMING_DIR/cinderx-update.tar" -C "$stage"

echo ">> rsync sources into $WORKDIR (preserve scratch/, dist/)"
rsync -a --delete --exclude scratch --exclude dist "$stage/cinderx-src/" "$WORKDIR/"
rm -rf "$stage" "$INCOMING_DIR/cinderx-update.tar"

cd "$WORKDIR"
export CMAKE_BUILD_PARALLEL_LEVEL="$PARALLEL"
export CINDERX_BUILD_JOBS="$PARALLEL"

if [[ "$FORCE_CLEAN_BUILD" == "1" ]]; then
  echo ">> clean build dirs"
  rm -rf "$WORKDIR/scratch/temp.linux-aarch64-cpython-314" \
         "$WORKDIR/scratch/lib.linux-aarch64-cpython-314"
fi

echo ">> build wheel (CMAKE_BUILD_PARALLEL_LEVEL=$CMAKE_BUILD_PARALLEL_LEVEL, CINDERX_BUILD_JOBS=$CINDERX_BUILD_JOBS)"
"$PY" -m build --wheel
WHEEL="$(ls -1t dist/cinderx-*.whl | head -n 1)"
echo "wheel=$WHEEL"

if [[ ! -d "$DRIVER_VENV" ]]; then
  echo ">> create driver venv $DRIVER_VENV"
  "$PY" -m venv "$DRIVER_VENV"
fi

echo ">> install wheel + pyperformance into driver venv"
. "$DRIVER_VENV/bin/activate"
PYTHONJIT=0 python -m pip install -q -U pip
PYTHONJIT=0 python -m pip install -q --force-reinstall "$WHEEL"
PYTHONJIT=0 python -m pip install -q -U pyperformance

DEV_PYTHONPATH="$WORKDIR/scratch/lib.linux-aarch64-cpython-314:$WORKDIR/cinderx/PythonLib"
export PYTHONPATH="$DEV_PYTHONPATH"
deactivate_if_active

echo ">> unittest: ARM runtime checks"
if [[ -n "$ARM_RUNTIME_TEST_NAMES" ]]; then
  IFS=',' read -r -a _arm_runtime_tests <<< "$ARM_RUNTIME_TEST_NAMES"
  echo "arm_runtime_test_names=$ARM_RUNTIME_TEST_NAMES"
  for _test_name in "${_arm_runtime_tests[@]}"; do
    if [[ -z "$_test_name" ]]; then
      continue
    fi
    echo "running: $_test_name"
    env PYTHONPATH="$PYTHONPATH" "$PY" cinderx/PythonLib/test_cinderx/test_arm_runtime.py "$_test_name" -v
  done
elif [[ -z "$ARM_RUNTIME_SKIP_TESTS" && -z "$ARM_RUNTIME_ONLY_TESTS" ]]; then
  env PYTHONPATH="$PYTHONPATH" "$PY" cinderx/PythonLib/test_cinderx/test_arm_runtime.py
else
  env PYTHONPATH="$PYTHONPATH" ARM_RUNTIME_SKIP_TESTS="$ARM_RUNTIME_SKIP_TESTS" ARM_RUNTIME_ONLY_TESTS="$ARM_RUNTIME_ONLY_TESTS" "$PY" - <<'PY'
import importlib.util
import os
import pathlib
import sys
import unittest

skip_tokens = [
    token.strip()
    for token in os.environ.get("ARM_RUNTIME_SKIP_TESTS", "").split(",")
    if token.strip()
]
only_tokens = [
    token.strip()
    for token in os.environ.get("ARM_RUNTIME_ONLY_TESTS", "").split(",")
    if token.strip()
]

test_path = pathlib.Path("cinderx/PythonLib/test_cinderx/test_arm_runtime.py")
spec = importlib.util.spec_from_file_location("test_arm_runtime", test_path)
if spec is None or spec.loader is None:
    raise SystemExit(f"failed to load {test_path}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

suite = unittest.defaultTestLoader.loadTestsFromModule(module)
filtered = unittest.TestSuite()
skipped = []


def iter_tests(s):
    for t in s:
        if isinstance(t, unittest.TestSuite):
            yield from iter_tests(t)
        else:
            yield t


for test in iter_tests(suite):
    test_id = test.id()
    if only_tokens and not any(token in test_id for token in only_tokens):
        skipped.append(test_id)
        continue
    if any(token in test_id for token in skip_tokens):
        skipped.append(test_id)
        continue
    filtered.addTest(test)

print("arm_runtime_only_tokens=", only_tokens)
print("arm_runtime_skip_tokens=", skip_tokens)
print("arm_runtime_skipped_count=", len(skipped))
for test_id in skipped:
    print("skipped:", test_id)

runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(filtered)
if not result.wasSuccessful():
    raise SystemExit(1)
PY
fi

echo ">> smoke: JIT is effective (compiled code executes, not just 'enabled')"
# We verify effectiveness by:
# 1) Run a function in interpreted mode and observe interpreted call count increases.
# 2) Force-compile it and observe the interpreted call count stops increasing while the function still runs.
env PYTHONPATH="$PYTHONPATH" PYTHONJITAUTO=1000000 "$PY" - <<'PY'
import cinderx
import cinderx.jit as jit

assert cinderx.is_initialized()
jit.enable()

# Ensure our first calls are interpreted (avoid auto-jit during the interpreted phase).
jit.compile_after_n_calls(1000000)


def f(n: int) -> int:
    s = 0
    for i in range(n):
        s += i
    return s


_ = jit.force_uncompile(f)
assert not jit.is_jit_compiled(f), "expected f() to start interpreted"

before = jit.count_interpreted_calls(f)
for _ in range(10):
    assert f(10) == 45
after = jit.count_interpreted_calls(f)
assert after > before, (before, after)

assert jit.force_compile(f), "force_compile failed"
assert jit.is_jit_compiled(f), "expected f() to be JIT compiled"
code_size = jit.get_compiled_size(f)
assert code_size > 0, code_size

interp0 = jit.count_interpreted_calls(f)
for _ in range(2000):
    assert f(10) == 45
interp1 = jit.count_interpreted_calls(f)
assert interp1 == interp0, (interp0, interp1)

print("jit-effective-ok", "compiled_size", code_size, "interp_calls", interp1)
PY
deactivate_if_active

echo ">> ensure pyperformance venv exists"
. "$DRIVER_VENV/bin/activate"
ensure_pyperf_venv() {
  local action="$1"
  local cmd=()
  if [[ "$action" == "recreate" ]]; then
    cmd=(python -m pyperformance venv recreate)
  else
    cmd=(python -m pyperformance venv create)
  fi

  set +e
  PYTHONJIT=0 "${cmd[@]}"
  local rc=$?
  set -e
  if [[ $rc -eq 0 ]]; then
    return 0
  fi

  echo "WARN: pyperformance venv ${action} failed (rc=$rc), cleanup '$WORKDIR/venv' and retry once"
  rm -rf "$WORKDIR/venv"
  PYTHONJIT=0 "${cmd[@]}"
}

set +e
PYVENV_PATH="$(
  PYTHONJIT=0 python -m pyperformance venv show 2>/dev/null | \
    sed -n 's/^Virtual environment path: \([^ ]*\).*$/\1/p'
)"
set -e
if [[ "$RECREATE_PYPERF_VENV" == "1" ]]; then
  ensure_pyperf_venv recreate
elif [[ -z "$PYVENV_PATH" || ! -x "$PYVENV_PATH/bin/python" ]]; then
  ensure_pyperf_venv create
fi
PYVENV_PATH="$(
  PYTHONJIT=0 python -m pyperformance venv show | \
    sed -n 's/^Virtual environment path: \([^ ]*\).*$/\1/p'
)"
echo "pyperf_venv=$PYVENV_PATH"
if [[ -z "$PYVENV_PATH" || ! -d "$PYVENV_PATH" ]]; then
  echo "ERROR: failed to determine pyperformance venv path"
  python -m pyperformance venv show || true
  exit 1
fi
deactivate_if_active

echo ">> install wheel into pyperformance venv"
. "$PYVENV_PATH/bin/activate"
PYTHONJIT=0 python -m pip install -q --force-reinstall "$WHEEL"
SITEPKG="$(python -c 'import site; print(site.getsitepackages()[0])')"
HOOK_SRC="$WORKDIR/scripts/arm/pyperf_env_hook/sitecustomize.py"
if [[ ! -f "$HOOK_SRC" ]]; then
  echo "ERROR: missing pyperf env hook: $HOOK_SRC"
  exit 1
fi
install -m 0644 "$HOOK_SRC" "$SITEPKG/sitecustomize.py"

if [[ "$SKIP_PYPERF_WORKER_PROBE" == "1" ]]; then
  echo ">> skip pyperformance worker probe"
else
  echo ">> verify pyperformance worker startup"
  env PYTHONPATH="$PYTHONPATH" python "$WORKDIR/scripts/arm/verify_pyperf_venv.py" \
    --venv "$PYVENV_PATH" \
    --output "/root/work/arm-sync/${BENCH}_pyperf_venv_${RUN_ID}.json" \
    --probe-worker \
    --worker-argv-token="--worker" \
    --worker-env "PYPERFORMANCE_RUNID=verify-${RUN_ID}" \
    --worker-env "PYTHONPATH=$PYTHONPATH" \
    --worker-env "CINDERX_WORKER_PYTHONJITAUTO=$SMOKE_AUTOJIT" \
    --require-sitecustomize-prefix "$SITEPKG" \
    --require-cinderx-initialized \
    --require-jit-enabled
fi

deactivate_if_active

echo ">> smoke: JIT init + generator + regex compile"
# Keep startup smoke below known crash-prone aggressive thresholds while still
# exercising JIT-enabled initialization in the benchmark venv.
env PYTHONPATH="$PYTHONPATH" PYPERFORMANCE_RUNID="smoke-${RUN_ID}" \
  CINDERX_WORKER_PYTHONJITAUTO="$SMOKE_AUTOJIT" \
  "$PYVENV_PATH/bin/python" -c 'g=(i for i in [1]); next(g, None); import re; re.compile("a+"); print("smoke-ok")'

if [[ "$SKIP_PYPERF" == "1" ]]; then
  echo "SKIP_PYPERF=1 set; done after smoke."
  exit 0
fi

echo ">> pyperformance gate (jitlist, debug-single-value)"
printf '%s\n' "$JITLIST_ENTRIES" | tr ',' '\n' >/tmp/jitlist_gate.txt
. "$DRIVER_VENV/bin/activate"
env PYTHONJITLISTFILE=/tmp/jitlist_gate.txt PYTHONJITENABLEJITLISTWILDCARDS=1 \
  PYTHONPATH="$PYTHONPATH" \
  python -m pyperformance run --debug-single-value -b "$BENCH" \
    --inherit-environ PYTHONPATH,PYTHONJITLISTFILE,PYTHONJITENABLEJITLISTWILDCARDS \
    -o "/root/work/arm-sync/${BENCH}_jitlist_${RUN_ID}.json"
deactivate_if_active

echo ">> pyperformance gate (auto-jit, debug-single-value)"
. "$DRIVER_VENV/bin/activate"
LOG="/tmp/jit_${BENCH}_autojit${AUTOJIT_GATE}_${RUN_ID}.log"
AUTOJIT_JITLIST_FILE="/tmp/jitlist_autojit_gate_${RUN_ID}.txt"
if [[ "$AUTOJIT_USE_JITLIST_FILTER" == "1" ]]; then
  if [[ -n "$AUTOJIT_JITLIST_ENTRIES" ]]; then
    printf '%s\n' "$AUTOJIT_JITLIST_ENTRIES" | tr ',' '\n' >"$AUTOJIT_JITLIST_FILE"
  else
    {
      echo "__main__:*"
      if [[ -n "$AUTOJIT_EXTRA_JITLIST" ]]; then
        IFS=',' read -r -a _extra_jitlist <<< "$AUTOJIT_EXTRA_JITLIST"
        for _entry in "${_extra_jitlist[@]}"; do
          if [[ -n "$_entry" ]]; then
            echo "$_entry"
          fi
        done
      fi
    } >"$AUTOJIT_JITLIST_FILE"
  fi
  echo "autojit_jitlist=$AUTOJIT_JITLIST_FILE"
  sed -n '1,50p' "$AUTOJIT_JITLIST_FILE"
  env PYTHONPATH="$PYTHONPATH" PYTHONJITAUTO="$AUTOJIT_GATE" \
    CINDERX_WORKER_PYTHONJITAUTO="$AUTOJIT_GATE" \
    PYTHONJITDEBUG=1 PYTHONJITLOGFILE="$LOG" \
    PYTHONJITLISTFILE="$AUTOJIT_JITLIST_FILE" PYTHONJITENABLEJITLISTWILDCARDS=1 \
    python -m pyperformance run --debug-single-value -b "$BENCH" \
      --inherit-environ PYTHONPATH,PYTHONJITAUTO,CINDERX_WORKER_PYTHONJITAUTO,PYTHONJITDEBUG,PYTHONJITLOGFILE,PYTHONJITLISTFILE,PYTHONJITENABLEJITLISTWILDCARDS \
      -o "/root/work/arm-sync/${BENCH}_autojit${AUTOJIT_GATE}_${RUN_ID}.json"
else
  env PYTHONPATH="$PYTHONPATH" PYTHONJITAUTO="$AUTOJIT_GATE" \
    CINDERX_WORKER_PYTHONJITAUTO="$AUTOJIT_GATE" \
    PYTHONJITDEBUG=1 PYTHONJITLOGFILE="$LOG" \
    python -m pyperformance run --debug-single-value -b "$BENCH" \
      --inherit-environ PYTHONPATH,PYTHONJITAUTO,CINDERX_WORKER_PYTHONJITAUTO,PYTHONJITDEBUG,PYTHONJITLOGFILE \
      -o "/root/work/arm-sync/${BENCH}_autojit${AUTOJIT_GATE}_${RUN_ID}.json"
fi
deactivate_if_active

if [[ ! -s "$LOG" ]]; then
  echo "ERROR: missing/empty JIT log: $LOG"
  exit 1
fi
# Ensure the benchmark actually hit JIT compilation of benchmark code (not just stdlib imports).
MAIN_COMPILE_COUNT="$(grep -c "Finished compiling __main__:" "$LOG" || true)"
TOTAL_COMPILE_COUNT="$(grep -c "Finished compiling " "$LOG" || true)"
OTHER_COMPILE_COUNT=$((TOTAL_COMPILE_COUNT - MAIN_COMPILE_COUNT))
COMPILE_SUMMARY_JSON="/root/work/arm-sync/${BENCH}_autojit${AUTOJIT_GATE}_${RUN_ID}_compile_summary.json"
python - <<'PY' "$COMPILE_SUMMARY_JSON" "$BENCH" "$AUTOJIT_GATE" "$AUTOJIT_USE_JITLIST_FILTER" \
  "$MAIN_COMPILE_COUNT" "$TOTAL_COMPILE_COUNT" "$OTHER_COMPILE_COUNT" "$LOG"
import json
import sys

path = sys.argv[1]
payload = {
    "benchmark": sys.argv[2],
    "autojit_gate": int(sys.argv[3]),
    "use_jitlist_filter": bool(int(sys.argv[4])),
    "main_compile_count": int(sys.argv[5]),
    "total_compile_count": int(sys.argv[6]),
    "other_compile_count": int(sys.argv[7]),
    "jit_log_path": sys.argv[8],
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"autojit_compile_summary={path}")
print(
    "autojit_compile_counts",
    f"total={payload['total_compile_count']}",
    f"main={payload['main_compile_count']}",
    f"other={payload['other_compile_count']}",
)
PY
if [[ "$MAIN_COMPILE_COUNT" -eq 0 ]]; then
  if [[ -z "$AUTOJIT_JITLIST_ENTRIES" ]]; then
    echo "ERROR: JIT did not compile any __main__ functions during '$BENCH' (JIT may not be active in benchmark workers)"
    echo "--- jit log tail ---"
    tail -n 120 "$LOG" || true
    exit 1
  elif [[ "$TOTAL_COMPILE_COUNT" -eq 0 ]]; then
    echo "ERROR: JIT did not compile any functions during '$BENCH'"
    echo "--- jit log tail ---"
    tail -n 120 "$LOG" || true
    exit 1
  fi
fi

echo "--- jit log tail ---"
tail -n 50 "$LOG" || true
deactivate_if_active
