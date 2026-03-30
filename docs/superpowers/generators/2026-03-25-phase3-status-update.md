# Phase 3 状态更新

**日期**: 2026-03-26
**更新**: Phase 3.2 T5 大部分完成（模式检测 ✅，SSA Phi 架构 ✅，CFG 集成 ❌）

---

## 当前状态

### Phase 3.1: 逃逸分析 - ✅ 完成

**完成时间**: 2026-03-25（2 天）
**性能改进**: 0.6%（架构限制）

### Phase 3.2: 状态机内联 - 🚧 进行中（~75%）

**开始时间**: 2026-03-25
**当前进度**: T1-T4 完成，T5 部分完成（模式检测 + SSA 架构），T6-T7 待实现

**已完成**:
- ✅ T1: 基础设施准备（配置常量、栈布局、测试框架）
- ✅ T2: StateMachineGenerator 类（7 个基本块方法）
- ✅ T3: 集成到 TreeIterStateMachinePass（模式检测、YieldFrom 替换、控制流连接）
- ✅ T4: 栈操作实现（GenDataFooter 栈数组 + StateStackPush/Pop 全链路）
- ✅ T5.1-T5.5: 状态机逻辑实现（详见下方）
  - ✅ 字段偏移量提取（TreeIterFieldInfo）
  - ✅ LoadPoppedPhase HIR 指令（全链路：opcode → HIR → LIR → x86/ARM codegen）
  - ✅ LoadStackTop HIR 指令（全链路）
  - ✅ SSA Phi 形式重构（替换可变寄存器模型）
  - ✅ 所有基本块的真实指令（LoadField、StateStackPush、YieldValue、LoadStackTop、StateStackPop、LoadPoppedPhase）
  - ✅ Phi 节点插入（2 个 Phi：current、phase，7 个前驱块）
  - ✅ 探针测试 5/5 通过
- ❌ T5.6: CFG 集成（阻塞项）
- ❌ T6: 边界情况处理（depth=0/1/12/15、回退验证）
- ❌ T7: 最终验证（4-6x 性能目标）

**文档**:
- [设计文档](./specs/2026-03-25-phase3.2-state-machine-inlining-design.md)
- [实施计划](./plans/2026-03-26-phase3.2-state-machine-inlining-implementation-plan.md)
- [Task 4 决策](./decisions/2026-03-26-phase3.2-task4-stack-implementation-decision.md)
- [Task 5 进度报告](./diagnostics/2026-03-26-phase3.2-task5-progress-report.md) ⭐ 最新

---

## Phase 3.2 架构

```
┌─────────────────────────────────────────────────────────┐
│ T1-T4: 基础设施 + 框架 + codegen ✅                       │
│ ├─ TreeIterPhase 枚举、StateMachineConfig 常量           │
│ ├─ StateMachineGenerator（SSA Phi 形式，7 个基本块）      │
│ ├─ TreeIterStateMachinePass（模式检测 + 字段提取）        │
│ ├─ StateStackPush/Pop HIR/LIR/codegen 全链路             │
│ ├─ LoadPoppedPhase HIR/LIR/codegen 全链路                │
│ ├─ LoadStackTop HIR/LIR/codegen 全链路                   │
│ └─ GenDataFooter 扩展（state_stack[16]）                 │
├─────────────────────────────────────────────────────────┤
│ T5: 状态机逻辑实现 🚧 ~85% 完成                           │
│ ├─ SSA Phi 架构重构 ✅                                   │
│ ├─ 字段偏移量提取（TreeIterFieldInfo）✅                 │
│ ├─ 新增 HIR 指令（LoadPoppedPhase, LoadStackTop）✅      │
│ ├─ 所有基本块真实指令 ✅                                  │
│ ├─ Phi 节点插入（2 Phi, 7 前驱）✅                       │
│ ├─ 探针测试 5/5 ✅                                       │
│ └─ CFG 集成 ❌ 阻塞项（详见下方）                          │
├─────────────────────────────────────────────────────────┤
│ T6-T7: 边界测试 + 性能验证 ❌                             │
│ └─ 目标: 4-6x 性能改进                                   │
└─────────────────────────────────────────────────────────┘
```

---

## T5 详细进展

### T5.1: 字段偏移量提取 ✅

**修改文件**: `tree_iter_state_machine_pass.h`, `tree_iter_state_machine_pass.cpp`

**实现**:
- 新增 `TreeIterFieldInfo` 结构体（name, offset, name_idx）
  - `name_idx >= 0`: 原始代码使用 LoadAttr（标准 Python）
  - `name_idx == -1`: 原始代码使用 LoadField（StaticPython 类型特化后）
- `isTreeIterPattern()` 重构：输出 `TreeIterFieldInfo&` 而非 bool
- 新增 `extractValueField()`: 扫描函数中的 `LoadField(self, "value")` 或 `LoadAttr(self, "value")`
  - 关键发现：receiver 不是直接的 `LoadArg(0)`，而是通过 Phi 节点间接引用 self
  - 使用递归 `is_self_reg` lambda 检查（同 `isTreeIterPattern` 的逻辑）

**提取结果**: `left_offset=24, right_offset=32, value_offset=40`

### T5.2: 新增 HIR 指令 ✅

**LoadPoppedPhase** (`Opcode::kLoadPoppedPhase`)
- 用途：读取 `GenDataFooter.popped_phase` 到寄存器（TCInt32）
- 使用场景：`GenerateBacktrackBlock()` 中 StateStackPop 之后读取保存的 phase 值

| 层级 | 实现 |
|------|------|
| HIR | `DEFINE_SIMPLE_INSTR(LoadPoppedPhase, (TCInt32), HasOutput, Operands<0>)` |
| isReplayable | false |
| isPassthrough | true |
| memoryEffects | 只读 (`commonEffects(inst, AEmpty)`) |
| LIR | `kLoadPoppedPhase`, 1 output (k32bit), 0 inputs |
| x86_64 codegen | `mov output, dword_ptr(rbp, offsetof(GenDataFooter, popped_phase))` |
| ARM64 codegen | `ldr w0, [fp, popped_phase_offset]; mov output, x0` |

**LoadStackTop** (`Opcode::kLoadStackTop`)
- 用途：读取 `GenDataFooter.stack_top` 到寄存器（TCInt32）
- 使用场景：`GenerateBacktrackBlock()` 中检查栈是否为空

| 层级 | 实现 |
|------|------|
| HIR | `DEFINE_SIMPLE_INSTR(LoadStackTop, (TCInt32), HasOutput, Operands<0>)` |
| isReplayable | false |
| isPassthrough | false（读取可变状态） |
| memoryEffects | 只读 (`commonEffects(inst, AEmpty)`) |
| LIR | `kLoadStackTop`, 1 output (k32bit), 0 inputs |
| x86_64 codegen | `mov output, dword_ptr(rbp, offsetof(GenDataFooter, stack_top))` |
| ARM64 codegen | `ldr w0, [fp, stack_top_offset]; mov output, x0` |

**涉及的文件**（每个指令需要修改 8 个文件）:

| 文件 | 修改内容 |
|------|---------|
| `Jit/hir/hir_ops.h` | `V(LoadPoppedPhase)`, `V(LoadStackTop)` 添加到 FOREACH_OPCODE |
| `Jit/hir/hir.h` | `DEFINE_SIMPLE_INSTR` 定义 |
| `Jit/hir/instr_effects.cpp` | `memoryEffects()` 和 `hasArbitraryExecution()` |
| `Jit/hir/hir.cpp` | `isReplayable()` 和 `isPassthrough()` |
| `Jit/hir/printer.cpp` | `format_immediates()` 调试输出 |
| `Jit/lir/generator.cpp` | HIR→LIR 降级 |
| `Jit/lir/instruction.h` | LIR 指令枚举定义 |
| `Jit/codegen/autogen.cpp` | x86_64 + ARM64 汇编代码生成 |

### T5.3: SaveState/LoadState 决策 ✅

**选择方案 B**: 不使用 SaveState/LoadState，完全依赖 Phi 节点管理 phase。

**原因**:
- SaveState/LoadState 的 LIR lowering 尚未实现（调用 `JIT_ABORT`）
- Task 5 的 scope 不需要 deopt 支持
- Phi 节点足以管理 phase 状态

### T5.4: SSA Phi 架构重构 ✅

**核心变更**: 从"可变寄存器"模型重构为 SSA Phi 节点驱动模型。

**旧模型**（已移除）:
```cpp
ctx.phase_reg = AllocateRegister();  // 在多个块中重复赋值 → 违反 SSA
ctx.current_node_reg = AllocateRegister();
```

**新模型**（当前）:
```cpp
// bb_loop 中的 Phi 节点
current = Phi({
  bb_init: self,
  bb_left_descend: left_child,
  bb_no_left: current,        // 自引用（循环变量）
  bb_after_yield: current,    // 自引用
  bb_right_descend: right_child,
  bb_no_right: current,       // 自引用
  bb_pop: popped_node
})

phase = Phi({
  bb_init: kLeft,
  bb_left_descend: kLeft,
  bb_no_left: kYield,
  bb_after_yield: kRight,
  bb_right_descend: kLeft,
  bb_no_right: kBacktrack,
  bb_pop: popped_phase
})
```

**StateMachineContext 重构**:

| 移除 | 新增 |
|------|------|
| `current_node_reg`, `phase_reg`, `stack_top_reg` | `current_phi`, `phase_phi` |
| `bb_left`, `bb_right` | `bb_has_left`, `bb_no_left`, `bb_after_yield`, `bb_has_right`, `bb_no_right`, `bb_pop` |
| — | 12 个 Phi 输入寄存器（每个前驱块一对） |
| — | `left_field`, `right_field`, `value_field` (`TreeIterFieldInfo`) |

### T5.5: 基本块真实指令 ✅

| 基本块 | 使用的指令 |
|--------|-----------|
| `bb_init` | `LoadArg(self, 0)`, `LoadConst(kLeft)` |
| `bb_loop` | 3× `LoadConst` + 3× `PrimitiveCompare(kEqual)` + 3× `CondBranch` |
| `bb_has_left` | `LoadField(current, "left")`, `LoadConst(None)`, `PrimitiveCompare`, `CondBranch` |
| `bb_left_descend` | `StateStackPush(current, kRight)`, `LoadConst(kLeft)`, `Branch(bb_loop)` |
| `bb_no_left` | `LoadConst(kYield)`, `Branch(bb_loop)` |
| `bb_yield` | `LoadField/LoadAttr(current, "value")`, `YieldValue(result, value, FrameState{})` |
| `bb_after_yield` | `LoadConst(kRight)`, `Branch(bb_loop)` |
| `bb_has_right` | `LoadField(current, "right")`, `LoadConst(None)`, `PrimitiveCompare`, `CondBranch` |
| `bb_right_descend` | `StateStackPush(current, kBacktrack)`, `LoadConst(kLeft)`, `Branch(bb_loop)` |
| `bb_no_right` | `LoadConst(kBacktrack)`, `Branch(bb_loop)` |
| `bb_backtrack` | `LoadStackTop`, `LoadConst(0)`, `PrimitiveCompare`, `CondBranch` |
| `bb_pop` | `StateStackPop(popped_node)`, `LoadPoppedPhase(popped_phase)`, `Branch(bb_loop)` |
| `bb_done` | `LoadConst(None)`, `Return(None)` |

### T5.6: CFG 集成 ❌ 阻塞项

**问题**: `generateStateMachine()` 中的 CFG 集成代码导致进程崩溃 (SIGSEGV)。

**崩溃原因分析**:

| 问题 | 说明 |
|------|------|
| CleanCFG 崩溃 | Phi 节点引用的前驱块被 CleanCFG 删除为不可达块，导致 Phi 悬空引用 |
| LIR generator 崩溃 | `AllocateBlock()` 将块添加到 CFG，LIR generator 尝试编译所有块（包括不可达的状态机块） |

**当前策略**: `generateStateMachine()` 调用被注释掉。只执行模式检测和探针计数器递增。

**解决方案方向**:
- **不使用 `AllocateBlock()`** 创建状态机块
- 直接在原始生成器块的现有指令中替换
- 保留原始块结构，避免创建孤立块

---

## 修改的文件汇总（T5）

| 文件 | 修改内容 | 行数变化 |
|------|---------|---------|
| `cinderx/Jit/hir/tree_iter_state_machine_pass.h` | TreeIterFieldInfo、StateMachineContext 重构、SSA Phi 架构 | +116/-48 |
| `cinderx/Jit/hir/tree_iter_state_machine_pass.cpp` | SSA Phi 重写、字段提取、真实指令 | ~734 行重写 |
| `cinderx/Jit/hir/hir_ops.h` | +2 opcodes (LoadPoppedPhase, LoadStackTop) | +4/-1 |
| `cinderx/Jit/hir/hir.h` | +2 DEFINE_SIMPLE_INSTR | +18 |
| `cinderx/Jit/hir/instr_effects.cpp` | +2 memoryEffects + hasArbitraryExecution | +8 |
| `cinderx/Jit/hir/hir.cpp` | +2 isReplayable + isPassthrough | +4 |
| `cinderx/Jit/hir/printer.cpp` | +2 format_immediates | +6 |
| `cinderx/Jit/lir/generator.cpp` | +2 LIR lowering | +16 |
| `cinderx/Jit/lir/instruction.h` | +2 LIR instruction definitions | +14 |
| `cinderx/Jit/codegen/autogen.cpp` | +2 translateX86 + translateARM + 2× BEGIN_RULES | +71 |

**总计**: 10 文件，+696/-521 行

---

## 探针测试结果

```
PYTHONJITHUGEPAGES=0 PYTHONJIT=1 PYTHONJITDEBUG=0 .venv/bin/python test_phase3_state_machine.py -v
```

| 测试 | 结果 | 说明 |
|------|------|------|
| test_00_probe_pass_triggered | ✅ PASS | 状态机 pass 被触发 (count=1) |
| test_01_probe_not_triggered_for_non_tree | ✅ PASS | 非树遍历函数不触发 |
| test_02_probe_reset | ✅ PASS | 计数器重置正常 |
| test_depth_3_correctness | ✅ PASS | depth=3 遍历结果正确 |
| test_depth_5_correctness | ✅ PASS | depth=5 遍历结果正确 |

**注意**: 测试通过是因为 `generateStateMachine()` 被注释掉。原始生成器代码保持不变，遍历结果来自原始 YieldFrom 实现。探针验证的是模式检测功能。

---

## 踩坑记录

### 1. FieldInfo 名称冲突
- **问题**: `tree_iter_state_machine_pass.h` 中定义的 `FieldInfo` 与 `preload.h` 中的同名结构体冲突
- **解决**: 重命名为 `TreeIterFieldInfo`

### 2. ARM64 GpX::W() 不存在
- **问题**: asmjit 的 `a64::GpX` 类型（`arch::reg_scratch_0` 的类型）没有 `.W()` 方法
- **解决**: 使用 `a64::w0`, `a64::w1` 等直接命名的 32 位寄存器

### 3. FOREACH_OPCODE 最后一项格式
- **问题**: 最后一项不能有尾随 `\` 或 `)`，必须是裸 `V(OpName)`
- **错误示例**: `V(LoadStackTop))` → 编译错误

### 4. yield self.value 的 receiver 不是直接 LoadArg
- **问题**: JIT 类型特化将 `LoadAttr(self, "value")` 转为 `LoadField(phi, "value")`，receiver 是 Phi 节点而非 `LoadArg(0)`
- **解决**: 使用递归 `is_self_reg` lambda 检查，支持 Phi 节点间接引用

### 5. Phi 节点与 CleanCFG 冲突
- **问题**: Phi 引用的前驱块被 CleanCFG 删除，导致悬空引用崩溃
- **解决**: 暂时跳过 CleanCFG，后续改用不创建新块的方案

### 6. AllocateBlock() 创建的孤立块导致 LIR generator 崩溃
- **问题**: 即使不调用 CleanCFG，LIR generator 也会尝试编译 CFG 中的所有块（包括不可达的状态机块）
- **解决**: 暂时注释掉 `generateStateMachine()` 调用

---

## 下一步

### T5.6: CFG 集成（阻塞项）
- 方案：不使用 `AllocateBlock()`，直接在现有块中替换指令
- 预估：1-2 天

### T6: 边界情况处理
- depth=0（空树）、depth=1（单节点）
- 左偏/右偏树（只有 left 或只有 right）
- depth=12（最大内联深度）
- depth=13+（超过限制的回退行为）

### T7: 最终验证
- 性能基准测试（目标 4-6x）
- 回归测试
- HIR 输出验证

---

**更新人**: Claude Code
**日期**: 2026-03-26
**状态**: Phase 3.2 T5 ~85% 完成，CFG 集成为唯一阻塞项
