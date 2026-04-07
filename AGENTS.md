# AGENTS.md

本仓库当前有一个正在进行中的专项 case：`issue85-object-heavy-osr-profitability`。

工作约定：

- `#76` 的 Phase 1 MVP 主线已经完成，新的运行时代码工作默认视为 `#85` follow-up。
- `#85` 的事实源优先级：
  - `plans/cases/issue85-object-heavy-osr-profitability/`
  - `plans/2026-03-31-issue76-hot-loop-osr/`
  - 根目录 `findings.md`
- 远端验证入口统一使用：
  - `scripts/push_to_arm.ps1`
  - `scripts/arm/remote_update_build_test.sh`
- 不要把 pyperformance 端到端噪音直接当成 correctness 结论。
- 先做分析和计划，再做实现；先做定向验证，再宣称收益或回退。
- 对 `go` / `chaos` 这类 object-heavy / search-heavy case，优先按 shape/profitability 处理，不做 benchmark 名称特判。

如果修改 `cinderx/` 下代码，仍需遵守 [cinderx/AGENTS.md](C:/work/code/cinderx1/cinderx/cinderx/AGENTS.md) 中已有约束。
