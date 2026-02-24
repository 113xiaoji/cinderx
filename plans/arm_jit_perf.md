## Goal

Make CinderX JIT on ARM64 (aarch64) measurably faster, using the same official
`pyperformance` benchmarks we already gate with on the ARM box. Longer-term
goal is to be competitive with (and ideally exceed) x86_64 results after
normalizing for hardware and build config.

## Constraints / Ground Rules

- All performance tests and verification run via the repo's remote entrypoint:
  `scripts/push_to_arm.ps1` -> `scripts/arm/remote_update_build_test.sh`.
- Keep changes correct-first (no crashes / miscompiles).
- Avoid benchmarks that can silently skip JIT; always validate JIT is effective
  and that benchmark workers actually compile `__main__` code.

## Metrics

- Primary: `pyperformance` wall-clock for a representative subset:
  `richards` (first), then expand to `deltablue`, `nbody`, `json_dumps`,
  `regex_compile` / `regex_v8` depending on availability.
- Secondary:
  - JIT compilation time (from `PYTHONJITDEBUG` / JIT log).
  - Code size of compiled functions (via `cinderx.jit.get_compiled_size()` for
    targeted synthetic tests).

## Brainstorming (Candidates)

- AArch64 call emission:
  - Today `emitCall(funcptr)` uses `mov imm64` + `blr`, which expands to
    multiple `movz/movk` instructions per callsite.
  - Replace with `ldr literal` + `blr` by emitting a per-function literal pool
    (PC-relative) for call targets. This should reduce code size and instruction
    count for call-heavy code.
- AArch64 addressing:
  - Audit `ptr_resolve()` usage; avoid falling back to `mov offset` + indexed
    addressing when we can use scaled immediates.
- Regalloc / save-restore:
  - Verify we don't over-save callee-saves on aarch64; reduce prologue/epilogue
    overhead when possible.
- Inline caches:
  - Confirm attr cache fast paths are enabled and not regressing on aarch64.
- Code allocator:
  - Huge pages (`use_huge_pages`) behavior on ARM; validate it doesn't regress.

## Selected First Experiment: AArch64 Call Target Literal Pool

Implement aarch64-only fast path for `emitCall(funcptr)`:

- Maintain a map `funcptr -> Label` in `jit::codegen::Environ`.
- At each callsite:
  - `ldr x16, [label]` (PC-relative literal load)
  - `blr x16`
- After codegen, emit a literal pool (8-byte aligned) containing the function
  pointers and bind the labels.

Why this first:
- Low risk to correctness (no semantic change, just how we materialize address).
- Likely wins broadly because JIT code calls many runtime helpers.

## Plan (Closed Loop)

1. Add a targeted ARM-only regression test that fails today and should pass
   after the optimization:
   - Build a function with many repeated `math.sqrt()` callsites and assert its
     compiled code size is below a threshold.
2. Wire that test into the remote ARM gate script so failures are caught via
   the standard entrypoint.
3. Implement the call-target literal pool.
4. Re-run the remote gate:
   - Ensure JIT-effective smoke passes.
   - Ensure `pyperformance richards` jitlist + autojit pass and JIT log shows
     compilation of `__main__`.
5. Record results (before/after) in `findings.md`.

## Verification Checklist

- `scripts/push_to_arm.ps1 ... -Benchmark richards` succeeds.
- Remote script logs:
  - `jit-effective-ok` present.
  - JIT autojit log contains `Finished compiling __main__:...`.
- New ARM runtime test passes.
- `findings.md` updated with new benchmark JSON value(s) and commit hash.

