# Benchmark Contract

This directory defines benchmark inputs and acceptance rules as machine-checkable
contracts. Markdown may explain a benchmark, but it is not the source of truth.

## JIT28 Fixed S12

The only valid entry point for the fixed JIT28 comparison is:

```bash
scripts/arm/run_jit28_contract_compare.sh \
  --base-workdir /path/to/base/source \
  --candidate-workdir /path/to/candidate/source \
  --driver-venv /path/to/driver/venv \
  --contract benchmark-contract/jit28.contract.json \
  --output-dir /root/work/arm-sync/jit28-contract
```

The runner reads benchmark candidates from:

- `benchmark-contract/suites/jit28-candidates.json`
- `benchmark-contract/suites/jit28-candidates.lock.json`

Shell scripts must not contain the benchmark case list. Agents must not pass an
ad hoc `BENCHMARKS=...` list for this contract.

## Suite Manifest And Lock

`jit28-candidates.json` contains the pyperformance selectors used by the runner.
`jit28-candidates.lock.json` contains the resolved benchmark rows that must
appear in the result.

The manifest and lock are both required:

- The manifest is the editable candidate source.
- The lock is the exact resolved case set.
- The lock stores the canonical SHA-256 of the manifest.
- The contract requires `expected_case_count == 28`.

If the manifest changes, the lock must be updated in the same change. A result is
invalid when the lock hash does not match the manifest.

## Valid Result Requirements

A comparison result is valid only when every item below is true:

- The suite manifest hash matches the suite lock.
- The resolved case count is exactly `28`.
- The raw pyperformance filter equals the suite manifest selectors.
- Every resolved case has exactly `12` samples.
- `AUTOJIT` is exactly `50`.
- Base and candidate summaries contain the same `contract_id`.
- Base and candidate summaries contain the same `suite_manifest_sha256`.
- No resolved case is missing and no extra case appears.
- The pyperformance parent process is started by the contract runner.
- The benchmark hook is the runner hook, not a variant-specific ad hoc hook.
- `cinderx.__file__` for each variant is under that variant's workdir.
- The runner hook is loaded inside each pyperformance worker process.
- Each worker can import `_cinderx`, reports CinderX initialized, and reports
  JIT enabled before benchmark execution.
- Any runtime library path required by the built wheel, for example a GCC
  `libstdc++` directory in `LD_LIBRARY_PATH`, is inherited by workers.

Anything else is `INVALID` and must not be used for a performance claim.

## Result Semantics

The report uses runtime deltas:

- Negative `delta_pct` means candidate is faster.
- Positive `delta_pct` means candidate is slower.

The overall conclusion is fixed:

- `real_gain`: `geomean_pct < 0` and the bootstrap 95% CI high bound is `< 0`.
- `real_regression`: `geomean_pct > 0` and the bootstrap 95% CI low bound is `> 0`.
- `noise`: all other cases.

Agents must quote the JSON report conclusion. They must not reinterpret wins,
losses, or individual benchmark rows as an overall gain.
