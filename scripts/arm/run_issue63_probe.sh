#!/usr/bin/env bash
set -euo pipefail

OUTDIR="${OUTDIR:-/root/work/arm-sync}"
LOOPS="${LOOPS:-20}"
PYTHON_BIN="${PYTHON:-python}"
RUN_ID="${RUN_ID:-issue63_probe}"

mkdir -p "$OUTDIR"

PYTHONJITDUMPFINALHIR=1 \
  "$PYTHON_BIN" scripts/arm/probe_issue63_unframer.py "$LOOPS" \
  > "$OUTDIR/${RUN_ID}.log" 2>&1

printf '%s\n' "$OUTDIR/${RUN_ID}.log"
