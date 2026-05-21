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
  candidates/
    index.md
    <loop>-<candidate>/
      case.md
      candidate.patch
  final-report.md
```

中文记录规则：除代码符号、命令、路径、benchmark 名称和状态 tag 外，所有 case
结果、状态解释、收益判断、否决原因、合入判断和下一步动作都必须用中文记录。

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
- local patch archive：
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
- [ ] 保存本地候选归档到 `candidates/<loop>-<candidate>/`
- [ ] 确认候选目录内同时包含 `case.md` 和 `candidate.patch`
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
- [ ] 有比较明确的 ARM 收益后，如另一台 ARM 可用，做同口径补充验证
- [ ] 第二台 ARM 确认类似趋势收益后，再进入 x86 对照；ARM 收益不明确时不做 x86

### Loop N：记录和继续

- [ ] 分类 accepted/needs-repeat/mechanism-only/rejected/blocked
- [ ] 更新 findings/progress/benchmark-matrix
- [ ] 如果未触发停止条件，选择下一轮候选或下一轮 benchmark snapshot

### Final：复查和汇报

- [ ] 确认确定收益后的 causality/workload 命中证据已经补齐
- [ ] 如另一台 ARM 可用，已完成补充趋势验证；不可用时已中文记录 blocker
- [ ] Review Agent 已检查方案泛化性、后置 x86 对照和 ARM/x86 收益边界；只有 ARM
      收益明确后才要求 x86 最小实现、标准测试和中文 case 记录
- [ ] 所有 case 结果、状态解释、收益判断、否决原因和合入判断均已用中文记录
- [ ] 如果所有合入前准备已完成，状态记录为 `ready-for-human-review`
- [ ] 分类最终状态
- [ ] 编写 final report
- [ ] 判断 commit/PR 是否就绪
```

## findings.md

```markdown
# <Case Name> Findings

## 最新整体进展

## 候选表

| 候选 | Loop | 命中 pattern | 文件 | 本地 Patch | 核心思路 | ARM 依据 | x86 gate 状态 | Benchmark | LIR/ASM | 状态 |
|---|---:|---|---|---|---|---|---|---|---|---|

## 代码因果链

## LIR / ASM 证据

| Artifact | 阶段 | 统计规则 | 路径 | 结果 |
|---|---|---|---|---|

## Benchmark 证据

| Run | Baseline | Candidate | Samples | 结果 | 分类 |
|---|---|---|---|---|---|

## Patch 归档

| Loop | 候选 | 本地 Patch | 状态 |
|---:|---|---|---|

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
- 本地 patch：
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
| 1 | <candidate> | second ARM trend | ARM 收益明确且环境可用时必需 | pending | | | | |
| 1 | <candidate> | x86 after ARM confirmed | ARM 收益明确后才评估 | pending | | | | |
```

## candidates/index.md

```markdown
# <Case Name> 候选归档

本目录按候选拆分。每个候选目录包含：

- `case.md`：候选方案、测试记录、结论和后续动作。
- `candidate.patch`：可恢复该候选代码的本地 patch。

| Loop | 候选 | 目录 | Case | Patch |
|---:|---|---|---|---|
```

## candidates/<loop>-<candidate>/case.md

```markdown
# <Loop> - <Candidate>

- Patch: `candidate.patch`
- 归档目录: `candidates/<loop>-<candidate>/`
- 状态标签：
- 记录语言：中文；代码符号、命令、路径、benchmark 名称和状态 tag 可保留原文

## 方案简介

## 方案泛化性

- 这个方案优化的是哪一类语义、LIR、codegen 或 helper-call 形态：
- 为什么不是单个 benchmark 特例：
- 触发条件：
- fallback 边界：

## ARM 亲和依据

- ARM 为什么更可能收益：
- 命中的 ARM/x86 差异 pattern：
- workload 命中证据或需要补的证据：

## 第二台 ARM 补充验证

- 是否进入补充验证：
- 进入原因：
- 环境：
- baseline/candidate artifact：
- 趋势是否相近：
- 如果未验证，原因或 blocker：

## x86 收益判断

- 是否进入 x86 gate（只有 ARM 收益明确后才进入）：
- x86 是否可能也有收益：
- 如果不可能或不应影响 x86，原因：
- 如果可能收益，x86 实验 patch/enable：
- x86 correctness gate：
- x86 benchmark artifact：
- x86 结论和标签：
- 如果只有 x86 收益、ARM 趋势不成立，是否已标记为 `x86-only-benefit`：

## 正确性测试

## Benchmark 证据

## 合入判断

- 是否合入：
- 是否 ARM-only：
- 是否需要禁止或关闭 x86：
- 仍缺什么证据：
- 是否已到 `ready-for-human-review`：
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
