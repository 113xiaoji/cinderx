# Task Plan: Issue 76 热循环 OSR 可行性研究

## Goal

- 基于当前 CinderX 3.14 实现，完成“基于热循环的 OSR（On-Stack Replacement）”现状梳理、业界对比、候选方案评估和推荐设计。

## Workflow

1. Brainstorming
2. Writing-Plans
3. Test-Driven-Development
4. Verification-Before-Completion

## Remote Test Entry

- 统一远端入口：
  - `scripts/push_to_arm.ps1`
  - `scripts/arm/remote_update_build_test.sh`

## Brainstorming Outcome

- 术语拆分：
  - 现有 CinderX 文档里的 “OSR” 实际上是 downward deopt。
  - 本 issue 里的 OSR 是 upward mid-frame entry。
- 备选方向：
  - A. 回边触发整函数编译，但下次调用才生效
  - B. 整函数编译 + loop header secondary entry
  - C. tracing JIT / side trace
- 推荐：
  - 选择 B 作为主方案；
  - A 作为低风险退路；
  - C 不进入 3.14 MVP。

## Writing-Plans Outcome

- 主交付文档：
  - `plans/2026-03-31-issue76-hot-loop-osr/deliverable.md`
- 计划已覆盖：
  - 当前现状
  - 问题定义
  - 业界对比
  - 候选方案
  - 推荐方案
  - 模块改动清单
  - Phase 0 / 1 / 2
  - 风险与测试计划

## TDD Plan For Future Implementation

- Phase 0 先写：
  - OSR metadata 构造测试
  - secondary entry 存在性测试
  - OSR-entered deopt round-trip 测试
- Phase 1 先写：
  - “函数只执行一次，但热循环中途进入 JIT”的 Python 回归
  - object-only `for` / `while` loop 回归
  - instrumentation / deopt 兼容性回归
- 远端验证统一通过：
  - `scripts/push_to_arm.ps1 -> scripts/arm/remote_update_build_test.sh`

## Verification Plan

- 本轮交付是设计文档，不修改 runtime 行为。
- 因此本轮验证目标是：
  - 文档结构完整；
  - 结论能落到具体代码路径；
  - 业界对比使用官方或一手资料；
  - 关键结论同步写入 `findings.md`。
- 后续任何 Phase 0/1 的可执行验证都必须走统一远端入口。

## Status

- [completed] Brainstorming
- [completed] Writing-Plans
- [completed] Test-Driven-Development
- [completed] Verification-Before-Completion

## Deliverables

- `plans/2026-03-31-issue76-hot-loop-osr/deliverable.md`
- `plans/2026-03-31-issue76-hot-loop-osr/findings.md`
- `plans/2026-03-31-issue76-hot-loop-osr/task_plan.md`
- `plans/2026-03-31-issue76-hot-loop-osr/phase0_plan.md`
- `plans/2026-03-31-issue76-hot-loop-osr/phase1_plan.md`

## Next Phase

- [completed] Phase 0 prototype landed and verified
- [completed] Phase 1 MVP slice agreed:
  - `JUMP_BACKWARD_JIT` 驱动
  - once-call hot loop
  - outermost / object-only / no generator or active exception region
- [in_progress] Phase 1 implementation planning
