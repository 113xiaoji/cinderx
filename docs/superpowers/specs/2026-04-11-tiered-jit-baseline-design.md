# 分层 JIT 设计草案：Baseline Tier 优先

## 背景

当前 CinderX 已经具备一套完整的优化型 JIT 流水线：

- `HIR -> LIR -> codegen`
- 多个 HIR pass
- register allocation
- deoptimization
- inline cache
- 函数级触发与入口替换

但它整体上仍然更像“解释器 + 单层优化 JIT”，而不是主流运行时常见的“解释器 + baseline JIT + optimizing JIT”的分层架构。

与 HotSpot、V8、.NET 这些主流 JIT 相比，当前最大的结构性差距不是“缺几个优化 pass”，而是：

- 缺一个编译极快、覆盖面广的 baseline tier
- 当前 JIT 更像优化 tier，却同时承担了“尽快脱离解释器”和“深度优化热点代码”两类职责
- 缺一个清晰的 tiering 控制器，把解释器、baseline tier 和优化 tier 串起来

这会直接带来两个问题：

- 中温代码、短生命周期代码、helper 密集函数很难以足够低的成本脱离解释器
- 当前优化 JIT 被迫同时面对“低编译延迟”和“高码质”两种目标，职责不够单一

## 对主流 JIT 的对比结论

### HotSpot

HotSpot glossary 里明确区分：

- `C1 compiler`
  - fast, lightly optimizing compiler
- `C2 compiler`
  - highly optimizing compiler
- `OSR`
  - 在解释器发现方法在循环中变热时，于 backward branch 处切入特殊 nmethod

这说明 HotSpot 的常规能力不是“只有一个 JIT”，而是：

- 有轻优化快速层
- 有重优化层
- 有清晰的 OSR / deopt / dependency 体系

### V8

V8 官方材料表明：

- `Sparkplug`
  - non-optimizing compiler
  - 位于 Ignition 和 TurboFan 之间
  - 直接从 bytecode 编译，以追求极低延迟
- `Maglev`
  - fast optimizing JIT
  - 作为 Sparkplug 和 TurboFan 之间的进一步分层

V8 的关键经验是：

- baseline tier 不需要追求极致优化
- baseline tier 首先要便宜到足够积极地把代码从解释器挪出来

### .NET

.NET 7 的官方文档和性能文章明确把 tiered compilation 当成默认能力，并把 OSR 和循环热点结合起来讲。

对当前 CinderX 的启示是：

- “非 tracing、保留方法级 JIT”的运行时，也完全可以做出有效的分层体系
- baseline tier 和 optimizing tier 可以共享统一的 code versioning 与后续重编译机制

### PyPy

PyPy 的 tracing JIT 在热循环和对象密集路径上很强，但它依赖的是 tracing recorder、guards、bridges 这一整套完全不同的架构。

对当前问题的启示是：

- tracing 路线很强
- 但不适合作为当前 CinderX 3.14 的最小演进路径

## 问题定义

如果现在要在 CinderX 里引入“真正的分层 JIT”，优先目标不应该是：

- 再加一批更激进的优化 pass
- 直接做一个 Maglev 风格的中层优化器
- 直接做 stencil / copy-and-patch 的极限实现

而应该先解决一个更基础的问题：

> 如何让大量普通函数、helper 函数、中温代码，以远低于当前优化 JIT 的编译成本脱离解释器？

只要这个问题不解决，当前系统就仍然会在以下两者之间硬切换：

- 继续解释执行
- 进入完整优化流水线

这正是与主流 JIT 的核心差距。

## 设计目标

本设计只讨论：

- `解释器 -> baseline JIT -> 当前优化 JIT`

不把以下内容作为本轮目标：

- 追求类似 Maglev 的 fast-optimizing tier
- tracing JIT
- 把 baseline tier 第一版做成极致的 copy-and-patch/stencil 系统

Baseline tier 的目标应当是：

1. 编译极快
2. 覆盖面广
3. 语义稳定
4. 能积累稳定的动态反馈
5. 为后续 optimizing tier 提供自然的上层入口

## 建议的分层结构

### Tier 0：解释器

职责：

- 最冷代码执行
- 所有不支持场景的语义兜底
- debug / tracing / profiling / instrumentation 的保底执行层

### Tier 1：Baseline JIT

职责：

- 以很低的编译延迟把代码从解释器挪出来
- 覆盖大量普通函数、中温函数、helper-heavy 函数
- 收集动态反馈，供更高层使用

第一原则：

- baseline tier 的成功标准不是“比 optimizing tier 更快”
- 而是“比解释器更快，并且足够便宜”

### Tier 2：当前 HIR/LIR JIT

职责：

- 作为 optimizing tier
- 消费更稳定的 feedback
- 执行更贵但更有收益的优化

对当前代码库的直接建议是：

- 不再把当前 JIT 视为唯一 JIT
- 明确把它重新定位为 optimizing tier

## 三种可行实现方案

### 方案 A：在当前 HIR/LIR 流水线上裁一个 fast-mode

思路：

- 继续使用当前 `Compiler::Compile()`
- 但提供一套新的 `baseline config`
- 尽量关掉或弱化：
  - inliner
  - 多数 HIR 优化 pass
  - 激进 specialization
  - 重型寄存器优化

优点：

- 改动最小
- 最适合快速原型验证
- 最大程度复用当前 deopt、entry patch、compiled function 生命周期

缺点：

- 很可能仍然不够快
- 当前流水线的固定成本仍在
- 最后容易得到“阉割版 optimizing JIT”，而不是真 baseline tier

适合用途：

- 原型验证
- 量化当前优化流水线的固定编译成本
- 判断 baseline tier 的收益窗口

不适合作为：

- 最终架构

### 方案 B：新增独立的 bytecode -> machine code baseline compiler

思路：

- 新增 `BaselineCompiler`
- 直接从 bytecode 编译
- 不建 HIR / 不走 SSA / 不走现有 pass 主链
- 尽量单遍或近单遍发码
- 尽量复用 runtime helper、deopt trampoline 和现有入口替换机制

优点：

- 架构边界最清晰
- 最符合 Sparkplug / C1 类 baseline tier 的定位
- 可以自然和当前 optimizing tier 分工

缺点：

- 需要新增一套 compiler/backend
- 需要自己管理 bytecode stack machine 到 machine state 的映射
- 需要补 tier controller、feedback 汇聚、code versioning

适合用途：

- 正式长期路线

这是推荐路线。

### 方案 C：做 stencil / copy-and-patch baseline tier

思路：

- 预制 opcode 或常见序列模板
- 编译时通过 patch 常量、helper 地址、cache 地址来快速生成代码

优点：

- 理论上编译延迟最低
- 是非常强的 baseline tier 实现方向

缺点：

- 工程门槛高
- 模板维护成本高
- 当前代码库几乎没有这套基础
- Python 语义复杂，第一步就这么做风险太高

适合用途：

- baseline tier 第二阶段
- 当 baseline tier 已经存在，并需要继续压低编译延迟时

不适合作为：

- 当前第一阶段落地方案

## 推荐路线

推荐组合是：

- 正式目标：方案 B
- 低成本预研：方案 A
- 暂不作为第一步：方案 C

也就是说：

1. 可以先用方案 A 做一轮短周期验证
2. 但正式架构应当转向方案 B
3. 不建议把方案 A 长期化，也不建议直接跳方案 C

## Baseline Tier 的职责边界

Baseline tier 不应该追求：

- 极强内联
- 复杂对象 specialization
- 多层反馈消费
- 激进对象优化

这些更适合 Tier 2。

Baseline tier 应该追求：

- 低延迟编译
- 高覆盖率
- 简单稳定的 code shape
- 低风险 deopt / fallback
- 稳定反馈积累

一句话总结：

> Baseline tier 的职责是“先把代码从解释器挪出来”，不是“尽可能把代码优化到极致”。

## Tiering 触发策略

### Interpreter -> Baseline

建议：

- 保留函数级 `call count` 作为粗触发
- 但阈值应显著低于当前 optimizing JIT 的触发阈值

原因：

- baseline tier 的目标就是更激进地离开解释器

### Baseline -> Optimizing

建议使用组合信号，而不是单一 `call count`：

- baseline 执行次数
- loop/backedge 热度
- 调用边热度
- receiver/type feedback 稳定性
- 热点 call edge 的单态/双态情况

原因：

- Tier 2 应该建立在更稳定、更高价值的热点识别之上

## 代码版本和入口切换

当前代码库已经有良好的基础：

- `PyFunctionObject::vectorcall` 可替换
- `CompiledFunction` 已有 `normal/static/reentry`
- `Context::finalizeFunc()` 已能安装编译后的入口

建议新增统一的 tier state，而不是让各层各自 patch。

理想模型：

- 默认 `vectorcall -> interpreter`
- baseline 编译完成后，`vectorcall -> baseline`
- optimizing 编译完成后，`vectorcall -> optimizing`
- deopt 时优先回 baseline，而不是总是直接回 interpreter

这比“只有解释器和优化 JIT 两层”更接近主流 JIT 的运行方式。

## MVP 支持范围

第一版 baseline tier 应明确只支持：

- 普通 Python 函数
- 无 generator / coroutine / async
- 无复杂异常处理区
- 无复杂闭包/cell/freevar 交互
- 常见字节码子集：
  - `LOAD_FAST`
  - `STORE_FAST`
  - `LOAD_CONST`
  - `LOAD_ATTR`
  - `LOAD_METHOD`
  - `CALL`
  - `BINARY_OP`
  - `COMPARE_OP`
  - 简单 `FOR_ITER`
  - 简单 `JUMP_*`
  - `RETURN_VALUE`

第一版明确不支持：

- generator / coroutine
- 复杂 `try/except/finally`
- module/class body
- 复杂 block-stack 语义
- 高级对象恢复需求

原因很简单：

- baseline tier 第一版必须先追求边界清晰
- 如果一开始就试图吞掉所有复杂语义，它会迅速退化成第二个 optimizing tier

## MVP 成功标准

第一版不要求：

- 比 optimizing tier 更快
- 峰值性能特别高

第一版要求：

1. 编译延迟显著低于当前 optimizing JIT
2. 能接管一批真实普通函数，而不是只跑 toy case
3. 中温代码相对解释器有稳定收益
4. 不支持场景边界清晰，fallback 正确
5. 能形成后续 Tier 2 可用的反馈基础

## 实施切片建议

### Phase 0：fast-mode 预研

目标：

- 用方案 A 估算当前 optimizing JIT 的固定编译成本
- 找出最贵的固定开销
- 确认 baseline tier 的收益窗口

### Phase 1：最小 baseline compiler

目标：

- 用方案 B 做最小独立 baseline compiler
- 只支持最常见字节码子集
- 先重 helper 调用和正确性，不追求码质

### Phase 2：tier controller 与入口版本切换

目标：

- 串起 interpreter、baseline、optimizing
- 形成清晰的 tier state 和 entry patch 机制

### Phase 3：feedback 汇聚

目标：

- baseline tier 不只是执行层，而成为稳定反馈层
- 优化 tier 开始系统消费反馈

## 风险

### 风险 1：方案 A 做出来“看起来像 baseline，其实不是”

这是最大的路线风险。

如果 fast-mode 只是比当前 optimizing tier 略快，但仍然很重，就会拖延正式 baseline tier 的建设。

### 风险 2：baseline tier 过早承担太多优化职责

如果第一版 baseline 就试图承担：

- 激进内联
- 深度 specialization
- 复杂对象优化

那它会迅速失去 baseline tier 的核心价值：低延迟。

### 风险 3：tiering 先于 feedback

如果先做 tiering 切换，但没有稳定 feedback，Tier 2 的进入条件会很粗糙，收益可能不稳定。

## 最终建议

当前最合理的分层 JIT 路线是：

1. 明确把当前 HIR/LIR JIT 重新定义为 optimizing tier
2. 先做 baseline-first，而不是 mid-tier-first
3. 用方案 A 做短周期验证
4. 用方案 B 做正式落地
5. 把 stencil/copy-and-patch 保留为 baseline tier 第二阶段优化方向

一句话版结论：

> 如果现在要做分层 JIT，正确的第一步不是“让当前 JIT 再快一点”，而是“先建立一个真正便宜、覆盖广、边界清晰的 baseline tier”。

## 参考资料

- HotSpot Glossary
  - https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html
- Sparkplug
  - https://v8.dev/blog/sparkplug
- Maglev
  - https://v8.dev/blog/maglev
- .NET 7 performance improvements
  - https://devblogs.microsoft.com/dotnet/performance_improvements_in_net_7/
- .NET compilation config
  - https://learn.microsoft.com/en-us/dotnet/core/runtime-config/compilation
- PyPy performance
  - https://pypy.org/performance.html
