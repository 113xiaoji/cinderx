# Mistake Ledger

## 2026-04-07

- 不要把 wrapper pollution 和 object-heavy 主问题混成一个 heuristic 解决。
- 不要在 `osr_count == 0` 的 case 上过度归因到 same-activation OSR。
- 不要在远端工作树不一致的情况下解读 A/B 结果。
