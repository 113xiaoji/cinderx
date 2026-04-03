# Phase 2 Week 2 Day 1: T2.2 状态机构建器基础实现完成报告

**完成日期**: 2026-03-24
**状态**: ✅ 完成
**提交**: [待定]

---

## 任务概览

完成了 T2.2 - 状态机构建器的基础实现，包括入口块、分发块、完成块和状态块的创建逻辑。

---

## 完成的工作

### ✅ 稡式识别 (T2.1)

在之前的提交中已经完成：
- `detectPattern()` - 检测树遍历模式
- `isTreePattern()` - 验证是否是树遍历
- `countStates()` - 估算状态数

### ✅ 状态机构建器基础 (T2.2)

**文件**: `cinderx/Jit/hir/state_machine_generator.cpp`

**主要实现**:

#### 1. createEntryBlock() - 入口块

```cpp
BasicBlock* StateMachineGenerator::createEntryBlock(StateMachine* sm) {
  // 创建入口块
  BasicBlock* entry = func_->cfg.AllocateUnlinkedBlock();

  // 加载当前状态
  sm->state_reg = func_->env.AllocateRegister();
  emitLoadState(entry, sm->state_reg);

  // 检查是否未初始化（state == -1）
  Register* uninit_const = func_->env.AllocateRegister();
  entry->append<LoadConst>(uninit_const, Type::fromCInt(-1, TCInt32));

  Register* is_uninit = func_->env.AllocateRegister();
  entry->append<PrimitiveCompare>(
      is_uninit,
      PrimitiveCompareOp::kEqual,
      sm->state_reg,
      uninit_const);

  // 创建初始化块
  BasicBlock* init_bb = func_->cfg.AllocateUnlinkedBlock();
  emitSaveState(init_bb, sm->state_reg, 0);  // 设置状态为 0
  init_bb->append<Branch>(sm->dispatch_block);

  // 条件跳转：如果未初始化则跳转到 init，否则跳转到 dispatch
  entry->append<CondBranch>(is_uninit, init_bb, sm->dispatch_block);

  return entry;
}
```

**特点**:
- 加载状态（LoadState 指令）
- 检查是否未初始化（state == -1）
- 创建初始化块（设置状态为 0）
- 条件跳转到初始化块或分发块

#### 2. createDispatchBlock() - 分发块

```cpp
BasicBlock* StateMachineGenerator::createDispatchBlock(StateMachine* sm) {
  // 创建分发块
  BasicBlock* dispatch = func_->cfg.AllocateUnlinkedBlock();

  // 使用 CondBranch 链实现状态分发
  // 对于每个状态 i，检查 state == i，如果是则跳转到 states[i].bb

  BasicBlock* current_bb = dispatch;

  for (size_t i = 0; i < sm->states.size(); ++i) {
    // 创建常量 i
    Register* state_const = func_->env.AllocateRegister();
    current_bb->append<LoadConst>(
        state_const,
        Type::fromCInt(sm->states[i].id, TCInt32));

    // 比较 state == i
    Register* is_state = func_->env.AllocateRegister();
    current_bb->append<PrimitiveCompare>(
        is_state,
        PrimitiveCompareOp::kEqual,
        sm->state_reg,
        state_const);

    // 确定下一个块
    BasicBlock* next_bb = nullptr;
    if (i + 1 < sm->states.size()) {
      // 还有更多状态，创建一个新的检查块
      next_bb = func_->cfg.AllocateUnlinkedBlock();
    } else {
      // 这是最后一个状态，如果都不匹配则跳转到 done
      next_bb = sm->done_block;
    }

    // 条件跳转
    current_bb->append<CondBranch>(
        is_state,
        sm->states[i].bb,
        next_bb);

    current_bb = next_bb;
  }

  return dispatch;
}
```

**特点**:
- 使用 CondBranch 链实现状态分发（避免复杂的 StateSwitch 实现）
- 对每个状态生成比较和条件跳转
- 最后一个状态不匹配时跳转到 done 块

#### 3. createDoneBlock() - 完成块

```cpp
BasicBlock* StateMachineGenerator::createDoneBlock(StateMachine* sm) {
  // 创建完成块
  BasicBlock* done = func_->cfg.AllocateUnlinkedBlock();

  // 创建 None 常量
  Register* none_reg = func_->env.AllocateRegister();
  done->append<LoadConst>(none_reg, Type::fromObject(Py_None));

  // 返回 None（表示迭代完成）
  done->append<Return>(none_reg, Type::fromObject(Py_None));

  return done;
}
```

**特点**:
- 创建 None 常量（使用 `Type::fromObject(Py_None)`）
- 返回 None 表示迭代完成

#### 4. createStateBlock() - 状态块（占位符实现）

```cpp
BasicBlock* StateMachineGenerator::createStateBlock(
    StateMachine* sm,
    int state_id) {
  // 创建状态块
  BasicBlock* state_bb = func_->cfg.AllocateUnlinkedBlock();

  // TODO: 根据状态 ID 生成对应的逻辑
  // 当前实现：占位符 - 直接返回并跳转到下一个状态或 done

  // 创建 None 常量
  Register* none_reg = func_->env.AllocateRegister();
  state_bb->append<LoadConst>(none_reg, Type::fromObject(Py_None));

  // Return None (简化实现，避免 YieldValue 的 FrameState 问题)
  state_bb->append<Return>(none_reg, Type::fromObject(Py_None));

  return state_bb;
}
```

**特点**:
- **占位符实现**: 当前仅返回 None
- **待完善**: 需要根据状态 ID 生成实际的逻辑（yield value, yield from left/right）
- **简化处理**: 暂时避免 YieldValue 的 FrameState 参数问题

---

## 技术决策记录

### 1. 使用 CondBranch 链代替 StateSwitch

**决策**: 使用 CondBranch 链实现状态分发

**理由**:
- StateSwitch 指令在 Week 1 中定义为 DEFINE_SIMPLE_INSTR，没有完整的目标块管理
- CondBranch 是标准的终止器指令，有完整的边管理
- CondBranch 链虽然效率略低于 StateSwitch，但实现简单且易于调试
- 未来可以优化为真正的 StateSwitch 实现（需要扩展 StateSwitch 定义）

### 2. 简化 YieldValue 处理

**决策**: 在状态块中使用 Return 代替 YieldValue

**理由**:
- YieldValue 需要 FrameState 参数，当前框架中难以获取
- 简化实现，让代码先工作起来
- 未来完善时需要添加正确的 YieldValue 逻辑

### 3. 使用 PrimitiveCompare 代替 CompareInt

**决策**: 使用 `PrimitiveCompare` 配合 `PrimitiveCompareOp::kEqual`

**理由**:
- `PrimitiveCompare` 用于整数比较（TCInt32 类型）
- `CompareInt` 指令不存在于 CinderX HIR 中
- `PrimitiveCompareOp::kEqual` 是正确的枚举值

---

## 编译验证

### 构建命令
```bash
CC=/opt/homebrew/bin/gcc-15 CXX=/opt/homebrew/bin/g++-15 \
  CMAKE=/usr/bin/cmake \
  LDFLAGS="-L/opt/homebrew/Cellar/gcc/15.2.0_1/lib/gcc/current -lstdc++" \
  .venv/bin/python3 setup.py build
```

### 构建结果
- ✅ **编译成功** - 所有文件编译通过
- ✅ **链接成功** - `_cinderx.so` 生成成功
- ⚠️ 警告: GCC 15 的 `-Wfree-nonheap-object` 警告（与第三方库相关，不影响功能）
- ✅ **代码签名成功** - macOS 上签名完成

---

## 文件变更清单

| 文件 | 修改内容 | 行数变化 |
|------|---------|---------|
| `cinderx/Jit/hir/state_machine_generator.cpp` | 实现 createEntryBlock, createDispatchBlock, createDoneBlock, createStateBlock | +85 |
| **总计** | **1 个文件** | **+85 行** |

---

## 已知限制

### 1. 状态块逻辑不完整

**问题**: `createStateBlock()` 当前仅返回 None（占位符）

**原因**:
- 缺少从模式信息提取状态转换逻辑
- 需要 YieldValue 但 FrameState 参数难以获取
- 需要实现 `yield value` 和 `yield from left/right` 的逻辑

**解决方案** (T2.3 或 T2.4):
- 容善 `detectPattern()` 提取完整的状态转换信息
- 为每个状态生成正确的 HIR 指令（LoadField, YieldValue, SaveState, Branch）
- 添加 FrameState 支持

### 2. StateSwitch 未完整实现

**问题**: 使用 CondBranch 链效率低于 StateSwitch

**原因**:
- StateSwitch 定义不完整，需要扩展

**解决方案** (未来优化):
- 扩展 StateSwitch 定义，添加目标块管理
- 实现 LIR 层的 StateSwitch 代码生成（跳转表）
- 替换 CondBranch 链为 StateSwitch

### 3. 缺少测试覆盖

**问题**: 没有单元测试或集成测试

**待添加**:
- [ ] HIR 生成测试（验证状态机结构）
- [ ] 性能基准测试（验证 4-6x 提升）
- [ ] 回归测试（验证现有功能不受影响）

---

## 下一步工作

### T2.2 后续任务

| 任务 | 描述 | 估计时间 |
|------|------|---------|
| T2.2.1 | 完善 createStateBlock() - 根据状态生成正确逻辑 | 1 天 |
| T2.2.2 | 添加 FrameState 支持 - YieldValue 需要参数 | 0.5 天 |
| T2.2.3 | 测试状态机生成 | 验证 HIR 结构正确 | 0.5 天 |

### T2.3 - 嵌套展平 (1.5 天)

**目标**: 实现嵌套生成器的状态机展平
- 递归提取子生成器的状态机
- 合并到父状态机中- 支持深度 ≤ 3 的嵌套

- 预期：4-6x 性能改进

### T2.4 - HIR 生成 (1.5 天)

**目标**: 将状态机生成集成到 HIR pipeline
- 在 `simplify.cpp` 中添加状态机生成调用
- 替换 InlineIter 为状态机（当深度 ≤ 3）
- 性能验证（达到 4-6x 目标）

- 预期：4-6x 性能改进

### T2.5 - 与 Escape Analysis 集成 (0.5 天)

**目标**: 集成状态机生成器与逃逸分析
- 决定何时使用状态机 vs InlineIter
- 测试集成
- 预期：完整功能

---

## 参考文档

- [Phase 2 实施计划](../plans/2026-03-23-generators-phase2-state-machine-plan.md)
- [状态机生成研究报告](../research/2026-03-23-generators-phase2-state-machine-research.md)
- [Week 1 完成报告](./2026-03-24-generators-phase2-week1-completion-report.md)
- [InlineIter Phase 1 总结](./2026-03-23-generators-inline-iter-phase1-summary.md)

---

**维护者**: Claude Code Agent
**最后更新**: 2026-03-24
**Git Commit**: [待创建]
