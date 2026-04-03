#!/usr/bin/env python3
"""检查 JIT 状态"""

import os
import sys

# 设置环境变量
os.environ['PYTHONJITHUGEPAGES'] = '0'
os.environ['PYTHONJIT'] = '1'
os.environ['PYTHONJITTREEITERSTATEMACHINE'] = '1'

from cinderx import jit

print(f"JIT enabled: {jit.is_enabled()}")
print(f"JIT auto mode: {jit.auto()}")

# 定义树遍历生成器
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

# 创建树
tree = Node(2, Node(1), Node(3))

# 尝试手动编译
print("\n尝试手动编译 Node.__iter__...")
try:
    jit.force_compile(Node.__iter__)
    print("✓ force_compile 成功！")
except Exception as e:
    print(f"✗ force_compile 失败: {e}")

# 测试运行
result = list(tree)
print(f"\n运行结果: {result}")

# 检查编译日志
import os.path
if os.path.exists("/tmp/jit_compile_debug.log"):
    print("\n=== JIT Compile Log ===")
    with open("/tmp/jit_compile_debug.log") as f:
        print(f.read())
else:
    print("\n❌ 没有 JIT 编译日志！")
