# Phase 2 Week 2 TDD 测试策略

**创建日期**: 2026-03-24
**状态**: 📋 计划中

---

## 测试原则

### 1. 测试驱动开发（TDD）

**原则**: 先写测试，再写实现

**流程**:
```
1. 编写测试用例（描述期望行为）
2. 运行测试（预期失败）
3. 编写最小实现
4. 运行测试（预期通过）
5. 重构代码
6. 重复
```

### 2. 测试金字塔

```
        /\
       /  \  E2E测试（少量）
      /----\
     / 集成  \ 集成测试（适量）
    /--------\
   /  单元测试  \ 单元测试（大量）
  /------------\
```

---

## Week 2 子任务测试计划

### T2.1 - Yield-From 模式识别

**测试文件**: `cinderx/RuntimeTests/test_state_machine_pattern.cpp`

**测试用例**:

```cpp
// 1. 基本树遍历模式
TEST(StateMachinePattern, TreeIterPattern) {
  // 输入: yield from self.left / yield from self.right
  // 期望: isTreePattern() == true
  // 期望: fields.size() == 2
  // 期望: depth == 1
}

// 2. 嵌套树遍历模式（depth=2）
TEST(StateMachinePattern, NestedTreeIter) {
  // 输入: 嵌套的 yield from
  // 期望: depth == 2
  // 期望: fields 包含 left.left, left.value, self.value
}

// 3. 非树遍历模式
TEST(StateMachinePattern, NotTreeIter) {
  // 输入: yield from other_iter (不是 self.left/right)
  // 期望: isTreePattern() == false
  // 期望: detectPattern() == nullptr
}

// 4. 空子树处理
TEST(StateMachinePattern, EmptySubtrees) {
  // 输入: self.left = None
  // 期望: 模式仍然识别
  // 期望: 生成正确的状态数
}

// 5. 深度限制
TEST(StateMachinePattern, DepthLimit) {
  // 输入: depth > 3
  // 期望: canFlatten() == false
  // 期望: 回退到 InlineIter
}

// 6. 状态数限制
TEST(StateMachinePattern, StateLimit) {
  // 输入: countStates() > 50
  // 期望: canFlatten() == false
  // 期望: 回退到 InlineIter
}
```

**估计时间**: 0.5 天（与T2.1并行）

---

### T2.2 - 状态机构建器

**测试文件**: `cinderx/RuntimeTests/test_state_machine_builder.cpp`

**测试用例**:

```cpp
// 1. 基本状态机结构
TEST(StateMachineBuilder, BasicStructure) {
  // 输入: depth=1 的树遍历
  // 期望:
  //   - entry_block 存在
  //   - dispatch_block 存在
  //   - done_block 存在
  //   - states.size() == 3 (left, value, right)
}

// 2. 入口块生成
TEST(StateMachineBuilder, EntryBlock) {
  // 输入: 状态机
  // 期望:
  //   - 加载 LoadState 指令
  //   - 检查 state == -1
  //   - 条件跳转到 init 或 dispatch
  //   - init 块设置 state = 0
}

// 3. 分发块生成
TEST(StateMachineBuilder, DispatchBlock) {
  // 输入: 3 个状态的状态机
  // 期望:
  //   - 使用 CondBranch 链
  //   - 检查 state == 0, 1, 2
  //   - 跳转到对应的状态块
  //   - 默认跳转到 done
}

// 4. 完成块生成
TEST(StateMachineBuilder, DoneBlock) {
  // 输入: 状态机
  // 期望:
  //   - 包含 Return 指令
  //   - 返回 None
}

// 5. 状态块生成（占位符）
TEST(StateMachineBuilder, StateBlocks) {
  // 输入: 状态机
  // 期望:
  //   - 每个状态有对应的基本块
  //   - 块中有 Return None（占位符）
  // TODO: 未来验证 YieldValue
}

// 6. Self 参数查找
TEST(StateMachineBuilder, SelfArgument) {
  // 输入: 带 self 参数的函数
  // 期望:
  //   - 找到 LoadArg(0) 指令
  //   - self_reg != nullptr
}

// 7. FrameState 传递
TEST(StateMachineBuilder, FrameStatePassing) {
  // 输入: 带 FrameState 的调用
  // 期望:
  //   - frame_state != nullptr
  //   - 可用于生成 YieldValue
}
```

**估计时间**: 0.5 天（与T2.2并行）

---

### T2.3 - 嵌套展平

**测试文件**: `cinderx/RuntimeTests/test_state_machine_flatten.cpp`

**测试用例**:

```cpp
// 1. 单层展平
TEST(StateMachineFlatten, SingleLayer) {
  // 输入: depth=1 的树遍历
  // 期望:
  //   - 状态数 = 3 (left, value, right)
  //   - 无嵌套状态
}

// 2. 两层展平
TEST(StateMachineFlatten, TwoLayers) {
  // 输入: depth=2 的树遍历
  // 期望:
  //   - 状态数 = 7 (ll, lv, l, v, r, rv, rl)
  //   - 所有状态扁平化
  //   - 无 YieldFrom 指令
}

// 3. 三层展平
TEST(StateMachineFlatten, ThreeLayers) {
  // 输入: depth=3 的树遍历
  // 期望:
  //   - 状态数 ≈ 15
  //   - 所有嵌套展开
}

// 4. 深度超限回退
TEST(StateMachineFlatten, DepthExceeded) {
  // 输入: depth=4 的树遍历
  // 期望:
  //   - canFlatten() == false
  //   - 回退到 InlineIter
  //   - 或部分展平（depth=3）
}

// 5. 混合模式
TEST(StateMachineFlatten, MixedPattern) {
  // 输入: 混合 tree + list
  // 期望:
  //   - tree 部分展平
  //   - list 部分使用 InlineIter
  //   - 或整体回退
}
```

**估计时间**: 0.5 天（与T2.3并行）

---

### T2.4 - HIR 生成

**测试文件**: `cinderx/RuntimeTests/test_state_machine_hir.cpp`

**测试用例**:

```cpp
// 1. HIR 正确性
TEST(StateMachineHIR, HIRCorrectness) {
  // 输入: 树遍历生成器
  // 期望:
  //   - HIR 语法正确
  //   - 所有基本块连接正确
  //   - 无悬空引用
}

// 2. HIR 打印/解析
TEST(StateMachineHIR, HIRPrintParse) {
  // 输入: 生成的状态机 HIR
  // 期望:
  //   - 可以打印为文本
  //   - 可以解析回来
  //   - 解析后的 HIR 与原始一致
}

// 3. CFG 验证
TEST(StateMachineHIR, CFGValidation) {
  // 输入: 状态机 CFG
  // 期望:
  //   - 入口块可达
  //   - 所有状态块可达
  //   - done 块可达
  //   - 无死代码
}

// 4. 寄存器分配
TEST(StateMachineHIR, RegisterAllocation) {
  // 输入: 状态机 HIR
  // 期望:
  //   - 所有寄存器正确分配
  //   - 无寄存器泄漏
  //   - Phi 节点正确
}
```

**估计时间**: 0.5 天（与T2.4并行）

---

### T2.5 - 与 Escape Analysis 集成

**测试文件**: `cinderx/RuntimeTests/test_state_machine_integration.cpp`

**测试用例**:

```cpp
// 1. 集成到 simplifyYieldFrom
TEST(StateMachineIntegration, SimplifyYieldFrom) {
  // 输入: YieldFrom 指令
  // 期望:
  //   - 调用 StateMachineGenerator
  //   - 返回状态机或 InlineIter
}

// 2. 与 InlineIter 协作
TEST(StateMachineIntegration, InlineIterFallback) {
  // 输入: 深度超限的树遍历
  // 期望:
  //   - 优先尝试状态机
  //   - 失败后回退到 InlineIter
  //   - 不会崩溃
}

// 3. 与 OptimizedYieldFrom 协作
TEST(StateMachineIntegration, OptimizedYieldFromFallback) {
  // 输入: 非树遍历模式
  // 期望:
  //   - 回退到 OptimizedYieldFrom
  //   - 不生成状态机
}

// 4. 端到端测试
TEST(StateMachineIntegration, EndToEnd) {
  // 输入: 完整的 Python 树遍历函数
  // 期望:
  //   - JIT 编译成功
  //   - 执行结果正确
  //   - 性能提升明显
}
```

**估计时间**: 0.5 天（与T2.5并行）

---

## Python 集成测试

### 测试文件: `test_state_machine.py`

```python
import cinderx
import unittest

class TestStateMachine(unittest.TestCase):
    """状态机生成器集成测试"""

    def setUp(self):
        cinderx.jit.auto()

    def test_basic_tree_traversal(self):
        """基本树遍历"""
        class Node:
            def __init__(self, value, left=None, right=None):
                self.value = value
                self.left = left
                self.right = right

            def __iter__(self):
                if self.left:
                    yield from self.left
                yield self.value
                if self.right:
                    yield from self.right

        # 构建树
        tree = Node(2,
                   Node(1),
                   Node(3))

        # 验证结果
        result = list(tree)
        self.assertEqual(result, [1, 2, 3])

    def test_nested_tree(self):
        """嵌套树遍历（depth=2）"""
        # 构建更深的树
        tree = Node(4,
                   Node(2,
                       Node(1),
                       Node(3)),
                   Node(6,
                       Node(5),
                       Node(7)))

        result = list(tree)
        self.assertEqual(result, [1, 2, 3, 4, 5, 6, 7])

    def test_empty_subtrees(self):
        """空子树处理"""
        tree = Node(1)
        result = list(tree)
        self.assertEqual(result, [1])

        tree = Node(2, Node(1))
        result = list(tree)
        self.assertEqual(result, [1, 2])

    def test_large_tree(self):
        """大树遍历（性能测试）"""
        def build_tree(depth):
            if depth == 0:
                return None
            return Node(depth,
                       build_tree(depth - 1),
                       build_tree(depth - 1))

        tree = build_tree(5)
        result = list(tree)
        # 验证节点数
        expected_count = 2 ** 5 - 1  # 31 nodes
        self.assertEqual(len(result), expected_count)

    def test_state_machine_generation(self):
        """验证状态机生成"""
        # TODO: 添加 HIR dump 验证
        # TODO: 验证状态数
        # TODO: 验证基本块结构
        pass

if __name__ == '__main__':
    unittest.main()
```

**估计时间**: 0.5 天

---

## 性能基准测试

### 测试文件: `benchmark_state_machine.py`

```python
import time
import cinderx

class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        if self.left:
            yield from self.left
        yield self.value
        if self.right:
            yield from self.right

def build_tree(depth):
    if depth == 0:
        return None
    return Node(depth,
               build_tree(depth - 1),
               build_tree(depth - 1))

def benchmark(depth, iterations=100):
    tree = build_tree(depth)

    # Warmup
    for _ in range(10):
        list(tree)

    # Benchmark
    start = time.time()
    for _ in range(iterations):
        list(tree)
    end = time.time()

    avg_time = (end - start) / iterations * 1000  # ms
    node_count = 2 ** depth - 1
    print(f"depth={depth}: {node_count} nodes, {avg_time:.4f}ms/iter")

    return avg_time

if __name__ == '__main__':
    cinderx.jit.auto()

    print("Phase 2 State Machine Performance Benchmark")
    print("=" * 50)

    for depth in [3, 5, 7, 10]:
        benchmark(depth)

    print("\nExpected improvement: 4-6x (depth ≤ 5)")
```

**估计时间**: 0.5 天

---

## 测试时间表

| 任务 | 测试文件 | 开发时间 | 测试时间 | 总计 |
|------|---------|---------|---------|------|
| T2.1 | test_state_machine_pattern.cpp | 1.5 天 | 0.5 天 | 2 天 |
| T2.2 | test_state_machine_builder.cpp | 2 天 | 0.5 天 | 2.5 天 |
| T2.3 | test_state_machine_flatten.cpp | 1.5 天 | 0.5 天 | 2 天 |
| T2.4 | test_state_machine_hir.cpp | 1.5 天 | 0.5 天 | 2 天 |
| T2.5 | test_state_machine_integration.cpp | 0.5 天 | 0.5 天 | 1 天 |
| **集成测试** | test_state_machine.py | - | 0.5 天 | 0.5 天 |
| **性能测试** | benchmark_state_machine.py | - | 0.5 天 | 0.5 天 |
| **总计** | - | **7 天** | **3.5 天** | **10.5 天** |

---

## CI/CD 集成

### GitHub Actions 配置

```yaml
name: State Machine Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Build CinderX
        run: |
          python -m build --wheel
          pip install dist/*.whl

      - name: Run C++ Tests
        run: |
          cd build
          ctest --output-on-failure

      - name: Run Python Tests
        run: |
          pytest cinderx/PythonLib/test_cinderx/test_state_machine.py

      - name: Run Performance Benchmarks
        run: |
          python benchmark_state_machine.py
```

---

## 测试覆盖率目标

| 类型 | 目标 | 当前 |
|------|------|------|
| 单元测试 | ≥ 80% | 0% |
| 集成测试 | 100% | 0% |
| 性能测试 | 4-6x | - |
| 边界情况 | 100% | 0% |

---

## 下一步行动

1. **立即创建 T2.1 测试** - 在继续实现之前
2. **为 T2.2 添加测试** - 验证当前实现
3. **设置 CI/CD** - 自动化测试
4. **创建测试框架** - 简化测试编写

---

**维护者**: Claude Code Agent
**最后更新**: 2026-03-24
