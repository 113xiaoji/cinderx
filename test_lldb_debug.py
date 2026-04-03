#!/usr/bin/env python3
"""使用 lldb 调试的测试脚本"""

import os
import sys

# 设置环境变量
os.environ['PYTHONJITHUGEPAGES'] = '0'
os.environ['PYTHONJIT'] = '1'
os.environ['PYTHONJITTREEITERSTATEMACHINE'] = '1'

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

# 手动编译
print("手动编译 Node.__iter__...")
jit.force_compile(Node.__iter__)

# 运行一次
tree = Node(2, Node(1), Node(3))
result = list(tree)
print(f"结果: {result}")

print("\n✓ 测试完成")
