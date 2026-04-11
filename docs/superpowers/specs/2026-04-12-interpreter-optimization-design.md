# CinderX 解释执行优化总纲设计

> 状态：草案
> 分支：`codex/interpreter-optimization-design`
> 范围：仅聚焦解释执行优化；不展开 Cinder JIT 主线设计

## 背景

当前仓库已经不属于“纯字节码解释器”状态。解释执行路径中已经具备：

- adaptive / specialization 路径
- tier2 / executor / uop 基础设施
- 一些针对热点形状的专门优化

典型证据包括：

- `Interpreter/3.14/interpreter.c` 与 `Interpreter/3.15/interpreter.c` 中的 adaptive、executor、tier2 入口
- `Interpreter/3.14/cinder-bytecodes.c` 与 `Interpreter/3.15/cinder-bytecodes.c` 中对 Cinder opcode 的 specialization 逻辑
- `Jit/hir/builder.cpp` 中已经存在的一些热点形状模式化处理

与此同时，当前解释执行层仍存在明显优化空间：

1. opcode 组合层面仍偏手工、局部，尚未形成系统化 superinstruction / macro-op 融合框架
2. 轻度多态对象访问、方法调用、全局读取、容器访问的解释器层 cache 仍有明显提升空间
3. tier2 / executor / uop 当前更像已有机制，而不是一条清晰、产品化的解释执行中间层
4. 缺少统一的解释执行反馈层，难以稳定判断哪些路径应该留在 tier1，哪些值得进入 tier2

本设计的目标，是在**不把 JIT 主线掺进来**的前提下，给出一条清晰的解释执行优化路线图。

## 目标

### 近中期目标

在不破坏现有 `3.14` / `3.15` 支持和解释器正确性的前提下：

- 降低 tier1 解释器 dispatch 成本
- 提升轻度多态热点路径的命中率与稳定性
- 明确 tier1 与 tier2 的解释执行层分工
- 建立面向解释执行的统一收益判定体系

### 长期目标

形成一条稳定的解释执行分层路径：

- Tier 1：adaptive interpreter + selective superinstructions + small PIC
- Tier 2：executor / uop interpreter + 更长的 macro-op / region 执行
- Shared feedback：统一记录热点组合、specialization、PIC、多态度、tier2 usefulness

## 非目标

本设计明确不包括：

- Cinder JIT 主线优化路线
- HIR / LIR / codegen 总体重构
- tracing JIT 路线
- 大规模重写解释器结构以依赖编译器黑科技
- 改变当前 `3.14` / `3.15` 兼容策略主线

JIT 在本设计中仅作为共存组件存在，不作为本轮优化主角。

## 方案对比

### 方案 A：解释器优先

第一阶段主攻：

- superinstruction / macro-op 融合
- small PIC

tier2 / executor / uop 只做观测和收口。

优点：

- 收益更快兑现
- 风险较低
- 更适合先在 `3.14` / `3.15` 上稳定落地

缺点：

- 会延后 tiering 的体系化建设

### 方案 B：tiering 优先

第一阶段主攻：

- tier2 / executor / uop 产品化

superinstruction / PIC 只做最小补充。

优点：

- 长期架构收益更大
- 与分层执行路线最一致

缺点：

- 工程复杂度高
- 短期未必拿到稳定收益

### 方案 C：双主线并行

第一阶段并列推进：

- superinstruction / macro-op 融合 + small PIC
- tier2 / executor / uop 的观测、准入与角色收口

第二阶段再把 tier2 做成稳定中间层。

优点：

- 兼顾短期收益与长期架构
- 避免解释器层收益和 tiering 建设彼此脱节

缺点：

- 设计和推进复杂度最高

### 推荐方案

推荐采用**方案 C**，但执行顺序上明确：

1. 先兑现 tier1 解释器层收益：`superinstruction + small PIC`
2. 同时建立 tier2 的观测与准入框架
3. 再决定 tier2 是否值得继续做重、做深

换句话说：

- 第一阶段是“双主线并行”
- 但资源投入顺序仍然是“解释器收益优先，tier2产品化其次”

## 设计范围

### 范围内

- `Interpreter/3.14`
- `Interpreter/3.15`
- opcode family specialization
- superinstruction / macro-op 融合
- small PIC
- executor / uop / tier2 的解释执行层准入和观测
- 与这些能力直接相关的验证和 benchmark

### 范围外

- JIT 主线优化
- tracing JIT
- HIR/LIR 优化路线
- 任何需要大规模推倒解释器结构的实验

## 架构主线

### 主线 A：superinstruction / macro-op 融合

#### 目标

将当前零散、手工的热点融合，提升为“可枚举、可生成、可验证”的解释器层优化机制。

#### 第一阶段原则

- 以 pair 为主
- triple 只对极少数高价值组合开放
- 从 profile 证据出发，不做全量生成
- 允许 `3.14` / `3.15` 各自生成具体代码，但共享规则定义

#### 第一批优先组合

- load/load/binary-op
- compare/jump
- truthiness/jump
- load-attr/call 前置准备序列
- 已经稳定的 Cinder specialized opcode 组合

#### 预期收益场景

- `richards`
- `richards_super`
- `nbody`
- `nqueens`
- `coverage`

#### 不建议做法

- 一上来自动生成大批融合组合
- 深度依赖单一编译器特性
- 把调试/反汇编可读性完全牺牲掉

### 主线 B：small PIC

#### 目标

让解释器层 specialization 从“单态场景表现很好”提升到“轻度多态场景也稳定受益”。

#### 第一阶段原则

- 只做 2~4 路小型 PIC
- 不做 megamorphic
- 解释器层 cache 与 JIT cache 分开
- fallback 简单、便宜、可靠

#### 第一批 family

- `LOAD_ATTR`
- `CALL`
- `LOAD_GLOBAL`
- `BINARY_SUBSCR`

#### 预期收益场景

- `go`
- `deltablue`
- `logging`
- `unpickle_pure_python`
- `xml.etree` 类 workload

### 主线 C：tier2 / executor / uop 的解释执行层产品化

#### 目标

把已有的 tier2 / executor / uop 机制，从“仓库里已经存在”推进成“解释执行层明确的一层”。

#### 第一阶段目标

第一阶段**不追求把 tier2 做重**，而是先做：

- 进入条件可解释
- 退出条件可解释
- 命中率可测
- usefulness 可测

#### 需要回答的问题

- 哪些热点应该停留在 tier1 + superinstruction / PIC
- 哪些热点进入 tier2 才有收益
- tier2 的收益是否独立于 JIT 可测

#### 预期收益场景

- `coroutines`
- `generators`
- 中型热点 helper
- 热但尚未热到进入重 JIT 的函数

## 模块划分

### 模块 1：`InterpProfile`

职责：

- 收集 opcode pair / triple 热度
- 收集 specialization hit / miss
- 收集 executor / tier2 进入与退出原因
- 输出稳定 profile 结构

原则：

- 默认可关闭
- 不改变行为
- 不和 JIT profile 混在一起

### 模块 2：`SuperinstructionPlanner`

职责：

- 维护允许融合的规则
- 根据 profile 选择高价值组合
- 生成 `3.14` / `3.15` family 的具体实现

原则：

- 控制规模
- 允许黑名单
- 允许回退

### 模块 3：`SmallPIC`

职责：

- 维护少量高价值 family 的多态 cache
- 负责 invalidation
- 负责记录命中率和退化原因

原则：

- 先小后大
- 先稳后全

### 模块 4：`Tier2Policy`

职责：

- 定义 tier1 与 tier2 的关系
- 决定 tier2 进入条件
- 记录 tier2 usefulness

原则：

- 第一阶段以观测和准入为主
- 不在第一阶段引入复杂调度逻辑

### 模块 5：`InterpPerfValidation`

职责：

- 跑解释执行专用 benchmark
- 输出分项收益
- 区分解释器收益与 JIT 收益

## 实施分期

### Phase 0：观测先行

产出：

- opcode 热度
- pair 热度
- specialization miss 原因
- tier2 命中率

目标：

- 不改行为，只加证据

### Phase 1：superinstruction v1

目标：

- 在稳定短序列 workload 上先吃收益
- 做小、稳、可验证的一批融合组合

### Phase 2：PIC v1

目标：

- 解决轻度多态对象访问退化
- 优先覆盖对象访问/方法调用/全局/下标访问

### Phase 3：tier2 准入产品化

目标：

- 明确 tier1 和 tier2 的边界
- 让 tier2 成为解释执行层的稳定中间层候选

### Phase 4：统一反馈层

目标：

- 将 superinstruction、PIC、tier2 的观测数据统一
- 为后续长期演进奠定基础

## 验证集与收益判定

### 核心验证集

建议固定以下 workload：

- `richards`
- `richards_super`
- `go`
- `deltablue`
- `unpickle_pure_python`

### 验证目标

每个优化项都要分别回答：

- 是否减少 tier1 dispatch
- 是否减少 generic fallback
- 是否提高 tier2 命中有效性
- 是否引入版本分叉维护成本

### 近中期成功标准

第一阶段成功，不要求直接在总 benchmark 上出现巨大几何平均提升，而要求：

- 至少 2 个“稳定序列型” workload 有明确收益
- 至少 2 个“轻度多态型” workload 有明确收益
- tier2 进入/退出开始可解释
- `3.14` / `3.15` 不需要两套完全不同的解释器优化实现

## Kill Criteria

### Kill 1：停止扩大 superinstruction 规模

如果出现以下任一情况，应暂停继续扩张：

- 新增组合明显多于真正带来收益的组合
- 调试和回归定位成本显著上升
- `3.14` / `3.15` 的实现分叉迅速扩大
- 在核心验证集上的收益小于噪音

### Kill 2：停止扩大 PIC family

如果出现以下情况，应暂停：

- invalidation 复杂度明显上升
- megamorphic 场景回退频繁且总体无收益
- 单态路径被拖慢
- cache 逻辑显著恶化解释器维护性

### Kill 3：暂停继续做重 tier2

如果出现以下情况，应暂停：

- tier2 命中率低
- tier2 进入后很快 fallback
- tier2 相比 tier1 + superinstruction/PIC 没有独立收益
- tier2 的维护成本接近另起一条执行器

## 长期演进图（只看解释执行）

### Tier 1

- adaptive interpreter
- selective superinstructions
- small PIC
- 便宜且稳定的 fallback

### Tier 2

- executor / uop interpreter
- 更长的 macro-op / region 执行
- 更强的反馈消费能力

### Shared Feedback

- opcode 热组合
- specialization family stats
- PIC 多态度
- tier2 usefulness / fallback 原因

JIT 不在这份设计中展开，只作为后续可消费同一反馈层的独立执行线存在。

## 推荐立项顺序

1. `superinstruction / macro-op` 框架
2. `small PIC`
3. `tier2/executor` 观测与准入
4. tier2 稳定中间层化

## 结论

对于当前仓库，最合理的解释执行优化路线不是继续抠单点 dispatch 微优化，也不是立即扩展 JIT 主线，而是：

- 先兑现 tier1 解释器层收益：`superinstruction + small PIC`
- 同时建立 tier2 的可观测性和准入逻辑
- 以证据决定 tier2 是否值得继续做重

这是最符合当前代码结构、版本支持现状以及验证基础设施的一条路线。
