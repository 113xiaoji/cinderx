#!/usr/bin/env python3
"""
Phase 3.2 状态机内联 TDD 测试

探针测试策略：
- 使用 g_state_machine_pass_triggered 计数器验证状态机 pass 是否被触发
- 这区分了 "pass 没有触发" 和 "pass 触发了但有 bug" 两种情况

环境要求：
- PYTHONJITHUGEPAGES=0 (macOS 必须)
- PYTHONJIT=1
"""

import os
import unittest
import faulthandler

faulthandler.enable()

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
    """模块级定义的树节点 - 使用 StaticPython 的 CheckField/LoadField"""
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


def in_order_values(node):
    """参考实现：递归收集中序遍历值"""
    if node is None:
        return []
    return in_order_values(node.left) + [node.value] + in_order_values(node.right)


class TestStateMachine(unittest.TestCase):
    """状态机内联测试

    注意：需要 JIT 可用。在 macOS 上需要 build_ext --inplace 构建。
    使用 compile_after_n_calls(1) 代替 force_compile，因为 force_compile
    在状态机生成时会导致 SIGSEGV。
    """

    @classmethod
    def setUpClass(cls):
        if not jit.is_enabled():
            raise unittest.SkipTest("JIT 不可用，跳过测试")

    def setUp(self):
        reset_state_machine_pass_triggered()

    def test_00_probe_pass_triggered(self):
        """T0: 验证状态机 pass 被树遍历生成器触发"""
        tree = build_tree(3)
        result = list(tree)

        # 验证基本正确性
        self.assertEqual(len(result), 7)

        # 验证 pass 被触发
        triggered = get_state_machine_pass_triggered()
        print(f"\n  状态机 pass 触发次数: {triggered}")
        self.assertGreater(
            triggered, 0,
            "TreeIterStateMachinePass 应该被触发。"
            "可能原因: 1) JIT 未启用 2) PYTHONJITTREEITERSTATEMACHINE 未设置"
        )

    def test_01_probe_not_triggered_for_non_tree(self):
        """T0b: 验证非树遍历函数不触发状态机 pass"""
        def simple_gen():
            yield 1
            yield 2

        list(simple_gen())

        triggered = get_state_machine_pass_triggered()
        self.assertEqual(
            triggered, 0,
            f"简单生成器不应触发状态机 pass，但触发了 {triggered} 次"
        )

    def test_02_probe_reset(self):
        """T0c: 验证计数器重置功能"""
        reset_state_machine_pass_triggered()
        self.assertEqual(get_state_machine_pass_triggered(), 0)

    def test_depth_3_correctness(self):
        """T1: depth=3 正确性测试"""
        tree = build_tree(3)
        result = list(tree)
        expected = in_order_values(tree)
        self.assertEqual(result, expected)

    def test_depth_5_correctness(self):
        """T2: depth=5 正确性测试"""
        tree = build_tree(5)
        result = list(tree)
        expected = in_order_values(tree)
        self.assertEqual(result, expected)
        self.assertEqual(len(result), 31)


if __name__ == '__main__':
    unittest.main()
