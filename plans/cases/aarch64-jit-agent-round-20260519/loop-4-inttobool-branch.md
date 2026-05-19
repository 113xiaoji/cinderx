# Loop 4 - AArch64 IntToBool Branch Fold

## Candidate

- Name: AArch64 `IntToBool + BranchZ/NZ` postalloc fold
- Status: `benefit-determined/needs-causality-before-review`
- Scope: LIR postalloc only, guarded by `CINDER_AARCH64`
- Changed file: `cinderx/Jit/lir/postalloc.cpp`
- Remote baseline: `/root/work/cinderx-jit28-base-gcc14`
- Remote candidate source: `/root/work/inttobool_branch_20260519_222446_src`
- Remote candidate workdir: `/root/work/inttobool_branch_20260519_222446_work`
- Compiler: GCC 14.3.0 on `root@113.44.53.223`

## Core Idea

When a conditional branch consumes the last use of a value produced by `IntToBool`, AArch64 can branch directly on the original 32-bit, 64-bit, or object register with `cbz/cbnz`. This removes the intermediate boolean materialization shape:

- Before: integer/object register -> `cmp #0` + `cset bool` -> branch on bool
- After: integer/object register -> `cbz/cbnz`

The optimization is intentionally AArch64-only. x86 is not changed in this candidate.

## Code Causal Chain

- HIR/LIR generation can emit `Instruction::kIntToBool` for integer-to-boolean conversion.
- AArch64 `translateIntToBool()` currently lowers this as `cmp input, #0; cset output, ne`.
- `doRewriteCondBranch()` in postalloc rewrites `CondBranch` to `BranchZ`/`BranchNZ`.
- This candidate adds an AArch64-only peephole before the default branch rewrite:
  - branch input must be a register and last-use;
  - previous instruction must be `kIntToBool`;
  - the `IntToBool` output physical register must match the branch input;
  - the `IntToBool` source must be a 32-bit, 64-bit, or object register;
  - the branch receives the original source operand and the `IntToBool` instruction is removed.
- Verifier boundary is already compatible with two-input AArch64 `BranchZ/NZ` for 32-bit, 64-bit, and object registers.
- x86 remains on the existing path because the peephole is inside `#if defined(CINDER_AARCH64)`.

## Benchmark Evidence

### Baseline Snapshot

Artifact: `/root/work/arm-sync/loop_run_20260519_221049`

S3 object medians:

| Benchmark | Baseline median |
|---|---:|
| chaos | 0.080208023 |
| deltablue | 0.004336543 |
| go | 0.137967196 |
| nqueens | 0.164353221 |
| raytrace | 0.394916533 |
| richards | 0.058179760 |

S3 scimark medians:

| Benchmark | Baseline median |
|---|---:|
| scimark_fft | 0.501053332 |
| scimark_lu | 0.180974694 |
| scimark_monte_carlo | 0.086334061 |
| scimark_sor | 0.162683960 |
| scimark_sparse_mat_mult | 0.006612660 |

### Candidate S3

Valid artifact: `/root/work/arm-sync/loop_run_inttobool_branch_20260519_230030`

Invalid artifact: `/root/work/arm-sync/loop_run_inttobool_branch_20260519_225905`

Invalid reason: script was invoked without `cd "$WORKDIR"`, so pyperformance used the wrong venv path. Do not use this run as evidence.

| Benchmark | Time delta |
|---|---:|
| chaos | -3.763% |
| deltablue | -14.482% |
| go | -8.491% |
| nqueens | -24.036% |
| raytrace | -9.453% |
| richards | -7.070% |
| scimark_fft | -3.753% |
| scimark_lu | -5.028% |
| scimark_monte_carlo | -1.620% |
| scimark_sor | -6.747% |
| scimark_sparse_mat_mult | -8.050% |

Focused 11-row time geomean: about `-8.615%`

Focused 11-row speedup: about `+9.428%`

### Candidate S12

Artifact: `/root/work/arm-sync/loop_run_inttobool_branch_s12_20260519_230310`

| Benchmark | Baseline median | Candidate median | Time delta |
|---|---:|---:|---:|
| chaos | 0.0823561235 | 0.0772342535 | -6.219% |
| deltablue | 0.0044032675 | 0.0037123350 | -15.691% |
| go | 0.1362344710 | 0.1266556285 | -7.031% |
| nqueens | 0.1655047660 | 0.1249523355 | -24.502% |
| raytrace | 0.3940234975 | 0.3581063015 | -9.115% |
| richards | 0.0578705270 | 0.0544761010 | -5.866% |
| scimark_fft | 0.4891389090 | 0.4790206225 | -2.069% |
| scimark_lu | 0.1825099990 | 0.1723455575 | -5.569% |
| scimark_monte_carlo | 0.0859673215 | 0.0852084940 | -0.883% |
| scimark_sor | 0.1622965045 | 0.1517067945 | -6.525% |
| scimark_sparse_mat_mult | 0.0066019155 | 0.0060834250 | -7.854% |

Focused 11-row time geomean: about `-8.534%`

Focused 11-row speedup: about `+9.330%`

Object-only time geomean: about `-11.675%`

Object-only speedup: about `+13.218%`

Scimark-only time geomean: about `-4.617%`

Scimark-only speedup: about `+4.840%`

### Full JIT28 S3

Artifact: `/root/work/arm-sync/inttobool_branch_jit28_s3_20260519_235714`

Summary files:

- `/root/work/arm-sync/inttobool_branch_jit28_s3_20260519_235714/merged_jit28_s3_summary.md`
- `/root/work/arm-sync/inttobool_branch_jit28_s3_20260519_235714/merged_jit28_s3_summary.json`

The full JIT28 run is valid as 28 rows:

- 20 non-scimark/non-logging rows from `compare_non_scimark_s3.json`
- 3 logging rows from `compare_logging_s3.json`
- 5 scimark rows from `compare_scimark_s3.json`

Full JIT28 S3 aggregate:

- time geomean delta: `-8.844%`
- speedup: `+9.702%`
- rows faster by at least 5% speedup: `18/28`
- slower rows: `2/28`, both tiny rows: `pickle -1.379% speedup`, `pickle_dict -0.296% speedup`

Rows over the single-benchmark 30% speedup threshold in S3:

| Benchmark | Baseline median | Candidate median | Time delta | Speedup |
|---|---:|---:|---:|---:|
| comprehensions | 0.0000537230225746 | 0.0000404720194638 | -24.665% | +32.741% |
| coroutines | 0.0455663199828 | 0.0320661639853 | -29.627% | +42.101% |
| nqueens | 0.164363087009 | 0.125104890991 | -23.885% | +31.380% |

Other notable rows:

| Benchmark | Time delta | Speedup |
|---|---:|---:|
| generators | -15.951% | +18.978% |
| deltablue | -15.891% | +18.894% |
| logging_format | -14.441% | +16.879% |
| logging_simple | -13.929% | +16.183% |
| nbody | -11.155% | +12.556% |
| raytrace | -10.372% | +11.572% |
| json_dumps | -9.518% | +10.519% |

Decision after S3:

- S3 crosses the single-benchmark 30% speedup threshold, but the stop condition requires trusted repeat evidence.
- Full JIT28 geomean speedup is close to, but still below, the 10% threshold.
- S12 full JIT28 repeat has started automatically in the same artifact directory.

### Full JIT28 S12

Artifact: `/root/work/arm-sync/inttobool_branch_jit28_s3_20260519_235714`

Summary files:

- `/root/work/arm-sync/inttobool_branch_jit28_s3_20260519_235714/merged_jit28_s12_summary.md`
- `/root/work/arm-sync/inttobool_branch_jit28_s3_20260519_235714/merged_jit28_s12_summary.json`

The S12 repeat is valid as 28 rows:

- 20 non-scimark/non-logging rows from `compare_non_scimark20_s12.json`
- 3 logging rows from `compare_logging_s12.json`
- 5 scimark rows from `compare_scimark_s12.json`

Full JIT28 S12 aggregate:

- time geomean delta: `-9.145%`
- speedup: `+10.065%`
- rows faster by at least 5% speedup: `20/28`
- rows with >=5% regression: `0/28`
- only slower row: `unpack_sequence -1.173% speedup`, tiny absolute-time row

Rows over the single-benchmark 30% speedup threshold in S12:

| Benchmark | Baseline median | Candidate median | Time delta | Speedup |
|---|---:|---:|---:|---:|
| comprehensions | 0.0000521670008311 | 0.0000401069992222 | -23.118% | +30.070% |
| coroutines | 0.0454894890136 | 0.0320944590057 | -29.446% | +41.736% |
| nqueens | 0.165356582991 | 0.125173445005 | -24.301% | +32.102% |

Decision after S12:

- Performance stop condition is triggered by repeated evidence:
  - full JIT28 geomean speedup is `+10.065%`, crossing the `>=10%` gate;
  - repeated JIT28 single rows cross `>=30%` speedup.
- Because the benefit is determined, the candidate must move immediately from search to causality evidence collection.
- Review/reporting is blocked until real-workload peephole hit evidence, a lightweight counter, or LIR/ASM census proves this peephole is responsible for the win.

## Diagnostic Evidence

- `/root/work/arm-sync/loop_run_inttobool_branch_lir_20260519_231000`: pyperformance LIR/ASM dump on `nqueens` timed out and was killed. Do not use as evidence.
- `/root/work/arm-sync/loop_run_inttobool_branch_lir_micro_20260519_234100`: unittest dump timed out and was killed. Do not use as evidence.
- `/root/work/arm-sync/loop_run_inttobool_branch_lir_micro3_20260519_235000`: static list-truthiness probe compiled, but it did not hit `IntToBool`; it already lowered to direct `BranchNZ` from list size. Use only as negative probe evidence.

## Current Interpretation

The performance evidence is now strong enough to stop broad search and require immediate causality evidence:

- full JIT28 S12 geomean speedup is `+10.065%`;
- repeated JIT28 rows over `>=30%` speedup are `comprehensions`, `coroutines`, and `nqueens`;
- direct LIR/ASM or counter evidence for real-workload peephole hits is still missing.

## Next Automatic Actions

1. Because the benefit is determined, add a low-cost hit-count mechanism for this peephole or find a reliable real workload LIR census method that does not dump full pyperformance logs.
2. Run the diagnostic-only focused/full workloads needed to prove the peephole fires in the rows that improved.
3. Do final code review for AArch64 boundary, verifier contract, and x86 non-change only after the causality gate is complete.
4. Prepare final report/merge decision with both the S12 artifact and the causality evidence.
