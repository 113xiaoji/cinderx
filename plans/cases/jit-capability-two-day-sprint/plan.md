# Plan

## Goal

在 2 天内，通过并行推进运行时策略、对象模型高价值点、以及验证基础设施，获得“性能/稳定性/迭代效率”的实质提升。

## Non-goals

- 不承诺在 2 天内完成完整 tiering
- 不承诺在 2 天内完成广覆盖 OSR
- 不承诺在 2 天内完成完整 escape analysis / scalar replacement

## Hard constraints

- 所有 A/B 结果默认对比固定基线 commit，而不是浮动 `origin/main`
- object-heavy regression 修复不能以明显破坏 hot-loop winners 为代价
- 如果候选改动在保护集上出现 material regression，就不进入 Day 2 收口

## Day 1

### 09:00-12:00 控制面与验证面收口

- 统一远端入口与环境快照
- 固化可重复的 A/B 运行脚本
- 固化结果落盘格式（JSON + markdown summary）
- 目标：
  - 任何一次关键实验都能在低人工干预下稳定重跑
  - 结果自动进入 findings / artifacts

### Track A: Verification / Harness

- 统一远端 ARM 入口
- 固化 benchmark 子集与 A/B 输出格式
- 自动沉淀 findings / compare 结果
- 降低 worker/venv/environment 漂移带来的噪音

建议优先文件：

- `scripts/arm/remote_update_build_test.sh`
- `scripts/arm/run_pyperf_subset.sh`
- `scripts/arm/bench_pyperf_direct.py`
- `scripts/arm/compare_pyperf_subset.py`

### Track B: Profitability / Feedback

- 梳理当前 same-activation、wrapper gate、shape policy 的决策路径
- 增加更可读的 runtime 观测面
- 让“为什么编 / 为什么跳过 / 为什么 deopt”更容易直接看到

建议优先文件：

- `cinderx/Jit/pyjit.cpp`
- `cinderx/Jit/context.h`
- `cinderx/Jit/context.cpp`
- `cinderx/PythonLib/cinderx/jit.py`

### Track C: High-ROI runtime target

- 选 1-2 个最可能在两天内带来收益的具体方向：
  - profitability/shape policy refinement
  - 对象模型相关的 attr/method polymorphism 优化
  - 特定热点 lowering / specialization 改进

建议优先级：

1. profitability / feedback 决策面
2. 对象模型热点（attr/method）
3. 其他高风险编译器改动

### Day 1 exit criteria

- 验证 harness 能稳定输出：
  - 固定基线 vs 当前 worktree 的 A/B
  - 至少一组 hot-loop winners
  - 至少一组 object-heavy/search-heavy case
- 至少一个候选 runtime 方向有定量收益证据
- 明确淘汰一批两天内不值得继续做的大项

### 13:00-18:00 首轮实现

- 只实现 Day 1 上午已经证明高 ROI 的 1-2 项
- 每项都必须带：
  - 定向红灯
  - 远端验证
  - findings 落盘

### 19:00-22:00 第一轮回归与重排优先级

- 根据数据淘汰低收益方向
- 确认 Day 2 只保留真正有本质收益的轨道

## Day 2

### Track D: Narrow implementation

- 只实现 Day 1 证明最有把握的 1-2 项
- 坚持最小改动面
- 统一走远端入口验证

### 09:00-14:00 第二轮实现

- 收敛 profitability / shape policy
- 如果对象模型热点有明确收益，再加一项

### 14:00-18:00 稳定性与性能总验证

- 对固定 benchmark 子集做最终 A/B
- 跑关键回归测试
- 输出定量结果

固定 benchmark 子集建议：

- winners:
  - `fannkuch`
  - `unpack_sequence`
  - `comprehensions`
  - `scimark`
- regressors / risk:
  - `go`
  - `chaos`
  - `raytrace`

### 19:00-22:00 Closeout

- 更新 findings / progress / learnings / ledger
- 形成“已完成 / 未完成 / 下一步”的最终交付说明

### Track E: Closeout

- 更新 findings / progress / learnings / ledger
- 输出 A/B 结果
- 列出未完成项与后续优先级

## Parallel agent layout

- 主控 agent：
  - 维护计划
  - 决定优先级
  - 审阅结果
- Worker A：
  - 验证 / benchmark harness
- Worker B：
  - profitability / feedback 数据面
- Worker C：
  - 运行时高 ROI 优化点
- Reviewer：
  - 专做定向 review / 结果一致性检查

## Expected best-case outcome in 2 days

- 不是“补齐所有顶级 JIT 能力”
- 而是：
  - 迭代速度显著提高
  - 性能结论更可信
  - profitability 决策更系统
  - 至少 1-2 个高价值路径获得真实改进

## Expected realistic deliverables

- 一个稳定可重复的远端 A/B harness
- 一层更可观测的 profitability / feedback 数据面
- 一个经验证的高 ROI runtime 改动
- 一份明确的 defer list，说明哪些“大能力”不应在两天内硬做
