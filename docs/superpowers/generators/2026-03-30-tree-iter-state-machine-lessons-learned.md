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

| 项目 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| ~~性能基准测试~~ | ~~高~~ | ✅ 完成 | pyperformance bm_generators: macOS 11.9x, kunpeng 14.1x |
| ~~清理提交~~ | ~~高~~ | ✅ 完成 | 10 commits, 合理拆分 |
| ~~内联优化~~ | ~~低~~ | ✅ 完成 | 8/8 操作原生 LIR codegen |
| deopt 支持 | 中 | 📋 待做 | 当前 YieldValue 用复制的 FrameState，不支持 deopt 回退 |
| 栈容量扩展 | 低 | 📋 待做 | 当前 16 entries（depth <= 12），可扩展到更大 |
| x86_64 验证 | 中 | 📋 待做 | translate 函数包含 x86_64 分支但未在 x86_64 平台测试 |
| checked-in 回归测试 | 中 | 📋 待做 | 缺少 PYTHONJITTREEITERSTATEMACHINE=1 的 CI 回归测试 |

---

## 坑 7: hasArbitraryExecution 过度优化导致正确性失败

### 现象

将 kSavePhase/kLoadCurrentNode 等 opcode 的 `hasArbitraryExecution` 从 `true` 改为 `false` 后，`test_phase3_state_machine.py` 仍然输出 "pass 触发次数: 1" 且 exit 0。
但实际遍历结果错误：depth=3 返回 `[1, 1, 1]`（只有左叶节点）而非正确的 `[1, 2, 1, 3, 1, 2, 1]`。

### 根因

`hasArbitraryExecution = false` 允许 HIR 优化器做以下优化：
- **CSE（公共子表达式消除）**：多个 `LoadPhase` 被合并为一个，但状态机循环中每次 `SavePhase` 后 `current_phase` 已改变，后续 `LoadPhase` 必须重新读取
- **DSE（死存储消除）**：`SavePhase` 的写入可能被判定为死存储而消除

kSavePhase 是**写入操作**，标记为 `false` 后优化器消除了关键的状态转换 → 状态机永远停留在 kLeft phase → 只遍历左子树叶节点。

### 为什么测试没发现

**构建缓存问题**：首次提交时 `python setup.py build_ext --inplace` 编译成功，但 CMake 增量构建可能没有重新编译所有依赖文件。测试实际运行的是旧二进制（未应用 hasArbitraryExecution 改动），因此通过了。

后续修改了其他文件（generator.cpp、autogen.cpp）触发完整重编译后，hasArbitraryExecution 的改动才真正生效，测试才暴露问题。

### 修复

只将**纯读取**操作标记为 `false`：
- ✅ kLoadPhase：只读 GenDataFooter.current_phase
- ✅ kLoadPoppedPhase：只读 GenDataFooter.popped_phase
- ✅ kLoadStackTop：只读 GenDataFooter.stack_top

写入和含副作用操作必须保留 `true`：
- ❌ kSavePhase：写入 GenDataFooter，CSE/DSE 会破坏状态转换
- ❌ kLoadCurrentNode：含 Py_INCREF，不能被消除
- ❌ kSaveCurrentNode：含 Py_DECREF + Py_INCREF
- ❌ kStateStackPush/Pop：含 refcount 操作

### 教训

1. **HIR 优化标记不能随意改** — `hasArbitraryExecution` 控制优化器的行为边界，写入操作必须标记为 `true`
2. **增量构建不可靠** — 每次改动 HIR 层代码后应 clean build 验证
3. **测试需要更全面** — 当前测试只检查最终遍历结果，缺少：
   - 循环迭代稳定性（多次 `list(t)` 同一棵树）
   - 性能回归检测（ON/OFF 对比）
   - 多深度连续测试（d1→d12 循环）

---

## 坑 8: translate 函数寄存器冲突（从未执行的代码路径）

### 现象

将 StateStackPush/Pop 从 C 调用改为原生 LIR 指令后，depth≥3 时 SIGSEGV。

### 根因

`autogen.cpp` 中 `translateStateStackPush` 的 AArch64 实现有寄存器冲突：

```cpp
// Step 1: 加载 stack_top 到 w12（x12 低 32 位）
as->ldr(a64::w12, ptr_resolve(...));

// Step 2: mov x12, offset  ← 覆盖了 w12！stack_top 值丢失！
as->mov(arch::reg_scratch_0, stack_base_offset);  // reg_scratch_0 = x12
as->add(arch::reg_scratch_0, arch::fp, arch::reg_scratch_0);
as->lsl(a64::x13, a64::x12, 4);  // x12 已被覆盖，不是 stack_top
```

`x12`（reg_scratch_0）和 `w12` 是同一寄存器。Step 2 的 `mov` 覆盖了 Step 1 加载的 stack_top。

### 为什么一直没发现

LIR generator 一直用 `appendInvokeInstruction`（创建 `kCall` LIR 指令），走标准 C 函数调用路径。BEGIN_RULES 中的 `CALL_C(translateStateStackPush)` 虽然存在，但 opcode `kStateStackPush` 的指令从未被生成过 → translate 函数从未执行 → bug 从未触发。

### 教训

**未执行代码不等于正确代码** — BEGIN_RULES 中有 translate 函数不代表它被使用过。验证方式：在 translate 函数中加 `JIT_ABORT` 断言，如果 C 调用路径在用，不应触发。

---

## 坑 9: PYTHONJITAUTO 环境变量不等于 auto() 激活

### 现象

使用 `PYTHONJIT=1 PYTHONJITAUTO=50 python run_benchmark.py --worker` 运行 pyperformance 基准测试，结果与无 JIT 完全相同（~36ms），"优化"和"基线"数据一致。

### 根因

`PYTHONJITAUTO=N` 仅设置编译阈值配置，**不激活自动编译功能**。必须显式调用以下之一：
- `cinderx.jit.auto()` — 激活自动编译（默认阈值 1000）
- `cinderx.jit.compile_after_n_calls(N)` — 激活自动编译（自定义阈值）

pyperformance 的 `run_benchmark.py` 不会调用这些函数，因此即使设置了 `PYTHONJITAUTO=50`，JIT 也不会编译任何用户函数。

### 验证方法

```bash
# 错误: 无 JIT 编译
PYTHONJIT=1 PYTHONJITAUTO=50 python3.14 run_benchmark.py --worker -l5 -w11 -n2

# 正确: 激活 JIT 编译
python3.14 -c "
import cinderx.jit
cinderx.jit.compile_after_n_calls(50)
exec(open('run_benchmark.py').read())
"
```

### 教训

**环境变量设置阈值 ≠ 激活编译**。必须在 Python 代码中调用 `auto()` 或 `compile_after_n_calls()` 才能激活。pyperformance 测试需要包装脚本。

---

## 坑 10: 低 AUTO 阈值编译标准库函数导致 segfault

### 现象

使用 `PYTHONJITAUTO=2`（或 10）+ `compile_after_n_calls(2)` 在 kunpeng 上运行基准测试，无论是否启用状态机优化，均 segfault。

### 根因

`compile_after_n_calls(2)` 激活自动编译后，**所有函数**（包括标准库）在调用 2 次后都会被 JIT 编译。kunpeng 上的编译路径中，`enum.Flag.__or__` 等标准库函数触发 `!stack_.empty()` 断言失败 → segfault。

此 bug 与状态机优化无关，是 JIT 编译器自身的限制。

### 解决方案

使用 `PYTHONJITLISTFILE` 限制编译范围：

```bash
# 只编译目标函数
echo "__main__:Tree.__iter__" > /tmp/jitlist.txt
echo "__main__:tree" >> /tmp/jitlist.txt
echo "__main__:bench_generators" >> /tmp/jitlist.txt

PYTHONJIT=1 PYTHONJITAUTO=2 \
  PYTHONJITLISTFILE=/tmp/jitlist.txt PYTHONJITENABLEJITLISTWILDCARDS=1 \
  python3.14 run_benchmark.py --worker -l5 -w11 -n2
```

### 教训

**低 AUTO 阈值需要 JITLIST 保护**。AUTO=2 编译所有函数（含 stdlib），某些函数会触发 JIT 编译器 bug。高 AUTO 阈值（≥50）通常安全，因为标准库函数很少单独被调用 50+ 次。
