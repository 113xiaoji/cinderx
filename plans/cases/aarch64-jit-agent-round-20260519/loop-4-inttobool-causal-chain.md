# Loop 4 Causal Chain - AArch64 IntToBool Branch Fold

## What Generates the Shape

- HIR opcode: `CIntToCBool`
- LIR lowering: `cinderx/Jit/lir/generator.cpp`
  - `Opcode::kCIntToCBool` emits `Instruction::kIntToBool`.
  - The `IntToBool` input is the integer/object value, and its output is an 8-bit boolean value.

## Baseline LIR/Postalloc Shape

The baseline shape this candidate targets is:

```text
IntToBool bool_reg:8bit, src_reg:32bit|64bit|Object
CondBranch bool_reg
```

During postalloc, `CondBranch` is rewritten to a target branch:

- If the branch input can be used as a direct AArch64 register test, postalloc keeps a two-input `BranchZ/NZ`.
- Otherwise, postalloc emits a `Test` and rewrites the branch to a label-only `BranchZ/NZ`.

For an `IntToBool` result, the baseline AArch64 codegen materializes a boolean first:

```text
cmp src, #0
cset bool, ne
cbz/cbnz bool, target
```

The key problem is that the boolean materialization is redundant when the only consumer is an immediate conditional branch.

## Candidate Postalloc Rewrite

The candidate adds an AArch64-only peephole in `doRewriteCondBranch()`:

1. The branch condition input must be a register.
2. The branch condition input must be last-use.
3. The previous instruction must be `Instruction::kIntToBool`.
4. The `IntToBool` output physical register must match the branch condition physical register.
5. The `IntToBool` source must be a register of type `k32bit`, `k64bit`, or `kObject`.
6. The branch is rewritten to consume the original source register directly.
7. The `IntToBool` instruction is removed.

After the rewrite:

```text
BranchZ/BranchNZ src_reg:32bit|64bit|Object, target
```

## Expected AArch64 Assembly Change

Baseline:

```asm
cmp   xN, #0
cset  wM, ne
cbz   wM, target
```

Candidate:

```asm
cbz   xN, target
```

or:

```asm
cbnz  xN, target
```

This is ARM-friendly because AArch64 has dedicated compare-and-branch instructions for zero tests. It reduces instruction count and removes the temporary boolean value.

## x86 Boundary

x86 is not changed by this candidate:

- The entire peephole is inside `#if defined(CINDER_AARCH64)`.
- x86 `BranchZ/NZ` codegen only has label-only `jz/jnz` patterns.
- x86 already expresses integer truthiness efficiently as `test reg, reg; setne bool` if it needs a materialized boolean. A direct branch fusion would require a separate x86-specific LIR/codegen path and is not part of this ARM-first experiment.

## Verifier Boundary

`cinderx/Jit/lir/verify.cpp` allows two-input branches only on AArch64, and only for `BranchZ/BranchNZ` with a 32-bit, 64-bit, or object register input. The candidate stays within that existing invariant.

## Evidence Gap

Performance evidence is strong on the focused subset, but direct hit evidence is incomplete:

- Full pyperformance LIR/ASM dump timed out and was killed.
- A static list-truthiness probe did not generate the target `IntToBool` shape.
- The next diagnostic should be a low-cost hit counter or a small compile-time census that counts this peephole during compilation without dumping full LIR for pyperformance.

## Recommended Low-Cost Hit Evidence

Preferred diagnostic build:

1. Add an AArch64-only diagnostic counter in the peephole block.
2. Guard output behind an environment variable such as `PYTHONJITDUMPINTTOBOOLBRANCHFOLD=1`.
3. Print one aggregate count per process at exit or after compile, not per instruction.
4. Run the same focused benchmarks with the diagnostic build only.
5. Record:
   - total peephole hit count;
   - optional per-function or per-module top counts if cheap;
   - benchmark path and exact artifact.

This should be a diagnostic-only build, separate from performance A/B, because printing or atomics can perturb benchmark results.

## Current Classification

- Mechanism: plausible and AArch64-specific.
- Focused performance: strong and repeated.
- Full JIT28 performance: stop-condition hit in S12.
- Real-workload hit evidence: pending.
- Final state: `benefit-determined/needs-causality-before-review`.
- Rule: because the benefit is now determined, workload hit evidence, lightweight counter data,
  or LIR/ASM census is the immediate next gate before final review/reporting.
