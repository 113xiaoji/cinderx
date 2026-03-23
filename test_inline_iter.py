#!/usr/bin/env python3
# Test script for InlineIter optimization
import time
import os

# 设置环境变量
os.environ.setdefault("PYTHONJITHUGEPAGES", "0")
os.environ.setdefault("PYTHONJIT", "1")
os.environ.setdefault("PYTHONJIT_ARM_INLINE_YIELD_FROM", "1")
os.environ.setdefault("PYTHONJITDEBUG", "0")

import cinderx.jit

cinderx.jit.enable()
print(f"JIT enabled: {cinderx.jit.is_enabled()}")

# Tree Node class
class TreeNode:
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
    """Build a complete binary tree of given depth."""
    if depth == 0:
        return TreeNode(1)
    return TreeNode(
        depth,
        build_tree(depth - 1),
        build_tree(depth - 1)
    )


def traverse_and_collect(tree):
    """Traverse tree and collect all values into a list."""
    result = []
    for x in tree:
        result.append(x)
    return result


# 标记函数为强制编译
cinderx.jit.force_compile(traverse_and_collect)


def test_inline_iter():
    print("Testing InlineIter optimization...")

    # Warm up JIT
    tree = build_tree(3)
    result = traverse_and_collect(tree)
    print(f"  Warmup (depth=3): {len(result)} values")

    # Test with different depths
    for depth in [5, 8, 10, 12]:
        tree = build_tree(depth)
        expected_count = 2 ** (depth + 1) - 1

        # Time the traversal
        n = 100
        start = time.perf_counter()
        for _ in range(n):
            result = traverse_and_collect(tree)
        elapsed = time.perf_counter() - start

        print(f"  depth={depth}: {len(result)} values (expected {expected_count}), "
              f"{n} iterations in {elapsed*1000:.2f}ms ({elapsed/n*1000:.4f}ms/iter)")
        assert len(result) == expected_count, f"Expected {expected_count}, got {len(result)}"

    print("All tests passed!")


if __name__ == "__main__":
    test_inline_iter()
