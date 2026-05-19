# CinderX Agent 入口

## 入口规则

这是仓库根目录的轻量入口文件。不要在这里维护完整流程细节；复杂规则必须放到对应
agent 文档里。

涉及 CinderX ARM/AArch64 JIT 后端性能时，先读取：

- `docs/agents/aarch64-jit-perf/README.md`
- `docs/agents/aarch64-jit-perf/patterns.md`
- `docs/agents/aarch64-jit-perf/orchestrator-agent.md`
- `docs/agents/aarch64-jit-perf/perf-evidence-agent.md`
- `docs/agents/aarch64-jit-perf/analysis-agent.md`
- `docs/agents/aarch64-jit-perf/code-causal-chain-agent.md`
- `docs/agents/aarch64-jit-perf/implementation-agent.md`
- `docs/agents/aarch64-jit-perf/debug-agent.md`
- `docs/agents/aarch64-jit-perf/review-agent.md`

## 快速约束

- 入口文件只负责路由，不复制各 Agent 职责。
- AArch64 性能任务默认按连续优化循环推进。
- 基准测试由 Perf Evidence Agent 使用固定脚本执行。
- 一旦有确定收益，立即进入因果证据门，补工作负载命中证据、轻量计数器、
  LIR/ASM 统计或等价统计；完成前不进入最终复查/汇报。
- 未触发停止条件、用户暂停或明确阻塞时，继续下一轮。
