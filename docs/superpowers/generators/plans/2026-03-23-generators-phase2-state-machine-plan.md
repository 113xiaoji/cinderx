# Phase 2 实施计划：状态机生成

**版本**: 1.0
**日期**: 2026-03-23
**目标**: 在 HIR Builder 阶段生成状态机，消除运行时状态管理
**预期性能**: 4-6x 改进（深度 ≤ 5）

---

## 1. 概述

### 1.1 目标

在 HIR Builder 阶段为非逃逸生成器生成显式状态机，通过以下方式提升性能：

1. **消除运行时状态管理**：状态在编译时确定
2. **保留 InlineIter 作为回退**：深度 > 3 使用 Phase 1 优化
3. **复用现有退优化机制**：使用 yield point 退优化

### 1.2 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      HIR Builder                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  GeneratorHIR  ──→  StateMachineGenerator  ──→  HIR BBs   │
│                                                              │
│  ┌─────────────┐    ┌──────────────────┐                   │
│  │ Escape      │───→│ CanInline?       │                   │
│  │ Analysis    │    │  depth ≤ 3       │                   │
│  └─────────────┘    │  states ≤ 50      │                   │
│                      └──────────────────┘                   │
│                              │                               │
│              ┌───────────────┼───────────────┐             │
│              ▼               ▼               ▼             │
│        ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│        │ Flatten  │  │ Partial  │  │ InlineIter│         │
│        │ State    │  │ Flatten  │  │ (Phase 1) │         │
│        │ Machine  │  │ + Inline  │  │           │         │
│        └──────────┘  └──────────┘  └──────────┘         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 预期性能

| 树深度 | 策略 | 性能改进 | 代码大小 |
|--------|------|----------|---------|
| ≤ 2 | 完全扁平化 | 5-8x ⭐ | +20% |
| 3-5 | 部分扁平化 | 4-6x ✅ | +30% |
| > 5 | InlineIter | 3-4x ⚠️ | +10% |

---

## 2. 技术设计

### 2.1 数据结构扩展

#### GenDataFooter 扩展

```cpp
// cinderx/Jit/gen_data_footer.h
struct GenDataFooter {
  // 现有字段...
  uint64_t linkAddress{};
  uint64_t returnAddress{};
  uint64_t originalFramePointer{};
  GenYieldPoint* yieldPoint{};
  size_t spillWords{};
  GenResumeFunc resumeEntry{};
  PyGenObject* gen{};
  CodeRuntime* code_rt{nullptr};

  // Phase 2 新增：状态机状态
  int32_t currentState{};  // 当前状态，-1 = 未初始化
};

// 状态定义
enum class GeneratorState : int32_t {
  UNINIT = -1,    // 未初始化
  INIT = 0,       // 初始状态
  // 动态生成的状态...
  DONE = INT32_MAX // 完成状态
};
```

#### HIR 指令新增

```cpp
// cinderx/Jit/hir/hir.h

// 状态机相关指令

// 1. 状态分发指令
class StateSwitch : public Terminator {
  Register* state_var;
  Vector<pair<int, BasicBlock*>> targets;
};

// 2. 状态保存指令
class SaveState : public Instruction {
  Register* state_var;
  int32_t new_state;
};

// 3. 状态加载指令
class LoadState : public Instruction {
  // 输出：当前状态
};

// 4. Yield From 内联指令（叶子节点）
class YieldFromInline : public Terminator {
  Register* receiver;
  const char* field_name;  // "left" or "right"
  int next_state;
};
```

### 2.2 状态机生成算法

```cpp
// cinderx/Jit/hir/state_machine_generator.cpp

class StateMachineGenerator {
  // 配置
  static constexpr int kMaxFlattenDepth = 3;
  static constexpr int kMaxStates = 50;

 public:
  // 主入口
  Vector<BasicBlock*> generate(GeneratorHIR* gen_hir, int depth);

 private:
  // 检查是否可以扁平化
  bool canFlatten(GeneratorHIR* gen, int depth) {
    if (depth > kMaxFlattenDepth) return false;
    if (countStates(gen) > kMaxStates) return false;
    if (!isTreePattern(gen)) return false;
    if (hasDynamicDispatch(gen)) return false;
    return true;
  }

  // 扁平化生成器
  Vector<BasicBlock*> flattenGenerator(GeneratorHIR* gen, int depth) {
    Vector<BasicBlock*> blocks;

    // 1. 创建状态分发基本块
    BasicBlock* dispatch = createDispatchBlock(gen);
    blocks.push_back(dispatch);

    // 2. 为每个状态创建基本块
    for (auto& state : gen->states()) {
      BasicBlock* bb = emitState(gen, state, depth);
      blocks.push_back(bb);
    }

    // 3. 添加结束基本块
    BasicBlock* done = createDoneBlock(gen);
    blocks.push_back(done);

    return blocks;
  }

  // 生成状态基本块
  BasicBlock* emitState(GeneratorHIR* gen, State& state, int depth) {
    BasicBlock* bb = createBasicBlock(state.name());

    // 设置下一个状态
    emit<SaveState>(state_var, state.next_state);

    // emit 状态内容
    switch (state.type()) {
      case StateType::YieldFromLeft:
        if (canFlatten(state.sub_generator(), depth + 1)) {
          // 递归扁平化
          auto sub_blocks = flattenGenerator(state.sub_generator(), depth + 1);
          bb->append(sub_blocks);
        } else {
          // 回退到 InlineIter
          emit<InlineIter>(state.iter(), state.next_state);
        }
        break;

      case StateType::YieldValue:
        emit<Yield>(state.value());
        break;

      case StateType::Return:
        emit<Return>(state.return_value());
        break;
    }

    // 跳转到分发基本块
    bb->append<Goto>(dispatch);

    return bb;
  }
};
```

### 2.3 HIR 生成示例

**输入：树遍历生成器（深度 2）**

```python
class Node:
    def __iter__(self):
        if self.left:
            yield from self.left
        yield self.value
        if self.right:
            yield from self.right
```

**输出：扁平化状态机 HIR**

```
BB_entry:
  %state = Load GenDataFooter.currentState
  %is_init = Compare %state == -1
  Branch %is_init, BB_init, BB_dispatch

BB_init:
  Store GenDataFooter.currentState, 0
  Jump BB_dispatch

BB_dispatch:
  Switch %state, [
    0: BB_state_0_left_left,
    1: BB_state_0_left_value,
    2: BB_state_0_value,
    3: BB_state_0_right,
    4: BB_done
  ]

// ===== State 0: yield from left.left =====
BB_state_0_left_left:
  %ll = LoadField self.left.left
  if %ll == null:
    Store %state, 1
    Jump BB_dispatch
  %llv = LoadField %ll.value
  Yield %llv
  // ... 继续遍历 left.left
  Store %state, 1
  Jump BB_dispatch

// ===== State 1: yield left.value =====
BB_state_0_left_value:
  %lv = LoadField self.left.value
  Yield %lv
  Store %state, 2
  Jump BB_dispatch

// ===== State 2: yield self.value =====
BB_state_0_value:
  %v = LoadField self.value
  Yield %v
  Store %state, 3
  Jump BB_dispatch

// ===== State 3: yield from right =====
BB_state_0_right:
  %r = LoadField self.right
  if %r == null:
    Store %state, 4
    Jump BB_dispatch
  // 类似 left 处理...

// ===== Done =====
BB_done:
  Return
```

---

## 3. 实施任务

### 3.1 任务分解

#### 阶段 1：基础设施（Week 1）

| 任务 | 描述 | 文件 | 估计时间 |
|------|------|------|---------|
| T1.1 | 扩展 GenDataFooter 添加 currentState | gen_data_footer.h | 0.5 天 |
| T1.2 | 新增 StateSwitch HIR 指令 | hir.h, hir_ops.h | 1 天 |
| T1.3 | 新增 SaveState/LoadState HIR 指令 | hir.h, hir_ops.h | 1 天 |
| T1.4 | 新增 YieldFromInline HIR 指令 | hir.h, hir_ops.h | 1 天 |
| T1.5 | 添加 HIR printer 支持新指令 | printer.cpp | 0.5 天 |
| T1.6 | 添加 HIR parser 支持新指令 | parser.cpp | 0.5 天 |

#### 阶段 2：状态机生成器（Week 2）

| 任务 | 描述 | 文件 | 估计时间 |
|------|------|------|---------|
| T2.1 | 创建 StateMachineGenerator 类 | state_machine_gen.cpp/h | 2 天 |
| T2.2 | 实现 canFlatten 启发式 | state_machine_gen.cpp | 1 天 |
| T2.3 | 实现扁平化生成逻辑 | state_machine_gen.cpp | 2 天 |
| T2.4 | 实现状态分发基本块生成 | state_machine_gen.cpp | 1 天 |
| T2.5 | 实现回退到 InlineIter | state_machine_gen.cpp | 1 天 |

#### 阶段 3：集成和优化（Week 3）

| 任务 | 描述 | 文件 | 估计时间 |
|------|------|------|---------|
| T3.1 | 在 simplify.cpp 中集成 | simplify.cpp | 2 天 |
| T3.2 | 添加 HIR 优化 pass（状态合并） | optimize.cpp | 1 天 |
| T3.3 | LIR 代码生成支持 | codegen/autogen.cpp | 2 天 |
| T3.4 | ARM64 代码生成支持 | codegen/autogen.cpp | 2 天 |

#### 阶段 4：测试和验证（Week 4）

| 任务 | 描述 | 文件 | 估计时间 |
|------|------|------|---------|
| T4.1 | 单元测试：状态机生成 | test_state_machine.cpp | 1 天 |
| T4.2 | 集成测试：树遍历 | test_inline_iter.py | 1 天 |
| T4.3 | 性能基准测试 | benchmark.py | 1 天 |
| T4.4 | 边界情况测试 | test_edge_cases.py | 1 天 |
| T4.5 | Bug 修复和调优 | - | 2 天 |

### 3.2 里程碑

```
Week 1: 基础设施完成
  ✓ GenDataFooter 扩展
  ✓ 新 HIR 指令定义
  ✓ HIR 打印/解析支持

Week 2: 状态机生成器完成
  ✓ StateMachineGenerator 类
  ✓ canFlatten 启发式
  ✓ 扁平化生成逻辑

Week 3: 集成完成
  ✓ simplify.cpp 集成
  ✓ HIR 优化 pass
  ✓ LIR 代码生成

Week 4: 测试完成
  ✓ 单元测试
  ✓ 集成测试
  ✓ 性能测试
  ✓ 文档更新
```

---

## 4. 风险和缓解

### 4.1 风险列表

| 风险 | 可能性 | 影响 | 缓解策略 |
|------|--------|------|---------|
| 代码膨胀失控 | 中 | 高 | 限制状态数（≤50），强制 InlineIter 回退 |
| 编译时间增加 | 高 | 中 | 增量编译，缓存状态机模板 |
| 状态机生成 bug | 高 | 高 | 充分测试，保留回退路径 |
| 性能未达预期 | 中 | 高 | 监控性能，动态调整启发式 |
| 栈溢出（深度递归） | 低 | 中 | 限制扁平化深度（≤3） |

### 4.2 缓解措施

1. **代码膨胀控制**
   ```cpp
   // 强制回退条件
   if (countStates() > 50 || depth > 3) {
     return emit<InlineIter>(...);  // 回退到 Phase 1
   }
   ```

2. **编译时间控制**
   ```cpp
   // 缓存已生成的状态机
   static LRUCache<GeneratorSig, Vector<BasicBlock*>> state_machine_cache;
   ```

3. **测试覆盖**
   ```python
   # 覆盖所有深度和模式
   test_depths = [1, 2, 3, 4, 5, 10, 100]
   test_patterns = ['tree', 'list', 'mixed']
   ```

---

## 5. 成功指标

### 5.1 性能指标

| 指标 | Phase 1 | Phase 2 目标 | 验证方法 |
|------|---------|--------------|---------|
| Depth 3 改进 | 32% | 4-5x | benchmark.py |
| Depth 5 改进 | 10% | 3-4x | benchmark.py |
| 编译时间增加 | 0% | ≤10% | 编译计时 |
| 代码大小增加 | 0% | ≤30% | 二进制大小 |

### 5.2 功能指标

- [ ] 支持深度 ≤ 3 的树完全扁平化
- [ ] 深度 > 3 正确回退到 InlineIter
- [ ] 所有现有测试通过
- [ ] 退优化正常工作
- [ ] 无内存泄漏

### 5.3 质量指标

- [ ] 代码审查通过
- [ ] 文档完整
- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 集成测试覆盖率 100%

---

## 6. 测试计划

### 6.1 单元测试

```cpp
// test_state_machine.cpp

TEST(StateMachineGenerator, FlattenDepth2) {
  // 测试深度 2 树扁平化
}

TEST(StateMachineGenerator, FallbackToInlineIter) {
  // 测试深度 > 3 回退
}

TEST(StateMachineGenerator, EmptySubtrees) {
  // 测试空子树处理
}

TEST(StateMachineGenerator, StateSwitchCorrect) {
  // 测试状态转换正确性
}
```

### 6.2 集成测试

```python
# test_phase2.py

def test_depth_3_tree():
    """深度 3 树应完全扁平化"""
    pass

def test_depth_5_tree():
    """深度 5 树应部分扁平化"""
    pass

def test_deep_tree():
    """深度 10+ 树应回退到 InlineIter"""
    pass

def test_performance_improvement():
    """性能改进应 ≥ 4x (depth 3)"""
    pass
```

### 6.3 性能测试

```python
# benchmark_phase2.py

def benchmark_tree_traversal():
    for depth in [3, 5, 10]:
        measure_performance(depth)
        compare_with_phase1()
        verify_improvement()
```

---

## 7. 文档

### 7.1 需要更新的文档

- [ ] `cinderx/Jit/inline_iter.md` - 添加 Phase 2 设计
- [ ] `docs/superpowers/generators/` - 添加 Phase 2 计划
- [ ] `cinderx/Jit/guide.md` - 更新 JIT 架构文档
- [ ] 代码注释 - 添加状态机生成器文档

### 7.2 新增文档

- [ ] `cinderx/Jit/state_machine.md` - 状态机生成器设计文档
- [ ] `docs/superpowers/generators/diagnostics/2026-03-XX-phase2-implementation-report.md` - 实施报告

---

## 8. 实施检查清单

### Week 1: 基础设施
- [ ] T1.1: GenDataFooter 扩展
- [ ] T1.2: StateSwitch HIR 指令
- [ ] T1.3: SaveState/LoadState HIR 指令
- [ ] T1.4: YieldFromInline HIR 指令
- [ ] T1.5: HIR printer 支持
- [ ] T1.6: HIR parser 支持

### Week 2: 状态机生成器
- [ ] T2.1: StateMachineGenerator 类
- [ ] T2.2: canFlatten 启发式
- [ ] T2.3: 扁平化生成逻辑
- [ ] T2.4: 状态分发基本块生成
- [ ] T2.5: 回退到 InlineIter

### Week 3: 集成和优化
- [ ] T3.1: simplify.cpp 集成
- [ ] T3.2: HIR 优化 pass
- [ ] T3.3: LIR 代码生成
- [ ] T3.4: ARM64 代码生成

### Week 4: 测试和验证
- [ ] T4.1: 单元测试
- [ ] T4.2: 集成测试
- [ ] T4.3: 性能基准测试
- [ ] T4.4: 边界情况测试
- [ ] T4.5: Bug 修复和调优

---

## 9. 附录

### A. 参考文档

- [Phase 1 总结](./diagnostics/2026-03-23-generators-inline-iter-phase1-summary.md)
- [状态机研究](./research/2026-03-23-generators-phase2-state-machine-research.md)
- [InlineIter 技术文档](../../../cinderx/Jit/inline_iter.md)

### B. 相关文件

```
cinderx/Jit/
├── hir/
│   ├── state_machine_gen.cpp    [新增]
│   ├── state_machine_gen.h      [新增]
│   ├── hir.h                    [修改]
│   ├── hir_ops.h                [修改]
│   ├── simplify.cpp             [修改]
│   └── ...
├── codegen/
│   └── autogen.cpp              [修改]
└── gen_data_footer.h           [修改]
```

### C. 术语表

| 术语 | 定义 |
|------|------|
| 扁平化 (Flatten) | 将嵌套生成器展开为单层状态机 |
| 状态分发 (Dispatch) | 根据当前状态跳转到对应基本块 |
| 回退 (Fallback) | 不满足条件时使用 InlineIter |
| 状态变量 | 跟踪生成器当前执行状态的变量 |

---

**计划创建日期**: 2026-03-23
**计划版本**: 1.0
**下次审查**: 实施开始后 1 周
