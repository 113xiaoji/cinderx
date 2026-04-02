# `generators`：为什么它的根因是 generator attr/resume/decref，而不是普通循环速度

## 1. benchmark 本体在做什么

`bm_generators` 做两件事：

1. `tree(range(100000))` 递归构造一棵二叉树；
2. 在 `Tree.__iter__()` 里递归 `yield from self.left` / `yield self.value` / `yield from self.right`。

这意味着热点主要在：

- `Tree.__iter__()`
- `yield from`
- generator resume/suspend
- `Tree.left/value/right` 属性读取

它并不是普通 `for` 循环 benchmark，而是一个 generator runtime benchmark。

## 2. 基准 CPython 分支的关键执行链

在基准 CPython 上，主要成本是：

- generator frame 推进
- `yield from` 状态转换
- 对 `left/right/value` 的属性读取
- 大量引用计数与对象生命周期管理

所以平台比值更多由：

- generator runtime
- attr load
- refcount/decref

共同决定。

## 3. 切到 CinderX 后，已知的关键差异

这里其实已经有比较明确的专项 findings。

### 3.1 low-local generator attr lowering 曾经缺失

已有 findings 明确指出：

- 低 local 数量的 generator helper 之前没有走现有 `LOAD_ATTR_INSTANCE_VALUE` lowering
- 放开之后，测试形状中的 `LoadAttrCached` C helper 调用可以消失

这说明 `generators` 的真实问题并不是“生成器本身一定慢”，而是：

- generator 里的 attr 访问之前没有被 lowering 到位

### 3.2 decref 仍然是剩余压力点

已有 findings 还确认：

- `Decref` 仍然很多
- `BatchDecref` 仍然没有充分出现

这意味着当前分支虽然修了一部分 generator attr 路径，但 refcount 清理仍然是剩余成本。

## 4. 静态机器码层面，为什么 Arm 更容易在这里吃亏

### 4.1 generator resume / yield-from 在 AArch64 上更重

已有 backend 分析已经说明：

- generator/coroutine resume 路径在 AArch64 上依赖更多 `ptr_resolve()` 与 `ldr/str`
- x86_64 往往可以更直接地用基址+偏移访问 frame metadata

`generators` 正好极高频地命中这些路径。

### 4.2 decref 链在 AArch64 上更容易表现为显式 load/store 压力

当 benchmark 本身大量产生：

- yield 点
- 临时 generator 状态
- 左右子树递归 frame

剩余的 `Decref` 成本就会不断暴露。  
而 AArch64 对这类碎的对象生命周期开销通常比 x86_64 更敏感。

## 5. JIT 侧应怎样理解

这个 benchmark 的 JIT 重点不是数值 opcode，而是：

- `yield from` lowering
- generator attr lowering
- decref / batch decref 形状

当前分支已经有两条重要进展：

1. generator 的 attr lowering 改善了；
2. generator-only decref lowering 也有推进。

但 findings 也明确说了：

- 剩余 decref 压力仍在

因此 `generators` 的问题状态应理解为：

- 主因已基本定位；
- 当前分支已有部分修复；
- 剩余平台比值差距仍可能来自 generator resume + decref 在 Arm 上更重。

## 6. 为什么平台比值会从 CPython 切到 CinderX 后继续恶化

最合理的解释链是：

1. benchmark 核心是 generator runtime，不是普通循环；
2. CinderX 在 generator 路径上有自己的 lowering 与 runtime；
3. 历史上 generator attr lowering 不足，曾额外引入 helper/cached attr 成本；
4. 即使这部分已修复，剩余 decref 与 frame glue 在 AArch64 上仍更重；
5. 因此从基准 CPython 到 CinderX，Arm 的相对损失更容易大于 AMD/x86_64。

## 7. 结论

`generators` 应独立成一个 generator 专项簇。  
它最该看的不是：

- 纯解释器 bookkeeping
- 纯浮点 JIT

而是：

- generator attr lowering
- `yield from` / resume 路径
- decref / batch decref

如果平台比值在 CinderX 上明显更差，最强解释仍然是：

- CinderX 的 generator 路径相对基准 CPython 更复杂
- 而这些新增复杂度在 AArch64 上的代价大于 AMD/x86_64

