#!/usr/bin/env python3
"""
Phase 3.2 状态机内联 TDD 测试

探针测试策略：
- 使用 g_state_machine_pass_triggered 计数器验证状态机 pass 是否被触发
- 这区分了 "pass 没有触发" 和 "pass 触发了但有 bug" 两种情况
"""

import os
import time
import unittest

os.environ['PYTHONJITHUGEPAGES'] = '0'
os.environ['PYTHONJIT'] = '1'
os.environ['PYTHONJITTREEITERSTATEMACHINE'] = '1'

from cinderx import jit
from cinderx import (
    get_state_machine_pass_triggered,
    reset_state_machine_pass_triggered,
)

jit.auto()


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
    return Node(depth, build_tree(depth - 1), build_tree(depth - 1))


class TestStateMachineProbe(unittest.TestCase):
    """探针测试：验证状态机 pass 是否被触发

    注意：这些测试需要 JIT 可用（Linux x86_64 或 aarch64）。
    在 macOS 上 JIT 被禁用，这些测试会被跳过。
    """

    @classmethod
    def setUpClass(cls):
        if not jit.is_enabled():
            raise unittest.SkipTest("JIT 不可用，跳过探针测试（需要 Linux）")

    def setUp(self):
        reset_state_machine_pass_triggered()

    def test_pass_triggered_by_tree_iter(self):
        """T0: 验证树遍历生成器触发状态机 pass"""
        tree = build_tree(3)

        # 重置计数器
        reset_state_machine_pass_triggered()
        self.assertEqual(get_state_machine_pass_triggered(), 0)

        # 强制编译并执行
        def traverse():
            return list(tree)

        jit.force_compile(traverse)
        traverse()

        # 验证 pass 被触发
        triggered = get_state_machine_pass_triggered()
        print(f"\n  状态机 pass 触发次数: {triggered}")
        self.assertGreater(
            triggered, 0,
            "TreeIterStateMachinePass 应该被触发但没有。"
            "可能原因: 1) pass 未注册到编译管线 2) 模式检测失败"
        )

    def test_pass_not_triggered_for_non_tree(self):
        """T0b: 验证非树遍历函数不触发状态机 pass"""
        reset_state_machine_pass_triggered()

        def simple_gen():
            yield 1
            yield 2
            yield 3

        jit.force_compile(simple_gen)
        list(simple_gen())

        # 简单生成器不应该触发状态机 pass
        triggered = get_state_machine_pass_triggered()
        self.assertEqual(
            triggered, 0,
            f"简单生成器不应该触发状态机 pass，但触发了 {triggered} 次"
        )

    def test_probe_reset(self):
        """T0c: 验证计数器重置功能"""
        reset_state_machine_pass_triggered()
        self.assertEqual(get_state_machine_pass_triggered(), 0)


class TestStateMachineCorrectness(unittest.TestCase):
    """正确性测试（在探针测试通过后有意义）"""

    @classmethod
    def setUpClass(cls):
        if not jit.is_enabled():
            raise unittest.SkipTest("JIT 不可用，跳过正确性测试（需要 Linux）")

    def setUp(self):
        reset_state_machine_pass_triggered()

    def test_depth_3_correctness(self):
        """T1: depth=3 正确性测试"""
        tree = build_tree(3)

        def traverse():
            return list(tree)

        jit.force_compile(traverse)
        result = traverse()

        # 验证结果正确（无论走状态机还是标准路径）
        expected = list(tree)
        self.assertEqual(result, expected)
        self.assertEqual(len(result), 7)

    def test_depth_5_correctness(self):
        """T2: depth=5 正确性测试"""
        tree = build_tree(5)

        def traverse():
            return list(tree)

        jit.force_compile(traverse)
        result = traverse()

        expected = list(tree)
        self.assertEqual(len(result), 31)
        self.assertEqual(result, expected)

    def test_depth_5_performance(self):
        """T3: depth=5 性能测试（目标 2-3x）"""
        tree = build_tree(5)
        iterations = 100

        def traverse():
            return list(tree)

        jit.force_compile(traverse)

        # 预热
        for _ in range(10):
            traverse()

        # 测量
        start = time.perf_counter()
        for _ in range(iterations):
            result = traverse()
        elapsed = (time.perf_counter() - start) * 1000 / iterations

        triggered = get_state_machine_pass_triggered()
        print(f"\n  depth=5: {elapsed:.4f} ms (状态机 pass 触发: {triggered})")
        # 目标: < 0.002 ms (2-3x 改进)
        self.assertLess(elapsed, 0.002)


if __name__ == '__main__':
    unittest.main()
