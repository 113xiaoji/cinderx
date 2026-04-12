# Mistake Ledger

## 2026-04-11

- Mistook an empty summary for a pyperformance execution failure instead of a
  parser/schema mismatch.
- Forgot that remote helper workdirs are archive-backed, not git-backed, so any
  artifact field like `git_commit` needs explicit injection.

## 2026-04-11 Day 2

- Verified a helper fast-path with an environment override that also broke the
  build step (`PIP_NO_INDEX=1`), which obscured the actual target behavior.
- Set the first attr-heavy threshold from intuition instead of measured loop
  body counts, then had to tighten it after a clean red failure.
- Trusted a “baseline” direct benchmark result too early before checking the
  remote source file actually matched the intended baseline revision.
- Used a failing `unittest discover` invocation as if it were a runtime
  regression, when the failure was only in the test harness command.
- Kept the interpreter on the `JUMP_BACKWARD_JIT` path after a known skip
  decision was cached, which left a large residual tax on `raytrace`.
- Treated small 5-repeat benchmark deltas as actionable regressions too early,
  before doing a thicker 15-repeat confirmation pass.
- The inverse mistake is also real: a broad-pass negative should not be
  dismissed as noise until it has had at least one thicker confirmation pass.
- Once the broad regressions were confirmed, the right next move was to search
  for a common mechanism instead of treating each benchmark as an independent
  optimization problem.
- Used the stale `incoming` helper once the workdir helper had already diverged,
  which created a fake pyperformance/pip failure unrelated to the runtime
  candidate under test.
- Tried to read too much into `bm_go` before separating \"synthetic semantic
  diff is good\" from \"full benchmark path still has a broader CinderX crash\".
- Treated the installed current venv as if it were \"CinderX loaded but JIT
  off\" when in fact the JIT is enabled by default there.
- The first pass at narrowing the helper gate forgot to distinguish loop-backed
  helpers from attr-heavy non-loop leaf methods, which immediately showed up as
  broad ARM runtime failures.
- A small residual benchmark delta after a correctness-preserving narrowing pass
  is exactly the kind of signal that should get a thick-sample recheck before
  any more runtime changes.
- After the helper gate was stable, the next wrong move would have been to keep
  tightening scheduling policy. The suppression matrix showed the next
  generalized opportunity is on the compiled-path quality side instead.

## 2026-04-07

- 在 ARM 上做 `HEAD^ -> HEAD` A/B 时，没有先确保远端工作树和本地分支完全一致。
- 对 `comprehensions` 的小幅回退信号，起初没有先做 A/A 和更厚样本排除噪音。
- 之后的改进原则：
  - 先确认远端源码一致性
  - 先确认 `osr` 是否真的发生
  - 对小幅性能信号，先做 A/A 和厚样本
