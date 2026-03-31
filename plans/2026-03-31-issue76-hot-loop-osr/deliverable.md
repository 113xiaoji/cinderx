# Deliverable: Issue 76 Hot-Loop OSR 可行性设计（CinderX 3.14）

## Terms And Executive Summary / 术语和结论摘要

- 本文里的 OSR 指的是“解释器正在执行某个函数时，在热循环处中途切入 JIT 代码继续跑”。
- 需要先澄清一个术语混淆：现有 `cinderx/Jit/guide.md:14-15` 把 deoptimization 也称作 on-stack replacement；那是 **JIT -> interpreter** 的 downward deopt，不是这次 issue 要的 **interpreter -> JIT** 的 upward OSR。
- 当前 CinderX 3.14 已经具备三块重要基础能力：
  - 函数级编译触发和代码缓存；
  - 完整的 deopt 回解释器链路；
  - 3.14 解释器里现成的热回边/JIT 挂点。
- 当前实现本质上仍然是 **函数级 JIT**，不是热循环驱动的 OSR，因为所有触发条件、缓存键和入口点都绑定在 `PyFunctionObject` 的 `vectorcall` 上，而不是绑定在“当前活跃 frame + 某个 loop header”上。
- 建议的主方案是：
  - 继续沿着“**整函数编译 + loop header secondary entry**”演进；
  - 不直接引入 tracing JIT。
- 结论：
  - **值得做**，但应先做一个明确受限的 MVP。
  - MVP 可以支持“函数只执行一次，但热循环中途进入 JIT”。
  - 第一版应刻意限制场景，把最大风险收敛在“解释器 frame -> loop-header native state”这一块。

## Current State / 当前现状

### 1. JIT 触发方式

- CinderX 3.14 的函数热度主要来自函数调用次数，而不是 loop backedge 次数。
- 关键路径：
  - `cinderx/Jit/pyjit.cpp:101-103`
    - `countCalls()` 读取 `code->co_mutable->ncalls`。
  - `cinderx/Jit/pyjit.cpp:193-216`
    - `jitVectorcall()` 在函数被调用时检查 `compile_after_n_calls`，未到阈值就继续走解释器入口。
  - `cinderx/Jit/pyjit.cpp:1551-1560`
    - `compile_after_n_calls_impl()` 配置阈值并遍历现有函数对象，给它们挂上未来编译资格。
  - `cinderx/Jit/pyjit.cpp:3684-3724`
    - `scheduleJitCompile()` 只是在函数对象上安装 `jitVectorcall`，未来“下次调用”再尝试编译。
  - `cinderx/Jit/pyjit.cpp:3144-3205`
    - `compile_func()` 预加载当前函数和依赖，再做整函数编译。

补充现状：

- `cinderx/Jit/guide.md:108-110` 也明确把 auto-JIT 描述成“根据函数观察到的 call count 自动编译 hot functions”。
- `cinderx/Common/util.h:535-542` 的 `walkFunctionObjects()` 说明现有批量调度是“扫描所有函数对象”这个粒度。

### 2. 进入方式

- 当前主入口仍然是函数调用边界。
- 关键路径：
  - `cinderx/Interpreter/interpreter_base.cpp:35-56`
    - `Ci_InitFrameEvalFunc()` 通过 PEP 523 安装 CinderX 的 frame evaluator；这给了 CinderX 自己的解释器循环。
  - `cinderx/Jit/pyjit.cpp:150-190`
    - `forcedJitVectorcall()` 在函数调用入口处触发编译，成功后直接改成 compiled `vectorcall`。
  - `cinderx/Jit/context.cpp:416-429`
    - `Context::finalizeFunc()` 真正把 `func->vectorcall` 改成 compiled entry。
  - `cinderx/Jit/compiled_function.h:31-47`
    - 现有 compiled code 已经有多个入口概念：
      - normal `vectorcall` entry；
      - static entry；
      - reentry。
  - `cinderx/Jit/codegen/gen_asm.cpp:2460-2584`
    - 生成器还额外有 `resume entry`。

这说明“一个 compiled function 拥有多个 secondary entry”在今天的代码生成框架里是成立的，不是全新概念。

### 3. 退出方式

- 正常返回：compiled function 正常从 native epilogue 返回到调用方。
- downward deopt：guard 失败、异常路径或显式 deopt 时，回到解释器。
- 显式停用：`disable_jit(deopt_all=True)` 会把已编译函数退回解释器入口。

关键路径：

- `cinderx/Jit/deoptimization.md:3-4`
  - 现有 deopt 明确定义为 “running JIT-compiled function -> interpreter”。
- `cinderx/Jit/hir/hir.h:3439`
  - `RunPeriodicTasks` 本身也是 `DeoptBase`。
- `cinderx/Jit/deopt.cpp:449-536`
  - `DeoptMetadata::fromInstr()` 把 HIR `FrameState` 和 live values 变成 deopt metadata。
- `cinderx/Jit/codegen/gen_asm.cpp:197-286`
  - `prepareForDeopt()` 重建解释器 frame，记录 deopt 统计。
- `cinderx/Jit/codegen/gen_asm.cpp:288-390`
  - `resumeInInterpreter()` 继续在解释器里跑。
- `cinderx/Jit/pyjit.cpp:1279-1318`
  - `deoptFuncImpl()` / `deoptFunc()` 显式把 `vectorcall` 改回解释器入口。

### 4. 为什么当前实现本质上仍然是函数级 JIT

这是本文最核心的现状判断。

原因不是“没有 loop 概念”，而是“没有把 loop 热度和 mid-frame entry 串成一个可运行路径”。

具体来说：

1. 触发信号是函数调用，不是 loop backedge。
   - `jitVectorcall()` 看的只有函数 call count。
   - `compile_after_n_calls` 的阈值也是“compile after N calls”。

2. 入口点绑定在 `PyFunctionObject::vectorcall`。
   - `scheduleJitCompile()` 和 `finalizeFunc()` 改的是函数对象入口。
   - 这天然要求“下一次调用函数”才能进入 compiled code。

3. 当前只有 downward state mapping，没有 upward state mapping。
   - 现有 `DeoptMetadata` 是 “native live values -> interpreter locals/stack/block stack”。
   - 没有对应的 “interpreter frame -> native live-ins at loop header” metadata。

4. 解释器虽然有热回边挂点，但没有接到 CinderX JIT 的 mid-frame 入口。
   - `cinderx/Interpreter/3.14/Includes/generated_cases.c.h:9274-9314`
     - `JUMP_BACKWARD` 会转成 `JUMP_BACKWARD_JIT` / `JUMP_BACKWARD_NO_JIT`。
   - `cinderx/Interpreter/3.14/Includes/generated_cases.c.h:9317-9377`
     - `JUMP_BACKWARD_JIT` 在 `_Py_TIER2` 下会走 `_PyOptimizer_Optimize()` 和 `GOTO_TIER_TWO(executor)`。
   - 这条路径今天服务的是 CPython tier2 executor，不是 CinderX JIT。

5. HIR 里有 loop header 概念，但当前只用于“已进入 JIT 之后”的周期活动，不用于 OSR entry。
   - `cinderx/Jit/hir/builder.cpp:1880,1908,1918`
     - builder 会识别 loop header。
   - `cinderx/Jit/hir/builder.cpp:2436-2437,7279-7291`
     - 只是在 loop header 前插 `LoadEvalBreaker` / `RunPeriodicTasks`。
   - 这解决的是 compiled loop 的 pending work 语义，不是 interpreter -> JIT 切入。

### 5. 当前已经具备、可以复用的基础能力

#### 5.1 可复用：函数级编译触发与缓存

- `trackEligibleCodeObjects()`、`registerFunction()`、`compile_func()`、`compileFunction()` 都已经能把“某个 Python function / code object 编译成 compiled code 并缓存下来”。
- 这意味着 OSR 不需要另起一套 compiler pipeline。

#### 5.2 可复用：deopt 回解释器

- `FrameState`、`Snapshot`、`DeoptMetadata`、`prepareForDeopt()`、`resumeInInterpreter()` 已经构成完整 downward deopt 基础设施。
- OSR 新增的主要是反向路径，而不是推翻现有 deopt。

#### 5.3 可复用：3.14 解释器热回边挂点

- `JUMP_BACKWARD_JIT` 已经是现成热点。
- 这是最自然的“热循环触发编译 / 尝试 OSR”的落点。

#### 5.4 可复用：多入口代码生成先例

- compiled function 已有 `static entry`、`reentry`、generator `resume entry`。
- 这强烈暗示 “loop header secondary entry” 更像是现有入口模型的扩展，而不是架构翻修。

#### 5.5 仍然缺失：mid-frame 进入 JIT 的关键部件

- 当前缺的不是“再编译一次 loop body”，而是：
  - 选哪个 loop header 作为 OSR 入口；
  - 如何把当前 `_PyInterpreterFrame` 的 locals/operand stack/block stack 映射到该入口所需的 native live-ins；
  - 如何不再额外分配/链接一层解释器 frame；
  - 如何在 loop header φ 节点语义下建立一个合法的 synthetic predecessor。

## Problem Definition / 问题定义

### 1. 当前方案的短板在哪些 workload 上明显

- 函数会被调用很多次的 workload：
  - 现有 auto-JIT 能覆盖得不错。
- 函数只调用一次，但函数体里有长时间热循环的 workload：
  - 现有方案覆盖明显不足。
- 典型形态：
  - 一次请求里触发一个长循环；
  - 一次性数据处理/初始化/编译步骤；
  - benchmark 外层只调一次，热度全部堆在内部 loop。

### 2. 为什么“函数只执行一次，但内部循环很热”是现有 JIT 的盲区

- 现有触发条件要等“这个函数以后再被调用”才能享受到 compiled entry。
- 如果函数只执行一次：
  - call count 很可能在函数返回前才刚刚变热；
  - 但 compiled entry 只能作用在未来调用；
  - 于是这次真正热起来的 loop，仍然整段跑在解释器里。

换句话说：

- 当前 JIT 对“跨调用复用”很友好；
- 对“单次 activation 内部变热”基本没有抓手。

### 3. 这个问题值不值得解决

我的判断：**值得，但应以受限 MVP 方式推进**。

原因：

- 这是当前函数级 JIT 的结构性盲区，而不是某个 heuristic 没调好。
- CinderX 3.14 已经有：
  - 自己的解释器；
  - backedge/JIT hook；
  - 完整 deopt；
  - 多入口 codegen 先例。
- 所以这不是“从 0 到 1”的 tracing JIT 项目，而是“把现有整函数 JIT 延伸到 mid-frame entry”。

预期收益主要来自：

- 一次性长循环 workload；
- auto-JIT 模式下减少“热度来得太晚”的 blind spot；
- 让现有 HIR/LIR/codegen 优化真正吃到 loop steady-state。

## Industry Comparison / 业界实现对比

| 系统 | 热循环触发编译 | 中途进入 JIT | 动态退出 | 依赖的基础设施 | 对 CinderX 的启发 |
| --- | --- | --- | --- | --- | --- |
| HotSpot JVM | 是，OSR 发生在 backward branch | 是，OSR nmethod | 是，deopt | interpreter profiling、OSR nmethod、safepoint/deopt map | 最接近“整方法编译 + OSR 入口” |
| .NET 7+ | 是，loop iteration counts 驱动 OSR | 是，mid-method code version switch | 是，tiered code / deopt-like 回退 | tiered compilation、loop instrumentation、code versioning | 说明“非 tracing、保留方法级 JIT”也能做 OSR |
| V8 | 是，hot loop 可触发 OSR/tier-up | 是，OSR from bytecode offset | 是，deoptimization | bytecode interpreter、optimized compiler、frame state translation | 需要精确的 bytecode offset -> native state 映射 |
| PyPy | 是，热循环/桥接阈值 | 是，trace entry | 是，guards + bridges | tracing recorder、guard snapshots、bridge compiler | tracing 方向收益高，但基础设施完全不同 |
| LuaJIT | 是，hotloop/hotexit | 是，root trace/side trace | 是，side exits/side traces | trace recorder、snapshots、side exits | 再次说明 tracing 不是当前最小演进方向 |

### HotSpot JVM

- OpenJDK glossary 直接把 OSR 定义成：
  - “在运行时，在 backward branch 处把解释器切到 OSR nmethod”。
- 这说明 HotSpot 的触发点就是热回边，而不是下次方法调用。
- 资料：
  - [HotSpot Glossary](https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html)

### .NET 7+

- .NET 官方在 .NET 7 性能文章里把 OSR 描述成：
  - 在方法已经开始执行后，中途把正在执行的代码切成更优化版本；
  - 典型目标是长时间运行的 loops；
  - 依赖 loop iteration counts。
- 这与本 issue 的目标几乎一一对应。
- 资料：
  - [Performance Improvements in .NET 7](https://devblogs.microsoft.com/dotnet/performance_improvements_in_net_7/)
  - [.NET 7 what's new](https://learn.microsoft.com/en-us/dotnet/core/whats-new/dotnet-7)

### V8

- V8 的 Sparkplug 文章明确提到：
  - 解释器里的函数如果在热循环中 tier-up，可以 OSR 到优化代码。
- V8 的 Maglev 文章说明：
  - deopt 依赖精确的 frame state / known node information，把 optimized state 翻回解释器。
- 这说明 V8 同时具备：
  - upward OSR；
  - downward deopt；
  - 并且都强依赖 bytecode-level state mapping。
- 资料：
  - [Sparkplug, a non-optimizing JavaScript compiler](https://v8.dev/blog/sparkplug)
  - [Maglev](https://v8.dev/blog/maglev)

### PyPy / LuaJIT

- PyPy 和 LuaJIT 都是 trace-based。
- PyPy 官方文档里：
  - `threshold` 控制 loop 编译阈值；
  - `trace_eagerness` 控制 bridge 编译阈值。
- LuaJIT 官方运行文档里：
  - `hotloop` 控制 loop 何时开始 trace；
  - `hotexit` 控制 side trace；
  - `maxtrace`、`maxsnap` 反映 trace/snapshot 基础设施。
- 它们非常适合“热循环中途进入 + guards side exit”，但前提是 tracing runtime。
- 对 CinderX 的意义：
  - 作为对照组很有价值；
  - 但不适合作为 3.14 最小演进路径。
- 资料：
  - [PyPy performance / tracing JIT overview](https://pypy.org/performance.html)
  - [PyPy JIT help](https://doc.pypy.org/en/latest/jit_help.html)
  - [LuaJIT running options](https://luajit.org/running.html)

## Candidate Options / 候选方案

### 方案 A：解释器回边触发整函数编译，但仍从下一次函数调用进入

描述：

- 在 `JUMP_BACKWARD_JIT` 处探测热循环；
- 如果 loop 很热，就编译整个函数；
- 但不尝试 mid-frame entry；
- 当前这次调用继续解释执行，等下次函数调用再走 compiled entry。

优点：

- 代码改动最小；
- 不需要解释器 frame -> native state 映射；
- 几乎不动 codegen/frame linking。

缺点：

- **不能解决 issue 的核心场景**；
- 对“函数只执行一次”的 loop 仍然无效；
- 只是把 loop 热度换成了新的函数级触发信号。

复杂度 / 风险 / 收益：

- 复杂度：低
- 风险：低
- 收益：低

### 方案 B：整函数编译 + loop header secondary entry

描述：

- 仍然编译整个函数；
- 对选中的 loop header 生成 secondary entry；
- 解释器在热回边上把当前 frame 映射到该 secondary entry 所需的 native state；
- 直接从 loop header 进入 compiled code。

优点：

- 保持现有 compiler pipeline；
- 能直接覆盖“函数只执行一次，但热循环中途进入 JIT”；
- deopt 可以继续复用现有链路。

缺点：

- 需要新增 upward OSR metadata；
- 需要处理 φ 节点、frame ownership、block stack 和 stack layout；
- 实现难度明显高于方案 A。

复杂度 / 风险 / 收益：

- 复杂度：中高
- 风险：中高
- 收益：高

### 方案 C：引入 tracing JIT / side trace

描述：

- 直接围绕 hot loop 录 trace；
- 从 trace root/side trace 进入；
- guard miss 走 side exit。

优点：

- 与热循环天然匹配；
- 可只编译真正热的 loop slice。

缺点：

- 对 CinderX 3.14 来说几乎是新系统；
- 需要 trace recorder、guard snapshots、bridge compiler、blacklist、trace cache；
- 与当前 HIR/function compiler 路线不连续。

复杂度 / 风险 / 收益：

- 复杂度：极高
- 风险：极高
- 收益：理论上高，但不符合本轮约束

## Recommended Design / 推荐方案

### 1. 推荐结论

推荐 **方案 B：整函数编译 + loop header secondary entry**。

原因：

- 它是唯一同时满足这几个条件的方案：
  - 支持 once-call hot loop；
  - 复用当前 compiler / deopt / runtime；
  - 不把项目直接升级成 tracing JIT。

### 2. 是否能支持“函数只执行一次，但热循环中途进入 JIT”

**能，但前提是实现 secondary entry + upward OSR metadata。**

推荐控制流如下：

1. `Ci_EvalFrame()` 在解释器里执行函数。
2. `JUMP_BACKWARD_JIT` 观察到某个 loop header 变热。
3. 运行时用“当前函数 + 当前 loop header bytecode offset”查 OSR entry cache。
4. 若未命中：
   - 触发整函数编译；
   - 编译产物里包含该 loop header 的 OSR secondary entry。
5. 运行时把当前 `_PyInterpreterFrame` 的 locals/operand stack 映射成 secondary entry 需要的 native live-ins。
6. 直接跳到该 secondary entry，后续 loop steady-state 在 JIT 中执行。

### 3. MVP 应该支持哪些场景

建议第一版只支持下面这些场景：

- Python 3.14。
- outermost frame only，不支持当前 activation 中存在 inlined frames 的 OSR 入口。
- 普通同步函数，不支持：
  - generator；
  - coroutine；
  - async generator。
- loop header 由 `JUMP_BACKWARD` / `JUMP_BACKWARD_NO_INTERRUPT` 标识。
- reducible loop。
- 不在 `try/except/finally` 活跃块里进入 OSR。
- 只支持 object-typed live-ins。
  - 这是本文的 **设计推断**：先避开 interpreter object -> native primitive register 的额外转换复杂度。
- 允许常见 `for` / `while` loop。
  - 包括 header snapshot 里带少量 operand stack（例如迭代器）的情况。

### 4. 第一版明确不支持哪些场景

- generator / coroutine / async-for loop。
- inlined callee 内部 loop 的 OSR。
- 需要恢复复杂 block stack 的 loop。
- 依赖 primitive locals / primitive stack values 才能进入的 OSR。
- tracing / side trace。
- 多个 loop header 之间的动态再 OSR / nested OSR。
- instrumentation 打开时的 OSR。
  - 当前 CinderX 在 instrumentation 下会直接 pause/deopt JIT，这一规则建议延续。

### 5. 需要改哪些模块、哪些数据结构、哪些 metadata、哪些 runtime helper

下面是我认为最合理的最小模块切分。

#### 5.1 解释器侧

- `cinderx/Interpreter/3.14/Includes/generated_cases.c.h`
  - 在 `JUMP_BACKWARD_JIT` 路径接入 CinderX OSR probe。
  - 最小目标：
    - 用当前 frame、当前 bytecode offset、当前 backedge counter 决定是否尝试 OSR。
  - 与 `_Py_TIER2` 的关系：
    - 建议 CinderX OSR probe 放在 `_PyOptimizer_Optimize()` 前面；
    - 若 CinderX 不接管，则保留现有 tier2 路径。

- `cinderx/Interpreter/interpreter_base.cpp`
  - 可能无需大改，但这里仍是解释器装配点，适合统一初始化 OSR helper / feature flag。

#### 5.2 JIT 调度与上下文

- `cinderx/Jit/pyjit.cpp`
  - 增加基于 loop header 的 compile/request 接口。
  - 可能新增：
    - `scheduleLoopOSR(func, bc_offset)`；
    - `tryLoopOSR(func, frame, bc_offset)`。

- `cinderx/Jit/context.h`
- `cinderx/Jit/context.cpp`
  - 新增 per-function/per-code OSR entry cache 和统计。
  - **设计推断**：
    - 可新增 `FunctionOSRCacheMap`，键为 `(PyCodeObject*, builtins, globals, bc_offset)`；
    - 值为 secondary entry 地址和 metadata 指针。

#### 5.3 HIR / compiler metadata

- `cinderx/Jit/hir/builder.cpp`
  - 继续复用已有 loop header 检测。
  - 新增“哪些 loop header 可生成 OSR entry”的筛选逻辑。
  - 最小化做法：
    - 只对 outermost、无异常块、对象值 live-ins 的 header 标记。

- `cinderx/Jit/hir/hir.h`
  - **建议新增一个伪指令或显式 metadata 节点**，例如 `OSREntry`。
  - 作用：
    - 固定 loop-header secondary entry 的 label；
    - 携带进入该点所需的 interpreter frame snapshot。

- `cinderx/Jit/hir/frame_state.h`
  - 现有 `FrameState` 基本可复用。
  - 但需要更稳定地把“loop header snapshot”暴露给 backend / runtime。

#### 5.4 Runtime metadata

- `cinderx/Jit/code_runtime.h`
- `cinderx/Jit/code_runtime.cpp`
  - **建议新增 `OSREntryMetadata`**。
  - 建议字段：
    - `BCOffset header_bc_offset`
    - `uintptr_t entry_address`
    - `FrameState` / compacted frame-state reference
    - `live_in_locations`
    - `spill_stack_size`
    - `requires_primitive_unboxing` flag
    - `inline_depth` restriction

- `cinderx/Jit/deopt.h`
- `cinderx/Jit/deopt.cpp`
  - 现有 `DeoptMetadata` 适合 downward path。
  - upward path 需要反向映射，因此我不建议硬塞进 `DeoptMetadata`。
  - **设计推断**：
    - 最稳妥的是单独引入 `OSRMetadata` / `OSREntryMetadata`，但复用 `FrameState`、`LiveValue::ValueKind`、`PhyLocation` 等现有类型。

#### 5.5 Codegen / frame linking

- `cinderx/Jit/codegen/gen_asm.cpp`
  - 需要新增 `generateOSREntry(...)`。
  - 这会是继：
    - normal entry；
    - static entry；
    - reentry；
    - generator resume entry；
    之后的又一种 secondary entry。

- `cinderx/Jit/codegen/frame_asm.cpp`
  - normal entry 现在会分配/链接 interpreter frame。
  - OSR entry 不能再新建一层 frame，而应“接管当前已存在 frame”。
  - 这部分是 MVP 的最大 runtime 风险点。

#### 5.6 Runtime helpers

- `cinderx/Jit/jit_rt.h`
- `cinderx/Jit/jit_rt.cpp`
  - **建议新增 helper**：
    - `JITRT_PrepareOSREntry(...)`
    - `JITRT_FillOSRSpillArea(...)`
    - `JITRT_EnterOSR(...)` 或等价接口
  - 核心职责：
    - 从当前 `_PyInterpreterFrame` 读 localsplus / operand stack；
    - 做 object-only live-in 搬运；
    - 初始化 OSR fixed frame；
    - 跳入 secondary entry。

### 6. 与现有 deopt 机制如何配合

推荐原则：

- OSR 只解决 **如何进**；
- deopt 继续复用现有 **如何退**。

具体配合方式：

1. once OSR succeeds，后续 loop body 就和普通 compiled function 一样执行。
2. loop body 里的 `Guard` / `RunPeriodicTasks` / 异常 slow path 仍然生成现有 deopt metadata。
3. `prepareForDeopt()` / `resumeInInterpreter()` 不需要知道“这段 compiled code 是从 normal entry 进来的，还是从 OSR entry 进来的”；
   - 它们只关心当前 `CodeRuntime + DeoptMetadata`。
4. 需要额外处理的是 frame ownership：
   - normal entry 会自己建/链 frame；
   - OSR entry 必须使用当前 frame；
   - 所以 prologue/epilogue 需要能区分“新 activation”与“adopt existing activation”。

这是我推荐 secondary entry 而不是“从函数 normal entry 半路跳过”的原因：

- 复用 compiled body；
- 但显式区分 OSR frame setup 和普通 call-entry frame setup。

## Engineering Conclusion / 工程化结论

### 候选方案对比

| 方案 | 复杂度 | 风险 | 收益 | 是否推荐 |
| --- | --- | --- | --- | --- |
| A. 回边触发整函数编译，但下次调用才生效 | 低 | 低 | 低 | 不推荐作为主方案 |
| B. 整函数编译 + loop header secondary entry | 中高 | 中高 | 高 | **推荐** |
| C. tracing JIT / side trace | 极高 | 极高 | 高 | 不推荐 |

### 推荐主方案

推荐 **B**。

原因可以压缩成一句话：

- 它是“唯一真正解决问题，同时又不推翻现有 CinderX 3.14 JIT 架构”的方案。

### 如果最后证明不值得做

退出条件我建议设成：

- Phase 0 无法在 outermost object-only loop 上稳定实现 frame adoption + deopt round-trip。

若出现这个结果，替代建议是：

- 不做 upward OSR；
- 退回方案 A；
- 并把资源继续投在：
  - hot-call 路径；
  - loop-body HIR 优化；
  - benchmark 定向 jit-list / force_compile tooling。

## Phased Rollout Plan / 分阶段落地计划

### Phase 0：验证 / 原型

目标：

- 证明“解释器 frame -> loop-header secondary entry -> deopt 回解释器”闭环可行。

范围：

- 单 benchmark / 单测试函数；
- 单个 outermost loop header；
- object-only live-ins；
- 无异常块；
- 无 generator / async。

建议工作：

- 在 `builder.cpp` 里挑出一个可 OSR 的 loop header。
- 手工或半自动生成一个 OSR secondary entry。
- 写一个只面向该 loop 的 runtime helper，把当前 frame 搬进去。
- 确认 guard failure 能从 OSR-entered code 正常走回解释器。

验证标准：

- 同一个函数只调用一次，也能在 loop 中途进入 compiled code。
- deopt 后结果正确。
- 不出现 double-link / double-pop frame bug。

### Phase 1：MVP

目标：

- 自动化支持 once-call hot loop 的基础 OSR。

范围：

- `JUMP_BACKWARD_JIT` 驱动；
- outermost, reducible, object-only loops；
- instrumentation off；
- no generator / async / active exception block。

必须先写的测试（TDD）：

- Python 回归：
  - 单次调用函数，内部 loop 很热，最终 `jit.is_jit_compiled(func)` 之外还能观察到“本次 activation 已进入 compiled loop”。
- Runtime/C++：
  - OSR metadata 生成；
  - OSR entry 地址存在；
  - φ 输入和 snapshot 对齐；
  - deopt round-trip。
- 远端验证：
  - 统一走 `scripts/push_to_arm.ps1 -> scripts/arm/remote_update_build_test.sh`。

成功标准：

- 目标回归通过；
- 自定义 once-call hot-loop benchmark 出现稳定收益；
- 无明显 correctness regressions。

### Phase 2：扩展支持范围

目标：

- 从“可用”扩展到“实用”。

扩展方向：

- primitive live-ins；
- 更多 loop 形态；
- exception region；
- 与 inlining 的配合；
- 更合理的 hot-loop compile / OSR heuristics；
- OSR stats / telemetry / suppression。

## Risks And Test Plan / 风险与测试计划

### 1. 主要风险

- φ / synthetic predecessor 风险
  - loop header 不是随便 jump 进去就合法，必须有一条语义正确的 OSR predecessor。
- frame ownership 风险
  - normal entry 和 OSR entry 的 frame 生命周期不同。
- 3.14 tier2 干扰风险
  - `JUMP_BACKWARD_JIT` 现在已经服务 `_Py_TIER2`。
- metadata 体积风险
  - 每个 loop header 都加 secondary entry / metadata，代码和内存都会膨胀。
- compile thrash 风险
  - 单次 activation 里边回边热度可能刚过阈值就触发 compile，若 loop 很短，收益可能不够覆盖 compile 成本。

### 2. 测试策略

#### 单元 / RuntimeTests

- `cinderx/RuntimeTests`
  - 新增 OSR metadata 构造测试；
  - 新增 OSR entry label / frame layout 测试；
  - 新增 OSR-entered deopt 测试。

#### Python 回归

- `cinderx/PythonLib/test_cinderx`
  - once-call hot loop 基础回归；
  - for / while 两种 loop；
  - exception pending / signal handling；
  - instrumentation 开关下应禁用或回退。

#### 性能

- 自定义微基准：
  - 单次调用 + 热循环。
- pyperformance 子集：
  - 优先选择 loop 主导型 benchmark。
- 指标：
  - 首次 activation 的总耗时；
  - steady-state loop 段耗时；
  - compile 开销；
  - 触发阈值敏感性。

### 3. 统一验证入口

按本仓库当前约定，后续可执行验证统一走：

- Windows 入口：
  - `scripts/push_to_arm.ps1`
- ARM 统一远端入口：
  - `scripts/arm/remote_update_build_test.sh`

说明：

- 本次 issue 76 交付物是研究/设计文档，没有 runtime 代码改动；
- 因此本轮没有实际执行远端 ARM build/test；
- 后续 Phase 0/1 的任何可执行验证都应统一走这条远端入口，并把关键结果写入同目录 `findings.md`。

## Final Recommendation / 最终结论

- 当前 CinderX 3.14 已经具备：
  - 函数级编译；
  - 完整 deopt；
  - 解释器热回边挂点；
  - 多 secondary entry 的 codegen 先例。
- 因此，**热循环驱动 OSR 在 3.14 上是有现实可行路径的**。
- 最合理的工程方向不是 tracing JIT，而是：
  - **整函数编译 + loop header secondary entry + 新的 upward OSR metadata**。
- 这条路线的关键风险集中在：
  - interpreter frame adoption；
  - loop-header φ 语义；
  - backward-branch hotness 与 tier2 的协作。
- 如果 Phase 0 能把这三个点跑通，我认为这个方向值得继续推进到 MVP。
