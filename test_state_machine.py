#!/usr/bin/env python3
"""
Phase 2 State Machine Integration Tests

Tests for state machine generation in tree traversal generators.
"""

from cinderx import jit
import unittest

class TestStateMachine(unittest.TestCase):
    """状态机生成器集成测试"""

    @classmethod
    def setUpClass(cls):
        """启用 JIT"""
        jit.auto()

    def test_basic_tree_traversal(self):
        """基本树遍历（depth=1）"""
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

    def test_nested_tree_traversal(self):
        """嵌套树遍历（depth=2）"""
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

    def test_empty_left_subtree(self):
        """空左子树"""
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

        tree = Node(2, None, Node(3))
        result = list(tree)
        self.assertEqual(result, [2, 3])

    def test_empty_right_subtree(self):
        """空右子树"""
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

        tree = Node(2, Node(1))
        result = list(tree)
        self.assertEqual(result, [1, 2])

    def test_single_node(self):
        """单节点树"""
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

        tree = Node(1)
        result = list(tree)
        self.assertEqual(result, [1])

    def test_deep_tree(self):
        """深树（depth=5）"""
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

        def build_tree(depth, start_value=1):
            """构建一个二叉搜索树用于测试"""
            if depth == 0:
                return None, start_value
            left, next_value = build_tree(depth - 1, start_value)
            root = Node(next_value)
            right, final_value = build_tree(depth - 1, next_value + 1)
            root.left = left
            root.right = right
            return root, final_value

        tree, _ = build_tree(5)
        result = list(tree)

        # 验证节点数
        expected_count = 2 ** 5 - 1  # 31 nodes
        self.assertEqual(len(result), expected_count)

        # 验证是有序的（因为是二叉搜索树的中序遍历）
        self.assertEqual(result, sorted(result))

    def test_for_loop_consumption(self):
        """for 循环消费"""
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
        result = []
        for value in tree:
            result.append(value)

        self.assertEqual(result, [1, 2, 3])

    def test_multiple_iterations(self):
        """多次迭代"""
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

        # 第一次迭代
        result1 = list(tree)
        self.assertEqual(result1, [1, 2, 3])

        # 第二次迭代
        result2 = list(tree)
        self.assertEqual(result2, [1, 2, 3])

        # 第三次迭代
        result3 = list(tree)
        self.assertEqual(result3, [1, 2, 3])

if __name__ == '__main__':
    unittest.main()
