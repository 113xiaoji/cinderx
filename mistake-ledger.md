# Mistake Ledger

## 2026-04-11

- Mistook an empty summary for a pyperformance execution failure instead of a
  parser/schema mismatch.
- Forgot that remote helper workdirs are archive-backed, not git-backed, so any
  artifact field like `git_commit` needs explicit injection.

## 2026-04-07

- 在 ARM 上做 `HEAD^ -> HEAD` A/B 时，没有先确保远端工作树和本地分支完全一致。
- 对 `comprehensions` 的小幅回退信号，起初没有先做 A/A 和更厚样本排除噪音。
- 之后的改进原则：
  - 先确认远端源码一致性
  - 先确认 `osr` 是否真的发生
  - 对小幅性能信号，先做 A/A 和厚样本
