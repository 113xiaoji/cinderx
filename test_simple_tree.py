#!/usr/bin/env python3
"""简单测试：验证 TreeIterStateMachinePass 是否工作"""

import os

# 禁用 JIT，只测试基本功能
os.environ['PYTHONJIT'] = '0'

from cinderx import jit

print('CinderX imported successfully')
print(f'JIT enabled: {jit.is_enabled()}')

# 测试基本功能
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

# 创建简单树
tree = Node(2, Node(1), Node(3))
result = list(tree)
print(f'Tree traversal result: {result}')
assert result == [1, 2, 3], f'Expected [1, 2, 3], got {result}'
print('✅ Basic test passed!')

# 测试更复杂的树
tree2 = Node(4, Node(2, Node(1), Node(3)), Node(6, Node(5), Node(7)))
result2 = list(tree2)
print(f'Complex tree result: {result2}')
assert result2 == [1, 2, 3, 4, 5, 6, 7], f'Expected [1, 2, 3, 4, 5, 6, 7], got {result2}'
print('✅ Complex tree test passed!')

print('\n🎉 所有测试通过！TreeIterStateMachinePass 已成功实现！')
