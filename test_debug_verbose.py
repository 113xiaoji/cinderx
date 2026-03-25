#!/usr/bin/env python3
"""使用详细调试输出的测试脚本"""

import os

# 设置环境变量
os.environ['PYTHONJITHUGEPAGES'] = '0'
os.environ['PYTHONJIT'] = '1'
os.environ['PYTHONJITTREEITERSTATEMACHINE'] = '1'
os.environ['PYTHONJITDEBUG'] = '1'  # 启用详细调试

from cinderx import jit

print("JIT 状态:")
print(f"  enabled: {jit.is_enabled()}")
print(f"  auto: {jit.auto()}")
print()

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
try:
    jit.force_compile(Node.__iter__)
    print("✓ force_compile 成功")
except Exception as e:
    print(f"✗ force_compile 失败: {e}")
    import traceback
    traceback.print_exc()

# 运行一次
print("\n运行测试...")
tree = Node(2, Node(1), Node(3))
result = list(tree)
print(f"结果: {result}")

print("\n✓ 测试完成")
