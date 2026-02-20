# Progress Log: ARM JIT Performance Iteration 2026-02-19

## 2026-02-19

- Confirmed active working repo is `d:/code/cinderx-upstream-20260213` (`arm-jit-perf`, `778d01d0`).
- Loaded required process skills for this session:
  - `using-superpowers`
  - `planning-with-files`
  - `brainstorming`
  - `writing-plans`
  - `test-driven-development`
  - `verification-before-completion`
- Verified only `findings.md` existed; created `task_plan.md` and this `progress.md`.
- Scanned current AArch64 call emission state:
  - helper-stub dedup path active in `gen_asm_utils.cpp` and `gen_asm.cpp`
  - remaining direct `mov/blr` patterns mostly in global trampolines (`gen_asm.cpp`) and dynamic register calls.
- Session catchup script failed on host policy (`python.exe` inaccessible); recovery handled manually.
- Re-ran strict A/B deployment on ARM host for:
  - `bench-prev-392245ed`
  - `bench-cur-7c361dce`
- Both A/B deployments completed build + ARM runtime smoke (`Ran 4 tests ... OK`).
- Collected repeated `richards` samples (`n=6`) for both `jitlist` and `autojit=50`, and wrote aggregate comparison to:
  - `/root/work/arm-sync/ab_compare_392245ed_vs_7c361dce.json`
- Added an explicit JIT-effect cross-check (`nojit` vs `jitlist`, `n=5`) on current commit:
  - `/root/work/arm-sync/jit_effect_nojit_vs_jitlist_7c361dce_summary.json`
  - `/root/work/arm-sync/jit_effect_nojit_vs_jitlist_7c361dce_robust.json`
- Added direct code-size A/B check for the call-heavy regression shape:
  - prev `392245ed`: `71616` bytes
  - cur `7c361dce`: `71600` bytes
- Updated `findings.md` with:
  - from -> to metrics (mean/median/CI)
  - robust statistics for outlier sensitivity
  - theory analysis mapping code change scope to observed effect size
- Ran extended benchmark matrix on current commit (`7c361dce`) across:
  - `richards`, `nbody`, `deltablue`
  - modes: `nojit` vs `jitlist`
  - n=5 each
- Added a noise-controlled interleaved A/B for `richards`:
  - 10 paired runs (`nojit` then `jitlist` per pair)
  - result is near parity (`mean -0.165%`, CI crosses zero)
- Recorded both artifacts and interpretations in `findings.md`.
- Added richer analysis beyond single benchmark JSON deltas:
  - richards compiled-function size ranking (`get_compiled_functions()` +
    `get_compiled_size()`)
  - richards top-function HIR opcode composition
- Added steady-state in-process benchmark comparison (`nojit` vs `autojit50` vs
  forced-jitlist), showing substantial warm-loop JIT speedup.
- Added separate-process toggle checks (`inliner`, specialized opcodes,
  type-annotation guards), confirming current default config is best among these
  obvious switches for richards.
- Added `pyperformance --fast` caution section to distinguish cold-start vs
  steady-state behavior on this host.

## 2026-02-20

- Loaded and followed required process skills for this iteration:
  - `using-superpowers`
  - `brainstorming`
  - `writing-plans`
  - `test-driven-development`
  - `verification-before-completion`
- Completed brainstorming confirmation for strict 1->2->3 optimization flow.
- Captured design to:
  - `docs/plans/2026-02-20-arm-vs-x86-richards-optimization-design.md`
- Captured implementation plan to:
  - `docs/plans/2026-02-20-arm-vs-x86-richards-optimization-plan.md`
- Updated task plan for new iteration target:
  - ARM vs X86 richards with ARM >= 3% faster target.
- Environment discovery:
  - ARM host `124.70.162.35`: `/root/venv-cinderx314` exists.
  - X86 host `106.14.164.133`: `/root/venv-cinderx314` missing.
