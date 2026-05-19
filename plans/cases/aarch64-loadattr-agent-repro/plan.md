# AArch64 LoadAttr Agent 复现计划

## 目标

使用 `agents.md` 中定义的 Agent 工作流，复现 AArch64
`LoadAttrCachedFastPath` 优化，并判断当前证据链能否重新生成，还是必须在远端
ARM 机器上重新跑。

## 当前已知上下文

- 任务开始时观察到的本地分支：
  `codex/aarch64-new-optimizations-20260512`
- 任务开始时观察到的本地 HEAD：
  `6a330ecc perf(jit): fold aarch64 fp compare branches`
- 5 月 12 日搜索记录中的基线：
  `95f8ac63 perf(jit): add aarch64 loadattr lir stub`
- 当前 working tree 有无关未提交改动。本次复现不能把这些改动混入任何
  LoadAttr patch 结论。

## 停止条件

- 如果可信重复 JIT28 单项提升至少 30%，停止搜索并转入复查/汇报。
- 如果 full JIT28 geomean 提升至少 10%，停止搜索并转入复查/汇报。
- 小集合 focused 收益不能停止搜索，除非 full JIT28 或有记录的阻塞说明为什么
  暂时无法做更大范围验证。

## 阶段

### Phase 1：Agent 和证据准备

- [x] 定义 Agent 角色和 skill 归属。
- [x] 创建候选证据表。
- [x] 记录当前分支、diff、artifact 状态。

### Phase 2：代码因果链

- [x] 确认 HIR `LoadAttrCached` lowering 到 LIR。
- [x] 确认 `LoadAttrCachedFastPath` LIR 定义。
- [x] 确认 postalloc rewrite 保留 call ABI 和返回寄存器处理。
- [x] 确认 AArch64 codegen 路径和 shared-stub 策略。
- [x] 确认 x86 fallback/default 路径安全。

### Phase 3：复现路径

- [x] 定位已有 baseline/candidate benchmark artifact。
- [x] 定位或重建 focused 和 JIT28 远端命令。
- [x] 判断本轮是否可行地重新远端运行。

### Phase 4：验证

- [x] 运行或收集 focused benchmark。
- [x] 如果 focused 有信号，运行或收集 S12 重复验证。
- [x] 如果 S12 仍可信，运行或收集 full JIT28。
- [x] 捕获或定位 LIR/ASM dump 和形态计数。

### Phase 5：复查和汇报

- [x] 将优化分类为 reproduced、partially reproduced 或 blocked。
- [x] 记录缺失证据和下一步最小动作。
- [x] 更新 findings/progress。

## 结果

状态：partially reproduced。

机器级机制在直接 microbench 中复现：
默认 AArch64 LoadAttr shared stub 比通过
`PYTHONJITAARCH64LOADATTRSTUBMINCALLS=9999` 禁用 stub 快 21.918%。

pyperformance workload 收益没有复现成可信结果：
focused object subset S12 geomean 只有 -0.087%，所有行都在约 +/-1% 内。
更宽的 JIT28 S3 检查也远低于停止条件。因此这轮只支持“机制存在”，不支持
“accepted pyperformance optimization”。

## 认定为“复现成功”所需的最小证据

- 从 HIR/LIR 到 AArch64 codegen 的代码因果链。
- 至少一组 focused run 的 before/after benchmark JSON 或 compare 文本。
- 重复验证证据，或明确说明只有历史证据可用。
- LIR/ASM 证据证明 `LoadAttrCachedFastPath` 存在并进入 AArch64
  helper-call/stub 路径。
- x86 安全性解释。
