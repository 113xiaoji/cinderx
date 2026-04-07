## 标题

hot-loop OSR profitability: object-heavy / search-heavy workloads regress under same-activation OSR

## 背景

issue #76 的 Phase 1 hot-loop OSR 已经完成了 same-activation loop entry 的正确性修复，并且在一批典型的“单次调用内长时间运行的稳定热循环”上带来了收益，例如：

- `fannkuch`
- `unpack_sequence`
- `comprehensions`
- `scimark` 的 `MonteCarlo`
- `scimark` 的 `SOR`
- `bpe_tokeniser`

但在另一类 workload 上，same-activation hot-loop OSR 不是收益不明显，而是会出现稳定回退。

## 问题描述

当前 Phase 1 hot-loop OSR 的触发条件仍然偏粗：

- 主要依据“当前函数是否有 backedge / 当前 loop 是否变热”
- 没有进一步区分这是不是一个适合 Phase 1 的 loop kernel

这会把一些并不适合当前 Phase 1 的函数也送进 same-activation OSR，例如：

- 大量对象状态更新
- 大量属性访问和方法调用
- 状态图遍历 / 搜索 / Monte Carlo tree search
- 几何对象运算
- 不是“单个稳定热循环主导”的函数

## 复现与证据

在当前分支、ARM、direct benchmark probe 的结果里，这类 case 有稳定回退：

### `bm_go`

- baseline: 解释执行 `versus_cpu()` 中位数约 `0.1459s`
- 编译所有 backedge 函数：约 `+62.0%`
- 只编 `Board.useful`：约 `+69.3%`
- 只编 `UCTNode.play`：约 `+77.6%`
- `Board.useful + UCTNode.play + UCTNode.random_playout`：约 `+73.8%`

这说明问题不是“编太多了”而已，而是这些核心对象/搜索函数本身就不适合当前 Phase 1。

### `bm_chaos`

- 解释执行 baseline
- 只编 `Chaosgame.create_image_chaos`：约 `+0.96%`
- 只编 `Chaosgame.transform_point`：约 `+4.26%`
- `create_image_chaos + transform_point + get_random_trafo`：约 `+0.30%`

同样是 object-heavy / geometry-heavy 形状，收益很弱甚至为负。

## 形状特征

这类回退 case 的共同点不是“没有回边”，而是：

- 回边循环里充满对象访问，而不是局部数值/容器 kernel
- `LOAD_ATTR/STORE_ATTR`、调用、状态更新密度很高
- 运行时成本更多在对象图、方法调度、状态迁移，而不是解释器循环派发本身

从字节码形状上看，典型例子：

- `Board.useful`
  - `jump_backward = 4`
  - `attr_ops = 24`
  - `call_ops = 5`
- `UCTNode.play`
  - `jump_backward = 1`
  - `attr_ops = 13`
  - `call_ops = 8`
- `Chaosgame.transform_point`
  - `jump_backward = 0`
  - `attr_ops = 25`
  - `call_ops = 10`

与此相对，真正有收益的 case 更像：

- 回边稳定
- 局部循环主导
- 对象状态访问密度低
- 热点集中在少数 kernel 内

## 为什么这不是 issue #76 的 blocker

issue #76 的目标是：

- 实现 Phase 1 same-activation hot-loop OSR 的正确性
- 让适合该路径的窄范围 loop kernel 真正进入 JIT

这已经完成。

这里暴露的是下一层问题：

- current Phase 1 对 profitability 的判断还不够细
- object-heavy / search-heavy workload 需要单独的 gate 或后续优化策略

因此这应当作为单独 follow-up，而不是回滚 issue #76 的主修复。

## 建议修复方向

### 方向 1：在 hot-loop OSR 入口增加 profitability gate

位置优先考虑：

- `cinderx/Jit/pyjit.cpp`
  - `_PyJIT_TryHotLoopOSR()`
  - `ensureCompiledForHotLoopOSR()`

目标：

- 不是所有 “backedge + 变热” 的函数都允许 same-activation OSR
- 对 object-heavy / search-heavy / state-machine-heavy 函数默认更保守

### 方向 2：把 `codeHasBackedge()` 从必要条件升级为“必要但不充分”

位置优先考虑：

- `cinderx/Jit/hir/builder.cpp`

当前逻辑里，“有 backedge” 已经足够让某些 specialization / hot-loop 路径打开。后续应考虑引入更细的 shape score，而不是只依赖一个布尔量。

### 方向 3：优先尝试通用 shape heuristic，而不是 benchmark 黑名单

建议避免直接按 benchmark 或函数名拉黑。

更合适的是通用规则，例如：

- 属性访问 / 调用 / 下标访问密度过高时，不走 same-activation hot-loop OSR
- 状态迁移 / 搜索型函数默认不走 current Phase 1
- 只让更像 loop kernel 的函数进入这条路径

## 验证标准

后续修复应至少验证：

- `bm_go` 不再出现当前量级的回退
- `bm_chaos` 不再出现稳定负收益
- `fannkuch`、`unpack_sequence`、`comprehensions`、`scimark MonteCarlo/SOR` 等当前正收益 case 不被明显伤害
- issue #76 的正确性测试继续保持通过

## 备注

另有一类 “回退” 更像是 over-compile / wrapper pollution，而不是 object-heavy 本身，例如：

- `barnes_hut`
- 某些模块级 direct probe 的 `scimark_lu`

这类可以作为更小的 profitability follow-up 处理，但不应和 object-heavy 这条 issue 混为一谈。
