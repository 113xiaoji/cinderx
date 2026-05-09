# ARM LIR/CODEGEN Indexed Memory Design

## Goal

Improve the ARM/AArch64 JIT28 benchmark set using only LIR and CODEGEN
changes. The first implementation candidate is AArch64 indexed memory
lowering. Stop only when at least one large-grain JIT28 row has a confirmed
30% single-row speedup, or the full JIT28 concrete-row geomean has a confirmed
10% speedup.

## Scope

Allowed production areas:

- `cinderx/Jit/lir/*`
- `cinderx/Jit/codegen/*`

The first candidate should modify CODEGEN only unless a narrow LIR test helper
is required. Do not use HIR, runtime tier policy, call admission, retained
object paths, or benchmark method changes as optimization sources.

## Benchmark Method

Use the ARM host `root@124.70.162.35`. The method follows
`docs/pyperformance-cinderx-integration.md`:

- build the exact checkout under test
- use the driver venv and pyperformance worker venv
- inject `scripts/arm/pyperf_env_hook/sitecustomize.py`
- inherit JIT environment into workers
- use `SAMPLES=5` for decision data
- record row median/min/max and geomean

The JIT28 textual filter list is:

```text
richards,go,deltablue,raytrace,nqueens,generators,coroutines,comprehensions,unpack_sequence,chaos,logging,coverage,nbody,spectral_norm,scimark,float,fannkuch,pickle,pickle_dict,pickle_list,json_dumps,json_loads
```

`logging` and `scimark` expand to 28 concrete rows. Geomean decisions must use
the concrete rows present in the JSON summaries.

## Candidate Ranking

1. AArch64 indexed memory operand lowering.
   Current `ptrIndirect()` computes `base + index << scale` into a scratch
   register, then emits a load or store from that scratch address. AArch64 can
   encode common indexed loads and stores directly when the scale matches the
   access width, saving one `add` and one scratch dependency per memory access.

2. LIR compare-result branch fusion.
   Single-use compare results feeding `CondBranch` can avoid materializing a
   boolean register and then testing it. This is promising but touches LIR
   control-flow rewrites and should follow the narrower CODEGEN candidate.

3. AArch64 negative immediate canonicalization.
   Convert encodable negative add/sub/compare immediates to the opposite
   instruction form where appropriate. This is low risk but likely too small to
   satisfy the stop condition alone.

Rejected for the next iteration: the near-deopt guard branch trial. Its first
ARM A/B showed `geomean_speedup_pct = -0.4232840449504005` over the 8-row
high-signal subset, with best single row `nqueens +2.296%`, so it is not
counted as an optimization.

## Indexed Memory Design

Add an AArch64-only helper near `ptrIndirect()` that can return a direct
register-offset `a64::Mem` for load/store operations.

Rules:

- Use direct indexed addressing only when the `MemoryIndirect` has an index
  register.
- Allow offset-free forms first: `[base, index]` and
  `[base, index, lsl #sizeshift]`.
- Use the current scratch-address fallback for unsupported forms.
- A scaled form is legal only when the LIR multiplier equals the load/store
  access-size shift: 0 for 8-bit, 1 for 16-bit, 2 for 32-bit, and 3 for
  64-bit/object/double.
- Pass access size from the load/store operand type rather than guessing in
  `ptrIndirect()`.
- Preserve current behavior for `Lea`, stack slots, absolute memory, and
  non-AArch64 targets.

Expected code evidence:

- 64-bit indexed load/store with offset 0 emits one fewer address-calculation
  instruction.
- Unsupported scales and nonzero offsets continue through the old
  `leaIndex()` plus `ptr_resolve()` path.

## Verification

Correctness:

- Run the focused LIR ABI/codegen test that covers scaled indexed move loads
  and stores.
- Run the ARM remote entrypoint with smoke validation.

Performance:

- Compare against a clean baseline without the rejected guard candidate.
- First run the high-signal subset:

```text
richards,deltablue,nqueens,comprehensions,unpack_sequence,go,raytrace,generators
```

- If a row reaches or approaches 30%, rerun the same row/subset and record
  hotspot compilation evidence.
- If the subset does not satisfy the stop condition, continue with the next
  ranked candidate.
- Once a candidate appears to satisfy the stop condition, run the full JIT28
  concrete-row comparison and classify the result using the integration guide.

