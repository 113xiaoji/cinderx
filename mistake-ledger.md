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

## 2026-04-07

- 在 ARM 上做 `HEAD^ -> HEAD` A/B 时，没有先确保远端工作树和本地分支完全一致。
- 对 `comprehensions` 的小幅回退信号，起初没有先做 A/A 和更厚样本排除噪音。
- 之后的改进原则：
  - 先确认远端源码一致性
  - 先确认 `osr` 是否真的发生
  - 对小幅性能信号，先做 A/A 和厚样本
