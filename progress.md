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
- Added TDD baseline utilities/scripts:
  - `scripts/bench/richards_metrics.py`
  - `scripts/bench/test_richards_metrics.py`
  - `scripts/bench/run_richards_remote.sh`
  - `scripts/bench/collect_arm_x86_richards.ps1`
- RED/GREEN evidence:
  - initial tests failed due missing `richards_metrics` module and missing
    `validate_runner_payload`.
  - tests now pass (`Ran 4 tests ... OK`).
- X86 host bootstrap and compatibility work:
  - installed CPython `3.14.3` to `/opt/python-3.14.3`,
  - recreated `/root/venv-cinderx314` on 3.14.3,
  - added `FT_ATOMIC_LOAD_PTR_CONSUME` fallback in `borrowed-3.14*` sources to
    support x86 host build.
- Ran unified collector:
  - `scripts/bench/collect_arm_x86_richards.ps1 -Samples 3`
  - produced combined summary:
    - `artifacts/richards/summary_arm_vs_x86_20260220_225757.json`
- Step 2 policy sweep completed via unified collector:
  - thresholds: `AutoJit=10/25/50/100`, `Samples=5`
  - confirmation: `AutoJit=10` vs `50`, `Samples=8`
  - generated `policy_autojit*.json` summaries in `artifacts/richards/`
- Step 2 conclusion:
  - observed ARM-side gain from `50 -> 10` is small and statistically
    inconclusive (`+0.4062%`, CI crosses 0)
  - kept default policy as-is and prepared to continue with Step 3 codegen work
- Deep-dive LIR dumps captured for `__main__:f` (math.sqrt shape) to inspect
  call/decref hot-path interactions before next codegen attempt.

## 2026-02-21

- Pulled interrupted remote artifact:
  - `artifacts/richards/arm_mcs1_richards.json`
- Ran `multiple_code_sections` confirmation sweep on ARM host with higher
  sample count:
  - `PYTHONJITMULTIPLECODESECTIONS=0`, `SAMPLES=8`, output
    `/tmp/arm_mcs0_richards_s8.json`
  - `PYTHONJITMULTIPLECODESECTIONS=1`, `SAMPLES=8`, output
    `/tmp/arm_mcs1_richards_s8.json`
- Synced new artifacts to repo:
  - `artifacts/richards/arm_mcs0_richards_s8.json`
  - `artifacts/richards/arm_mcs1_richards_s8.json`
- Added aggregate compare output:
  - `artifacts/richards/mcs_compare_summary_20260221.json`
- Updated `findings.md` with from->to and CI:
  - `jitlist`: `0.0519003826 -> 0.0517930794 s` (`+0.2072%`, CI crosses 0)
  - `autojit50`: `0.0519645600 -> 0.0518082064 s` (`+0.3018%`, CI crosses 0)
- Decision:
  - keep `multiple_code_sections` out of Step 3 primary path for now and
    continue on call-lowering/register/branch hot-path work.
- Implemented Step 3 code change in `cinderx/Jit/lir/regalloc.cpp`:
  - AArch64 return-register preference for call outputs in short immediate
    call-chain pattern (`call -> single immediate use -> call(arg0=...)`).
- Systematic debugging loop during this change:
  - Attempt A (broad call-output hint) caused code-size regression and ARM
    runtime failures (`size200` jumped to `85160`).
  - Attempt B (FP-only hint) removed regression but showed weak gains.
  - Attempt C (current short-chain heuristic) preserved code size/tests and
    gave small autojit uplift in repeated runs.
- Verification on ARM host:
  - wheel rebuild + reinstall passed
  - `test_arm_runtime.py`: `5/5` pass
  - code-size probe: `size1=760`, `size2=1144`, `delta=384`, `size200=77160`
- Performance artifacts added:
  - `artifacts/richards/arm_after_regalloc_callchain_hint_mcs0_s8.json`
  - `artifacts/richards/arm_after_regalloc_callchain_hint_mcs0_s8_b.json`
  - `artifacts/richards/regalloc_callchain_hint_vs_baseline_mcs0_s8_summary.json`
  - `artifacts/richards/regalloc_callchain_hint_repeat_summary_20260221.json`
- Ran unified ARM/X86 collector after call-chain hint:
  - `scripts/bench/collect_arm_x86_richards.ps1 -Samples 5 -AutoJit 50`
  - combined summary:
    - `artifacts/richards/summary_arm_vs_x86_20260221_011223.json`
  - noted that this run's ARM-vs-X86 delta increase is mainly from x86-side
    variance; ARM absolute autojit mean remains near-flat.
- Tried a broader variant of the regalloc hint (map short-chain call output to
  actual `argN` ABI register, not only `arg0`) and validated correctness:
  - ARM rebuild + `test_arm_runtime.py` passed.
- Performance measurement for that wider variant was contaminated by external
  host load (`cargo/rustc` on ARM host), producing large cross-mode outliers.
- Reverted that wider variant to avoid keeping a non-validated optimization.
- Waited for ARM host load to return to idle, then reran stable short-chain
  (`arg0`) hint measurement:
  - `artifacts/richards/arm_after_regalloc_callchain_hint_mcs0_s8_clean2.json`
  - summary:
    - `artifacts/richards/regalloc_callchain_hint_vs_baseline_mcs0_s8_clean2_summary.json`
  - key result on clean rerun:
    - `autojit50`: `0.0519645600 -> 0.0516449700 s` (`+0.6188%`, CI positive)
- Added a new Step 3 micro-optimization candidate in postalloc
  (`retreg->tmp->argreg` fold) and evaluated via strict A/B deploy:
  - created isolated worktree `d:/code/cinderx-arm-eval`
  - baseline deploy (no postalloc fold) + remote smoke/tests passed
  - postalloc deploy + remote smoke/tests passed
- A/B benchmark artifacts (same runner/options on ARM):
  - baseline:
    - `artifacts/richards/arm_baseline_postalloc_ab_s8_clean_20260221_084809.json`
  - after:
    - `artifacts/richards/arm_postalloc_ab_s8_clean_20260221_085811.json`
  - summary:
    - `artifacts/richards/postalloc_hotpath_vs_baseline_s8_summary_20260221.json`
- Measured delta:
  - `jitlist`: `+0.0350%` (CI crosses 0)
  - `autojit50`: `+0.4555%` (CI positive)
- Ran unified ARM/X86 cross-host check after postalloc fold:
  - command:
    - `scripts/bench/collect_arm_x86_richards.ps1 -Samples 8 -AutoJit 50`
  - outputs:
    - `artifacts/richards/summary_arm_vs_x86_20260221_091757.json`
    - `artifacts/richards/arm_samples_20260221_091757.json`
    - `artifacts/richards/x86_samples_20260221_091757.json`
    - per-mode summaries:
      - `summary_nojit_20260221_091757.json`
      - `summary_jitlist_20260221_091757.json`
      - `summary_autojit50_20260221_091757.json`
- Cross-host `autojit50` snapshot:
  - ARM mean `0.0520960826 s`
  - X86 mean `0.1080564280 s`
  - ARM faster by `+51.7881%`
- Noted run-to-run tail noise on both hosts; kept ARM-only postalloc A/B as
  the primary micro-optimization evidence.
