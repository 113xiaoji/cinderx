# TreeIterStateMachinePass 实现经验总结

> 日期: 2026-03-30
> 状态: 功能完成，5/5 测试通过，depth 1-12（1~4095 节点）全部正确

## 概述

TreeIterStateMachinePass 是 CinderX JIT 编译器的一个 HIR 优化 pass，用于将树遍历生成器（`yield from self.left; yield self.value; yield from self.right`）编译为显式状态机，消除递归帧切换开销。

实现采用 GenDataFooter 驱动的状态机架构（非 SSA Phi），通过 16 个基本块模拟中序遍历的递归行为。

## 改动文件

共 23 个文件，+1228/-748 行。

| 文件 | 改动说明 |
|------|---------|
| `Jit/hir/tree_iter_state_machine_pass.cpp` | 状态机生成器主体（模式检测 + CFG 生成） |
| `Jit/hir/tree_iter_state_machine_pass.h` | StateMachineContext + StateMachineGenerator 类定义 |
| `Jit/jit_rt.cpp` / `jit_rt.h` | 8 个运行时函数（LoadCurrentNode, SaveCurrentNode, StateStackPush 等） |
| `Jit/gen_data_footer.h` | GenDataFooter 扩展（current_node, current_phase, state_stack[16]） |
| `Jit/hir/hir.h` | 10 个新 HIR 指令类定义 |
| `Jit/hir/hir_ops.h` | 新 opcode 枚举 |
| `Jit/hir/instr_effects.cpp` | 内存效果标注 |
| `Jit/hir/pass.cpp` | 输出类型推断 |
| `Jit/hir/printer.cpp` | 调试输出格式化 |
| `Jit/hir/hir.cpp` | isReplayable/isPassthrough |
| `Jit/lir/generator.cpp` | LIR lowering（C 运行时调用） |
| `Jit/lir/instruction.h` | LIR 指令类型注册 |
| `Jit/codegen/autogen.cpp` | AArch64 codegen 规则 |

---

## 坑 1: 引用计数 — 运行时函数必须自己管理 refcount

### 现象

depth=2（3 节点）测试通过，depth>=3（4+ 节点）SIGSEGV 崩溃。调试日志显示同一节点在 SaveCurrentNode 时字段正确（left=None, right=None），但 LoadCurrentNode 时字段变为 0x0。

### 根因

JIT 的 RefcountInsertion pass 对所有 TObject/TOptObject 类型寄存器自动插入 XDecref。运行时函数（LoadCurrentNode, StateStackPop）返回的是**借用引用**（borrowed ref，没有 incref），XDecref 会把 refcount 减到 0，导致对象被释放、内存损坏。

为什么 depth=2 恰好通过：只有一个 LoadField 寄存器被 XDecref，对象的 refcount 恰好没降到 0（被树结构保持引用）。depth>=3 时多个 LoadField 结果被 XDecref，中间节点的 refcount 真的降到 0，触发释放和内存重用。

### 修复

在所有返回/存储 PyObject* 的运行时函数中正确管理引用计数：

```cpp
// SaveCurrentNode: decref 旧值，incref 新值
void JITRT_SaveCurrentNode(PyObject* node) {
  GenDataFooter* footer = ...;
  PyObject* old = (PyObject*)footer->current_node;
  if (old) Py_DECREF(old);       // 释放 GenDataFooter 持有的旧引用
  if (node) Py_INCREF(node);     // GenDataFooter 持有新引用
  footer->current_node = (int64_t)node;
}

// LoadCurrentNode: incref 返回值
PyObject* JITRT_LoadCurrentNode() {
  GenDataFooter* footer = ...;
  PyObject* result = (PyObject*)footer->current_node;
  if (result) Py_INCREF(result);  // 给寄存器一份独立引用
  return result;                   // RefcountInsertion 的 XDecref 会释放这份引用
}

// StateStackPush: incref 入栈值
void JITRT_StateStackPush(PyObject* node, int32_t phase) {
  ...
  if (node) Py_INCREF(node);  // 栈持有引用
  footer->stack_top = top + 1;
}

// StateStackPop: 转移栈引用给调用者（不 incref）
PyObject* JITRT_StateStackPop() {
  ...
  return node;  // 栈引用直接转移，XDecref 会释放
}
```

### 教训

**CinderX JIT 中，任何返回 PyObject* 的运行时函数，如果返回值会被存入寄存器，必须 Py_INCREF。** RefcountInsertion 不区分 owned/borrowed reference。

---

## 坑 2: SSA 违规 — insert 位置必须保证定义先于使用

### 现象

SIGSEGV 崩溃（exit 139），无输出。

### 根因

在 bb_init 中，需要将 SaveCurrentNode 和 SavePhase 插入到 InitialYield **之前**（因为 InitialYield 会 clobber 寄存器）。使用辅助函数 `CreatePhaseConst` 创建 LoadConst：

```cpp
// CreatePhaseConst 使用 bb->append<LoadConst>，追加到块末尾
Register* init_phase = CreatePhaseConst(func, bb_init_, TreeIterPhase::kLeft);
auto* save_phase = SavePhase::create(init_phase);
bb_init_->insert(save_phase, init_iter);  // 插入到 InitialYield 前
```

`BasicBlock::insert(instr, iterator)` 在 iterator 位置**之前**插入。但 `CreatePhaseConst` 使用 `bb->append` 追加到块**末尾**（InitialYield 之后）。

运行时指令顺序变成：
```
LoadArg(0) → self_reg
SaveCurrentNode(self_reg)        ← 正确
SavePhase(init_phase)            ← BUG! init_phase 尚未计算
InitialYield                     ← yield/resume
LoadConst → init_phase           ← 定义在这里，太晚了
```

SavePhase 引用了在 InitialYield 之后才定义的 init_phase 寄存器 → SSA 违规 → SIGSEGV。

### 修复

不用 `CreatePhaseConst`（它用 append），直接创建 `LoadConst::create` 再用 `insert`：

```cpp
Register* init_phase = env.AllocateRegister();
auto* load_phase = LoadConst::create(
    init_phase, Type::fromCInt(static_cast<int>(TreeIterPhase::kLeft), TCInt32));
bb_init_->insert(load_phase, init_iter);   // InitialYield 前
auto* save_phase = SavePhase::create(init_phase);
bb_init_->insert(save_phase, init_iter);   // InitialYield 前
```

### 教训

在已有指令（如 InitialYield）前插入多条指令时，所有新指令都必须用 `insert` 而非 `append`。辅助函数如果用 append 就不能用于这种场景。

---

## 坑 3: InitialYield 会 clobber 寄存器

### 现象

SaveCurrentNode 保存了错误的节点地址。

### 根因

InitialYield 导致 generator yield/resume cycle，**所有 caller-saved 寄存器被覆盖**。如果 SaveCurrentNode(self_reg) 在 InitialYield 之后执行，self_reg 已经是垃圾值。

### 修复

整个 bb_init 的指令顺序必须保证 SaveCurrentNode 和 SavePhase 在 InitialYield **之前**：

```
LoadArg(0) → self_reg
SaveCurrentNode(self_reg)     ← InitialYield 前
LoadConst(kLeft) → init_phase ← InitialYield 前
SavePhase(init_phase)          ← InitialYield 前
InitialYield                   ← yield/resume, clobber 所有 caller-saved 寄存器
Branch(bb_loop)
```

### 教训

在 CinderX JIT 中，任何涉及 yield/resume 的指令都会 clobber caller-saved 寄存器。所有需要保留的值必须在 yield 之前存储到不会被 clobber 的位置（如 GenDataFooter）。

---

## 坑 4: YieldValue 需要 FrameState

### 现象

构造 YieldValue 时编译报错或运行时崩溃。

### 根因

YieldValue 继承 DeoptBase，构造函数**必须**接收 FrameState 参数：`YieldValue(dst, value, frame)`。

### 当前做法

从原始 YieldValue 指令提取 FrameState 并复用：

```cpp
// 在 generateStateMachine 中提取
FrameState* yield_frame_state = nullptr;
for (auto& block : func.cfg.blocks) {
  for (auto& instr : block) {
    if (instr.IsYieldValue()) {
      yield_frame_state = static_cast<YieldValue*>(&instr)->frameState();
      break;
    }
  }
}

// 在 bb_yield 中使用
bb_yield->append<YieldValue>(yield_result, yield_value, *ctx_.yield_frame_state);
```

### 已知限制

当前实现不支持 deopt。如果触发 deopt，FrameState 中的信息不足以恢复到正确的状态机状态。后续任务需要完善。

---

## 坑 5: GenDataFooter 替代 Phi 节点的设计选择

### 问题

状态机有循环变量（current_node, phase, stack_top），在 SSA 形式下需要 Phi 节点处理自引用：

```
current = Phi({
  bb_init: self,
  bb_has_left: left_child,
  bb_no_left: current,      // 自引用！
  bb_pop: popped_node
})
```

Phi 自引用在 CinderX 中难以正确处理，且 CopyPropagation pass 在状态机 pass 之后不运行。

### 解决方案

用 GenDataFooter 作为可变状态存储，每次循环从 GenDataFooter 加载/保存状态：

- `SaveCurrentNode(reg)` → 写 GenDataFooter.current_node
- `LoadCurrentNode()` → 读 GenDataFooter.current_node
- `SavePhase(reg)` → 写 GenDataFooter.current_phase
- `LoadPhase()` → 读 GenDataFooter.current_phase

### 优缺点

| 优点 | 缺点 |
|------|------|
| 避免 Phi 自引用问题 | 每次状态读写是 C 函数调用（~5-10ns/操作） |
| 不需要 CopyPropagation | 不支持 deopt |
| 代码直观，类似 C 状态机 | GenDataFooter 内存占用增加 ~300 bytes |

---

## 坑 6: None vs nullptr 检查

### 问题

Python 中 `None` 存储为 `Py_None` 指针（非 StaticPython），不是 C 的 `nullptr`。StaticPython 内联存储可能用 `nullptr`。

### 解决

两个基本块链式检查：

```cpp
// bb_left: 先比较 Py_None
bb_left->append<LoadConst>(none_left, Type::fromObject(Py_None));
bb_left->append<PrimitiveCompare>(cmp_none_left, kEqual, left_child, none_left);
bb_left->append<CondBranch>(cmp_none_left, bb_no_left, bb_check_null_left);

// bb_check_null_left: 再比较 nullptr（兼容 StaticPython）
bb_check_null_left->append<LoadConst>(null_left, Type::fromCInt(0, TCInt64));
bb_check_null_left->append<PrimitiveCompare>(cmp_null_left, kEqual, left_child, null_left);
bb_check_null_left->append<CondBranch>(cmp_null_left, bb_no_left, bb_has_left);
```

---

## 状态机基本块结构

```
bb_init ──→ bb_loop ──→ bb_left ──→ bb_check_null_left ──→ bb_has_left ──→ bb_loop
  │             │                └──→ bb_no_left ──→ bb_loop
  │             ├──→ bb_check_yield ──→ bb_yield ──→ bb_after_yield ──→ bb_loop
  │             ├──→ bb_check_right ──→ bb_right ──→ bb_check_null_right ──→ bb_has_right ──→ bb_loop
  │             │                                      └──→ bb_no_right ──→ bb_loop
  │             └──→ bb_backtrack ──→ bb_pop ──→ bb_loop
  │                            └──→ bb_done (Return None)
```

共 16 个基本块，包含：
- 1 个 init 块（LoadArg + SaveCurrentNode + SavePhase + InitialYield）
- 1 个 loop 块（LoadPhase + 3 路 dispatch）
- 4 个 left/right 子树检查块（None + nullptr 双重检查）
- 2 个 has_child 块（push + save child）
- 2 个 no_child 块（转换 phase）
- 1 个 yield 块（LoadField(value) + YieldValue）
- 1 个 backtrack 块（LoadStackTop + 空栈检查）
- 1 个 pop 块（StateStackPop + LoadPoppedPhase + SaveCurrentNode）
- 1 个 done 块（Return Py_None）

---

## 测试策略

### 探针测试（验证 pass 是否被触发）

```python
# C 侧定义探针计数器
extern "C" int g_state_machine_pass_triggered{0};

# Python 侧读取
from cinderx import get_state_machine_pass_triggered, reset_state_machine_pass_triggered
triggered = get_state_machine_pass_triggered()
assert triggered > 0  # 验证 pass 被触发
```

### 正确性测试

- depth=3（7 节点）和 depth=5（31 节点）的中序遍历正确性
- 单节点、左右子树、不对称树
- 非树遍历生成器不应触发 pass

### 边界测试

- depth 1-12（1~4095 节点）全部验证
- depth=12 是栈容量 16 entries 的上限（最大 2^12-1 = 4095 节点）

---

## 后续工作

| 项目 | 优先级 | 说明 |
|------|--------|------|
| 性能基准测试 | 高 | 量化状态机 vs 原始生成器的加速比 |
| 清理提交 | 高 | 整理代码，拆分合理提交 |
| deopt 支持 | 中 | 当前 YieldValue 用复制的 FrameState，不支持 deopt 回退 |
| 栈容量扩展 | 低 | 当前 16 entries（depth <= 12），可扩展到更大 |
| 内联优化 | 低 | 将 C 运行时调用替换为内联汇编，减少函数调用开销 |
