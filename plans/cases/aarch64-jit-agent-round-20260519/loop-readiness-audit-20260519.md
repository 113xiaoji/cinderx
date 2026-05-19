# AArch64 JIT Agent 循环可运行性审计 2026-05-19

## 问题

这套 markdown 之前没有真正“转起来”，主要原因不是缺少角色，而是角色和流程被写成了一次性审计：

1. `README.md` 的标准流程先要求启动只读 Agent，并把 Perf Evidence 也放进只读语境。
   结果 Perf Agent 容易只审历史 JSON，不实际跑 benchmark。
2. Orchestrator Agent 的职责是“决定继续搜索、重复验证、否决，还是汇报”，但没有硬性规定
   未触发停止条件时必须继续下一轮。
3. Analysis Agent 只要求找 pattern 和排序候选，没有要求消费 benchmark snapshot、LIR/ASM census
   和历史 rejected 去重，所以容易只输出静态建议。
4. Implementation Agent 不能写成“每轮都等用户批准”；在循环语境里，Orchestrator 选定候选后应自动实现实验 patch，
   只有越界、高风险或改变 harness 口径时才请示用户。
5. Perf Evidence Agent 写成“定位或运行证据”，没有规定它就是正式 benchmark 执行者，
   也没有明确 baseline/candidate A/B 的升级 gate。
6. Case template 是线性 phase，而不是 Loop N。Phase 5 写成 final report，容易让每轮都像
   结束流程。
7. `cinderx/AGENTS.md` 入口仍然写着“运行或模拟这些只读 Agent”，没有把连续循环作为默认行为。
8. 仓库根目录没有 `AGENTS.md`，从 `C:\work\code\cinderx6` 进入时没有强触发入口。

## 修改

已把 workflow 改成连续循环：

- `docs/agents/aarch64-jit-perf/README.md`
  - 新增“连续循环协议”。
  - 明确 Perf Evidence Agent 是 benchmark 执行者。
  - 明确未触发停止条件时必须进入下一轮。
- `docs/agents/aarch64-jit-perf/orchestrator-agent.md`
  - 明确 Orchestrator 负责驱动 benchmark、候选选择、实现、复测、记录、继续。
- `docs/agents/aarch64-jit-perf/perf-evidence-agent.md`
  - 明确必须用 `scripts/arm/run_pyperf_subset.sh` 和 `compare_pyperf_subset.py`。
  - 增加 snapshot -> S3 -> S12 -> full JIT28 gate。
- `docs/agents/aarch64-jit-perf/analysis-agent.md`
  - 明确必须读取 benchmark snapshot / compare / LIR/ASM/census。
  - 明确输出可执行候选队列，而不是只给建议。
- `docs/agents/aarch64-jit-perf/implementation-agent.md`
  - 明确 Orchestrator 选定即可自动实现实验 patch。
  - 只有越界、高风险或改变 harness 口径时才请示用户。
- `docs/agents/aarch64-jit-perf/debug-agent.md`
  - 明确一次失败不能终止整个循环。
- `docs/agents/aarch64-jit-perf/review-agent.md`
  - 明确 Review 只用于 accepted/汇报/合入 gate。
- `docs/agents/aarch64-jit-perf/case-template.md`
  - 从线性 phase 改成 Loop N。
  - 增加 benchmark snapshot、候选实现、记录和继续。
- `docs/agents/aarch64-jit-perf/prompts.md`
  - 增加 Continuous Loop Driver prompt。
  - 更新 Analysis、Perf、Implementation、Debug、Review prompt。
- `cinderx/AGENTS.md`
  - 入口改成连续优化循环，不再把 Perf Evidence 当只读 Agent。
- `AGENTS.md`
  - 新增仓库根入口，确保从 repo root 进入时也能触发连续循环。

## 当前剩余注意点

- `docs/agents/aarch64-jit-perf` 目录当前是 untracked，需要后续按你的提交策略决定是否纳入提交。
- 当前工作区还有多处历史 dirty C++ 文件，其中不少是行尾噪音；做候选 patch 时必须避免把无关 diff 带入。
- 正式性能数据仍必须按 `docs/pyperformance-cinderx-integration.md` 和脚本方法跑。
