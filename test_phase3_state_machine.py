#!/usr/bin/env python3
"""
Phase 3.2 状态机内联 TDD 测试
"""

import os
import sys
import time
import unittest

os.environ['PYTHONJITHUGEPAGES'] = '0'
os.environ['PYTHONJIT'] = '1'

from cinderx import jit

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


class TestStateMachineInline(unittest.TestCase):
    def test_depth_3_correctness(self):
        """T1: depth=3 正确性测试"""
        tree = build_tree(3)

        def traverse():
            return list(tree)

        jit.force_compile(traverse)
        result = traverse()

        # 验证结果正确
        expected = list(tree)
        self.assertEqual(result, expected)

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

        print(f"\n  depth=5: {elapsed:.4f} ms")
        # 目标: < 0.002 ms (3x 改进)
        self.assertLess(elapsed, 0.002)
