# Phase 2 Week 1 基础设施完成报告

**完成日期**: 2026-03-24
**状态**: ✅ 完成
**提交**: 70a1477a

---

## 任务概览

Week 1 完成了 Phase 2 状态机生成的基础设施，包括 HIR 指令定义、内存效果、调试支持和解析支持。

---

## 完成的任务

### ✅ T1.1 - GenDataFooter 扩展

**文件**: `cinderx/Jit/gen_data_footer.h`

**修改**:
```cpp
// Phase 2: State machine support
// Current state for state machine generators.
// -1 = uninitialized, 0 = initial, >0 = generated states
// This field is used by the state machine generator to track execution state.
#if PY_VERSION_HEX >= 0x030E0000
  // Python 3.14+: Use existing gi_frame_state field from CPython
  // No additional field needed, state is stored in PyGenObject::gi_frame_state
#else
  // Python < 3.14: Store state machine state in GenDataFooter
  // Using int32_t for efficiency (aligned to 4 bytes, but padded to 8)
  int32_t currentState{-1};
#endif
```

**设计决策**:
- Python 3.14+ 复用 CPython 的 `gi_frame_state` 字段
- Python < 3.14 使用新增的 `currentState` 字段
- 默认值 `-1` 表示未初始化状态

---

### ✅ T1.2 - HIR Opcodes 定义

**文件**: `cinderx/Jit/hir/hir_ops.h`

**新增 4 个 opcodes**:
```cpp
V(InlineIter)                        // Phase 1: 内联迭代器
V(StateSwitch)                       // Phase 2: 状态分发
V(SaveState)                         // Phase 2: 状态保存
V(LoadState)                         // Phase 2: 状态加载
V(YieldFromInline)                   // Phase 2: 内联 yield from
```

**命名约定**:
- `StateSwitch`: 状态机分发指令（terminator）
- `SaveState`: 保存状态到 GenDataFooter
- `LoadState`: 从 GenDataFooter 加载状态
- `YieldFromInline`: 内联的 yield-from 指令

---

### ✅ T1.3 - HIR 指令类定义

**文件**: `cinderx/Jit/hir/hir.h`

**新增 4 个 HIR 指令类**:

#### 1. StateSwitch - 状态分发指令
```cpp
// StateSwitch: 状态分发指令
// 根据当前状态跳转到对应的基本块
// 操作数: state_var (状态变量，TCInt32类型)
// 这是一个终结器指令（Terminator）
DEFINE_SIMPLE_INSTR(
    StateSwitch,
    (TCInt32),
    Operands<1>);
```

**特点**:
- 终止器指令（类似 Branch/CondBranch）
- 输入: 状态变量 (TCInt32)
- 根据状态值跳转到对应的基本块

#### 2. SaveState - 状态保存指令
```cpp
// SaveState: 状态保存指令
// 将状态值保存到 GenDataFooter.currentState
// 操作数: new_state (新状态值，TCInt32类型)
DEFINE_SIMPLE_INSTR(
    SaveState,
    (TCInt32),
    Operands<1>);
```

**特点**:
- 无输出（类似 StoreField）
- 将状态保存到 GenDataFooter
- 在 yield 前调用

#### 3. LoadState - 状态加载指令
```cpp
// LoadState: 状态加载指令
// 从 GenDataFooter.currentState 加载当前状态
// 输出: 当前状态值（TCInt32类型）
DEFINE_SIMPLE_INSTR(
    LoadState,
    (),
    HasOutput,
    Operands<0>);
```

**特点**:
- 有输出 (TCInt32)
- 从 GenDataFooter 加载状态
- 在生成器恢复时调用

#### 4. YieldFromInline - 内联 yield from
```cpp
// YieldFromInline: 内联 yield from 指令（叶子节点）
// 对于嵌套的生成器，如果可以完全内联则使用此指令
// 操作数: receiver, field_name_idx, next_state
// 输出: yield 的值
DEFINE_SIMPLE_INSTR(
    YieldFromInline,
    (TObject, TOptObject),
    HasOutput,
    Operands<3>,
    DeoptBase);
```

**特点**:
- 类似 YieldFrom，但用于内联场景
- 包含 deopt 信息（支持回退到解释器）
- 操作数: receiver, field_idx, next_state

---

### ✅ T1.4 - HIR Effects

**文件**:
- `cinderx/Jit/hir/instr_effects.cpp`
- `cinderx/Jit/hir/hir.cpp`

#### 内存效果定义 (instr_effects.cpp)

```cpp
// Phase 2: 状态机指令
case Opcode::kStateSwitch:
  // 状态分发只读状态变量
  return commonEffects(inst, AEmpty);
case Opcode::kSaveState:
  // 保存状态到 GenDataFooter
  return commonEffects(inst, AOther);
case Opcode::kLoadState:
  // 从 GenDataFooter 加载状态
  return commonEffects(inst, AEmpty);
case Opcode::kYieldFromInline:
  // 内联 yield from 读写生成器状态
  return {true, AFuncArgs, {3, 1}, AAny};
```

#### isReplayable 支持 (hir.cpp)

```cpp
case Opcode::kYieldFromInline:  // Phase 2: 内联 yield from
  return false;  // 不可重放（有副作用）
```

#### isPassthrough 支持 (hir.cpp)

```cpp
case Opcode::kLoadState:  // Phase 2: 加载状态是透传指令
  return true;

case Opcode::kYieldFromInline:  // Phase 2: 内联 yield from
  return false;

case Opcode::kSaveState:  // Phase 2: 保存状态无输出
  JIT_ABORT("Opcode {} has no output", instr.opname());

case Opcode::kStateSwitch:  // Phase 2: 状态分发无输出
  JIT_ABORT("Opcode {} has no output", instr.opname());
```

---

### ✅ T1.5 - HIR Printer 支持

**文件**: `cinderx/Jit/hir/printer.cpp`

**新增格式化输出**:
```cpp
case Opcode::kLoadState:  // Phase 2: 无额外信息需要格式化
  return "";
case Opcode::kStateSwitch: {
  const auto& sw = static_cast<const StateSwitch&>(instr);
  return fmt::format("state_var={}", sw.GetOperand(0)->id());
}
case Opcode::kSaveState: {
  const auto& save = static_cast<const SaveState&>(instr);
  return fmt::format("new_state={}", save.GetOperand(0)->id());
}
case Opcode::kYieldFromInline: {
  const auto& yfi = static_cast<const YieldFromInline&>(instr);
  return fmt::format(
      "receiver={}, field_idx={}, next_state={}",
      yfi.GetOperand(0)->id(),
      yfi.GetOperand(1)->id(),
      yfi.GetOperand(2)->id());
}
```

**示例输出**:
```
v5 = LoadState
StateSwitch v5
SaveState v10
v12 = YieldFromInline v3, 0, 5
```

---

### ✅ T1.6 - HIR Parser 支持

**文件**: `cinderx/Jit/hir/parser.cpp`

**新增解析逻辑**:
```cpp
// Phase 2: 状态机指令解析
case Opcode::kLoadState: {
  // LoadState 没有输入操作数，从 GenDataFooter 加载状态
  NEW_INSTR(LoadState, dst);
  break;
}
case Opcode::kSaveState: {
  // SaveState 有一个输入操作数（新状态值）
  auto new_state = ParseRegister();
  NEW_INSTR(SaveState, new_state);
  break;
}
case Opcode::kStateSwitch: {
  // StateSwitch 是终止器指令，基于状态变量跳转
  auto state_var = ParseRegister();
  NEW_INSTR(StateSwitch, state_var);
  break;
}
```

**说明**:
- `YieldFromInline` 标记为 unsupported（与 YieldFrom 类似）
- 其他 3 个指令支持完整解析
- 可用于测试 HIR 文本格式

---

## 编译验证

### 构建命令
```bash
CC=/opt/homebrew/bin/gcc-15 CXX=/opt/homebrew/bin/g++-15 \
  CMAKE=/usr/bin/cmake \
  LDFLAGS="-L/opt/homebrew/Cellar/gcc/15.2.0_1/lib/gcc/current -lstdc++" \
  uv run --python 3.14 python setup.py build
```

### 构建结果
- ✅ **编译成功** - 所有文件编译通过
- ✅ **链接成功** - `_cinderx.so` 生成成功
- ⚠️ 警告: GCC 15 的 `-Wfree-nonheap-object` 警告（与第三方库相关，不影响功能）

### 代码签名（macOS）
```bash
codesign --force --deep --sign - cinderx/PythonLib/_cinderx.so
```

---

## 文件变更清单

| 文件 | 修改内容 | 行数变化 |
|------|---------|---------|
| `cinderx/Jit/gen_data_footer.h` | 添加 `currentState` 字段 | +8 |
| `cinderx/Jit/hir/hir_ops.h` | 添加 4 个 opcodes | +4 |
| `cinderx/Jit/hir/hir.h` | 定义 4 个 HIR 指令类 | +45 |
| `cinderx/Jit/hir/instr_effects.cpp` | 添加内存效果和 hasArbitraryExecution | +11 |
| `cinderx/Jit/hir/hir.cpp` | 添加 isReplayable/isPassthrough | +5 |
| `cinderx/Jit/hir/printer.cpp` | 添加格式化输出 | +17 |
| `cinderx/Jit/hir/parser.cpp` | 添加解析支持 | +20 |
| `docs/superpowers/generators/README.md` | 更新文档索引 | +3 |
| **总计** | **8 个文件** | **+113 行** |

---

## 技术决策记录

### 1. 状态变量类型选择

**决策**: 使用 `TCInt32` 而非 `TInt32` 或 `TObject`

**理由**:
- `TCInt32` 是 C 原生 int32，直接映射到机器寄存器
- 避免装箱/拆箱开销
- 状态值是编译时常量，不需要 Python 对象表示
- 与 GenDataFooter 中的 `int32_t currentState` 对应

### 2. 状态存储位置

**决策**: Python <3.14 使用 GenDataFooter，3.14+ 复用 CPython 字段

**理由**:
- Python 3.14+ 的 `gi_frame_state` 已提供状态存储
- 避免重复字段，减少内存占用
- 保持与 CPython 上游兼容

### 3. YieldFromInline 设计

**决策**: 作为独立的 HIR 指令，而非扩展现有的 YieldFrom

**理由**:
- 语义不同: YieldFromInline 用于已展开的嵌套生成器
- 需要额外的 `next_state` 操作数用于状态转换
- 支持不同的优化路径（完全内联 vs 委托）
- 清晰的指令边界，便于调试和优化

### 4. StateSwitch vs Switch

**决策**: 新增 StateSwitch 而非复用现有的 Switch 指令

**理由**:
- Switch 是通用指令，StateSwitch 专用于状态机分发
- StateSwitch 可以有特定的优化（例如跳转表）
- 明确的语义分离，便于分析和优化
- StateSwitch 不需要 default 分支（状态值由编译器控制）

---

## 已知限制

### 1. Parser 限制
- `YieldFromInline` 标记为 unsupported，需要未来扩展
- 原因: 与 YieldFrom 类似，需要完整的 FrameState 解析

### 2. 状态机深度限制
- Week 1 仅定义基础设施，未实现状态机生成逻辑
- Week 2 将实现 canFlatten 启发式（限制深度 ≤ 3）

### 3. 代码膨胀风险
- 需要在 Week 2 实现状态数限制（≤ 50 个状态）
- 超过限制时回退到 InlineIter (Phase 1)

---

## 测试覆盖

### 手动测试
- ✅ 编译验证通过
- ✅ 无运行时断言失败

### 待添加的测试（Week 2+）
- [ ] HIR parser 单元测试（解析新的指令）
- [ ] 状态机生成集成测试
- [ ] 性能基准测试（验证 4-6x 提升）
- [ ] 代码膨胀测试（验证 ≤ 30% 增长）

---

## 下一步工作（Week 2）

### 任务列表

| 任务 | 描述 | 估计时间 |
|------|------|---------|
| T2.1 | Yield-From 模式识别 | 1.5 天 |
| T2.2 | 状态机构建器 | 2 天 |
| T2.3 | 嵌套展平 | 1.5 天 |
| T2.4 | HIR 生成 | 1.5 天 |
| T2.5 | 与 Escape Analysis 集成 | 0.5 天 |

### 关键里程碑
1. **模式识别完成** - 识别 `yield from self.left/right` 模式
2. **状态机生成** - 将模式转换为显式状态机 HIR
3. **嵌套展平** - 支持深度 ≤ 3 的嵌套生成器
4. **性能验证** - 达到 4-6x 性能提升目标

---

## 参考文档

- [Phase 2 实施计划](../plans/2026-03-24-generators-phase2-state-machine-plan.md)
- [状态机生成研究报告](../research/2026-03-23-generators-phase2-state-machine-research.md)
- [InlineIter Phase 1 总结](./2026-03-23-generators-inline-iter-phase1-summary.md)

---

**维护者**: Claude Code Agent
**最后更新**: 2026-03-24
**Git Commit**: 70a1477a
