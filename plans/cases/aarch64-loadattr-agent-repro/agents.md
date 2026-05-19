# AArch64 LoadAttr Agent 复现 Agents

## 目标

通过 harness 风格的多 Agent 工作流，复现 AArch64
`LoadAttrCachedFastPath` / `LoadAttrCache::invoke` 优化。

范围只限 ARM/AArch64 JIT 后端性能：LIR、CODEGEN、postalloc、regalloc、
LIR/ASM 证据和 benchmark 验证。除非 HIR 改动直接服务于后端证据收集，否则不在
本 case 范围内。

## Agent 分工

### Orchestrator Agent

Skill：
- 停止条件 gate
- 分支和 worktree 范围控制
- 证据路由
- 合入就绪决策

职责：
- 保持本轮运行聚焦在 AArch64 后端性能。
- 决定继续、重复、否决，还是进入汇报。
- 强制执行停止条件：
  - 任一可信 JIT28 单项提升至少 30%
  - 或 full JIT28 geomean 提升至少 10%
- 在把 benchmark delta 当成真实收益前，必须要求代码因果链。

输入：
- `git status`、`git log`、当前分支
- case plan、findings、progress
- 子 Agent 报告

输出：
- accepted/rejected/needs-repeat 最终决策
- 下一步最小实验

### Progress Audit Agent

Skill：
- 最近改动审计
- artifact 索引
- 候选状态分类

职责：
- 重新扫描当前 git diff 和最近记录。
- 区分 accepted、stacked、rejected、needs-repeat 候选。
- 区分单独优化、叠加优化、microbench、focused pyperformance、S12、full JIT28
  证据。

输入：
- `progress.md`
- `findings.md`
- `task_plan.md`
- `plans/**`
- `artifacts/**`

输出：
- 当前整体进展
- 带证据路径的候选表

### Analysis Agent

Skill：
- ARM/x86 差异 pattern 挖掘
- LIR/ASM 阅读
- 微架构假设构建
- 候选排序

职责：
- 从 ARM/x86 差异里找优化点。
- 解释为什么 AArch64 比 x86 有更大的机会。
- 如果机制看起来合理但 benchmark 证据弱，要否决或标成待验证。

输入：
- LIR dump
- 汇编 dump
- perf/PMU 记录
- benchmark delta
- LIR lowering 和 codegen 附近代码

输出：
- 排序后的 ARM 亲和假设
- 机器级因果解释

### Implementation Agent

Skill：
- LIR opcode 形态设计
- postalloc rewrite 推理
- AArch64 codegen
- x86 fallback 和安全性
- 构建、崩溃、性能异常调试

职责：
- 负责实现推理，但内部保持三个角色分离：
  - Analysis Role：编辑前确认代码因果链。
  - Codegen Role：保持 patch 最小。
  - Debug Role：质疑失败和可疑收益。
- 本次复现轮不修改优化代码，除非缺少必要的 harness-only 文件。

输入：
- 选中的候选
- 代码因果链
- verifier/codegen 约束

输出：
- patch 就绪判断
- 已知风险和必需测试

### LIR/ASM Evidence Agent

Skill：
- dump 收集
- 形态计数
- before/after LIR 和 ASM 对比

职责：
- 捕获或定位 before/after LIR dump 和汇编证据。
- 记录精确阶段、文件路径和统计规则。
- 不混用全日志 grep 和 postalloc 过滤后的统计。

相关时必须统计：
- `Test`
- register `BranchZ` / `BranchNZ`
- label-only `BranchZ` / `BranchNZ`
- `LoadAttrCachedFastPath`
- `LoadAttrCache::invoke` 调用
- AArch64 shared-stub 使用

输出：
- LIR/ASM 证据表

### Perf Agent

Skill：
- focused benchmark
- S12 重复验证
- full JIT28
- pyperf JSON 对比
- 噪声分类

职责：
- 先跑 focused benchmark。
- 如果有信号，跑 S12 重复验证。
- 如果仍可信，运行或定位 full JIT28。
- 直接比较 baseline JSON 和 candidate JSON。
- 如果 benchmark 行耗时极小或不稳定，分类为噪声，除非代码因果链也很强。

输出：
- focused 结果
- S12 结果
- 如有，full JIT28 结果
- accepted/noise/needs-repeat 分类

### Debug Agent

Skill：
- 构建失败根因分析
- 崩溃根因分析
- verifier/autogen/ABI 问题诊断
- 性能异常诊断

职责：
- 调查失败时不能默认优化正确。
- 记录失败是使候选无效，还是只是 harness 问题。
- 检查 x86 和 AArch64 边界问题。

输出：
- 根因和修复路径
- invalid-run 说明

### Review Agent

Skill：
- 代码因果链复查
- ARM/x86 边界复查
- 最小 patch 复查
- 合入 gate

职责：
- 检查 patch 是否按预期用 `CINDER_AARCH64` 隔离。
- 如果引入新 LIR 形态，检查 verifier 和 x86 codegen 安全。
- 确认没有包含无关改动。
- 判断证据是否足以进入合入、汇报，还是需要更多重复验证。

输出：
- review findings
- merge readiness 状态
