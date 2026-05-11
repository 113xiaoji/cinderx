# AArch64 LoadAttrCache shared stub

## Goal

Reduce hot `LoadAttrCache::invoke` helper-call overhead on AArch64 without
changing HIR or LIR semantics. This keeps the optimization ARM-local while
preserving the original C++ helper as the fallback for every unsupported case.

## Design

`emitCall()` recognizes hot calls to `LoadAttrCache::invoke` and routes them
through an AArch64 shared stub when the call target is frequent enough. The
default threshold for this helper is `1`, with
`PYTHONJITAARCH64LOADATTRSTUBMINCALLS` available as an override.

The stub handles only the safe split-inline-values case:

- `x0=cache`, `x1=obj`, `x2=name` are preserved until a fast-path hit.
- Up to `min(attr_cache_size, 4)` attribute cache entries are scanned.
- The cached type must match `Py_TYPE(obj)`.
- The cache kind must be `kSplitInlineKnownOffset`.
- Inline values must still be valid and the slot must be non-null.
- The loaded value is incref'd and returned in `x0`.
- All misses tail-branch to the original `LoadAttrCache::invoke`.

This is intentionally implemented in codegen rather than HIR/LIR for the
initial merge because the fast path is AArch64-specific, depends on CPython
object layout and calling convention details, and is still easy to disable or
tune through the helper threshold.

## Verification

Remote target: `root@124.70.162.35`.

Build method:

- GCC 14: `/opt/toolchains/gcc-14.2.0`
- LTO on, PGO off
- `.md` runner: `/root/work/arm-sync/run_pyperf_subset_mdjit.sh`

Correctness smoke passed:

- `/root/work/arm-sync/loadattrstub_multientry_smoke_default_20260511.log`
- `/root/work/arm-sync/loadattrstub_multientry_polymorphic_smoke_20260511.log`
- `/root/work/arm-sync/loadattrstub_multientry_smoke_attrcachesize1_20260511.log`

Performance evidence:

- Focus S=3/W=3:
  `/root/work/arm-sync/loadattrstub_multientry_focus_s3w3_20260511_compare.txt`
- Repeat S=5/W=5:
  `/root/work/arm-sync/loadattrstub_multientry_repeat_s5w5_20260511_compare.txt`
- Full JIT28 S=3/W=3:
  `/root/work/arm-sync/loadattrstub_multientry_jit28_s3w3_20260511_compare.txt`

Full JIT28 compared with the clean GCC14 baseline:

- geomean: `+3.54%`
- `richards +26.49%`
- `deltablue +21.30%`
- `scimark_sor +17.13%`
- `comprehensions +12.31%`
- `raytrace +10.13%`
- `go +8.08%`
- `pickle_dict +7.43%`

Incremental comparison against the entry0-only LoadAttr stub showed the
multi-entry extension mainly helps `richards`:

- JIT28 geomean: `+0.50%`
- `richards +14.02%`

## Risk

The stub is deliberately narrow. Descriptor, combined dict, invalid inline
values, deleted slot, and unknown type cases all fall back to the original
helper. The main remaining risk is code-size and layout sensitivity from making
this helper's shared stub active at threshold `1`.
