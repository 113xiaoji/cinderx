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

    # --- 防护用例：捕获 hasArbitraryExecution/寄存器冲突等回归 ---

    def test_depth_1_to_12_sequential(self):
        """T3: 连续遍历 depth 1-12（暴露循环迭代稳定性问题）

        背景：hasArbitraryExecution 过度优化导致 depth>=3 结果错误，
        但单独跑 depth=3 时可能因构建缓存而通过。
        连续遍历能确保使用新编译的二进制。
        """
        for d in range(1, 13):
            tree = build_tree(d)
            result = list(tree)
            expected = in_order_values(tree)
            self.assertEqual(
                result, expected,
                f"depth={d} 遍历错误: got {result[:10]}{'...' if len(result) > 10 else ''}, "
                f"expected {len(expected)} nodes"
            )

    def test_repeated_iteration_same_tree(self):
        """T4: 同一棵树多次迭代（暴露生成器/GenDataFooter 重用问题）

        背景：GenDataFooter 从 free-list 分配时可能有未初始化字段。
        多次迭代会回收再分配 GenDataFooter，暴露初始化遗漏。
        """
        tree = build_tree(5)
        expected = in_order_values(tree)
        for i in range(10):
            result = list(tree)
            self.assertEqual(
                result, expected,
                f"第 {i+1} 次迭代结果错误"
            )

    def test_sequential_different_depths(self):
        """T5: 不同深度交替遍历（暴露状态机状态残留问题）

        背景：如果 GenDataFooter 的 stack_top 等字段在回收后未清零，
        后续分配可能继承脏数据。
        """
        depths = [1, 3, 5, 2, 8, 4, 10, 7, 12, 6]
        for d in depths:
            tree = build_tree(d)
            result = list(tree)
            expected = in_order_values(tree)
            self.assertEqual(
                result, expected,
                f"depth={d} (序列: {depths}) 遍历错误"
            )

    def test_performance_not_degraded(self):
        """T6: 状态机不能比无状态机更慢

        背景：某些优化（如 hasArbitraryExecution 错误标记）可能导致
        正确但性能严重退化的行为。
        """
        import time
        import statistics

        tree = build_tree(10)  # 1023 节点

        # warmup
        for _ in range(3):
            list(tree)

        # 测量当前状态（状态机开启）
        times = []
        for _ in range(5):
            t0 = time.perf_counter_ns()
            list(tree)
            times.append(time.perf_counter_ns() - t0)

        median_us = statistics.median(times) / 1000

        # 1023 节点的状态机遍历应在合理时间内完成
        # 无状态机时约 300µs，状态机应 < 50µs
        # 如果 > 200µs，说明可能有问题
        self.assertLess(
            median_us, 200,
            f"depth=10 遍历耗时 {median_us:.1f}µs，"
            f"可能存在性能退化（预期 < 50µs，上限 200µs）"
        )


if __name__ == '__main__':
    unittest.main()
