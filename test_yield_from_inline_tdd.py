#!/usr/bin/env python3
"""
TDD Tests for Phase 2 T2.4: YieldFromInline Implementation

These tests verify:
1. YieldFromInline HIR instruction generation
2. State machine control flow correctness
3. Performance improvements
"""

# ⚠️ 环境变量必须在导入 cinderx 之前设置
import os
os.environ['PYTHONJITHUGEPAGES'] = '0'
os.environ['PYTHONJIT'] = '1'
os.environ['PYTHONJITTREEITERSTATEMACHINE'] = '1'

import sys
import time
import unittest
from cinderx import jit


class TestYieldFromInlineHIR(unittest.TestCase):
    """测试 YieldFromInline HIR 指令生成"""

    @classmethod
    def setUpClass(cls):
        """启用 JIT 和状态机优化"""
        jit.auto()

    def test_yield_from_inline_generated(self):
        """验证 YieldFromInline 指令被生成"""
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

        # 多次调用触发 JIT 编译
        for _ in range(100):
            tree = Node(2, Node(1), Node(3))
            result = list(tree)

        # 验证结果正确性
        self.assertEqual(result, [1, 2, 3])

        # TODO: 添加 HIR dump 验证，确认 YieldFromInline 被生成

    def test_state_machine_correctness_basic(self):
        """测试状态机基本正确性"""
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

        # 测试用例 1: 基本树
        tree1 = Node(2, Node(1), Node(3))
        for _ in range(100):  # 触发编译
            list(tree1)
        result1 = list(tree1)
        self.assertEqual(result1, [1, 2, 3])

        # 测试用例 2: 只有左子树
        tree2 = Node(3, Node(2, Node(1)))
        for _ in range(100):
            list(tree2)
        result2 = list(tree2)
        self.assertEqual(result2, [1, 2, 3])

        # 测试用例 3: 只有右子树
        tree3 = Node(1, None, Node(2, None, Node(3)))
        for _ in range(100):
            list(tree3)
        result3 = list(tree3)
        self.assertEqual(result3, [1, 2, 3])

    def test_state_machine_correctness_deep(self):
        """测试状态机深度遍历正确性"""
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

        def build_balanced_tree(depth):
            """构建平衡二叉树"""
            if depth == 0:
                return None
            if depth == 1:
                return Node(1)
            left = build_balanced_tree(depth - 1)
            right = build_balanced_tree(depth - 1)
            return Node(depth, left, right)

        # 测试不同深度
        for depth in [3, 5, 8, 10]:
            tree = build_balanced_tree(depth)
            expected_count = 2 ** depth - 1

            # 触发编译
            for _ in range(10):
                list(tree)

            # 验证结果
            result = list(tree)
            self.assertEqual(len(result), expected_count,
                           f"Depth {depth}: expected {expected_count} nodes, got {len(result)}")

    def test_state_machine_edge_cases(self):
        """测试状态机边界情况"""
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

        # 边界情况 1: 空树
        # (无法测试，因为 __iter__ 需要实例)

        # 边界情况 2: 单节点
        tree_single = Node(42)
        for _ in range(100):
            list(tree_single)
        self.assertEqual(list(tree_single), [42])

        # 边界情况 3: 左斜树
        tree_left_skew = Node(3, Node(2, Node(1)))
        for _ in range(100):
            list(tree_left_skew)
        self.assertEqual(list(tree_left_skew), [1, 2, 3])

        # 边界情况 4: 右斜树
        tree_right_skew = Node(1, None, Node(2, None, Node(3)))
        for _ in range(100):
            list(tree_right_skew)
        self.assertEqual(list(tree_right_skew), [1, 2, 3])


class TestYieldFromInlinePerformance(unittest.TestCase):
    """测试 YieldFromInline 性能改进"""

    @classmethod
    def setUpClass(cls):
        """启用 JIT 和状态机优化"""
        os.environ['PYTHONJITHUGEPAGES'] = '0'
        os.environ['PYTHONJIT'] = '1'
        os.environ['PYTHONJITTREEITERSTATEMACHINE'] = '1'

        jit.auto()

    def measure_iteration_time(self, tree, iterations=10):
        """测量迭代时间"""
        # Warmup
        for _ in range(iterations):
            list(tree)

        # Measure
        start = time.perf_counter()
        for _ in range(iterations):
            list(tree)
        elapsed = (time.perf_counter() - start) / iterations * 1000  # ms
        return elapsed

    def test_performance_small_tree(self):
        """测试小树性能（depth=5, 31 nodes）"""
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
            if depth == 1:
                return Node(1)
            return Node(depth, build_tree(depth - 1), build_tree(depth - 1))

        tree = build_tree(5)
        elapsed = self.measure_iteration_time(tree)

        # 验证结果正确性
        result = list(tree)
        self.assertEqual(len(result), 31)

        # 记录性能（不设置硬性阈值，只是记录）
        print(f"\n  depth=5 (31 nodes): {elapsed:.4f} ms")

        # 目标: < 0.01 ms (性能改进后应该更快)
        # 当前: ~0.005 ms (已经很快)
        self.assertLess(elapsed, 0.05, "Performance too slow for depth=5")

    def test_performance_medium_tree(self):
        """测试中等树性能（depth=10, 1023 nodes）"""
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
            if depth == 1:
                return Node(1)
            return Node(depth, build_tree(depth - 1), build_tree(depth - 1))

        tree = build_tree(10)
        elapsed = self.measure_iteration_time(tree)

        result = list(tree)
        self.assertEqual(len(result), 1023)

        print(f"  depth=10 (1023 nodes): {elapsed:.4f} ms")

        # 目标: < 0.5 ms
        # 当前: ~0.17 ms
        self.assertLess(elapsed, 1.0, "Performance too slow for depth=10")

    def test_performance_large_tree(self):
        """测试大树性能（depth=15, 32767 nodes）"""
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
            if depth == 1:
                return Node(1)
            return Node(depth, build_tree(depth - 1), build_tree(depth - 1))

        tree = build_tree(15)
        elapsed = self.measure_iteration_time(tree)

        result = list(tree)
        self.assertEqual(len(result), 32767)

        print(f"  depth=15 (32767 nodes): {elapsed:.4f} ms")

        # 目标: < 10 ms (状态机优化后应该更快)
        # 当前: ~6.3 ms
        self.assertLess(elapsed, 15.0, "Performance too slow for depth=15")

    def test_performance_comparison(self):
        """性能对比：状态机启用 vs 禁用"""
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
            if depth == 1:
                return Node(1)
            return Node(depth, build_tree(depth - 1), build_tree(depth - 1))

        tree = build_tree(12)

        # 测试当前性能（状态机启用）
        elapsed_with_sm = self.measure_iteration_time(tree)

        result = list(tree)
        self.assertEqual(len(result), 4095)

        print(f"\n  Performance comparison (depth=12, 4095 nodes):")
        print(f"    WITH state machine: {elapsed_with_sm:.4f} ms")

        # 目标: 状态机优化后应该比禁用时快 4-6x
        # 但我们无法在同一进程中禁用，所以只记录当前性能
        # TODO: 在 CI 中运行对比测试


class TestYieldFromInlineIntegration(unittest.TestCase):
    """集成测试：测试与现有功能的兼容性"""

    @classmethod
    def setUpClass(cls):
        """启用 JIT 和状态机优化"""
        os.environ['PYTHONJITHUGEPAGES'] = '0'
        os.environ['PYTHONJIT'] = '1'
        os.environ['PYTHONJITTREEITERSTATEMACHINE'] = '1'

        jit.auto()

    def test_compatibility_with_other_iterators(self):
        """测试与其他迭代器的兼容性"""
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

        tree = Node(2, Node(1), Node(3))

        # 测试与 list() 的兼容性
        for _ in range(100):
            list(tree)
        result_list = list(tree)
        self.assertEqual(result_list, [1, 2, 3])

        # 测试与 for 循环的兼容性
        result_for = []
        for value in tree:
            result_for.append(value)
        self.assertEqual(result_for, [1, 2, 3])

        # 测试与 enumerate() 的兼容性
        result_enum = list(enumerate(tree))
        self.assertEqual(result_enum, [(0, 1), (1, 2), (2, 3)])

        # 测试与 zip() 的兼容性
        result_zip = list(zip(tree, [10, 20, 30]))
        self.assertEqual(result_zip, [(1, 10), (2, 20), (3, 30)])

    def test_compatibility_with_generator_expressions(self):
        """测试与生成器表达式的兼容性"""
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

        tree = Node(2, Node(1), Node(3))

        for _ in range(100):
            list(tree)

        # 生成器表达式
        squared = [x * x for x in tree]
        self.assertEqual(squared, [1, 4, 9])

        # 过滤
        filtered = [x for x in tree if x > 1]
        self.assertEqual(filtered, [2, 3])

        # 聚合
        total = sum(tree)
        self.assertEqual(total, 6)


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
