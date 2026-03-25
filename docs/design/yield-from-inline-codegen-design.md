# YieldFromInline 代码生成设计文档

**日期**: 2026-03-25
**状态**: 设计阶段
**优先级**: 高
**预计工作量**: 2-3 天

## 背景

当前 TreeIterStateMachinePass 已完成 Phi 节点模式检测（100% ✅），但状态机生成被暂时禁用，因为 YieldFromInline 指令的代码生成尚未实现。

## 问题分析

### 当前 generateStateMachine 实现的缺陷

**问题 1**: 假设 `iter` 直接来自 `GetIter`
```cpp
// 第 574 行
if (!iter_instr->IsGetIter()) {
  JIT_DLOG("iter is not from GetIter, skipping");
  state_bb->append<Branch>(done_block);
  continue;
}
```

**现实**: 在 Phi 节点情况下，`iter` 是 Phi 节点的输出，不是 GetIter！

**Phi 节点结构**:
```
v2 = Phi [
  CheckField(LoadField(self, "left")),   // 初始检查
  GetIter(CheckField(LoadField(...)))    // 循环迭代
]
```

### 解决方案选项

#### 选项 A: 从 Phi 节点提取 GetIter ⭐ 推荐

**优点**:
- 与现有模式检测逻辑一致
- 不需要修改 HIR 结构

**缺点**:
- 需要遍历 Phi 输入查找 GetIter
- 代码复杂度中等

**实现**:
```cpp
// 从 Phi 节点提取 GetIter
Instr* iter_instr = iter_reg->instr();
GetIter* get_iter = nullptr;

if (iter_instr->IsPhi()) {
  // 遍历 Phi 输入查找 GetIter
  auto* phi = static_cast<const Phi*>(iter_instr);
  for (size_t i = 0; i < phi->NumOperands(); i++) {
    Instr* input = phi->GetOperand(i)->instr();
    if (input->IsGetIter()) {
      get_iter = static_cast<GetIter*>(input);
      break;
    }
  }
} else if (iter_instr->IsGetIter()) {
  get_iter = static_cast<GetIter*>(iter_instr);
}

if (get_iter == nullptr) {
  // 错误处理
  continue;
}
```

#### 选项 B: 在模式检测时保存 GetIter

**优点**:
- 避免重复遍历 Phi 节点
- 代码更简洁

**缺点**:
- 需要修改 isTreeIterPattern 返回值
- 需要额外存储结构

**实现**: 暂不采用

#### 选项 C: 简化为状态标记

**优点**:
- 实现最简单
- 避免生成复杂的状态机

**缺点**:
- 性能改进有限
- 不符合原始设计目标

**实现**: 暂不采用

## 推荐方案：选项 A + 分阶段实现

### 阶段 1: 修复 generateStateMachine (0.5 天)

**目标**: 使 generateStateMachine 能处理 Phi 节点

**修改文件**: `cinderx/Jit/hir/tree_iter_state_machine_pass.cpp`

**关键修改**:
1. 添加 `extractGetIterFromPhi()` 辅助函数
2. 修改 generateStateMachine 使用该函数
3. 添加错误处理和日志

**验证**:
- 运行 TDD 测试确认不崩溃
- 检查 HIR dump 确认 YieldFromInline 被正确生成

### 阶段 2: 实现 translateYieldFromInline (1-1.5 天)

**目标**: 实现 YieldFromInline 的 x86_64 和 ARM64 代码生成

**修改文件**: `cinderx/Jit/codegen/autogen.cpp`

**实现策略**:

YieldFromInline 的语义：
```
result = YieldFromInline(receiver, field_idx, next_state)

等价于：
  field_value = receiver.fields[field_idx]
  if field_value is None:
    // 子树为空，跳过
    goto next_state
  else:
    // yield from field_value
    iter = iter(field_value)
    value = next(iter)
    yield value
    state = next_state
    return value
```

**代码生成伪代码** (x86_64):
```cpp
void translateYieldFromInline(Environ* env, const Instruction* instr) {
  arch::Builder* as = env->as;

  // 1. 加载 receiver (self)
  PhyLocation receiver_loc = instr->getInput(0)->getStackSlot();
  as->mov(x86::rax, x86::qword_ptr(x86::rbp, receiver_loc.loc));

  // 2. 加载 field_idx
  PhyLocation field_idx_loc = instr->getInput(1)->getStackSlot();
  as->mov(x86::rcx, x86::qword_ptr(x86::rbp, field_idx_loc.loc));

  // 3. 获取字段值: field_value = receiver->fields[field_idx]
  // 假设字段在固定偏移量（需要从类型信息获取）
  // 简化：假设 left=offset_0, right=offset_1
  as->mov(x86::rdx, x86::qword_ptr(x86::rax, x86::rcx, 8));  // rdx = field_value

  // 4. 检查 field_value 是否为 None
  as->cmp(x86::rdx, reinterpret_cast<uint64_t>(Py_None));
  asmjit::Label skip_label = as->newLabel();
  as->je(skip_label);  // 如果为 None，跳过

  // 5. field_value 非空：调用 GetIter + Next
  // TODO: 调用 JITRT_YieldFromInlineHelper(field_value)
  // 或者内联 GetIter + Next 逻辑

  // 6. 保存下一个状态
  PhyLocation next_state_loc = instr->getInput(2)->getStackSlot();
  // TODO: 存储到 GenDataFooter->currentState

  as->bind(skip_label);
  // 返回 None（跳过空子树）
}
```

**关键挑战**:
1. **字段偏移量获取**: 需要从类型信息获取 left/right 字段的偏移量
2. **GenDataFooter 集成**: 需要正确读写 currentState
3. **异常处理**: GetIter/Next 可能抛出异常

### 阶段 3: 实现运行时辅助函数 (0.5 天)

**目标**: 实现 JITRT_YieldFromInlineHelper

**修改文件**: `cinderx/Jit/jit_rt.cpp`, `cinderx/Jit/jit_rt.h`

**函数签名**:
```cpp
// 运行时辅助：内联 yield from
// 参数:
//   - iter: 子迭代器
//   - gen_data: 生成器数据（用于保存状态）
//   - next_state: 下一个状态值
// 返回:
//   - 非 nullptr: yield 的值
//   - nullptr: 迭代完成或异常
PyObject* JITRT_YieldFromInlineHelper(
    PyObject* iter,
    GenDataFooter* gen_data,
    int32_t next_state);
```

**实现**:
```cpp
PyObject* JITRT_YieldFromInlineHelper(
    PyObject* iter,
    GenDataFooter* gen_data,
    int32_t next_state) {
  // 1. 调用 next(iter)
  PyObject* value = PyIter_Next(iter);

  // 2. 检查结果
  if (value == nullptr) {
    // 迭代完成或异常
    if (PyErr_Occurred()) {
      // 有异常，传播
      return nullptr;
    } else {
      // 正常完成，设置 StopIteration
      PyErr_SetNone(PyExc_StopIteration);
      return nullptr;
    }
  }

  // 3. 保存下一个状态
  gen_data->currentState = next_state;

  // 4. 返回 yield 值
  return value;
}
```

### 阶段 4: 测试和优化 (0.5 天)

**测试计划**:
1. 单元测试: 验证 YieldFromInline 代码生成
2. 集成测试: 运行 TDD 测试套件
3. 性能测试: 运行 `dump_hir.py` 验证 4-6x 改进

**优化点**:
- 内联 GetIter/Next 避免函数调用
- 优化状态保存/加载路径
- 减少 branch 指令

## 风险评估

### 高风险

1. **字段偏移量硬编码**
   - 风险: left/right 字段偏移量可能在不同类中不同
   - 缓解: 从类型信息动态获取偏移量

2. **GenDataFooter 生命周期**
   - 风险: GenDataFooter 可能在状态机执行期间被释放
   - 缓解: 添加引用计数或使用栈分配

### 中等风险

3. **异常处理复杂**
   - 风险: yield from 过程中的异常需要正确传播
   - 缓解: 参考 OptimizedYieldFrom 的异常处理

4. **调试困难**
   - 风险: 状态机内联后栈追踪不直观
   - 缓解: 添加详细的调试日志

## 替代方案

如果实现复杂度太高，可以考虑：

### 方案 D: 简化为 OptimizedYieldFrom 变体

**思路**: 不生成完整状态机，只优化 Phi 节点处理

**优点**: 实现简单，风险低
**缺点**: 性能改进有限（预计 1.5-2x）

### 方案 E: 延迟到 Week 3

**思路**: 先完成 Week 2 其他任务，Week 3 再实现 YieldFromInline

**优点**: 有更多时间设计
**缺点**: 延迟性能验证

## 下一步行动

1. ✅ 创建此设计文档
2. ⏸️ 评估时间和优先级
3. ⏸️ 决定是否立即实现或延迟到下次会话

## 参考资料

- **OptimizedYieldFrom 实现**: `cinderx/Jit/codegen/autogen.cpp:1172`
- **GenDataFooter 定义**: `cinderx/Jit/gen_data_footer.h`
- **Phase 2 计划**: `.planning/phases/02-implementation/02-generators-phase2-state-machine.md`
