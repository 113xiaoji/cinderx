# AArch64 JIT 性能优化 Case 模板

每个候选或优化搜索都创建一个新的 case 目录：

```text
plans/cases/<case-name>/
  agents.md
  plan.md
  findings.md
  progress.md
  code-causal-chain.md
  benchmark-matrix.md
  final-report.md
```

## agents.md

```markdown
# <Case Name> Agents

## 范围

- 目标：
- 范围内：
- 范围外：
- 停止条件：

## Agent 分工

| Agent | 负责角色 | Prompt 来源 | 状态 |
|---|---|---|---|
| Orchestrator | main thread | docs/agents/aarch64-jit-perf/README.md | active |
| Progress Audit | sub-agent | docs/agents/aarch64-jit-perf/prompts.md | pending |
| Analysis | sub-agent or main | docs/agents/aarch64-jit-perf/prompts.md | pending |
| Code Causal Chain | sub-agent | docs/agents/aarch64-jit-perf/prompts.md | pending |
| Perf Evidence | sub-agent | docs/agents/aarch64-jit-perf/prompts.md | pending |
| Implementation | main or worker | docs/agents/aarch64-jit-perf/prompts.md | blocked |
| Debug | main or sub-agent | docs/agents/aarch64-jit-perf/prompts.md | blocked |
| Review | sub-agent or main | docs/agents/aarch64-jit-perf/prompts.md | pending |
```

## plan.md

```markdown
# <Case Name> Plan

## 目标

## 当前已知上下文

- branch：
- base commit：
- candidate commit/patch：
- remote host：
- compiler/toolchain：

## 停止条件

- JIT28 单项提升 >= 30%
- full JIT28 geomean 提升 >= 10%
- 或用户明确暂停/停止

## 阶段

### Loop 0：初始化

- [ ] 读取 git status/log
- [ ] 读取 progress/findings/task_plan
- [ ] 分类已有候选
- [ ] 确认远端、GCC14、driver venv、workdir、脚本路径
- [ ] 创建本 case 的 findings/progress/benchmark-matrix

### Loop N：Benchmark snapshot

- [ ] 用 `scripts/arm/run_pyperf_subset.sh` 跑当前基线 focused S3
- [ ] 记录 JSON、log、manifest
- [ ] 如有历史 baseline，运行 compare

### Loop N：分析和代码因果链

- [ ] 识别 ARM/x86 差异
- [ ] 跟踪 HIR/LIR lowering
- [ ] 跟踪 postalloc/regalloc/codegen
- [ ] 记录 x86 边界
- [ ] 统计 LIR/ASM/census 形态
- [ ] 排序候选队列

### Loop N：实现一个候选

- [ ] Orchestrator 选择一个候选
- [ ] Implementation Agent 自动实现实验 patch
- [ ] 记录修改文件和因果假设
- [ ] 跑 correctness gate

### Loop N：focused 验证

- [ ] 运行 focused benchmark
- [ ] 收集 baseline JSON
- [ ] 收集 candidate JSON
- [ ] compare

### Loop N：重复和更大范围验证

- [ ] 如果 focused 有信号，运行 S12
- [ ] 如果 S12 仍可信，运行 full JIT28
- [ ] 收集 LIR/ASM 证据
- [ ] 一旦有确定收益或停止条件触发，立即补 workload 命中证据、轻量 counter、
      LIR/ASM census 或等价统计；完成前不进入最终 review/reporting

### Loop N：记录和继续

- [ ] 分类 accepted/needs-repeat/mechanism-only/rejected/blocked
- [ ] 更新 findings/progress/benchmark-matrix
- [ ] 如果未触发停止条件，选择下一轮候选或下一轮 benchmark snapshot

### Final：复查和汇报

- [ ] 确认确定收益后的 causality/workload 命中证据已经补齐
- [ ] 分类最终状态
- [ ] 编写 final report
- [ ] 判断 commit/PR 是否就绪
```

## findings.md

```markdown
# <Case Name> Findings

## 最新整体进展

## 候选表

| 候选 | Loop | 命中 pattern | 文件 | 核心思路 | ARM 依据 | x86 影响 | Benchmark | LIR/ASM | 状态 |
|---|---:|---|---|---|---|---|---|---|---|

## 代码因果链

## LIR / ASM 证据

| Artifact | 阶段 | 统计规则 | 路径 | 结果 |
|---|---|---|---|---|

## Benchmark 证据

| Run | Baseline | Candidate | Samples | 结果 | 分类 |
|---|---|---|---|---|---|

## 循环队列

| 优先级 | 候选 | 下一动作 | 负责 Agent | 阻塞项 |
|---:|---|---|---|---|

## 噪声 / Tiny 行

## 已否决假设

## 缺失证据

## 最终分类
```

## progress.md

```markdown
# <Case Name> Progress

## YYYY-MM-DD

- Loop：
- 发生了什么：
- 运行的 benchmark：
- 收集到的证据：
- 错误：
- 候选状态变更：
- 下一步最小动作：
```

## benchmark-matrix.md

```markdown
# <Case Name> Benchmark Matrix

| Loop | 候选 | 层级 | 是否必需 | 状态 | Baseline | Candidate | Compare | 结论 |
|---:|---|---|---|---|---|---|---|---|
| 0 | baseline | focused S3 snapshot | 是 | pending | | | | |
| 1 | <candidate> | correctness | 是 | pending | | | | |
| 1 | <candidate> | focused S3 | 是 | pending | | | | |
| 1 | <candidate> | focused S12 | S3 有信号时必需 | pending | | | | |
| 1 | <candidate> | full JIT28 S12 | accepted/汇报前必需 | pending | | | | |
```

## final-report.md

```markdown
# <Case Name> Final Report

## 最新整体进展

## 当前最强候选

## 代码因果链

## 测试证据

## 决策

## 下一轮动作
```
