# Phase 2 状态机优化实现计划

**日期**: 2026-03-24
**状态**: 🚧 框架创建完成，实际集成待完成
**目标**: 实现 4-6x 性能改进（depth ≤ 5）

---

## 当前状态

### 已完成
- ✅ **TreeIterStateMachinePass 框架** - 状态机 pass 基础框架
- ✅ **状态机生成框架** - entry/init/dispatch/done/state blocks 框架
- ✅ **模式检测框架** - isTreeIterGenerator, collectYieldFromInstrs, isTreeIterPattern

### 待完成
- ⏳ **集成到编译 pipeline** - 将 pass 添加到编译器
- ⏳ **状态块实际逻辑** - 实现 yield value 提取和发射
- ⏳ **YieldFrom 替换** - 将原始指令替换为状态机跳转
- ⏳ **性能测试验证** - 验证 4-6x 改进

---

## 实现步骤

### 步骤 1: 集成到编译 Pipeline

**目标**: 在 HIR 构建后运行 TreeIterStateMachinePass

**修改文件**: `cinderx/Jit/compiler.cpp`

**修改内容**:
```cpp
#include "cinderx/Jit/hir/tree_iter_state_machine_pass.h"

// 在 HIR 构建后添加 pass
void Compiler::CompileFunction(...) {
  // ... 现有的 HIR 构建代码 ...

  // 运行状态机 pass
  if (enable_tree_iter_state_machine_) {
    TreeIterStateMachinePass pass;
    pass.Run(func);
  }
}
```

**环境变量控制**:
```bash
# 启用状态机优化
export PYTHONJIT_TREE_ITER_STATE_MACHINE=1
```

---

### 步骤 2: 实现状态块逻辑

**目标**: 状态块不仅保存状态，还要 yield 实际的值

**当前实现** (占位符):
```cpp
// 状态块内容 (占位符):
// 1. 保存下一个状态 (state = i + 1)
Register* next_state = func.env.AllocateRegister();
state_bb->append<LoadConst>(next_state, Type::fromCInt(i + 1, TCInt32));
state_bb->append<SaveState>(next_state);

// 2. 获取要 yield 的值（从 YieldFrom 指令获取）
// 这里简化处理：直接返回 None
Register* yield_value = func.env.AllocateRegister();
state_bb->append<LoadConst>(yield_value, Type::fromObject(Py_None));

// 3. 跳转到 dispatch
state_bb->append<Branch>(dispatch_block);
```

**目标实现**:
```cpp
// 状态块内容 (实际实现):
// 1. 保存下一个状态
Register* next_state = func.env.AllocateRegister();
state_bb->append<LoadConst>(next_state, Type::fromCInt(i + 1, TCInt32));
state_bb->append<SaveState>(next_state);

// 2. 获取要 yield 的值
// 从原始 YieldFrom 指令提取
const YieldFrom* original_yf = yield_froms[i];

// 提取 field 信息
Register* field_value = extractFieldValue(original_yf);

// 3. YieldValue 指令
// 注意: YieldValue 需要 FrameState
const FrameState* frame = original_yf->frameState();
Register* result = func.env.AllocateRegister();
state_bb->append<YieldValue>(result, field_value, *frame);

// 4. 跳转到 dispatch
state_bb->append<Branch>(dispatch_block);
```

---

### 步骤 3: 实现 YieldFrom 替换

**目标**: 将原始 YieldFrom 指令替换为跳转到 entry_block

**当前问题**: `simplifyYieldFrom` 返回一个 Register，但状态机需要替换整个指令序列

**解决方案**: 使用分支替换

```cpp
void TreeIterStateMachinePass::replaceYieldFromWithStateMachine(
    Function& func,
    const std::vector<const YieldFrom*>& yield_froms,
    BasicBlock* entry_block) {

  for (const YieldFrom* yf : yield_froms) {
    // 获取包含 YieldFrom 的基本块
    BasicBlock* block = yf->block();

    // 找到 YieldFrom 在块中的位置
    auto it = block->iterator_to(*yf);

    // 在 YieldFrom 之前插入跳转到 entry_block
    // 注意: 这需要修改控制流
    Register* dummy = func.env.AllocateRegister();
    block->insert_before(it, dummy);  // 占位

    // TODO: 实现实际的跳转逻辑
    // 需要:
    // 1. 创建新的基本块
    // 2. 将原始 YieldFrom 替换为 Branch
    // 3. 删除原始 YieldFrom
  }
}
```

---

### 步骤 4: 实现嵌套展平 (T2.3)

**目标**: 处理 `yield from self.left.left` 等嵌套模式

**嵌套模式示例**:
```python
def __iter__(self):
    if self.left:
        if self.left.left:  # 嵌套
            yield from self.left.left
        yield from self.left
    yield self.value
    if self.right:
        yield from self.right
```

**展平后的状态机**:
```
State 0: check left.left (if exists)
State 1: yield from left.left
State 2: check left
State 3: yield from left
State 4: yield self.value
State 5: check right
State 6: yield from right
State 7: done
```

**实现策略**:
```cpp
void flattenNestedYieldFrom(
    std::vector<const YieldFrom*>& yield_froms,
    int max_depth = StateMachineConfig::kMaxFlattenDepth) {

  // 1. 遍历所有 YieldFrom
  // 2. 检测嵌套模式（GetIter(GetIter(...)))
  // 3. 展平为单层状态
}
```

---

## 性能分析

### 预期性能改进

| 实现阶段 | 预期改进 | 说明 |
|---------|---------|------|
| 当前状态 | 1.3-1.5x | JIT 基本优化 |
| + 状态机框架 | 2-3x | 减少指令数 |
| + 实际状态块 | 3-4x | 消除中间指令 |
| + 嵌套展平 | 4-6x | 完整优化 |

### 性能瓶颈分析

**当前瓶颈**:
1. 多次 yield 协议调用
2. GenDataFooter 保存/恢复
3. resumeEntry() 间接调用

**状态机优化后**:
1. 单次函数调用
2. 直接状态跳转（Branch）
3. 无间接调用

---

## 测试验证

### 单元测试
```bash
# 运行 C++ 单元测试
cd build && ctest -R state_machine -V
```

### 集成测试
```bash
# 运行 Python 集成测试
PYTHONJITHUGEPAGES=0 PYTHONJIT=1 \
  .venv/bin/python3 test_state_machine.py -v
```

### 性能测试
```bash
# 运行性能基准测试
PYTHONJITHUGEPAGES=0 PYTHONJIT=1 \
  .venv/bin/python3 benchmark_state_machine.py

# 验证 4-6x 改进
# depth=2: 目标 1.5x
# depth=3: 目标 2.5x
# depth=5: 目标 4-6x
```

---

## 风险和注意事项

### 风险 1: 状态机膨胀
- **问题**: 深度过深的树会导致状态数爆炸
- **解决方案**: 限制 `kMaxFlattenDepth = 3`，超过则回退到 InlineIter

### 风险 2: 正确性验证
- **问题**: 状态机生成可能引入 bug
- **解决方案**:
  1. 单元测试验证每个状态块
  2. 集成测试验证整体行为
  3. HIR dump 验证结构

### 风险 3: 性能回归
- **问题**: 状态机可能比原代码更慢
- **解决方案**: 性能测试对比，只在有改进时启用

---

## 实施时间线

| 步骤 | 任务 | 估计时间 | 状态 |
|------|------|---------|------|
| 1 | 集成到 pipeline | 0.5 天 | ⏳ 待开始 |
| 2 | 状态块逻辑 | 0.5 天 | ⏳ 待开始 |
| 3 | YieldFrom 替换 | 1 天 | ⏳ 待开始 |
| 4 | 嵌套展平 | 1.5 天 | ⏳ 待开始 |
| 5 | 性能测试验证 | 0.5 天 | ⏳ 待开始 |
| **总计** | - | **3.5 天** | - |

---

## 下一步行动

### 立即行动 (今天)
1. 集成 TreeIterStateMachinePass 到编译 pipeline
2. 运行测试验证框架工作

### 明天
1. 实现状态块的实际逻辑
2. 实现 YieldFrom 替换

### 后天
1. 实现嵌套展平
2. 性能测试验证

---

**维护者**: Claude Code Agent
**最后更新**: 2026-03-24
